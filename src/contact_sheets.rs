//! Bounded contact sheets of immutable previews from one color-managed document.
use crate::{Error, control::Control, geometry, model::*, previews, render_quality, scene};
use base64::{Engine, engine::general_purpose::STANDARD};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{io::Cursor, path::Path};

pub const MAX_VIEWS: usize = 16;
pub const MAX_PIXELS: u64 = 4_194_304;

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(default, deny_unknown_fields)]
pub struct Options {
    pub views: Vec<previews::Options>,
    pub columns: u32,
    pub cell_size: [u32; 2],
    pub gap: u32,
}
impl Default for Options {
    fn default() -> Self {
        Self {
            views: vec![],
            columns: 4,
            cell_size: [256; 2],
            gap: 8,
        }
    }
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_REQUEST", message)
}

fn evaluation_pixels(document: &Document, options: &previews::Options) -> Result<u64, Error> {
    let plan = if let previews::Focus::Artboard { id, include_bleed } = &options.focus {
        let item = &document.items[scene::index(document, id)?];
        let Content::Frame { frame } = &item.content else {
            return Err(invalid("Contact sheet artboard focus requires an artboard"));
        };
        if frame.role != crate::boards::Role::Artboard {
            return Err(invalid("Contact sheet artboard focus requires an artboard"));
        }
        let pad = if *include_bleed {
            frame.bleed
        } else {
            Default::default()
        };
        render_quality::Plan::new(
            frame.width + pad.left + pad.right,
            frame.height + pad.top + pad.bottom,
            options.scale,
            Some(&options.render_options),
        )?
    } else {
        render_quality::Plan::for_document(document, options.scale, Some(&options.render_options))?
    };
    Ok(plan.evaluation[0] as u64 * plan.evaluation[1] as u64 * (plan.internal_scale as u64).pow(2))
}

