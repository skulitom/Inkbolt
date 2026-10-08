//! Original bounded exemplar repair, patch placement and guided robust correction.
use crate::{Error, assets, control::Control, geometry, model::*, render, retouch, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

pub const MAX_WORK: u64 = 67_108_864;
pub const MAX_PATCHES: usize = 4096;
fn one() -> f64 {
    1.0
}
fn radius() -> u32 {
    1
}
fn synthesized_weight() -> f64 {
    0.5
}
fn invalid(s: &str) -> Error {
    Error::new("INVALID_REPAIR", s)
}
fn quality(s: &str) -> Error {
    Error::new("REPAIR_QUALITY", s)
}
fn unit(v: f64) -> bool {
    v.is_finite() && (0.0..=1.0).contains(&v)
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Fill {
    pub source_id: String,
    pub donor_region: Option<retouch::Region>,
    #[serde(default = "radius")]
    pub patch_radius: u32,
    #[serde(default = "synthesized_weight")]
    pub synthesized_weight: f64,
    pub max_context_rms: f64,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Action {
    Patch {
        source_id: String,
        source_origin: [u32; 2],
        #[serde(default)]
        search_radius: u32,
        #[serde(default = "radius")]
        context_radius: u32,
        max_context_rms: f64,
        blend: retouch::Mode,
    },
    Fill {
        fill: Fill,
    },
    Move {
        offset: [i32; 2],
        fill: Fill,
    },
    EdgeCorrect {
        guide_id: String,
        radius: u32,
        range_sigma: f64,
        max_change_rms: f64,
        #[serde(default = "one")]
        minimum_effective_samples: f64,
    },
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Options {
    pub region: retouch::Region,
    pub action: Action,
    #[serde(default = "one")]
    pub opacity: f64,
    #[serde(default)]
    pub use_selection: bool,
    pub max_boundary_rms: Option<f64>,
}
struct Work<'a> {
    count: u64,
    control: &'a Control,
}
impl Work<'_> {
    fn add(&mut self, n: usize) -> Result<(), Error> {
        self.count += n as u64;
        if self.count > MAX_WORK {
            return Err(limit("Repair exceeds 67108864 work units"));
        }
        self.control.check()
    }
}
#[derive(Clone)]
struct Grid {
    w: usize,
    h: usize,
    bytes: Vec<u8>,
    pixels: Vec<[f64; 4]>,
}
impl Grid {
    fn read(document: &Document, id: &str) -> Result<Self, Error> {
        let i = scene::index(document, id)?;
        crate::pixel_warps::reject_native(&document.items[i])?;
        let Content::Raster {
            width,
            height,
            rgba_hex,
            ..
        } = &document.items[i].content
        else {
            return Err(Error::new(
                "INVALID_OPERATION",
                "Repair requires inline native pixel sources, targets and guides",
            ));
        };
        let bytes = render::unhex(rgba_hex);
        let pixels = bytes.as_chunks::<4>().0.iter().map(|c| pm(c)).collect();
        Ok(Self {
            w: *width as usize,
            h: *height as usize,
            bytes,
            pixels,
        })
    }
    fn hash(&self) -> String {
        assets::identity(self.w as u32, self.h as u32, &self.bytes)
    }
    fn at(&self, x: i64, y: i64) -> Option<usize> {
        if x >= 0 && y >= 0 && x < self.w as i64 && y < self.h as i64 {
            Some(y as usize * self.w + x as usize)
        } else {
            None
        }
    }
}
fn pm(c: &[u8]) -> [f64; 4] {
    let a = c[3] as f64 / 255.0;
    [
        c[0] as f64 / 255.0 * a,
        c[1] as f64 / 255.0 * a,
        c[2] as f64 / 255.0 * a,
        a,
    ]
}
fn encoded(c: [f64; 4]) -> [u8; 4] {
    let byte = |v: f64| (v.clamp(0.0, 1.0) * 255.0).round() as u8;
    let a = byte(c[3]);
    if a == 0 {
        [0; 4]
    } else {
        [byte(c[0] / c[3]), byte(c[1] / c[3]), byte(c[2] / c[3]), a]
    }
}
fn error2(a: [f64; 4], b: [f64; 4]) -> f64 {
    (0..4).map(|k| (a[k] - b[k]).powi(2)).sum::<f64>() / 4.0
}
fn region(r: &retouch::Region, w: usize, h: usize) -> Result<Vec<f64>, Error> {
    if r.width == 0
        || r.height == 0
        || r.x as u64 + r.width as u64 > w as u64
        || r.y as u64 + r.height as u64 > h as u64
    {
        return Err(invalid(
            "Repair region must be nonempty and inside its native grid",
        ));
    }
    let mask = if let Some(hex) = &r.gray_hex {
        if hex.len() != r.width as usize * r.height as usize * 2
            || !hex.bytes().all(|b| b.is_ascii_hexdigit())
        {
            return Err(invalid("Region gray_hex requires one byte per region cell"));
        }
        render::unhex(hex)
    } else {
        vec![255; r.width as usize * r.height as usize]
    };
    let mut out = vec![0.0; w * h];
    for y in 0..r.height as usize {
        for x in 0..r.width as usize {
            out[(y + r.y as usize) * w + x + r.x as usize] =
                mask[y * r.width as usize + x] as f64 / 255.0;
        }
    }
    Ok(out)
}
fn window(g: &Grid, i: usize, r: u32) -> Vec<(usize, i64, i64)> {
    let x = (i % g.w) as i64;
    let y = (i / g.w) as i64;
    let r = r as i64;
    let mut out = Vec::new();
    for dy in -r..=r {
        for dx in -r..=r {
            if let Some(j) = g.at(x + dx, y + dy) {
                out.push((j, dx, dy));
            }
        }
    }
    out
}
fn extent(ids: &[usize], w: usize) -> Option<[usize; 4]> {
    if ids.is_empty() {
        return None;
    }
    let mut b = [usize::MAX, usize::MAX, 0, 0];
    for &i in ids {
        let x = i % w;
        let y = i / w;
        b = [b[0].min(x), b[1].min(y), b[2].max(x + 1), b[3].max(y + 1)];
    }
    Some(b)
}
fn boundary(g: &Grid, weights: &[f64], pixels: &[[f64; 4]]) -> (usize, Option<f64>) {
    let mut count = 0;
    let mut sum = 0.0;
    for (i, &a) in weights.iter().enumerate() {
        if a > 0.0 {
            let x = (i % g.w) as i64;
            let y = (i / g.w) as i64;
            for (dx, dy) in [(-1, 0), (1, 0), (0, -1), (0, 1)] {
                if let Some(j) = g.at(x + dx, y + dy)
                    && weights[j] == 0.0
                {
                    count += 1;
                    sum += error2(pixels[i], g.pixels[j]);
                }
            }
        }
    }
    (
        count,
        if count > 0 {
            Some((sum / count as f64).sqrt())
        } else {
            None
        },
    )
}
fn validate_fill(f: &Fill) -> Result<(), Error> {
    if !(1..=4).contains(&f.patch_radius)
        || !unit(f.max_context_rms)
        || !f.synthesized_weight.is_finite()
        || !(0.01..=1.0).contains(&f.synthesized_weight)
    {
        return Err(invalid(
            "Fill requires radius1..4,synthesized_weight0.01..1 and max_context_rms0..1",
        ));
    }
    Ok(())
}
struct Synthesis {
    pixels: Vec<[f64; 4]>,
    receipt: Value,
}
fn synthesize(
    target: &Grid,
    source: &Grid,
    same: bool,
    weights: &[f64],
    f: &Fill,
    work: &mut Work<'_>,
) -> Result<Synthesis, Error> {
    validate_fill(f)?;
    let mut allowed = if let Some(r) = &f.donor_region {
        region(r, source.w, source.h)?
    } else {
        vec![1.0; source.w * source.h]
    };
    for (i, a) in allowed.iter_mut().enumerate() {
        if *a != 0.0 && *a != 1.0 {
            return Err(invalid("Donor regions require binary0/255 masks"));
        }
        if same && weights[i] > 0.0 {
            *a = 0.0;
        }
    }
    let n = target.w * target.h;
    let mut pending: Vec<_> = weights.iter().map(|&v| v > 0.0).collect();
    let original_pending = pending.clone();
    let mut remaining = pending.iter().filter(|&&v| v).count();
    let mut pixels = target.pixels.clone();
    let r = f.patch_radius as usize;
    let side = 2 * r + 1;
    let mut candidates = Vec::new();
    if source.w >= side && source.h >= side {
        for y in r..source.h - r {
            for x in r..source.w - r {
                work.add(side * side)?;
                if (y - r..=y + r)
                    .all(|yy| (x - r..=x + r).all(|xx| allowed[yy * source.w + xx] > 0.0))
                {
                    candidates.push(y * source.w + x);
                }
            }
        }
    }
    if remaining > 0 && candidates.is_empty() {
        return Err(quality("No complete valid donor patch is available"));
    }
    let mut decisions = Vec::new();
    let mut worst = 0.0f64;
    while remaining > 0 {
        work.control.check()?;
        if decisions.len() == MAX_PATCHES {
            return Err(limit("Repair exceeds4096synthesis patches"));
        }
        let mut best_front = None;
        let mut best_count = 0usize;
        for (i, &unknown) in pending.iter().enumerate() {
            if unknown {
                let context = window(target, i, f.patch_radius);
                work.add(context.len())?;
                let count = context.iter().filter(|(j, _, _)| !pending[*j]).count();
                if count > best_count {
                    best_count = count;
                    best_front = Some(i);
                }
            }
        }
        let center = best_front.ok_or_else(|| quality("Fill has no known surrounding context"))?;
        let context: Vec<_> = window(target, center, f.patch_radius)
            .into_iter()
            .filter(|(j, _, _)| !pending[*j])
            .collect();
        let mut best = None;
        let mut best_score = f64::INFINITY;
        let total: f64 = context
            .iter()
            .map(|(j, _, _)| {
                if original_pending[*j] {
                    f.synthesized_weight
                } else {
                    1.0
                }
            })
            .sum();
        for &candidate in &candidates {
            work.add(context.len())?;
            let x = (candidate % source.w) as i64;
            let y = (candidate / source.w) as i64;
            let mut score = 0.0;
            for &(j, dx, dy) in &context {
                let donor = source.at(x + dx, y + dy).expect("complete donor patch");
                let confidence = if original_pending[j] {
                    f.synthesized_weight
                } else {
                    1.0
                };
                score += confidence * error2(pixels[j], source.pixels[donor]);
            }
            score /= total;
            if score < best_score {
                best_score = score;
                best = Some(candidate);
            }
        }
        let donor = best.expect("nonempty donors");
        let rms = best_score.sqrt();
        worst = worst.max(rms);
        if rms > f.max_context_rms {
            return Err(quality("Best donor patch exceeds max_context_rms"));
        }
        let mut filled = 0;
        let sx = (donor % source.w) as i64;
        let sy = (donor / source.w) as i64;
        for (i, dx, dy) in window(target, center, f.patch_radius) {
            if pending[i] {
                pixels[i] =
                    source.pixels[source.at(sx + dx, sy + dy).expect("complete donor patch")];
                pending[i] = false;
                remaining -= 1;
                filled += 1;
            }
        }
        decisions.push(json!({"target_center":[center%target.w,center/target.w],"source_center":[donor%source.w,donor/source.w],"context_cells":context.len(),"context_weight":total,"context_rms":rms,"filled_pixels":filled}));
    }
    work.add(n)?;
    Ok(Synthesis {
        pixels,
        receipt: json!({"source_id":f.source_id,"source_sha256":source.hash(),"candidate_patches":candidates.len(),"maximum_context_rms":worst,"patches":decisions,"donor_policy":"frozen_complete_binary_valid_patches;self_source_excludes_entire_positive_domain","priority":"most_known_context_cells_then_target_row_major","tie":"first_source_row_major_exact_minimum","synthesized_weight":f.synthesized_weight}),
    })
}
fn write_result(
    document: &mut Document,
    index: usize,
    target: &Grid,
    values: &[[f64; 4]],
) -> Vec<usize> {
    let mut bytes = target.bytes.clone();
    let mut changed = Vec::new();
    for (i, &value) in values.iter().enumerate() {
        if value != target.pixels[i] {
            let out = encoded(value);
            if out != target.bytes[i * 4..i * 4 + 4] {
                bytes[i * 4..i * 4 + 4].copy_from_slice(&out);
                changed.push(i);
            }
        }
    }
    let Content::Raster { rgba_hex, .. } = &mut document.items[index].content else {
        unreachable!()
    };
    *rgba_hex = render::hex(&bytes);
    changed
}
pub(crate) fn apply(
    document: &mut Document,
    index: usize,
    o: &Options,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    if !unit(o.opacity) || o.max_boundary_rms.is_some_and(|v| !unit(v)) {
        return Err(invalid(
            "Repair opacity and boundary RMS limits require0..1",
        ));
    }
    let target = Grid::read(document, &document.items[index].id)?;
    let n = target.w * target.h;
    let mut weights = region(&o.region, target.w, target.h)?;
    let world = scene::world_transform(document, index)?;
    if o.use_selection {
        let s = document
            .selection
            .as_ref()
            .ok_or_else(|| invalid("use_selection requires an explicit active selection"))?;
        let gray = render::unhex(&s.gray_hex);
        for (i, a) in weights.iter_mut().enumerate() {
            let p = geometry::map(
                world,
                [(i % target.w) as f64 + 0.5, (i / target.w) as f64 + 0.5],
            );
            let x = p[0].floor();
            let y = p[1].floor();
            *a *= if x >= 0.0 && y >= 0.0 && x < document.width as f64 && y < document.height as f64
            {
                gray[y as usize * document.width as usize + x as usize] as f64 / 255.0
            } else {
                0.0
            };
        }
    }
    let ids: Vec<_> = weights
        .iter()
        .enumerate()
        .filter_map(|(i, &a)| (a > 0.0).then_some(i))
        .collect();
    let mut affected = weights.clone();
    let mut values = target.pixels.clone();
    let mut work = Work { count: 0, control };
    work.add(n)?;
    let action_receipt = match &o.action {
        Action::Patch {
            source_id,
            source_origin,
            search_radius,
            context_radius,
            max_context_rms,
            blend,
        } => {
            if *search_radius > 32
                || !(1..=4).contains(context_radius)
                || !unit(*max_context_rms)
                || source_origin.iter().any(|&v| v > 32768)
            {
                return Err(invalid(
                    "Patch requires search_radius0..32,context_radius1..4,bounded source origin and max_context_rms0..1",
                ));
            }
            let source = Grid::read(document, source_id)?;
            let mut context_flag = vec![false; n];
            for &i in &ids {
                let cells = window(&target, i, *context_radius);
                work.add(cells.len())?;
                for (j, _, _) in cells {
                    if weights[j] == 0.0 {
                        context_flag[j] = true;
                    }
                }
            }
            let context: Vec<_> = context_flag
                .iter()
                .enumerate()
                .filter_map(|(i, &v)| v.then_some(i))
                .collect();
            if !ids.is_empty() && context.is_empty() {
                return Err(quality("Patch requires unselected surrounding context"));
            }
            let mut chosen = None;
            let mut best_score = f64::INFINITY;
            let mut best_distance = i64::MAX;
            let mut valid = 0usize;
            let radius = *search_radius as i64;
            for dy in -radius..=radius {
                for dx in -radius..=radius {
                    control.check()?;
                    let sx = source_origin[0] as i64 + dx;
                    let sy = source_origin[1] as i64 + dy;
                    let tx = sx - o.region.x as i64;
                    let ty = sy - o.region.y as i64;
                    let mapped = |i: usize| {
                        source.at((i % target.w) as i64 + tx, (i / target.w) as i64 + ty)
                    };
                    work.add(ids.len() + context.len())?;
                    if !ids.iter().chain(&context).all(|&i| {
                        mapped(i).is_some_and(|j| {
                            source_id != &document.items[index].id || weights[j] == 0.0
                        })
                    }) {
                        continue;
                    }
                    valid += 1;
                    let score = if context.is_empty() {
                        0.0
                    } else {
                        context
                            .iter()
                            .map(|&i| {
                                error2(
                                    target.pixels[i],
                                    source.pixels[mapped(i).expect("validated mapping")],
                                )
                            })
                            .sum::<f64>()
                            / context.len() as f64
                    };
                    let distance = dx * dx + dy * dy;
                    if score < best_score || (score == best_score && distance < best_distance) {
                        chosen = Some([sx, sy]);
                        best_score = score;
                        best_distance = distance;
                    }
                }
            }
            let chosen = chosen.ok_or_else(|| quality("Patch has no valid source placement"))?;
            let rms = best_score.sqrt();
            if rms > *max_context_rms {
                return Err(quality("Best patch placement exceeds max_context_rms"));
            }
            let ro = retouch::Options {
                source_id: source_id.clone(),
                source_transform: [
                    1.0,
                    0.0,
                    0.0,
                    1.0,
                    (chosen[0] - o.region.x as i64) as f64,
                    (chosen[1] - o.region.y as i64) as f64,
                ],
                region: o.region.clone(),
                mode: blend.clone(),
                sampling: retouch::Sampling::Nearest,
                border: retouch::Border::Error,
                opacity: o.opacity,
                use_selection: o.use_selection,
            };
            let details = retouch::apply(document, index, &ro, control)?;
            work.add(details["work"].as_u64().expect("retouch work") as usize)?;
            json!({"source_id":source_id,"source_sha256":source.hash(),"source_origin":chosen,"valid_candidates":valid,"context_cells":context.len(),"context_rms":rms,"retouch":details})
        }
        Action::Fill { fill } | Action::Move { fill, .. } => {
            validate_fill(fill)?;
            let source = Grid::read(document, &fill.source_id)?;
            let moved = if let Action::Move { offset, .. } = &o.action {
                Some(*offset)
            } else {
                None
            };
            let mut destination = Vec::new();
            if let Some([dx, dy]) = moved {
                for &i in &ids {
                    let j = target
                        .at(
                            (i % target.w) as i64 + dx as i64,
                            (i / target.w) as i64 + dy as i64,
                        )
                        .ok_or_else(|| {
                            invalid("Move destination extends outside the target native grid")
                        })?;
                    destination.push((i, j));
                    affected[j] = affected[j].max(weights[i]);
                }
            }
            let same = fill.source_id == document.items[index].id;
            let synthesis = if moved == Some([0, 0]) {
                if let Some(r) = &fill.donor_region
                    && region(r, source.w, source.h)?
                        .iter()
                        .any(|&v| v != 0.0 && v != 1.0)
                {
                    return Err(invalid("Donor regions require binary0/255 masks"));
                }
                Synthesis {
                    pixels: target.pixels.clone(),
                    receipt: json!({"zero_offset":true,"source_id":fill.source_id,"source_sha256":source.hash(),"patches":[]}),
                }
            } else {
                synthesize(&target, &source, same, &weights, fill, &mut work)?
            };
            for &i in &ids {
                values[i] = std::array::from_fn(|k| {
                    target.pixels[i][k]
                        + (synthesis.pixels[i][k] - target.pixels[i][k]) * weights[i]
                });
            }
            for &(i, j) in &destination {
                values[j] = std::array::from_fn(|k| {
                    values[j][k] + (target.pixels[i][k] - values[j][k]) * weights[i]
                });
            }
            for (i, v) in values.iter_mut().enumerate() {
                for (k, c) in v.iter_mut().enumerate() {
                    *c = target.pixels[i][k] + (*c - target.pixels[i][k]) * o.opacity;
                }
            }
            json!({"synthesis":synthesis.receipt,"moved_pixels":destination.len(),"offset":moved,"move_compositing":"fill_source_domain_then_replace_from_frozen_original_then_whole_action_opacity"})
        }
        Action::EdgeCorrect {
            guide_id,
            radius,
            range_sigma,
            max_change_rms,
            minimum_effective_samples,
        } => {
            if !(1..=16).contains(radius)
                || !range_sigma.is_finite()
                || !(0.0001..=1.0).contains(range_sigma)
                || !unit(*max_change_rms)
                || !minimum_effective_samples.is_finite()
                || !(1.0..=1089.0).contains(minimum_effective_samples)
            {
                return Err(invalid(
                    "Edge correction requires radius1..16,range_sigma0.0001..1,max_change_rms0..1 and minimum_effective_samples1..1089",
                ));
            }
            let guide = Grid::read(document, guide_id)?;
            if guide.w != target.w || guide.h != target.h {
                return Err(invalid(
                    "Guide and target native grids must have the same dimensions",
                ));
            }
            let mut minimum = None::<f64>;
            let mut maximum = 0.0f64;
            for &i in &ids {
                let mut samples = Vec::new();
                let mut sum = 0.0;
                let mut square = 0.0;
                let cells = window(&target, i, *radius);
                work.add(cells.len() * 5)?;
                for (j, dx, dy) in cells {
                    let spatial = (*radius as i64 + 1 - dx.abs()) as f64
                        * (*radius as i64 + 1 - dy.abs()) as f64;
                    let weight = spatial
                        * (-error2(guide.pixels[i], guide.pixels[j])
                            / (2.0 * range_sigma * range_sigma))
                            .exp();
                    if weight > 0.0 {
                        sum += weight;
                        square += weight * weight;
                        samples.push((j, weight));
                    }
                }
                let effective = sum * sum / square;
                minimum = Some(minimum.map_or(effective, |v| v.min(effective)));
                if effective < *minimum_effective_samples {
                    return Err(quality(
                        "Edge correction has insufficient effective guide support",
                    ));
                }
                let mut corrected = [0.0; 4];
                for (k, c) in corrected.iter_mut().enumerate() {
                    samples.sort_by(|(a, _), (b, _)| {
                        target.pixels[*a][k]
                            .total_cmp(&target.pixels[*b][k])
                            .then(a.cmp(b))
                    });
                    let mut cumulative = 0.0;
                    for &(j, weight) in &samples {
                        cumulative += weight;
                        if cumulative >= sum / 2.0 {
                            *c = target.pixels[j][k];
                            break;
                        }
                    }
                }
                values[i] = std::array::from_fn(|k| {
                    target.pixels[i][k]
                        + (corrected[k] - target.pixels[i][k]) * weights[i] * o.opacity
                });
                let preview = if values[i] == target.pixels[i] {
                    values[i]
                } else {
                    pm(&encoded(values[i]))
                };
                let shift = error2(target.pixels[i], preview).sqrt();
                maximum = maximum.max(shift);
                if shift > *max_change_rms {
                    return Err(quality("Edge correction exceeds max_change_rms"));
                }
            }
            json!({"guide_id":guide_id,"guide_sha256":guide.hash(),"minimum_effective_samples":minimum,"maximum_change_rms":maximum,"estimator":"per_channel_guided_weighted_median","spatial_kernel":"separable_integer_tent","range_metric":"normalized_premultiplied_rgba_mean_squared_difference"})
        }
    };
    work.add(n)?;
    let changed = if matches!(o.action, Action::Patch { .. }) {
        let out = Grid::read(document, &document.items[index].id)?;
        (0..n)
            .filter(|&i| target.bytes[i * 4..i * 4 + 4] != out.bytes[i * 4..i * 4 + 4])
            .collect()
    } else {
        write_result(document, index, &target, &values)
    };
    let output = Grid::read(document, &document.items[index].id)?;
    let (edges, after) = boundary(&target, &affected, &output.pixels);
    if o.max_boundary_rms
        .is_some_and(|limit| after.is_some_and(|v| v > limit))
    {
        return Err(quality("Final quantized boundary exceeds max_boundary_rms"));
    }
    let (_, before) = boundary(&target, &affected, &target.pixels);
    control.check()?;
    let settings = format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(o).expect("validated repair"))
    );
    Ok(
        json!({"algorithm":"inkbolt-region-repair-v1","settings_sha256":settings,"target_before_sha256":target.hash(),"result_sha256":output.hash(),"region_pixels":ids.len(),"region_bounds":extent(&ids,target.w),"changed_pixels":changed.len(),"changed_bounds":extent(&changed,target.w),"boundary_edges":edges,"boundary_rms_before":before,"boundary_rms_after":after,"action":action_receipt,"work":work.count,"coordinates":"native_pixel_grids","quantization":"final_rgba8_once","source_state":"frozen_before_operation","quality_failure":"atomic_rejection_no_candidate_published"}),
    )
}
