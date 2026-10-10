//! Immutable focused PNG views with explicit document/pixel coordinate maps.
use crate::{Error, boards, control::Control, geometry, model::*, render, render_quality, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::Path;

#[derive(Clone, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Focus {
    #[default]
    Canvas,
    Region {
        /// Document coordinates: min x, min y, max x, max y.
        bounds: geometry::Bounds,
    },
    Items {
        ids: Vec<String>,
        /// Expand unclipped geometry bounds in document units; includes other artwork.
        #[serde(default)]
        margin: f64,
    },
    Artboard {
        id: String,
        #[serde(default)]
        include_bleed: bool,
    },
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(default, deny_unknown_fields)]
pub struct Options {
    pub focus: Focus,
    pub scale: u32,
    pub render_options: render_quality::Options,
}
impl Default for Options {
    fn default() -> Self {
        Self {
            focus: Focus::Canvas,
            scale: 1,
            render_options: Default::default(),
        }
    }
}

fn invalid(message: &str) -> Error {
    Error::new("INVALID_REQUEST", message)
}

fn checked_bounds(bounds: geometry::Bounds) -> Result<geometry::Bounds, Error> {
    if bounds
        .iter()
        .any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE)
    {
        return Err(invalid(
            "Preview bounds must be finite and within document coordinate limits",
        ));
    }
    if bounds[2] <= bounds[0] || bounds[3] <= bounds[1] {
        return Err(Error::new(
            "EMPTY_PREVIEW",
            "Preview bounds need positive width and height; supply a region or item margin",
        ));
    }
    Ok(bounds)
}

pub(crate) fn mapping(
    local_to_world: Matrix,
    origin: Point,
    scale: u32,
    dimensions: [u32; 2],
) -> Result<Value, Error> {
    let s = scale as f64;
    use geometry::TransformFactor::{Forward, Inverse};
    let world_to_pixel = geometry::transform_expression(&[
        Forward([s, 0.0, 0.0, s, 0.0, 0.0]),
        Forward([1.0, 0.0, 0.0, 1.0, -origin[0], -origin[1]]),
        Inverse(local_to_world),
    ])?;
    let pixel_to_world = geometry::transform_expression(&[
        Forward(local_to_world),
        Forward([1.0, 0.0, 0.0, 1.0, origin[0], origin[1]]),
        Inverse([s, 0.0, 0.0, s, 0.0, 0.0]),
    ])?;
    let [w, h] = dimensions.map(|v| v as f64);
    let corners =
        [[0.0, 0.0], [w, 0.0], [w, h], [0.0, h]].map(|p| geometry::map(pixel_to_world, p));
    Ok(
        json!({"world_to_pixel":world_to_pixel,"pixel_to_world":pixel_to_world,"world_corners":corners,
        "pixel_coordinates":"Pixel edges; pixel (x,y) has center (x+0.5,y+0.5). Bounds are end-exclusive.",
        "matrix_convention":"[a,b,c,d,e,f]: (a*x+c*y+e,b*x+d*y+f)"}),
    )
}

/// Preview only: no document mutation, publication or state reservation.
pub fn preview(
    document: &Document,
    options: &Options,
    asset_root: Option<&Path>,
    font_root: Option<&Path>,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    crate::model::validate_controlled(document, control)?;
    crate::finite::check(options).map_err(|_| invalid("Preview option numbers must be finite"))?;
    control.check_resource_paths(&crate::sessions::Resources {
        asset_root: asset_root.map(Path::to_owned),
        font_root: font_root.map(Path::to_owned),
    })?;
    let mut result = if let Focus::Artboard { id, include_bleed } = &options.focus {
        artboard(
            document,
            options,
            id,
            *include_bleed,
            asset_root,
            font_root,
            control,
        )?
    } else {
        document_region(document, options, asset_root, font_root, control)?
    };
    result["document_id"] = json!(document.id);
    result["revision"] = json!(document.revision);
    result["document_sha256"] = json!(crate::assets::sha256(
        &serde_json::to_vec(document)
            .map_err(|_| invalid("Unable to encode preview document identity"))?
    ));
    result["focus"] = json!(options.focus);
    result["source_changed"] = json!(false);
    control.check()?;
    Ok(result)
}

