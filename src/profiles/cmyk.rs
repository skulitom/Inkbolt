//! Explicit profile-driven four-channel delivery from a flattened display surface.
use super::*;
use crate::control::Control;

/// Four-dimensional output-device tables need a separate bounded allowance.
pub const MAX_PROFILE_BYTES: usize = 4 * 1024 * 1024;

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Source {
    Builtin {
        name: Builtin,
    },
    Icc {
        data: String,
    },
    File {
        source_path: std::path::PathBuf,
        sha256: String,
    },
}
impl From<super::Profile> for Source {
    fn from(profile: super::Profile) -> Self {
        match profile {
            super::Profile::Builtin { name } => Self::Builtin { name },
            super::Profile::Icc { data } => Self::Icc { data },
        }
    }
}
pub(crate) fn read_source(source: &Source) -> Result<Vec<u8>, Error> {
    use std::io::Read;
    match source {
        Source::Builtin { .. } => Err(Error::new(
            "UNSUPPORTED",
            "CMYK delivery needs an explicit output ICC profile; RGB builtins are not printing conditions",
        )),
        Source::Icc { data } => {
            if data.len() > MAX_PROFILE_BYTES.div_ceil(3) * 4 {
                return Err(limit("Encoded CMYK ICC profile exceeds byte limit"));
            }
            STANDARD.decode(data).map_err(|_| invalid())
        }
        Source::File {
            source_path,
            sha256,
        } => {
            if !source_path.is_absolute()
                || sha256.len() != 64
                || !sha256
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
            {
                return Err(Error::new(
                    "INVALID_REQUEST",
                    "A file profile requires an absolute source_path and lowercase SHA-256",
                ));
            }
            let file = std::fs::File::open(source_path).map_err(|_| {
                Error::new("PROFILE_IO", "Unable to open the declared CMYK profile")
            })?;
            let metadata = file.metadata().map_err(|_| {
                Error::new("PROFILE_IO", "Unable to inspect the declared CMYK profile")
            })?;
            if !metadata.is_file() {
                return Err(Error::new(
                    "PROFILE_IO",
                    "The CMYK profile must be a regular file",
                ));
            }
            if metadata.len() > MAX_PROFILE_BYTES as u64 {
                return Err(limit("CMYK ICC profile exceeds 4 MiB"));
            }
            let mut bytes = Vec::new();
            file.take(MAX_PROFILE_BYTES as u64 + 1)
                .read_to_end(&mut bytes)
                .map_err(|_| {
                    Error::new("PROFILE_IO", "Unable to read the declared CMYK profile")
                })?;
            if bytes.len() > MAX_PROFILE_BYTES {
                return Err(limit("CMYK ICC profile exceeds 4 MiB"));
            }
            if assets::sha256(&bytes) != *sha256 {
                return Err(Error::new(
                    "PROFILE_MISMATCH",
                    "The CMYK profile bytes do not match the declared SHA-256",
                ));
            }
            Ok(bytes)
        }
    }
}

pub struct Converter {
    pub bytes: Vec<u8>,
    pub intent: Intent,
    transform: DeliveryTransform,
}
enum DeliveryTransform {
    Colorimetric(std::sync::Arc<moxcms::TransformF64Executor>),
    Managed(Box<super::device::Connection>),
}

