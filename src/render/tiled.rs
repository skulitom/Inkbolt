//! Bounded regional composition over one prepared scene and immutable sources.
use super::*;
pub use crate::limits::render_tiled::EDGE;
pub use crate::limits::render_tiled::MAX_PIXELS;

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

pub(super) fn local_support(operator: &crate::filters::Operator, scale: u32) -> Option<u32> {
    use crate::filters::Operator;
    Some(match *operator {
        Operator::Box { radius } | Operator::Surface { radius, .. } => radius * scale,
        Operator::Gaussian { sigma } => (3.0 * sigma * scale as f64).ceil() as u32,
        Operator::Directional { length, .. } => (length * scale as f64 * 0.5).ceil() as u32 + 1,
        Operator::Detail { ref operator } => {
            use crate::detail_filters::Operator as Detail;
            match **operator {
                Detail::Sharpen { .. } => scale,
                Detail::Unsharp { sigma, .. } => (3.0 * sigma * scale as f64).ceil() as u32,
                Detail::Median { radius } => radius * scale,
                Detail::Noise { .. } => 0,
            }
        }
        Operator::Spatial { ref operator } => {
            use crate::spatial_filters::Operator as Spatial;
            match **operator {
                Spatial::Offset { offset } | Spatial::Displace { amount: offset, .. } => {
                    (offset[0].abs().max(offset[1].abs()) * scale as f64).ceil() as u32 + 1
                }
                Spatial::Mosaic { size } => {
                    if size == 1 {
                        0
                    } else {
                        size * scale - 1
                    }
                }
            }
        }
        Operator::Creative { ref operator } => {
            use crate::creative_filters::Operator as Creative;
            match **operator {
                Creative::Relief { distance, .. } => (distance * scale as f64).ceil() as u32 + 1,
                Creative::HighPass { sigma } => (3.0 * sigma * scale as f64).ceil() as u32,
                Creative::Extrema { radius, .. } => radius * scale,
                Creative::ToneFold { .. } | Creative::ValueField { .. } => 0,
                Creative::EdgeInk { .. } => scale,
                Creative::StrokeRank { radius, .. } => radius * scale + 1,
                Creative::FieldRepair { .. } => 1,
                Creative::Twist { .. } => return None,
            }
        }
        Operator::Radial { .. } => return None,
    })
}

pub(super) fn validate(
    document: &Document,
    scale: u32,
    control: &crate::control::Control,
) -> Result<Option<Neighborhood>, Error> {
    let mut radii = Vec::with_capacity(document.items.len());
    let mut needed = false;
    let mut nonlocal = false;
    for item in &document.items {
        if item.artwork_mask.is_some()
            || matches!(item.content, Content::Raw { .. } | Content::Object { .. })
        {
            return Err(Error::new("UNSUPPORTED_TILED_RENDER", "Tiled evaluation does not yet support artwork masks, raw development or retained object surfaces").at_item(&item.id));
        }
        let mut radius = 0;
        for filter in &item.filters {
            use crate::filters::Border;
            needed = true;
            let support = local_support(&filter.operator, scale);
            nonlocal |= support.is_none();
            if filter.border == Border::Wrap {
                return Err(Error::new(
                    "UNSUPPORTED_TILED_RENDER",
                    "Wrapped filter borders require nonlocal viewport access",
                )
                .at_item(&item.id));
            }
            radius += support.unwrap_or(0);
        }
        needed |= !item.effects.is_empty();
        radius += crate::effects::support(item, scale, document.global_light);
        radii.push(radius);
    }
    if !needed {
        return Ok(None);
    }
    let mut halo = 0;
    for (i, &radius) in radii.iter().enumerate() {
        let ancestors = scene::ancestors(document, i)?;
        halo = halo.max(radius + ancestors.into_iter().map(|p| radii[p]).sum::<u32>());
    }
    Ok(Some(Neighborhood {
        halo,
        mapping: if nonlocal {
            Some(super::filter_regions::Plan::new(document, scale, control)?)
        } else {
            None
        },
    }))
}

