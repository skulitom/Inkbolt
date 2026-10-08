//! Original bounded graphic treatments over the shared encoded-sRGB viewport.
use crate::{
    Error,
    filters::{self, Border},
    geometry,
    model::*,
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Extreme {
    Minimum,
    Maximum,
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Operator {
    Twist {
        center: Point,
        radius: f64,
        angle: f64,
    },
    Relief {
        angle: f64,
        distance: f64,
        strength: f64,
    },
    HighPass {
        sigma: f64,
    },
    Extrema {
        radius: u32,
        mode: Extreme,
    },
    ToneFold {
        threshold: f64,
    },
    EdgeInk {
        strength: f64,
    },
    StrokeRank {
        radius: u32,
        angle: f64,
        quantile: f64,
    },
    ValueField {
        seed: u32,
        cell_size: f64,
        octaves: u32,
        origin: Point,
        low: [u8; 3],
        high: [u8; 3],
    },
    FieldRepair {
        keep_parity: u32,
    },
}
fn range(x: f64, lo: f64, hi: f64) -> bool {
    x.is_finite() && (lo..=hi).contains(&x)
}
impl Operator {
    pub fn validate(&self, world: Matrix) -> Result<(), Error> {
        geometry::inverse(world)?;
        let point = |p: Point| p.iter().all(|v| range(*v, -MAX_COORDINATE, MAX_COORDINATE));
        let valid = match *self {
            Self::Twist {
                center,
                radius,
                angle,
            } => {
                point(center) && range(radius, 0.0001, 32768.0) && range(angle, -360000.0, 360000.0)
            }
            Self::Relief {
                angle,
                distance,
                strength,
            } => {
                range(angle, -360000.0, 360000.0)
                    && range(distance, 0.0, 32.0)
                    && range(strength, 0.0, 8.0)
            }
            Self::HighPass { sigma } => range(sigma, 0.0, 16.0),
            Self::Extrema { radius, .. } | Self::StrokeRank { radius, .. } => radius <= 8,
            Self::ToneFold { threshold } => range(threshold, 0.0, 1.0),
            Self::EdgeInk { strength } => range(strength, 0.0, 8.0),
            Self::ValueField {
                cell_size,
                octaves,
                origin,
                ..
            } => range(cell_size, 1.0, 4096.0) && (1..=4).contains(&octaves) && point(origin),
            Self::FieldRepair { keep_parity } => keep_parity <= 1,
        };
        let valid = valid
            && match *self {
                Self::StrokeRank {
                    angle, quantile, ..
                } => range(angle, -360000.0, 360000.0) && range(quantile, 0.0, 1.0),
                _ => true,
            };
        if valid {
            Ok(())
        } else {
            Err(invalid(
                "Creative controls exceed declared coordinate, radius, angle, strength, octave or parity limits",
            ))
        }
    }
    pub fn work(&self, scale: u32) -> u64 {
        match *self {
            Self::Twist { .. } => 48,
            Self::Relief { .. } => 32,
            Self::HighPass { sigma } => filters::Operator::Gaussian { sigma }.work(scale) + 8,
            Self::Extrema { radius, .. } => 8 * (2 * radius as u64 * scale as u64 + 1).pow(2),
            Self::ToneFold { .. } => 4,
            Self::EdgeInk { .. } => 96,
            Self::StrokeRank { radius, .. } => 32 * (2 * radius as u64 * scale as u64 + 1),
            Self::ValueField { octaves, .. } => 256 * octaves as u64,
            Self::FieldRepair { .. } => 8,
        }
    }
    pub(crate) fn rebase(&mut self, delta: Point) {
        let p = match self {
            Self::Twist { center, .. } => center,
            Self::ValueField { origin, .. } => origin,
            _ => return,
        };
        p[0] += delta[0];
        p[1] += delta[1];
    }
}
fn color(p: [f64; 4], fallback: [f64; 4]) -> [f64; 4] {
    if p[3] == 0.0 {
        fallback
    } else {
        filters::straight(p)
    }
}
fn lattice(seed: u32, x: i64, y: i64, octave: u32) -> f64 {
    let mut h = Sha256::new();
    h.update(b"Inkbolt value field v1\0");
    h.update(seed.to_le_bytes());
    h.update(x.to_le_bytes());
    h.update(y.to_le_bytes());
    h.update(octave.to_le_bytes());
    let bytes = h.finalize();
    let n = u64::from_le_bytes(bytes[..8].try_into().unwrap()) >> 12;
    (n as f64 + 0.5) / 4503599627370496.0
}
pub(crate) fn field(seed: u32, p: Point, octaves: u32) -> f64 {
    let mut sum = 0.0;
    let mut total = 0.0;
    for o in 0..octaves {
        let freq = (1u32 << o) as f64;
        let q = p.map(|v| v * freq);
        let cell = q.map(|v| v.floor() as i64);
        let u: Point = std::array::from_fn(|i| {
            let t = q[i] - q[i].floor();
            t * t * (3.0 - 2.0 * t)
        });
        let a = lattice(seed, cell[0], cell[1], o);
        let b = lattice(seed, cell[0] + 1, cell[1], o);
        let c = lattice(seed, cell[0], cell[1] + 1, o);
        let d = lattice(seed, cell[0] + 1, cell[1] + 1, o);
        sum += ((a * (1.0 - u[0]) + b * u[0]) * (1.0 - u[1])
            + (c * (1.0 - u[0]) + d * u[0]) * u[1])
            / freq;
        total += 1.0 / freq;
    }
    sum / total
}
pub(crate) fn evaluate(
    pixels: &[f64],
    size: [u32; 3],
    world: Matrix,
    op: &Operator,
    border: Border,
) -> Vec<f64> {
    let [w, h, scale] = size;
    let s = scale as f64;
    let inverse = geometry::inverse(world).expect("validated creative world");
    let blurred = if let Operator::HighPass { sigma } = *op {
        Some(filters::evaluate(
            pixels,
            size,
            world,
            &filters::Operator::Gaussian { sigma },
            border,
        ))
    } else {
        None
    };
    let mut out = vec![0.0; pixels.len()];
    for y in 0..h {
        for x in 0..w {
            let i = (y as usize * w as usize + x as usize) * 4;
            let p = filters::at(pixels, [w, h], x as i64, y as i64, border);
            let center = filters::straight(p);
            let fetch = |dx: i64, dy: i64| {
                color(
                    filters::at(pixels, [w, h], x as i64 + dx, y as i64 + dy, border),
                    center,
                )
            };
            let sample = |dx: f64, dy: f64| {
                color(
                    filters::sample(pixels, [w, h], [x as f64 + dx, y as f64 + dy], border),
                    center,
                )
            };
            let mut rgb = [0.0; 3];
            match *op {
                Operator::Twist { .. } | Operator::FieldRepair { .. } => {
                    unreachable!("Positive creative filters use shared transport")
                }
                _ if p[3] == 0.0 => continue,
                Operator::Relief {
                    angle,
                    distance,
                    strength,
                } => {
                    let (sn, cs) = angle.to_radians().sin_cos();
                    let dx = cs * distance * s;
                    let dy = sn * distance * s;
                    let a = sample(-dx, -dy);
                    let b = sample(dx, dy);
                    for c in 0..3 {
                        rgb[c] = 0.5 + strength * (b[c] - a[c]) * 0.5;
                    }
                }
                Operator::HighPass { .. } => {
                    let buf = blurred.as_ref().unwrap();
                    let q = color(buf[i..i + 4].try_into().unwrap(), center);
                    for c in 0..3 {
                        rgb[c] = 0.5 + center[c] - q[c];
                    }
                }
                Operator::Extrema { radius, mode } => {
                    rgb.copy_from_slice(&center[..3]);
                    let r = (radius * scale) as i64;
                    for dy in -r..=r {
                        for dx in -r..=r {
                            let q = fetch(dx, dy);
                            for c in 0..3 {
                                rgb[c] = match mode {
                                    Extreme::Minimum => rgb[c].min(q[c]),
                                    Extreme::Maximum => rgb[c].max(q[c]),
                                };
                            }
                        }
                    }
                }
                Operator::ToneFold { threshold } => {
                    for c in 0..3 {
                        rgb[c] = if center[c] > threshold {
                            1.0 - center[c]
                        } else {
                            center[c]
                        };
                    }
                }
                Operator::EdgeInk { strength } => {
                    let mut gx = 0.0;
                    let mut gy = 0.0;
                    for dy in -1i64..=1 {
                        for dx in -1i64..=1 {
                            let q = fetch(dx * scale as i64, dy * scale as i64);
                            let v = (q[0] + q[1] + q[2]) / 3.0;
                            gx += v * dx as f64 * if dy == 0 { 2.0 } else { 1.0 };
                            gy += v * dy as f64 * if dx == 0 { 2.0 } else { 1.0 };
                        }
                    }
                    rgb.fill(1.0 - strength * gx.hypot(gy) / 4.0);
                }
                Operator::StrokeRank {
                    radius,
                    angle,
                    quantile,
                } => {
                    let (sn, cs) = angle.to_radians().sin_cos();
                    let r = (radius * scale) as i64;
                    let mut channels: [Vec<f64>; 3] =
                        std::array::from_fn(|_| Vec::with_capacity((2 * r + 1) as usize));
                    for d in -r..=r {
                        let q = filters::sample(
                            pixels,
                            [w, h],
                            [x as f64 + cs * d as f64, y as f64 + sn * d as f64],
                            border,
                        );
                        if q[3] > 0.0 {
                            let q = filters::straight(q);
                            for c in 0..3 {
                                channels[c].push(q[c]);
                            }
                        }
                    }
                    for c in 0..3 {
                        channels[c].sort_unstable_by(f64::total_cmp);
                        rgb[c] = channels[c]
                            [(quantile * (channels[c].len() - 1) as f64).floor() as usize];
                    }
                }
                Operator::ValueField {
                    seed,
                    cell_size,
                    octaves,
                    origin,
                    low,
                    high,
                } => {
                    let q = geometry::map(inverse, [(x as f64 + 0.5) / s, (y as f64 + 0.5) / s]);
                    let t = field(
                        seed,
                        [
                            (q[0] - origin[0]) / cell_size,
                            (q[1] - origin[1]) / cell_size,
                        ],
                        octaves,
                    );
                    for c in 0..3 {
                        rgb[c] = (low[c] as f64 * (1.0 - t) + high[c] as f64 * t) / 255.0;
                    }
                }
            }
            for c in 0..3 {
                out[i + c] = rgb[c].clamp(0.0, 1.0) * p[3];
            }
            out[i + 3] = p[3];
        }
    }
    out
}
