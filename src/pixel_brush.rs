//! Original deterministic native-pixel strokes with integrated circular coverage.
use crate::{
    Error, assets, control::Control, geometry, model::*, native_pixels as pixels, render, scene,
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::path::Path;

pub const MAX_POINTS: usize = 1024;
pub const MAX_DABS: usize = 8192;
pub const MAX_WORK: u64 = 67_108_864;
pub const MAX_MEMORY_BYTES: u64 = 128 * 1024 * 1024;
pub const MAX_TEXTURE_PIXELS: usize = 4096;
pub const COVERAGE_TOLERANCE: f64 = 0.0000001;
const ALGORITHM: &str = "inkbolt-pixel-brush-v1";
fn one() -> f64 {
    1.0
}
fn yes() -> bool {
    true
}
fn spacing() -> f64 {
    0.25
}
fn scale() -> Point {
    [1.0; 2]
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Node {
    pub point: Point,
    #[serde(default = "one")]
    pub size: f64,
    #[serde(default = "one")]
    pub opacity: f64,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Border {
    #[default]
    Transparent,
    Clamp,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Mode {
    Paint {
        color: Color,
    },
    Erase {},
    Smudge {
        #[serde(default)]
        border: Border,
    },
    Mixer {
        color: Color,
        pickup: f64,
        load: f64,
    },
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Texture {
    pub width: u32,
    pub height: u32,
    pub gray_hex: String,
    #[serde(default)]
    pub origin: Point,
    #[serde(default = "scale")]
    pub scale: Point,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Stroke {
    pub points: Vec<Node>,
    pub diameter: f64,
    #[serde(default = "one")]
    pub hardness: f64,
    #[serde(default = "spacing")]
    pub spacing: f64,
    #[serde(default = "yes")]
    pub include_end: bool,
    #[serde(default = "one")]
    pub opacity: f64,
    #[serde(default = "one")]
    pub flow: f64,
    #[serde(default)]
    pub scatter: f64,
    #[serde(default)]
    pub seed: u32,
    pub mode: Mode,
    #[serde(default)]
    pub texture: Option<Texture>,
    #[serde(default)]
    pub use_selection: bool,
}
#[derive(Clone, Debug, Serialize)]
pub struct Dab {
    pub distance: f64,
    pub path_point: Point,
    pub center: Point,
    pub diameter: f64,
    pub opacity: f64,
}
struct Prepared {
    dabs: Vec<Dab>,
    length: f64,
    bounds: [f64; 4],
    texture: Vec<u8>,
    hash: String,
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_BRUSH", message)
}
fn unit(value: f64) -> bool {
    value.is_finite() && (0.0..=1.0).contains(&value)
}
fn validate_stroke(s: &Stroke) -> Result<(), Error> {
    if s.points.is_empty() || s.points.len() > MAX_POINTS {
        return Err(limit("Brush strokes require 1..1024 control points"));
    }
    if !s.diameter.is_finite()
        || !(0.25..=512.0).contains(&s.diameter)
        || !s.spacing.is_finite()
        || !(0.01..=4.0).contains(&s.spacing)
        || !unit(s.hardness)
        || !unit(s.opacity)
        || !unit(s.flow)
        || !s.scatter.is_finite()
        || !(0.0..=4.0).contains(&s.scatter)
    {
        return Err(invalid(
            "Brush diameter requires 0.25..512, spacing 0.01..4, scatter 0..4 and hardness/opacity/flow 0..1",
        ));
    }
    for n in &s.points {
        if !unit(n.size)
            || !unit(n.opacity)
            || n.point
                .iter()
                .any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE)
        {
            return Err(invalid(
                "Brush points require bounded finite coordinates and size/opacity factors in 0..1",
            ));
        }
    }
    if let Mode::Mixer { pickup, load, .. } = s.mode
        && (!unit(pickup) || !unit(load))
    {
        return Err(invalid("Mixer pickup and load require 0..1"));
    }
    if let Some(t) = &s.texture {
        let n = t.width as u64 * t.height as u64;
        if t.width == 0 || t.height == 0 || n > MAX_TEXTURE_PIXELS as u64 {
            return Err(limit("Brush texture requires 1..4096 grayscale pixels"));
        }
        if t.gray_hex.len() != n as usize * 2
            || !t.gray_hex.bytes().all(|v| v.is_ascii_hexdigit())
            || t.origin
                .iter()
                .any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE)
            || t.scale
                .iter()
                .any(|v| !v.is_finite() || !(0.001..=1024.0).contains(v))
        {
            return Err(invalid(
                "Brush texture requires exact grayscale bytes, bounded origin and scale 0.001..1024",
            ));
        }
    }
    Ok(())
}
fn jitter(seed: u32, index: usize) -> Point {
    let mut hash = Sha256::new();
    hash.update(b"inkbolt.brush.scatter.v1\0");
    hash.update(seed.to_le_bytes());
    hash.update((index as u64).to_le_bytes());
    let hash = hash.finalize();
    std::array::from_fn(|i| {
        let word = u32::from_le_bytes(hash[i * 4..i * 4 + 4].try_into().unwrap());
        2.0 * (word as f64 + 0.5) / 4294967296.0 - 1.0
    })
}
fn prepare(s: &Stroke, control: &Control) -> Result<Prepared, Error> {
    validate_stroke(s)?;
    control.check()?;
    let mut nodes = Vec::<Node>::new();
    for n in &s.points {
        if nodes.last().is_some_and(|last| last.point == n.point) {
            *nodes.last_mut().unwrap() = n.clone();
        } else {
            nodes.push(n.clone());
        }
    }
    let mut distances = vec![0.0];
    for pair in nodes.windows(2) {
        distances.push(
            distances.last().unwrap()
                + (pair[1].point[0] - pair[0].point[0]).hypot(pair[1].point[1] - pair[0].point[1]),
        );
    }
    let length = *distances.last().unwrap();
    let step = s.diameter * s.spacing;
    let regular = (length / step).floor() as usize;
    if regular >= MAX_DABS {
        return Err(limit("Stroke spacing exceeds 8192 dabs"));
    }
    let mut positions = (0..=regular).map(|i| i as f64 * step).collect::<Vec<_>>();
    let last = positions.last_mut().unwrap();
    if (length - *last).abs() <= 16.0 * f64::EPSILON * length.max(1.0) {
        *last = length;
    } else if s.include_end {
        positions.push(length);
    }
    if positions.len() > MAX_DABS {
        return Err(limit("Stroke endpoint exceeds 8192 dabs"));
    }
    let mut dabs = Vec::with_capacity(positions.len());
    let mut bounds = [
        f64::INFINITY,
        f64::INFINITY,
        f64::NEG_INFINITY,
        f64::NEG_INFINITY,
    ];
    let mut segment = 0;
    for (i, distance) in positions.into_iter().enumerate() {
        if i % 64 == 0 {
            control.check()?;
        }
        while segment + 1 < distances.len() - 1 && distances[segment + 1] < distance {
            segment += 1;
        }
        let a = &nodes[segment];
        let b = &nodes[(segment + 1).min(nodes.len() - 1)];
        let t = if a.point == b.point {
            0.0
        } else {
            ((distance - distances[segment]) / (distances[segment + 1] - distances[segment]))
                .clamp(0.0, 1.0)
        };
        let mix = |a: f64, b: f64| a + (b - a) * t;
        let path_point = std::array::from_fn(|k| mix(a.point[k], b.point[k]));
        let diameter = s.diameter * mix(a.size, b.size);
        let random = jitter(s.seed, i);
        let center =
            std::array::from_fn(|k| path_point[k] + random[k] * s.scatter * diameter / 2.0);
        for k in 0..2 {
            bounds[k] = bounds[k].min(center[k] - diameter / 2.0);
            bounds[k + 2] = bounds[k + 2].max(center[k] + diameter / 2.0);
        }
        dabs.push(Dab {
            distance,
            path_point,
            center,
            diameter,
            opacity: mix(a.opacity, b.opacity),
        });
    }
    control.check()?;
    Ok(Prepared {
        dabs,
        length,
        bounds,
        texture: s
            .texture
            .as_ref()
            .map(|t| render::unhex(&t.gray_hex))
            .unwrap_or_default(),
        hash: assets::sha256(&serde_json::to_vec(s).unwrap()),
    })
}
pub fn inspect(s: &Stroke, include_dabs: bool, control: &Control) -> Result<Value, Error> {
    let p = prepare(s, control)?;
    let mut result = json!({"algorithm":ALGORITHM,"stroke":s,"stroke_sha256":p.hash,"length":p.length,"spacing_distance":s.spacing*s.diameter,"dab_count":p.dabs.len(),"bounds":p.bounds,"coordinates":"target_native_pixel_grid","coverage":"pixel_integrated_plateau_and_squared_radius_falloff","coverage_numeric_tolerance":COVERAGE_TOLERANCE,"limits":{"points":MAX_POINTS,"dabs":MAX_DABS,"work":MAX_WORK,"texture_pixels":MAX_TEXTURE_PIXELS},"repeatability":"same_engine_build_and_floating_point_environment;stateless_integer_seeded_scatter"});
    if include_dabs {
        result["dabs"] = json!(p.dabs);
    }
    control.check()?;
    Ok(result)
}

struct Work<'a> {
    count: u64,
    control: &'a Control,
}
impl Work<'_> {
    fn add(&mut self, n: u64) -> Result<(), Error> {
        let old = self.count;
        self.count = self.count.saturating_add(n);
        if self.count > MAX_WORK {
            return Err(limit("Brush evaluation exceeds 67108864 work units"));
        }
        if old / 1024 != self.count / 1024 {
            self.control.check()?;
        }
        Ok(())
    }
}
impl pixels::Budget for Work<'_> {
    fn charge(&mut self, pixels: usize) -> Result<(), Error> {
        self.add(pixels as u64)
    }
    fn control(&self) -> &Control {
        self.control
    }
}
fn primitive(x: f64) -> f64 {
    (x * (1.0 - x * x).max(0.0).sqrt() + x.asin()) / 2.0
}
fn quadrant(radius: f64, x: f64, y: f64) -> f64 {
    let u = (x.abs() / radius).min(1.0);
    let v = (y.abs() / radius).min(1.0);
    let split = (1.0 - v * v).max(0.0).sqrt().min(u);
    let area = radius * radius * (split * v + primitive(u) - primitive(split));
    if (x < 0.0) != (y < 0.0) { -area } else { area }
}
fn circle_area(radius: f64, rect: [f64; 4]) -> f64 {
    if radius == 0.0 {
        return 0.0;
    }
    let [x0, y0, x1, y1] = rect;
    let r2 = radius * radius;
    let near = |a: f64, b: f64| {
        if a > 0.0 {
            a
        } else if b < 0.0 {
            b
        } else {
            0.0
        }
    };
    if near(x0, x1).powi(2) + near(y0, y1).powi(2) >= r2 {
        return 0.0;
    }
    if x0.abs().max(x1.abs()).powi(2) + y0.abs().max(y1.abs()).powi(2) <= r2 {
        return 1.0;
    }
    (quadrant(radius, x1, y1) - quadrant(radius, x0, y1) - quadrant(radius, x1, y0)
        + quadrant(radius, x0, y0))
    .clamp(0.0, 1.0)
}
struct Integral {
    radius2: f64,
    inner2: f64,
    rect: [f64; 4],
}
impl Integral {
    fn value(&self, t: f64, work: &mut Work) -> Result<f64, Error> {
        work.add(1)?;
        Ok(circle_area(
            (self.inner2 + (self.radius2 - self.inner2) * t).sqrt(),
            self.rect,
        ))
    }
    fn integrate(
        &self,
        range: [f64; 2],
        v: [f64; 3],
        whole: f64,
        tolerance: f64,
        depth: u32,
        work: &mut Work,
    ) -> Result<f64, Error> {
        let [a, b] = range;
        let m = (a + b) / 2.0;
        let l = self.value((a + m) / 2.0, work)?;
        let r = self.value((m + b) / 2.0, work)?;
        let left = (m - a) * (v[0] + 4.0 * l + v[1]) / 6.0;
        let right = (b - m) * (v[1] + 4.0 * r + v[2]) / 6.0;
        let delta = left + right - whole;
        if delta.abs() <= 15.0 * tolerance {
            return Ok(left + right + delta / 15.0);
        }
        if depth == 0 {
            return Err(Error::new(
                "BRUSH_PRECISION",
                "Brush coverage integration did not converge",
            ));
        }
        Ok(self.integrate(
            [a, m],
            [v[0], l, v[1]],
            left,
            tolerance / 2.0,
            depth - 1,
            work,
        )? + self.integrate(
            [m, b],
            [v[1], r, v[2]],
            right,
            tolerance / 2.0,
            depth - 1,
            work,
        )?)
    }
}
fn coverage(dab: &Dab, hardness: f64, x: u32, y: u32, work: &mut Work) -> Result<f64, Error> {
    work.add(1)?;
    let radius = dab.diameter / 2.0;
    if radius == 0.0 {
        return Ok(0.0);
    }
    let rect = [
        x as f64 - dab.center[0],
        y as f64 - dab.center[1],
        x as f64 + 1.0 - dab.center[0],
        y as f64 + 1.0 - dab.center[1],
    ];
    let outer = circle_area(radius, rect);
    if outer == 0.0 || hardness == 1.0 {
        return Ok(outer);
    }
    if circle_area(radius * hardness, rect) == 1.0 {
        return Ok(1.0);
    }
    let integral = Integral {
        radius2: radius * radius,
        inner2: (radius * hardness).powi(2),
        rect,
    };
    let [x0, y0, x1, y1] = rect;
    let mut breaks = vec![0.0, 1.0];
    for square in [
        x0 * x0,
        x1 * x1,
        y0 * y0,
        y1 * y1,
        x0 * x0 + y0 * y0,
        x0 * x0 + y1 * y1,
        x1 * x1 + y0 * y0,
        x1 * x1 + y1 * y1,
    ] {
        let t = (square - integral.inner2) / (integral.radius2 - integral.inner2);
        if t > 0.0 && t < 1.0 {
            breaks.push(t);
        }
    }
    breaks.sort_by(f64::total_cmp);
    breaks.dedup();
    let mut result = 0.0;
    for b in breaks.windows(2) {
        let [a, z] = [b[0], b[1]];
        let v = [
            integral.value(a, work)?,
            integral.value((a + z) / 2.0, work)?,
            integral.value(z, work)?,
        ];
        let whole = (z - a) * (v[0] + 4.0 * v[1] + v[2]) / 6.0;
        result += integral.integrate([a, z], v, whole, COVERAGE_TOLERANCE * (z - a), 20, work)?;
    }
    Ok(result.clamp(0.0, 1.0))
}
fn premul(color: Color) -> [f64; 4] {
    let a = color[3] as f64 / 255.0;
    [
        color[0] as f64 / 255.0 * a,
        color[1] as f64 / 255.0 * a,
        color[2] as f64 / 255.0 * a,
        a,
    ]
}
fn over(old: [f64; 4], source: [f64; 4], weight: f64) -> [f64; 4] {
    std::array::from_fn(|i| source[i] * weight + old[i] * (1.0 - source[3] * weight))
}
fn interpolate(a: [f64; 4], b: [f64; 4], t: f64) -> [f64; 4] {
    std::array::from_fn(|i| a[i] + (b[i] - a[i]) * t)
}
fn sample(
    mut data: impl FnMut(u32, u32) -> Result<[f64; 4], Error>,
    w: u32,
    h: u32,
    p: Point,
    border: Border,
) -> Result<[f64; 4], Error> {
    let x = p[0] - 0.5;
    let y = p[1] - 0.5;
    let ix = x.floor() as i64;
    let iy = y.floor() as i64;
    let dx = x - ix as f64;
    let dy = y - iy as f64;
    let mut result = [0.0; 4];
    for (mut xx, mut yy, weight) in [
        (ix, iy, (1.0 - dx) * (1.0 - dy)),
        (ix + 1, iy, dx * (1.0 - dy)),
        (ix, iy + 1, (1.0 - dx) * dy),
        (ix + 1, iy + 1, dx * dy),
    ] {
        if matches!(border, Border::Clamp) {
            xx = xx.clamp(0, w as i64 - 1);
            yy = yy.clamp(0, h as i64 - 1);
        }
        if weight > 0.0 && xx >= 0 && yy >= 0 && xx < w as i64 && yy < h as i64 {
            let pixel = data(xx as u32, yy as u32)?;
            for k in 0..4 {
                result[k] += pixel[k] * weight;
            }
        }
    }
    Ok(result)
}
fn pixel_bounds(dab: &Dab, w: u32, h: u32) -> ([u32; 2], [u32; 2]) {
    let r = dab.diameter / 2.0;
    (
        [
            (dab.center[0] - r).floor().clamp(0.0, w as f64) as u32,
            (dab.center[1] - r).floor().clamp(0.0, h as f64) as u32,
        ],
        [
            (dab.center[0] + r).ceil().clamp(0.0, w as f64) as u32,
            (dab.center[1] + r).ceil().clamp(0.0, h as f64) as u32,
        ],
    )
}
pub(crate) fn apply(
    document: &mut Document,
    index: usize,
    s: &Stroke,
    asset_root: Option<&Path>,
    control: &Control,
) -> Result<Value, Error> {
    let prepared = prepare(s, control)?;
    let world = scene::world_transform(document, index)?;
    crate::pixel_warps::reject_native(&document.items[index])?;
    let content = &document.items[index].content;
    let spec = pixels::spec(content)?;
    let (w, h) = (spec.width, spec.height);
    let (mut low, mut high) = ([w, h], [0, 0]);
    let mut minimum_work = 0u64;
    for (i, dab) in prepared.dabs.iter().enumerate() {
        if i % 64 == 0 {
            control.check()?;
        }
        if dab.diameter == 0.0 || dab.opacity == 0.0 || s.flow == 0.0 || s.opacity == 0.0 {
            continue;
        }
        let (a, b) = pixel_bounds(dab, w, h);
        let area = (b[0] - a[0]) as u64 * (b[1] - a[1]) as u64;
        minimum_work += area;
        if minimum_work > MAX_WORK {
            return Err(limit(
                "Brush footprint preflight exceeds 67108864 work units",
            ));
        }
        if area > 0 {
            low = [low[0].min(a[0]), low[1].min(a[1])];
            high = [high[0].max(b[0]), high[1].max(b[1])];
        }
    }
    if high == [0, 0] {
        low = [0, 0];
    }
    let region = crate::sample_store::Region {
        x: low[0],
        y: low[1],
        width: high[0] - low[0],
        height: high[1] - low[1],
    };
    let count = region.width as u64 * region.height as u64;
    if count > crate::sample_store::MAX_REGION_PIXELS {
        return Err(limit(
            "Brush deposition bounds exceed the 65536-pixel local edit window",
        ));
    }
    // Include original/working/frozen-dab/output windows, weights, exact hex
    // patches, source preparation/cache and complete replacement blocks.
    let processing_memory_bytes = count * 256
        + 8 * 1024 * 1024
        + pixels::memory(content)
        + pixels::replacement_memory(content, region);
    if processing_memory_bytes > MAX_MEMORY_BYTES {
        return Err(limit(
            "Brush preparation and replacement blocks exceed the processing memory bound",
        ));
    }
    let mut work = Work { count: 0, control };
    let mut target =
        pixels::Pixels::new(content, asset_root, "UNSUPPORTED_BRUSH_ENCODING", &mut work)?;
    let source_hash = target.identity.clone();
    let stride = target.stride();
    let mut original = Vec::with_capacity(count as usize * stride);
    for y in low[1]..high[1] {
        control.check()?;
        for x in low[0]..high[0] {
            original.extend_from_slice(&target.raw(x as usize, y as usize, &mut work)?[..stride]);
        }
    }

    let selection = if s.use_selection {
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
    let mut data: Vec<_> = original
        .chunks_exact(stride)
        .map(|c| pixels::premultiplied(c, spec))
        .collect();
    let mut reservoir = match s.mode {
        Mode::Mixer { color, .. } => premul(color),
        _ => [0.0; 4],
    };
    let mut previous = prepared.dabs[0].center;
    for (dab_index, dab) in prepared.dabs.iter().enumerate() {
        control.check()?;
        if dab.diameter == 0.0 || dab.opacity == 0.0 || s.flow == 0.0 || s.opacity == 0.0 {
            previous = dab.center;
            continue;
        }
        let (dab_low, dab_high) = pixel_bounds(dab, w, h);
        let mut weights = Vec::new();
        let mut sampled = [0.0; 4];
        let mut total = 0.0;
        for y in dab_low[1]..dab_high[1] {
            for x in dab_low[0]..dab_high[0] {
                let mut weight = coverage(dab, s.hardness, x, y, &mut work)?;
                if let Some(t) = &s.texture {
                    let tx = ((x as f64 + 0.5 - t.origin[0]) / t.scale[0])
                        .floor()
                        .rem_euclid(t.width as f64) as usize;
                    let ty = ((y as f64 + 0.5 - t.origin[1]) / t.scale[1])
                        .floor()
                        .rem_euclid(t.height as f64) as usize;
                    weight *= prepared.texture[ty * t.width as usize + tx] as f64 / 255.0;
                }
                if let Some(selection) = &selection {
                    let p = geometry::map(world, [x as f64 + 0.5, y as f64 + 0.5]);
                    let xx = p[0].floor();
                    let yy = p[1].floor();
                    weight *= if xx >= 0.0
                        && yy >= 0.0
                        && xx < document.width as f64
                        && yy < document.height as f64
                    {
                        selection[yy as usize * document.width as usize + xx as usize] as f64
                            / 255.0
                    } else {
                        0.0
                    };
                }
                if weight == 0.0 {
                    continue;
                }
                let i = (y - low[1]) as usize * region.width as usize + (x - low[0]) as usize;
                weights.push((i, x, y, weight * s.flow * dab.opacity));
                total += weight;
                for k in 0..4 {
                    sampled[k] += data[i][k] * weight;
                }
            }
        }
        match s.mode {
            Mode::Paint { color } => {
                let color = premul(color);
                for (i, _, _, a) in weights {
                    data[i] = over(data[i], color, a);
                }
            }
            Mode::Erase {} => {
                for (i, _, _, a) in weights {
                    data[i] = data[i].map(|v| v * (1.0 - a));
                }
            }
            Mode::Mixer {
                color,
                pickup,
                load,
            } => {
                reservoir = interpolate(reservoir, premul(color), load);
                if total > 0.0 {
                    reservoir = interpolate(reservoir, sampled.map(|v| v / total), pickup);
                }
                for (i, _, _, a) in weights {
                    data[i] = over(data[i], reservoir, a);
                }
            }
            Mode::Smudge { border } if dab_index > 0 && !weights.is_empty() => {
                work.add(data.len() as u64)?;
                let prior = data.clone();
                let delta = [dab.center[0] - previous[0], dab.center[1] - previous[1]];
                for (i, x, y, a) in weights {
                    data[i] = interpolate(
                        prior[i],
                        sample(
                            |xx, yy| {
                                if xx >= low[0] && xx < high[0] && yy >= low[1] && yy < high[1] {
                                    Ok(prior[(yy - low[1]) as usize * region.width as usize
                                        + (xx - low[0]) as usize])
                                } else {
                                    // No dab can write outside this window. Read
                                    // those donor cells from the immutable source.
                                    target.sample(xx as usize, yy as usize, &mut work)
                                }
                            },
                            w,
                            h,
                            [x as f64 + 0.5 - delta[0], y as f64 + 0.5 - delta[1]],
                            border,
                        )?,
                        a,
                    );
                }
            }
            Mode::Smudge { .. } => (),
        }
        previous = dab.center;
    }
    let mut output = original.clone();
    let mut changed = 0usize;
    let mut bounds = [w, h, 0, 0];
    for (i, (before, after)) in original.chunks_exact(stride).zip(data).enumerate() {
        work.add(1)?;
        let a = pixels::premultiplied(before, spec);
        let color = interpolate(a, after, s.opacity);
        if color == a {
            continue;
        }
        let rgba = pixels::encode(color, spec)?;
        if &rgba[..stride] != before {
            output[i * stride..i * stride + stride].copy_from_slice(&rgba[..stride]);
            changed += 1;
            let x = i as u32 % region.width + low[0];
            let y = i as u32 / region.width + low[1];
            bounds = [
                bounds[0].min(x),
                bounds[1].min(y),
                bounds[2].max(x + 1),
                bounds[3].max(y + 1),
            ];
        }
    }
    let (next, result_hash) = if changed > 0 {
        target.replace(content, region, &output, &mut work)?
    } else {
        (content.clone(), source_hash.clone())
    };
    control.check()?;
    document.items[index].content = next;
    Ok(
        json!({"algorithm":ALGORITHM,"stroke_sha256":prepared.hash,"source_sha256":source_hash,"result_sha256":result_hash,"dab_count":prepared.dabs.len(),"path_length":prepared.length,"dab_bounds":prepared.bounds,"changed_pixels":changed,"changed_bounds":if changed>0 {Some(bounds)} else {None},"work":work.count,"coordinates":"native_pixel_grid","selection_sampling":"world_mapped_native_centers","coverage_numeric_tolerance":COVERAGE_TOLERANCE,"source_identity_kind":target.identity_kind,"result_identity_kind":target.identity_kind,"sample_type":spec,"working_window":if count>0 {Some([region.x,region.y,region.width,region.height])} else {None},"processing_memory_bound_bytes":processing_memory_bytes,"files_written":false,"outside_window_preserved":true,"quantization":"one_final_straight_encoding_at_target_native_depth_per_stroke","stroke_opacity":"final_premultiplied_interpolation_with_original"}),
    )
}
