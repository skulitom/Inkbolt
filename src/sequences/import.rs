use super::*;
use crate::assets::{ColorPolicy, ImageAsset, Interpretation, Provenance, Storage};
use std::{
    collections::BTreeMap,
    io::Cursor,
    path::{Path, PathBuf},
};

#[derive(Clone, Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ImageFrame {
    pub source_path: PathBuf,
    pub delay: Delay,
}
#[derive(Clone, Debug, Deserialize, JsonSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Source {
    Gif {
        source_path: PathBuf,
        #[serde(default)]
        background: GifBackground,
    },
    Apng {
        source_path: PathBuf,
        #[serde(default)]
        compositing_space: CompositingSpace,
    },
    Images {
        frames: Vec<ImageFrame>,
        #[serde(default)]
        plays: u32,
    },
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum CompositingSpace {
    #[default]
    LinearSrgb,
    EncodedSrgb,
}
#[derive(Clone, Copy)]
struct Rectangle {
    width: u32,
    height: u32,
    x: u32,
    y: u32,
    delay: Delay,
    dispose: u8,
    blend: u8,
}
struct Plan {
    width: u32,
    height: u32,
    plays: u32,
    poster: bool,
    frames: Vec<Rectangle>,
}
fn malformed() -> Error {
    Error::new(
        "INVALID_SEQUENCE",
        "Animated PNG framing or frame data is invalid",
    )
}
fn u32_at(p: &[u8], at: usize) -> u32 {
    u32::from_be_bytes(p[at..at + 4].try_into().unwrap())
}
fn preflight(bytes: &[u8]) -> Result<Plan, Error> {
    // Complete chunk lengths and CRCs have already been checked by the PNG preflight.
    let width = u32_at(bytes, 16);
    let height = u32_at(bytes, 20);
    let mut count = None;
    let mut plays = 0;
    let mut seq = 0;
    let mut frames = vec![];
    let mut idat = false;
    let mut poster = true;
    let mut frame_data = false;
    let mut in_idat = false;
    let mut idat_ended = false;
    let mut at = 8;
    while at < bytes.len() {
        let size = u32_at(bytes, at) as usize;
        let kind = &bytes[at + 4..at + 8];
        let p = &bytes[at + 8..at + 8 + size];
        if in_idat && kind != b"IDAT" {
            in_idat = false;
            idat_ended = true;
        }
        match kind {
            b"acTL" => {
                if size != 8 || count.is_some() || idat {
                    return Err(malformed());
                }
                let n = u32_at(p, 0) as usize;
                if n == 0 || n > MAX_FRAMES {
                    return Err(limit("Animated PNG requires 1..256 frames"));
                }
                count = Some(n);
                plays = u32_at(p, 4);
            }
            b"fcTL" => {
                if count.is_none()
                    || size != 26
                    || u32_at(p, 0) != seq
                    || (!frames.is_empty() && !frame_data)
                {
                    return Err(malformed());
                }
                seq += 1;
                frame_data = false;
                let r = Rectangle {
                    width: u32_at(p, 4),
                    height: u32_at(p, 8),
                    x: u32_at(p, 12),
                    y: u32_at(p, 16),
                    delay: Delay {
                        numerator: u16::from_be_bytes(p[20..22].try_into().unwrap()),
                        denominator: u16::from_be_bytes(p[22..24].try_into().unwrap()),
                    },
                    dispose: p[24],
                    blend: p[25],
                };
                if r.width == 0
                    || r.height == 0
                    || r.x as u64 + r.width as u64 > width as u64
                    || r.y as u64 + r.height as u64 > height as u64
                    || r.dispose > 2
                    || r.blend > 1
                {
                    return Err(malformed());
                }
                if !idat {
                    if !frames.is_empty() || (r.width, r.height, r.x, r.y) != (width, height, 0, 0)
                    {
                        return Err(malformed());
                    }
                    poster = false;
                }
                frames.push(r);
                if frames.len() > count.unwrap() {
                    return Err(malformed());
                }
            }
            b"IDAT" => {
                if count.is_none() || idat_ended {
                    return Err(malformed());
                }
                idat = true;
                in_idat = true;
                if !poster {
                    frame_data = true;
                }
            }
            b"fdAT" => {
                if !idat
                    || frames.is_empty()
                    || (!poster && frames.len() == 1)
                    || size < 4
                    || u32_at(p, 0) != seq
                {
                    return Err(malformed());
                }
                seq += 1;
                frame_data = true;
            }
            _ => {}
        }
        at += size + 12;
    }
    if !idat || count != Some(frames.len()) || !frame_data {
        return Err(malformed());
    }
    if width as u64 * height as u64 * (frames.len() as u64 + u64::from(poster)) > MAX_PIXELS {
        return Err(limit("Decoded sequence exceeds its aggregate pixel limit"));
    }
    Ok(Plan {
        width,
        height,
        plays,
        poster,
        frames,
    })
}
fn rgba(info: &png::OutputInfo, bytes: &[u8], stride: usize) -> Result<Vec<u8>, Error> {
    if info.bit_depth != png::BitDepth::Eight {
        return Err(Error::new(
            "UNSUPPORTED",
            "Frame exchange currently requires samples expandable to RGBA8",
        ));
    }
    // The locked decoder uses full-canvas stride for interlaced subframes.
    // Normalize only the written rows; padding can contain earlier frame bytes.
    let packed = (0..info.height as usize)
        .flat_map(|y| {
            bytes[y * stride..y * stride + info.line_size]
                .iter()
                .copied()
        })
        .collect::<Vec<_>>();
    let b = packed.as_slice();
    Ok(match info.color_type {
        png::ColorType::Rgba => b.to_vec(),
        png::ColorType::Rgb => b
            .as_chunks::<3>()
            .0
            .iter()
            .flat_map(|c| [c[0], c[1], c[2], 255])
            .collect(),
        png::ColorType::Grayscale => b.iter().flat_map(|v| [*v, *v, *v, 255]).collect(),
        png::ColorType::GrayscaleAlpha => b
            .as_chunks::<2>()
            .0
            .iter()
            .flat_map(|v| [v[0], v[0], v[0], v[1]])
            .collect(),
        _ => return Err(malformed()),
    })
}
fn composite(
    canvas: &mut [u8],
    source: &[u8],
    r: Rectangle,
    width: u32,
    space: CompositingSpace,
    control: &control::Control,
) -> Result<(), Error> {
    for row in 0..r.height as usize {
        control.check()?;
        for x in 0..r.width as usize {
            let a = (row * r.width as usize + x) * 4;
            let b = ((row + r.y as usize) * width as usize + x + r.x as usize) * 4;
            let s = &source[a..a + 4];
            let d = &mut canvas[b..b + 4];
            if r.blend == 0 {
                d.copy_from_slice(s);
                continue;
            }
            let sa = u32::from(s[3]);
            let da = u32::from(d[3]);
            let alpha = sa * 255 + da * (255 - sa);
            if alpha == 0 {
                d.fill(0);
                continue;
            }
            for c in 0..3 {
                d[c] = match space {
                    CompositingSpace::EncodedSrgb => {
                        let numerator =
                            u32::from(s[c]) * sa * 255 + u32::from(d[c]) * da * (255 - sa);
                        ((numerator + alpha / 2) / alpha) as u8
                    }
                    CompositingSpace::LinearSrgb => {
                        let front = crate::hdr::decode(f64::from(s[c]) / 255.0);
                        let back = crate::hdr::decode(f64::from(d[c]) / 255.0);
                        let light = (front * f64::from(sa * 255)
                            + back * f64::from(da * (255 - sa)))
                            / f64::from(alpha);
                        (crate::hdr::encode(light).clamp(0.0, 1.0) * 255.0).round() as u8
                    }
                };
            }
            d[3] = ((alpha + 127) / 255) as u8;
        }
    }
    Ok(())
}
struct Prepared {
    width: u32,
    height: u32,
    plays: u32,
    frames: Vec<(ImageAsset, Delay)>,
    poster: Option<ImageAsset>,
    receipts: Vec<Value>,
    pending: BTreeMap<String, Vec<u8>>,
}
fn descriptor(
    width: u32,
    height: u32,
    rgba: &[u8],
    source: &str,
    interpretation: Interpretation,
) -> ImageAsset {
    ImageAsset {
        width,
        height,
        sha256: assets::identity(width, height, rgba),
        storage: Storage::Stored,
        provenance: Some(Provenance {
            source_sha256: source.into(),
            source_profile_sha256: None,
            interpretation,
        }),
    }
}
fn apng(
    path: &Path,
    policy: ColorPolicy,
    space: CompositingSpace,
    control: &control::Control,
) -> Result<Prepared, Error> {
    assets::absolute(path)?;
    control.check()?;
    let bytes = assets::read_bounded(path, assets::MAX_IMPORT_BYTES)?;
    let interpretation = assets::preflight_sequence(&bytes, policy)?;
    let plan = preflight(&bytes)?;
    if plan.width as u64 * plan.height as u64 > crate::render::MAX_RENDER_PIXELS {
        return Err(limit("Animation canvas exceeds the render pixel limit"));
    }
    let mut decoder = png::Decoder::new_with_limits(
        Cursor::new(&bytes),
        png::Limits {
            bytes: 64 * 1024 * 1024,
        },
    );
    decoder.set_ignore_text_chunk(true);
    decoder.set_transformations(png::Transformations::EXPAND);
    let mut reader = decoder.read_info().map_err(|_| malformed())?;
    let mut buffer = vec![0; reader.output_buffer_size().ok_or_else(malformed)?];
    let source = assets::sha256(&bytes);
    let mut pending = BTreeMap::new();
    let mut poster = None;
    if plan.poster {
        let info = reader.next_frame(&mut buffer).map_err(|_| malformed())?;
        if (info.width, info.height) != (plan.width, plan.height) {
            return Err(malformed());
        }
        let stride = if reader.info().interlaced {
            reader.output_line_size(plan.width).ok_or_else(malformed)?
        } else {
            info.line_size
        };
        let pixels = rgba(&info, &buffer, stride)?;
        let asset = descriptor(plan.width, plan.height, &pixels, &source, interpretation);
        pending.insert(asset.sha256.clone(), pixels);
        poster = Some(asset);
    }
    let mut canvas = vec![0; plan.width as usize * plan.height as usize * 4];
    let mut frames = vec![];
    let mut receipts = vec![];
    for (index, r) in plan.frames.into_iter().enumerate() {
        control.check()?;
        let info = reader.next_frame(&mut buffer).map_err(|_| malformed())?;
        if (info.width, info.height) != (r.width, r.height) {
            return Err(malformed());
        }
        let stride = if reader.info().interlaced {
            reader.output_line_size(plan.width).ok_or_else(malformed)?
        } else {
            info.line_size
        };
        let pixels = rgba(&info, &buffer, stride)?;
        let previous = if r.dispose == 2 {
            Some(canvas.clone())
        } else {
            None
        };
        composite(&mut canvas, &pixels, r, plan.width, space, control)?;
        let asset = descriptor(plan.width, plan.height, &canvas, &source, interpretation);
        pending
            .entry(asset.sha256.clone())
            .or_insert_with(|| canvas.clone());
        frames.push((asset, r.delay));
        receipts.push(json!({"index":index,"source_rectangle":[r.x,r.y,r.width,r.height],"delay":r.delay,"blend":r.blend,"disposal":r.dispose,"rgba_sha256":assets::sha256(&canvas)}));
        match r.dispose {
            1 => {
                for y in r.y..r.y + r.height {
                    let begin = (y as usize * plan.width as usize + r.x as usize) * 4;
                    canvas[begin..begin + r.width as usize * 4].fill(0);
                }
            }
            2 => canvas = previous.unwrap(),
            _ => {}
        }
    }
    reader.finish().map_err(|_| malformed())?;
    receipts.push(json!({"source_sha256":source,"source_bytes":bytes.len(),"source_format":"apng","poster_retained":plan.poster,"interpretation":interpretation,"compositing_space":space,"precision":"RGBA8 round to nearest after each displayed frame"}));
    Ok(Prepared {
        width: plan.width,
        height: plan.height,
        plays: plan.plays,
        frames,
        poster,
        receipts,
        pending,
    })
}
pub fn import(
    source: &Source,
    root: &Path,
    id: String,
    policy: ColorPolicy,
    ppi: f64,
    control: &control::Control,
) -> Result<Value, Error> {
    control.check()?;
    assets::absolute(root)?;
    if !valid_id(&id) || !ppi.is_finite() || !(1.0..=9600.0).contains(&ppi) {
        return Err(error("Sequence document ID or resolution is invalid"));
    }
    let prepared = match source {
        Source::Gif {
            source_path,
            background,
        } => {
            if !matches!(policy, ColorPolicy::AssumeSrgb) {
                return Err(Error::new(
                    "COLOR_POLICY_REQUIRED",
                    "Untagged GIF sequences require explicit assume_srgb",
                ));
            }
            assets::absolute(source_path)?;
            let bytes = assets::read_bounded(source_path, assets::MAX_IMPORT_BYTES)?;
            let animation = crate::image_io::gif::decode(&bytes, *background, control)?;
            if animation.width as u64 * animation.height as u64 > crate::render::MAX_RENDER_PIXELS {
                return Err(limit("GIF canvas exceeds render pixel limit"));
            }
            let source_hash = assets::sha256(&bytes);
            let mut pending = BTreeMap::new();
            let frames = animation
                .frames
                .into_iter()
                .map(|frame| {
                    let asset = descriptor(
                        animation.width,
                        animation.height,
                        &frame.rgba,
                        &source_hash,
                        Interpretation::AssumedSrgb,
                    );
                    pending.entry(asset.sha256.clone()).or_insert(frame.rgba);
                    (asset, frame.delay)
                })
                .collect();
            Prepared {
                width: animation.width,
                height: animation.height,
                plays: animation.plays,
                frames,
                poster: None,
                pending,
                receipts: vec![
                    json!({"source_format":"gif","source_sha256":source_hash,"source_bytes":bytes.len(),"background":background,"metadata":animation.metadata,"metadata_trust":"untrusted","timing":"exact_centiseconds","loop_count":"stored_positive_repeats_plus_initial_play_zero_infinite","color_policy":"assume_srgb","losses":["Frames retain displayed palette pixels and binary alpha; source palette indexing and compression are represented by source identity. Unknown comments are not copied to document metadata. Logical-screen background interpretation is explicitly selectable."]}),
                ],
            }
        }
        Source::Apng {
            source_path,
            compositing_space,
        } => apng(source_path, policy, *compositing_space, control)?,
        Source::Images { frames, plays } => {
            if frames.is_empty() || frames.len() > MAX_FRAMES {
                return Err(limit(
                    "Image sequences require 1..256 explicit ordered files",
                ));
            }
            let mut prepared = Prepared {
                width: 0,
                height: 0,
                plays: *plays,
                frames: vec![],
                poster: None,
                receipts: vec![],
                pending: BTreeMap::new(),
            };
            let mut pixels = 0;
            for (index, frame) in frames.iter().enumerate() {
                control.check()?;
                let imported = assets::import(&frame.source_path, root, policy)?;
                let asset = &imported.asset;
                if index == 0 {
                    prepared.width = asset.width;
                    prepared.height = asset.height;
                }
                if (asset.width, asset.height) != (prepared.width, prepared.height) {
                    return Err(error("Every imported frame must have identical dimensions"));
                }
                pixels += asset.width as u64 * asset.height as u64;
                if pixels > MAX_PIXELS
                    || asset.width as u64 * asset.height as u64 > crate::render::MAX_RENDER_PIXELS
                {
                    return Err(limit("Imported sequence exceeds its pixel limits"));
                }
                prepared
                    .receipts
                    .push(json!({"index":index,"import":imported}));
                prepared.frames.push((imported.asset, frame.delay));
            }
            prepared
        }
    };
    let mut ids = BTreeMap::new();
    let mut assets = BTreeMap::new();
    let mut frames = vec![];
    for (index, (asset, delay)) in prepared.frames.iter().enumerate() {
        let next = ids.len();
        let name = ids
            .entry(asset.sha256.clone())
            .or_insert_with(|| format!("image-{next}"));
        assets.entry(name.clone()).or_insert_with(|| asset.clone());
        frames.push(Frame {
            id: format!("frame-{index}"),
            dataset: name.clone(),
            delay: *delay,
        });
    }
    if ids.len() > variants::MAX_DATASETS {
        return Err(limit(
            "Sequence import supports at most 32 distinct rendered frame states",
        ));
    }
    let bindings = assets
        .keys()
        .map(|id| variants::Binding {
            key: id.clone(),
            item_id: id.clone(),
            property: variants::Property::Visible,
        })
        .collect::<Vec<_>>();
    let datasets = assets
        .keys()
        .map(|id| {
            (
                id.clone(),
                variants::Dataset {
                    parent: None,
                    values: assets
                        .keys()
                        .map(|k| (k.clone(), variants::Value::Visible(k == id)))
                        .collect(),
                },
            )
        })
        .collect();
    let mut items=assets.keys().map(|id|json!({"id":id,"name":id,"visible":false,"content":{"type":"image","asset_id":id,"width":prepared.width,"height":prepared.height,"sampling":"nearest"}})).collect::<Vec<_>>();
    let poster = if let Some(asset) = prepared.poster {
        assets.insert("poster".into(), asset);
        items.push(json!({"id":"poster","name":"Separate default image","visible":false,"content":{"type":"image","asset_id":"poster","width":prepared.width,"height":prepared.height,"sampling":"nearest"}}));
        Some("poster")
    } else {
        None
    };
    let mut document:Document=serde_json::from_value(json!({"schema_version":2,"id":id,"kind":"raster","width":prepared.width,"height":prepared.height,"resolution_ppi":ppi,"color_space":"srgb","items":items,"assets":assets})).map_err(|_|error("Unable to construct sequence document"))?;
    variants::define(&mut document, variants::Definition { bindings, datasets })?;
    let first = frames[0].dataset.clone();
    set(
        &mut document,
        Some(Timeline {
            plays: prepared.plays,
            frames,
        }),
    )?;
    variants::select(&mut document, Some(first))?;
    crate::validate(&document)?;
    let mut created = 0;
    for (hash, pixels) in prepared.pending {
        control.check()?;
        let asset = document.assets.values().find(|a| a.sha256 == hash).unwrap();
        if assets::publish(asset, &pixels, root)? {
            created += 1;
        }
    }
    Ok(
        json!({"document":document,"source_preserved":true,"poster_item":poster,"source_receipts":prepared.receipts,"created_apng_assets":created,"losses":["Animated subframes and disposal are normalized into full-canvas RGBA8 states; original files stay unchanged. A separate default image is retained as a hidden poster item. Sequence timing references editable variant datasets.","Descriptive file metadata is returned in source receipts where supported, not applied to sequence artwork. No implicit profile conversion is performed for animated PNG."]}),
    )
}
