//! Original linear-light neighbourhood processing and calibrated lens pull mapping.
use super::{Capture, invalid_raw};
use crate::{Error, control::Control};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Border {
    Clamp,
    Transparent,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Lens {
    pub center: [f64; 2],
    pub focal: [f64; 2],
    pub radial: [f64; 3],
    pub tangential: [f64; 2],
    pub border: Border,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Denoise {
    pub radius: u32,
    pub threshold: f64,
    pub amount: f64,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Detail {
    pub radius: u32,
    pub threshold: f64,
    pub amount: f64,
}
#[derive(Clone, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Corrections {
    pub denoise: Option<Denoise>,
    pub lens: Option<Lens>,
    pub detail: Option<Detail>,
}
impl Corrections {
    pub fn validate(&self, capture: &Capture) -> Result<(), Error> {
        capture.validate()?;
        for (radius, threshold, amount, maximum) in self
            .denoise
            .iter()
            .map(|p| (p.radius, p.threshold, p.amount, 1.0))
            .chain(
                self.detail
                    .iter()
                    .map(|p| (p.radius, p.threshold, p.amount, 4.0)),
            )
        {
            if !(1..=4).contains(&radius)
                || !threshold.is_finite()
                || !(0.0..=16.0).contains(&threshold)
                || !amount.is_finite()
                || !(0.0..=maximum).contains(&amount)
            {
                return Err(invalid_raw(
                    "Noise/detail radius must be 1..4, threshold 0..16 and amount 0..1 for noise or 0..4 for detail",
                ));
            }
        }
        if let Some(lens) = &self.lens {
            lens.bound(capture)?;
        }
        Ok(())
    }
}
impl Lens {
    /// A sufficient global bound on ||J-I|| in normalized coordinates.
    /// A symmetric Jacobian bounded below by .05 I implies a one-to-one map
    /// on the convex output rectangle; no sparse-grid fold heuristic is used.
    pub fn bound(&self, c: &Capture) -> Result<f64, Error> {
        c.validate()?;
        for (i, size) in [c.width, c.height].into_iter().enumerate() {
            if !self.center[i].is_finite()
                || !(0.0..=(size - 1) as f64).contains(&self.center[i])
                || !self.focal[i].is_finite()
                || !(1.0..=32768.0).contains(&self.focal[i])
            {
                return Err(invalid_raw(
                    "Lens center must be inside the sensor pixel-center rectangle and focal lengths in 1..32768 pixels",
                ));
            }
        }
        if self.radial.iter().any(|v| !v.is_finite() || v.abs() > 1.0)
            || self
                .tangential
                .iter()
                .any(|v| !v.is_finite() || v.abs() > 0.25)
        {
            return Err(invalid_raw(
                "Lens radial coefficients must be in -1..1 and tangential coefficients in -.25...25",
            ));
        }
        let r2 = [c.width, c.height]
            .into_iter()
            .enumerate()
            .map(|(i, size)| {
                (self.center[i].max((size - 1) as f64 - self.center[i]) / self.focal[i]).powi(2)
            })
            .sum::<f64>();
        let bound = self
            .radial
            .iter()
            .enumerate()
            .map(|(i, k)| (2 * i + 3) as f64 * k.abs() * r2.powi(i as i32 + 1))
            .sum::<f64>()
            + 8.0 * (self.tangential[0].abs() + self.tangential[1].abs()) * r2.sqrt();
        if !bound.is_finite() || bound >= 0.95 {
            return Err(Error::new(
                "UNSUPPORTED_LENS_MAP",
                "Lens calibration exceeds the global no-fold bound (<0.95); no correction was applied",
            ));
        }
        Ok(bound)
    }
    pub fn source_point(&self, p: [f64; 2]) -> [f64; 2] {
        let x = (p[0] - self.center[0]) / self.focal[0];
        let y = (p[1] - self.center[1]) / self.focal[1];
        let r = x * x + y * y;
        let k = 1.0 + r * (self.radial[0] + r * (self.radial[1] + r * self.radial[2]));
        let [p1, p2] = self.tangential;
        [
            self.center[0] + self.focal[0] * (x * k + 2.0 * p1 * x * y + p2 * (r + 2.0 * x * x)),
            self.center[1] + self.focal[1] * (y * k + p1 * (r + 2.0 * y * y) + 2.0 * p2 * x * y),
        ]
    }
}
pub(super) fn apply(
    pixels: &mut [f64],
    capture: &Capture,
    options: &Corrections,
    control: &Control,
) -> Result<(), Error> {
    let w = capture.width as usize;
    let h = capture.height as usize;
    if let Some(noise) = &options.denoise {
        neighborhood(
            pixels,
            w,
            h,
            noise.radius,
            noise.threshold,
            noise.amount,
            true,
            control,
        )?;
    }
    if let Some(lens) = &options.lens {
        let source = pixels.to_vec();
        for y in 0..h {
            control.check()?;
            for x in 0..w {
                let p = lens.source_point([x as f64, y as f64]);
                let p = if matches!(lens.border, Border::Clamp) {
                    [
                        p[0].clamp(0.0, (w - 1) as f64),
                        p[1].clamp(0.0, (h - 1) as f64),
                    ]
                } else {
                    p
                };
                let ix = p[0].floor() as i64;
                let iy = p[1].floor() as i64;
                let fx = p[0] - ix as f64;
                let fy = p[1] - iy as f64;
                let mut out = [0.0; 4];
                for (yy, wy) in [(iy, 1.0 - fy), (iy + 1, fy)] {
                    for (xx, wx) in [(ix, 1.0 - fx), (ix + 1, fx)] {
                        if xx < 0 || yy < 0 || xx >= w as i64 || yy >= h as i64 {
                            continue;
                        }
                        let at = (yy as usize * w + xx as usize) * 4;
                        let weight = wx * wy;
                        for c in 0..3 {
                            out[c] += source[at + c] * source[at + 3] * weight;
                        }
                        out[3] += source[at + 3] * weight;
                    }
                }
                if out[3] > 0.0 {
                    for c in 0..3 {
                        out[c] /= out[3];
                    }
                }
                pixels[(y * w + x) * 4..(y * w + x) * 4 + 4].copy_from_slice(&out);
            }
        }
    }
    if let Some(detail) = &options.detail {
        neighborhood(
            pixels,
            w,
            h,
            detail.radius,
            detail.threshold,
            detail.amount,
            false,
            control,
        )?;
    }
    Ok(())
}
#[allow(clippy::too_many_arguments)]
fn neighborhood(
    pixels: &mut [f64],
    w: usize,
    h: usize,
    radius: u32,
    threshold: f64,
    amount: f64,
    denoise: bool,
    control: &Control,
) -> Result<(), Error> {
    if amount == 0.0 {
        return Ok(());
    }
    let source = pixels.to_vec();
    let r = radius as usize;
    for y in 0..h {
        control.check()?;
        for x in 0..w {
            let at = (y * w + x) * 4;
            if source[at + 3] == 0.0 {
                continue;
            }
            let mut sum = [0.0; 3];
            let mut weight = 0.0;
            for yy in y.saturating_sub(r)..=(y + r).min(h - 1) {
                for xx in x.saturating_sub(r)..=(x + r).min(w - 1) {
                    let i = (yy * w + xx) * 4;
                    let distance = (0..3)
                        .map(|c| (source[i + c] - source[at + c]).abs())
                        .fold(0.0, f64::max);
                    if denoise && distance > threshold {
                        continue;
                    }
                    weight += source[i + 3];
                    for c in 0..3 {
                        sum[c] += source[i + c] * source[i + 3];
                    }
                }
            }
            for c in 0..3 {
                let delta = sum[c] / weight - source[at + c];
                if denoise {
                    pixels[at + c] = source[at + c] + amount * delta;
                } else if delta.abs() > threshold {
                    pixels[at + c] = source[at + c] - amount * delta;
                }
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::raw::{Packing, Pattern};

    #[test]
    fn direct_library_helpers_reject_invalid_capture_before_lens_arithmetic() {
        let mut capture = Capture {
            width: 2,
            height: 2,
            packing: Packing::U8,
            row_stride: 2,
            pattern: Pattern::Rggb,
            black: [0.0; 4],
            white: [255.0; 4],
            camera_to_linear_srgb: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        };
        let lens = Lens {
            center: [0.0, 0.0],
            focal: [1.0, 1.0],
            radial: [0.0; 3],
            tangential: [0.0; 2],
            border: Border::Clamp,
        };
        assert_eq!(lens.bound(&capture).unwrap(), 0.0);
        for [width, height] in [[0, 0], [0, 2], [2, 0], [1, 2], [2, 1]] {
            capture.width = width;
            capture.height = height;
            assert_eq!(lens.bound(&capture).unwrap_err().code, "INVALID_RAW");
            assert_eq!(
                Corrections::default().validate(&capture).unwrap_err().code,
                "INVALID_RAW"
            );
        }
        capture.width = 2;
        capture.height = 2;
        capture.white[0] = f64::NAN;
        assert_eq!(lens.bound(&capture).unwrap_err().code, "INVALID_RAW");
    }
}
