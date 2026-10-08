//! Explicit RGB profiles at image boundaries and retained normalized source grids.
use crate::{Document, Error, assets, model::limit};
use base64::{Engine, engine::general_purpose::STANDARD};
use moxcms::{
    ColorProfile, DataColorSpace, Layout, ParsingOptions, RenderingIntent, TransformOptions,
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::HashSet;
pub mod cmyk;
mod curves;
pub mod device;
pub mod gamut;
pub mod proof;

pub const MAX_PROFILE_BYTES: usize = 256 * 1024;
pub const MAX_PROFILE_TAGS: usize = 128;
pub const TRANSFORM_STACK_BYTES: usize = 32 * 1024 * 1024;
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Intent {
    #[default]
    RelativeColorimetric,
    AbsoluteColorimetric,
    Perceptual,
    Saturation,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Builtin {
    Srgb,
    LinearSrgb,
    DisplayP3,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Profile {
    Builtin { name: Builtin },
    Icc { data: String },
}
fn invalid() -> Error {
    Error::new(
        "INVALID_PROFILE",
        "ICC profile has invalid framing, tags or required color data",
    )
}
fn unsupported() -> Error {
    Error::new(
        "UNSUPPORTED",
        "Profile conversion requires a supported RGB ICC v2/v4 input, display or output profile with XYZ/Lab connection space",
    )
}
fn options() -> TransformOptions {
    TransformOptions {
        rendering_intent: RenderingIntent::RelativeColorimetric,
        allow_use_cicp_transfer: false,
        prefer_fixed_point: false,
        ..Default::default()
    }
}
fn word(bytes: &[u8], at: usize) -> Result<usize, Error> {
    Ok(u32::from_be_bytes(
        bytes
            .get(at..at + 4)
            .ok_or_else(invalid)?
            .try_into()
            .unwrap(),
    ) as usize)
}
/// Bound the complete file and table before the external parser sees any profile.
pub fn parse(bytes: &[u8]) -> Result<ColorProfile, Error> {
    parse_space(bytes, false)
}
fn parse_space(bytes: &[u8], cmyk: bool) -> Result<ColorProfile, Error> {
    parse_model(
        bytes,
        if cmyk {
            DataColorSpace::Cmyk
        } else {
            DataColorSpace::Rgb
        },
        cmyk,
    )
}
fn parse_model(bytes: &[u8], space: DataColorSpace, printing: bool) -> Result<ColorProfile, Error> {
    let cmyk = space == DataColorSpace::Cmyk;
    let (signature, channels) = match space {
        DataColorSpace::Rgb => (b"RGB ", 3),
        DataColorSpace::Cmyk => (b"CMYK", 4),
        DataColorSpace::Gray => (b"GRAY", 1),
        _ => return Err(unsupported()),
    };
    let max_bytes = if cmyk {
        cmyk::MAX_PROFILE_BYTES
    } else {
        MAX_PROFILE_BYTES
    };
    if bytes.len() > max_bytes {
        return Err(limit(&format!("ICC profile exceeds {max_bytes} bytes")));
    }
    if bytes.len() < 132 || word(bytes, 0)? != bytes.len() || bytes[36..40] != *b"acsp" {
        return Err(invalid());
    }
    if ![2, 4].contains(&bytes[8])
        || !matches!(&bytes[12..16], b"scnr" | b"mntr" | b"prtr")
        || bytes[16..20] != *signature
        || (printing && bytes[12..16] != *b"prtr")
        || !matches!(&bytes[20..24], b"XYZ " | b"Lab ")
    {
        return Err(if cmyk {
            Error::new(
                "UNSUPPORTED",
                "Print delivery requires a CMYK ICC v2/v4 output profile with XYZ/Lab connection space",
            )
        } else {
            unsupported()
        });
    }
    let count = word(bytes, 128)?;
    if count > MAX_PROFILE_TAGS {
        return Err(limit("ICC profile exceeds 128 tags"));
    }
    let end = 132 + count * 12;
    if end > bytes.len() {
        return Err(invalid());
    }
    let mut signatures = HashSet::new();
    let mut ranges = Vec::new();
    for at in (132..end).step_by(12) {
        if cmyk && matches!(&bytes[at..at + 3], b"D2B" | b"B2D") {
            return Err(Error::new(
                "UNSUPPORTED",
                "Float PCS override tables are not supported by CMYK print delivery",
            ));
        }
        let offset = word(bytes, at + 4)?;
        let size = word(bytes, at + 8)?;
        let last = offset.checked_add(size).ok_or_else(invalid)?;
        if !signatures.insert(&bytes[at..at + 4])
            || offset < end
            || offset % 4 != 0
            || size < 8
            || last > bytes.len()
        {
            return Err(invalid());
        }
        if cmyk && matches!(&bytes[at..at + 3], b"A2B" | b"B2A") {
            let forward = bytes[at] == b'A';
            let tag = &bytes[offset..last];
            let classic = matches!(&tag[..4], b"mft1" | b"mft2");
            let modern = tag[..4] == *(if forward { b"mAB " } else { b"mBA " });
            if tag.len() < 12
                || (!classic && !modern)
                || tag[8..10]
                    != if forward {
                        [channels, 3]
                    } else {
                        [3, channels]
                    }
                || (modern && bytes[8] != 4)
            {
                return Err(invalid());
            }
        }
        for &(start, stop) in &ranges {
            if offset < stop && start < last && (offset, last) != (start, stop) {
                return Err(invalid());
            }
        }
        ranges.push((offset, last));
    }
    let parsed = ColorProfile::new_from_slice_with_options(
        bytes,
        ParsingOptions {
            max_profile_size: max_bytes + 1,
            max_allowed_clut_size: max_bytes,
            max_allowed_trc_size: 65536,
        },
    )
    .map_err(|_| invalid())?;
    if parsed.color_space != space {
        return Err(unsupported());
    }
    Ok(parsed)
}
pub fn resolve(profile: &Profile) -> Result<(Vec<u8>, ColorProfile), Error> {
    let bytes = match profile {
        Profile::Icc { data } => {
            if data.len() > MAX_PROFILE_BYTES.div_ceil(3) * 4 {
                return Err(limit("Encoded ICC profile exceeds byte limit"));
            }
            STANDARD.decode(data).map_err(|_| invalid())?
        }
        Profile::Builtin { name } => {
            let mut p = match name {
                Builtin::Srgb | Builtin::LinearSrgb => ColorProfile::new_srgb(),
                Builtin::DisplayP3 => ColorProfile::new_display_p3(),
            };
            // ICC v4 display profiles declare PCS D50 as their media white.
            // The adaptation matrix maps the D65 adopted white into D50;
            // a cone-response matrix alone does not describe that adaptation.
            p.white_point = moxcms::Xyzd::new(0.9642, 1.0, 0.8249);
            p.media_white_point = Some(p.white_point);
            p.chromatic_adaptation = Some(moxcms::Matrix3d {
                v: [
                    [1.0478860032225503, 0.02291876517477949, -0.050216095311733],
                    [
                        0.029581782498003393,
                        0.9904835184905486,
                        -0.01707870770448268,
                    ],
                    [
                        -0.009251880839208844,
                        0.015072607487031316,
                        0.7516781336176034,
                    ],
                ],
            });
            if *name == Builtin::LinearSrgb {
                let curve = moxcms::ToneReprCurve::Parametric(vec![1.0]);
                p.red_trc = Some(curve.clone());
                p.green_trc = Some(curve.clone());
                p.blue_trc = Some(curve);
                p.cicp = None;
                p.description = Some(moxcms::ProfileText::Localizable(vec![
                    moxcms::LocalizableString::new(
                        "en".into(),
                        "US".into(),
                        "Inkbolt linear sRGB".into(),
                    ),
                ]));
            }
            align_generated_profile(&p.encode().map_err(|_| invalid())?)?
        }
    };
    let parsed = parse(&bytes)?;
    Ok((bytes, parsed))
}
/// The codec's generated text tags are not always aligned. Reframe builtins only;
/// supplied ICC bytes are always validated and retained exactly as supplied.
fn align_generated_profile(bytes: &[u8]) -> Result<Vec<u8>, Error> {
    let count = word(bytes, 128)?;
    let end = 132 + count * 12;
    if count > MAX_PROFILE_TAGS || end > bytes.len() {
        return Err(invalid());
    }
    let mut output = bytes[..end].to_vec();
    for at in (132..end).step_by(12) {
        let start = word(bytes, at + 4)?;
        let size = word(bytes, at + 8)?;
        let value = bytes
            .get(start..start.checked_add(size).ok_or_else(invalid)?)
            .ok_or_else(invalid)?;
        let offset = output.len() as u32;
        output[at + 4..at + 8].copy_from_slice(&offset.to_be_bytes());
        output.extend_from_slice(value);
        output.resize(output.len().div_ceil(4) * 4, 0);
    }
    let size = output.len() as u32;
    output[..4].copy_from_slice(&size.to_be_bytes());
    // Generated profiles are definitions, not timestamped export events.
    for (i, value) in [2000u16, 1, 1, 0, 0, 0].iter().enumerate() {
        output[24 + i * 2..26 + i * 2].copy_from_slice(&value.to_be_bytes());
    }
    output[84..100].fill(0); // ICC permits an unset profile ID; receipts use SHA-256.
    Ok(output)
}
pub fn validate_destination(profile: &Profile) -> Result<(), Error> {
    let (_, dest) = resolve(profile)?;
    transform(&working()?, &dest)?;
    Ok(())
}
fn transform(
    source: &ColorProfile,
    destination: &ColorProfile,
) -> Result<std::sync::Arc<moxcms::TransformF64Executor>, Error> {
    transform_with_intent(source, destination, Intent::default(), false)
}
fn transform_with_intent(
    source: &ColorProfile,
    destination: &ColorProfile,
    intent: Intent,
    extended: bool,
) -> Result<std::sync::Arc<moxcms::TransformF64Executor>, Error> {
    transform_with_precision(
        source,
        destination,
        intent,
        extended,
        source.color_space == DataColorSpace::Cmyk,
    )
}
fn transform_with_precision(
    source: &ColorProfile,
    destination: &ColorProfile,
    intent: Intent,
    extended: bool,
    high_precision: bool,
) -> Result<std::sync::Arc<moxcms::TransformF64Executor>, Error> {
    let mut source = source.clone();
    let mut destination = destination.clone();
    // Select the declared directional tables explicitly. Run their connection
    // as colorimetric so the dependency cannot add implicit black-point mapping.
    let a = match intent {
        Intent::RelativeColorimetric | Intent::AbsoluteColorimetric => source
            .lut_a_to_b_colorimetric
            .as_ref()
            .or(source.lut_a_to_b_perceptual.as_ref()),
        Intent::Perceptual => source.lut_a_to_b_perceptual.as_ref(),
        Intent::Saturation => source
            .lut_a_to_b_saturation
            .as_ref()
            .or(source.lut_a_to_b_perceptual.as_ref()),
    }
    .cloned();
    let b = match intent {
        Intent::RelativeColorimetric | Intent::AbsoluteColorimetric => destination
            .lut_b_to_a_colorimetric
            .as_ref()
            .or(destination.lut_b_to_a_perceptual.as_ref()),
        Intent::Perceptual => destination.lut_b_to_a_perceptual.as_ref(),
        Intent::Saturation => destination
            .lut_b_to_a_saturation
            .as_ref()
            .or(destination.lut_b_to_a_perceptual.as_ref()),
    }
    .cloned();
    if (a.is_none()
        && (source.lut_a_to_b_perceptual.is_some()
            || source.lut_a_to_b_colorimetric.is_some()
            || source.lut_a_to_b_saturation.is_some()))
        || (b.is_none()
            && (destination.lut_b_to_a_perceptual.is_some()
                || destination.lut_b_to_a_colorimetric.is_some()
                || destination.lut_b_to_a_saturation.is_some()))
    {
        return Err(Error::new(
            "UNSUPPORTED_PROFILE_INTENT",
            "Profile lacks the requested directional intent table and its default fallback",
        ));
    }
    source.lut_a_to_b_colorimetric = a;
    destination.lut_b_to_a_colorimetric = b;
    // The external high-precision table builder needs more than the default
    // Windows stack. The owned worker exits before conversion/publication.
    std::thread::scope(|scope| {
        std::thread::Builder::new()
            .name("inkbolt-color-setup".into())
            .stack_size(TRANSFORM_STACK_BYTES)
            .spawn_scoped(scope, move || {
                source.create_transform_f64(
                    if source.color_space == DataColorSpace::Cmyk {
                        Layout::Rgba
                    } else {
                        Layout::Rgb
                    },
                    &destination,
                    if destination.color_space == DataColorSpace::Cmyk {
                        Layout::Rgba
                    } else {
                        Layout::Rgb
                    },
                    TransformOptions {
                        allow_extended_range_rgb_xyz: extended,
                        // Continuous process fallbacks must not be reduced to
                        // byte-sized interpolation bins by the color backend.
                        barycentric_weight_scale: if high_precision {
                            moxcms::BarycentricWeightScale::High
                        } else {
                            moxcms::BarycentricWeightScale::Low
                        },
                        ..options()
                    },
                )
            })
            .map_err(|_| limit("Unable to allocate bounded color transform worker"))?
            .join()
            .map_err(|_| Error::new("COLOR_CONVERSION", "Color transform setup failed"))?
            .map_err(|_| unsupported())
    })
}
fn absolute_scale(source: &ColorProfile, destination: &ColorProfile) -> Result<[f64; 3], Error> {
    let a = source.media_white_point.ok_or_else(invalid)?;
    let b = destination.media_white_point.ok_or_else(invalid)?;
    let a = [a.x, a.y, a.z];
    let b = [b.x, b.y, b.z];
    if a.iter()
        .chain(b.iter())
        .any(|v| !v.is_finite() || *v <= 0.0)
    {
        return Err(invalid());
    }
    // ICC.1:2022 section6.3.2.2: source relative -> absolute -> destination relative.
    Ok(std::array::from_fn(|i| a[i] / b[i]))
}
fn xyz_bridge() -> ColorProfile {
    let mut p = ColorProfile::new_srgb();
    // A temporary linear matrix profile represents RGB channels as XYZ/2.
    // It is an internal transform coordinate system, never a published profile.
    p.red_colorant = moxcms::Xyzd::new(2.0, 0.0, 0.0);
    p.green_colorant = moxcms::Xyzd::new(0.0, 2.0, 0.0);
    p.blue_colorant = moxcms::Xyzd::new(0.0, 0.0, 2.0);
    p.red_trc = Some(moxcms::ToneReprCurve::Parametric(vec![1.0]));
    p.green_trc = p.red_trc.clone();
    p.blue_trc = p.red_trc.clone();
    p.cicp = None;
    p
}
/// RGB rows stay straight; alpha and hidden source RGB survive conversion.
/// Return the number of channel values outside the destination range before clipping.
pub(crate) fn convert_f64(
    rgba: &mut [f64],
    source: &Profile,
    destination: &Profile,
    intent: Intent,
    clip: bool,
    control: Option<&crate::control::Control>,
) -> Result<usize, Error> {
    // Extended values are needed only at the explicitly linear working boundary.
    // Normalized nonlinear destinations must clip before their inverse TRC.
    let extended = matches!(
        destination,
        Profile::Builtin {
            name: Builtin::LinearSrgb
        }
    );
    let (source_bytes, mut source) = resolve(source)?;
    let (dest_bytes, dest) = resolve(destination)?;
    // An identical profile never needs an approximate round trip through the PCS.
    if source_bytes == dest_bytes {
        return Ok(0);
    }
    if let Some(c) = control {
        c.check()?;
    }
    let scale = if intent == Intent::AbsoluteColorimetric {
        absolute_scale(&source, &dest)?
    } else {
        [1.0; 3]
    };
    let bridge = xyz_bridge();
    let mut absolute = scale != [1.0; 3];
    if absolute
        && source.lut_a_to_b_perceptual.is_none()
        && source.lut_a_to_b_colorimetric.is_none()
        && source.lut_a_to_b_saturation.is_none()
    {
        // Matrix profiles can apply the absolute PCS scale directly. This also
        // retains negative adapted XYZ components from wide-gamut primaries.
        for column in [
            &mut source.red_colorant,
            &mut source.green_colorant,
            &mut source.blue_colorant,
        ] {
            column.x *= scale[0];
            column.y *= scale[1];
            column.z *= scale[2];
        }
        absolute = false;
    }
    let linearize = if (absolute || extended)
        && source.lut_a_to_b_perceptual.is_none()
        && source.lut_a_to_b_colorimetric.is_none()
        && source.lut_a_to_b_saturation.is_none()
    {
        // Evaluate normalized device curves using the bounded table path first.
        // The extended matrix stage then sees three identical identity curves,
        // avoiding the dependency's approximate-gamma and float table-index paths.
        let mut linear = source.clone();
        linear.red_trc = Some(moxcms::ToneReprCurve::Parametric(vec![1.0]));
        linear.green_trc = linear.red_trc.clone();
        linear.blue_trc = linear.red_trc.clone();
        linear.cicp = None;
        let transform = transform_with_intent(&source, &linear, intent, false)?;
        source = linear;
        Some(transform)
    } else {
        None
    };
    let transform = transform_with_intent(
        &source,
        if absolute { &bridge } else { &dest },
        intent,
        absolute || extended,
    )?;
    let second = if absolute {
        Some(transform_with_intent(
            &bridge,
            &dest,
            Intent::RelativeColorimetric,
            extended,
        )?)
    } else {
        None
    };
    let mut clipped = 0;
    for row in rgba.chunks_mut(4096 * 4) {
        if let Some(c) = control {
            c.check()?;
        }
        let mut input: Vec<f64> = row
            .as_chunks::<4>()
            .0
            .iter()
            .flat_map(|p| p[..3].iter().copied())
            .collect();
        if let Some(linearize) = &linearize {
            let mut linear = vec![0.0; input.len()];
            linearize.transform(&input, &mut linear).map_err(|_| {
                Error::new(
                    "COLOR_CONVERSION",
                    "Unable to linearize retained RGB samples",
                )
            })?;
            input = linear;
        }
        let mut output = vec![0.0; input.len()];
        transform.transform(&input, &mut output).map_err(|_| {
            Error::new("COLOR_CONVERSION", "Unable to convert retained RGB samples")
        })?;
        if let Some(second) = &second {
            for p in output.as_chunks_mut::<3>().0 {
                for c in 0..3 {
                    p[c] *= scale[c];
                }
            }
            if output
                .iter()
                .any(|v| !v.is_finite() || !(0.0..=1.0).contains(v))
            {
                return Err(Error::new(
                    "UNSUPPORTED_PROFILE_RANGE",
                    "Absolute connection exceeds the bounded XYZ/2 bridge range",
                ));
            }
            let mut converted = vec![0.0; output.len()];
            second.transform(&output, &mut converted).map_err(|_| {
                Error::new("COLOR_CONVERSION", "Absolute destination conversion failed")
            })?;
            output = converted;
        }
        if output.iter().any(|v| !v.is_finite()) {
            return Err(Error::new(
                "COLOR_CONVERSION",
                "Profile conversion produced non-finite samples",
            ));
        }
        for (pixel, color) in row
            .as_chunks_mut::<4>()
            .0
            .iter_mut()
            .zip(output.as_chunks::<3>().0)
        {
            for c in 0..3 {
                clipped += usize::from(!(0.0..=1.0).contains(&color[c]));
                pixel[c] = if clip {
                    color[c].clamp(0.0, 1.0)
                } else {
                    color[c]
                };
            }
        }
    }
    if let Some(c) = control {
        c.check()?;
    }
    Ok(clipped)
}
pub(crate) fn validate_source(profile: &Profile) -> Result<(), Error> {
    transform(&resolve(profile)?.1, &working()?)?;
    Ok(())
}
fn working() -> Result<ColorProfile, Error> {
    // Use the same quantized ICC definition that is declared in sRGB output.
    Ok(resolve(&Profile::Builtin {
        name: Builtin::Srgb,
    })?
    .1)
}
fn convert(
    rgba: &mut [u8],
    source: &ColorProfile,
    destination: &ColorProfile,
) -> Result<(), Error> {
    let transform = transform(source, destination)?;
    // Bounded rows of RGB protect alpha, including hidden RGB at zero alpha.
    for row in rgba.chunks_mut(4096 * 4) {
        let rgb: Vec<f64> = row
            .as_chunks::<4>()
            .0
            .iter()
            .flat_map(|p| p[..3].iter().map(|&v| v as f64 / 255.0))
            .collect();
        let mut out = vec![0.0; rgb.len()];
        transform
            .transform(&rgb, &mut out)
            .map_err(|_| Error::new("COLOR_CONVERSION", "Unable to convert RGB samples"))?;
        if out.iter().any(|v| !v.is_finite()) {
            return Err(Error::new(
                "COLOR_CONVERSION",
                "Profile conversion produced a non-finite sample",
            ));
        }
        for (pixel, color) in row
            .as_chunks_mut::<4>()
            .0
            .iter_mut()
            .zip(out.as_chunks::<3>().0)
        {
            for c in 0..3 {
                pixel[c] = (color[c].clamp(0.0, 1.0) * 255.0).round() as u8;
            }
        }
    }
    Ok(())
}
pub fn import(
    rgba: &mut [u8],
    embedded: Option<&[u8]>,
    declared: Option<&Profile>,
    policy: assets::ColorPolicy,
) -> Result<Option<String>, Error> {
    if embedded.is_none() && declared.is_none() {
        return Ok(None);
    }
    if policy != assets::ColorPolicy::ConvertSrgb {
        return Err(Error::new(
            "UNSUPPORTED",
            "Profile-tagged or explicitly profiled input requires convert_srgb color policy",
        ));
    }
    let supplied = declared.map(resolve).transpose()?;
    if let (Some(bytes), Some((expected, _))) = (embedded, supplied.as_ref())
        && bytes != expected
    {
        return Err(Error::new(
            "PROFILE_CONFLICT",
            "Embedded and explicitly declared input profiles differ",
        ));
    }
    let bytes = embedded
        .or_else(|| supplied.as_ref().map(|(b, _)| b.as_slice()))
        .unwrap();
    let source = parse(bytes)?;
    convert(rgba, &source, &working()?)?;
    Ok(Some(assets::sha256(bytes)))
}
pub fn summary(profile: &Profile) -> Result<Value, Error> {
    let (bytes, _) = resolve(profile)?;
    Ok(
        json!({"icc_sha256":assets::sha256(&bytes),"icc_bytes":bytes.len(),"samples":"rgb8","working_space":"srgb","intent":"relative_colorimetric","black_point_compensation":false,"profile_embedded":true}),
    )
}
pub fn output(document: &Document, rgba: &mut [u8]) -> Result<Option<(Vec<u8>, Value)>, Error> {
    let Some(profile) = &document.output_profile else {
        return Ok(None);
    };
    let (bytes, destination) = resolve(profile)?;
    convert(rgba, &working()?, &destination)?;
    let summary = json!({"icc_sha256":assets::sha256(&bytes),"icc_bytes":bytes.len(),"samples":"rgb8","working_space":"srgb","intent":"relative_colorimetric","black_point_compensation":false,"profile_embedded":true});
    Ok(Some((bytes, summary)))
}
