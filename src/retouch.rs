//! Original source-preserving region cloning and boundary-constrained healing.
use crate::{Error, assets, control::Control, geometry, model::*, render, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

pub const MAX_WORK: u64 = 67_108_864;
pub const MAX_ITERATIONS: u32 = 4096;
const ALGORITHM: &str = "inkbolt-region-retouch-v1";
fn one() -> f64 {
    1.0
}
fn tolerance() -> f64 {
    1e-9
}
fn iterations() -> u32 {
    2048
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Sampling {
    Nearest,
    #[default]
    Bilinear,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Border {
    #[default]
    Error,
    Transparent,
    Clamp,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Mode {
    Clone {},
    Heal {
        #[serde(default)]
        screening: f64,
        #[serde(default = "tolerance")]
        tolerance: f64,
        #[serde(default = "iterations")]
        max_iterations: u32,
    },
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Region {
    pub x: u32,
    pub y: u32,
    pub width: u32,
    pub height: u32,
    pub gray_hex: Option<String>,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Options {
    pub source_id: String,
    #[serde(default = "identity")]
    pub source_transform: Matrix,
    pub region: Region,
    pub mode: Mode,
    #[serde(default)]
    pub sampling: Sampling,
    #[serde(default)]
    pub border: Border,
    #[serde(default = "one")]
    pub opacity: f64,
    #[serde(default)]
    pub use_selection: bool,
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_RETOUCH", message)
}
struct Work<'a> {
    count: u64,
    control: &'a Control,
}
impl Work<'_> {
    fn add(&mut self, n: usize) -> Result<(), Error> {
        self.count += n as u64;
        if self.count > MAX_WORK {
            return Err(limit("Retouch exceeds 67108864 work units"));
        }
        self.control.check()
    }
}
fn premul(c: &[u8]) -> [f64; 4] {
    let a = c[3] as f64 / 255.0;
    [
        c[0] as f64 / 255.0 * a,
        c[1] as f64 / 255.0 * a,
        c[2] as f64 / 255.0 * a,
        a,
    ]
}
fn encode(c: [f64; 4]) -> [u8; 4] {
    let byte = |v: f64| (v.clamp(0.0, 1.0) * 255.0).round() as u8;
    let a = byte(c[3]);
    if a == 0 {
        [0; 4]
    } else {
        [byte(c[0] / c[3]), byte(c[1] / c[3]), byte(c[2] / c[3]), a]
    }
}
fn neighbors(i: usize, w: usize, h: usize) -> [Option<usize>; 4] {
    let x = i % w;
    let y = i / w;
    [
        (x > 0).then(|| i - 1),
        (x + 1 < w).then_some(i + 1),
        (y > 0).then(|| i - w),
        (y + 1 < h).then_some(i + w),
    ]
}
fn sample(
    data: &[[f64; 4]],
    w: usize,
    h: usize,
    p: Point,
    sampling: Sampling,
    border: Border,
) -> Result<[f64; 4], Error> {
    let mut taps = Vec::with_capacity(4);
    match sampling {
        Sampling::Nearest => taps.push((p[0].floor() as i64, p[1].floor() as i64, 1.0)),
        Sampling::Bilinear => {
            let x = p[0] - 0.5;
            let y = p[1] - 0.5;
            let ix = x.floor() as i64;
            let iy = y.floor() as i64;
            let dx = x - ix as f64;
            let dy = y - iy as f64;
            taps.extend([
                (ix, iy, (1.0 - dx) * (1.0 - dy)),
                (ix + 1, iy, dx * (1.0 - dy)),
                (ix, iy + 1, (1.0 - dx) * dy),
                (ix + 1, iy + 1, dx * dy),
            ]);
        }
    }
    let mut out = [0.0; 4];
    for (mut x, mut y, weight) in taps {
        if weight == 0.0 {
            continue;
        }
        if matches!(border, Border::Clamp) {
            x = x.clamp(0, w as i64 - 1);
            y = y.clamp(0, h as i64 - 1);
        }
        if x < 0 || y < 0 || x >= w as i64 || y >= h as i64 {
            if matches!(border, Border::Error) {
                return Err(invalid(
                    "Required source sampling footprint extends outside its native grid",
                ));
            }
            continue;
        }
        for k in 0..4 {
            out[k] += weight * data[y as usize * w + x as usize][k];
        }
    }
    Ok(out)
}
struct System {
    diagonal: Vec<f64>,
    adjacent: Vec<[Option<usize>; 4]>,
}
impl System {
    fn multiply(&self, v: &[f64], work: &mut Work<'_>) -> Result<Vec<f64>, Error> {
        work.add(v.len())?;
        Ok((0..v.len())
            .map(|i| {
                self.diagonal[i] * v[i]
                    - self.adjacent[i]
                        .iter()
                        .flatten()
                        .map(|&j| v[j])
                        .sum::<f64>()
            })
            .collect())
    }
    fn solve(
        &self,
        b: &[f64],
        tol: f64,
        max: u32,
        work: &mut Work<'_>,
    ) -> Result<(Vec<f64>, u32, f64), Error> {
        let norm = |v: &[f64]| v.iter().fold(0.0f64, |a, b| a.max(b.abs()));
        let dot = |a: &[f64], b: &[f64]| a.iter().zip(b).map(|(x, y)| x * y).sum::<f64>();
        let n = b.len();
        let mut x = vec![0.0; n];
        let mut r = b.to_vec();
        let mut z: Vec<_> = r.iter().zip(&self.diagonal).map(|(r, d)| r / d).collect();
        let mut p = z.clone();
        let mut rz = dot(&r, &z);
        if norm(&r) <= tol {
            return Ok((x, 0, norm(&r)));
        }
        for iteration in 1..=max {
            let ap = self.multiply(&p, work)?;
            let denominator = dot(&p, &ap);
            if !denominator.is_finite() || denominator <= 0.0 {
                return Err(Error::new(
                    "RETOUCH_PRECISION",
                    "Healing solver lost a positive finite search direction",
                ));
            }
            let step = rz / denominator;
            work.add(n)?;
            for i in 0..n {
                x[i] += step * p[i];
                r[i] -= step * ap[i];
            }
            let restart = norm(&r) <= tol || iteration % 64 == 0;
            if restart {
                let ax = self.multiply(&x, work)?;
                for i in 0..n {
                    r[i] = b[i] - ax[i];
                }
                let residual = norm(&r);
                if residual <= tol {
                    return Ok((x, iteration, residual));
                }
            }
            work.add(n)?;
            for i in 0..n {
                z[i] = r[i] / self.diagonal[i];
            }
            let next = dot(&r, &z);
            let beta = if restart { 0.0 } else { next / rz };
            for i in 0..n {
                p[i] = z[i] + beta * p[i];
            }
            rz = next;
        }
        Err(Error::new(
            "RETOUCH_PRECISION",
            "Healing did not satisfy the requested true residual within max_iterations",
        ))
    }
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
pub(crate) fn apply(
    document: &mut Document,
    index: usize,
    o: &Options,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    if !o.opacity.is_finite() || !(0.0..=1.0).contains(&o.opacity) {
        return Err(invalid("Retouch opacity requires 0..1"));
    }
    geometry::validate_matrix(o.source_transform)?;
    let heal = matches!(o.mode, Mode::Heal { .. });
    if let Mode::Heal {
        screening,
        tolerance,
        max_iterations,
    } = o.mode
        && (!screening.is_finite()
            || !(0.0..=16.0).contains(&screening)
            || !tolerance.is_finite()
            || !(1e-12..=1e-4).contains(&tolerance)
            || !(1..=MAX_ITERATIONS).contains(&max_iterations))
    {
        return Err(invalid(
            "Healing requires screening0..16,tolerance1e-12..1e-4 and max_iterations1..4096",
        ));
    }
    crate::pixel_warps::reject_native(&document.items[index])?;
    let Content::Raster {
        width,
        height,
        rgba_hex,
        ..
    } = &document.items[index].content
    else {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Retouch requires an inline native pixel target",
        ));
    };
    let (w, h) = (*width as usize, *height as usize);
    let n = w * h;
    let original = render::unhex(rgba_hex);
    let source_index = scene::index(document, &o.source_id)?;
    crate::pixel_warps::reject_native(&document.items[source_index])?;
    let Content::Raster {
        width: sw,
        height: sh,
        rgba_hex: source_hex,
        ..
    } = &document.items[source_index].content
    else {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Retouch source must be an inline native pixel layer",
        ));
    };
    let source_bytes = render::unhex(source_hex);
    let source_hash = assets::identity(*sw, *sh, &source_bytes);
    let target_hash = assets::identity(w as u32, h as u32, &original);
    let r = &o.region;
    if r.width == 0
        || r.height == 0
        || r.x as u64 + r.width as u64 > w as u64
        || r.y as u64 + r.height as u64 > h as u64
    {
        return Err(invalid(
            "Retouch region must be nonempty and entirely within the target native grid",
        ));
    }
    let gray = if let Some(hex) = &r.gray_hex {
        if hex.len() != r.width as usize * r.height as usize * 2
            || !hex.bytes().all(|b| b.is_ascii_hexdigit())
        {
            return Err(invalid(
                "Region gray_hex must contain one byte per native region cell",
            ));
        }
        render::unhex(hex)
    } else {
        vec![255; r.width as usize * r.height as usize]
    };
    let selection = if o.use_selection {
        Some(render::unhex(
            &document
                .selection
                .as_ref()
                .ok_or_else(|| invalid("use_selection requires an explicit active selection"))?
                .gray_hex,
        ))
    } else {
        None
    };
    let world = scene::world_transform(document, index)?;
    let mut work = Work { count: 0, control };
    work.add(n)?;
    let mut weights = vec![0.0; n];
    let mut ids = Vec::new();
    let mut mapping = vec![usize::MAX; n];
    for y in r.y as usize..(r.y + r.height) as usize {
        control.check()?;
        for x in r.x as usize..(r.x + r.width) as usize {
            let mut a =
                gray[(y - r.y as usize) * r.width as usize + x - r.x as usize] as f64 / 255.0;
            if let Some(s) = &selection {
                let p = geometry::map(world, [x as f64 + 0.5, y as f64 + 0.5]);
                let xx = p[0].floor();
                let yy = p[1].floor();
                a *= if xx >= 0.0
                    && yy >= 0.0
                    && xx < document.width as f64
                    && yy < document.height as f64
                {
                    s[yy as usize * document.width as usize + xx as usize] as f64 / 255.0
                } else {
                    0.0
                };
            }
            let i = y * w + x;
            weights[i] = a;
            if a > 0.0 {
                mapping[i] = ids.len();
                ids.push(i);
            }
        }
    }
    let mut boundary_edges = 0usize;
    let mut image_edges = 0usize;
    let mut components = 0usize;
    let mut unanchored = 0usize;
    let mut visited = vec![false; n];
    let mut needed = vec![false; n];
    for &start in &ids {
        needed[start] = true;
        for q in neighbors(start, w, h) {
            match q {
                Some(j) if weights[j] == 0.0 => {
                    boundary_edges += 1;
                    if heal {
                        needed[j] = true;
                    }
                }
                None => image_edges += 1,
                _ => (),
            }
        }
        if visited[start] {
            continue;
        }
        components += 1;
        let mut stack = vec![start];
        visited[start] = true;
        let mut anchored = false;
        while let Some(i) = stack.pop() {
            for j in neighbors(i, w, h).into_iter().flatten() {
                if weights[j] == 0.0 {
                    anchored = true;
                } else if !visited[j] {
                    visited[j] = true;
                    stack.push(j);
                }
            }
        }
        if !anchored {
            unanchored += 1;
        }
    }
    work.add(ids.len())?;
    if let Mode::Heal { screening: 0.0, .. } = o.mode
        && unanchored > 0
        && o.opacity > 0.0
    {
        return Err(invalid(
            "Unscreened healing requires an unselected in-image boundary for every component; set positive screening explicitly for an unanchored region",
        ));
    }
    let before: Vec<_> = original
        .as_chunks::<4>()
        .0
        .iter()
        .map(|c| premul(c))
        .collect();
    let src: Vec<_> = source_bytes
        .as_chunks::<4>()
        .0
        .iter()
        .map(|c| premul(c))
        .collect();
    let mut field = vec![[0.0; 4]; n];
    if o.opacity > 0.0 {
        for (i, &required) in needed.iter().enumerate() {
            if i % 1024 == 0 {
                control.check()?;
            }
            if required {
                field[i] = sample(
                    &src,
                    *sw as usize,
                    *sh as usize,
                    geometry::map(
                        o.source_transform,
                        [(i % w) as f64 + 0.5, (i / w) as f64 + 0.5],
                    ),
                    o.sampling,
                    o.border,
                )?;
            }
        }
        work.add(needed.iter().filter(|&&v| v).count())?;
    }
    let mut solved = field.clone();
    let mut solver_iterations = [0u32; 4];
    let mut residuals = [0.0f64; 4];
    if let Mode::Heal {
        screening,
        tolerance,
        max_iterations,
    } = o.mode
        && o.opacity > 0.0
        && !ids.is_empty()
    {
        let system = System {
            diagonal: ids
                .iter()
                .map(|&i| neighbors(i, w, h).iter().flatten().count() as f64 + screening)
                .collect(),
            adjacent: ids
                .iter()
                .map(|&i| {
                    neighbors(i, w, h)
                        .map(|j| j.and_then(|j| (mapping[j] != usize::MAX).then_some(mapping[j])))
                })
                .collect(),
        };
        for k in 0..4 {
            work.add(ids.len())?;
            let b: Vec<_> = ids
                .iter()
                .map(|&i| {
                    neighbors(i, w, h)
                        .into_iter()
                        .flatten()
                        .filter(|&j| weights[j] == 0.0)
                        .map(|j| before[j][k] - field[j][k])
                        .sum()
                })
                .collect();
            let (correction, iterations, residual) =
                system.solve(&b, tolerance, max_iterations, &mut work)?;
            solver_iterations[k] = iterations;
            residuals[k] = residual;
            for (j, &i) in ids.iter().enumerate() {
                solved[i][k] += correction[j];
            }
        }
    }
    let mut output = original.clone();
    let mut changed = Vec::new();
    let mut clamped = 0usize;
    work.add(ids.len())?;
    if o.opacity > 0.0 {
        for &i in &ids {
            let raw = solved[i];
            let a = raw[3].clamp(0.0, 1.0);
            let color = [
                raw[0].clamp(0.0, a),
                raw[1].clamp(0.0, a),
                raw[2].clamp(0.0, a),
                a,
            ];
            if color != raw {
                clamped += 1;
            }
            let strength = weights[i] * o.opacity;
            let value =
                std::array::from_fn(|k| before[i][k] + (color[k] - before[i][k]) * strength);
            if value == before[i] {
                continue;
            }
            let bytes = encode(value);
            if bytes != original[i * 4..i * 4 + 4] {
                output[i * 4..i * 4 + 4].copy_from_slice(&bytes);
                changed.push(i);
            }
        }
    }
    let mut seam_before = 0.0;
    let mut seam_after = 0.0;
    for &i in &ids {
        for j in neighbors(i, w, h)
            .into_iter()
            .flatten()
            .filter(|&j| weights[j] == 0.0)
        {
            let after = premul(&output[i * 4..i * 4 + 4]);
            for k in 0..4 {
                seam_before += (before[i][k] - before[j][k]).powi(2);
                seam_after += (after[k] - before[j][k]).powi(2);
            }
        }
    }
    let seam = |sum: f64| {
        if boundary_edges > 0 {
            Some((sum / (4 * boundary_edges) as f64).sqrt())
        } else {
            None
        }
    };
    let result_hash = assets::identity(w as u32, h as u32, &output);
    let hash = format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(o).expect("validated retouch settings"))
    );
    control.check()?;
    let Content::Raster { rgba_hex, .. } = &mut document.items[index].content else {
        unreachable!()
    };
    *rgba_hex = render::hex(&output);
    Ok(
        json!({"algorithm":ALGORITHM,"settings_sha256":hash,"source_id":o.source_id,"source_sha256":source_hash,"target_before_sha256":target_hash,"result_sha256":result_hash,"region_pixels":ids.len(),"region_bounds":extent(&ids,w),"coverage_sum":weights.iter().sum::<f64>(),"components":components,"boundary_edges":boundary_edges,"image_edge_faces":image_edges,"perimeter":boundary_edges+image_edges,"changed_pixels":changed.len(),"changed_bounds":extent(&changed,w),"clamped_pixels":clamped,"solver_iterations":solver_iterations,"solver_residuals":residuals,"solver_residual_space":"unclamped_normalized_premultiplied_rgba","boundary_rms_before":seam(seam_before),"boundary_rms_after":seam(seam_after),"work":work.count,"coordinates":"target_native_grid_to_source_native_grid","source_sampling":"frozen_before_this_operation","selection_sampling":"world_mapped_native_centers","compositing":"masked_premultiplied_replacement_once","boundary_measurement":"four_connected_positive_coverage_domain"}),
    )
}
