//! Bounded full-canvas review through an immutable projected evaluation copy.
use super::*;
use crate::limits::previews::{MAX_OVERVIEW_AXIS, MIN_OVERVIEW_AXIS};
use geometry::TransformFactor::{Forward, Inverse};

pub(crate) fn plan(
    document: &Document,
    options: &Options,
) -> Result<(render_quality::Plan, f64, Point), Error> {
    let size = options
        .max_size
        .ok_or_else(|| invalid("Overview size is required"))?;
    if size
        .iter()
        .any(|v| !(MIN_OVERVIEW_AXIS..=MAX_OVERVIEW_AXIS).contains(v))
        || !matches!(options.focus, Focus::Canvas)
        || options.scale != 1
        || options.render_options.padding != 0
        || !options.render_options.crop_to_canvas
        || options.render_options.evaluation != render_quality::Evaluation::Whole
    {
        return Err(invalid(&format!(
            "Overview requires canvas focus, max_size axes {MIN_OVERVIEW_AXIS}..={MAX_OVERVIEW_AXIS}, scale 1, zero padding, canvas cropping and whole evaluation"
        )));
    }
    if document.kind != DocumentKind::Vector {
        return Err(Error::new(
            "UNSUPPORTED",
            "Overview currently requires a vector document",
        ));
    }
    let logical = crate::vector_canvas::logical_size(document);
    let mut factor = (size[0] as f64 / logical[0])
        .min(size[1] as f64 / logical[1])
        .min(1.0);
    // A rounded quotient must not create a pixel outside the requested box.
    while (0..2).any(|i| (logical[i] * factor).ceil() > size[i] as f64) {
        factor = factor.next_down();
    }
    let extent = logical.map(|v| v * factor);
    let sampling = render_quality::Plan::new(
        extent[0].ceil() as u32,
        extent[1].ceil() as u32,
        1,
        Some(&options.render_options),
    )?;
    Ok((sampling, factor, extent))
}

fn supported(document: &Document, control: &Control) -> Result<(), Error> {
    if document.background.is_some() || document.ink_recipe.is_some() {
        return Err(Error::new(
            "UNSUPPORTED",
            "Overview does not yet support backgrounds or native ink recipes",
        ));
    }
    for item in &document.items {
        control.check()?;
        if !item.effects.is_empty()
            || !item.filters.is_empty()
            || item.pixel_warp.is_some()
            || item.artwork_mask.is_some()
            || item.hdr_grade.is_some()
            || !matches!(
                item.content,
                Content::Vector { .. }
                    | Content::Group { .. }
                    | Content::Frame { .. }
                    | Content::WorkPath { .. }
                    | Content::Text { .. }
                    | Content::StoryFrame { .. }
                    | Content::Image { .. }
                    | Content::Raster { .. }
                    | Content::Samples { .. }
                    | Content::StoredSamples { .. }
            )
        {
            return Err(Error::new("UNSUPPORTED", "Overview does not yet support this retained content, effects, filters, pixel warps, artwork masks or HDR grades").at_item(&item.id));
        }
        if matches!(&item.content, Content::Vector { stroke: Some(s), .. }
            if s.scaling == crate::strokes::Scaling::Document)
        {
            return Err(Error::new(
                "UNSUPPORTED",
                "Overview currently requires object-scaled strokes",
            )
            .at_item(&item.id));
        }
    }
    Ok(())
}

pub(super) fn preview(
    document: &Document,
    options: &Options,
    asset_root: Option<&Path>,
    font_root: Option<&Path>,
    control: &Control,
) -> Result<Value, Error> {
    let (_, factor, extent) = plan(document, options)?;
    supported(document, control)?;
    let origin = document.vector_canvas.map_or([0.0; 2], |c| c.origin_px);
    let scaling = [factor, 0.0, 0.0, factor, 0.0, 0.0];
    let translation = [1.0, 0.0, 0.0, 1.0, -origin[0], -origin[1]];
    let mut view = document.clone();
    // Scene artboards are nonpainting markers with no children. Their source
    // translation-only contract must not be rewritten as a scaled artboard.
    view.items.retain(
        |i| !matches!(&i.content, Content::Frame { frame } if frame.scope == boards::Scope::Scene),
    );
    for item in &mut view.items {
        control.check()?;
        if item.parent.is_none() {
            item.transform = geometry::transform_expression(&[
                Forward(scaling),
                Forward(translation),
                Forward(item.transform),
            ])?;
        }
        if let Some(mask) = item.mask.as_mut().filter(|m| !m.linked) {
            mask.transform = geometry::transform_expression(&[
                Forward(scaling),
                Forward(translation),
                Forward(mask.transform),
            ])?;
        }
    }
    view.selection = None;
    view.channels.clear();
    view.variants = None;
    [view.width, view.height] = extent.map(|v| v.ceil() as u32);
    view.vector_canvas = Some(crate::vector_canvas::Canvas {
        origin_px: [0.0; 2],
        size_px: extent,
        unit: crate::dimensions::Unit::Px,
        process_space: document
            .vector_canvas
            .map_or(Default::default(), |c| c.process_space),
    });
    // All source validation happened before projection; the temporary copy also
    // retains ordinary matrix, geometry, storage and renderer admission limits.
    crate::model::validate_controlled(&view, control)?;
    let sampling = render_quality::Plan::for_document(&view, 1, Some(&options.render_options))?;
    let pixels = render::rasterize_controlled(
        &view,
        1,
        asset_root,
        font_root,
        Some(&options.render_options),
        control,
    )?;
    let dimensions = [pixels.width, pixels.height];
    // Encoding density describes the sampled view, never a saved document edit.
    view.resolution_ppi = document.resolution_ppi * factor;
    let artifact = render::png_pixels(&view, pixels, 1)?;
    let world_to_pixel = geometry::transform_expression(&[Forward(scaling), Forward(translation)])?;
    let pixel_to_world = geometry::transform_expression(&[
        Forward([1.0, 0.0, 0.0, 1.0, origin[0], origin[1]]),
        Inverse(scaling),
    ])?;
    let [w, h] = dimensions.map(f64::from);
    let corners =
        [[0.0, 0.0], [w, 0.0], [w, h], [0.0, h]].map(|p| geometry::map(pixel_to_world, p));
    let mut receipt = sampling.receipt();
    receipt["source_units_per_pixel"] = json!(1.0 / factor);
    receipt["source_origin"] = json!(origin);
    receipt["source_logical_size"] = json!(crate::vector_canvas::logical_size(document));
    Ok(
        json!({"composition":"vector_overview","bounds_space":"document",
        "requested_bounds":crate::vector_canvas::bounds(document),
        "actual_bounds":[origin[0],origin[1],corners[2][0],corners[2][1]],
        "clipped_to_render":false,"crop_pixels":[0,0,dimensions[0],dimensions[1]],
        "mapping":{"world_to_pixel":world_to_pixel,"pixel_to_world":pixel_to_world,"world_corners":corners,
            "pixel_coordinates":"Pixel edges; centers at (x+0.5,y+0.5).",
            "matrix_convention":"[a,b,c,d,e,f]: (a*x+c*y+e,b*x+d*y+f)"},
        "artifact":artifact,"full_render":receipt,"max_size":options.max_size,"overview_scale":factor,
        "semantics":"Full vector canvas evaluated at reduced density in a temporary copy. No full-size pixel buffer, enlargement or source edit. Ordinary work, memory, matrix and geometry limits remain. Thin details may disappear; use original coordinates and focused full-resolution views for precision decisions."}),
    )
}
