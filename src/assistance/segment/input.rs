use super::*;
use crate::{
    native_pixels as native,
    sample_store::Region,
    samples::{Channels, Depth},
};

pub(super) fn read(
    document: &Document,
    id: &str,
    requested: Option<Region>,
    root: Option<&Path>,
    work: &mut Work<'_>,
) -> Result<Grid, Error> {
    let item = &document.items[scene::index(document, id)?];
    crate::pixel_warps::reject_native(item)?;
    let typed = matches!(&item.content, Content::StoredSamples { .. })
        || matches!(&item.content, Content::Samples { grid } if grid.depth != Depth::U8);
    if requested.is_none() && !typed {
        return legacy(document, id, root);
    }
    if let Content::Image {
        asset_id,
        width,
        height,
        crop,
        ..
    } = &item.content
    {
        let asset = &document.assets[asset_id];
        let crop = assets::crop(asset.width, asset.height, *crop)?;
        let region = region(crop.width, crop.height, requested)?;
        // The asset loader retains its full verified RGBA source. Large native
        // images should use their block store instead of this legacy asset path.
        let encoded = match &asset.storage {
            assets::Storage::Encoded { data_base64, .. } => data_base64.len() as u64 * 3 / 4,
            _ => 0,
        };
        let memory = admit(
            region,
            asset.width as u64 * asset.height as u64 * 16 + encoded,
        )?;
        native::Budget::prepare(work, asset.width as u64 * asset.height as u64 * 3)?;
        let pixels = assets::load(asset, root)?;
        let mut bytes = Vec::with_capacity(region.width as usize * region.height as usize * 4);
        for y in crop.y + region.y..crop.y + region.y + region.height {
            work.add(region.width as u64 * 4)?;
            let start = (y as usize * pixels.width as usize + (crop.x + region.x) as usize) * 4;
            bytes.extend_from_slice(&pixels.rgba[start..start + region.width as usize * 4]);
        }
        let sx = width / crop.width as f64;
        let sy = height / crop.height as f64;
        return Ok(Grid {
            width: region.width,
            height: region.height,
            bytes,
            transform: [sx, 0.0, 0.0, sy, region.x as f64 * sx, region.y as f64 * sy],
            origin: [region.x, region.y],
            features: None,
            feature_scale: 1,
            analysis: Some(description(
                region,
                8,
                memory,
                json!({"kind":"rgba8_image_asset", "sha256":asset.sha256,"width":asset.width,"height":asset.height,"crop":crop}),
                false,
            )),
        });
    }
    if !matches!(
        item.content,
        Content::Raster { .. } | Content::Samples { .. } | Content::StoredSamples { .. }
    ) {
        return Err(Error::new(
            "UNSUPPORTED",
            "Native region selection requires a pixel layer or a verified image asset",
        ));
    }
    if let Content::Samples { grid } = &item.content
        && grid.profile.is_some()
    {
        return Err(Error::new(
            "PROFILE_CONVERSION_REQUIRED",
            "Local selection requires explicit sample_profile conversion to working sRGB",
        ));
    }
    let spec = native::spec(&item.content)?;
    let region = region(spec.width, spec.height, requested)?;
    let memory = admit(region, native::memory(&item.content))?;
    let mut pixels =
        native::Pixels::new(&item.content, root, "UNSUPPORTED_ASSISTANCE_ENCODING", work)?;
    let n = region.width as usize * region.height as usize;
    let mut bytes = Vec::with_capacity(n * pixels.stride());
    let mut features = Vec::with_capacity(n);
    for y in region.y..region.y + region.height {
        for x in region.x..region.x + region.width {
            work.add(4)?;
            let raw = pixels.raw(x as usize, y as usize, work)?;
            bytes.extend_from_slice(&raw[..pixels.stride()]);
            features.push(native_feature(&raw, spec)?);
        }
    }
    let bits = if spec.depth == Depth::U8 { 8 } else { 16 };
    Ok(Grid {
        width: region.width,
        height: region.height,
        bytes,
        transform: [1.0, 0.0, 0.0, 1.0, region.x as f64, region.y as f64],
        origin: [region.x, region.y],
        features: Some(features),
        feature_scale: if bits == 8 { 1 } else { 257 * 257 },
        analysis: Some(description(
            region,
            bits,
            memory,
            json!({"kind":pixels.identity_kind,"sha256":pixels.identity,"samples":spec}),
            spec.depth == Depth::F32,
        )),
    })
}

