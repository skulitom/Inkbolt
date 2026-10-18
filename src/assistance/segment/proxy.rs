//! Declared coarse sampling followed by an exact conditional native cut.
use super::{Cut, Work, assets, cut, distance, feature, invalid, limits};
use crate::native_pixels::Budget;
use crate::{Error, control::Control, masks, model::*, render, scene};
use base64::{Engine, engine::general_purpose::STANDARD};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{collections::HashSet, path::Path};
mod band;
mod source;

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Options {
    /// Native cell size; explicit sampling can miss features outside the band.
    pub step: u32,
    /// Native boundary dilation radius; oversized graphs fail explicitly.
    pub refine_radius: u32,
    #[serde(default)]
    pub include_preview: bool,
}

struct Grid {
    width: u32,
    height: u32,
    step: u32,
    columns: u32,
    rows: u32,
}
impl Grid {
    fn new(width: u32, height: u32, step: u32) -> Result<Self, Error> {
        let columns = width.div_ceil(step);
        let rows = height.div_ceil(step);
        if columns as u64 * rows as u64 > limits::MAX_PIXELS as u64 {
            return Err(crate::model::limit(
                "Proxy selection exceeds coarse node limit; use a larger step or smaller region",
            ));
        }
        Ok(Self {
            width,
            height,
            step,
            columns,
            rows,
        })
    }
    fn len(&self) -> usize {
        self.columns as usize * self.rows as usize
    }
    fn index(&self, x: u32, y: u32) -> usize {
        (y * self.columns + x) as usize
    }
    fn cell(&self, x: u32, y: u32) -> (u32, u32, u32, u32) {
        (
            x * self.step,
            y * self.step,
            ((x + 1) * self.step).min(self.width),
            ((y + 1) * self.step).min(self.height),
        )
    }
    fn center(&self, x: u32, y: u32) -> [u32; 2] {
        let (x0, y0, x1, y1) = self.cell(x, y);
        [x0 + (x1 - x0 - 1) / 2, y0 + (y1 - y0 - 1) / 2]
    }
    fn label(&self, labels: &[bool], x: u32, y: u32) -> bool {
        labels[self.index(x / self.step, y / self.step)]
    }
}

fn admit(coarse: usize, fine: usize, source: u64, costs: bool) -> Result<u64, Error> {
    let coarse = coarse as u64;
    let fine = fine as u64;
    let memory = source
        + limits::PROXY_FIXED_BYTES
        + (coarse * limits::WORKING_BYTES_PER_PIXEL).max(
            coarse * limits::PROXY_RETAINED_BYTES_PER_PIXEL + fine * limits::REFINE_BYTES_PER_PIXEL,
        )
        + if costs {
            (coarse + fine) * limits::PROXY_COST_BYTES_PER_PIXEL
        } else {
            0
        };
    if memory > limits::PROXY_MEMORY_BYTES {
        return Err(crate::model::limit(
            "Proxy selection exceeds processing memory bound; reduce the region, boundary or optional cost detail",
        ));
    }
    Ok(memory)
}

fn unary(
    features: &[[i64; 4]],
    prototypes: &[Vec<[i64; 4]>; 2],
    work: &mut Work<'_>,
) -> Result<Vec<[u64; 2]>, Error> {
    features
        .iter()
        .map(|&pixel| {
            let mut costs = [0; 2];
            for class in 0..2 {
                work.add(prototypes[class].len() as u64 * 4)?;
                costs[class] = prototypes[class]
                    .iter()
                    .map(|&p| distance(pixel, p))
                    .min()
                    .unwrap();
            }
            Ok(costs)
        })
        .collect()
}

fn edge(a: [i64; 4], b: [i64; 4], options: &super::Options, scale: u64) -> u64 {
    let strength = options.smoothness as u128 * scale as u128;
    let scale = options.edge_scale as u128 * scale as u128;
    (strength * scale / (scale + distance(a, b) as u128)) as u64
}

fn certificate(cut: &Cut) -> Value {
    json!({"minimum_energy":cut.flow.to_string(),"max_flow":cut.flow.to_string(),
        "data_cost":cut.data_cost.to_string(),"boundary_cost":cut.boundary_cost.to_string(),"hard_seed_cost":cut.hard.to_string(),
        "integer_encoding":"decimal_string","tie_rule":"smallest_foreground_set_among_minimum_cuts"})
}