pub fn sheet(
    document: &Document,
    options: &Options,
    asset_root: Option<&Path>,
    font_root: Option<&Path>,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    crate::model::validate_controlled(document, control)?;
    if options.views.is_empty()
        || options.views.len() > MAX_VIEWS
        || !(1..=8).contains(&options.columns)
        || options.cell_size.iter().any(|v| !(1..=512).contains(v))
        || options.gap > 64
    {
        return Err(invalid(
            "Contact sheets require 1..=16 views, 1..=8 columns, cell axes 1..=512 and gap 0..=64",
        ));
    }
    crate::finite::check(options)
        .map_err(|_| invalid("Contact sheet option numbers must be finite"))?;
    // Admit cumulative render pixels before starting any view, including padding
    // and supersampling. Each renderer additionally enforces its full work limits.
    let mut evaluation = 0u64;
    for view in &options.views {
        control.check()?;
        evaluation += evaluation_pixels(document, view)?;
        if evaluation > MAX_PIXELS {
            return Err(Error::new(
                "RESOURCE_LIMIT",
                "Contact sheet views exceed aggregate evaluation pixel budget",
            ));
        }
    }
    let columns = options.columns.min(options.views.len() as u32);
    let rows = (options.views.len() as u32).div_ceil(columns);
    let width = columns * options.cell_size[0] + (columns - 1) * options.gap;
    let height = rows * options.cell_size[1] + (rows - 1) * options.gap;
    if width as u64 * height as u64 > MAX_PIXELS {
        return Err(Error::new(
            "RESOURCE_LIMIT",
            "Contact sheet image exceeds pixel budget",
        ));
    }
    let mut rgba = vec![0; width as usize * height as usize * 4];
    let mut entries = vec![];
    let mut profile: Option<Vec<u8>> = None;
    let mut color_profile = Value::Null;
    for (index, view) in options.views.iter().enumerate() {
        control.check()?;
        let mut result = previews::preview(document, view, asset_root, font_root, control)?;
        let mut artifact = result.as_object_mut().unwrap().remove("artifact").unwrap();
        let data = artifact.as_object_mut().unwrap().remove("data").unwrap();
        let encoded = STANDARD
            .decode(data.as_str().unwrap())
            .map_err(|_| invalid("Invalid internal preview encoding"))?;
        let sha256 = crate::assets::sha256(&encoded);
        let mut decoder = png::Decoder::new_with_limits(
            Cursor::new(encoded),
            png::Limits {
                bytes: 16 * 1024 * 1024,
            },
        );
        decoder.set_transformations(png::Transformations::IDENTITY);
        let mut reader = decoder
            .read_info()
            .map_err(|_| invalid("Invalid internal preview PNG"))?;
        let current_profile = reader.info().icc_profile.as_deref().map(ToOwned::to_owned);
        if index == 0 {
            profile = current_profile;
            color_profile = artifact["color_profile"].clone();
        } else if current_profile != profile {
            return Err(invalid(
                "Contact sheet views have inconsistent color profiles",
            ));
        }
        let size = reader
            .output_buffer_size()
            .filter(|n| *n <= crate::render::MAX_RENDER_PIXELS as usize * 4)
            .ok_or_else(|| Error::new("RESOURCE_LIMIT", "Preview decode exceeds pixel budget"))?;
        let mut pixels = vec![0; size];
        let info = reader
            .next_frame(&mut pixels)
            .map_err(|_| invalid("Invalid internal preview pixels"))?;
        if info.bit_depth != png::BitDepth::Eight || info.color_type != png::ColorType::Rgba {
            return Err(invalid("Preview must contain RGBA8 pixels"));
        }
        let factor = (options.cell_size[0] as f64 / info.width as f64)
            .min(options.cell_size[1] as f64 / info.height as f64)
            .min(1.0);
        let tw = ((info.width as f64 * factor).floor() as u32).max(1);
        let th = ((info.height as f64 * factor).floor() as u32).max(1);
        let cell_origin = [
            index as u32 % columns * (options.cell_size[0] + options.gap),
            index as u32 / columns * (options.cell_size[1] + options.gap),
        ];
        let left = cell_origin[0] + (options.cell_size[0] - tw) / 2;
        let top = cell_origin[1] + (options.cell_size[1] - th) / 2;
        for y in 0..th {
            control.check()?;
            let sy = ((2 * y + 1) as u64 * info.height as u64 / (2 * th) as u64) as usize;
            for x in 0..tw {
                let sx = ((2 * x + 1) as u64 * info.width as u64 / (2 * tw) as u64) as usize;
                let from = (sy * info.width as usize + sx) * 4;
                let to = ((top + y) as usize * width as usize + (left + x) as usize) * 4;
                rgba[to..to + 4].copy_from_slice(&pixels[from..from + 4]);
            }
        }
        let px: Matrix = serde_json::from_value(result["mapping"]["pixel_to_world"].clone())
            .map_err(|_| invalid("Invalid internal preview mapping"))?;
        let wp: Matrix = serde_json::from_value(result["mapping"]["world_to_pixel"].clone())
            .map_err(|_| invalid("Invalid internal preview mapping"))?;
        let [sx, sy] = [
            tw as f64 / info.width as f64,
            th as f64 / info.height as f64,
        ];
        let world_to_sheet = geometry::multiply([sx, 0.0, 0.0, sy, left as f64, top as f64], wp);
        let sheet_to_world = geometry::multiply(
            px,
            [
                1.0 / sx,
                0.0,
                0.0,
                1.0 / sy,
                -(left as f64) / sx,
                -(top as f64) / sy,
            ],
        );
        artifact.as_object_mut().unwrap().remove("encoding");
        artifact["sha256"] = json!(sha256);
        result["source_artifact"] = artifact;
        entries.push(json!({"index":index,"cell_bounds":[cell_origin[0],cell_origin[1],cell_origin[0]+options.cell_size[0],cell_origin[1]+options.cell_size[1]],
            "image_bounds":[left,top,left+tw,top+th],"world_to_sheet":world_to_sheet,"sheet_to_world":sheet_to_world,"preview":result}));
    }
    control.check()?;
    let bytes =
        crate::render::encode_png_with_profile(width, height, &rgba, 96.0, profile.as_deref())?;
    let mut artifact = json!({"media_type":"image/png","encoding":"base64","width":width,"height":height,"data":STANDARD.encode(bytes)});
    if !color_profile.is_null() {
        artifact["color_profile"] = color_profile;
        artifact["color_space"] = json!("icc_rgb");
    }
    control.check()?;
    Ok(
        json!({"document_id":document.id,"revision":document.revision,"document_sha256":entries[0]["preview"]["document_sha256"],
        "columns":columns,"rows":rows,"evaluation_pixels":evaluation,"views":entries,"artifact":artifact,"source_changed":false,
        "semantics":"Row-major, transparent gaps, centered thumbnails, no enlargement. Nearest source pixel at each thumbnail center; thin details can disappear. Matrices map continuous image edges; actual sampled pixels are discrete. All views share the source document output profile. Sheet density is 96 pixels per inch. Full-scene view rendering cost applies; this is not a high-fidelity resized delivery."}),
    )
}
