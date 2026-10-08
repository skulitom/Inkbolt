//! Explicit native sample-depth and grayscale conversion on retained source copies.
use crate::{
    Error,
    model::*,
    samples::{Channels, Depth, Grid},
    scene,
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Gray {
    #[default]
    RequireNeutral,
    EncodedLuma,
    LinearLuminance,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Conversion {
    pub encoding: Option<crate::hdr::Encoding>,
    pub view: Option<crate::hdr::View>,
    pub depth: Depth,
    pub channels: Channels,
    pub gray: Option<Gray>,
}
fn decode_srgb(v: f64) -> f64 {
    if v <= 0.04045 {
        v / 12.92
    } else {
        ((v + 0.055) / 1.055).powf(2.4)
    }
}
fn encode_srgb(v: f64) -> f64 {
    if v <= 0.0031308 {
        v * 12.92
    } else {
        1.055 * v.powf(1.0 / 2.4) - 0.055
    }
}
fn neutral(p: &[f64], method: Gray) -> Result<f64, Error> {
    if p[0] == p[1] && p[1] == p[2] {
        return Ok(p[0]);
    }
    if method == Gray::RequireNeutral {
        return Err(Error::new(
            "GRAYSCALE_CONVERSION_REQUIRED",
            "Chromatic source samples require explicit encoded_luma or linear_luminance conversion",
        ));
    }
    let c = if method == Gray::LinearLuminance {
        [decode_srgb(p[0]), decode_srgb(p[1]), decode_srgb(p[2])]
    } else {
        [p[0], p[1], p[2]]
    };
    let v = (2126.0 * c[0] + 7152.0 * c[1] + 722.0 * c[2]) / 10000.0;
    Ok(if method == Gray::LinearLuminance {
        encode_srgb(v)
    } else {
        v
    }
    .clamp(0.0, 1.0))
}
fn integer_gray(p: &[f64; 4], source: Depth, destination: Depth) -> Option<f64> {
    let maximum = |depth| match depth {
        Depth::U8 => Some(255_u64),
        Depth::U16 => Some(65535_u64),
        Depth::F32 => None,
    };
    let src = maximum(source)?;
    let dst = maximum(destination)?;
    let weighted: u64 = p[..3]
        .iter()
        .zip([2126, 7152, 722])
        .map(|(v, weight)| (v * src as f64).round() as u64 * weight)
        .sum();
    let denominator = src * 10000;
    Some(((weighted * dst + denominator / 2) / denominator) as f64 / dst as f64)
}

pub(crate) fn apply(d: &mut Document, id: &str, conversion: &Conversion) -> Result<Value, Error> {
    if conversion.channels != Channels::GrayAlpha && conversion.gray.is_some() {
        return Err(Error::new(
            "INVALID_OPERATION",
            "A grayscale policy only applies to gray_alpha output",
        ));
    }
    let i = scene::index(d, id)?;
    scene::check_unlocked(d, i, false)?;
    let (source, promoted) = match &d.items[i].content {
        Content::Samples { grid } => (grid.as_ref().clone(), false),
        Content::Raster {
            width,
            height,
            rgba_hex,
            sampling,
        } => (
            Grid {
                profile: None,
                encoding: Default::default(),
                width: *width,
                height: *height,
                depth: Depth::U8,
                channels: Channels::Rgba,
                data_hex: rgba_hex.clone(),
                sampling: *sampling,
            },
            true,
        ),
        _ => {
            return Err(Error::new(
                "INVALID_OPERATION",
                "Sample conversion requires retained samples or a legacy inline RGBA8 layer",
            ));
        }
    };
    source.validate()?;
    if source.profile.is_some() || conversion.encoding == Some(crate::hdr::Encoding::ProfiledRgb) {
        return Err(Error::new(
            "PROFILE_CONVERSION_REQUIRED",
            "Use sample_profile to convert profiled samples to explicit working sRGB before depth, grayscale or HDR conversion",
        ));
    }
    let encoding = conversion.encoding.unwrap_or(source.encoding);
    let linear = encoding == crate::hdr::Encoding::LinearSrgb;
    if linear && conversion.depth != Depth::F32 {
        return Err(Error::new(
            "UNSUPPORTED_HDR_MODE",
            "Linear source conversion requires binary32 depth",
        ));
    }
    if linear && conversion.gray == Some(Gray::EncodedLuma) {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Linear grayscale requires neutral or linear_luminance policy",
        ));
    }
    let projecting = source.encoding == crate::hdr::Encoding::LinearSrgb && !linear;
    if projecting && conversion.view.is_none() {
        return Err(Error::new(
            "HDR_VIEW_REQUIRED",
            "Converting linear source samples to encoded display samples requires explicit view",
        ));
    }
    if conversion.view.is_some() && !projecting {
        return Err(Error::new(
            "INVALID_OPERATION",
            "A conversion view applies only from linear to encoded samples",
        ));
    }
    if let Some(view) = conversion.view {
        view.validate()?;
    }
    let mut converted = source.clone();
    let mut changed = 0usize;
    let mut maximum = 0.0_f64;
    let values = crate::samples::decode_values(&source.data_hex, source.depth);
    if source.depth != conversion.depth
        || source.channels != conversion.channels
        || source.encoding != encoding
    {
        let mut output = Vec::with_capacity(
            source.width as usize * source.height as usize * conversion.channels.count(),
        );
        for p in values.chunks_exact(source.channels.count()) {
            let mut p = match source.channels {
                Channels::Rgba => [p[0], p[1], p[2], p[3]],
                Channels::GrayAlpha => [p[0], p[0], p[0], p[1]],
            };
            if linear && source.encoding == crate::hdr::Encoding::EncodedSrgb {
                for v in &mut p[..3] {
                    *v = crate::hdr::decode(*v);
                }
            } else if let Some(view) = conversion.view {
                p = view.project(p);
            }
            let gray;
            let target = match conversion.channels {
                Channels::Rgba => p.as_slice(),
                Channels::GrayAlpha => {
                    let value = if linear && conversion.gray == Some(Gray::LinearLuminance) {
                        (p[0] * 2126.0 + p[1] * 7152.0 + p[2] * 722.0) / 10000.0
                    } else {
                        neutral(&p, conversion.gray.unwrap_or_default())?
                    };
                    gray = [value, p[3]];
                    gray.as_slice()
                }
            };
            for (channel, &value) in target.iter().enumerate() {
                let exact = if channel == 0
                    && conversion.channels == Channels::GrayAlpha
                    && conversion.gray == Some(Gray::EncodedLuma)
                    && source.encoding == encoding
                    && !linear
                {
                    integer_gray(&p, source.depth, conversion.depth)
                } else {
                    None
                };
                let q = exact.unwrap_or_else(|| conversion.depth.quantize(value));
                let error = (value - q).abs();
                changed += usize::from(error != 0.0);
                maximum = maximum.max(error);
                output.push(q);
            }
        }
        converted.depth = conversion.depth;
        converted.channels = conversion.channels;
        converted.encoding = encoding;
        converted.data_hex = crate::samples::encode_values(&output, conversion.depth);
    }
    converted.validate()?;
    let receipt = json!({"id":id,"promoted_inline_rgba8":promoted,"source_depth":source.depth,"source_channels":source.channels,"depth":converted.depth,"channels":converted.channels,"gray_policy":conversion.gray.unwrap_or_default(),"before_data_sha256":crate::assets::sha256(&crate::render::unhex(&source.data_hex)),"after_data_sha256":crate::assets::sha256(&crate::render::unhex(&converted.data_hex)),"quantized_channels":changed,"maximum_quantization_error":maximum,"alpha":"converted_at_requested_depth_without_premultiplication","transparent_source_color":"converted_without_alpha_zero_discard","geometry_and_appearance_controls":"unchanged","working_interpretation":converted.encoding,"source_encoding":source.encoding,"view":conversion.view,"source_preservation":"caller_snapshot_and_durable_history"});
    d.items[i].content = Content::Samples {
        grid: Box::new(converted),
    };
    Ok(receipt)
}