/// A retained output tile depends on the summed support along its source tree.
/// Clip each read to the full evaluation viewport so every filter stage keeps
/// the same real border as whole evaluation. Internal read edges are discarded.
pub(super) struct Neighborhood {
    halo: u32,
    mapping: Option<super::filter_regions::Plan>,
}
impl Neighborhood {
    pub fn buffer_values(&self) -> u64 {
        self.mapping.as_ref().map_or(0, |m| m.buffer_values)
    }
    pub fn region(
        &self,
        origin: [u32; 2],
        size: [u32; 2],
        extent: [u32; 2],
        control: &crate::control::Control,
    ) -> Result<([u32; 2], [u32; 2]), Error> {
        if let Some(mapping) = &self.mapping {
            return mapping.region(origin, size, extent, control);
        }
        let start = origin.map(|v| v.saturating_sub(self.halo));
        let end: [u32; 2] =
            std::array::from_fn(|i| (origin[i] + size[i] + self.halo).min(extent[i]));
        Ok((start, std::array::from_fn(|i| end[i] - start[i])))
    }
    pub fn work(
        &self,
        document: &Document,
        texts: &BTreeMap<String, crate::text::Layout>,
        spatial: Option<&super::spatial::Plan>,
        sampling: &crate::render_quality::Plan,
        max_rows: u32,
        control: &crate::control::Control,
    ) -> Result<(u64, u64), Error> {
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
        let mut peak_pixels = 0u64;
        let mut paint_work = 0u64;
        let mut filter_work = 0u64;
        let mut effect_work = 0u64;
        let shape = if crate::knockout::active(document) {
            24
        } else {
            0
        };
        let shape_passes = if shape == 0 { 1 } else { 2 };
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
            let filter = crate::filters::work(item, scale) * shape_passes;
            let effect = crate::effects::work(item, scale) * shape_passes;
            let passes = 1 + texts.get(&item.id).map_or(0, |t| t.paths.len()) as u64;
            costs.push((
                2 + passes + paint + filter + effect + shape,
                paint,
                filter,
                effect,
            ));
        }
        let generated = if spatial.is_none() {
            crate::strokes::generated_work(document)?
        } else {
            0
        };
        for (position, size) in traversal.tiles() {
            control.check()?;
            work += self.mapping.as_ref().map_or(0, |m| m.work);
            if work > MAX_RENDER_WORK {
                return Err(limit("Filter source mapping exceeds render work limit"));
            }
            let origin = position.map(|v| sampling.offset + v * factor);
            let (origin, size) = self.region(origin, size.map(|v| v * factor), extent, control)?;
            let count = u64::from(size[0]) * u64::from(size[1]);
            peak_pixels = peak_pixels.max(count);
            work += count;
            let tile = spatial.map(|p| p.tile(origin, size));
            let indices: Vec<_> = tile.as_ref().map_or_else(
                || (0..document.items.len()).collect(),
                |t| t.children.values().flatten().copied().collect(),
            );
            for i in indices {
                pixels[i] += count;
                let (cost, paint, filter, effect) = costs[i];
                work += count * cost;
                paint_work += count * paint;
                filter_work += count * filter;
                effect_work += count * effect;
            }
            if spatial.is_none() {
                work += path_work(document, texts, size)?
                    + generated * u64::from(size[1]) * u64::from(size[0].div_ceil(EDGE));
            }
            if work > MAX_RENDER_WORK
                || paint_work > crate::paint::MAX_PAINT_WORK
                || filter_work > crate::filters::MAX_WORK
                || effect_work > crate::effects::MAX_WORK
            {
                return Err(limit(
                    "Filter/effect neighborhoods exceed visited tile work limits",
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
                "Filter/effect neighborhoods and reconstruction exceed render work limit",
            ));
        }
        Ok((work, peak_pixels))
    }
}