fn costs_json(costs: &[[u64; 2]], neighbors: &[(usize, usize, u64)]) -> Value {
    json!({"class_costs":costs.iter().map(|c|c.map(|v|v.to_string())).collect::<Vec<_>>(),
        "neighbor_costs":neighbors.iter().map(|&(a,b,w)|json!([a,b,w.to_string()])).collect::<Vec<_>>()})
}

pub(super) fn compact(report: &mut Value) {
    let fields = report.as_object_mut().unwrap();
    fields.remove("costs");
    fields.remove("preview");
    fields.insert("cost_arrays_included".into(), json!(false));
    fields.insert("preview_included".into(), json!(false));
}

pub(super) fn evaluate(
    document: &Document,
    id: &str,
    options: &super::Options,
    proxy: &Options,
    root: Option<&Path>,
    work: &mut Work<'_>,
) -> Result<(masks::Mask, Value), Error> {
    if !(1..=limits::MAX_PROXY_STEP).contains(&proxy.step)
        || !(1..=limits::MAX_REFINE_RADIUS).contains(&proxy.refine_radius)
    {
        return Err(invalid(
            "Proxy step and refinement radius must be positive and within declared limits",
        ));
    }
    let mut source = source::Source::new(document, id, options.region, root, proxy, work)?;
    let region = source.region;
    let grid = Grid::new(region.width, region.height, proxy.step)?;
    let mut seen = HashSet::new();
    let mut seed_coordinates = [Vec::new(), Vec::new()];
    let mut coarse_seeds = [Vec::new(), Vec::new()];
    for (class, coordinates) in [&options.foreground, &options.background]
        .into_iter()
        .enumerate()
    {
        for &[x, y] in coordinates {
            if x < region.x
                || y < region.y
                || x - region.x >= region.width
                || y - region.y >= region.height
                || !seen.insert([x, y])
            {
                return Err(invalid(
                    "Seeds must be unique and inside the requested cropped-native region",
                ));
            }
            let (x, y) = (x - region.x, y - region.y);
            seed_coordinates[class].push([x, y]);
            let cell = grid.index(x / grid.step, y / grid.step);
            if class == 1 && coarse_seeds[0].contains(&cell) {
                return Err(invalid(
                    "Opposite seed classes share a proxy cell; choose a finer sampling step",
                ));
            }
            if !coarse_seeds[class].contains(&cell) {
                coarse_seeds[class].push(cell);
            }
        }
    }
    let prototypes = [
        source.features(&seed_coordinates[0], work)?,
        source.features(&seed_coordinates[1], work)?,
    ];
    let centers: Vec<_> = (0..grid.rows)
        .flat_map(|y| (0..grid.columns).map(move |x| (x, y)))
        .map(|(x, y)| grid.center(x, y))
        .collect();
    let features = source.features(&centers, work)?;
    let mut coarse_costs = unary(&features, &prototypes, work)?;
    let mut neighbors = Vec::with_capacity(grid.len() * 2);
    for y in 0..grid.rows {
        for x in 0..grid.columns {
            let i = grid.index(x, y);
            let (x0, y0, x1, y1) = grid.cell(x, y);
            for cost in &mut coarse_costs[i] {
                *cost *= (x1 - x0) as u64 * (y1 - y0) as u64;
            }
            for (j, length) in [
                (
                    if x + 1 < grid.columns {
                        Some(i + 1)
                    } else {
                        None
                    },
                    y1 - y0,
                ),
                (
                    if y + 1 < grid.rows {
                        Some(i + grid.columns as usize)
                    } else {
                        None
                    },
                    x1 - x0,
                ),
            ] {
                if let Some(j) = j {
                    work.add(5)?;
                    neighbors.push((
                        i,
                        j,
                        edge(features[i], features[j], options, source.scale) * length as u64,
                    ));
                }
            }
        }
    }
    let coarse = cut(&mut coarse_costs, &neighbors, &coarse_seeds, work)?;
    let mut costs = Value::Null;
    // Account for requested JSON costs before constructing them; coarse fields
    // are retained while the fine graph is built and serialized.
    admit(grid.len(), 0, source.memory, options.include_costs)?;
    if options.include_costs {
        costs = json!({"coarse":costs_json(&coarse_costs,&neighbors)});
    }
    drop(features);
    drop(coarse_costs);
    drop(neighbors);
    let band = band::Band::new(&grid, &coarse.labels, proxy.refine_radius, work)?;
    let memory = admit(
        grid.len(),
        band.coordinates.len(),
        source.memory,
        options.include_costs,
    )?;
    let features = source.features(&band.coordinates, work)?;
    let mut fine_costs = unary(&features, &prototypes, work)?;
    let mut neighbors = Vec::with_capacity(band.coordinates.len() * 2);
    let mut fixed_queries = Vec::new();
    let mut fixed_owners = Vec::new();
    for (i, &[x, y]) in band.coordinates.iter().enumerate() {
        for (xx, yy) in [
            (x.wrapping_sub(1), y),
            (x + 1, y),
            (x, y.wrapping_sub(1)),
            (x, y + 1),
        ] {
            if xx >= grid.width || yy >= grid.height {
                continue;
            }
            work.add(5)?;
            if let Some(j) = band.index(xx, yy) {
                if i < j {
                    neighbors.push((i, j, edge(features[i], features[j], options, source.scale)));
                }
            } else {
                fixed_queries.push([xx, yy]);
                fixed_owners.push(i);
            }
        }
    }
    let fixed_features = source.features(&fixed_queries, work)?;
    for ((&[x, y], &i), &pixel) in fixed_queries.iter().zip(&fixed_owners).zip(&fixed_features) {
        let fixed = grid.label(&coarse.labels, x, y);
        fine_costs[i][usize::from(fixed)] += edge(features[i], pixel, options, source.scale);
    }
    drop(features);
    drop(fixed_queries);
    drop(fixed_owners);
    drop(fixed_features);
    let fine_seeds = seed_coordinates.map(|coordinates| {
        coordinates
            .into_iter()
            .filter_map(|[x, y]| band.index(x, y))
            .collect()
    });
    let initial: Vec<_> = band
        .coordinates
        .iter()
        .map(|&[x, y]| grid.label(&coarse.labels, x, y))
        .collect();
    let before = fine_costs
        .iter()
        .enumerate()
        .map(|(i, c)| c[usize::from(!initial[i])])
        .sum::<u64>()
        + neighbors
            .iter()
            .filter(|&&(i, j, _)| initial[i] != initial[j])
            .map(|e| e.2)
            .sum::<u64>();
    let fine = cut(&mut fine_costs, &neighbors, &fine_seeds, work)?;
    if fine.flow > before {
        return Err(Error::new(
            "ASSISTANCE_SOLVER",
            "Native boundary refinement increased the conditional energy",
        ));
    }
    if options.include_costs {
        costs["refinement"] = costs_json(&fine_costs, &neighbors);
        costs["refinement"]["coordinates"] = json!(band.coordinates);
        costs["refinement"]["initial_labels"] = json!(initial);
        costs["coarse"]["labels"] = json!(coarse.labels);
    }
    drop(fine_costs);
    drop(neighbors);
    drop(initial);
    let source_preparation = work.preparation.work;
    // Output authoring, hashing and native block construction are a global
    // preparation pass, separately charged from graph optimization.
    work.prepare(region.width as u64 * region.height as u64 * 3)?;
    let mut digest = Sha256::new();
    let mut selected = 0u64;
    let mut bounds = [region.width, region.height, 0, 0];
    let candidate = crate::scalar_store::Candidate::from_private_rows(
        crate::scalar_store::Spec {
            width: region.width,
            height: region.height,
        },
        work.control,
        |y, row| {
            work.control.check()?;
            for cx in 0..grid.columns {
                let (x0, _, x1, _) = grid.cell(cx, y / grid.step);
                row[x0 as usize..x1 as usize].fill(
                    if coarse.labels[grid.index(cx, y / grid.step)] {
                        255
                    } else {
                        0
                    },
                );
            }
            for run in &band.rows[y as usize] {
                for (x, value) in row[run.x as usize..run.end as usize].iter_mut().enumerate() {
                    *value = if fine.labels[run.offset + x] { 255 } else { 0 };
                }
            }
            for (x, &value) in row.iter().enumerate() {
                if value != 0 {
                    selected += 1;
                    bounds[0] = bounds[0].min(x as u32);
                    bounds[1] = bounds[1].min(y);
                    bounds[2] = bounds[2].max(x as u32 + 1);
                    bounds[3] = bounds[3].max(y + 1);
                }
            }
            digest.update(row);
            Ok(())
        },
    )?;
    let mask = masks::Mask {
        constant: false,
        width: region.width,
        height: region.height,
        gray_hex: String::new(),
        native: Some(crate::stored_scalars::Grid::from_candidate(candidate)),
        transform: source.transform,
        linked: true,
        enabled: true,
        clip: true,
        invert: false,
        density: 1.0,
        feather: 0,
        sampling: assets::Sampling::Nearest,
    };
    mask.validate(scene::world_transform(
        document,
        scene::index(document, id)?,
    )?)?;
    let mut report = json!({"document_id":document.id,"revision":document.revision,"id":id,"algorithm":"seeded_proxy_refine_cut_v1","mode":"proxy_then_refine",
        "result_format":"proxy_selection_summary_v1","source_snapshot_sha256":assets::sha256(&serde_json::to_vec(document).map_err(|_|invalid("Unable to identify selection source"))?),
        "source":source.description,"source_preserved":true,"options":options,"region":region,"foreground_pixels":selected,
        "mask_summary":{"width":region.width,"height":region.height,"transform":source.transform,"gray_sha256":render::hex(&digest.finalize()),"storage":"native_scalar_blocks","outside_region":"zero_coverage", "bounds":if selected==0 {Value::Null} else {json!({"x":bounds[0],"y":bounds[1],"width":bounds[2]-bounds[0],"height":bounds[3]-bounds[1]})}},
        "proxy_cut":certificate(&coarse),"refinement_cut":certificate(&fine),"initial_conditional_energy":before.to_string(),
        "proxy_grid":{"width":grid.columns,"height":grid.rows,"step":grid.step,"sample":"lower_cell_center","last_cell_width":(grid.width-1)%grid.step+1,"last_cell_height":(grid.height-1)%grid.step+1},
        "refinement_pixels":band.coordinates.len(),"approximation":{"method":"cell_center_sampling_then_exact_native_boundary_cut","maximum_axis_sampling_displacement":grid.step/2,
            "refine_radius":proxy.refine_radius,"outside_band":"fixed_projected_coarse_labels","conditional_objective":"native_color_costs_and_edges_incident_to_band;outside_only_constant_excluded",
            "global_native_optimum":false,"losses":["small_features_outside_refinement_band_may_be_missed"],"semantic_accuracy_bound":Value::Null},
        "local_work":work.count,"source_preparation_work":source_preparation,"output_preparation_work":work.preparation.work-source_preparation,
        "processing_memory_bound_bytes":memory,"cost_arrays_included":options.include_costs,"preview_included":proxy.include_preview,
        "dependencies":{"execution":"builtin_cpu","models":[],"gpu":false,"network":false}});
    if options.include_costs {
        report["costs"] = costs;
    }
    if proxy.include_preview {
        let preview: Vec<_> = centers
            .iter()
            .map(|&[x, y]| {
                if band
                    .index(x, y)
                    .map_or_else(|| grid.label(&coarse.labels, x, y), |i| fine.labels[i])
                {
                    255
                } else {
                    0
                }
            })
            .collect();
        let bytes = crate::proof::scalar_png(grid.columns, grid.rows, &preview, 72.0)?;
        report["preview"] = json!({"media_type":"image/png","encoding":"base64","data":STANDARD.encode(&bytes),"sha256":assets::sha256(&bytes),"sample_sha256":assets::sha256(&preview),"width":grid.columns,"height":grid.rows,"mapping":"final_native_mask_at_proxy_grid_lower_cell_centers"});
    }
    work.control.check()?;
    Ok((mask, report))
}
