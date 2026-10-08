//! Original detail operators and coordinate-addressed reproducible image noise.
use crate::{
    Error,
    filters::{self, Border},
    model::*,
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Distribution {
    #[default]
    Uniform,
    Gaussian,
}
fn yes() -> bool {
    true
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Operator {
    Sharpen {
        amount: f64,
    },
    Unsharp {
        sigma: f64,
        amount: f64,
        #[serde(default)]
        threshold: f64,
    },
    Median {
        radius: u32,
    },
    Noise {
        amount: f64,
        seed: u32,
        #[serde(default)]
        distribution: Distribution,
        #[serde(default = "yes")]
        monochrome: bool,
    },
}
fn range(v: f64, hi: f64) -> bool {
    v.is_finite() && (0.0..=hi).contains(&v)
}
impl Operator {
    pub fn validate(&self) -> Result<(), Error> {
        let valid = match *self {
            Self::Sharpen { amount } => range(amount, 8.0),
            Self::Unsharp {
                sigma,
                amount,
                threshold,
            } => range(sigma, 16.0) && range(amount, 8.0) && range(threshold, 1.0),
            Self::Median { radius } => radius <= 8,
            Self::Noise { amount, .. } => range(amount, 1.0),
        };
        if valid {
            Ok(())
        } else {
            Err(invalid(
                "Detail controls exceed amount, sigma, radius or threshold limits",
            ))
        }
    }
    pub fn work(&self, scale: u32) -> u64 {
        match *self {
            Self::Sharpen { .. } => 16,
            Self::Unsharp { sigma, .. } => filters::Operator::Gaussian { sigma }.work(scale) + 8,
            Self::Median { radius } => 8 * (2 * radius as u64 * scale as u64 + 1).pow(2),
            Self::Noise { .. } => 64,
        }
    }
}
fn sharpen(p: [f64; 4], blurred: [f64; 4], amount: f64, threshold: f64) -> [f64; 4] {
    if p[3] == 0.0 {
        return [0.0; 4];
    }
    let color = filters::straight(p);
    let reference = if blurred[3] == 0.0 {
        color
    } else {
        filters::straight(blurred)
    };
    let mut result = p;
    for c in 0..3 {
        let delta = color[c] - reference[c];
        result[c] = if delta.abs() >= threshold {
            (color[c] + amount * delta).clamp(0.0, 1.0) * p[3]
        } else {
            p[c]
        };
    }
    result
}
pub(crate) fn noise(seed: u32, x: u32, y: u32, channel: u8, distribution: Distribution) -> f64 {
    let mut hash = Sha256::new();
    hash.update(b"Inkbolt noise v1\0");
    for v in [seed, x, y] {
        hash.update(v.to_le_bytes());
    }
    hash.update([channel]);
    variate(hash.finalize().into(), distribution)
}
pub(crate) fn variate(bytes: [u8; 32], distribution: Distribution) -> f64 {
    let uniform = |start: usize| {
        let n = u64::from_le_bytes(bytes[start..start + 8].try_into().unwrap()) >> 12;
        // 52 bits plus half a unit is exactly representable and strictly between zero and one.
        (n as f64 + 0.5) / 4503599627370496.0
    };
    let u = uniform(0);
    match distribution {
        Distribution::Uniform => 2.0 * u - 1.0,
        Distribution::Gaussian => {
            (-2.0 * u.ln()).sqrt() * (std::f64::consts::TAU * uniform(8)).cos()
        }
    }
}
pub(crate) fn evaluate(
    pixels: &[f64],
    size: [u32; 3],
    operator: &Operator,
    border: Border,
) -> Vec<f64> {
    let [w, h, scale] = size;
    let mut blurred = if let Operator::Unsharp { sigma, .. } = *operator {
        filters::evaluate(
            pixels,
            size,
            identity(),
            &filters::Operator::Gaussian { sigma },
            border,
        )
    } else {
        Vec::new()
    };
    // Reuse the completed Gaussian result as output: no third full-frame temporary.
    if blurred.is_empty() {
        blurred.resize(pixels.len(), 0.0);
    }
    let mut values: [Vec<f64>; 3] = std::array::from_fn(|_| Vec::new());
    for y in 0..h {
        for x in 0..w {
            let i = (y as usize * w as usize + x as usize) * 4;
            let p: [f64; 4] = pixels[i..i + 4].try_into().unwrap();
            let result = match *operator {
                Operator::Sharpen { amount } => {
                    let mut average = [0.0; 4];
                    let step = scale as i64;
                    for (dx, dy) in [(-step, 0), (step, 0), (0, -step), (0, step)] {
                        let q = filters::at(pixels, [w, h], x as i64 + dx, y as i64 + dy, border);
                        for c in 0..4 {
                            average[c] += q[c] / 4.0;
                        }
                    }
                    sharpen(p, average, amount, 0.0)
                }
                Operator::Unsharp {
                    amount, threshold, ..
                } => sharpen(p, blurred[i..i + 4].try_into().unwrap(), amount, threshold),
                Operator::Median { radius } => {
                    if p[3] == 0.0 {
                        [0.0; 4]
                    } else {
                        for channel in &mut values {
                            channel.clear();
                        }
                        let r = (radius * scale) as i64;
                        for dy in -r..=r {
                            for dx in -r..=r {
                                let q = filters::at(
                                    pixels,
                                    [w, h],
                                    x as i64 + dx,
                                    y as i64 + dy,
                                    border,
                                );
                                if q[3] > 0.0 {
                                    for c in 0..3 {
                                        values[c].push(q[c] / q[3]);
                                    }
                                }
                            }
                        }
                        let mut result = p;
                        for c in 0..3 {
                            let middle = values[c].len() / 2;
                            result[c] =
                                *values[c].select_nth_unstable_by(middle, f64::total_cmp).1 * p[3];
                        }
                        result
                    }
                }
                Operator::Noise {
                    amount,
                    seed,
                    distribution,
                    monochrome,
                } => {
                    if p[3] == 0.0 {
                        [0.0; 4]
                    } else {
                        let shared = noise(seed, x / scale, y / scale, 0, distribution);
                        let mut result = p;
                        for c in 0..3 {
                            let v = if monochrome || c == 0 {
                                shared
                            } else {
                                noise(seed, x / scale, y / scale, c as u8, distribution)
                            };
                            result[c] = (p[c] / p[3] + amount * v).clamp(0.0, 1.0) * p[3];
                        }
                        result
                    }
                }
            };
            blurred[i..i + 4].copy_from_slice(&result);
        }
    }
    blurred
}
