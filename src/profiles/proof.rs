//! Colorimetric observation of the actual four-channel delivery samples.
use super::*;
use crate::control::Control;

const WHITE: [f64; 3] = [0.9642, 1.0, 0.8249];
type Transform = std::sync::Arc<moxcms::TransformF64Executor>;

pub struct Observer {
    source_xyz: Transform,
    ink_xyz: Transform,
    xyz_linear: Transform,
    white_scale: [f64; 3],
    lab_scale: Option<f64>,
    pub display_profile: Vec<u8>,
}
pub struct Sample {
    pub source_xyz: [f64; 3],
    pub proof_xyz: [f64; 3],
    pub source_lab: [f64; 3],
    pub proof_lab: [f64; 3],
    pub linear_rgb: [f64; 3],
    pub display_rgb: [u8; 3],
    pub delta_e76: f64,
}

pub(super) fn lab(xyz: [f64; 3]) -> [f64; 3] {
    let f: [f64; 3] = std::array::from_fn(|i| {
        let t = xyz[i] / WHITE[i];
        if t > (6.0_f64 / 29.0).powi(3) {
            t.cbrt()
        } else {
            t / (3.0 * (6.0_f64 / 29.0).powi(2)) + 4.0 / 29.0
        }
    });
    [
        116.0 * f[1] - 16.0,
        500.0 * (f[0] - f[1]),
        200.0 * (f[1] - f[2]),
    ]
}
pub(super) fn from_lab(lab: [f64; 3]) -> [f64; 3] {
    let y = (lab[0] + 16.0) / 116.0;
    let f = [y + lab[1] / 500.0, y, y - lab[2] / 200.0];
    std::array::from_fn(|i| {
        WHITE[i]
            * if f[i] > 6.0 / 29.0 {
                f[i].powi(3)
            } else {
                3.0 * (6.0_f64 / 29.0).powi(2) * (f[i] - 4.0 / 29.0)
            }
    })
}
fn apply(transform: &Transform, input: &[f64], output: &mut [f64]) -> Result<(), Error> {
    transform.transform(input, output).map_err(|_| {
        Error::new(
            "COLOR_CONVERSION",
            "Unable to evaluate the colorimetric proof",
        )
    })?;
    if output.iter().any(|v| !v.is_finite()) {
        return Err(Error::new(
            "COLOR_CONVERSION",
            "Proof produced nonfinite samples",
        ));
    }
    Ok(())
}
impl Observer {
    pub fn new(profile_bytes: &[u8], intent: Intent) -> Result<Self, Error> {
        if !matches!(
            intent,
            Intent::RelativeColorimetric | Intent::AbsoluteColorimetric
        ) {
            return Err(Error::new(
                "UNSUPPORTED_PROFILE_INTENT",
                "Proof viewing requires a colorimetric intent",
            ));
        }
        let mut ink = parse_space(profile_bytes, true)?;
        let selected = ink
            .lut_a_to_b_colorimetric
            .as_ref()
            .or(ink.lut_a_to_b_perceptual.as_ref())
            .ok_or_else(invalid)?;
        let legacy = matches!(selected, moxcms::LutWarehouse::Lut(lut) if lut.lut_type == moxcms::LutType::Lut16);
        let eight_bit = matches!(selected, moxcms::LutWarehouse::Lut(lut) if lut.lut_type == moxcms::LutType::Lut8);
        if ink.pcs == DataColorSpace::Xyz && eight_bit {
            return Err(Error::new(
                "UNSUPPORTED",
                "Proof rejects ambiguous eight-bit XYZ connection tables",
            ));
        }
        // Request numerical table outputs through a private linear XYZ bridge.
        // For Lab tables, interpret those normalized codes ourselves afterwards:
        // ICC.1 section 10.10 chooses legacy Lab encoding by tag type, not profile
        // version. This also avoids resampling a nonlinear Lab-to-XYZ conversion
        // into the backend's intermediate four-dimensional delivery table.
        // This private parsed clone is never serialized or returned as a profile.
        let lab_scale = if ink.pcs == DataColorSpace::Lab {
            ink.pcs = DataColorSpace::Xyz;
            Some(if legacy { 65535.0 / 65280.0 } else { 1.0 })
        } else {
            None
        };
        let (display_profile, display) = resolve(&Profile::Builtin {
            name: Builtin::Srgb,
        })?;
        let (_, linear) = resolve(&Profile::Builtin {
            name: Builtin::LinearSrgb,
        })?;
        let bridge = xyz_bridge();
        let white_scale = if intent == Intent::AbsoluteColorimetric {
            absolute_scale(&ink, &display)?
        } else {
            [1.0; 3]
        };
        Ok(Self {
            source_xyz: transform_with_intent(
                &display,
                &bridge,
                Intent::RelativeColorimetric,
                false,
            )?,
            ink_xyz: transform_with_intent(&ink, &bridge, Intent::RelativeColorimetric, true)?,
            xyz_linear: transform_with_intent(
                &bridge,
                &linear,
                Intent::RelativeColorimetric,
                true,
            )?,
            white_scale,
            lab_scale,
            display_profile,
        })
    }
    fn ink_linear(&self, ink: &[f64]) -> Result<(Vec<f64>, Vec<f64>), Error> {
        let mut proof_xyz = vec![0.0; ink.len() / 4 * 3];
        apply(&self.ink_xyz, ink, &mut proof_xyz)?;
        for p in proof_xyz.as_chunks_mut::<3>().0 {
            if let Some(scale) = self.lab_scale {
                // The backend's XYZ/2 bridge includes the u1.15 normalization.
                // Remove it before applying the original Lab tag encoding.
                let q = p.map(|v| (v * (65536.0 / 65535.0) * scale).clamp(0.0, 1.0));
                *p = from_lab([q[0] * 100.0, q[1] * 255.0 - 128.0, q[2] * 255.0 - 128.0])
                    .map(|v| v * 0.5);
            }
            for (i, v) in p.iter_mut().enumerate() {
                *v *= self.white_scale[i];
            }
        }
        let mut linear = vec![0.0; ink.len() / 4 * 3];
        apply(&self.xyz_linear, &proof_xyz, &mut linear)?;
        Ok((proof_xyz, linear))
    }
    /// Continuous encoded RGB observation for an explicitly selected print adjustment policy.
    pub(crate) fn process_rgb(&self, ink: &[f64]) -> Result<Vec<f64>, Error> {
        if !ink.len().is_multiple_of(4)
            || ink.len() > 4096 * 4
            || ink
                .iter()
                .any(|v| !v.is_finite() || !(0.0..=1.0).contains(v))
        {
            return Err(Error::new(
                "INVALID_REQUEST",
                "Process observation requires a bounded normalized CMYK batch",
            ));
        }
        let (_, linear) = self.ink_linear(ink)?;
        Ok(linear
            .into_iter()
            .map(|v| crate::hdr::encode(v.clamp(0.0, 1.0)))
            .collect())
    }
    /// Inputs are the exact matte products and separated CMYK8 values. Chunking
    /// bounds temporary storage and exposes cancellation between color batches.
    pub fn observe(
        &self,
        rgba: &[u8],
        inks: &[u8],
        matte: [u8; 3],
        control: &Control,
        visit: impl FnMut(usize, Sample),
    ) -> Result<(), Error> {
        self.observe_values(rgba, inks, matte, control, |v| v as f64 / 255.0, visit)
    }
    pub fn observe_continuous(
        &self,
        rgba: &[u8],
        inks: &[f64],
        matte: [u8; 3],
        control: &Control,
        visit: impl FnMut(usize, Sample),
    ) -> Result<(), Error> {
        self.observe_values(rgba, inks, matte, control, |v| v, visit)
    }
    fn observe_values<T: Copy>(
        &self,
        rgba: &[u8],
        inks: &[T],
        matte: [u8; 3],
        control: &Control,
        normalize: impl Fn(T) -> f64,
        mut visit: impl FnMut(usize, Sample),
    ) -> Result<(), Error> {
        if rgba.len() != inks.len() || !rgba.len().is_multiple_of(4) {
            return Err(Error::new(
                "INVALID_REQUEST",
                "Proof inputs require equal complete four-channel rows",
            ));
        }
        if rgba.len() as u64 / 4 > crate::render::MAX_RENDER_PIXELS {
            return Err(limit("Proof exceeds the render pixel budget"));
        }
        for (chunk, (source, ink)) in rgba.chunks(4096 * 4).zip(inks.chunks(4096 * 4)).enumerate() {
            control.check()?;
            let rgb: Vec<f64> = source
                .as_chunks::<4>()
                .0
                .iter()
                .flat_map(|p| {
                    (0..3).map(move |c| {
                        (p[c] as f64 * p[3] as f64 + matte[c] as f64 * (255 - p[3]) as f64)
                            / 65025.0
                    })
                })
                .collect();
            let ink: Vec<f64> = ink.iter().map(|&v| normalize(v)).collect();
            if ink
                .iter()
                .any(|v| !v.is_finite() || !(0.0..=1.0).contains(v))
            {
                return Err(Error::new(
                    "INVALID_REQUEST",
                    "Proof ink fractions must be finite and normalized",
                ));
            }
            let mut source_xyz = vec![0.0; rgb.len()];
            apply(&self.source_xyz, &rgb, &mut source_xyz)?;
            let (proof_xyz, linear) = self.ink_linear(&ink)?;
            for (i, ((a, b), l)) in source_xyz
                .as_chunks::<3>()
                .0
                .iter()
                .zip(proof_xyz.as_chunks::<3>().0)
                .zip(linear.as_chunks::<3>().0)
                .enumerate()
            {
                // The private matrix bridge stores XYZ/2; Lab sees true XYZ.
                let source_xyz = a.map(|v| v * 2.0);
                let proof_xyz = b.map(|v| v * 2.0);
                let source_lab = lab(source_xyz);
                let proof_lab = lab(proof_xyz);
                let delta_e76 = (0..3)
                    .map(|c| (source_lab[c] - proof_lab[c]).powi(2))
                    .sum::<f64>()
                    .sqrt();
                if !delta_e76.is_finite() {
                    return Err(Error::new(
                        "COLOR_CONVERSION",
                        "Proof difference is not finite",
                    ));
                }
                let display_rgb = l.map(|v| {
                    let v = v.clamp(0.0, 1.0);
                    let encoded = if v <= 0.0031308 {
                        12.92 * v
                    } else {
                        1.055 * v.powf(1.0 / 2.4) - 0.055
                    };
                    (encoded * 255.0).round() as u8
                });
                visit(
                    chunk * 4096 + i,
                    Sample {
                        source_xyz,
                        proof_xyz,
                        source_lab,
                        proof_lab,
                        linear_rgb: *l,
                        display_rgb,
                        delta_e76,
                    },
                );
            }
        }
        control.check()
    }
}
