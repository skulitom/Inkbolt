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

pub(super) fn validate(document: &Document, scale: u32) -> Result<Option<Neighborhood>, Error> {
    let mut radii = Vec::with_capacity(document.items.len());
    let mut filtered = false;
    for item in &document.items {
        if !item.effects.is_empty()
            || item.artwork_mask.is_some()
            || matches!(item.content, Content::Raw { .. } | Content::Object { .. })
        {
            return Err(Error::new("UNSUPPORTED_TILED_RENDER", "Tiled evaluation does not yet support effects, artwork masks, raw development or retained object surfaces").at_item(&item.id));
        }
        let mut radius = 0;
        for filter in &item.filters {
            use crate::filters::{Border, Operator};
            filtered = true;
            let support = match filter.operator {
                Operator::Box { radius } | Operator::Surface { radius, .. } => radius * scale,
                Operator::Gaussian { sigma } => (3.0 * sigma * scale as f64).ceil() as u32,
                Operator::Directional { length, .. } => (length * scale as f64 * 0.5).ceil() as u32 + 1,
                _ => return Err(Error::new("UNSUPPORTED_TILED_RENDER", "Tiled filters currently support box, Gaussian, directional and surface neighborhoods").at_item(&item.id)),
            };
            if filter.border == Border::Wrap {
                return Err(Error::new(
                    "UNSUPPORTED_TILED_RENDER",
                    "Wrapped filter borders require nonlocal viewport access",
                )
                .at_item(&item.id));
            }
            radius += support;
        }
        radii.push(radius);
    }
    if !filtered {
        return Ok(None);
    }
    let mut halo = 0;
    for (i, &radius) in radii.iter().enumerate() {
        let ancestors = scene::ancestors(document, i)?;
        halo = halo.max(radius + ancestors.into_iter().map(|p| radii[p]).sum::<u32>());
    }
    Ok(Some(Neighborhood { halo }))
}

/// A retained output tile depends on the summed support along its source tree.
/// Clip each read to the full evaluation viewport so every filter stage keeps
/// the same real border as whole evaluation. Internal read edges are discarded.
pub(super) struct Neighborhood {
    pub halo: u32,
}
impl Neighborhood {
    pub fn region(
        &self,
        origin: [u32; 2],
        size: [u32; 2],
        extent: [u32; 2],
    ) -> ([u32; 2], [u32; 2]) {
        let start = origin.map(|v| v.saturating_sub(self.halo));
        let end: [u32; 2] =
            std::array::from_fn(|i| (origin[i] + size[i] + self.halo).min(extent[i]));
        (start, std::array::from_fn(|i| end[i] - start[i]))
    }
    pub fn work(
        &self,
        document: &Document,
        texts: &BTreeMap<String, crate::text::Layout>,
        spatial: Option<&super::spatial::Plan>,
        sampling: &crate::render_quality::Plan,
        max_rows: u32,
        control: &crate::control::Control,
    ) -> Result<u64, Error> {
        let scale = sampling.internal_scale;
        let factor = sampling.options.antialias.factor();
        let edge = if spatial.is_some() {
            super::spatial::EDGE
        } else {
            EDGE
        };
        let traversal =
            super::traversal::Plan::new(sampling.output, edge / factor, sampling.scale, max_rows);
        let extent = sampling.evaluation.map(|v| v * scale);
        let mut pixels = vec![0u64; document.items.len()];
        let mut work = 0u64;
        let mut paint_work = 0u64;
        let mut filter_work = 0u64;
        let shape = if crate::knockout::active(document) {
            24
        } else {
            0
        };
        let filter_passes = if shape == 0 { 1 } else { 2 };
        let mut costs = Vec::new();
        for item in &document.items {
            let paint: u64 = match &item.content {
                Content::Adjustment { adjustment } => adjustment.work(),
                Content::Vector { fill, stroke, .. } => fill
                    .iter()
                    .chain(stroke.iter().map(|s| &s.color))
                    .map(crate::paint::work)
                    .sum(),
                Content::Fill { paint, .. } => crate::paint::work(paint),
                Content::Text { .. } | Content::StoryFrame { .. } => texts[&item.id]
                    .paths
                    .iter()
                    .map(|p| crate::paint::work(&p.fill))
                    .sum(),
                _ => 1,
            };
            let paint = paint + 4 * u64::from(item.mask.as_ref().is_some_and(|m| m.enabled));
            let filter = crate::filters::work(item, scale) * filter_passes;
            let passes = 1 + texts.get(&item.id).map_or(0, |t| t.paths.len()) as u64;
            costs.push((2 + passes + paint + filter + shape, paint, filter));
        }
        let generated = if spatial.is_none() {
            crate::strokes::generated_work(document)?
        } else {
            0
        };
        for (position, size) in traversal.tiles() {
            control.check()?;
            let origin = position.map(|v| sampling.offset + v * factor);
            let (origin, size) = self.region(origin, size.map(|v| v * factor), extent);
            let count = u64::from(size[0]) * u64::from(size[1]);
            work += count;
            let tile = spatial.map(|p| p.tile(origin, size));
            let indices: Vec<_> = tile.as_ref().map_or_else(
                || (0..document.items.len()).collect(),
                |t| t.children.values().flatten().copied().collect(),
            );
            for i in indices {
                pixels[i] += count;
                let (cost, paint, filter) = costs[i];
                work += count * cost;
                paint_work += count * paint;
                filter_work += count * filter;
            }
            if spatial.is_none() {
                work += path_work(document, texts, size)?
                    + generated * u64::from(size[1]) * u64::from(size[0].div_ceil(EDGE));
            }
            if work > MAX_RENDER_WORK
                || paint_work > crate::paint::MAX_PAINT_WORK
                || filter_work > crate::filters::MAX_WORK
            {
                return Err(limit(
                    "Filter neighborhoods exceed visited tile work limits",
                ));
            }
        }
        if let Some(spatial) = spatial {
            work = (work + spatial.coverage.work).max(spatial.work);
        }
        work += crate::resample::document_work_for_pixels(document, scale, Some(&pixels))?;
        work += crate::pixel_warps::work_for_pixels(document, scale, Some(&pixels))?;
        if work > MAX_RENDER_WORK {
            return Err(limit(
                "Filter neighborhoods and reconstruction exceed render work limit",
            ));
        }
        Ok(work)
    }
}
