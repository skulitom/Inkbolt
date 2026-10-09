//! Bounded regional composition over one prepared scene and immutable sources.
use super::*;
pub const MAX_PIXELS: u64 = 16_777_216;
pub const EDGE: u32 = 128;

/// Rebuilding/scanning a coverage path is paid again in every tile column.
/// This remains conservative until paths and regional object indices are cached.
pub(super) fn path_work(
    document: &Document,
    texts: &BTreeMap<String, crate::text::Layout>,
    size: [u32; 2],
) -> Result<u64, Error> {
    fn controls(g: &Geometry) -> u64 {
        match g {
            Geometry::Ellipse { .. } => 97,
            Geometry::Compound { operands, .. } => {
                operands.iter().map(|o| controls(&o.geometry)).sum()
            }
            _ => geometry::control_points(g).len() as u64,
        }
    }
    let mut count = 0;
    for item in &document.items {
        count += match &item.content {
            Content::Vector { geometry, fill, .. } => {
                if fill.is_some() {
                    controls(geometry)
                } else {
                    0
                }
            }
            Content::Frame { .. } => 8, // Background and frame clipping.
            Content::Fill { .. } => 4,
            Content::Samples { .. }
            | Content::StoredSamples { .. }
            | Content::Raster { .. }
            | Content::Image { .. } => {
                crate::pixel_warps::plan(item)?.map_or(4, |p| controls(&p.geometry()))
            }
            _ => 0,
        };
        count += item
            .clip
            .as_ref()
            .map_or(0, |clip| controls(&clip.geometry));
    }
    count += texts
        .values()
        .flat_map(|t| &t.paths)
        .map(|p| controls(&p.geometry))
        .sum::<u64>();
    Ok(count
        .saturating_mul(size[1] as u64)
        .saturating_mul(size[0].div_ceil(EDGE) as u64))
}

pub(super) fn validate(document: &Document) -> Result<(), Error> {
    for item in &document.items {
        if !item.filters.is_empty()
            || !item.effects.is_empty()
            || item.artwork_mask.is_some()
            || matches!(item.content, Content::Raw { .. } | Content::Object { .. })
        {
            return Err(Error::new("UNSUPPORTED_TILED_RENDER", "Tiled evaluation does not yet support neighbourhood filters/effects, artwork masks, raw development or retained object surfaces").at_item(&item.id));
        }
    }
    Ok(())
}
