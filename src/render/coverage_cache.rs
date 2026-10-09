//! Prepare shape coverage once, independently of small compositor tile edges.
use super::*;
pub const MAX_PIXELS: u64 = 16_777_216;
#[derive(Default)]
pub(super) struct Coverage {
    origin: [u32; 2],
    size: [u32; 2],
    alpha: Vec<u8>,
}
impl Coverage {
    pub fn at(&self, p: [u32; 2]) -> u8 {
        if p[0] < self.origin[0]
            || p[1] < self.origin[1]
            || p[0] >= self.origin[0] + self.size[0]
            || p[1] >= self.origin[1] + self.size[1]
        {
            return 0;
        }
        self.alpha[((p[1] - self.origin[1]) * self.size[0] + p[0] - self.origin[0]) as usize]
    }
    pub fn mask(&self, origin: [u32; 2], size: [u32; 2]) -> Result<tiny_skia::Mask, Error> {
        let mut mask = tiny_skia::Mask::new(size[0], size[1])
            .ok_or_else(|| limit("Unable to allocate coverage tile"))?;
        for (i, p) in mask.data_mut().iter_mut().enumerate() {
            *p = self.at([
                origin[0] + i as u32 % size[0],
                origin[1] + i as u32 / size[0],
            ]);
        }
        Ok(mask)
    }
}
#[derive(Default)]
pub(super) struct Cache {
    pub paints: BTreeMap<String, Vec<Coverage>>,
    pub clips: BTreeMap<String, Coverage>,
    pub text_clips: BTreeMap<String, Coverage>,
    pub work: u64,
    pub buffer_values: u64,
    pixels: u64,
    largest: u64,
    budget: [u64; 2],
}
impl Cache {
    fn prepare(
        &mut self,
        g: &Geometry,
        world: Matrix,
        rule: FillRule,
        size: [u32; 3],
        antialias: crate::render_quality::Antialias,
    ) -> Result<Coverage, Error> {
        let [width, height, scale] = size;
        // The same output-space f32 path as whole evaluation; translation is
        // only an integer crop of its conservative control bounds.
        let path = coverage_path::path(g, world.map(|v| v * scale as f64))?;
        let b = path.bounds();
        let [x0, y0, x1, y1] = [
            (b.left().floor() as f64 - 2.).clamp(0., width as f64) as u32,
            (b.top().floor() as f64 - 2.).clamp(0., height as f64) as u32,
            (b.right().ceil() as f64 + 2.).clamp(0., width as f64) as u32,
            (b.bottom().ceil() as f64 + 2.).clamp(0., height as f64) as u32,
        ];
        if x1 <= x0 || y1 <= y0 {
            return Ok(Coverage::default());
        }
        let pixels = (x1 - x0) as u64 * (y1 - y0) as u64;
        self.pixels += pixels;
        self.largest = self.largest.max(pixels);
        self.work += pixels + (path.points().len() as u64) * (y1 - y0) as u64;
        if self.pixels > MAX_PIXELS || self.work > self.budget[0] {
            return Err(limit(
                "Prepared coverage exceeds storage or scan work limit",
            ));
        }
        self.buffer_values = (self.pixels + 5 * self.largest).div_ceil(8);
        if self.buffer_values > self.budget[1] {
            return Err(limit(
                "Prepared coverage exceeds remaining render memory limit",
            ));
        }
        let mut pixmap = tiny_skia::Pixmap::new(x1 - x0, y1 - y0)
            .ok_or_else(|| limit("Unable to allocate prepared coverage"))?;
        pixmap.fill_path(
            &path,
            &paint([255; 4], antialias.coverage()),
            match rule {
                FillRule::Nonzero => tiny_skia::FillRule::Winding,
                FillRule::EvenOdd => tiny_skia::FillRule::EvenOdd,
            },
            tiny_skia::Transform::from_translate(-(x0 as f32), -(y0 as f32)),
            None,
        );
        Ok(Coverage {
            origin: [x0, y0],
            size: [x1 - x0, y1 - y0],
            alpha: pixmap.pixels().iter().map(|p| p.alpha()).collect(),
        })
    }
    pub fn new(
        document: &Document,
        texts: &BTreeMap<String, crate::text::Layout>,
        worlds: &[Matrix],
        size: [u32; 3],
        antialias: crate::render_quality::Antialias,
        control: &crate::control::Control,
        budget: [u64; 2],
    ) -> Result<Self, Error> {
        let mut cache = Self {
            budget,
            ..Self::default()
        };
        for (i, item) in document.items.iter().enumerate() {
            control.check()?;
            if !scene::effective_visible(document, i)? {
                continue;
            }
            let mut paints = Vec::new();
            match &item.content {
                Content::Vector {
                    geometry,
                    fill,
                    stroke,
                    fill_rule,
                } if curved(geometry) || stroke.is_some() => {
                    if fill.is_some() {
                        paints
                            .push(cache.prepare(geometry, worlds[i], *fill_rule, size, antialias)?);
                    }
                    if let Some(stroke) = stroke {
                        paints.push(
                            if let Some(g) =
                                crate::strokes::generate_placed(geometry, stroke, worlds[i])?
                            {
                                cache.prepare(
                                    &g,
                                    stroke.scaling.matrix(worlds[i]),
                                    FillRule::Nonzero,
                                    size,
                                    antialias,
                                )?
                            } else {
                                Coverage::default()
                            },
                        );
                    }
                }
                Content::Text { .. } | Content::StoryFrame { .. } => {
                    for glyph in &texts[&item.id].paths {
                        paints.push(cache.prepare(
                            &glyph.geometry,
                            worlds[i],
                            FillRule::Nonzero,
                            size,
                            antialias,
                        )?);
                    }
                    if let Some(g) = crate::text::clip_geometry(&item.content, &texts[&item.id]) {
                        let mask =
                            cache.prepare(&g, worlds[i], FillRule::Nonzero, size, antialias)?;
                        cache.text_clips.insert(item.id.clone(), mask);
                    }
                }
                _ => {}
            }
            if !paints.is_empty() {
                cache.paints.insert(item.id.clone(), paints);
            }
            // Compound clips use the engine's retained boolean coverage
            // evaluator, not the display path backend used by this cache.
            if let Some(clip) = item
                .clip
                .as_ref()
                .filter(|c| c.enabled && !matches!(c.geometry, Geometry::Compound { .. }))
            {
                let mask = cache.prepare(
                    &clip.geometry,
                    geometry::multiply(worlds[i], clip.transform),
                    clip.fill_rule,
                    size,
                    antialias,
                )?;
                cache.clips.insert(item.id.clone(), mask);
            }
        }
        Ok(cache)
    }
}
fn curved(g: &Geometry) -> bool {
    match g {
        Geometry::Ellipse { .. } | Geometry::RoundedRect { .. } => true,
        Geometry::Path { commands } => commands
            .iter()
            .any(|c| matches!(c, PathCommand::Cubic { .. })),
        Geometry::Compound { operands, .. } => operands.iter().any(|v| curved(&v.geometry)),
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn coverage_respects_remaining_preparation_budgets() {
        let g = Geometry::Ellipse {
            cx: 10.,
            cy: 10.,
            rx: 8.,
            ry: 8.,
        };
        for budget in [[0, MAX_BUFFER_PIXELS * 4], [MAX_RENDER_WORK, 0]] {
            let mut cache = Cache {
                budget,
                ..Cache::default()
            };
            let result = cache.prepare(
                &g,
                identity(),
                FillRule::Nonzero,
                [32, 32, 1],
                crate::render_quality::Antialias::Coverage,
            );
            assert!(matches!(result, Err(e) if e.code == "RESOURCE_LIMIT"));
        }
    }
}
