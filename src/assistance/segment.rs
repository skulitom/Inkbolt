//! Original seeded color/edge selection with an exact integer minimum-cut certificate.
use crate::{Error, assets, control::Control, masks, model::*, render, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{HashSet, VecDeque},
    path::Path,
};

pub const MAX_PIXELS: usize = 65_536;
pub const MAX_SEEDS: usize = 32;
pub const MAX_WORK: u64 = 67_108_864;
fn default_weight() -> u32 {
    4096
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_ASSISTANCE", message)
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Options {
    pub foreground: Vec<[u32; 2]>,
    pub background: Vec<[u32; 2]>,
    #[serde(default = "default_weight")]
    pub smoothness: u32,
    #[serde(default = "default_weight")]
    pub edge_scale: u32,
    #[serde(default)]
    pub include_costs: bool,
}
struct Work<'a> {
    count: u64,
    control: &'a Control,
}
impl Work<'_> {
    fn add(&mut self, count: u64) -> Result<(), Error> {
        let before = self.count;
        self.count += count;
        if self.count > MAX_WORK {
            return Err(Error::new(
                "RESOURCE_LIMIT",
                "Local selection exceeds 67108864 work units",
            ));
        }
        if self.count >> 11 != before >> 11 {
            self.control.check()?;
        }
        Ok(())
    }
}
struct Grid {
    width: u32,
    height: u32,
    bytes: Vec<u8>,
    transform: Matrix,
}
fn grid(document: &Document, id: &str, root: Option<&Path>) -> Result<Grid, Error> {
    let i = scene::index(document, id)?;
    crate::pixel_warps::reject_native(&document.items[i])?;
    match &document.items[i].content {
        Content::Samples { grid } => {
            if grid.profile.is_some() {
                return Err(Error::new(
                    "PROFILE_CONVERSION_REQUIRED",
                    "Local selection requires explicit sample_profile conversion to working sRGB",
                ));
            }
            if grid.depth != crate::samples::Depth::U8 {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "Local selection requires explicit conversion of high-depth samples to encoded eight-bit input",
                ));
            }
            size(grid.width, grid.height)?;
            let data = render::unhex(&grid.data_hex);
            let bytes = match grid.channels {
                crate::samples::Channels::Rgba => data,
                crate::samples::Channels::GrayAlpha => data
                    .as_chunks::<2>()
                    .0
                    .iter()
                    .flat_map(|p| [p[0], p[0], p[0], p[1]])
                    .collect(),
            };
            Ok(Grid {
                width: grid.width,
                height: grid.height,
                bytes,
                transform: identity(),
            })
        }
        Content::Raster {
            width,
            height,
            rgba_hex,
            ..
        } => {
            size(*width, *height)?;
            Ok(Grid {
                width: *width,
                height: *height,
                bytes: render::unhex(rgba_hex),
                transform: identity(),
            })
        }
        Content::Image {
            asset_id,
            width,
            height,
            crop,
            ..
        } => {
            let asset = &document.assets[asset_id];
            let crop = assets::crop(asset.width, asset.height, *crop)?;
            size(crop.width, crop.height)?;
            let pixels = assets::load(asset, root)?;
            let mut bytes = Vec::with_capacity(crop.width as usize * crop.height as usize * 4);
            for y in crop.y..crop.y + crop.height {
                let start = (y as usize * pixels.width as usize + crop.x as usize) * 4;
                bytes.extend_from_slice(&pixels.rgba[start..start + crop.width as usize * 4]);
            }
            Ok(Grid {
                width: crop.width,
                height: crop.height,
                bytes,
                transform: [
                    width / crop.width as f64,
                    0.0,
                    0.0,
                    height / crop.height as f64,
                    0.0,
                    0.0,
                ],
            })
        }
        _ => Err(Error::new(
            "UNSUPPORTED",
            "Local selection requires an inline eight-bit pixel layer or a verified RGBA8 image asset",
        )),
    }
}
fn size(width: u32, height: u32) -> Result<(), Error> {
    if width == 0 || height == 0 || width as u64 * height as u64 > MAX_PIXELS as u64 {
        return Err(Error::new(
            "RESOURCE_LIMIT",
            "Local selection requires 1..65536 native pixels",
        ));
    }
    Ok(())
}
fn feature(p: &[u8; 4]) -> [i64; 4] {
    let a = p[3] as i64;
    [
        (p[0] as i64 * a + 127) / 255,
        (p[1] as i64 * a + 127) / 255,
        (p[2] as i64 * a + 127) / 255,
        a,
    ]
}
fn distance(a: [i64; 4], b: [i64; 4]) -> u64 {
    a.into_iter()
        .zip(b)
        .map(|(a, b)| ((a - b) * (a - b)) as u64)
        .sum()
}
#[derive(Clone, Copy)]
struct Edge {
    to: usize,
    reverse: usize,
    capacity: u64,
}
struct Graph {
    edges: Vec<Vec<Edge>>,
}
impl Graph {
    fn edge(&mut self, from: usize, to: usize, capacity: u64, reverse_capacity: u64) {
        let reverse = self.edges[to].len();
        let back = self.edges[from].len();
        self.edges[from].push(Edge {
            to,
            reverse,
            capacity,
        });
        self.edges[to].push(Edge {
            to: from,
            reverse: back,
            capacity: reverse_capacity,
        });
    }
    fn levels(&self, source: usize, work: &mut Work<'_>) -> Result<Vec<i32>, Error> {
        let mut levels = vec![-1; self.edges.len()];
        let mut queue = VecDeque::from([source]);
        levels[source] = 0;
        while let Some(u) = queue.pop_front() {
            for edge in &self.edges[u] {
                work.add(1)?;
                if edge.capacity > 0 && levels[edge.to] < 0 {
                    levels[edge.to] = levels[u] + 1;
                    queue.push_back(edge.to);
                }
            }
        }
        Ok(levels)
    }
    fn solve(
        &mut self,
        source: usize,
        sink: usize,
        work: &mut Work<'_>,
    ) -> Result<(u64, Vec<bool>), Error> {
        let mut flow = 0;
        loop {
            let mut levels = self.levels(source, work)?;
            if levels[sink] < 0 {
                return Ok((flow, levels.into_iter().map(|v| v >= 0).collect()));
            }
            let mut current = vec![0; self.edges.len()];
            let mut nodes = vec![source];
            let mut path: Vec<(usize, usize)> = Vec::new();
            while let Some(&u) = nodes.last() {
                work.add(1)?;
                if u == sink {
                    let amount = path
                        .iter()
                        .map(|&(v, k)| self.edges[v][k].capacity)
                        .min()
                        .unwrap();
                    work.add(path.len() as u64 * 2)?;
                    for &(v, k) in &path {
                        let edge = self.edges[v][k];
                        self.edges[v][k].capacity -= amount;
                        self.edges[edge.to][edge.reverse].capacity += amount;
                    }
                    flow += amount;
                    nodes.clear();
                    nodes.push(source);
                    path.clear();
                    continue;
                }
                while current[u] < self.edges[u].len() {
                    work.add(1)?;
                    let edge = self.edges[u][current[u]];
                    if edge.capacity > 0 && levels[edge.to] == levels[u] + 1 {
                        break;
                    }
                    current[u] += 1;
                }
                if current[u] == self.edges[u].len() {
                    levels[u] = -1;
                    nodes.pop();
                    if let Some((parent, _)) = path.pop() {
                        current[parent] += 1;
                    }
                } else {
                    path.push((u, current[u]));
                    nodes.push(self.edges[u][current[u]].to);
                }
            }
        }
    }
}

