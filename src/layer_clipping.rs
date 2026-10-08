//! Stable sibling relationships for alpha-preserving layer clipping groups.
use crate::{Error, model::*, scene};

pub(crate) fn drawable(content: &Content) -> bool {
    !matches!(
        content,
        Content::Adjustment { .. }
            | Content::WorkPath { .. }
            | Content::MaskSource {}
            | Content::Group {
                isolated: false,
                ..
            }
    )
}
pub(crate) fn auxiliary(content: &Content) -> bool {
    matches!(content, Content::WorkPath { .. } | Content::MaskSource {})
        || matches!(content,Content::Adjustment { adjustment } if adjustment.clip_to.is_some())
}
pub(crate) fn validate(document: &Document) -> Result<(), Error> {
    for (i, item) in document.items.iter().enumerate() {
        let Some(base_id) = &item.clip_to else {
            continue;
        };
        if document.kind != DocumentKind::Raster || !drawable(&item.content) {
            return Err(Error::new(
                "UNSUPPORTED",
                "Layer clipping requires a raster drawable or isolated container",
            )
            .at_item(&item.id));
        }
        let siblings = scene::children(document, item.parent.as_deref());
        let position = siblings.iter().position(|&j| j == i).unwrap();
        let base = siblings[..position].iter().rev().find(|&&j| {
            let candidate = &document.items[j];
            candidate.clip_to.is_none() && !auxiliary(&candidate.content)
        });
        if base.is_none_or(|&j| {
            document.items[j].id != *base_id || !drawable(&document.items[j].content)
        }) {
            return Err(invalid("Clipped layers must reference the base of their contiguous preceding sibling clipping group").at_item(&item.id));
        }
    }
    Ok(())
}
pub(crate) fn needs_buffer(item: &Item) -> bool {
    item.content.is_isolated()
        || matches!(
            item.content,
            Content::Group {
                isolated: false,
                ..
            }
        ) && (item.content.is_knockout()
            || item.opacity != 1.0
            || item.clip.as_ref().is_some_and(|c| c.enabled)
            || item.mask.as_ref().is_some_and(|m| m.enabled)
            || item.artwork_mask.as_ref().is_some_and(|m| m.enabled))
}
