//! Immutable visual comparisons on an explicit common pixel grid.
use crate::{
    Error, control::Control, geometry, model::*, previews, render, render_quality, scene,
    sessions::Resources,
};
use base64::{Engine, engine::general_purpose::STANDARD};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{collections::HashSet, io::Cursor};

pub const MAX_PIXELS: u64 = render::MAX_RENDER_PIXELS;

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(default, deny_unknown_fields)]
pub struct Options {
    pub focus: previews::Focus,
    pub scale: u32,
    /// Highlight pixels whose largest RGBA8 channel delta is strictly greater.
    pub threshold: u8,
    pub before_render_options: render_quality::Options,
    pub after_render_options: render_quality::Options,
    pub include_structural: bool,
}
impl Default for Options {
    fn default() -> Self {
        Self {
            focus: Default::default(),
            scale: 1,
            threshold: 0,
            before_render_options: Default::default(),
            after_render_options: Default::default(),
            include_structural: true,
        }
    }
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_REQUEST", message)
}

struct View {
    metadata: Value,
    pixels: render::Rasterized,
    origin: Point,
    local_to_world: Matrix,
}

// Reuse the ordinary preview's composition and artboard materialization exactly.
// Output-profile conversion is deliberately absent from this ephemeral view; the
// original document is validated and its identity restored in the returned metadata.
fn view(
    document: &Document,
    resources: &Resources,
    focus: &previews::Focus,
    scale: u32,
    quality: render_quality::Options,
    control: &Control,
) -> Result<View, Error> {
    let mut working = document.clone();
    working.output_profile = None;
    let mut metadata = previews::preview(
        &working,
        &previews::Options {
            focus: focus.clone(),
            scale,
            render_options: quality,
        },
        resources.asset_root.as_deref(),
        resources.font_root.as_deref(),
        control,
    )?;
    metadata["document_sha256"] = json!(crate::assets::sha256(
        &serde_json::to_vec(document).map_err(|_| invalid("Cannot encode comparison identity"))?
    ));
    metadata["original_output_profile"] = json!(document.output_profile);
    let mut artifact = metadata
        .as_object_mut()
        .unwrap()
        .remove("artifact")
        .unwrap();
    let data = artifact.as_object_mut().unwrap().remove("data").unwrap();
    let bytes = STANDARD
        .decode(data.as_str().unwrap())
        .map_err(|_| invalid("Invalid internal comparison PNG encoding"))?;
    artifact["sha256"] = json!(crate::assets::sha256(&bytes));
    artifact.as_object_mut().unwrap().remove("encoding");
    let decoder = png::Decoder::new_with_limits(
        Cursor::new(bytes),
        png::Limits {
            bytes: 16 * 1024 * 1024,
        },
    );
    let mut reader = decoder
        .read_info()
        .map_err(|_| invalid("Invalid internal comparison PNG"))?;
    if reader.info().icc_profile.is_some() {
        return Err(invalid(
            "Comparison view unexpectedly has an output profile",
        ));
    }
    let size = reader
        .output_buffer_size()
        .filter(|n| *n <= MAX_PIXELS as usize * 4)
        .ok_or_else(|| {
            Error::new(
                "RESOURCE_LIMIT",
                "Comparison source image exceeds pixel budget",
            )
        })?;
    let mut rgba = vec![0; size];
    let info = reader
        .next_frame(&mut rgba)
        .map_err(|_| invalid("Invalid internal comparison pixels"))?;
    if info.bit_depth != png::BitDepth::Eight || info.color_type != png::ColorType::Rgba {
        return Err(invalid("Comparison requires RGBA8 view pixels"));
    }
    let origin = [
        metadata["actual_bounds"][0].as_f64().unwrap(),
        metadata["actual_bounds"][1].as_f64().unwrap(),
    ];
    let local_to_world = if let previews::Focus::Artboard { id, .. } = focus {
        scene::world_transform(document, scene::index(document, id)?)?
    } else {
        identity()
    };
    metadata["source_artifact"] = artifact;
    control.check()?;
    Ok(View {
        metadata,
        pixels: render::Rasterized {
            width: info.width,
            height: info.height,
            rgba,
        },
        origin,
        local_to_world,
    })
}