fn document_region(
    document: &Document,
    options: &Options,
    asset_root: Option<&Path>,
    font_root: Option<&Path>,
    control: &Control,
) -> Result<Value, Error> {
    let plan =
        render_quality::Plan::for_document(document, options.scale, Some(&options.render_options))?;
    let base_origin = document
        .vector_canvas
        .map_or([0.0; 2], |c| c.origin_px)
        .map(|v| {
            v - if options.render_options.crop_to_canvas {
                0.0
            } else {
                options.render_options.padding as f64
            }
        });
    let s = options.scale as f64;
    let output_bounds = [
        base_origin[0],
        base_origin[1],
        base_origin[0] + plan.output[0] as f64 / s,
        base_origin[1] + plan.output[1] as f64 / s,
    ];
    let requested = match &options.focus {
        Focus::Canvas => {
            if options.render_options.crop_to_canvas {
                crate::vector_canvas::bounds(document)
            } else {
                output_bounds
            }
        }
        Focus::Region { bounds } => checked_bounds(*bounds)?,
        Focus::Items { ids, margin } => {
            if !(0.0..=MAX_COORDINATE).contains(margin) {
                return Err(invalid(
                    "Preview item margin must be nonnegative and within coordinate limits",
                ));
            }
            let mut bounds = None;
            for i in scene::selection(document, ids, false)? {
                control.check()?;
                if let Some(b) = scene::bounds(document, i)? {
                    bounds = Some(bounds.map_or(b, |a| scene::union(a, b)));
                }
            }
            let b = bounds.ok_or_else(|| {
                Error::new(
                    "EMPTY_PREVIEW",
                    "Selected items have no geometric bounds; supply a document region",
                )
            })?;
            checked_bounds([b[0] - margin, b[1] - margin, b[2] + margin, b[3] + margin])?
        }
        Focus::Artboard { .. } => unreachable!(),
    };
    // Crop completed full-scene pixels. Replacing the evaluation canvas would alter
    // filters, backgrounds and canvas-relative operators at the new boundary.
    let wanted = [
        (requested[0] - base_origin[0]) * s,
        (requested[1] - base_origin[1]) * s,
        (requested[2] - base_origin[0]) * s,
        (requested[3] - base_origin[1]) * s,
    ];
    let quantized = [
        wanted[0].floor(),
        wanted[1].floor(),
        wanted[2].ceil(),
        wanted[3].ceil(),
    ];
    let crop = std::array::from_fn::<_, 4, _>(|i| {
        quantized[i].clamp(0.0, plan.output[i % 2] as f64) as u32
    });
    if crop[2] <= crop[0] || crop[3] <= crop[1] {
        return Err(Error::new(
            "FOCUS_OUTSIDE_CANVAS",
            "Preview focus does not intersect the rendered canvas; choose another region or explicit render padding",
        ));
    }
    let full = render::rasterize_controlled(
        document,
        options.scale,
        asset_root,
        font_root,
        Some(&options.render_options),
        control,
    )?;
    let dimensions = [crop[2] - crop[0], crop[3] - crop[1]];
    let pixels = if crop == [0, 0, full.width, full.height] {
        full
    } else {
        let mut rgba = Vec::with_capacity(dimensions[0] as usize * dimensions[1] as usize * 4);
        for y in crop[1]..crop[3] {
            control.check()?;
            let offset = (y as usize * full.width as usize + crop[0] as usize) * 4;
            rgba.extend_from_slice(&full.rgba[offset..offset + dimensions[0] as usize * 4]);
        }
        render::Rasterized {
            width: dimensions[0],
            height: dimensions[1],
            rgba,
        }
    };
    let origin = [
        base_origin[0] + crop[0] as f64 / s,
        base_origin[1] + crop[1] as f64 / s,
    ];
    let actual = [
        origin[0],
        origin[1],
        base_origin[0] + crop[2] as f64 / s,
        base_origin[1] + crop[3] as f64 / s,
    ];
    let artifact = render::png_pixels(document, pixels, options.scale)?;
    Ok(
        json!({"composition":"document","bounds_space":"document","requested_bounds":requested,"actual_bounds":actual,
        "clipped_to_render":(0..4).any(|i|quantized[i]!=crop[i] as f64),"crop_pixels":crop,
        "mapping":mapping(identity(),origin,options.scale,dimensions)?,"artifact":artifact,"full_render":plan.receipt(),
        "semantics":"Full composition cropped outward to its existing pixel grid. Item focus uses unclipped geometry (text frames), including hidden items, excluding strokes/effects. Other artwork remains visible. Full render limits and evaluation cost apply."}),
    )
}

fn artboard(
    document: &Document,
    options: &Options,
    id: &str,
    include_bleed: bool,
    asset_root: Option<&Path>,
    font_root: Option<&Path>,
    control: &Control,
) -> Result<Value, Error> {
    let i = scene::index(document, id)?;
    let world = scene::world_transform(document, i)?;
    let mut output = boards::export_controlled(
        document,
        &boards::Selection::Ids {
            ids: vec![id.to_owned()],
        },
        boards::ExportOptions {
            render_options: Some(&options.render_options),
            metadata_policy: None,
            image_options: None,
            format: boards::Format::Png,
            scale: options.scale,
            include_bleed,
            asset_root,
            font_root,
        },
        control,
    )?;
    let entry = &mut output["artifacts"][0];
    let bounds: geometry::Bounds = serde_json::from_value(entry["source_bounds"].clone())
        .map_err(|_| invalid("Invalid internal artboard bounds"))?;
    let mut artifact = entry["artifact"].take();
    let dimensions = [
        artifact["width"].as_u64().unwrap() as u32,
        artifact["height"].as_u64().unwrap() as u32,
    ];
    let pad = if options.render_options.crop_to_canvas {
        0.0
    } else {
        options.render_options.padding as f64
    };
    let origin = [bounds[0] - pad, bounds[1] - pad];
    let actual = [
        origin[0],
        origin[1],
        origin[0] + dimensions[0] as f64 / options.scale as f64,
        origin[1] + dimensions[1] as f64 / options.scale as f64,
    ];
    let render_settings = artifact
        .as_object_mut()
        .unwrap()
        .remove("render_settings")
        .unwrap_or(Value::Null);
    Ok(
        json!({"composition":"standalone_artboard","bounds_space":"artboard_local","requested_bounds":bounds,"actual_bounds":actual,
        "clipped_to_render":false,"crop_pixels":[0,0,dimensions[0],dimensions[1]],"mapping":mapping(world,origin,options.scale,dimensions)?,
        "artifact":artifact,"full_render":render_settings,"semantics":output["coordinate_contract"]}),
    )
}