pub fn inspect(
    document: &Document,
    id: &str,
    options: &Options,
    root: Option<&Path>,
    control: &Control,
) -> Result<Value, Error> {
    Ok(evaluate(document, id, options, root, control)?.1)
}
fn evaluate(
    document: &Document,
    id: &str,
    options: &Options,
    root: Option<&Path>,
    control: &Control,
) -> Result<(masks::Mask, Value), Error> {
    control.check()?;
    validate(document)?;
    if document.color_space != ColorSpace::Srgb {
        return Err(Error::new(
            "UNSUPPORTED",
            "Local selection currently requires encoded sRGB input",
        ));
    }
    if options.smoothness > 65535
        || !(1..=260100).contains(&options.edge_scale)
        || options.foreground.is_empty()
        || options.background.is_empty()
        || options.foreground.len() > MAX_SEEDS
        || options.background.len() > MAX_SEEDS
    {
        return Err(invalid(
            "Provide 1..32 seeds per class, smoothness 0..65535 and edge_scale 1..260100",
        ));
    }
    let grid = grid(document, id, root)?;
    let n = grid.width as usize * grid.height as usize;
    let mut seen = HashSet::new();
    let mut seeds = [Vec::new(), Vec::new()];
    for (class, values) in [&options.foreground, &options.background]
        .into_iter()
        .enumerate()
    {
        for &[x, y] in values {
            if x >= grid.width || y >= grid.height || !seen.insert([x, y]) {
                return Err(invalid(
                    "Seed coordinates must be unique across both classes and inside the native cropped grid",
                ));
            }
            seeds[class].push(y as usize * grid.width as usize + x as usize);
        }
    }
    let features: Vec<_> = grid.bytes.as_chunks::<4>().0.iter().map(feature).collect();
    let mut work = Work { count: 0, control };
    let mut costs = Vec::with_capacity(n);
    for &pixel in &features {
        let mut cost = [0; 2];
        for class in 0..2 {
            work.add(seeds[class].len() as u64 * 4)?;
            cost[class] = seeds[class]
                .iter()
                .map(|&p| distance(pixel, features[p]))
                .min()
                .unwrap();
        }
        costs.push(cost);
    }
    let mut neighbors = Vec::new();
    for y in 0..grid.height as usize {
        for x in 0..grid.width as usize {
            let u = y * grid.width as usize + x;
            for v in [
                if x + 1 < grid.width as usize {
                    Some(u + 1)
                } else {
                    None
                },
                if y + 1 < grid.height as usize {
                    Some(u + grid.width as usize)
                } else {
                    None
                },
            ]
            .into_iter()
            .flatten()
            {
                work.add(5)?;
                let capacity = options.smoothness as u64 * options.edge_scale as u64
                    / (options.edge_scale as u64 + distance(features[u], features[v]));
                neighbors.push((u, v, capacity));
            }
        }
    }
    // This strict upper bound exceeds every feasible finite-labeling energy.
    let hard = 1
        + costs.iter().map(|c| c[0].max(c[1])).sum::<u64>()
        + neighbors.iter().map(|n| n.2).sum::<u64>();
    for &p in &seeds[0] {
        costs[p][1] = hard;
    }
    for &p in &seeds[1] {
        costs[p][0] = hard;
    }
    let source = n;
    let sink = n + 1;
    let mut graph = Graph {
        edges: vec![Vec::new(); n + 2],
    };
    for (p, &[foreground, background]) in costs.iter().enumerate() {
        work.add(2)?;
        graph.edge(source, p, background, 0);
        graph.edge(p, sink, foreground, 0);
    }
    for &(u, v, w) in &neighbors {
        work.add(1)?;
        graph.edge(u, v, w, w);
    }
    let (flow, reachable) = graph.solve(source, sink, &mut work)?;
    let data_cost = costs
        .iter()
        .enumerate()
        .map(|(p, c)| c[usize::from(!reachable[p])])
        .sum::<u64>();
    let boundary_cost = neighbors
        .iter()
        .filter(|&&(u, v, _)| reachable[u] != reachable[v])
        .map(|n| n.2)
        .sum::<u64>();
    if data_cost + boundary_cost != flow
        || seeds[0].iter().any(|&p| !reachable[p])
        || seeds[1].iter().any(|&p| reachable[p])
    {
        return Err(Error::new(
            "ASSISTANCE_SOLVER",
            "Local selection failed its minimum-cut or hard-seed certificate",
        ));
    }
    let mask = masks::Mask {
        constant: false,
        width: grid.width,
        height: grid.height,
        gray_hex: render::hex(
            &reachable[..n]
                .iter()
                .map(|&v| if v { 255 } else { 0 })
                .collect::<Vec<_>>(),
        ),
        transform: grid.transform,
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
    control.check()?;
    let source_bytes =
        serde_json::to_vec(document).map_err(|_| invalid("Unable to identify selection source"))?;
    let mut report = json!({"document_id":document.id,"revision":document.revision,"id":id,"source_snapshot_sha256":assets::sha256(&source_bytes),"source_pixels_sha256":assets::sha256(&grid.bytes),"source_preserved":true,"algorithm":"seeded_color_cut_v1","options":options,"width":grid.width,"height":grid.height,"mask":mask,"foreground_pixels":reachable[..n].iter().filter(|&&v| v).count(),"minimum_energy":flow,"max_flow":flow,"data_cost":data_cost,"boundary_cost":boundary_cost,"hard_seed_cost":hard,"work":work.count,"dependencies":{"execution":"builtin_cpu","models":[],"gpu":false,"network":false},"scope":"native_unfiltered_RGBA8_pixels;binary_foreground_mask;seeds_in_cropped_native_grid;no_semantic_model_or_alpha_matting","tie_rule":"smallest_foreground_set_among_minimum_cuts"});
    if options.include_costs {
        report["class_costs"] = json!(costs);
        report["neighbor_costs"] = json!(neighbors);
    }
    Ok((mask, report))
}

pub(crate) fn apply(
    document: &mut Document,
    id: &str,
    options: &Options,
    replace_existing: bool,
    root: Option<&Path>,
    control: &Control,
) -> Result<Value, Error> {
    let i = scene::index(document, id)?;
    scene::check_unlocked(document, i, true)?;
    if document.items[i].mask.is_some() && !replace_existing {
        return Err(invalid(
            "An existing pixel mask requires explicit replace_existing",
        ));
    }
    let (mask, report) = evaluate(document, id, options, root, control)?;
    document.items[i].mask = Some(Box::new(mask));
    Ok(report)
}
