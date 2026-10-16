//! Bounded native-depth image import into a new editable raster snapshot.
use crate::{
    Error,
    assets::{self, ColorPolicy, Interpretation},
    model::*,
    samples::{Channels, Depth, Grid},
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    io::{BufReader, Read, Seek},
    path::{Path, PathBuf},
};
use tiff::tags::Tag;
mod pixels;
mod png_passes;
mod source;
mod tiff_rows;
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Policy {
    #[default]
    RequireSrgb,
    AssumeSrgb,
    ConvertSrgb,
    AssumeLinearSrgb,
}

pub use crate::limits::sample_import::MAX_NATIVE_DECODED_BYTES;
fn decoder_limit(max_pixels: usize) -> usize {
    if max_pixels > MAX_STORED_PIXELS {
        crate::limits::sample_import::MAX_NATIVE_CODEC_BYTES
    } else {
        crate::limits::sample_import::MAX_INLINE_DECODER_BYTES
    }
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct NativeStore {
    pub store_root: PathBuf,
    /// New imports use block manifests (2); explicitly select 1 for legacy patches.
    #[serde(default = "default_storage_version")]
    pub storage_version: u32,
}
fn default_storage_version() -> u32 {
    2
}
struct DecodedSource {
    width: u32,
    height: u32,
    depth: Depth,
    channels: Channels,
    pixels: DecodedPixels,
}
enum DecodedPixels {
    Bytes(Vec<u8>),
    Tiles(pixels::Prepared),
}

fn malformed() -> Error {
    Error::new(
        "INVALID_IMAGE",
        "Sample image is truncated, malformed or inconsistent",
    )
}
fn unsupported(message: &str) -> Error {
    Error::new("UNSUPPORTED", message)
}
fn tiff_error(e: tiff::TiffError) -> Error {
    match e {
        tiff::TiffError::LimitsExceeded => limit("Sample image decoder allocation limit exceeded"),
        tiff::TiffError::UnsupportedError(_) => unsupported("TIFF sample encoding is unsupported"),
        _ => malformed(),
    }
}
fn size(w: u32, h: u32, max_pixels: usize) -> Result<(), Error> {
    assets::dimensions(w, h)?;
    if w as u64 * h as u64 > max_pixels as u64 {
        return Err(limit(
            "Sample import exceeds the selected storage pixel budget",
        ));
    }
    Ok(())
}
fn png<R: Read + Seek>(
    input: R,
    length: u64,
    policy: ColorPolicy,
    max_pixels: usize,
    staging: Option<&source::Budget>,
    control: &crate::control::Control,
) -> Result<(DecodedSource, Interpretation, Value), Error> {
    let native_store = staging.is_some();
    let mut input =
        BufReader::with_capacity(crate::limits::sample_import::INPUT_BUFFER_BYTES, input);
    let interpretation =
        assets::preflight_samples_reader(&mut input, length, policy, max_pixels, control)?;
    input.rewind().map_err(|_| malformed())?;
    let mut decoder = png::Decoder::new_with_limits(
        input,
        png::Limits {
            bytes: decoder_limit(max_pixels),
        },
    );
    decoder.ignore_checksums(false);
    decoder.set_ignore_text_chunk(true);
    decoder.set_transformations(png::Transformations::EXPAND);
    let mut reader = decoder.read_info().map_err(|_| malformed())?;
    let input_depth = reader.info().bit_depth as u8;
    let input_color = format!("{:?}", reader.info().color_type);
    size(reader.info().width, reader.info().height, max_pixels)?;
    let count = reader
        .output_buffer_size()
        .filter(|n| *n <= max_pixels.saturating_mul(8).min(MAX_NATIVE_DECODED_BYTES))
        .ok_or_else(|| limit("Sample PNG exceeds decoded byte limit"))?;
    let width = reader.info().width;
    let height = reader.info().height;
    let (color, bit_depth) = reader.output_color_type();
    let depth = match bit_depth {
        png::BitDepth::Eight => Depth::U8,
        png::BitDepth::Sixteen => Depth::U16,
        _ => return Err(unsupported("Expanded PNG requires 8-bit or 16-bit samples")),
    };
    let n = match color {
        png::ColorType::Grayscale => 1,
        png::ColorType::GrayscaleAlpha => 2,
        png::ColorType::Rgb => 3,
        png::ColorType::Rgba => 4,
        _ => return Err(malformed()),
    };
    let channels = if n <= 2 {
        Channels::GrayAlpha
    } else {
        Channels::Rgba
    };
    let native_size = width as usize * height as usize * channels.count() * depth.bytes();
    if native_size > MAX_NATIVE_DECODED_BYTES {
        return Err(limit(&format!(
            "Native image channels exceed the {} MiB private pixel extent budget",
            MAX_NATIVE_DECODED_BYTES / (1024 * 1024)
        )));
    }
    let interlaced = reader.info().interlaced;
    let pixels = if native_store {
        let spec = crate::sample_store::Spec {
            width,
            height,
            depth,
            channels,
            encoding: crate::hdr::Encoding::EncodedSrgb,
        };
        let candidate = if interlaced {
            png_passes::decode(&mut reader, spec, n, staging.unwrap(), control)?
        } else {
            pixels::Builder::from_rows(spec, staging.unwrap(), control, |_, destination| {
                let row = reader
                    .next_row()
                    .map_err(|_| malformed())?
                    .ok_or_else(malformed)?;
                normalize_png(row.data(), destination, depth, n)
            })?
        };
        if !interlaced && reader.next_row().map_err(|_| malformed())?.is_some() {
            return Err(malformed());
        }
        DecodedPixels::Tiles(candidate)
    } else {
        let mut data = vec![0; count];
        let info = reader.next_frame(&mut data).map_err(|_| malformed())?;
        data.truncate(info.buffer_size());
        let mut native = vec![0; native_size];
        normalize_png(&data, &mut native, depth, n)?;
        DecodedPixels::Bytes(native)
    };
    reader.finish().map_err(|_| malformed())?;
    control.check()?;
    Ok((
        DecodedSource {
            width,
            height,
            depth,
            channels,
            pixels,
        },
        interpretation,
        json!({"input_depth":input_depth,"input_color":input_color,"decode_storage":if !native_store {"complete_decoded_frame"} else if interlaced {"adam7_passes_to_native_blocks"} else {"rows_to_native_blocks"},"normalization":"big_endian_to_little_endian;palette_and_low_bits_expanded;missing_alpha_opaque"}),
    ))
}
fn normalize_png(
    source: &[u8],
    destination: &mut [u8],
    depth: Depth,
    n: usize,
) -> Result<(), Error> {
    let unit = depth.bytes();
    let output_channels = if n <= 2 { 2 } else { 4 };
    if !source.len().is_multiple_of(n * unit)
        || source.len() / (n * unit) * output_channels * unit != destination.len()
    {
        return Err(malformed());
    }
    for (src, dst) in source
        .chunks_exact(n * unit)
        .zip(destination.chunks_exact_mut(output_channels * unit))
    {
        for (a, b) in src.chunks_exact(unit).zip(dst.chunks_exact_mut(unit)) {
            if depth == Depth::U16 {
                b.copy_from_slice(&[a[1], a[0]]);
            } else {
                b[0] = a[0];
            }
        }
        if n == 1 || n == 3 {
            dst[n * unit..].fill(255);
        }
    }
    Ok(())
}
fn tiff<R: Read + Seek>(
    input: R,
    policy: ColorPolicy,
    max_pixels: usize,
    native_encoding: Option<(crate::hdr::Encoding, &source::Budget)>,
    control: &crate::control::Control,
) -> Result<(DecodedSource, Interpretation, Value), Error> {
    let mut limits = tiff::decoder::Limits::default();
    limits.decoding_buffer_size = decoder_limit(max_pixels);
    limits.intermediate_buffer_size = decoder_limit(max_pixels);
    let mut decoder = tiff::decoder::Decoder::new(BufReader::with_capacity(
        crate::limits::sample_import::INPUT_BUFFER_BYTES,
        input,
    ))
    .map_err(tiff_error)?
    .with_limits(limits);
    let (w, h) = decoder.dimensions().map_err(tiff_error)?;
    size(w, h, max_pixels)?;
    if decoder.more_images() {
        return Err(unsupported(
            "Sample import requires a single TIFF image; sequences need an explicit importer",
        ));
    }
    for tag in [301, 318, 319, 330, 34665, 34675, 50706] {
        if decoder
            .find_tag(Tag::from_u16_exhaustive(tag))
            .map_err(tiff_error)?
            .is_some()
        {
            return Err(unsupported(
                "Sample TIFF import does not support embedded profiles, transfer functions, alternate chromaticities, raw or nested directories",
            ));
        }
    }
    if policy != ColorPolicy::AssumeSrgb {
        return Err(Error::new(
            "COLOR_POLICY_REQUIRED",
            "Untagged TIFF samples require explicit assume_srgb policy",
        ));
    }
    if decoder
        .find_tag_unsigned::<u16>(Tag::Orientation)
        .map_err(tiff_error)?
        .unwrap_or(1)
        != 1
    {
        return Err(unsupported(
            "Sample TIFF import requires top-left orientation",
        ));
    }
    let compression = decoder
        .find_tag_unsigned::<u16>(Tag::Compression)
        .map_err(tiff_error)?
        .unwrap_or(1);
    if ![1, 5, 8, 32946, 32773].contains(&compression) {
        return Err(unsupported(
            "Sample TIFF import supports uncompressed, LZW, Deflate and PackBits",
        ));
    }
    let photo = decoder
        .find_tag_unsigned::<u16>(Tag::PhotometricInterpretation)
        .map_err(tiff_error)?
        .ok_or_else(malformed)?;
    let n = decoder
        .find_tag_unsigned::<u16>(Tag::SamplesPerPixel)
        .map_err(tiff_error)?
        .unwrap_or(1) as usize;
    let channels = match (photo, n) {
        (0, 1) | (1, 1 | 2) => Channels::GrayAlpha,
        (2, 3 | 4) => Channels::Rgba,
        _ => {
            return Err(unsupported(
                "Sample TIFF import requires grayscale/RGB with optional straight alpha",
            ));
        }
    };
    let bits = decoder
        .find_tag_unsigned_vec::<u16>(Tag::BitsPerSample)
        .map_err(tiff_error)?
        .unwrap_or_else(|| vec![1]);
    let formats = decoder
        .find_tag_unsigned_vec::<u16>(Tag::SampleFormat)
        .map_err(tiff_error)?
        .unwrap_or_else(|| vec![1]);
    if ![1, n].contains(&bits.len()) || ![1, n].contains(&formats.len()) {
        return Err(malformed());
    }
    if bits.iter().any(|b| *b != bits[0]) || formats.iter().any(|f| *f != formats[0]) {
        return Err(unsupported(
            "Mixed TIFF sample formats/depths are not supported",
        ));
    }
    let depth = match (bits[0], formats[0]) {
        (8, 1) => Depth::U8,
        (16, 1) => Depth::U16,
        (32, 3) => Depth::F32,
        _ => {
            return Err(unsupported(
                "Sample TIFF import requires unsigned 8/16 or IEEE binary32 components",
            ));
        }
    };
    let extra = decoder
        .find_tag_unsigned_vec::<u16>(Tag::ExtraSamples)
        .map_err(tiff_error)?
        .unwrap_or_default();
    if ((n == 2 || n == 4) && extra != [2]) || ((n == 1 || n == 3) && !extra.is_empty()) {
        return Err(unsupported(
            "Sample TIFF alpha must be explicitly unassociated",
        ));
    }
    let planar = decoder
        .find_tag_unsigned::<u16>(Tag::PlanarConfiguration)
        .map_err(tiff_error)?
        .unwrap_or(1);
    if ![1, 2].contains(&planar) {
        return Err(malformed());
    }
    let count = w as usize * h as usize;
    let unit = depth.bytes();
    if count * channels.count() * unit > MAX_NATIVE_DECODED_BYTES {
        return Err(limit(&format!(
            "Native image channels exceed the {} MiB private pixel extent budget",
            MAX_NATIVE_DECODED_BYTES / (1024 * 1024)
        )));
    }
    if let Some((encoding, budget)) = native_encoding {
        let spec = crate::sample_store::Spec {
            width: w,
            height: h,
            depth,
            channels,
            encoding,
        };
        let pixels = tiff_rows::decode(&mut decoder, spec, n, planar == 2, budget, control)?;
        return Ok((
            DecodedSource {
                width: w,
                height: h,
                depth,
                channels,
                pixels: DecodedPixels::Tiles(pixels),
            },
            Interpretation::AssumedSrgb,
            json!({"compression":compression,"planar_configuration":planar,"input_photometric":photo,
                "decode_storage":"chunk_bands_to_native_blocks",
                "normalization":"native_decoded_endian_to_little_endian;planes_interleaved;white_zero_inverted_by_codec;missing_alpha_opaque"}),
        ));
    }
    let mut data = vec![0; count * n * unit];
    if decoder.get_chunk_type() == tiff::decoder::ChunkType::Tile {
        let (cw, ch) = decoder.chunk_dimensions();
        if cw == 0 || ch == 0 {
            return Err(malformed());
        }
        let across = w.div_ceil(cw);
        let per_plane = across * h.div_ceil(ch);
        let planes = if planar == 2 { n } else { 1 };
        let tile_samples = if planar == 2 { 1 } else { n };
        let tiles = per_plane as usize * planes;
        if decoder.tile_count().map_err(tiff_error)? as usize != tiles {
            return Err(malformed());
        }
        let stride = cw as u64 * tile_samples as u64 * unit as u64;
        let padded = stride
            .checked_mul(ch as u64)
            .and_then(|v| v.checked_mul(tiles as u64))
            .ok_or_else(|| limit("Sample TIFF padded tile work exceeds limit"))?;
        if padded > crate::limits::sample_import::MAX_TIFF_PADDED_BYTES {
            return Err(limit(&format!(
                "Sample TIFF padded tile work exceeds {} MiB",
                crate::limits::sample_import::MAX_TIFF_PADDED_BYTES / (1024 * 1024)
            )));
        }
        let stride = stride as usize;
        let mut tile = tiff::decoder::DecodingResult::U8(Vec::new());
        for index in 0..tiles {
            // Decode full padded rows. This avoids a locked-codec LZW partial-read
            // failure when a compressed code crosses the cropped right edge.
            decoder
                .read_chunk_to_buffer(&mut tile, index as u32, stride)
                .map_err(tiff_error)?;
            let mut buffer = tile.as_buffer(0);
            let bytes = buffer.as_bytes_mut();
            let plane = index / per_plane as usize;
            let region = index % per_plane as usize;
            let x = (region % across as usize) * cw as usize;
            let y = (region / across as usize) * ch as usize;
            let width = (w as usize - x).min(cw as usize);
            let height = (h as usize - y).min(ch as usize);
            let used = width * tile_samples * unit;
            for row in 0..height {
                let dest = (plane * count + (y + row) * w as usize + x) * tile_samples * unit;
                data[dest..dest + used].copy_from_slice(&bytes[row * stride..row * stride + used]);
            }
        }
    } else {
        // Explicit complete allocation reads every plane, unlike the legacy read_image API.
        decoder.read_image_bytes(&mut data).map_err(tiff_error)?;
    }
    let mut native = Vec::with_capacity(count * channels.count() * unit);
    for i in 0..count {
        for c in 0..n {
            let at = (if planar == 2 {
                c * count + i
            } else {
                i * n + c
            }) * unit;
            let value = &data[at..at + unit];
            match depth {
                Depth::U8 => native.push(value[0]),
                Depth::U16 => {
                    native.extend(u16::from_ne_bytes(value.try_into().unwrap()).to_le_bytes())
                }
                Depth::F32 => {
                    native.extend(f32::from_ne_bytes(value.try_into().unwrap()).to_le_bytes())
                }
            }
        }
        if n == 1 || n == 3 {
            match depth {
                Depth::U8 => native.push(255),
                Depth::U16 => native.extend(u16::MAX.to_le_bytes()),
                Depth::F32 => native.extend(1.0_f32.to_le_bytes()),
            }
        }
    }
    Ok((
        DecodedSource {
            width: w,
            height: h,
            depth,
            channels,
            pixels: DecodedPixels::Bytes(native),
        },
        Interpretation::AssumedSrgb,
        json!({"compression":compression,"planar_configuration":planar,"input_photometric":photo,"decode_storage":"complete_decoded_frame","normalization":"native_decoded_endian_to_little_endian;planes_interleaved;white_zero_inverted_by_codec;missing_alpha_opaque"}),
    ))
}
pub fn import(
    source: &Path,
    id: String,
    resolution_ppi: f64,
    selected: Policy,
) -> Result<Value, Error> {
    import_with_storage(
        source,
        id,
        resolution_ppi,
        selected,
        None,
        &crate::control::Control::default(),
    )
}
pub fn import_with_storage(
    source: &Path,
    id: String,
    resolution_ppi: f64,
    selected: Policy,
    storage: Option<&NativeStore>,
    control: &crate::control::Control,
) -> Result<Value, Error> {
    control.check()?;
    control.check_path(source)?;
    if let Some(storage) = storage {
        if !matches!(storage.storage_version, 1 | 2) {
            return Err(Error::new(
                "INVALID_REQUEST",
                "Native import storage_version must be 1 (legacy patches) or 2 (block manifests)",
            ));
        }
        assets::absolute(&storage.store_root)?;
        control.check_path(&storage.store_root)?;
    }
    let max_pixels = if storage.is_some() {
        crate::sample_store::MAX_PIXELS as usize
    } else {
        MAX_STORED_PIXELS
    };
    let linear = matches!(selected, Policy::AssumeLinearSrgb);
    let encoding = if linear {
        crate::hdr::Encoding::LinearSrgb
    } else {
        crate::hdr::Encoding::EncodedSrgb
    };
    let policy = match selected {
        Policy::RequireSrgb => ColorPolicy::RequireSrgb,
        Policy::AssumeSrgb | Policy::AssumeLinearSrgb => ColorPolicy::AssumeSrgb,
        Policy::ConvertSrgb => ColorPolicy::ConvertSrgb,
    };
    assets::absolute(source)?;
    if policy == ColorPolicy::ConvertSrgb {
        return Err(unsupported(
            "High-depth profile conversion is not implemented; sample import cannot use an RGB8 conversion",
        ));
    }
    let mut captured = source::Source::open(source, storage.is_some(), control)?;
    let mut signature = [0; 8];
    let signature_len = captured.bytes.min(signature.len());
    captured
        .reader
        .read_exact(&mut signature[..signature_len])
        .map_err(|_| malformed())?;
    captured.reader.rewind().map_err(|_| malformed())?;
    let (decoded, interpretation, normalization, format) =
        if signature_len == 8 && &signature == b"\x89PNG\r\n\x1a\n" {
            if linear {
                return Err(unsupported(
                    "Linear HDR sample import requires an explicit binary32 TIFF source",
                ));
            }
            let (g, i, n) = png(
                &mut captured.reader,
                captured.bytes as u64,
                policy,
                max_pixels,
                captured.staging.as_ref(),
                control,
            )?;
            (g, i, n, "png")
        } else if signature[..signature_len].starts_with(b"II")
            || signature[..signature_len].starts_with(b"MM")
        {
            let (g, i, n) = tiff(
                &mut captured.reader,
                policy,
                max_pixels,
                captured.staging.as_ref().map(|budget| (encoding, budget)),
                control,
            )?;
            (g, i, n, "tiff")
        } else {
            return Err(unsupported("Sample import requires PNG or TIFF"));
        };
    control.check()?;
    let spec = crate::sample_store::Spec {
        width: decoded.width,
        height: decoded.height,
        depth: decoded.depth,
        channels: decoded.channels,
        encoding,
    };
    let decoded_bytes = spec.byte_len()?;
    let candidate;
    let content = if let Some(storage) = storage {
        candidate = Some(match decoded.pixels {
            DecodedPixels::Tiles(candidate) => candidate,
            DecodedPixels::Bytes(bytes) => pixels::Builder::from_rows(
                spec,
                captured.staging.as_ref().ok_or_else(malformed)?,
                control,
                |y, row| {
                    let start = y as usize * row.len();
                    row.copy_from_slice(&bytes[start..start + row.len()]);
                    Ok(())
                },
            )?,
        });
        Content::StoredSamples {
            grid: Box::new(crate::stored_samples::Grid {
                storage_version: storage.storage_version,
                base: candidate.as_ref().unwrap().manifest().clone(),
                patches: Vec::new(),
                profile: None,
                sampling: Default::default(),
                staged: None,
            }),
        }
    } else {
        candidate = None;
        let DecodedPixels::Bytes(bytes) = decoded.pixels else {
            return Err(malformed());
        };
        let grid = Grid {
            profile: None,
            encoding,
            width: decoded.width,
            height: decoded.height,
            depth: decoded.depth,
            channels: decoded.channels,
            data_hex: crate::render::hex(&bytes),
            sampling: Default::default(),
        };
        grid.validate()?;
        Content::Samples {
            grid: Box::new(grid),
        }
    };
    let interpretation = if linear {
        json!("assumed_linear_srgb")
    } else {
        json!(interpretation)
    };
    let document:Document=serde_json::from_value(json!({"schema_version":2,"id":id,"kind":"raster","width":spec.width,"height":spec.height,"resolution_ppi":resolution_ppi,"color_space":if linear {"linear_srgb"}else{"srgb"},"items":[{"id":"pixels","content":content}]})).map_err(|_|malformed())?;
    crate::validate(&document)?;
    let metadata = crate::metadata::recover_reader(
        &mut captured.reader,
        captured.bytes as u64,
        format,
        control,
    )?;
    drop(captured.reader);
    control.check()?;
    let mut result = json!({"document":document,"source_sha256":captured.sha256,"source_bytes":captured.bytes,"source_format":format,"interpretation":interpretation,"normalization":normalization,"metadata":metadata,"source_changed":false,"losses":["Returns a new inline sample document without changing the source file. Palette/low-bit PNG samples expand to explicit channels, missing alpha becomes opaque, TIFF planes interleave and white-is-zero normalizes. Source descriptions remain separate untrusted metadata; source density does not override explicit document resolution. Explicit assume_linear_srgb imports finite signed binary32 TIFF radiance. Profiles, orientation transforms, associated alpha and multi-image TIFF remain unsupported."]});
    if let (Some(storage), Some(candidate)) = (storage, candidate) {
        let publication = candidate.publish(&storage.store_root, control)?;
        result["storage"] = json!({"kind":"native_tiles","store_root":storage.store_root,"manifest_sha256":publication.manifest.sha256,
            "created_tiles":publication.created_tiles,"existing_tiles":publication.existing_tiles,"decoded_bytes":decoded_bytes});
        if storage.storage_version == 1 {
            result["losses"][0] = json!(
                "Returns a new native stored-sample document with immutable base blocks and exact retained patch edits. Original source bytes are unchanged. Profiles, orientation transforms, associated alpha and multi-image TIFF remain unsupported. Metadata remains separate; explicit resolution governs document size."
            );
        } else {
            result["storage"]["storage_version"] = json!(2);
            result["losses"][0] = json!(
                "Returns a new native block-manifest document (storage version 2). Edits publish complete immutable replacement blocks before committing the current manifest; old blocks and source bytes remain unchanged. Profiles, orientation transforms, associated alpha and multi-image TIFF remain unsupported. Metadata remains separate; explicit resolution governs document size."
            );
        }
    }
    Ok(result)
}