mod native;
pub(super) mod table;
pub(crate) use native::{PaintConverter, SourceConverter};
impl Converter {
    pub fn new(profile: &Source, intent: Intent) -> Result<Self, Error> {
        Self::with_precision(profile, intent, false)
    }
    fn with_precision(
        profile: &Source,
        intent: Intent,
        high_precision: bool,
    ) -> Result<Self, Error> {
        let bytes = read_source(profile)?;
        let destination = parse_space(&bytes, true)?;
        // ICCBased images use AToB for later interpretation. BToA supplies the
        // current separation. Never embed a one-way profile as a calibrated image.
        if destination.lut_a_to_b_perceptual.is_none()
            || destination.lut_b_to_a_perceptual.is_none()
        {
            return Err(Error::new(
                "UNSUPPORTED",
                "CMYK image delivery requires both A2B0 and B2A0 profile tables",
            ));
        }
        if matches!(intent, Intent::Perceptual | Intent::Saturation) {
            let transform = super::device::Connection::new(
                &crate::swatches::device::display(),
                &super::device::Endpoint {
                    space: super::device::Space::Cmyk,
                    profile: Some(Profile::Icc {
                        data: STANDARD.encode(&bytes),
                    }),
                    untagged: super::device::Untagged::Reject,
                },
                intent,
            )?;
            return Ok(Self {
                bytes,
                intent,
                transform: DeliveryTransform::Managed(Box::new(transform)),
            });
        }
        let mut source = working()?;
        if intent == Intent::AbsoluteColorimetric {
            let scale = absolute_scale(&source, &destination)?;
            for column in [
                &mut source.red_colorant,
                &mut source.green_colorant,
                &mut source.blue_colorant,
            ] {
                column.x *= scale[0];
                column.y *= scale[1];
                column.z *= scale[2];
            }
        }
        let transform =
            transform_with_precision(&source, &destination, intent, false, high_precision)?;
        Ok(Self {
            bytes,
            intent,
            transform: DeliveryTransform::Colorimetric(transform),
        })
    }
    /// Composite the explicit encoded-sRGB matte before conversion. Each CMYK
    /// component is an ink fraction, independently quantized; K is never alpha.
    pub fn convert(
        &self,
        rgba: &[u8],
        matte: [u8; 3],
        control: Option<&Control>,
    ) -> Result<Vec<u8>, Error> {
        if !rgba.len().is_multiple_of(4) {
            return Err(Error::new(
                "INVALID_REQUEST",
                "CMYK conversion requires complete RGBA pixels",
            ));
        }
        if rgba.len() as u64 / 4 > crate::pdf::MAX_IMAGE_PIXELS {
            return Err(limit("CMYK conversion exceeds the page image pixel budget"));
        }
        let mut result = Vec::with_capacity(rgba.len());
        for row in rgba.chunks(4096 * 4) {
            if let Some(c) = control {
                c.check()?;
            }
            let input: Vec<f64> = row
                .as_chunks::<4>()
                .0
                .iter()
                .flat_map(|p| {
                    (0..3).map(move |c| {
                        // Retain the exact byte/alpha product until the color engine.
                        (p[c] as f64 * p[3] as f64 + matte[c] as f64 * (255 - p[3]) as f64)
                            / 65025.0
                    })
                })
                .collect();
            let mut output = vec![0.0; row.len()];
            match &self.transform {
                DeliveryTransform::Managed(transform) => {
                    for (source, destination) in input
                        .as_chunks::<3>()
                        .0
                        .iter()
                        .zip(output.as_chunks_mut::<4>().0)
                    {
                        destination.copy_from_slice(&transform.sample(source)?.values);
                    }
                }
                DeliveryTransform::Colorimetric(transform) => {
                    transform.transform(&input, &mut output).map_err(|_| {
                        Error::new(
                            "COLOR_CONVERSION",
                            "Unable to convert flattened pixels to CMYK",
                        )
                    })?
                }
            }
            if output
                .iter()
                .any(|v| !v.is_finite() || !(0.0..=1.0).contains(v))
            {
                return Err(Error::new(
                    "COLOR_CONVERSION",
                    "CMYK profile produced invalid normalized ink samples",
                ));
            }
            result.extend(output.iter().map(|v| (v * 255.0).round() as u8));
        }
        if let Some(c) = control {
            c.check()?;
        }
        Ok(result)
    }
    pub fn receipt(&self) -> Value {
        json!({"icc_sha256":assets::sha256(&self.bytes),"icc_bytes":self.bytes.len(),"samples":"cmyk8","working_space":"srgb","intent":self.intent,"black_point_compensation":false,"endpoint_fixups":false,"profile_embedded":true,"alpha":"explicit_matte_before_conversion","quantization":"nearest_byte_after_profile_conversion","connection":match self.transform {DeliveryTransform::Managed(_) => "explicit_directional_tables;v4_reference_medium_bridge;legacy_v2_direct_PCS;continuous_tensor",DeliveryTransform::Colorimetric(_) => "colourimetric_profile_tables;explicit_absolute_media_white_scaling;pinned_float_engine"}})
    }
}
