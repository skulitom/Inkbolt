//! Original native color operators preserve each ink's addressed fraction.
use super::super::{Context, Surface};
use crate::{
    Error,
    creative_filters::Operator as Creative,
    detail_filters::Operator as Detail,
    filters::{Border, Operator, transport},
    geometry,
    model::*,
};
use sha2::{Digest, Sha256};

pub(in crate::prepress) fn scratch(operator: &Operator, scale: u32) -> u64 {
    match operator {
        Operator::Detail { operator } => match **operator {
            Detail::Median { radius } => (2 * radius as u64 * scale as u64 + 1).pow(2),
            _ => 0,
        },
        Operator::Creative { operator } => match **operator {
            Creative::StrokeRank { radius, .. } => 2 * radius as u64 * scale as u64 + 1,
            _ => 0,
        },
        _ => 0,
    }
}

fn coordinate(value: i64, size: u32, border: Border) -> Option<usize> {
    crate::filters::index(value, size, border)
}

struct Source<'a> {
    surface: &'a Surface,
    width: u32,
    height: u32,
    border: Border,
}
impl Source<'_> {
    fn index(&self, x: i64, y: i64) -> Option<usize> {
        Some(
            coordinate(y, self.height, self.border)? * self.width as usize
                + coordinate(x, self.width, self.border)?,
        )
    }
    fn at(&self, x: i64, y: i64, channel: usize) -> [f64; 2] {
        self.index(x, y).map_or([0.0; 2], |i| {
            [
                self.surface.values[i * (self.surface.channels + 1) + channel],
                self.surface.removal[i * self.surface.channels + channel],
            ]
        })
    }
    fn sample(&self, x: f64, y: f64, channel: usize) -> [f64; 2] {
        let fx = x - x.floor();
        let fy = y - y.floor();
        let mut result = [0.0; 2];
        for (dx, wx) in [(0, 1.0 - fx), (1, fx)] {
            for (dy, wy) in [(0, 1.0 - fy), (1, fy)] {
                let p = self.at(x.floor() as i64 + dx, y.floor() as i64 + dy, channel);
                for c in 0..2 {
                    result[c] += p[c] * wx * wy;
                }
            }
        }
        result
    }
}
fn density(pair: [f64; 2], fallback: f64) -> f64 {
    if pair[1] == 0.0 {
        fallback
    } else {
        (pair[0] / pair[1]).clamp(0.0, 1.0)
    }
}