fn requested_bounds(
    before: &Document,
    after: &Document,
    focus: &previews::Focus,
    control: &Control,
) -> Result<Option<geometry::Bounds>, Error> {
    let bounds = match focus {
        previews::Focus::Canvas | previews::Focus::Artboard { .. } => return Ok(None),
        previews::Focus::Region { bounds } => *bounds,
        previews::Focus::Items { ids, margin } => {
            if ids.is_empty() || !(0.0..=MAX_COORDINATE).contains(margin) {
                return Err(invalid(
                    "Comparison item focus needs IDs and a nonnegative bounded margin",
                ));
            }
            let mut seen = HashSet::new();
            let mut bounds = None;
            for id in ids {
                control.check()?;
                if !seen.insert(id) {
                    return Err(invalid("Comparison item IDs must be unique"));
                }
                let mut found = false;
                for document in [before, after] {
                    if let Some(i) = document.items.iter().position(|item| &item.id == id) {
                        found = true;
                        if let Some(b) = scene::bounds(document, i)? {
                            bounds = Some(bounds.map_or(b, |a| scene::union(a, b)));
                        }
                    }
                }
                if !found {
                    return Err(Error::new(
                        "NOT_FOUND",
                        "Comparison item is absent from both revisions",
                    )
                    .at_item(id));
                }
            }
            let b = bounds.ok_or_else(|| {
                Error::new(
                    "EMPTY_PREVIEW",
                    "Comparison items have no geometric bounds; supply a region",
                )
            })?;
            [b[0] - margin, b[1] - margin, b[2] + margin, b[3] + margin]
        }
    };
    if bounds
        .iter()
        .any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE)
    {
        return Err(invalid(
            "Comparison bounds must be finite and within document coordinate limits",
        ));
    }
    if bounds[2] <= bounds[0] || bounds[3] <= bounds[1] {
        return Err(Error::new(
            "EMPTY_PREVIEW",
            "Comparison bounds need positive area",
        ));
    }
    Ok(Some(bounds))
}

fn artifact(width: u32, height: u32, pixels: &[u8]) -> Result<Value, Error> {
    let bytes = render::encode_png(width, height, pixels, 96.0)?;
    Ok(
        json!({"media_type":"image/png","encoding":"base64","data":STANDARD.encode(&bytes),
        "width":width,"height":height,"sha256":crate::assets::sha256(&bytes),"color_profile":{"type":"srgb"},"resolution_ppi":96}),
    )
}

fn aligned(
    view: &View,
    offset: [i64; 2],
    crop: [i64; 4],
    control: &Control,
) -> Result<Vec<u8>, Error> {
    let [width, height] = [crop[2] - crop[0], crop[3] - crop[1]];
    let mut pixels = vec![0; (width * height * 4) as usize];
    let left = crop[0].max(offset[0]);
    let right = crop[2].min(offset[0] + view.pixels.width as i64);
    for y in crop[1].max(offset[1])..crop[3].min(offset[1] + view.pixels.height as i64) {
        control.check()?;
        if right <= left {
            break;
        }
        let source = ((y - offset[1]) * view.pixels.width as i64 + left - offset[0]) as usize * 4;
        let target = ((y - crop[1]) * width + left - crop[0]) as usize * 4;
        let len = (right - left) as usize * 4;
        pixels[target..target + len].copy_from_slice(&view.pixels.rgba[source..source + len]);
    }
    Ok(pixels)
}