fn region(width: u32, height: u32, requested: Option<Region>) -> Result<Region, Error> {
    let r = requested.unwrap_or(Region {
        x: 0,
        y: 0,
        width,
        height,
    });
    if r.width == 0
        || r.height == 0
        || r.x as u64 + r.width as u64 > width as u64
        || r.y as u64 + r.height as u64 > height as u64
    {
        return Err(invalid(
            "Selection region must be nonempty and inside the cropped native grid",
        ));
    }
    size(r.width, r.height)?;
    Ok(r)
}

fn admit(r: Region, source_memory: u64) -> Result<u64, Error> {
    let memory = r.width as u64 * r.height as u64 * limits::WORKING_BYTES_PER_PIXEL
        + limits::FIXED_WORKING_BYTES
        + source_memory;
    if memory > limits::MAX_MEMORY_BYTES {
        return Err(crate::model::limit(
            "Native region selection exceeds its processing memory bound",
        ));
    }
    Ok(memory)
}

fn description(region: Region, bits: u32, memory: u64, source: Value, float: bool) -> Value {
    json!({"mode":"native_region","region":region,"feature_bits":bits,
        "feature_construction":"rounded_premultiplied_encoded_RGB_plus_alpha",
        "energy_scale":if bits==8 {1} else {257*257},"source":source,
        "pixel_hash_kind":"row_major_native_region_samples;RGBA8_for_image_assets",
        "seed_coordinates":"cropped_native_grid","cost_indices":"row_major_region",
        "outside_region":"excluded_from_objective;zero_mask_coverage",
        "processing_memory_bound_bytes":memory,
            "approximation":if float {json!({"method":"exact_binary32_premultiplication_then_u16_feature_rounding",
            "maximum_feature_rounding_error":0.5/65535.0,
            "losses":["float_analysis_feature_quantization"],"source_converted":false})} else {Value::Null}})
}

pub(super) fn native_feature(
    raw: &[u8; 16],
    spec: crate::sample_store::Spec,
) -> Result<[i64; 4], Error> {
    let mut p = [0u64; 4];
    if spec.depth != Depth::F32 {
        for (value, bytes) in p
            .iter_mut()
            .zip(raw.chunks_exact(spec.depth.bytes()))
            .take(spec.channels.count())
        {
            *value = match spec.depth {
                Depth::U8 => bytes[0] as u64,
                Depth::U16 => u16::from_le_bytes(bytes.try_into().unwrap()) as u64,
                Depth::F32 => unreachable!(),
            };
        }
        if spec.channels == Channels::GrayAlpha {
            p = [p[0], p[0], p[0], p[1]];
        }
        let maximum = if spec.depth == Depth::U8 { 255 } else { 65535 };
        return Ok([
            (p[0] * p[3] + maximum / 2) / maximum,
            (p[1] * p[3] + maximum / 2) / maximum,
            (p[2] * p[3] + maximum / 2) / maximum,
            p[3],
        ]
        .map(|v| v as i64));
    }
    let mut f = [0.0; 4];
    for (value, bytes) in f
        .iter_mut()
        .zip(raw.as_chunks::<4>().0)
        .take(spec.channels.count())
    {
        *value = f32::from_le_bytes(*bytes) as f64;
    }
    if spec.channels == Channels::GrayAlpha {
        f = [f[0], f[0], f[0], f[1]];
    }
    if f[3] == 0.0 {
        return Ok([0; 4]);
    }
    if f.iter().any(|v| !v.is_finite() || !(0.0..=1.0).contains(v)) {
        return Err(Error::new(
            "UNSUPPORTED_ASSISTANCE_RANGE",
            "Float selection features require normalized visible samples; convert explicitly before selection",
        ));
    }
    Ok([
        float_feature(f[0], Some(f[3])),
        float_feature(f[1], Some(f[3])),
        float_feature(f[2], Some(f[3])),
        float_feature(f[3], None),
    ])
}

