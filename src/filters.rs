//! Original bounded, editable viewport filters over premultiplied encoded-sRGB buffers.
use crate::{Error, model::*};
pub(crate) mod transport;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;

pub const MAX_STACK: usize = 8;
pub const MAX_DOCUMENT_FILTERS: usize = 64;
pub const MAX_WORK: u64 = 67_108_864;
fn yes() -> bool {
    true
}
fn one() -> f64 {
    1.0
}
fn samples() -> u32 {
    33
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Border {
    #[default]
    Transparent,
    Clamp,
    Reflect,
    Wrap,
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Operator {
    Creative {
        operator: Box<crate::creative_filters::Operator>,
    },
    Detail {
        operator: Box<crate::detail_filters::Operator>,
    },
    Spatial {
        operator: Box<crate::spatial_filters::Operator>,
    },
    Box {
        radius: u32,
    },
    Gaussian {
        sigma: f64,
    },
    Directional {
        length: f64,
        angle: f64,
        #[serde(default = "samples")]
        samples: u32,
    },
    Radial {
        center: Point,
        angle: f64,
        #[serde(default)]
        zoom: f64,
        #[serde(default = "samples")]
        samples: u32,
    },
    Surface {
        radius: u32,
        threshold: f64,
    },
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Filter {
    pub id: String,
    pub operator: Operator,
    #[serde(default = "yes")]
    pub enabled: bool,
    #[serde(default = "one")]
    pub opacity: f64,
    #[serde(default)]
    pub blend: BlendMode,
    #[serde(default)]
    pub border: Border,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub mask: Option<Box<crate::masks::Mask>>,
}
fn range(x: f64, lo: f64, hi: f64) -> bool {
    x.is_finite() && (lo..=hi).contains(&x)
}
impl Operator {
    fn validate(&self, world: Matrix) -> Result<(), Error> {
        let valid = match *self {
            Self::Creative { ref operator } => return operator.validate(world),
            Self::Detail { ref operator } => return operator.validate(),
            Self::Spatial { ref operator } => return operator.validate(world),
            Self::Box { radius } => radius <= 32,
            Self::Gaussian { sigma } => range(sigma, 0.0, 16.0),
            Self::Directional {
                length,
                angle,
                samples,
            } => {
                range(length, 0.0, 64.0)
                    && range(angle, -360000.0, 360000.0)
                    && (3..=129).contains(&samples)
                    && samples % 2 == 1
            }
            Self::Radial {
                center,
                angle,
                zoom,
                samples,
            } => {
                center
                    .iter()
                    .all(|v| range(*v, -MAX_COORDINATE, MAX_COORDINATE))
                    && range(angle, -180.0, 180.0)
                    && range(zoom, -1.0, 1.0)
                    && (3..=129).contains(&samples)
                    && samples % 2 == 1
            }
            Self::Surface { radius, threshold } => radius <= 16 && range(threshold, 0.0, 1.0),
        };
        if valid {
            Ok(())
        } else {
            Err(invalid(
                "Filter controls exceed declared radius, angle, sample or threshold limits",
            ))
        }
    }
    pub fn work(&self, scale: u32) -> u64 {
        let s = scale as u64;
        8 + match *self {
            Self::Creative { ref operator } => operator.work(scale),
            Self::Detail { ref operator } => operator.work(scale),
            Self::Spatial { ref operator } => operator.work(),
            Self::Box { radius } => 2 * (2 * radius as u64 * s + 1),
            Self::Gaussian { sigma } => 2 * (2 * (3.0 * sigma * scale as f64).ceil() as u64 + 1),
            Self::Directional { samples, .. } | Self::Radial { samples, .. } => 4 * samples as u64,
            Self::Surface { radius, .. } => 8 * (2 * radius as u64 * s + 1).pow(2),
        }
    }
}
pub fn work(item: &Item, scale: u32) -> u64 {
    item.filters
        .iter()
        .map(|f| f.operator.work(scale) + 4 * u64::from(f.mask.is_some()))
        .sum()
}
pub fn validate(item: &Item, world: Matrix) -> Result<usize, Error> {
    if item.filters.len() > MAX_STACK {
        return Err(limit("Item exceeds 8 filters"));
    }
    if !item.filters.is_empty()
        && matches!(
            item.content,
            Content::Adjustment { .. }
                | Content::Group {
                    isolated: false,
                    ..
                }
        )
    {
        return Err(Error::new(
            "UNSUPPORTED",
            "Filters require drawable content or an isolated container",
        ));
    }
    let mut seen = HashSet::new();
    let mut pixels = 0;
    for f in &item.filters {
        if !valid_id(&f.id) || !seen.insert(&f.id) {
            return Err(invalid(
                "Filter IDs must be valid and unique within the item",
            ));
        }
        f.operator.validate(world)?;
        if let Operator::Spatial { operator } = &f.operator {
            pixels += operator.stored_pixels();
        }
        if !range(f.opacity, 0.0, 1.0) {
            return Err(invalid("Filter opacity must be in 0..=1"));
        }
        if let Some(m) = &f.mask {
            pixels += m.validate(world)?;
        }
    }
    Ok(pixels)
}
pub(crate) fn index(x: i64, n: u32, border: Border) -> Option<usize> {
    let n = n as i64;
    Some(match border {
        Border::Transparent => {
            if x < 0 || x >= n {
                return None;
            } else {
                x
            }
        }
        Border::Clamp => x.clamp(0, n - 1),
        Border::Wrap => x.rem_euclid(n),
        Border::Reflect => {
            let x = x.rem_euclid(2 * n);
            if x < n { x } else { 2 * n - 1 - x }
        }
    } as usize)
}
pub(crate) fn at(pixels: &[f64], size: [u32; 2], x: i64, y: i64, border: Border) -> [f64; 4] {
    let [w, h] = size;
    match (index(x, w, border), index(y, h, border)) {
        (Some(x), Some(y)) => pixels[(y * w as usize + x) * 4..][..4].try_into().unwrap(),
        _ => [0.0; 4],
    }
}
pub(crate) fn sample(pixels: &[f64], size: [u32; 2], p: Point, border: Border) -> [f64; 4] {
    let [x, y] = p;
    let ix = x.floor() as i64;
    let iy = y.floor() as i64;
    let fx = x - x.floor();
    let fy = y - y.floor();
    let mut sum = [0.0; 4];
    for (dx, wx) in [(0, 1.0 - fx), (1, fx)] {
        for (dy, wy) in [(0, 1.0 - fy), (1, fy)] {
            let p = at(pixels, size, ix + dx, iy + dy, border);
            for c in 0..4 {
                sum[c] += p[c] * wx * wy;
            }
        }
    }
    sum
}
pub(crate) fn straight(p: [f64; 4]) -> [f64; 4] {
    if p[3] == 0.0 {
        [0.0; 4]
    } else {
        [p[0] / p[3], p[1] / p[3], p[2] / p[3], p[3]]
    }
}
pub(crate) fn evaluate(
    pixels: &[f64],
    size: [u32; 3],
    world: Matrix,
    operator: &Operator,
    border: Border,
) -> Vec<f64> {
    let [w, h, scale] = size;
    if transport::supports(operator) {
        return transport::evaluate(pixels, size, world, operator, border, None)
            .expect("Validated spatial filter without cancellation");
    }
    match operator {
        Operator::Creative { operator } => {
            return crate::creative_filters::evaluate(pixels, size, world, operator, border);
        }
        Operator::Detail { operator } => {
            return crate::detail_filters::evaluate(pixels, size, operator, border);
        }
        _ => {}
    }
    let Operator::Surface { radius, threshold } = *operator else {
        unreachable!()
    };
    let mut out = vec![0.0; pixels.len()];
    for y in 0..h {
        for x in 0..w {
            let dst = &mut out[(y as usize * w as usize + x as usize) * 4..][..4];
            let mut count = 0.0;
            let center = straight(at(pixels, [w, h], x as i64, y as i64, border));
            let r = (radius * scale) as i64;
            for dy in -r..=r {
                for dx in -r..=r {
                    let p = at(pixels, [w, h], x as i64 + dx, y as i64 + dy, border);
                    let color = straight(p);
                    if (0..4).all(|c| (color[c] - center[c]).abs() <= threshold) {
                        for c in 0..4 {
                            dst[c] += p[c];
                        }
                        count += 1.0;
                    }
                }
            }
            for v in dst {
                *v /= count;
            }
        }
    }
    out
}
pub(crate) fn apply(
    item: &Item,
    pixels: &mut [f64],
    size: [u32; 3],
    world: Matrix,
) -> Result<(), Error> {
    let [width, _, scale] = size;
    for f in item
        .filters
        .iter()
        .filter(|f| f.enabled && f.opacity != 0.0)
    {
        let filtered = evaluate(pixels, size, world, &f.operator, f.border);
        let mask = f
            .mask
            .as_ref()
            .filter(|m| m.enabled)
            .map(|m| crate::masks::prepare(m, world))
            .transpose()?;
        for (i, (dst, src)) in pixels
            .as_chunks_mut::<4>()
            .0
            .iter_mut()
            .zip(filtered.as_chunks::<4>().0)
            .enumerate()
        {
            let weight = f.opacity
                * mask.as_ref().map_or(1.0, |m| {
                    m.sample([
                        (i % width as usize) as f64 / scale as f64 + 0.5 / scale as f64,
                        (i / width as usize) as f64 / scale as f64 + 0.5 / scale as f64,
                    ])
                });
            let before = straight(*dst);
            let after = straight(*src);
            let blended = crate::blending::mix(
                [before[0], before[1], before[2]],
                [after[0], after[1], after[2]],
                f.blend,
            );
            // Filter mix replaces alpha as well as color; it is not a duplicate source-over layer.
            let alpha = (1.0 - weight) * dst[3] + weight * src[3];
            for c in 0..3 {
                let effect = (1.0 - before[3]) * after[c] + before[3] * blended[c];
                dst[c] = ((1.0 - weight) * dst[c] + weight * src[3] * effect)
                    .clamp(0.0, alpha.clamp(0.0, 1.0));
            }
            dst[3] = alpha.clamp(0.0, 1.0);
        }
    }
    Ok(())
}
