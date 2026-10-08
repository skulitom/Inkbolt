//! Bounded public image interchange, explicit alpha policy and immutable source handling.
use crate::{Document, Error, ExportFormat, assets, model::limit, sessions::Resources};
use assets::{ColorPolicy, Interpretation, Pixels};
use base64::{Engine, engine::general_purpose::STANDARD};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::io::Cursor;
use tiff::tags::Tag;
pub(crate) mod gif;
mod legacy;

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Chroma {
    Full,
    Half,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Compression {
    None,
    Lzw,
    #[default]
    Deflate,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Alpha {
    #[default]
    Unassociated,
    Associated,
}
#[derive(Clone, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Options {
    pub alpha: Option<Alpha>,
    pub quality: Option<u8>,
    pub chroma: Option<Chroma>,
    pub matte: Option<[u8; 3]>,
    pub compression: Option<Compression>,
    pub depth: Option<crate::samples::Depth>,
    pub channels: Option<crate::samples::Channels>,
}
pub(crate) fn validate_options(
    format: ExportFormat,
    options: Option<&Options>,
) -> Result<(), Error> {
    if let Some(o) = options {
        match format {
            ExportFormat::Jpeg
                if o.compression.is_none()
                    && o.depth.is_none()
                    && o.channels.is_none()
                    && o.alpha.is_none() =>
            {
                if o.quality.is_some_and(|q| !(1..=100).contains(&q)) {
                    return Err(Error::new(
                        "INVALID_REQUEST",
                        "JPEG quality must be in 1..=100",
                    ));
                }
            }
            ExportFormat::Tiff
                if o.quality.is_none() && o.chroma.is_none() && o.matte.is_none() => {}
            ExportFormat::Bmp
                if o.quality.is_none()
                    && o.chroma.is_none()
                    && o.compression.is_none()
                    && o.depth.is_none()
                    && o.channels.is_none()
                    && o.alpha.is_none() => {}
            ExportFormat::Tga
                if o.quality.is_none()
                    && o.chroma.is_none()
                    && o.matte.is_none()
                    && o.compression.is_none()
                    && o.depth.is_none()
                    && o.channels.is_none()
                    && o.alpha.is_none() => {}
            _ => {
                return Err(Error::new(
                    "INVALID_REQUEST",
                    "Image options do not apply to this export format",
                ));
            }
        }
    }
    Ok(())
}
fn malformed() -> Error {
    Error::new("INVALID_IMAGE", "Image is truncated, corrupt or malformed")
}
fn unsupported(message: &str) -> Error {
    Error::new("UNSUPPORTED", message)
}
fn tiff_error(error: tiff::TiffError) -> Error {
    match error {
        tiff::TiffError::UnsupportedError(_) => {
            unsupported("TIFF uses unsupported encoding or sample semantics")
        }
        tiff::TiffError::LimitsExceeded => limit("TIFF decoder allocation limit exceeded"),
        _ => malformed(),
    }
}
fn assume(policy: ColorPolicy) -> Result<Interpretation, Error> {
    if policy == ColorPolicy::AssumeSrgb {
        Ok(Interpretation::AssumedSrgb)
    } else {
        Err(Error::new(
            "COLOR_POLICY_REQUIRED",
            "Untagged images require explicit assume_srgb color policy or an input profile",
        ))
    }
}
pub(crate) struct Decoded {
    pub metadata: Option<Value>,
    pub source_profile_sha256: Option<String>,
    pub pixels: Pixels,
    pub interpretation: Interpretation,
    pub format: &'static str,
    pub losses: Vec<&'static str>,
}

/// Validate all marker framing, including later progressive scans and metadata.
fn jpeg_framing(bytes: &[u8]) -> Result<Option<Vec<u8>>, Error> {
    let mut position = 2;
    let mut scanned = false;
    let mut parts: Vec<Option<Vec<u8>>> = Vec::new();
    let mut profile_size = 0;
    while position < bytes.len() {
        if bytes[position] != 255 {
            return Err(malformed());
        }
        while bytes.get(position) == Some(&255) {
            position += 1;
        }
        let marker = *bytes.get(position).ok_or_else(malformed)?;
        position += 1;
        match marker {
            0xd9 => {
                return if scanned && position == bytes.len() {
                    if parts.is_empty() {
                        Ok(None)
                    } else {
                        let mut profile = Vec::with_capacity(profile_size);
                        for part in parts {
                            profile.extend(part.ok_or_else(malformed)?);
                        }
                        Ok(Some(profile))
                    }
                } else {
                    Err(malformed())
                };
            }
            0 | 0xd0..=0xd8 => return Err(malformed()),
            1 => continue,
            _ => {}
        }
        let length = bytes.get(position..position + 2).ok_or_else(malformed)?;
        let length = u16::from_be_bytes([length[0], length[1]]) as usize;
        if length < 2 {
            return Err(malformed());
        }
        let end = position
            .checked_add(length)
            .filter(|&v| v <= bytes.len())
            .ok_or_else(malformed)?;
        if marker == 0xe2 && bytes[position + 2..end].starts_with(b"ICC_PROFILE\0") {
            let payload = &bytes[position + 2..end];
            if payload.len() < 15
                || payload[12] == 0
                || payload[13] == 0
                || payload[12] > payload[13]
            {
                return Err(malformed());
            }
            if parts.is_empty() {
                parts.resize(payload[13] as usize, None);
            }
            if parts.len() != payload[13] as usize || parts[payload[12] as usize - 1].is_some() {
                return Err(malformed());
            }
            profile_size += payload.len() - 14;
            if profile_size > crate::profiles::MAX_PROFILE_BYTES {
                return Err(limit("JPEG profile exceeds 256 KiB"));
            }
            parts[payload[12] as usize - 1] = Some(payload[14..].to_vec());
        } else if matches!(marker, 0xe1 | 0xe2 | 0xed | 0xee) {
            return Err(unsupported(
                "JPEG extended application metadata, profiles and orientation require explicit unsupported-semantics handling",
            ));
        }
        position = end;
        if marker == 0xda {
            scanned = true;
            loop {
                match bytes.get(position) {
                    None => return Err(malformed()),
                    Some(255) => match bytes.get(position + 1) {
                        Some(0 | 0xd0..=0xd7) => position += 2,
                        Some(255) => position += 1,
                        Some(_) => break,
                        None => return Err(malformed()),
                    },
                    Some(_) => position += 1,
                }
            }
        }
    }
    Err(malformed())
}
fn jpeg(
    bytes: &[u8],
    policy: ColorPolicy,
    declared: Option<&crate::profiles::Profile>,
) -> Result<Decoded, Error> {
    let profile = jpeg_framing(bytes)?;
    let interpretation = if profile.is_some() || declared.is_some() {
        Interpretation::ConvertedSrgb
    } else {
        assume(policy)?
    };
    let mut decoder = jpeg_decoder::Decoder::new(Cursor::new(bytes));
    decoder.set_max_decoding_buffer_size(64 * 1024 * 1024);
    decoder.read_info().map_err(|_| malformed())?;
    let info = decoder.info().ok_or_else(malformed)?;
    let (width, height) = (info.width as u32, info.height as u32);
    assets::dimensions(width, height)?;
    let channels = match info.pixel_format {
        jpeg_decoder::PixelFormat::L8 => 1,
        jpeg_decoder::PixelFormat::RGB24 => 3,
        _ => {
            return Err(unsupported(
                "JPEG import requires 8-bit grayscale or RGB samples",
            ));
        }
    };
    if channels == 1 && profile.is_some() {
        return Err(unsupported(
            "Profile-tagged grayscale requires the grayscale color pipeline",
        ));
    }
    let decoded = decoder.decode().map_err(|_| malformed())?;
    if decoded.len() != width as usize * height as usize * channels {
        return Err(malformed());
    }
    let mut rgba = decoded
        .chunks_exact(channels)
        .flat_map(|p| {
            if channels == 1 {
                [p[0], p[0], p[0], 255]
            } else {
                [p[0], p[1], p[2], 255]
            }
        })
        .collect::<Vec<_>>();
    let source_profile_sha256 =
        crate::profiles::import(&mut rgba, profile.as_deref(), declared, policy)?;
    Ok(Decoded {
        metadata: None,
        source_profile_sha256,
        pixels: Pixels {
            width,
            height,
            rgba,
        },
        interpretation,
        format: "jpeg",
        losses: vec![
            "JPEG decoding retains the decoded 8-bit samples; lossy source compression cannot be reversed. Recognized Inkbolt descriptions are returned separately as untrusted metadata; other ancillary data and source density are retained only through the source-byte hash.",
        ],
    })
}
fn tiff(
    bytes: &[u8],
    policy: ColorPolicy,
    declared: Option<&crate::profiles::Profile>,
) -> Result<Decoded, Error> {
    let mut limits = tiff::decoder::Limits::default();
    limits.decoding_buffer_size = 64 * 1024 * 1024;
    limits.intermediate_buffer_size = 64 * 1024 * 1024;
    let mut decoder = tiff::decoder::Decoder::new(Cursor::new(bytes))
        .map_err(tiff_error)?
        .with_limits(limits);
    let (width, height) = decoder.dimensions().map_err(tiff_error)?;
    assets::dimensions(width, height)?;
    if decoder.more_images() {
        return Err(unsupported(
            "Multiple TIFF pages require an explicit page or sequence importer",
        ));
    }
    for tag in [301, 318, 319, 330, 34665, 50706] {
        if decoder
            .find_tag(Tag::from_u16_exhaustive(tag))
            .map_err(tiff_error)?
            .is_some()
        {
            return Err(unsupported(
                "TIFF profiles, transfer functions, alternate chromaticities, raw data and nested image directories are unsupported",
            ));
        }
    }
    let profile = decoder
        .find_tag(Tag::from_u16_exhaustive(34675))
        .map_err(tiff_error)?
        .map(|v| v.into_u8_vec())
        .transpose()
        .map_err(tiff_error)?;
    if profile.is_some() && policy != ColorPolicy::ConvertSrgb {
        return Err(unsupported(
            "Embedded TIFF profiles require explicit convert_srgb policy",
        ));
    }
    if decoder
        .find_tag_unsigned::<u16>(Tag::Orientation)
        .map_err(tiff_error)?
        .unwrap_or(1)
        != 1
    {
        return Err(unsupported(
            "TIFF orientation requires explicit normalization; only top-left pixels are supported",
        ));
    }
    let compression = decoder
        .find_tag_unsigned::<u16>(Tag::Compression)
        .map_err(tiff_error)?
        .unwrap_or(1);
    if ![1, 5, 8, 32946, 32773].contains(&compression) {
        return Err(unsupported(
            "TIFF import supports uncompressed, LZW, Deflate and PackBits samples",
        ));
    }
    let photometric = decoder
        .find_tag_unsigned::<u16>(Tag::PhotometricInterpretation)
        .map_err(tiff_error)?
        .ok_or_else(malformed)?;
    let samples = decoder
        .find_tag_unsigned::<u16>(Tag::SamplesPerPixel)
        .map_err(tiff_error)?
        .unwrap_or(1);
    let sample_formats = decoder
        .find_tag_unsigned_vec::<u16>(Tag::SampleFormat)
        .map_err(tiff_error)?
        .unwrap_or_else(|| vec![1]);
    if sample_formats.iter().any(|&v| v != 1) || ![0, 1, 2].contains(&photometric) {
        return Err(unsupported(
            "TIFF import requires unsigned grayscale or RGB samples",
        ));
    }
    if photometric == 0 && samples != 1 {
        return Err(unsupported(
            "White-is-zero TIFF currently requires one grayscale sample without alpha",
        ));
    }
    let channels = match decoder.colortype().map_err(tiff_error)? {
        tiff::ColorType::Gray(8) => 1,
        tiff::ColorType::GrayA(8) => 2,
        tiff::ColorType::RGB(8) => 3,
        tiff::ColorType::RGBA(8) => 4,
        tiff::ColorType::Multiband {
            bit_depth: 8,
            num_samples: 2,
        } if photometric <= 1 && samples == 2 => 2,
        _ => {
            return Err(unsupported(
                "TIFF import requires 8-bit grayscale, grayscale-alpha, RGB or RGBA samples",
            ));
        }
    };
    let extra = decoder
        .find_tag_unsigned_vec::<u16>(Tag::ExtraSamples)
        .map_err(tiff_error)?
        .unwrap_or_default();
    if (channels == 2 || channels == 4) && extra != [2] && extra != [1]
        || (channels == 1 || channels == 3) && !extra.is_empty()
    {
        return Err(unsupported(
            "TIFF alpha must be explicitly associated or unassociated; unspecified extra samples are unsupported",
        ));
    }
    let planar = decoder
        .find_tag_unsigned::<u16>(Tag::PlanarConfiguration)
        .map_err(tiff_error)?
        .unwrap_or(1);
    if ![1, 2].contains(&planar) {
        return Err(malformed());
    }
    if channels < 3 && profile.is_some() {
        return Err(unsupported(
            "Profile-tagged grayscale requires the grayscale color pipeline",
        ));
    }
    let interpretation = if profile.is_some() || declared.is_some() {
        Interpretation::ConvertedSrgb
    } else {
        assume(policy)?
    };
    let count = width as usize * height as usize;
    let mut decoded = vec![0; count * channels];
    decoder.read_image_bytes(&mut decoded).map_err(tiff_error)?;
    let mut rgba = Vec::with_capacity(count * 4);
    for i in 0..count {
        let sample = |c| {
            decoded[if planar == 2 {
                c * count + i
            } else {
                i * channels + c
            }]
        };
        rgba.extend_from_slice(&match channels {
            1 => [sample(0), sample(0), sample(0), 255],
            2 => [sample(0), sample(0), sample(0), sample(1)],
            3 => [sample(0), sample(1), sample(2), 255],
            _ => [sample(0), sample(1), sample(2), sample(3)],
        });
    }
    if extra == [1] {
        for pixel in rgba.as_chunks_mut::<4>().0 {
            legacy::unassociate(pixel)?;
        }
    }
    let source_profile_sha256 =
        crate::profiles::import(&mut rgba, profile.as_deref(), declared, policy)?;
    Ok(Decoded {
        metadata: None,
        source_profile_sha256,
        pixels: Pixels {
            width,
            height,
            rgba,
        },
        interpretation,
        format: "tiff",
        losses: vec![
            "Recognized Inkbolt descriptions are returned separately as untrusted metadata; other descriptions and source density are retained only through the source-byte hash. Placement uses explicit pixel dimensions; source files remain unchanged. Associated alpha is unassociated with integer rounding; hidden zero-alpha RGB becomes zero.",
        ],
    })
}
pub(crate) fn decode(
    bytes: &[u8],
    policy: ColorPolicy,
    declared: Option<&crate::profiles::Profile>,
) -> Result<Decoded, Error> {
    if bytes.starts_with(b"GIF87a") || bytes.starts_with(b"GIF89a") {
        gif::still(bytes, policy, declared)
    } else if bytes.starts_with(b"BM") {
        legacy::bmp(bytes, policy, declared)
    } else if bytes.starts_with(&[255, 216]) {
        jpeg(bytes, policy, declared)
    } else if bytes.starts_with(b"II") || bytes.starts_with(b"MM") {
        tiff(bytes, policy, declared)
    } else if legacy::is_tga(bytes) {
        legacy::tga(bytes, policy, declared)
    } else {
        Err(unsupported(
            "Image import requires PNG, JPEG, TIFF, BMP, TGA or GIF input",
        ))
    }
}

pub(crate) fn export_with_metadata(
    document: &Document,
    format: ExportFormat,
    scale: u32,
    resources: &Resources,
    options: Option<&Options>,
    metadata: Option<&str>,
    render_options: Option<&crate::render_quality::Options>,
) -> Result<Value, Error> {
    validate_options(format, options)?;
    let defaults = Options::default();
    let options = options.unwrap_or(&defaults);
    if options.depth.is_some() || options.channels.is_some() {
        if matches!(options.alpha, Some(Alpha::Associated)) {
            return Err(unsupported(
                "Associated TIFF delivery currently requires the RGBA8 image path; explicit native-depth delivery retains unassociated alpha",
            ));
        }
        return crate::sample_tiff::export(
            document,
            scale,
            resources,
            options,
            metadata,
            render_options,
        );
    }
    let mut p = crate::render::rasterize_with_options(
        document,
        scale,
        resources.asset_root.as_deref(),
        resources.font_root.as_deref(),
        render_options,
    )?;
    if matches!(format, ExportFormat::Bmp | ExportFormat::Tga) {
        if document.output_profile.is_some() {
            return Err(unsupported(
                "BMP24 and TGA delivery cannot embed an output ICC profile; clear the association explicitly or choose a profiled format",
            ));
        }
        if metadata.is_some() {
            return Err(unsupported(
                "BMP24 and TGA delivery cannot embed descriptive metadata; select metadata stripping or choose a metadata carrier",
            ));
        }
    }
    if matches!(format, ExportFormat::Jpeg | ExportFormat::Bmp) {
        if options.matte.is_none() && p.rgba.as_chunks::<4>().0.iter().any(|v| v[3] != 255) {
            return Err(Error::new(
                "ALPHA_POLICY_REQUIRED",
                "RGB-only delivery cannot retain alpha; supply an explicit RGB matte",
            ));
        }
        let matte = options.matte.unwrap_or([0; 3]);
        for pixel in p.rgba.as_chunks_mut::<4>().0 {
            for c in 0..3 {
                pixel[c] = ((pixel[c] as u32 * pixel[3] as u32
                    + matte[c] as u32 * (255 - pixel[3] as u32)
                    + 127)
                    / 255) as u8;
            }
            pixel[3] = 255;
        }
    }
    let profile = crate::profiles::output(document, &mut p.rgba)?;
    let ppi = document.resolution_ppi * scale as f64;
    let (bytes, media, losses, settings) = match format {
        ExportFormat::Bmp | ExportFormat::Tga => {
            let bmp = matches!(format, ExportFormat::Bmp);
            (
                legacy::encode(&p, format, ppi)?,
                if bmp { "image/bmp" } else { "image/x-tga" },
                vec![if bmp {
                    "BMP24 retains rendered RGB exactly after any explicit encoded-sRGB matte. It cannot retain alpha, profiles or descriptions. Density is rounded to whole pixels per meter. Editable layers require snapshots."
                } else {
                    "TGA32 retains rendered straight RGBA8 exactly with useful alpha declared in its version-2 extension. It cannot retain ICC profiles, descriptions or physical density in this contract. Editable layers require snapshots."
                }],
                json!({"alpha":if bmp {"opaque"} else {"unassociated"},"matte":options.matte,"resolution_ppi":if bmp {Some((ppi/0.0254).round()*0.0254)} else {None}}),
            )
        }
        ExportFormat::Jpeg => {
            if p.width > u16::MAX as u32
                || p.height > u16::MAX as u32
                || ppi.round() > u16::MAX as f64
            {
                return Err(limit("JPEG dimensions or rounded density exceed 65535"));
            }
            let quality = options.quality.unwrap_or(90);
            let chroma = options.chroma.unwrap_or(Chroma::Full);
            let rgb: Vec<u8> = p
                .rgba
                .as_chunks::<4>()
                .0
                .iter()
                .flat_map(|v| v[..3].iter().copied())
                .collect();
            let mut bytes = Vec::new();
            let mut encoder = jpeg_encoder::Encoder::new(&mut bytes, quality);
            if let Some((bytes, _)) = &profile {
                encoder
                    .add_icc_profile(bytes)
                    .map_err(|_| Error::new("EXPORT_ERROR", "Unable to embed JPEG profile"))?;
            }
            encoder.set_sampling_factor(match chroma {
                Chroma::Full => jpeg_encoder::SamplingFactor::F_1_1,
                Chroma::Half => jpeg_encoder::SamplingFactor::F_2_2,
            });
            encoder.set_density(jpeg_encoder::PixelDensity::dpi(ppi.round() as u16));
            encoder
                .encode(
                    &rgb,
                    p.width as u16,
                    p.height as u16,
                    jpeg_encoder::ColorType::Rgb,
                )
                .map_err(|_| Error::new("EXPORT_ERROR", "Unable to encode JPEG samples"))?;
            (
                bytes,
                "image/jpeg",
                vec![
                    "JPEG is lossy and cannot preserve alpha or editable layers. An explicit matte composites alpha in encoded sRGB before compression. Quality is an encoder setting, not a universal pixel-error guarantee.",
                    if profile.is_some() {
                        "Output uses the embedded RGB profile with relative colorimetric conversion and no black-point compensation. Gamut clipping and RGB8 quantization are not reversible. Density is rounded to whole pixels per inch."
                    } else {
                        "Output uses untagged sRGB sample interpretation; no ICC profile is embedded. Density is rounded to whole pixels per inch."
                    },
                ],
                json!({"quality":quality,"chroma":chroma,"matte":options.matte,"resolution_ppi":ppi.round()}),
            )
        }
        ExportFormat::Tiff => {
            let compression = options.compression.unwrap_or_default();
            let alpha = options.alpha.unwrap_or_default();
            if matches!(alpha, Alpha::Associated) {
                for pixel in p.rgba.as_chunks_mut::<4>().0 {
                    let a = u32::from(pixel[3]);
                    for v in &mut pixel[..3] {
                        *v = ((u32::from(*v) * a + 127) / 255) as u8;
                    }
                }
            }
            let mut bytes = Cursor::new(Vec::new());
            {
                let method = match compression {
                    Compression::None => tiff::encoder::Compression::Uncompressed,
                    Compression::Lzw => tiff::encoder::Compression::Lzw,
                    Compression::Deflate => tiff::encoder::Compression::Deflate(Default::default()),
                };
                let mut encoder = tiff::encoder::TiffEncoder::new(&mut bytes)
                    .map_err(|_| Error::new("EXPORT_ERROR", "Unable to create TIFF"))?
                    .with_compression(method);
                let mut image = encoder
                    .new_image::<tiff::encoder::colortype::RGBA8>(p.width, p.height)
                    .map_err(|_| Error::new("EXPORT_ERROR", "Unable to encode TIFF header"))?;
                if let Some(metadata) = metadata {
                    image
                        .encoder()
                        .write_tag(
                            Tag::ImageDescription,
                            format!("{}{}", crate::metadata::TEXT_PREFIX, metadata).as_str(),
                        )
                        .map_err(|_| {
                            Error::new("EXPORT_ERROR", "Unable to encode TIFF metadata")
                        })?;
                }
                if let Some((bytes, _)) = &profile {
                    image
                        .encoder()
                        .write_tag(Tag::from_u16_exhaustive(34675), bytes.as_slice())
                        .map_err(|_| Error::new("EXPORT_ERROR", "Unable to embed TIFF profile"))?;
                }
                image
                    .encoder()
                    .write_tag(
                        Tag::ExtraSamples,
                        &[if matches!(alpha, Alpha::Associated) {
                            1u16
                        } else {
                            2u16
                        }][..],
                    )
                    .map_err(|_| {
                        Error::new("EXPORT_ERROR", "Unable to encode TIFF alpha semantics")
                    })?;
                image
                    .encoder()
                    .write_tag(Tag::Orientation, 1u16)
                    .map_err(|_| Error::new("EXPORT_ERROR", "Unable to encode TIFF orientation"))?;
                image.resolution(
                    tiff::tags::ResolutionUnit::Inch,
                    tiff::encoder::Rational {
                        n: (ppi * 1000.0).round() as u32,
                        d: 1000,
                    },
                );
                image
                    .write_data(&p.rgba)
                    .map_err(|_| Error::new("EXPORT_ERROR", "Unable to encode TIFF samples"))?;
            }
            (
                bytes.into_inner(),
                "image/tiff",
                vec![if profile.is_some() {
                    "TIFF stores converted RGBA8 samples with the exact embedded RGB profile and declared alpha mode. Relative colorimetric conversion clips gamut and quantizes RGB8 without black-point compensation; that conversion is not reversible. Editable layers require snapshots. Density is rounded to 0.001 pixels per inch."
                } else {
                    "TIFF retains rendered RGBA8 with declared alpha mode; unassociated samples are lossless. Editable layers and source metadata require snapshots. Output uses untagged sRGB sample interpretation with no ICC profile; density is rounded to 0.001 pixels per inch."
                }],
                json!({"compression":compression,"alpha":alpha,"resolution_ppi":(ppi*1000.0).round()/1000.0}),
            )
        }
        _ => return Err(unsupported("JPEG/TIFF encoder requires a matching format")),
    };
    if bytes.len() > crate::publish::MAX_OUTPUT_BYTES {
        return Err(limit("Encoded image exceeds output byte limit"));
    }
    let mut artifact = json!({"media_type":media,"encoding":"base64","width":p.width,"height":p.height,"color_space":"srgb","settings":settings,"losses":losses,"data":STANDARD.encode(bytes)});
    if matches!(options.alpha, Some(Alpha::Associated)) {
        artifact["losses"].as_array_mut().unwrap().push(json!("Associated alpha multiplies encoded destination color by alpha and rounds to RGB8. Unassociation cannot recover hidden RGB or every low-alpha source value; alpha bytes remain exact."));
    }
    if let Some((_, summary)) = profile {
        artifact["color_profile"] = summary;
        artifact["color_space"] = json!("icc_rgb");
    }
    crate::swatches::annotate(document, &mut artifact)?;
    crate::samples::annotate(document, &mut artifact, crate::samples::Depth::U8);
    Ok(artifact)
}
