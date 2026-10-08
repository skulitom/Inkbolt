//! Original, bounded paint evaluation in local coordinates. Geometry coverage is separate.
use crate::{
    Error, geometry,
    model::{Color, MAX_COORDINATE, Matrix, Point, identity, invalid, limit},
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

pub const MAX_PAINT_SAMPLES: usize = 4096;
pub const MAX_STOPS: usize = 64;
pub const MAX_PATTERN_PIXELS: usize = 4096;
pub const MAX_PAINT_WORK: u64 = 134_217_728;

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(untagged)]
pub enum Paint {
    Solid(Color),
    Precise(Precise),
    Named(crate::swatches::Reference),
    Field(Field),
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Precise {
    pub rgba: [f64; 4],
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Interpolation {
    #[default]
    Srgb,
    LinearRgb,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Spread {
    #[default]
    Pad,
    Repeat,
    Reflect,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Dither {
    #[default]
    None,
    Ordered4x4,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Stop {
    pub offset: f64,
    pub color: Color,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Anchor {
    pub point: Point,
    pub color: Color,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Field {
    Mesh {
        mesh: Box<crate::meshes::Mesh>,
        #[serde(default)]
        space: Interpolation,
        #[serde(default = "identity")]
        transform: Matrix,
    },
    Linear {
        start: Point,
        end: Point,
        stops: Vec<Stop>,
        #[serde(default)]
        spread: Spread,
        #[serde(default)]
        space: Interpolation,
        #[serde(default = "identity")]
        transform: Matrix,
    },
    Radial {
        center: Point,
        radius: f64,
        stops: Vec<Stop>,
        #[serde(default)]
        spread: Spread,
        #[serde(default)]
        space: Interpolation,
        #[serde(default = "identity")]
        transform: Matrix,
    },
    Freeform {
        anchors: Vec<Anchor>,
        #[serde(default)]
        space: Interpolation,
        #[serde(default = "identity")]
        transform: Matrix,
    },
    Pattern {
        width: u32,
        height: u32,
        rgba_hex: String,
        #[serde(default = "identity")]
        transform: Matrix,
    },
}
impl Field {
    pub fn transform(&self) -> Matrix {
        match self {
            Self::Mesh { transform, .. }
            | Self::Linear { transform, .. }
            | Self::Radial { transform, .. }
            | Self::Freeform { transform, .. }
            | Self::Pattern { transform, .. } => *transform,
        }
    }
}
fn point(p: Point) -> Result<(), Error> {
    if p.iter().any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE) {
        return Err(invalid(
            "Paint coordinates must be finite and within coordinate limits",
        ));
    }
    Ok(())
}
pub fn validate(paint: &Paint) -> Result<(usize, usize), Error> {
    if let Paint::Named(reference) = paint {
        reference.validate()?;
    }
    if let Paint::Precise(color) = paint
        && color
            .rgba
            .iter()
            .any(|v| !v.is_finite() || !(0.0..=1.0).contains(v))
    {
        return Err(invalid(
            "Precise solid paint requires finite RGBA components in 0..=1",
        ));
    }
    let Paint::Field(field) = paint else {
        return Ok((0, 0));
    };
    geometry::validate_matrix(field.transform())?;
    let stops = match field {
        Field::Mesh { mesh, space, .. } => {
            mesh.prepare(*space)?;
            return Ok((0, mesh.knots.len()));
        }
        Field::Linear {
            start, end, stops, ..
        } => {
            point(*start)?;
            point(*end)?;
            if (end[0] - start[0]).hypot(end[1] - start[1]) < 0.001 {
                return Err(invalid(
                    "Linear gradient endpoints must be at least 0.001 apart",
                ));
            }
            stops
        }
        Field::Radial {
            center,
            radius,
            stops,
            ..
        } => {
            point(*center)?;
            if !radius.is_finite() || !(0.001..=MAX_COORDINATE).contains(radius) {
                return Err(invalid("Radial gradient radius must be in 0.001..=32768"));
            }
            stops
        }
        Field::Freeform { anchors, .. } => {
            if !(2..=MAX_STOPS).contains(&anchors.len()) {
                return Err(limit("Freeform paint requires 2 through 64 anchors"));
            }
            for (i, a) in anchors.iter().enumerate() {
                point(a.point)?;
                if anchors[..i]
                    .iter()
                    .any(|b| (a.point[0] - b.point[0]).hypot(a.point[1] - b.point[1]) < 0.001)
                {
                    return Err(invalid("Freeform anchors must be at least 0.001 apart"));
                }
            }
            return Ok((0, anchors.len()));
        }
        Field::Pattern {
            width,
            height,
            rgba_hex,
            ..
        } => {
            let count = *width as u64 * *height as u64;
            if *width == 0 || *height == 0 || count > MAX_PATTERN_PIXELS as u64 {
                return Err(limit("Pattern tiles require 1 through 4096 pixels"));
            }
            if rgba_hex.len() != count as usize * 8
                || !rgba_hex.bytes().all(|c| c.is_ascii_hexdigit())
            {
                return Err(invalid(
                    "Pattern tile requires exactly width*height straight RGBA8 hex values",
                ));
            }
            return Ok((count as usize, 0));
        }
    };
    if !(2..=MAX_STOPS).contains(&stops.len()) {
        return Err(limit("Gradients require 2 through 64 stops"));
    }
    if stops
        .iter()
        .any(|s| !s.offset.is_finite() || !(0.0..=1.0).contains(&s.offset))
        || stops.windows(2).any(|s| s[0].offset > s[1].offset)
    {
        return Err(invalid(
            "Gradient offsets must be ordered, finite and in 0..=1",
        ));
    }
    Ok((0, stops.len()))
}
pub fn work(paint: &Paint) -> u64 {
    match paint {
        Paint::Field(Field::Mesh { mesh, .. }) => {
            if mesh.knots.iter().any(|k| k.offset != [0.0; 2]) {
                crate::meshes::INVERSE_STEPS as u64
            } else {
                16
            }
        }
        Paint::Field(Field::Freeform { anchors, .. }) => anchors.len() as u64,
        _ => 1,
    }
}
pub(crate) fn validate_world(paint: &Paint, world: Matrix) -> Result<(), Error> {
    if let Paint::Field(field) = paint {
        geometry::validate_matrix(geometry::multiply(world, field.transform()))?;
    }
    Ok(())
}
pub(crate) fn decode(v: f64) -> f64 {
    if v <= 0.04045 {
        v / 12.92
    } else {
        ((v + 0.055) / 1.055).powf(2.4)
    }
}
pub(crate) fn encode(v: f64) -> f64 {
    if v <= 0.0031308 {
        v * 12.92
    } else {
        1.055 * v.powf(1.0 / 2.4) - 0.055
    }
}
pub(crate) fn color(c: Color, space: Interpolation) -> [f64; 4] {
    std::array::from_fn(|i| {
        let v = c[i] as f64 / 255.0;
        if i < 3 && space == Interpolation::LinearRgb {
            decode(v)
        } else {
            v
        }
    })
}
pub(crate) fn output(mut c: [f64; 4], space: Interpolation) -> [f64; 4] {
    if space == Interpolation::LinearRgb {
        for v in &mut c[..3] {
            *v = encode(*v);
        }
    }
    c
}
fn ramp(stops: &[Stop], t: f64, spread: Spread, space: Interpolation) -> [f64; 4] {
    let t = match spread {
        Spread::Pad => t.clamp(0.0, 1.0),
        Spread::Repeat => t.rem_euclid(1.0),
        Spread::Reflect => {
            let v = t.rem_euclid(2.0);
            if v > 1.0 { 2.0 - v } else { v }
        }
    };
    let right = stops.partition_point(|s| s.offset <= t);
    if right == 0 {
        return stops[0].color.map(|v| v as f64 / 255.0);
    }
    if right == stops.len() {
        return stops[right - 1].color.map(|v| v as f64 / 255.0);
    }
    let a = &stops[right - 1];
    let b = &stops[right];
    let f = (t - a.offset) / (b.offset - a.offset);
    let ca = color(a.color, space);
    let cb = color(b.color, space);
    output(std::array::from_fn(|i| ca[i] + (cb[i] - ca[i]) * f), space)
}
/// Construct once for a validated paint. `world` maps item-local points to canvas space.
pub struct Sampler<'a> {
    mesh: Option<crate::meshes::Prepared>,
    paint: &'a Paint,
    inverse: Matrix,
    tile: Vec<u8>,
}
impl<'a> Sampler<'a> {
    pub fn new(paint: &'a Paint, world: Matrix) -> Result<Self, Error> {
        validate(paint)?;
        let transform = match paint {
            Paint::Solid(_) | Paint::Precise(_) => identity(),
            Paint::Named(_) => {
                return Err(Error::new(
                    "SWATCH_CONTEXT_REQUIRED",
                    "Resolve named paint against its document before sampling",
                ));
            }
            Paint::Field(f) => f.transform(),
        };
        let inverse = geometry::inverse(geometry::multiply(world, transform))?;
        let tile = match paint {
            Paint::Field(Field::Pattern { rgba_hex, .. }) => crate::render::unhex(rgba_hex),
            _ => Vec::new(),
        };
        let mesh = match paint {
            Paint::Field(Field::Mesh { mesh, space, .. }) => Some(mesh.prepare(*space)?),
            _ => None,
        };
        Ok(Self {
            mesh,
            paint,
            inverse,
            tile,
        })
    }
    pub fn sample(&self, canvas: Point) -> [f64; 4] {
        let p = geometry::map(self.inverse, canvas);
        match self.paint {
            Paint::Field(Field::Mesh { .. }) => self.mesh.as_ref().unwrap().sample(p),
            Paint::Solid(c) => c.map(|v| v as f64 / 255.0),
            Paint::Precise(c) => c.rgba,
            Paint::Named(_) => unreachable!("Unresolved named paint cannot construct a sampler"),
            Paint::Field(Field::Linear {
                start,
                end,
                stops,
                spread,
                space,
                ..
            }) => {
                let dx = end[0] - start[0];
                let dy = end[1] - start[1];
                let t = ((p[0] - start[0]) * dx + (p[1] - start[1]) * dy) / (dx * dx + dy * dy);
                ramp(stops, t, *spread, *space)
            }
            Paint::Field(Field::Radial {
                center,
                radius,
                stops,
                spread,
                space,
                ..
            }) => ramp(
                stops,
                (p[0] - center[0]).hypot(p[1] - center[1]) / radius,
                *spread,
                *space,
            ),
            Paint::Field(Field::Freeform { anchors, space, .. }) => {
                // Normalize inverse-square weights by the nearest squared distance.
                // This is bounded even at an anchor and preserves exact anchor colors.
                let distance =
                    |a: &Anchor| (p[0] - a.point[0]).powi(2) + (p[1] - a.point[1]).powi(2);
                let nearest = anchors.iter().map(distance).fold(f64::INFINITY, f64::min);
                let mut sum = 0.0;
                let mut mixed = [0.0; 4];
                for a in anchors {
                    let d = distance(a);
                    if d == 0.0 {
                        return a.color.map(|v| v as f64 / 255.0);
                    }
                    let weight = nearest / d;
                    let c = color(a.color, *space);
                    for i in 0..4 {
                        mixed[i] += weight * c[i];
                    }
                    sum += weight;
                }
                output(mixed.map(|v| v / sum), *space)
            }
            Paint::Field(Field::Pattern { width, height, .. }) => {
                let x = p[0].floor().rem_euclid(*width as f64) as usize;
                let y = p[1].floor().rem_euclid(*height as f64) as usize;
                let i = (y * *width as usize + x) * 4;
                std::array::from_fn(|c| self.tile[i + c] as f64 / 255.0)
            }
        }
    }
}
/// Ordered RGB quantization noise, anchored to layer-local pixel cells. Alpha is unchanged.
pub fn dither(mut c: [f64; 4], p: Point, mode: Dither) -> [f64; 4] {
    if mode == Dither::Ordered4x4 {
        const RANKS: [[u8; 4]; 4] = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]];
        let x = p[0].floor().rem_euclid(4.0) as usize;
        let y = p[1].floor().rem_euclid(4.0) as usize;
        let noise = ((RANKS[y][x] as f64 + 0.5) / 16.0 - 0.5) / 255.0;
        for v in &mut c[..3] {
            *v = (*v + noise).clamp(0.0, 1.0);
        }
    }
    c
}
