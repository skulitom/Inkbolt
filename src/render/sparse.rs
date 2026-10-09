//! Bounded regional evaluation for ordinary large vector scenes.
use super::*;

struct Region {
    item: usize,
    world: Matrix,
    // Half-open output-pixel rectangle, including conservative coverage padding.
    bounds: [u32; 4],
}
pub(super) struct Plan {
    regions: Vec<Region>,
    pub work: u64,
    pub paint_work: u64,
    pub buffer_pixels: u64,
}
impl Plan {
    pub fn new(
        document: &Document,
        size: [u32; 3],
        control: &crate::control::Control,
    ) -> Result<Option<Self>, Error> {
        if document.resource_profile != ResourceProfile::LargeVector
            || document.background.is_some()
            || document.items.iter().any(|item| {
                item.blend != BlendMode::Normal
                    || !item.coverage.is_smooth()
                    || item.hdr_grade.is_some()
                    || item.pixel_warp.is_some()
                    || !item.effects.is_empty()
                    || !item.filters.is_empty()
                    || item.clip_to.is_some()
                    || item.clip.is_some()
                    || item.mask.is_some()
                    || item.artwork_mask.is_some()
                    || !match &item.content {
                        Content::Vector { geometry, .. } => {
                            !matches!(geometry, Geometry::Compound { .. })
                        }
                        Content::Group {
                            knockout: false, ..
                        } => item.opacity == 1.0 && item.fill_opacity == 1.0,
                        _ => false,
                    }
            })
        {
            return Ok(None);
        }
        let [width, height, scale] = size;
        let mut ordered = Vec::new();
        fn visit(
            document: &Document,
            parent: Option<&str>,
            ordered: &mut Vec<usize>,
            control: &crate::control::Control,
        ) -> Result<(), Error> {
            for i in scene::children(document, parent) {
                control.check()?;
                let item = &document.items[i];
                if !item.visible || item.opacity == 0.0 {
                    continue;
                }
                if matches!(item.content, Content::Group { .. }) {
                    visit(document, Some(&item.id), ordered, control)?;
                } else {
                    ordered.push(i);
                }
            }
            Ok(())
        }
        visit(document, None, &mut ordered, control)?;
        let count = width as u64 * height as u64;
        let mut plan = Self {
            regions: Vec::new(),
            work: count,
            paint_work: 0,
            buffer_pixels: 2 * count,
        };
        let mut largest = 0;
        for i in ordered {
            control.check()?;
            let item = &document.items[i];
            let Content::Vector {
                geometry: shape,
                fill,
                stroke,
                ..
            } = &item.content
            else {
                unreachable!()
            };
            let world = scene::world_transform(document, i)?;
            let mut bounds = [
                f64::INFINITY,
                f64::INFINITY,
                f64::NEG_INFINITY,
                f64::NEG_INFINITY,
            ];
            let mut controls = 0;
            let mut include = |g: &Geometry, matrix: Matrix| {
                let points = geometry::control_points(g);
                controls += if matches!(g, Geometry::Ellipse { .. }) {
                    97
                } else {
                    points.len() as u64
                };
                for point in points {
                    let p = geometry::map(matrix, point).map(|v| v * scale as f64);
                    bounds[0] = bounds[0].min(p[0]);
                    bounds[1] = bounds[1].min(p[1]);
                    bounds[2] = bounds[2].max(p[0]);
                    bounds[3] = bounds[3].max(p[1]);
                }
            };
            if fill.is_some() {
                include(shape, world);
            }
            if let Some(stroke) = stroke
                && let Some(outline) = crate::strokes::generate_placed(shape, stroke, world)?
            {
                include(&outline, stroke.scaling.matrix(world));
            }
            if controls == 0 {
                continue;
            }
            if bounds.iter().any(|v| !v.is_finite()) {
                return Err(limit("Regional coverage bounds are not finite"));
            }
            let bounds = [
                (bounds[0].floor() - 2.0).clamp(0.0, width as f64) as u32,
                (bounds[1].floor() - 2.0).clamp(0.0, height as f64) as u32,
                (bounds[2].ceil() + 2.0).clamp(0.0, width as f64) as u32,
                (bounds[3].ceil() + 2.0).clamp(0.0, height as f64) as u32,
            ];
            let region_height = (bounds[3] - bounds[1]) as u64;
            let area = (bounds[2] - bounds[0]) as u64 * region_height;
            // Scan, paint, composition and path-control work are bounded using
            // the region actually visited, never a discounted full-canvas pass.
            let paints = fill
                .iter()
                .chain(stroke.iter().map(|s| &s.color))
                .collect::<Vec<_>>();
            let paint_work = area * paints.iter().map(|p| crate::paint::work(p)).sum::<u64>();
            plan.paint_work += paint_work;
            plan.work += area * (2 + paints.len() as u64) + paint_work + controls * region_height;
            if plan.work > MAX_RENDER_WORK || plan.paint_work > crate::paint::MAX_PAINT_WORK {
                return Err(limit(
                    "Regional vector evaluation exceeds render or paint work limits",
                ));
            }
            largest = largest.max(area);
            if area != 0 {
                plan.regions.push(Region {
                    item: i,
                    world,
                    bounds,
                });
            }
        }
        plan.buffer_pixels += 2 * largest;
        Ok(Some(plan))
    }
    pub fn render(
        &self,
        document: &Document,
        size: [u32; 3],
        resources: &Resources,
        accum: &mut [f64],
    ) -> Result<(), Error> {
        let [width, _, scale] = size;
        for region in &self.regions {
            resources.control.check()?;
            let item = &document.items[region.item];
            let [x0, y0, x1, y1] = region.bounds;
            let w = x1 - x0;
            let pixels = painted_region(
                item,
                [w, y1 - y0, scale],
                region.world,
                (resources.antialias, resources.linear),
                [x0, y0],
                Some(&resources.control),
                None,
            )?;
            for (i, src) in pixels.as_chunks::<4>().0.iter().enumerate() {
                if i.is_multiple_of(4096) {
                    resources.control.check()?;
                }
                if src[3] == 0.0 {
                    continue;
                }
                let dst = ((y0 as usize + i / w as usize) * width as usize
                    + x0 as usize
                    + i % w as usize)
                    * 4;
                composite(
                    &mut accum[dst..dst + 4],
                    [src[0] / src[3], src[1] / src[3], src[2] / src[3], src[3]],
                    item.opacity * item.fill_opacity,
                    BlendMode::Normal,
                    resources.linear,
                );
            }
        }
        Ok(())
    }
}
