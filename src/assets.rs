//! Immutable image assets. Explicit paths are runtime inputs, never snapshot identities.
use crate::{
    Error,
    model::{MAX_DIMENSION, MAX_STORED_PIXELS, invalid, limit},
    render,
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs::{self, File, OpenOptions},
    io::{Cursor, Read, Write},
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};

pub const MAX_ASSETS: usize = 64;
pub const MAX_ASSET_PIXELS: u64 = 16_777_216;
pub const MAX_IMPORT_BYTES: u64 = 32 * 1024 * 1024;
const MAGIC: &[u8; 8] = b"INKRGBA1";
static TEMP_ID: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ColorPolicy {
    #[default]
    RequireSrgb,
    AssumeSrgb,
    ConvertSrgb,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Interpretation {
    DeclaredSrgb,
    AssumedSrgb,
    ConvertedSrgb,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Provenance {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_profile_sha256: Option<String>,
    pub source_sha256: String,
    pub interpretation: Interpretation,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Storage {
    Stored,
    Embedded { rgba_hex: String },
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ImageAsset {
    pub width: u32,
    pub height: u32,
    pub sha256: String,
    pub storage: Storage,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provenance: Option<Provenance>,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Sampling {
    #[default]
    Nearest,
    Bilinear,
    Area,
    Bicubic,
    Lanczos3,
}
impl Sampling {
    pub(crate) fn advanced(self) -> bool {
        matches!(self, Self::Area | Self::Bicubic | Self::Lanczos3)
    }
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Crop {
    pub x: u32,
    pub y: u32,
    pub width: u32,
    pub height: u32,
}
pub struct Pixels {
    pub width: u32,
    pub height: u32,
    pub rgba: Vec<u8>,
}
pub fn sha256(bytes: &[u8]) -> String {
    render::hex(&Sha256::digest(bytes))
}
fn header(width: u32, height: u32) -> [u8; 16] {
    let mut h = [0; 16];
    h[..8].copy_from_slice(MAGIC);
    h[8..12].copy_from_slice(&width.to_le_bytes());
    h[12..].copy_from_slice(&height.to_le_bytes());
    h
}
pub fn identity(width: u32, height: u32, rgba: &[u8]) -> String {
    let mut digest = Sha256::new();
    digest.update(header(width, height));
    digest.update(rgba);
    render::hex(&digest.finalize())
}
fn valid_hash(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
pub(crate) fn dimensions(width: u32, height: u32) -> Result<u64, Error> {
    let count = width as u64 * height as u64;
    if !(1..=MAX_DIMENSION).contains(&width)
        || !(1..=MAX_DIMENSION).contains(&height)
        || count > MAX_ASSET_PIXELS
    {
        return Err(limit(
            "Asset dimensions or decoded pixel count exceed limits",
        ));
    }
    Ok(count)
}
pub fn validate(asset: &ImageAsset) -> Result<usize, Error> {
    let count = dimensions(asset.width, asset.height)?;
    if !valid_hash(&asset.sha256)
        || asset.provenance.as_ref().is_some_and(|p| {
            !valid_hash(&p.source_sha256)
                || p.source_profile_sha256
                    .as_ref()
                    .is_some_and(|s| !valid_hash(s))
                || (p.interpretation == Interpretation::ConvertedSrgb)
                    != p.source_profile_sha256.is_some()
        })
    {
        return Err(invalid("Asset identities must be lowercase SHA-256 hex"));
    }
    if let Storage::Embedded { rgba_hex } = &asset.storage {
        if count > MAX_STORED_PIXELS as u64 {
            return Err(limit("Embedded image exceeds inline pixel limit"));
        }
        if rgba_hex.len() != count as usize * 8 || !rgba_hex.bytes().all(|c| c.is_ascii_hexdigit())
        {
            return Err(invalid(
                "Embedded image requires exactly width*height RGBA8 hex values",
            ));
        }
        if identity(asset.width, asset.height, &render::unhex(rgba_hex)) != asset.sha256 {
            return Err(Error::new(
                "ASSET_CORRUPT",
                "Embedded pixels do not match their declared content identity",
            ));
        }
        return Ok(count as usize);
    }
    Ok(0)
}
pub fn crop(asset_width: u32, asset_height: u32, crop: Option<Crop>) -> Result<Crop, Error> {
    let c = crop.unwrap_or(Crop {
        x: 0,
        y: 0,
        width: asset_width,
        height: asset_height,
    });
    if c.width == 0
        || c.height == 0
        || c.x as u64 + c.width as u64 > asset_width as u64
        || c.y as u64 + c.height as u64 > asset_height as u64
    {
        return Err(invalid(
            "Image crop must be nonempty and inside source pixels",
        ));
    }
    Ok(c)
}
pub(crate) fn absolute(path: &Path) -> Result<(), Error> {
    if !path.is_absolute() {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Asset paths must be absolute",
        ));
    }
    Ok(())
}
fn io_error() -> Error {
    Error::new(
        "IO_ERROR",
        "Unable to access the explicitly supplied asset path",
    )
}
pub(crate) fn read_bounded(path: &Path, max: u64) -> Result<Vec<u8>, Error> {
    let f = File::open(path).map_err(|_| io_error())?;
    let metadata = f.metadata().map_err(|_| io_error())?;
    if !metadata.is_file() {
        return Err(io_error());
    }
    if metadata.len() > max {
        return Err(limit("Asset input exceeds byte limit"));
    }
    let mut bytes = Vec::new();
    f.take(max + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| io_error())?;
    if bytes.len() as u64 > max {
        return Err(limit("Asset input exceeds byte limit"));
    }
    Ok(bytes)
}
pub fn load(asset: &ImageAsset, root: Option<&Path>) -> Result<Pixels, Error> {
    validate(asset)?;
    let rgba = match &asset.storage {
        Storage::Embedded { rgba_hex } => render::unhex(rgba_hex),
        Storage::Stored => {
            let root = root.ok_or_else(|| {
                Error::new(
                    "ASSET_ROOT_REQUIRED",
                    "Stored images require an explicit asset root",
                )
            })?;
            absolute(root)?;
            let path = root.join(format!("{}.rgba8", asset.sha256));
            let metadata = fs::symlink_metadata(&path).map_err(|e| {
                if e.kind() == std::io::ErrorKind::NotFound {
                    Error::new(
                        "ASSET_MISSING",
                        "Content-addressed image is missing from the supplied asset root",
                    )
                } else {
                    io_error()
                }
            })?;
            if metadata.file_type().is_symlink() || !metadata.is_file() {
                return Err(Error::new(
                    "ASSET_CORRUPT",
                    "Stored asset must be a regular, non-symlink file",
                ));
            }
            let expected = 16 + asset.width as u64 * asset.height as u64 * 4;
            if metadata.len() != expected {
                return Err(Error::new(
                    "ASSET_CORRUPT",
                    "Stored image size does not match its descriptor",
                ));
            }
            let bytes = read_bounded(&path, expected)?;
            if bytes.len() != expected as usize
                || bytes[..16] != header(asset.width, asset.height)
                || sha256(&bytes) != asset.sha256
            {
                return Err(Error::new(
                    "ASSET_CORRUPT",
                    "Stored image bytes do not match their content identity",
                ));
            }
            bytes[16..].to_vec()
        }
    };
    Ok(Pixels {
        width: asset.width,
        height: asset.height,
        rgba,
    })
}
/// Resolve every referenced asset before rendering, including hidden items; never render a partial result.
pub fn resolve(
    document: &crate::Document,
    root: Option<&Path>,
) -> Result<BTreeMap<String, Pixels>, Error> {
    let mut result = BTreeMap::new();
    for item in &document.items {
        if let crate::model::Content::Image { asset_id, .. } = &item.content
            && !result.contains_key(asset_id)
        {
            let asset = document
                .assets
                .get(asset_id)
                .ok_or_else(|| invalid("Image refers to an undefined asset"))?;
            result.insert(
                asset_id.clone(),
                load(asset, root).map_err(|e| e.at_asset(asset_id))?,
            );
        }
    }
    Ok(result)
}
pub fn embed(asset: &ImageAsset, root: Option<&Path>) -> Result<ImageAsset, Error> {
    if asset.width as u64 * asset.height as u64 > MAX_STORED_PIXELS as u64 {
        return Err(limit(
            "Image is too large to embed; retain its stored identity",
        ));
    }
    let pixels = load(asset, root)?;
    let mut result = asset.clone();
    result.storage = Storage::Embedded {
        rgba_hex: render::hex(&pixels.rgba),
    };
    Ok(result)
}
struct Temporary(PathBuf);
impl Drop for Temporary {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.0);
    }
}
pub(crate) fn publish(asset: &ImageAsset, rgba: &[u8], root: &Path) -> Result<bool, Error> {
    absolute(root)?;
    fs::create_dir_all(root).map_err(|_| io_error())?;
    let root = fs::canonicalize(root).map_err(|_| io_error())?;
    let target = root.join(format!("{}.rgba8", asset.sha256));
    if target.try_exists().map_err(|_| io_error())? {
        load(asset, Some(&root))?;
        return Ok(false);
    }
    let mut attempts = 0;
    let (temporary, mut f) = loop {
        attempts += 1;
        if attempts > 64 {
            return Err(Error::new(
                "ASSET_STORE_ERROR",
                "Unable to reserve a temporary asset name within the retry limit",
            ));
        }
        let path = root.join(format!(
            ".inkbolt-{}-{}.tmp",
            std::process::id(),
            TEMP_ID.fetch_add(1, Ordering::Relaxed)
        ));
        match OpenOptions::new().write(true).create_new(true).open(&path) {
            Ok(f) => break (Temporary(path), f),
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(_) => return Err(io_error()),
        }
    };
    #[cfg(all(test, windows))]
    crate::resource_recovery_tests::checkpoint(&root, "image_before_write");
    f.write_all(&header(asset.width, asset.height))
        .and_then(|_| f.write_all(rgba))
        .and_then(|_| f.sync_all())
        .map_err(|_| io_error())?;
    drop(f);
    #[cfg(all(test, windows))]
    crate::resource_recovery_tests::checkpoint(&root, "image_before_publish");
    // A hard link publishes the completely written file without replacing an existing name.
    let created = match fs::hard_link(&temporary.0, &target) {
        Ok(()) => true,
        Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {
            load(asset, Some(&root))?;
            false
        }
        Err(_) => {
            return Err(Error::new(
                "ASSET_STORE_ERROR",
                "Asset root must support atomic create-only hard-link publication",
            ));
        }
    };
    #[cfg(all(test, windows))]
    crate::resource_recovery_tests::checkpoint(&root, "image_after_publish");
    Ok(created)
}
fn png_error() -> Error {
    Error::new("INVALID_IMAGE", "PNG is truncated, corrupt or malformed")
}
/// Inspect framing before decoding so unsupported animation/profile/orientation semantics cannot disappear.
fn preflight(bytes: &[u8], policy: ColorPolicy, declared: bool) -> Result<Interpretation, Error> {
    preflight_depth(bytes, policy, declared, false, false)
}
pub(crate) fn preflight_samples(
    bytes: &[u8],
    policy: ColorPolicy,
) -> Result<Interpretation, Error> {
    preflight_depth(bytes, policy, false, true, false)
}
pub(crate) fn preflight_sequence(
    bytes: &[u8],
    policy: ColorPolicy,
) -> Result<Interpretation, Error> {
    if policy == ColorPolicy::ConvertSrgb {
        return Err(Error::new(
            "UNSUPPORTED",
            "Sequence import does not yet convert color profiles",
        ));
    }
    preflight_depth(bytes, policy, false, false, true)
}
fn preflight_depth(
    bytes: &[u8],
    policy: ColorPolicy,
    declared: bool,
    samples: bool,
    animation: bool,
) -> Result<Interpretation, Error> {
    if bytes.get(..8) != Some(b"\x89PNG\r\n\x1a\n") {
        return Err(Error::new(
            "UNSUPPORTED",
            "Image import currently requires PNG input",
        ));
    }
    let mut offset = 8usize;
    let mut srgb = false;
    let mut icc = false;
    let mut other_color = false;
    let mut ended = false;
    while offset < bytes.len() {
        let framing = bytes.get(offset..offset + 8).ok_or_else(png_error)?;
        let size = u32::from_be_bytes(framing[..4].try_into().unwrap()) as usize;
        let kind = &framing[4..];
        let end = offset
            .checked_add(size)
            .and_then(|v| v.checked_add(12))
            .filter(|v| *v <= bytes.len())
            .ok_or_else(png_error)?;
        let expected = u32::from_be_bytes(bytes[end - 4..end].try_into().unwrap());
        if crc32fast::hash(&bytes[offset + 4..end - 4]) != expected {
            return Err(png_error());
        }
        if offset == 8 {
            if kind != b"IHDR" || size != 13 {
                return Err(png_error());
            }
            let w = u32::from_be_bytes(bytes[offset + 8..offset + 12].try_into().unwrap());
            let h = u32::from_be_bytes(bytes[offset + 12..offset + 16].try_into().unwrap());
            dimensions(w, h)?;
            if samples && w as u64 * h as u64 > MAX_STORED_PIXELS as u64 {
                return Err(limit("Sample import exceeds 65536 inline pixels"));
            }
            if bytes[offset + 16] == 16 && !samples {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "Use sample.import to retain 16-bit image samples",
                ));
            }
        }
        match kind {
            b"iCCP" if policy == ColorPolicy::ConvertSrgb => {
                if icc {
                    return Err(png_error());
                }
                icc = true;
            }
            b"iCCP" | b"cICP" | b"mDCV" | b"cLLI" => {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "Embedded profiles and HDR color metadata are not supported by this image importer",
                ));
            }
            b"acTL" | b"fcTL" | b"fdAT" if !animation => {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "Animated PNG requires an explicit sequence importer",
                ));
            }
            b"eXIf" => {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "Image orientation metadata is not supported; provide an explicitly oriented pixel image",
                ));
            }
            b"sRGB" => srgb = true,
            b"gAMA" | b"cHRM" => other_color = true,
            b"IEND" => {
                if size != 0 || end != bytes.len() {
                    return Err(png_error());
                }
                ended = true;
            }
            _ => {}
        }
        offset = end;
    }
    if !ended {
        return Err(png_error());
    }
    if icc && srgb {
        return Err(png_error());
    }
    if declared && (srgb || (!icc && other_color)) {
        return Err(Error::new(
            "PROFILE_CONFLICT",
            "An explicit input profile cannot override tagged PNG color semantics",
        ));
    }
    if icc || declared {
        Ok(Interpretation::ConvertedSrgb)
    } else if srgb {
        Ok(Interpretation::DeclaredSrgb)
    } else if other_color {
        Err(Error::new(
            "UNSUPPORTED",
            "Gamma/chromaticity-tagged input without sRGB requires color conversion",
        ))
    } else if policy == ColorPolicy::AssumeSrgb {
        Ok(Interpretation::AssumedSrgb)
    } else {
        Err(Error::new(
            "COLOR_POLICY_REQUIRED",
            "Untagged PNG requires explicit assume_srgb color policy",
        ))
    }
}
#[derive(Serialize)]
pub struct Imported {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metadata: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub color_conversion: Option<serde_json::Value>,
    pub asset: ImageAsset,
    pub created: bool,
    pub source_format: &'static str,
    pub losses: Vec<&'static str>,
}
pub fn import(source: &Path, root: &Path, policy: ColorPolicy) -> Result<Imported, Error> {
    import_with_profile(source, root, policy, None)
}
pub fn import_with_profile(
    source: &Path,
    root: &Path,
    policy: ColorPolicy,
    declared: Option<&crate::profiles::Profile>,
) -> Result<Imported, Error> {
    absolute(source)?;
    absolute(root)?;
    let bytes = read_bounded(source, MAX_IMPORT_BYTES)?;
    if !bytes.starts_with(b"\x89PNG\r\n\x1a\n") {
        let decoded = crate::image_io::decode(&bytes, policy, declared)?;
        let asset = ImageAsset {
            width: decoded.pixels.width,
            height: decoded.pixels.height,
            sha256: identity(
                decoded.pixels.width,
                decoded.pixels.height,
                &decoded.pixels.rgba,
            ),
            storage: Storage::Stored,
            provenance: Some(Provenance {
                source_profile_sha256: decoded.source_profile_sha256,
                source_sha256: sha256(&bytes),
                interpretation: decoded.interpretation,
            }),
        };
        validate(&asset)?;
        let metadata = decoded
            .metadata
            .or(crate::metadata::recover(&bytes, decoded.format)?);
        let created = publish(&asset, &decoded.pixels.rgba, root)?;
        return Ok(Imported {
            metadata,
            color_conversion: conversion_receipt(&asset),
            asset,
            created,
            source_format: decoded.format,
            losses: decoded.losses,
        });
    }
    let interpretation = preflight(&bytes, policy, declared.is_some())?;
    let mut decoder = png::Decoder::new_with_limits(
        Cursor::new(&bytes),
        png::Limits {
            bytes: 64 * 1024 * 1024,
        },
    );
    decoder.set_ignore_text_chunk(true);
    decoder.set_transformations(png::Transformations::EXPAND);
    let mut reader = decoder.read_info().map_err(|_| png_error())?;
    let profile = reader.info().icc_profile.as_ref().map(|v| v.to_vec());
    if profile.is_some()
        && matches!(
            reader.info().color_type,
            png::ColorType::Grayscale | png::ColorType::GrayscaleAlpha
        )
    {
        return Err(Error::new(
            "UNSUPPORTED",
            "Profile-tagged grayscale samples require the grayscale color pipeline",
        ));
    }
    dimensions(reader.info().width, reader.info().height)?;
    let size = reader
        .output_buffer_size()
        .filter(|s| *s as u64 <= MAX_ASSET_PIXELS * 4)
        .ok_or_else(|| limit("Decoded PNG exceeds allocation limit"))?;
    let mut decoded = vec![0; size];
    let info = reader.next_frame(&mut decoded).map_err(|_| png_error())?;
    reader.finish().map_err(|_| png_error())?;
    if info.bit_depth != png::BitDepth::Eight {
        return Err(Error::new(
            "UNSUPPORTED",
            "PNG normalization did not produce 8-bit channels",
        ));
    }
    decoded.truncate(info.buffer_size());
    let mut rgba = match info.color_type {
        png::ColorType::Rgba => decoded,
        png::ColorType::Rgb => decoded
            .as_chunks::<3>()
            .0
            .iter()
            .flat_map(|p| [p[0], p[1], p[2], 255])
            .collect(),
        png::ColorType::Grayscale => decoded.iter().flat_map(|p| [*p, *p, *p, 255]).collect(),
        png::ColorType::GrayscaleAlpha => decoded
            .as_chunks::<2>()
            .0
            .iter()
            .flat_map(|p| [p[0], p[0], p[0], p[1]])
            .collect(),
        _ => {
            return Err(Error::new(
                "UNSUPPORTED",
                "PNG normalization produced an unsupported color type",
            ));
        }
    };
    let source_profile_sha256 =
        crate::profiles::import(&mut rgba, profile.as_deref(), declared, policy)?;
    let asset = ImageAsset {
        width: info.width,
        height: info.height,
        sha256: identity(info.width, info.height, &rgba),
        storage: Storage::Stored,
        provenance: Some(Provenance {
            source_profile_sha256,
            source_sha256: sha256(&bytes),
            interpretation,
        }),
    };
    validate(&asset)?;
    let metadata = crate::metadata::recover(&bytes, "png")?;
    let created = publish(&asset, &rgba, root)?;
    Ok(Imported {
        metadata,
        color_conversion: conversion_receipt(&asset),
        asset,
        created,
        source_format: "png",
        losses: vec![
            "Recognized Inkbolt descriptions are returned separately as untrusted metadata. Other source metadata is retained only through its byte hash. Density does not change placement, which uses explicit pixel dimensions.",
        ],
    })
}
fn conversion_receipt(asset: &ImageAsset) -> Option<serde_json::Value> {
    let source = asset.provenance.as_ref()?.source_profile_sha256.as_ref()?;
    Some(
        serde_json::json!({"source_profile_sha256":source,"destination":"encoded_srgb_rgba8","intent":"relative_colorimetric","black_point_compensation":false,"alpha":"unchanged","loss":"RGB8 quantization and destination-gamut clipping are not reversible"}),
    )
}
impl Pixels {
    /// Premultiplied bilinear interpolation avoids transparent-color fringes; edges clamp to crop pixels.
    pub fn sample(
        &self,
        crop: Crop,
        point: [f64; 2],
        sampling: Sampling,
    ) -> Result<[f64; 4], Error> {
        self.sample_planned(
            crop,
            point,
            &crate::resample::Plan::new(sampling, [1.0, 1.0])?,
        )
    }
    pub(crate) fn sample_planned(
        &self,
        crop: Crop,
        point: [f64; 2],
        plan: &crate::resample::Plan,
    ) -> Result<[f64; 4], Error> {
        let get = |x: i64, y: i64| {
            let x = x.clamp(crop.x as i64, (crop.x + crop.width - 1) as i64) as usize;
            let y = y.clamp(crop.y as i64, (crop.y + crop.height - 1) as i64) as usize;
            let i = (y * self.width as usize + x) * 4;
            let a = self.rgba[i + 3] as f64 / 255.0;
            [
                self.rgba[i] as f64 / 255.0 * a,
                self.rgba[i + 1] as f64 / 255.0 * a,
                self.rgba[i + 2] as f64 / 255.0 * a,
                a,
            ]
        };
        crate::resample::straight(point, plan, get)
    }

    pub fn cropped(&self, crop: Crop) -> Vec<u8> {
        let mut bytes = Vec::with_capacity(crop.width as usize * crop.height as usize * 4);
        for y in crop.y..crop.y + crop.height {
            let i = (y as usize * self.width as usize + crop.x as usize) * 4;
            bytes.extend_from_slice(&self.rgba[i..i + crop.width as usize * 4]);
        }
        bytes
    }
}

/// Stabilize the discontinuous nearest-pixel decision at integer boundaries.
/// Affine composition/inversion can put an intended integer a few rounding
/// steps below itself. The tolerance is relative to the source coordinate,
/// eight machine epsilons with an absolute floor of eight epsilons.
pub(crate) fn pixel_index(value: f64) -> i64 {
    let integer = value.round();
    let tolerance = 8.0 * f64::EPSILON * value.abs().max(1.0);
    if (value - integer).abs() <= tolerance {
        integer as i64
    } else {
        value.floor() as i64
    }
}
