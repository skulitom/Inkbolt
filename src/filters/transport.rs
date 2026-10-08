//! Positive spatial transport shared by display samples and native ink fields.
use super::{Border, Operator, index};
use crate::{Error, control::Control, geometry, model::*};

pub(crate) fn supports(operator: &Operator) -> bool {
    matches!(
        operator,
        Operator::Box { .. }
            | Operator::Gaussian { .. }
            | Operator::Directional { .. }
            | Operator::Radial { .. }
            | Operator::Spatial { .. }
    ) || matches!(operator, Operator::Creative { operator } if matches!(**operator, crate::creative_filters::Operator::Twist { .. } | crate::creative_filters::Operator::FieldRepair { .. }))
}

fn check(control: Option<&Control>) -> Result<(), Error> {
    control.map_or(Ok(()), Control::check)
}

fn add_at(
    source: &[f64],
    size: [u32; 2],
    point: [i64; 2],
    border: Border,
    weight: f64,
    target: &mut [f64],
) {
    if let (Some(x), Some(y)) = (
        index(point[0], size[0], border),
        index(point[1], size[1], border),
    ) {
        let offset = (y * size[0] as usize + x) * target.len();
        for (dst, src) in target.iter_mut().zip(&source[offset..]) {
            *dst += weight * src;
        }
    }
}

fn add_sample(source: &[f64], size: [u32; 2], point: Point, border: Border, target: &mut [f64]) {
    let [x, y] = point;
    let fx = x - x.floor();
    let fy = y - y.floor();
    for (dx, wx) in [(0, 1.0 - fx), (1, fx)] {
        for (dy, wy) in [(0, 1.0 - fy), (1, fy)] {
            if let (Some(ix), Some(iy)) = (
                index(x.floor() as i64 + dx, size[0], border),
                index(y.floor() as i64 + dy, size[1], border),
            ) {
                let offset = (iy * size[0] as usize + ix) * target.len();
                for (dst, src) in target.iter_mut().zip(&source[offset..]) {
                    *dst += src * wx * wy;
                }
            }
        }
    }
}