fn float_feature(value: f64, alpha: Option<f64>) -> i64 {
    // Every input is an exact widening of normalized binary32. Retain its
    // rational value so multiplication near a half-feature tie cannot round
    // across the tie in an intermediate floating-point operation.
    let parts = |value: f64| {
        let bits = (value as f32).to_bits();
        let exponent = (bits >> 23) & 255;
        let fraction = bits & 0x7fffff;
        if exponent == 0 {
            (fraction as u128, 149)
        } else {
            ((fraction | 0x800000) as u128, 150 - exponent)
        }
    };
    let (mut numerator, mut shift) = parts(value);
    if let Some(alpha) = alpha {
        let (factor, extra) = parts(alpha);
        numerator *= factor;
        shift += extra;
    }
    numerator *= 65535;
    // The numerator has at most 64 bits. A larger denominator rounds to zero;
    // all other half-up additions and shifts fit the wide intermediate.
    if shift >= 128 {
        0
    } else {
        ((numerator + (1u128 << (shift - 1))) >> shift) as i64
    }
}

fn legacy(document: &Document, id: &str, root: Option<&Path>) -> Result<Grid, Error> {
    let i = scene::index(document, id)?;
    crate::pixel_warps::reject_native(&document.items[i])?;
    match &document.items[i].content {
        Content::Samples { grid } => {
            if grid.profile.is_some() {
                return Err(Error::new(
                    "PROFILE_CONVERSION_REQUIRED",
                    "Local selection requires explicit sample_profile conversion to working sRGB",
                ));
            }
            if grid.depth != crate::samples::Depth::U8 {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "Local selection requires explicit conversion of high-depth samples to encoded eight-bit input",
                ));
            }
            size(grid.width, grid.height)?;
            let data = render::unhex(&grid.data_hex);
            let bytes = match grid.channels {
                crate::samples::Channels::Rgba => data,
                crate::samples::Channels::GrayAlpha => data
                    .as_chunks::<2>()
                    .0
                    .iter()
                    .flat_map(|p| [p[0], p[0], p[0], p[1]])
                    .collect(),
            };
            Ok(Grid {
                width: grid.width,
                height: grid.height,
                bytes,
                transform: identity(),
                origin: [0, 0],
                features: None,
                feature_scale: 1,
                analysis: None,
            })
        }
        Content::Raster {
            width,
            height,
            rgba_hex,
            ..
        } => {
            size(*width, *height)?;
            Ok(Grid {
                width: *width,
                height: *height,
                bytes: render::unhex(rgba_hex),
                transform: identity(),
                origin: [0, 0],
                features: None,
                feature_scale: 1,
                analysis: None,
            })
        }
        Content::Image {
            asset_id,
            width,
            height,
            crop,
            ..
        } => {
            let asset = &document.assets[asset_id];
            let crop = assets::crop(asset.width, asset.height, *crop)?;
            size(crop.width, crop.height)?;
            let pixels = assets::load(asset, root)?;
            let mut bytes = Vec::with_capacity(crop.width as usize * crop.height as usize * 4);
            for y in crop.y..crop.y + crop.height {
                let start = (y as usize * pixels.width as usize + crop.x as usize) * 4;
                bytes.extend_from_slice(&pixels.rgba[start..start + crop.width as usize * 4]);
            }
            Ok(Grid {
                width: crop.width,
                height: crop.height,
                bytes,
                origin: [0, 0],
                features: None,
                feature_scale: 1,
                analysis: None,
                transform: [
                    width / crop.width as f64,
                    0.0,
                    0.0,
                    height / crop.height as f64,
                    0.0,
                    0.0,
                ],
            })
        }
        _ => Err(Error::new(
            "UNSUPPORTED",
            "Local selection requires an inline eight-bit pixel layer or a verified RGBA8 image asset",
        )),
    }
}
