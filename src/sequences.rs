//! Ordered, exactly timed views of retained variant artwork and local frame exchange.
use crate::{Document, Error, assets, control, model::*, sessions::Resources, variants};
use base64::{Engine, engine::general_purpose::STANDARD};
use num_rational::BigRational;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{collections::HashSet, io::Write};

mod import;
pub use crate::image_io::gif::Background as GifBackground;
pub use import::{CompositingSpace, Source, import};
pub const MAX_FRAMES: usize = 256;
pub const MAX_PIXELS: u64 = 16_777_216;
pub const LOSS: &str = "Animation frames retain order, delay fractions and play count, but are flattened RGBA8 views. Keep the snapshot and resource stores for editable layers, text, variants and sequence controls. Transparent display colors may normalize to zero. A retained separate poster is not exported; the first animation frame is the default image.";

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Delay {
    pub numerator: u16,
    pub denominator: u16,
}
impl Delay {
    fn rational(self) -> BigRational {
        BigRational::new(
            self.numerator.into(),
            u32::from(if self.denominator == 0 {
                100
            } else {
                self.denominator
            })
            .into(),
        )
    }
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Frame {
    pub id: String,
    pub dataset: String,
    pub delay: Delay,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Timeline {
    #[serde(default)]
    pub plays: u32,
    pub frames: Vec<Frame>,
}
fn error(message: &str) -> Error {
    Error::new("INVALID_SEQUENCE", message)
}
pub(crate) fn validate(state: &variants::State) -> Result<(), Error> {
    let Some(timeline) = &state.sequence else {
        return Ok(());
    };
    if timeline.frames.is_empty() || timeline.frames.len() > MAX_FRAMES {
        return Err(limit("A sequence requires 1..256 ordered frames"));
    }
    let mut ids = HashSet::new();
    for frame in &timeline.frames {
        if !valid_id(&frame.id)
            || !ids.insert(&frame.id)
            || !state.definition.datasets.contains_key(&frame.dataset)
        {
            return Err(error(
                "Sequence frame IDs must be unique and each dataset must exist",
            ));
        }
    }
    Ok(())
}
pub(crate) fn timeline(d: &Document) -> Result<&Timeline, Error> {
    d.variants
        .as_ref()
        .and_then(|s| s.sequence.as_ref())
        .ok_or_else(|| error("Document has no frame sequence"))
}
pub(crate) fn set(d: &mut Document, sequence: Option<Timeline>) -> Result<Value, Error> {
    let state = d
        .variants
        .as_mut()
        .ok_or_else(|| error("Define variant artwork before a frame sequence"))?;
    state.sequence = sequence;
    validate(state)?;
    Ok(json!({"sequence":state.sequence,"artwork_unchanged":true}))
}
pub fn inspect(d: &Document) -> Result<Value, Error> {
    crate::validate(d)?;
    let t = timeline(d)?;
    let fraction = |v: &BigRational| json!({"numerator":v.numer().to_string(),"denominator":v.denom().to_string()});
    let mut start = BigRational::from_integer(0.into());
    let mut frames = vec![];
    for (index, frame) in t.frames.iter().enumerate() {
        let end = &start + frame.delay.rational();
        frames.push(json!({"index":index,"id":frame.id,"dataset":frame.dataset,"delay":frame.delay,"start_seconds":fraction(&start),"end_seconds":fraction(&end)}));
        start = end;
    }
    Ok(
        json!({"frames":frames,"duration_seconds":fraction(&start),"plays":t.plays,"infinite":t.plays==0,"selected_dataset":d.variants.as_ref().unwrap().selected,"width":d.width,"height":d.height,"zero_delay":"advance_as_fast_as_consumer_allows","denominator_zero":"one_hundred","source_preserved":true}),
    )
}
pub(crate) fn select(d: &mut Document, id: &str) -> Result<Value, Error> {
    let frame = timeline(d)?
        .frames
        .iter()
        .find(|f| f.id == id)
        .ok_or_else(|| error("Sequence frame does not exist"))?
        .clone();
    let view = variants::select(d, Some(frame.dataset.clone()))?;
    Ok(json!({"frame":frame,"selection":view}))
}
pub fn open(d: &Document, id: &str) -> Result<Value, Error> {
    crate::validate(d)?;
    let frame = timeline(d)?
        .frames
        .iter()
        .find(|f| f.id == id)
        .ok_or_else(|| error("Sequence frame does not exist"))?;
    let mut view = variants::view(d, &frame.dataset)?;
    view.variants = None;
    crate::validate(&view)?;
    Ok(
        json!({"document":view,"frame":frame,"source_preserved":true,"losses":["The returned still retains editable artwork at this frame, but detaches variant bindings and sequence timing. The source animation stays unchanged."]}),
    )
}
pub(crate) fn from_layers(
    d: &mut Document,
    ids: &[String],
    delay: Delay,
    plays: u32,
) -> Result<Value, Error> {
    if d.variants.is_some() {
        return Err(error(
            "Layer conversion requires no existing variant table; retain or explicitly clear it first",
        ));
    }
    if ids.is_empty()
        || ids.len() > variants::MAX_DATASETS
        || ids.iter().collect::<HashSet<_>>().len() != ids.len()
    {
        return Err(error(
            "Layer conversion requires 1..32 unique root item IDs in frame order",
        ));
    }
    for id in ids {
        let i = crate::scene::index(d, id)?;
        if d.items[i].parent.is_some()
            || d.items[i].clip_to.is_some()
            || matches!(
                d.items[i].content,
                Content::ComponentSource {}
                    | Content::MaskSource {}
                    | Content::WorkPath { .. }
                    | Content::Adjustment { .. }
            )
        {
            return Err(error("Frame layers must be independent printable roots"));
        }
        crate::scene::check_unlocked(d, i, true)?;
    }
    let bindings = ids
        .iter()
        .enumerate()
        .map(|(i, id)| variants::Binding {
            key: format!("layer-{i}"),
            item_id: id.clone(),
            property: variants::Property::Visible,
        })
        .collect::<Vec<_>>();
    let datasets = ids
        .iter()
        .enumerate()
        .map(|(i, _)| {
            (
                format!("frame-{i}"),
                variants::Dataset {
                    parent: None,
                    values: bindings
                        .iter()
                        .enumerate()
                        .map(|(j, b)| (b.key.clone(), variants::Value::Visible(i == j)))
                        .collect(),
                },
            )
        })
        .collect();
    variants::define(d, variants::Definition { bindings, datasets })?;
    set(
        d,
        Some(Timeline {
            plays,
            frames: ids
                .iter()
                .enumerate()
                .map(|(i, _)| Frame {
                    id: format!("frame-{i}"),
                    dataset: format!("frame-{i}"),
                    delay,
                })
                .collect(),
        }),
    )?;
    variants::select(d, Some("frame-0".into()))?;
    Ok(
        json!({"ordered_layers":ids,"source_content_retained":true,"unlisted_items":"retain_their_current_visibility","sequence":timeline(d)?}),
    )
}
struct Bounded<'a>(Vec<u8>, &'a control::Control);
fn check_work(
    d: &Document,
    plan: &crate::render_quality::Plan,
    frames: usize,
) -> Result<(), Error> {
    let pixels = plan.output[0] as u64 * plan.output[1] as u64 * frames as u64;
    let evaluated = plan.evaluation[0] as u64
        * plan.evaluation[1] as u64
        * (plan.internal_scale as u64).pow(2)
        * frames as u64;
    if pixels > MAX_PIXELS
        || evaluated.saturating_mul(d.items.len().max(1) as u64) > crate::render::MAX_RENDER_WORK
    {
        return Err(limit(
            "Sequence output exceeds aggregate pixel or scene-work limits",
        ));
    }
    Ok(())
}
impl Write for Bounded<'_> {
    fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
        self.1
            .check()
            .map_err(|e| std::io::Error::other(e.message))?;
        if self.0.len().saturating_add(bytes.len()) > crate::publish::MAX_OUTPUT_BYTES {
            return Err(std::io::Error::other("Sequence output exceeds byte limit"));
        }
        self.0.extend_from_slice(bytes);
        Ok(bytes.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}
pub fn export(
    d: &Document,
    resources: &Resources,
    scale: u32,
    options: Option<&crate::render_quality::Options>,
    control: &control::Control,
) -> Result<Value, Error> {
    crate::validate(d)?;
    let t = timeline(d)?;
    if d.output_profile.is_some() {
        return Err(Error::new(
            "UNSUPPORTED",
            "Animated PNG currently delivers encoded sRGB without an output profile",
        ));
    }
    let plan = crate::render_quality::Plan::for_document(d, scale, options)?;
    let [width, height] = plan.output;
    check_work(d, &plan, t.frames.len())?;
    control.check()?;
    let encode_error = |_: png::EncodingError| {
        control
            .check()
            .err()
            .unwrap_or_else(|| Error::new("EXPORT_ERROR", "Unable to encode bounded animated PNG"))
    };
    let mut output = Bounded(vec![], control);
    let mut encoder = png::Encoder::new(&mut output, width, height);
    encoder.set_color(png::ColorType::Rgba);
    encoder.set_depth(png::BitDepth::Eight);
    encoder
        .set_animated(t.frames.len() as u32, t.plays)
        .map_err(encode_error)?;
    encoder.set_source_srgb(png::SrgbRenderingIntent::RelativeColorimetric);
    let density = (d.resolution_ppi * scale as f64 / 0.0254).round() as u32;
    encoder.set_pixel_dims(Some(png::PixelDimensions {
        xppu: density,
        yppu: density,
        unit: png::Unit::Meter,
    }));
    let mut writer = encoder.write_header().map_err(encode_error)?;
    let mut frames = vec![];
    for (index, frame) in t.frames.iter().enumerate() {
        control.check()?;
        let view = variants::view(d, &frame.dataset)?;
        let raster = crate::render::rasterize_with_options(
            &view,
            scale,
            resources.asset_root.as_deref(),
            resources.font_root.as_deref(),
            options,
        )?;
        writer
            .set_frame_delay(frame.delay.numerator, frame.delay.denominator)
            .map_err(encode_error)?;
        writer
            .write_image_data(&raster.rgba)
            .map_err(encode_error)?;
        frames.push(json!({"index":index,"id":frame.id,"dataset":frame.dataset,"delay":frame.delay,"rgba_sha256":assets::sha256(&raster.rgba)}));
    }
    writer.finish().map_err(encode_error)?;
    Ok(
        json!({"media_type":"image/apng","encoding":"base64","data":STANDARD.encode(output.0),"width":width,"height":height,"sequence":{"frames":frames,"plays":t.plays,"all_frames":true,"color":"encoded_srgb_rgba8","frame_storage":"full_canvas_source_replace_no_disposal"},"render_settings":plan.receipt(),"losses":[LOSS]}),
    )
}

/// Return independent PNG files in sequence order; callers may retain every artifact.
pub fn export_frames(
    d: &Document,
    resources: &Resources,
    scale: u32,
    options: Option<&crate::render_quality::Options>,
    policy: Option<crate::metadata::Policy>,
    control: &control::Control,
) -> Result<Value, Error> {
    control.check()?;
    crate::validate(d)?;
    let t = timeline(d)?;
    let plan = crate::render_quality::Plan::for_document(d, scale, options)?;
    check_work(d, &plan, t.frames.len())?;
    let mut frames = Vec::new();
    let mut encoded_bytes = 0usize;
    for (index, frame) in t.frames.iter().enumerate() {
        control.check()?;
        let mut view = variants::view(d, &frame.dataset)?;
        view.variants = None;
        let artifact = crate::publish::export_with_render_options(
            &view,
            crate::ExportFormat::Png,
            scale,
            resources,
            crate::publish::FormatOptions {
                control: Some(control),
                render_options: options,
                metadata_policy: policy,
                ..Default::default()
            },
        )?;
        let data = artifact["data"].as_str().unwrap();
        encoded_bytes = encoded_bytes.saturating_add(data.len());
        if encoded_bytes > crate::publish::MAX_OUTPUT_BYTES * 4 / 3 {
            return Err(limit(
                "Sequence PNG artifacts exceed the aggregate output limit",
            ));
        }
        frames.push(json!({"index":index,"id":frame.id,"dataset":frame.dataset,"delay":frame.delay,"file_name":format!("frame-{index:04}.png"),"sha256":assets::sha256(&STANDARD.decode(data).map_err(|_|Error::new("EXPORT_ERROR","Invalid PNG encoding"))?),"artifact":artifact}));
    }
    control.check()?;
    Ok(
        json!({"frames":frames,"plays":t.plays,"width":plan.output[0],"height":plan.output[1],"source_preserved":true,"losses":["PNG frame files retain rendered pixels in explicit order. Timing and play count are in this receipt; retain it with the files. Editable artwork remains in the source snapshot."]}),
    )
}

/// Exact palette delivery for a still or all ordered sequence frames.
pub fn export_gif(
    d: &Document,
    resources: &Resources,
    scale: u32,
    options: Option<&crate::render_quality::Options>,
    metadata: Option<&str>,
    control: &control::Control,
) -> Result<Value, Error> {
    use crate::image_io::gif::{Animation, Frame};
    control.check()?;
    crate::validate(d)?;
    if d.output_profile.is_some() {
        return Err(Error::new(
            "UNSUPPORTED",
            "GIF delivery requires working sRGB and cannot embed an output profile; clear the association explicitly or choose a profiled format",
        ));
    }
    let sequence = d.variants.as_ref().and_then(|v| v.sequence.as_ref());
    let plan = crate::render_quality::Plan::for_document(d, scale, options)?;
    check_work(d, &plan, sequence.map_or(1, |s| s.frames.len()))?;
    let mut frames = vec![];
    let mut receipts = vec![];
    let requests: Vec<_> = if let Some(sequence) = sequence {
        sequence
            .frames
            .iter()
            .map(|f| (Some(f.dataset.as_str()), f.delay))
            .collect()
    } else {
        vec![(
            None,
            Delay {
                numerator: 0,
                denominator: 100,
            },
        )]
    };
    for (index, (dataset, delay)) in requests.into_iter().enumerate() {
        control.check()?;
        let selected = dataset.map(|id| variants::view(d, id)).transpose()?;
        let raster = crate::render::rasterize_with_options(
            selected.as_ref().unwrap_or(d),
            scale,
            resources.asset_root.as_deref(),
            resources.font_root.as_deref(),
            options,
        )?;
        receipts.push(json!({"index":index,"dataset":dataset,"delay":delay,"rgba_sha256":assets::sha256(&raster.rgba)}));
        frames.push(Frame {
            rgba: raster.rgba,
            delay,
        });
    }
    let animation = Animation {
        width: plan.output[0],
        height: plan.output[1],
        plays: sequence.map_or(1, |s| s.plays),
        frames,
        metadata: None,
    };
    let bytes = crate::image_io::gif::encode(&animation, metadata, control)?;
    control.check()?;
    Ok(
        json!({"media_type":"image/gif","encoding":"base64","data":STANDARD.encode(bytes),"width":animation.width,"height":animation.height,
        "sequence":{"frames":receipts,"plays":animation.plays,"all_frames":sequence.is_some(),"color":"untagged_srgb_exact_palette_binary_alpha","frame_storage":"full_canvas_restore_transparent_backdrop"},
        "render_settings":plan.receipt(),"losses":["GIF stores exact palettes up to 256 entries per frame, including one reserved transparent entry whenever any frame has transparency. No color quantization, alpha thresholding or timing rounding is performed. More colors, partial alpha and non-centisecond delays fail explicitly. Transparent hidden colors normalize to black. Comments carry only the selected Inkbolt metadata envelope; ICC profiles and physical density are unsupported. Editable artwork remains in the source snapshot. Positive stored loop counts mean repetitions after the initial play; consumer scheduling can differ from the exact stored delays."]}),
    )
}