pub(crate) fn evaluate(
    source: &[f64],
    size: [u32; 3],
    world: Matrix,
    operator: &Operator,
    border: Border,
    control: Option<&Control>,
) -> Result<Vec<f64>, Error> {
    check(control)?;
    let [w, h, scale] = size;
    let channels = source.len() / (w as usize * h as usize);
    let s = scale as f64;
    let kernel = match *operator {
        Operator::Box { radius } => {
            let n = 2 * radius * scale + 1;
            Some(vec![1.0 / n as f64; n as usize])
        }
        Operator::Gaussian { sigma } => {
            if sigma == 0.0 {
                return Ok(source.to_vec());
            }
            let sigma = sigma * s;
            let radius = (3.0 * sigma).ceil() as i32;
            // Divide first so a tiny positive sigma retains its center weight.
            let mut weights: Vec<f64> = (-radius..=radius)
                .map(|d| (-0.5 * (d as f64 / sigma).powi(2)).exp())
                .collect();
            let total: f64 = weights.iter().sum();
            for weight in &mut weights {
                *weight /= total;
            }
            Some(weights)
        }
        _ => None,
    };
    if let Some(kernel) = kernel {
        let radius = (kernel.len() / 2) as i64;
        let mut temporary = vec![0.0; source.len()];
        let mut result = vec![0.0; source.len()];
        for horizontal in [true, false] {
            let (src, dst) = if horizontal {
                (source, &mut temporary)
            } else {
                (temporary.as_slice(), &mut result)
            };
            for y in 0..h {
                check(control)?;
                for x in 0..w {
                    let offset = (y as usize * w as usize + x as usize) * channels;
                    for (j, weight) in kernel.iter().enumerate() {
                        let delta = j as i64 - radius;
                        add_at(
                            src,
                            [w, h],
                            [
                                x as i64 + if horizontal { delta } else { 0 },
                                y as i64 + if horizontal { 0 } else { delta },
                            ],
                            border,
                            *weight,
                            &mut dst[offset..offset + channels],
                        );
                    }
                }
            }
        }
        return Ok(result);
    }
    if let Operator::Creative { operator } = operator {
        use crate::creative_filters::Operator as Creative;
        let inverse = geometry::inverse(world)?;
        let mut result = vec![0.0; source.len()];
        for y in 0..h {
            check(control)?;
            for x in 0..w {
                let offset = (y as usize * w as usize + x as usize) * channels;
                let dst = &mut result[offset..offset + channels];
                match **operator {
                    Creative::FieldRepair { keep_parity } => {
                        if y % 2 == keep_parity || h == 1 {
                            dst.copy_from_slice(&source[offset..offset + channels]);
                            continue;
                        }
                        let first = keep_parity;
                        let last = h - 1 - ((h - 1 - keep_parity) % 2);
                        let before = (y as i64 - 1).clamp(first as i64, last as i64) as usize;
                        let after = (y as i64 + 1).clamp(first as i64, last as i64) as usize;
                        for c in 0..channels {
                            dst[c] = (source[(before * w as usize + x as usize) * channels + c]
                                + source[(after * w as usize + x as usize) * channels + c])
                                * 0.5;
                        }
                    }
                    Creative::Twist {
                        center,
                        radius,
                        angle,
                    } => {
                        let q =
                            geometry::map(inverse, [(x as f64 + 0.5) / s, (y as f64 + 0.5) / s]);
                        let dx = q[0] - center[0];
                        let dy = q[1] - center[1];
                        let r = dx.hypot(dy) / radius;
                        if angle == 0.0 || r >= 1.0 {
                            dst.copy_from_slice(&source[offset..offset + channels]);
                            continue;
                        }
                        let (sn, cs) = (angle.to_radians() * (1.0 - r).powi(2)).sin_cos();
                        let point = geometry::map(
                            world,
                            [center[0] + cs * dx - sn * dy, center[1] + sn * dx + cs * dy],
                        )
                        .map(|v| v * s - 0.5);
                        add_sample(source, [w, h], point, border, dst);
                    }
                    _ => {
                        return Err(Error::new(
                            "UNSUPPORTED",
                            "This creative filter is not positive spatial transport",
                        ));
                    }
                }
            }
        }
        return Ok(result);
    }
    use crate::spatial_filters::Operator as Spatial;
    if let Operator::Spatial { operator } = operator
        && let Spatial::Mosaic { size } = **operator
    {
        if size == 1 {
            return Ok(source.to_vec());
        }
        let n = size * scale;
        let mut result = vec![0.0; source.len()];
        let mut sum = vec![0.0; channels];
        for by in (0..h).step_by(n as usize) {
            for bx in (0..w).step_by(n as usize) {
                sum.fill(0.0);
                let ex = (bx + n).min(w);
                let ey = (by + n).min(h);
                for y in by..ey {
                    check(control)?;
                    for x in bx..ex {
                        let offset = (y as usize * w as usize + x as usize) * channels;
                        for c in 0..channels {
                            sum[c] += source[offset + c];
                        }
                    }
                }
                for v in &mut sum {
                    *v /= ((ex - bx) * (ey - by)) as f64;
                }
                for y in by..ey {
                    check(control)?;
                    for x in bx..ex {
                        let offset = (y as usize * w as usize + x as usize) * channels;
                        result[offset..offset + channels].copy_from_slice(&sum);
                    }
                }
            }
        }
        return Ok(result);
    }
    let center = if let Operator::Radial { center, .. } = operator {
        geometry::map(world, *center).map(|v| v * s - 0.5)
    } else {
        [0.0; 2]
    };
    let inverse = if let Operator::Spatial { operator } = operator
        && let Spatial::Displace { map, .. } = &**operator
    {
        geometry::inverse(geometry::multiply(world, map.transform))?
    } else {
        identity()
    };
    let mut result = vec![0.0; source.len()];
    let mut sample = vec![0.0; channels];
    for y in 0..h {
        check(control)?;
        for x in 0..w {
            let offset = (y as usize * w as usize + x as usize) * channels;
            let dst = &mut result[offset..offset + channels];
            let count = match operator {
                Operator::Directional { samples, .. } | Operator::Radial { samples, .. } => {
                    *samples
                }
                Operator::Spatial { .. } => 1,
                _ => {
                    return Err(Error::new(
                        "UNSUPPORTED",
                        "This filter is not positive spatial transport",
                    ));
                }
            };
            for j in 0..count {
                let t = if count == 1 {
                    0.0
                } else {
                    j as f64 / (count - 1) as f64 - 0.5
                };
                let point = match operator {
                    Operator::Directional { length, angle, .. } => {
                        let (sn, cs) = angle.to_radians().sin_cos();
                        [
                            x as f64 + cs * length * s * t,
                            y as f64 + sn * length * s * t,
                        ]
                    }
                    Operator::Radial { angle, zoom, .. } => {
                        let (sn, cs) = (angle.to_radians() * t).sin_cos();
                        let a = x as f64 - center[0];
                        let b = y as f64 - center[1];
                        [
                            center[0] + (a * cs - b * sn) * (1.0 + zoom * t),
                            center[1] + (a * sn + b * cs) * (1.0 + zoom * t),
                        ]
                    }
                    Operator::Spatial { operator } => match &**operator {
                        Spatial::Offset { offset } => {
                            [x as f64 - offset[0] * s, y as f64 - offset[1] * s]
                        }
                        Spatial::Displace { map, amount } => {
                            let local = geometry::map(
                                inverse,
                                [(x as f64 + 0.5) / s, (y as f64 + 0.5) / s],
                            );
                            let vector = crate::spatial_filters::field(map, local);
                            [
                                x as f64 + vector[0] * amount[0] * s,
                                y as f64 + vector[1] * amount[1] * s,
                            ]
                        }
                        _ => unreachable!(),
                    },
                    _ => unreachable!(),
                };
                sample.fill(0.0);
                add_sample(source, [w, h], point, border, &mut sample);
                for c in 0..channels {
                    dst[c] += sample[c];
                }
            }
            for v in dst {
                *v /= count as f64;
            }
        }
    }
    Ok(result)
}
