//! Non-owning, axis-aligned views over a single editable vector scene.
use super::*;

pub(super) fn is_view(item: &Item) -> bool {
    matches!(&item.content, Content::Frame { frame } if frame.scope == Scope::Scene)
}

pub(crate) fn validate_item(document: &Document, item: &Item) -> Result<(), Error> {
    if !is_view(item) {
        return Ok(());
    }
    if document.kind != DocumentKind::Vector
        || item.parent.is_some()
        || document
            .items
            .iter()
            .any(|child| child.parent.as_deref() == Some(&item.id))
    {
        return Err(invalid(
            "Scene artboards require a vector document, no parent and no owned children",
        )
        .at_item(&item.id));
    }
    if item.transform[..4] != [1.0, 0.0, 0.0, 1.0] {
        return Err(Error::new("UNSUPPORTED", "Scene artboards support translation only; move or resize the viewport without transforming artwork").at_item(&item.id));
    }
    if !item.visible
        || item.opacity != 1.0
        || item.fill_opacity != 1.0
        || !item.coverage.is_smooth()
        || item.blend != BlendMode::Normal
        || item.clip.is_some()
        || item.clip_to.is_some()
        || item.mask.is_some()
        || item.artwork_mask.is_some()
        || !item.filters.is_empty()
        || !item.effects.is_empty()
        || item.hdr_grade.is_some()
        || item.pixel_warp.is_some()
    {
        return Err(invalid("Scene artboards are nonpainting viewport markers: visible, full opacity, normal blending and no appearance modifiers").at_item(&item.id));
    }
    Ok(())
}

pub(super) fn standalone(
    document: &Document,
    i: usize,
    frame: &Frame,
    pad: Insets,
    dimensions: [u32; 2],
) -> Result<Document, Error> {
    let position = document.items[i].transform;
    let mut result = crate::vector_canvas::translated(
        document,
        [pad.left as f64 - position[4], pad.top as f64 - position[5]],
    )?;
    result.items.retain(|item| !is_view(item));
    result.width = dimensions[0];
    result.height = dimensions[1];
    result.selection = None;
    result.channels.clear();
    result.ink_recipe = None;
    result.vector_canvas = Some(crate::vector_canvas::Canvas {
        origin_px: [0.0; 2],
        size_px: [
            frame.size()[0] + (pad.left + pad.right) as f64,
            frame.size()[1] + (pad.top + pad.bottom) as f64,
        ],
        unit: document
            .vector_canvas
            .map_or(crate::dimensions::Unit::Px, |c| c.unit),
        process_space: document
            .vector_canvas
            .map_or(Default::default(), |c| c.process_space),
    });
    crate::validate(&result)?;
    Ok(result)
}