/// Three PNGs share a pixel grid; structural edits and source identities remain separate.
pub fn compare(
    before: &Document,
    after: &Document,
    before_resources: &Resources,
    after_resources: &Resources,
    options: &Options,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    crate::finite::check(options)
        .map_err(|_| invalid("Comparison option numbers must be finite"))?;
    for (document, resources) in [(before, before_resources), (after, after_resources)] {
        resources.validate()?;
        control.check_resource_paths(resources)?;
        crate::model::validate_controlled(document, control)?;
    }
    if before.id != after.id || before.kind != after.kind {
        return Err(invalid(
            "Visual comparison requires the same document ID and kind",
        ));
    }
    let requested = requested_bounds(before, after, &options.focus, control)?;
    let focus = if matches!(options.focus, previews::Focus::Artboard { .. }) {
        options.focus.clone()
    } else {
        previews::Focus::Canvas
    };
    let mut a = view(
        before,
        before_resources,
        &focus,
        options.scale,
        options.before_render_options,
        control,
    )?;
    let mut b = view(
        after,
        after_resources,
        &focus,
        options.scale,
        options.after_render_options,
        control,
    )?;
    let s = options.scale as f64;
    let shift: [f64; 2] = std::array::from_fn(|i| (b.origin[i] - a.origin[i]) * s);
    // Tolerate only arithmetic roundoff, never an appreciable subpixel resampling.
    if shift.iter().any(|v| (v - v.round()).abs() > 1e-9) {
        return Err(Error::new(
            "INCOMPATIBLE_PIXEL_GRIDS",
            "View origins differ by fractional pixels at this scale; use a compatible scale or compare standalone artboards. No resampling was performed",
        ));
    }
    let offset = shift.map(|v| v.round() as i64);
    let union = [
        0.min(offset[0]),
        0.min(offset[1]),
        (a.pixels.width as i64).max(offset[0] + b.pixels.width as i64),
        (a.pixels.height as i64).max(offset[1] + b.pixels.height as i64),
    ];
    let quantized = requested.map_or(union, |bounds| {
        [
            ((bounds[0] - a.origin[0]) * s).floor() as i64,
            ((bounds[1] - a.origin[1]) * s).floor() as i64,
            ((bounds[2] - a.origin[0]) * s).ceil() as i64,
            ((bounds[3] - a.origin[1]) * s).ceil() as i64,
        ]
    });
    let crop = [
        quantized[0].max(union[0]),
        quantized[1].max(union[1]),
        quantized[2].min(union[2]),
        quantized[3].min(union[3]),
    ];
    if crop[2] <= crop[0] || crop[3] <= crop[1] {
        return Err(Error::new(
            "FOCUS_OUTSIDE_CANVAS",
            "Comparison focus does not intersect the union of rendered canvases",
        ));
    }
    let [width, height] = [(crop[2] - crop[0]) as u32, (crop[3] - crop[1]) as u32];
    if width as u64 * height as u64 > MAX_PIXELS {
        return Err(Error::new(
            "RESOURCE_LIMIT",
            "Common comparison image exceeds pixel budget; choose a region or item focus",
        ));
    }
    let old = aligned(&a, [0, 0], crop, control)?;
    let new = aligned(&b, offset, crop, control)?;
    // Release both full source images before allocating the difference mask.
    a.pixels.rgba = Vec::new();
    b.pixels.rgba = Vec::new();
    let origin = [
        a.origin[0] + crop[0] as f64 / s,
        a.origin[1] + crop[1] as f64 / s,
    ];
    let actual = [
        origin[0],
        origin[1],
        origin[0] + width as f64 / s,
        origin[1] + height as f64 / s,
    ];
    let mut mask = vec![0; old.len()];
    let mut changed = 0u64;
    let mut highlighted = 0u64;
    let mut maximum_delta = 0u8;
    let mut changed_bounds = [width, height, 0, 0];
    let mut highlighted_bounds = changed_bounds;
    for y in 0..height {
        control.check()?;
        for x in 0..width {
            let start = (y as usize * width as usize + x as usize) * 4;
            let delta = (0..4)
                .map(|i| old[start + i].abs_diff(new[start + i]))
                .max()
                .unwrap();
            maximum_delta = maximum_delta.max(delta);
            if delta > 0 {
                changed += 1;
                expand(&mut changed_bounds, x, y);
            }
            if delta > options.threshold {
                highlighted += 1;
                expand(&mut highlighted_bounds, x, y);
                mask[start..start + 4].copy_from_slice(&[255, 0, 255, 255]);
            }
        }
    }
    let changed_bounds = (changed > 0).then_some(changed_bounds);
    let highlighted_bounds = (highlighted > 0).then_some(highlighted_bounds);
    for v in [&mut a, &mut b] {
        let mapping = previews::mapping(v.local_to_world, origin, options.scale, [width, height])?;
        let pixel_to_world: Matrix =
            serde_json::from_value(mapping["pixel_to_world"].clone()).unwrap();
        v.metadata["comparison_mapping"] = mapping;
        v.metadata["changed_world_corners"] =
            json!(changed_bounds.map(|r| corners(pixel_to_world, r)));
        v.metadata["highlighted_world_corners"] =
            json!(highlighted_bounds.map(|r| corners(pixel_to_world, r)));
    }
    let structural = if options.include_structural {
        Some(crate::diff::compare(
            before,
            after,
            before_resources,
            after_resources,
            false,
            control,
        )?)
    } else {
        None
    };
    let result = json!({"version":1,"document_id":before.id,"from_revision":before.revision,"to_revision":after.revision,
        "focus":options.focus,"scale":options.scale,"width":width,"height":height,
        "bounds_space":a.metadata["bounds_space"],"requested_bounds":requested,"actual_bounds":actual,"clipped_to_render":crop!=quantized,
        "before":a.metadata,"after":b.metadata,"structural":structural,
        "pixels":{"changed_pixels":changed,"changed_bounds":changed_bounds,"highlighted_pixels":highlighted,"highlighted_bounds":highlighted_bounds,"maximum_channel_delta":maximum_delta,"threshold":options.threshold},
        "artifacts":{"before":artifact(width,height,&old)?,"after":artifact(width,height,&new)?,"mask":artifact(width,height,&mask)?},
        "source_changed":false,
        "semantics":{"color":"Common sRGB RGBA8 display view. Original output ICC profiles are recorded but not applied. This does not compare print delivery, perceptual color distance, or retained high-precision samples. Each side retains its explicit render/HDR view settings and loss annotations.",
        "alignment":"Document world coordinates, or artboard-local coordinates for a standalone artboard. Union of rendered extents; missing pixels are transparent black. Equal grid phase required (1e-9 pixel arithmetic tolerance). No image registration or resampling.",
        "focus":"Region crops outward on the before grid then clips to the union. Item focus unions unclipped geometry in both revisions (including added/removed/hidden items), excludes strokes/effects, and retains other artwork. Full source rendering limits and costs apply.",
        "mask":"Opaque magenta when maximum absolute RGBA8 channel delta is strictly greater than threshold; transparent black otherwise. Exact changed count/bounds remain independent of threshold. Bounds are end-exclusive.",
        "limitations":"Visual equality does not prove structural equality. Hidden, profile-only, sub-byte and off-view changes require structural or source-sample review; artboard placement is reported through the separate world mappings and structural diff."}});
    control.check()?;
    Ok(result)
}

fn expand(bounds: &mut [u32; 4], x: u32, y: u32) {
    *bounds = [
        bounds[0].min(x),
        bounds[1].min(y),
        bounds[2].max(x + 1),
        bounds[3].max(y + 1),
    ];
}
fn corners(matrix: Matrix, bounds: [u32; 4]) -> [Point; 4] {
    let [x, y, r, b] = bounds.map(|v| v as f64);
    [[x, y], [r, y], [r, b], [x, b]].map(|point| geometry::map(matrix, point))
}
