//! Original color controls and bounded lookup evaluation for the adjustment pipeline.
use crate::{Error, model::*, paint::Interpolation};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
pub const MAX_LUT_1D: usize = 4096;
pub const MAX_LUT_3D_SIDE: u32 = 33;
pub const MAX_DOCUMENT_LUT_ENTRIES: usize = 65536;
pub const MAX_MAP_STOPS: usize = 64;
pub type Rgb = [f64; 3];
pub fn domain() -> [Rgb; 2] {
    [[0.0; 3], [1.0; 3]]
}
fn one() -> f64 {
    1.0
}
fn yes() -> bool {
    true
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Gray {
    #[default]
    Luma,
    Average,
    Lightness,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CorrectionMode {
    #[default]
    Relative,
    Absolute,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq, Hash)]
#[serde(rename_all = "snake_case")]
pub enum Band {
    Reds,
    Yellows,
    Greens,
    Cyans,
    Blues,
    Magentas,
    Whites,
    Neutrals,
    Blacks,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Correction {
    pub band: Band,
    pub cmyk: [f64; 4],
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Stop {
    pub offset: f64,
    pub color: Rgb,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Adjustment {
    HueSaturation {
        #[serde(default)]
        hue: f64,
        #[serde(default)]
        saturation: f64,
        #[serde(default)]
        lightness: f64,
    },
    Desaturate {
        #[serde(default)]
        method: Gray,
        #[serde(default = "one")]
        amount: f64,
    },
    ChannelMixer {
        matrix: [Rgb; 3],
        #[serde(default)]
        offset: Rgb,
    },
    Balance {
        #[serde(default)]
        shadows: Rgb,
        #[serde(default)]
        midtones: Rgb,
        #[serde(default)]
        highlights: Rgb,
        #[serde(default = "yes")]
        preserve_luma: bool,
    },
    Selective {
        corrections: Vec<Correction>,
        #[serde(default)]
        mode: CorrectionMode,
    },
    Lut1d {
        values: Vec<Rgb>,
        #[serde(default = "domain")]
        domain: [Rgb; 2],
        #[serde(default = "one")]
        strength: f64,
    },
    Lut3d {
        size: u32,
        values: Vec<Rgb>,
        #[serde(default = "domain")]
        domain: [Rgb; 2],
        #[serde(default = "one")]
        strength: f64,
    },
    GradientMap {
        stops: Vec<Stop>,
        #[serde(default)]
        space: Interpolation,
        #[serde(default = "one")]
        strength: f64,
    },
}
fn range(x: f64, low: f64, high: f64) -> bool {
    x.is_finite() && (low..=high).contains(&x)
}
fn values_ok(v: &[Rgb], d: [Rgb; 2], s: f64) -> bool {
    range(s, 0.0, 1.0)
        && v.iter().flatten().all(|&x| range(x, -16.0, 16.0))
        && d.iter().flatten().all(|&x| range(x, -16.0, 16.0))
        && (0..3).all(|i| d[0][i] < d[1][i])
}
impl Adjustment {
    pub fn validate(&self) -> Result<(), Error> {
        let valid = match self {
            Self::HueSaturation {
                hue,
                saturation,
                lightness,
            } => {
                range(*hue, -360000.0, 360000.0)
                    && range(*saturation, -1.0, 1.0)
                    && range(*lightness, -1.0, 1.0)
            }
            Self::Desaturate { amount, .. } => range(*amount, 0.0, 1.0),
            Self::ChannelMixer { matrix, offset } => matrix
                .iter()
                .flatten()
                .chain(offset)
                .all(|&x| range(x, -4.0, 4.0)),
            Self::Balance {
                shadows,
                midtones,
                highlights,
                ..
            } => shadows
                .iter()
                .chain(midtones)
                .chain(highlights)
                .all(|&x| range(x, -1.0, 1.0)),
            Self::Selective { corrections, .. } => {
                let mut seen = HashSet::new();
                (1..=9).contains(&corrections.len())
                    && corrections
                        .iter()
                        .all(|c| seen.insert(c.band) && c.cmyk.iter().all(|&x| range(x, -1.0, 1.0)))
            }
            Self::Lut1d {
                values,
                domain,
                strength,
            } => (2..=MAX_LUT_1D).contains(&values.len()) && values_ok(values, *domain, *strength),
            Self::Lut3d {
                size,
                values,
                domain,
                strength,
            } => {
                (2..=MAX_LUT_3D_SIDE).contains(size)
                    && values.len() == (*size as usize).pow(3)
                    && values_ok(values, *domain, *strength)
            }
            Self::GradientMap {
                stops, strength, ..
            } => {
                range(*strength, 0.0, 1.0)
                    && (2..=MAX_MAP_STOPS).contains(&stops.len())
                    && stops.iter().all(|s| {
                        range(s.offset, 0.0, 1.0) && s.color.iter().all(|&x| range(x, 0.0, 1.0))
                    })
                    && stops.windows(2).all(|p| p[0].offset <= p[1].offset)
            }
        };
        if valid {
            Ok(())
        } else {
            Err(invalid(
                "Color adjustment has invalid parameters, table dimensions or duplicate bands",
            ))
        }
    }
    pub fn entries(&self) -> usize {
        match self {
            Self::Lut1d { values, .. } | Self::Lut3d { values, .. } => values.len(),
            _ => 0,
        }
    }
    pub fn work(&self) -> u64 {
        match self {
            Self::Selective { corrections, .. } => 16 + corrections.len() as u64 * 4,
            Self::Lut3d { .. } => 32,
            Self::GradientMap { .. } => 16,
            _ => 16,
        }
    }
}
fn luma(c: Rgb) -> f64 {
    c[0] * 0.2126 + c[1] * 0.7152 + c[2] * 0.0722
}
fn shift(x: f64, a: f64) -> f64 {
    if a >= 0.0 {
        x + (1.0 - x) * a
    } else {
        x * (1.0 + a)
    }
}
fn hsl(c: Rgb) -> [f64; 3] {
    let high = c.into_iter().fold(0.0, f64::max);
    let low = c.into_iter().fold(1.0, f64::min);
    let delta = high - low;
    let lightness = (high + low) * 0.5;
    if delta == 0.0 {
        return [0.0, 0.0, lightness];
    }
    let hue = if high == c[0] {
        (c[1] - c[2]) / delta
    } else if high == c[1] {
        (c[2] - c[0]) / delta + 2.0
    } else {
        (c[0] - c[1]) / delta + 4.0
    };
    [
        60.0 * hue.rem_euclid(6.0),
        delta
            / if lightness <= 0.5 {
                high + low
            } else {
                2.0 - high - low
            },
        lightness,
    ]
}
fn from_hsl([h, s, l]: [f64; 3]) -> Rgb {
    let chroma = if l <= 0.5 {
        2.0 * l * s
    } else {
        2.0 * (1.0 - l) * s
    };
    let sector = h.rem_euclid(360.0) / 60.0;
    let other = chroma * (1.0 - (sector.rem_euclid(2.0) - 1.0).abs());
    let rgb = match sector as u32 {
        0 => [chroma, other, 0.0],
        1 => [other, chroma, 0.0],
        2 => [0.0, chroma, other],
        3 => [0.0, other, chroma],
        4 => [other, 0.0, chroma],
        _ => [chroma, 0.0, other],
    };
    rgb.map(|x| x + l - chroma * 0.5)
}
fn preserve(c: Rgb, target: f64) -> Rgb {
    let mean = luma(c);
    let delta = c.map(|x| x - mean);
    let mut scale = 1.0_f64;
    for d in delta {
        if d > 0.0 {
            scale = scale.min((1.0 - target) / d)
        } else if d < 0.0 {
            scale = scale.min(-target / d)
        }
    }
    delta.map(|d| target + scale * d)
}
fn coordinate(x: f64, low: f64, high: f64, n: usize) -> (usize, f64) {
    let p = ((x - low) / (high - low)).clamp(0.0, 1.0) * (n - 1) as f64;
    let base = (p as usize).min(n - 2);
    (base, p - base as f64)
}
fn mix(c: Rgb, v: Rgb, strength: f64) -> Rgb {
    std::array::from_fn(|i| c[i] + strength * (v[i] - c[i]))
}
fn membership(c: Rgb, band: Band) -> f64 {
    let [h, _, l] = hsl(c);
    let chroma = c.into_iter().fold(0.0, f64::max) - c.into_iter().fold(1.0, f64::min);
    let center = match band {
        Band::Reds => 0.0,
        Band::Yellows => 60.0,
        Band::Greens => 120.0,
        Band::Cyans => 180.0,
        Band::Blues => 240.0,
        Band::Magentas => 300.0,
        Band::Whites => return (1.0 - chroma) * l * l,
        Band::Neutrals => return (1.0 - chroma) * 2.0 * l * (1.0 - l),
        Band::Blacks => return (1.0 - chroma) * (1.0 - l).powi(2),
    };
    let distance = (h - center + 180.0).rem_euclid(360.0) - 180.0;
    chroma * (1.0 - distance.abs() / 60.0).max(0.0)
}
pub(crate) fn evaluate(c: Rgb, adjustment: &Adjustment) -> Rgb {
    let result = match adjustment {
        Adjustment::HueSaturation {
            hue,
            saturation,
            lightness,
        } => {
            let [h, s, l] = hsl(c);
            from_hsl([h + hue, shift(s, *saturation), shift(l, *lightness)])
        }
        Adjustment::Desaturate { method, amount } => {
            let gray = match method {
                Gray::Luma => luma(c),
                Gray::Average => c.iter().sum::<f64>() / 3.0,
                Gray::Lightness => hsl(c)[2],
            };
            mix(c, [gray; 3], *amount)
        }
        Adjustment::ChannelMixer { matrix, offset } => std::array::from_fn(|i| {
            matrix[i].iter().zip(c).map(|(a, b)| a * b).sum::<f64>() + offset[i]
        }),
        Adjustment::Balance {
            shadows,
            midtones,
            highlights,
            preserve_luma,
        } => {
            let y = luma(c);
            let weights = [(1.0 - y).powi(2), 2.0 * y * (1.0 - y), y * y];
            let mapped = std::array::from_fn(|i| {
                shift(
                    c[i],
                    weights[0] * shadows[i] + weights[1] * midtones[i] + weights[2] * highlights[i],
                )
            });
            if *preserve_luma {
                preserve(mapped, y)
            } else {
                mapped
            }
        }
        Adjustment::Selective { corrections, mode } => {
            let mut changes = [0.0; 3];
            for correction in corrections {
                let weight = membership(c, correction.band);
                for (i, d) in changes.iter_mut().enumerate() {
                    *d -= weight * (correction.cmyk[i] + correction.cmyk[3]);
                }
            }
            std::array::from_fn(|i| match mode {
                CorrectionMode::Absolute => c[i] + changes[i],
                CorrectionMode::Relative => shift(c[i], changes[i].clamp(-1.0, 1.0)),
            })
        }
        Adjustment::Lut1d {
            values,
            domain,
            strength,
        } => {
            let mapped = std::array::from_fn(|i| {
                let (n, t) = coordinate(c[i], domain[0][i], domain[1][i], values.len());
                values[n][i] + t * (values[n + 1][i] - values[n][i])
            });
            mix(c, mapped, *strength)
        }
        Adjustment::Lut3d {
            size,
            values,
            domain,
            strength,
        } => {
            let n = *size as usize;
            let coords: [(usize, f64); 3] =
                std::array::from_fn(|i| coordinate(c[i], domain[0][i], domain[1][i], n));
            let mut mapped = [0.0; 3];
            for corner in 0..8 {
                let mut index = [0; 3];
                let mut weight = 1.0;
                for i in 0..3 {
                    let bit = (corner >> i) & 1;
                    index[i] = coords[i].0 + bit;
                    weight *= if bit == 0 {
                        1.0 - coords[i].1
                    } else {
                        coords[i].1
                    };
                }
                let sample = values[(index[2] * n + index[1]) * n + index[0]];
                for i in 0..3 {
                    mapped[i] += sample[i] * weight;
                }
            }
            mix(c, mapped, *strength)
        }
        Adjustment::GradientMap {
            stops,
            space,
            strength,
        } => {
            let position = luma(c);
            let right = stops.partition_point(|s| s.offset <= position);
            let mapped = if right == 0 {
                stops[0].color
            } else if right == stops.len() {
                stops[right - 1].color
            } else {
                let a = &stops[right - 1];
                let b = &stops[right];
                let t = (position - a.offset) / (b.offset - a.offset);
                std::array::from_fn(|i| {
                    if *space == Interpolation::LinearRgb {
                        let x = crate::paint::decode(a.color[i]);
                        crate::paint::encode(x + t * (crate::paint::decode(b.color[i]) - x))
                    } else {
                        a.color[i] + t * (b.color[i] - a.color[i])
                    }
                })
            };
            mix(c, mapped, *strength)
        }
    };
    result.map(|x| x.clamp(0.0, 1.0))
}
