//! Original named viewport containers, nonprinting guides and standalone artboard exports.
use crate::{Document, Error, geometry, layout::Axis, model::*, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{collections::HashSet, path::Path};
pub const MAX_ARTBOARDS: usize = 32;
pub const MAX_GUIDES: usize = 512;
pub const MAX_FRAME_GUIDES: usize = 64;
pub const MAX_BLEED: u32 = 4096;
pub const MAX_BATCH_PIXELS: u64 = 4_194_304;
pub const MAX_BATCH_BYTES: usize = 32 * 1024 * 1024;
pub const MAX_BATCH_WORK: u64 = 134_217_728;

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Role {
    #[default]
    Frame,
    Artboard,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(default, deny_unknown_fields)]
pub struct Insets {
    pub top: u32,
    pub right: u32,
    pub bottom: u32,
    pub left: u32,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Guide {
    pub id: String,
    pub axis: Axis,
    pub position: f64,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Frame {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub logical_size: Option<Point>,
    #[serde(default)]
    pub role: Role,
    pub width: u32,
    pub height: u32,
    #[serde(default)]
    pub bleed: Insets,
    #[serde(default)]
    pub guides: Vec<Guide>,
    #[serde(default)]
    pub background: Option<Color>,
}
impl Frame {
    pub fn size(&self) -> Point {
        self.logical_size
            .unwrap_or([self.width as f64, self.height as f64])
    }
    pub fn geometry(&self) -> Geometry {
        Geometry::Rect {
            x: 0.0,
            y: 0.0,
            width: self.size()[0],
            height: self.size()[1],
        }
    }
    pub fn clip(&self) -> Clip {
        Clip {
            geometry: self.geometry(),
            fill_rule: FillRule::Nonzero,
            transform: identity(),
            enabled: true,
        }
    }
}
pub fn validate(frame: &Frame) -> Result<(), Error> {
    if let Some(size) = frame.logical_size {
        let canvas = crate::vector_canvas::Canvas {
            origin_px: [0.0; 2],
            size_px: size,
            unit: crate::dimensions::Unit::Px,
            process_space: Default::default(),
        };
        if canvas.dimensions()? != [frame.width, frame.height] {
            return Err(invalid(
                "Frame pixel dimensions must equal the ceiling of its logical size",
            ));
        }
    }
    if !(1..=MAX_DIMENSION).contains(&frame.width) || !(1..=MAX_DIMENSION).contains(&frame.height) {
        return Err(invalid("Frame dimensions must be integers in 1..=32768"));
    }
    if [
        frame.bleed.top,
        frame.bleed.right,
        frame.bleed.bottom,
        frame.bleed.left,
    ]
    .iter()
    .any(|&v| v > MAX_BLEED)
    {
        return Err(limit("Bleed must be within 0..=4096 per edge"));
    }
    if frame.role == Role::Frame && frame.bleed != Insets::default() {
        return Err(invalid(
            "Bleed belongs to artboards; ordinary frames require zero bleed",
        ));
    }
    if frame.guides.len() > MAX_FRAME_GUIDES {
        return Err(limit("Frame exceeds 64 guides"));
    }
    let mut ids = HashSet::new();
    for guide in &frame.guides {
        if !valid_id(&guide.id) || !ids.insert(&guide.id) {
            return Err(invalid(
                "Guide IDs must be valid and unique within their frame",
            ));
        }
        if !guide.position.is_finite() || guide.position.abs() > MAX_COORDINATE {
            return Err(invalid("Guide position exceeds coordinate limits"));
        }
    }
    Ok(())
}
pub fn order(document: &Document) -> Vec<usize> {
    fn visit(document: &Document, parent: Option<&str>, out: &mut Vec<usize>) {
        for i in scene::children(document, parent) {
            let item = &document.items[i];
            if matches!(&item.content,Content::Frame{frame} if frame.role==Role::Artboard) {
                out.push(i);
            }
            if item.content.is_container() {
                visit(document, Some(&item.id), out);
            }
        }
    }
    let mut out = Vec::new();
    visit(document, None, &mut out);
    out
}
pub fn inspect(document: &Document) -> Result<Vec<Value>, Error> {
    order(document).iter().enumerate().map(|(ordinal,&i)|{
        let item=&document.items[i];let Content::Frame{frame}=&item.content else{unreachable!()};
        Ok(json!({"id":item.id,"name":item.name,"order":ordinal,"parent":item.parent,"frame":frame,"world_transform":scene::world_transform(document,i)?,"geometry_bounds":scene::bounds(document,i)?}))
    }).collect()
}
pub fn guide_bounds(
    document: &Document,
    frame_id: &str,
    id: &str,
    axis: Axis,
) -> Result<geometry::Bounds, Error> {
    let i = scene::index(document, frame_id)?;
    let Content::Frame { frame } = &document.items[i].content else {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Guide reference requires a frame or artboard",
        ));
    };
    let guide = frame
        .guides
        .iter()
        .find(|g| g.id == id)
        .ok_or_else(|| Error::new("NOT_FOUND", "Guide ID does not exist in this frame"))?;
    let points = match guide.axis {
        Axis::X => [[guide.position, 0.0], [guide.position, frame.size()[1]]],
        Axis::Y => [[0.0, guide.position], [frame.size()[0], guide.position]],
    };
    let m = scene::world_transform(document, i)?;
    let [a, b] = points.map(|p| geometry::map(m, p));
    let n = axis.index();
    if (a[n] - b[n]).abs() > 1e-8 {
        return Err(Error::new(
            "UNSUPPORTED",
            "Guide must be constant along the requested world alignment axis",
        ));
    }
    Ok([
        a[0].min(b[0]),
        a[1].min(b[1]),
        a[0].max(b[0]),
        a[1].max(b[1]),
    ])
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Selection {
    All {},
    Ids { ids: Vec<String> },
    Range { start: usize, end: usize },
}
impl Default for Selection {
    fn default() -> Self {
        Self::All {}
    }
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Format {
    Bmp,
    Tga,
    Png,
    Jpeg,
    Tiff,
    Svg,
}
pub fn select(document: &Document, selection: &Selection) -> Result<Vec<usize>, Error> {
    let order = order(document);
    let chosen = match selection {
        Selection::All {} => order,
        Selection::Ids { ids } => {
            if ids.len() > MAX_ARTBOARDS {
                return Err(limit("Artboard selection exceeds 32 IDs"));
            }
            let mut seen = HashSet::new();
            let mut indices = Vec::new();
            for id in ids {
                if !seen.insert(id) {
                    return Err(
                        Error::new("INVALID_OPERATION", "Artboard IDs must be unique")
                            .at_artboard(id),
                    );
                }
                let i = scene::index(document, id).map_err(|e| e.at_artboard(id))?;
                if !order.contains(&i) {
                    return Err(Error::new(
                        "INVALID_OPERATION",
                        "Selected item is not an artboard",
                    )
                    .at_artboard(id));
                }
                indices.push(i);
            }
            indices
        }
        Selection::Range { start, end } => {
            if start >= end || *end > order.len() {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Artboard range must be nonempty, zero-based, end-exclusive and within the current order",
                ));
            }
            order[*start..*end].to_vec()
        }
    };
    if chosen.is_empty() {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Artboard export requires a nonempty selection",
        ));
    }
    Ok(chosen)
}
fn padding(frame: &Frame, include_bleed: bool) -> Insets {
    if include_bleed {
        frame.bleed
    } else {
        Insets::default()
    }
}
fn dimensions(frame: &Frame, pad: Insets) -> Result<[u32; 2], Error> {
    let width = frame.width + pad.left + pad.right;
    let height = frame.height + pad.top + pad.bottom;
    if width > MAX_DIMENSION || height > MAX_DIMENSION {
        return Err(limit(
            "Artboard including bleed exceeds document dimension limit",
        ));
    }
    Ok([width, height])
}
/// An isolated local-coordinate subtree. Only a clone is shifted; the source is immutable.
pub fn standalone(document: &Document, id: &str, include_bleed: bool) -> Result<Document, Error> {
    crate::validate(document)?;
    let i = scene::index(document, id)?;
    let Content::Frame { frame } = &document.items[i].content else {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Standalone export requires an artboard",
        ));
    };
    if frame.role != Role::Artboard {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Standalone export requires an artboard",
        ));
    }
    let pad = padding(frame, include_bleed);
    let [width, height] = dimensions(frame, pad)?;
    let mut members: HashSet<_> = scene::subtree(document, i).into_iter().collect();
    crate::artwork_masks::include_sources(document, &mut members)?;
    let mut result = document.clone();
    if result.background.as_ref().is_some_and(|b| b.item_id != id) {
        result.background = None;
    }
    result.variants = None;
    result.selection = None;
    result.channels.clear();
    result.ink_recipe = None;
    let logical = [
        frame.size()[0] + (pad.left + pad.right) as f64,
        frame.size()[1] + (pad.top + pad.bottom) as f64,
    ];
    result.vector_canvas = if document.vector_canvas.is_some() || frame.logical_size.is_some() {
        Some(crate::vector_canvas::Canvas {
            origin_px: [0.0; 2],
            size_px: logical,
            unit: document
                .vector_canvas
                .map_or(crate::dimensions::Unit::Px, |c| c.unit),
            process_space: document
                .vector_canvas
                .map_or(Default::default(), |c| c.process_space),
        })
    } else {
        None
    };
    result.width = width;
    result.height = height;
    result.items = document
        .items
        .iter()
        .enumerate()
        .filter(|(i, _)| members.contains(i))
        .map(|(_, item)| item.clone())
        .collect();
    let offset = [1.0, 0.0, 0.0, 1.0, pad.left as f64, pad.top as f64];
    let board_world = scene::world_transform(document, i)?;
    let to_export = geometry::multiply(offset, geometry::inverse(board_world)?);
    for item in &mut result.items {
        // Unlinked masks in a definition use component coordinates. Instances
        // rebase those after placement, so do not treat them as document masks.
        let component =
            crate::instances::source_owner(document, scene::index(document, &item.id)?)?.is_some();
        if let Some(mask) = item.artwork_mask.as_mut() {
            if !mask.linked && !component {
                mask.transform = geometry::multiply(to_export, mask.transform);
            } else if item.id == id {
                mask.transform = geometry::multiply(offset, mask.transform);
            }
        }
        for mask in item
            .mask
            .iter_mut()
            .chain(item.filters.iter_mut().filter_map(|f| f.mask.as_mut()))
        {
            if !mask.linked && !component {
                mask.transform = geometry::multiply(to_export, mask.transform);
            } else if item.id == id {
                mask.transform = geometry::multiply(offset, mask.transform);
            }
        }
        if item.id == id {
            for filter in &mut item.filters {
                if let crate::filters::Operator::Creative { operator } = &mut filter.operator {
                    operator.rebase([pad.left as f64, pad.top as f64]);
                }
                if let crate::filters::Operator::Radial { center, .. } = &mut filter.operator {
                    *center = geometry::map(offset, *center);
                }
                if let crate::filters::Operator::Spatial { operator } = &mut filter.operator
                    && let crate::spatial_filters::Operator::Displace { map, .. } =
                        operator.as_mut()
                {
                    map.transform = geometry::multiply(offset, map.transform);
                }
            }
            item.parent = None;
            item.clip_to = None;
            item.transform = identity();
            if let Some(clip) = &mut item.clip {
                clip.transform = geometry::multiply(offset, clip.transform);
            }
            let Content::Frame { frame } = &mut item.content else {
                unreachable!()
            };
            frame.width = width;
            frame.height = height;
            frame.logical_size = frame.logical_size.map(|_| logical);
            frame.bleed = Insets::default();
            frame.guides.clear();
        } else if item.parent.as_deref() == Some(id) {
            item.transform = geometry::multiply(offset, item.transform);
        }
    }
    crate::validate(&result)?;
    Ok(result)
}
pub struct ExportOptions<'a> {
    pub render_options: Option<&'a crate::render_quality::Options>,
    pub metadata_policy: Option<crate::metadata::Policy>,
    pub image_options: Option<&'a crate::image_io::Options>,
    pub format: Format,
    pub scale: u32,
    pub include_bleed: bool,
    pub asset_root: Option<&'a Path>,
    pub font_root: Option<&'a Path>,
}
pub fn export(
    document: &Document,
    selection: &Selection,
    options: ExportOptions<'_>,
) -> Result<Value, Error> {
    export_controlled(
        document,
        selection,
        options,
        &crate::control::Control::default(),
    )
}
pub fn export_controlled(
    document: &Document,
    selection: &Selection,
    options: ExportOptions<'_>,
    control: &crate::control::Control,
) -> Result<Value, Error> {
    control.check()?;
    crate::image_io::validate_options(
        match options.format {
            Format::Png => crate::ExportFormat::Png,
            Format::Bmp => crate::ExportFormat::Bmp,
            Format::Tga => crate::ExportFormat::Tga,
            Format::Svg => crate::ExportFormat::Svg,
            Format::Jpeg => crate::ExportFormat::Jpeg,
            Format::Tiff => crate::ExportFormat::Tiff,
        },
        options.image_options,
    )?;
    crate::render_quality::validate_format(
        if matches!(options.format, Format::Svg) {
            crate::ExportFormat::Svg
        } else {
            crate::ExportFormat::Png
        },
        options.render_options,
    )?;
    crate::model::validate_controlled(document, control)?;
    let expanded = crate::instances::evaluate(document)?;
    let variants = document.variants.as_ref();
    let document = expanded.as_ref().unwrap_or(document);
    let warped = crate::warps::evaluate_controlled(document, control)?;
    let document = warped.as_ref().unwrap_or(document);
    let repeated = crate::repeats::evaluate(document)?;
    let document = repeated.as_ref().unwrap_or(document);
    let interpolated = crate::interpolation::evaluate(document)?;
    let document = interpolated.as_ref().unwrap_or(document);
    if !(1..=4).contains(&options.scale) {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Export scale must be an integer in 1..=4",
        ));
    }
    if matches!(options.format, Format::Svg)
        && (options.scale != 1 || document.kind != DocumentKind::Vector)
    {
        return Err(Error::new(
            "UNSUPPORTED",
            "Artboard SVG requires a vector document and scale 1",
        ));
    }
    let chosen = select(document, selection)?;
    let mut pixels = 0u64;
    let mut work = 0u64;
    let mut image_pixels = 0u64;
    let mut artwork_copies = 0usize;
    let mut dash_work = 0;
    let mut svg_strokes = 0;
    let mut mesh_pixels = 0;
    // Check the complete range before producing an artifact or allocating output buffers.
    for &i in &chosen {
        control.check()?;
        let item = &document.items[i];
        let Content::Frame { frame } = &item.content else {
            unreachable!()
        };
        let [width, height] = dimensions(frame, padding(frame, options.include_bleed))
            .map_err(|e| e.at_artboard(&item.id))?;
        // SVG retains its own vector budgets; image budgets include every
        // supersampled and padded evaluation pixel, even if subsequently cropped.
        let plan = if matches!(options.format, Format::Svg) {
            None
        } else {
            Some(
                crate::render_quality::Plan::new(
                    width,
                    height,
                    options.scale,
                    options.render_options,
                )
                .map_err(|e| e.at_artboard(&item.id))?,
            )
        };
        let scale = plan.as_ref().map_or(options.scale, |p| p.internal_scale);
        let [width, height] = plan.as_ref().map_or([width, height], |p| p.evaluation);
        let area = width as u64 * height as u64 * scale as u64 * scale as u64;
        let mut members: HashSet<_> = scene::subtree(document, i).into_iter().collect();
        crate::artwork_masks::include_sources(document, &mut members)?;
        let stroke_view = standalone(document, &item.id, options.include_bleed)
            .map_err(|e| e.at_artboard(&item.id))?;
        if matches!(
            options.format,
            Format::Png | Format::Jpeg | Format::Tiff | Format::Bmp | Format::Tga
        ) {
            let (dash, generated) =
                crate::strokes::repeated_work(&stroke_view).map_err(|e| e.at_artboard(&item.id))?;
            dash_work += dash;
            work += height as u64 * scale as u64 * generated;
            crate::strokes::check_work(dash_work, crate::strokes::MAX_RANGE_WORK)
                .map_err(|e| e.at_artboard(&item.id))?;
        } else {
            mesh_pixels += crate::meshes::svg_texture_pixels(&stroke_view)?;
            if mesh_pixels > crate::meshes::MAX_SVG_TEXTURE_PIXELS {
                return Err(
                    limit("Artboard SVG mesh range exceeds texture budget").at_artboard(&item.id)
                );
            }
            svg_strokes +=
                crate::strokes::svg_work(&stroke_view).map_err(|e| e.at_artboard(&item.id))?;
        }
        for &j in &members {
            if let Some(mask) = document.items[j]
                .artwork_mask
                .as_ref()
                .filter(|m| m.enabled)
            {
                let source = scene::subtree(document, scene::index(document, &mask.source)?);
                let copies = source.len();
                match options.format {
                    Format::Png | Format::Jpeg | Format::Tiff | Format::Bmp | Format::Tga => {
                        work += area * (copies as u64 + 4);
                    }
                    Format::Svg => {
                        artwork_copies += copies;
                    }
                }
            }
        }
        if artwork_copies > crate::artwork_masks::MAX_SVG_ITEMS {
            return Err(
                limit("Artboard SVG range exceeds artwork-mask copy budget").at_artboard(&item.id)
            );
        }
        if svg_strokes > crate::strokes::MAX_SVG_RANGE_COMMANDS {
            return Err(limit(
                "Artboard SVG stroke outlines exceed generated-command range budget",
            )
            .at_artboard(&item.id));
        }
        for &j in &members {
            for mask in document.items[j]
                .mask
                .iter()
                .chain(
                    document.items[j]
                        .filters
                        .iter()
                        .filter_map(|f| f.mask.as_ref()),
                )
                .filter(|m| m.enabled)
            {
                let [w, h] = mask.prepared_size();
                let n = w as u64 * h as u64;
                work += n * if mask.feather == 0 {
                    1
                } else {
                    2 * (2 * mask.feather as u64 + 1)
                };
                if matches!(
                    options.format,
                    Format::Png | Format::Jpeg | Format::Tiff | Format::Bmp | Format::Tga
                ) {
                    work += area * 4;
                } else {
                    image_pixels += n;
                }
            }
        }
        if work > MAX_BATCH_WORK {
            return Err(
                limit("Artboard masks exceed preparation or sampling work budget")
                    .at_artboard(&item.id),
            );
        }
        match options.format {
            Format::Png | Format::Jpeg | Format::Tiff | Format::Bmp | Format::Tga => {
                let view = plan
                    .as_ref()
                    .unwrap()
                    .prepare(&stroke_view)
                    .map_err(|e| e.at_artboard(&item.id))?;
                work += crate::resample::document_work(&view, scale)?;
                work += crate::pixel_warps::work(&view, scale)?;
                work += area * crate::knockout::work(&view, scale);
                work += area
                    * members
                        .iter()
                        .map(|&j| crate::effects::work(&document.items[j], scale))
                        .sum::<u64>();
                pixels += area;
                work += area * (members.len() as u64 + u64::from(view.background.is_some()));
                work += area
                    * members
                        .iter()
                        .map(|&j| crate::filters::work(&document.items[j], scale))
                        .sum::<u64>();
                work += area
                    * members
                        .iter()
                        .map(|&j| match &document.items[j].content {
                            Content::Adjustment { adjustment } => adjustment.work(),
                            _ => 0,
                        })
                        .sum::<u64>();
                // Plan::new already checks each board's selected evaluation mode.
                if pixels > MAX_BATCH_PIXELS || work > MAX_BATCH_WORK {
                    return Err(limit("Artboard range exceeds render pixel or work budget")
                        .at_artboard(&item.id));
                }
            }
            Format::Svg => {
                for j in members {
                    if let Content::Image { asset_id, crop, .. } = &document.items[j].content {
                        let source = &document.assets[asset_id];
                        let crop = crate::assets::crop(source.width, source.height, *crop)?;
                        image_pixels += crop.width as u64 * crop.height as u64;
                    }
                }
                if image_pixels > MAX_BATCH_PIXELS {
                    return Err(
                        limit("Artboard SVG range exceeds embedded image copy budget")
                            .at_artboard(&item.id),
                    );
                }
            }
        }
    }
    let mut artifacts = Vec::new();
    let mut bytes = 0;
    for i in chosen {
        control.check()?;
        let item = &document.items[i];
        let Content::Frame { frame } = &item.content else {
            unreachable!()
        };
        let pad = padding(frame, options.include_bleed);
        let standalone = standalone(document, &item.id, options.include_bleed)
            .map_err(|e| e.at_artboard(&item.id))?;
        let mut artifact = crate::publish::export_with_render_options(
            &standalone,
            match options.format {
                Format::Png => crate::ExportFormat::Png,
                Format::Bmp => crate::ExportFormat::Bmp,
                Format::Tga => crate::ExportFormat::Tga,
                Format::Jpeg => crate::ExportFormat::Jpeg,
                Format::Tiff => crate::ExportFormat::Tiff,
                Format::Svg => crate::ExportFormat::Svg,
            },
            options.scale,
            &crate::sessions::Resources {
                asset_root: options.asset_root.map(Path::to_owned),
                font_root: options.font_root.map(Path::to_owned),
            },
            crate::publish::FormatOptions {
                control: Some(control),
                image_options: options.image_options,
                metadata_policy: options.metadata_policy,
                render_options: options.render_options,
                pdf_options: None,
            },
        )
        .map_err(|e| e.at_artboard(&item.id))?;
        if expanded.is_some() && matches!(options.format, Format::Svg) {
            artifact["losses"].as_array_mut().unwrap().push(json!("Component instances export as independent expanded groups. Retain snapshots for shared definitions and local overrides."));
        }
        if warped.is_some() && matches!(options.format, Format::Svg) {
            artifact["losses"].as_array_mut().unwrap().push(json!("Warped geometry exports as certified line segments within its saved local tolerance. Retain snapshots for original geometry and editable map controls."));
        }
        if repeated.is_some() && matches!(options.format, Format::Svg) {
            artifact["losses"].as_array_mut().unwrap().push(json!("Repeat layouts export as ordinary compound geometry. Retain snapshots for editable motif and layout controls."));
        }
        if interpolated.is_some() && matches!(options.format, Format::Svg) {
            artifact["losses"].as_array_mut().unwrap().push(json!("Interpolation objects export as ordinary vector steps. Retain snapshots for endpoints, contour correspondence, spine, orientation and editable interpolation settings."));
        }
        crate::variants::annotate_export(variants, &mut artifact, false);
        bytes += artifact["data"].as_str().map_or(0, str::len);
        if bytes > MAX_BATCH_BYTES {
            return Err(
                limit("Artboard artifacts exceed 32 MiB encoded output budget")
                    .at_artboard(&item.id),
            );
        }
        artifacts.push(json!({"id":item.id,"name":item.name,"logical_size":crate::vector_canvas::logical_size(&standalone),"scale":options.scale,"source_bounds":[-(pad.left as f64),-(pad.top as f64),frame.size()[0]+pad.right as f64,frame.size()[1]+pad.bottom as f64],"trim_box":[pad.left as f64,pad.top as f64,pad.left as f64+frame.size()[0],pad.top as f64+frame.size()[1]],"artifact":artifact}));
    }
    control.check()?;
    Ok(
        json!({"document_id":document.id,"revision":document.revision,"scope":"artboard_subtree_local","include_bleed":options.include_bleed,"coordinate_contract":"Each selected artboard exports its owned subtree in local coordinates. Its placement transform and all ancestor transforms, visibility, clipping and effects are excluded. Its own visibility, opacity, blending, explicit clip and opacity mask remain. Owned unlinked masks convert into the board export coordinate system. Guides do not render. Background extends into requested bleed.","artifacts":artifacts}),
    )
}