impl Context<'_> {
    pub(in crate::prepress) fn nonlinear_filter(
        &self,
        surface: &Surface,
        operator: &Operator,
        border: Border,
        world: Matrix,
    ) -> Result<Surface, Error> {
        if let Operator::Surface { radius, threshold } = *operator {
            return self.surface_filter(surface, radius, threshold, border);
        }
        if let Operator::Creative { operator } = operator
            && let Creative::ValueField { .. } = **operator
        {
            return self.value_filter(surface, operator, world);
        }
        let n = self.channels();
        let scale = self.scale as i64;
        let sigma = match operator {
            Operator::Detail { operator } => match **operator {
                Detail::Unsharp { sigma, .. } => Some(sigma),
                _ => None,
            },
            Operator::Creative { operator } => match **operator {
                Creative::HighPass { sigma } => Some(sigma),
                _ => None,
            },
            _ => None,
        };
        let blurred = if let Some(sigma) = sigma {
            let op = Operator::Gaussian { sigma };
            let size = [self.width, self.height, self.scale];
            Some((
                transport::evaluate(
                    &surface.values,
                    size,
                    world,
                    &op,
                    border,
                    Some(self.control),
                )?,
                transport::evaluate(
                    &surface.removal,
                    size,
                    world,
                    &op,
                    border,
                    Some(self.control),
                )?,
            ))
        } else {
            None
        };
        let source = Source {
            surface,
            width: self.width,
            height: self.height,
            border,
        };
        let mut result = surface.clone();
        let mut ranked = Vec::with_capacity(scratch(operator, self.scale) as usize);
        for y in 0..self.height {
            self.control.check()?;
            for x in 0..self.width {
                let i = (y * self.width + x) as usize;
                for c in 0..n {
                    let weight = surface.removal[i * n + c];
                    if weight == 0.0 {
                        continue;
                    }
                    let d = density([surface.values[i * (n + 1) + c], weight], 0.0);
                    let at = |dx, dy| density(source.at(x as i64 + dx, y as i64 + dy, c), d);
                    let sample =
                        |dx, dy| density(source.sample(x as f64 + dx, y as f64 + dy, c), d);
                    let reference = || {
                        let (v, w) = blurred.as_ref().unwrap();
                        density([v[i * (n + 1) + c], w[i * n + c]], d)
                    };
                    let value = match operator {
                        Operator::Detail { operator } => match **operator {
                            Detail::Sharpen { amount } => {
                                let mut avg = [0.0; 2];
                                for (dx, dy) in [(-scale, 0), (scale, 0), (0, -scale), (0, scale)] {
                                    let q = source.at(x as i64 + dx, y as i64 + dy, c);
                                    for j in 0..2 {
                                        avg[j] += q[j] / 4.0;
                                    }
                                }
                                d + amount * (d - density(avg, d))
                            }
                            Detail::Unsharp {
                                amount, threshold, ..
                            } => {
                                let delta = d - reference();
                                if delta.abs() >= threshold {
                                    d + amount * delta
                                } else {
                                    d
                                }
                            }
                            Detail::Median { radius } => {
                                ranked.clear();
                                let r = radius as i64 * scale;
                                for dy in -r..=r {
                                    self.control.check()?;
                                    for dx in -r..=r {
                                        let q = source.at(x as i64 + dx, y as i64 + dy, c);
                                        if q[1] > 0.0 {
                                            ranked.push(density(q, d));
                                        }
                                    }
                                }
                                // Upper median in complement light is lower median in ink.
                                let k = (ranked.len() - 1) / 2;
                                *ranked.select_nth_unstable_by(k, f64::total_cmp).1
                            }
                            Detail::Noise {
                                amount,
                                seed,
                                distribution,
                                monochrome,
                            } => {
                                let noise = if monochrome || c < 4 {
                                    crate::detail_filters::noise(
                                        seed,
                                        x / self.scale,
                                        y / self.scale,
                                        if monochrome { 0 } else { c as u8 },
                                        distribution,
                                    )
                                } else {
                                    let id = self.noise_ids[c - 4].as_bytes();
                                    let mut hash = Sha256::new();
                                    hash.update(b"Inkbolt ink noise v1\0");
                                    for v in [seed, x / self.scale, y / self.scale, id.len() as u32]
                                    {
                                        hash.update(v.to_le_bytes());
                                    }
                                    hash.update(id);
                                    crate::detail_filters::variate(
                                        hash.finalize().into(),
                                        distribution,
                                    )
                                };
                                d - amount * noise
                            }
                        },
                        Operator::Creative { operator } => match **operator {
                            Creative::Relief {
                                angle,
                                distance,
                                strength,
                            } => {
                                let (sn, cs) = angle.to_radians().sin_cos();
                                let dx = cs * distance * self.scale as f64;
                                let dy = sn * distance * self.scale as f64;
                                0.5 + strength * (sample(dx, dy) - sample(-dx, -dy)) * 0.5
                            }
                            Creative::HighPass { .. } => 0.5 + d - reference(),
                            Creative::Extrema { radius, mode } => {
                                let mut value = d;
                                let r = radius as i64 * scale;
                                for dy in -r..=r {
                                    self.control.check()?;
                                    for dx in -r..=r {
                                        let q = at(dx, dy);
                                        value = match mode {
                                            crate::creative_filters::Extreme::Minimum => {
                                                value.max(q)
                                            }
                                            crate::creative_filters::Extreme::Maximum => {
                                                value.min(q)
                                            }
                                        };
                                    }
                                }
                                value
                            }
                            Creative::ToneFold { threshold } => {
                                if d < 1.0 - threshold {
                                    1.0 - d
                                } else {
                                    d
                                }
                            }
                            Creative::EdgeInk { strength } => {
                                let mut gx = 0.0;
                                let mut gy = 0.0;
                                for dy in -1i64..=1 {
                                    for dx in -1i64..=1 {
                                        let q = at(dx * scale, dy * scale);
                                        gx += q * dx as f64 * if dy == 0 { 2.0 } else { 1.0 };
                                        gy += q * dy as f64 * if dx == 0 { 2.0 } else { 1.0 };
                                    }
                                }
                                strength * gx.hypot(gy) / 4.0
                            }
                            Creative::StrokeRank {
                                radius,
                                angle,
                                quantile,
                            } => {
                                let (sn, cs) = angle.to_radians().sin_cos();
                                let r = radius as i64 * scale;
                                ranked.clear();
                                for k in -r..=r {
                                    let q = source.sample(
                                        x as f64 + cs * k as f64,
                                        y as f64 + sn * k as f64,
                                        c,
                                    );
                                    if q[1] > 0.0 {
                                        ranked.push(density(q, d));
                                    }
                                }
                                let k = (quantile * (ranked.len() - 1) as f64).floor() as usize;
                                *ranked.select_nth_unstable_by(k, |a, b| b.total_cmp(a)).1
                            }
                            _ => unreachable!(
                                "Transport and procedural color have separate evaluators"
                            ),
                        },
                        _ => unreachable!(
                            "Positive transport and range gate have separate evaluators"
                        ),
                    };
                    result.values[i * (n + 1) + c] = weight * value.clamp(0.0, 1.0);
                }
            }
        }
        Ok(result)
    }

    fn surface_filter(
        &self,
        surface: &Surface,
        radius: u32,
        threshold: f64,
        border: Border,
    ) -> Result<Surface, Error> {
        let source = Source {
            surface,
            width: self.width,
            height: self.height,
            border,
        };
        let n = self.channels();
        let r = radius as i64 * self.scale as i64;
        let mut result = Surface::new(
            (self.width * self.height) as usize,
            n,
            false,
            surface.shape.is_some(),
        );
        for y in 0..self.height {
            self.control.check()?;
            for x in 0..self.width {
                let i = (y * self.width + x) as usize;
                let a = surface.values[i * (n + 1) + n];
                let mut count = 0.0;
                let mut shape_count = 0.0;
                for dy in -r..=r {
                    self.control.check()?;
                    for dx in -r..=r {
                        let index = source.index(x as i64 + dx, y as i64 + dy);
                        let b = index.map_or(0.0, |j| surface.values[j * (n + 1) + n]);
                        let mut accepted = (a - b).abs() <= threshold;
                        for c in 0..n {
                            let bc = if b == 0.0 {
                                0.0
                            } else {
                                surface.values[index.unwrap() * (n + 1) + c] / b
                            };
                            let bw = if b == 0.0 {
                                0.0
                            } else {
                                surface.removal[index.unwrap() * n + c] / b
                            };
                            let ac = if a == 0.0 {
                                0.0
                            } else {
                                surface.values[i * (n + 1) + c] / a
                            };
                            let aw = if a == 0.0 {
                                0.0
                            } else {
                                surface.removal[i * n + c] / a
                            };
                            accepted &=
                                (bc - ac).abs() <= threshold && (bw - aw).abs() <= threshold;
                        }
                        if accepted {
                            count += 1.0;
                            if let Some(j) = index {
                                for c in 0..=n {
                                    result.values[i * (n + 1) + c] +=
                                        surface.values[j * (n + 1) + c];
                                }
                                for c in 0..n {
                                    result.removal[i * n + c] += surface.removal[j * n + c];
                                }
                            }
                        }
                        if let (Some(shape), Some(out)) = (&surface.shape, &mut result.shape) {
                            let q = index.map_or(0.0, |j| shape[j]);
                            if (q - shape[i]).abs() <= threshold {
                                out[i] += q;
                                shape_count += 1.0;
                            }
                        }
                    }
                }
                for c in 0..=n {
                    result.values[i * (n + 1) + c] /= count;
                }
                for c in 0..n {
                    result.removal[i * n + c] /= count;
                }
                if let Some(shape) = &mut result.shape {
                    shape[i] /= shape_count;
                }
            }
        }
        Ok(result)
    }

    fn value_filter(
        &self,
        surface: &Surface,
        operator: &Creative,
        world: Matrix,
    ) -> Result<Surface, Error> {
        let Creative::ValueField {
            seed,
            cell_size,
            octaves,
            origin,
            low,
            high,
        } = *operator
        else {
            unreachable!()
        };
        let n = self.channels();
        let inverse = geometry::inverse(world)?;
        let mut result = surface.clone();
        let pixels = (self.width * self.height) as usize;
        for start in (0..pixels).step_by(4096) {
            self.control.check()?;
            let end = (start + 4096).min(pixels);
            let mut rgb = Vec::with_capacity((end - start) * 3);
            for i in start..end {
                let q = geometry::map(inverse, self.point(i));
                let t = crate::creative_filters::field(
                    seed,
                    [
                        (q[0] - origin[0]) / cell_size,
                        (q[1] - origin[1]) / cell_size,
                    ],
                    octaves,
                );
                for c in 0..3 {
                    rgb.push((low[c] as f64 * (1.0 - t) + high[c] as f64 * t) / 255.0);
                }
            }
            let converted = self.converter.rgb(&rgb)?;
            for (j, process) in converted.as_chunks::<4>().0.iter().enumerate() {
                for (c, value) in process.iter().enumerate() {
                    result.values[(start + j) * (n + 1) + c] =
                        surface.removal[(start + j) * n + c] * value;
                }
            }
        }
        Ok(result)
    }
}
