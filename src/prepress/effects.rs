//! Native ink decoration driven by shared original scalar effect fields.
use super::{Composition, Context, Error, Surface};
use crate::{effects::Operator, model::*, paint, scene};

impl Context<'_> {
    // Keep conversion in bounded batches, before decoration and compositing.
    fn effect_colors(
        &self,
        source: &Paint,
        world: Matrix,
        mut visit: impl FnMut(usize, &[f64], &[bool], f64),
    ) -> Result<(), Error> {
        let count = (self.width * self.height) as usize;
        if let Some(solid) = self.solid(source)? {
            for pixel in 0..count {
                if pixel.is_multiple_of(4096) {
                    self.control.check()?;
                }
                visit(pixel, &solid.values, &solid.addressed, solid.opacity);
            }
        } else {
            let sampler = paint::Sampler::new(source, world)?;
            let addressed = vec![true; self.channels()];
            let mut values = vec![0.0; self.channels()];
            for start in (0..count).step_by(4096) {
                self.control.check()?;
                let end = (start + 4096).min(count);
                let mut rgb = Vec::with_capacity((end - start) * 3);
                let mut alpha = Vec::with_capacity(end - start);
                for pixel in start..end {
                    let rgba = sampler.sample(self.point(pixel));
                    rgb.extend_from_slice(&rgba[..3]);
                    alpha.push(rgba[3]);
                }
                let converted = self.converter.rgb(&rgb)?;
                for (j, (cmyk, a)) in converted.as_chunks::<4>().0.iter().zip(alpha).enumerate() {
                    values[..4].copy_from_slice(cmyk);
                    visit(start + j, &values, &addressed, a);
                }
            }
        }
        Ok(())
    }

    pub(super) fn decorate(&self, i: usize, surface: &mut Surface) -> Result<(), Error> {
        let item = &self.document.items[i];
        if !item.effects.iter().any(|e| e.enabled) {
            // Preserve the previous no-effect arithmetic in apply_coverage.
            return Ok(());
        }
        self.control.check()?;
        let n = self.channels();
        let size = [self.width, self.height, self.scale];
        let world = scene::world_transform(self.document, i)?;
        let alpha: Vec<f64> = surface.values.chunks_exact(n + 1).map(|p| p[n]).collect();
        let shape = surface.shape.clone();
        let mut behind = Surface::new(alpha.len(), n, false, self.track_shape);
        // Every decoration samples the immutable source coverage, not a
        // preceding effect. Shape runs the same field with content fill one.
        for phase in 0..3 {
            if phase == 1 {
                for (pixel, src) in surface.values.chunks_exact_mut(n + 1).enumerate() {
                    if pixel.is_multiple_of(4096) {
                        self.control.check()?;
                    }
                    for value in src {
                        *value *= item.fill_opacity;
                    }
                    for removed in &mut surface.removal[pixel * n..(pixel + 1) * n] {
                        *removed *= item.fill_opacity;
                    }
                }
            }
            for e in item.effects.iter().filter(|e| {
                e.enabled
                    && match e.operator {
                        Operator::Shadow { .. } | Operator::LitShadow { .. } => phase == 0,
                        Operator::Overlay {} => phase == 1,
                        Operator::Stroke { .. } => phase == 2,
                    }
            }) {
                let field = e.field(&alpha, size, self.document.global_light, self.control)?;
                let shape_field = shape
                    .as_ref()
                    .map(|a| e.field(a, size, self.document.global_light, self.control))
                    .transpose()?;
                let target = if phase == 0 {
                    &mut behind
                } else {
                    &mut *surface
                };
                self.effect_colors(&e.color, world, |pixel, values, addressed, opacity| {
                    let q = opacity * e.opacity;
                    if phase == 1 {
                        let src = &mut target.values[pixel * (n + 1)..(pixel + 1) * (n + 1)];
                        let a = src[n];
                        let replacement = field[pixel];
                        for c in 0..n {
                            let removed = &mut target.removal[pixel * n + c];
                            // An overlay replaces a conditional silhouette.
                            // Overprinted inks retain its current conditional
                            // fractions as a contour changes that silhouette's
                            // alpha, including its ambient-ink contribution.
                            let (color, removal) = if addressed[c] {
                                (values[c] * replacement, replacement)
                            } else if a != 0.0 {
                                (src[c] / a * replacement, *removed / a * replacement)
                            } else {
                                (0.0, 0.0)
                            };
                            src[c] = (1.0 - q) * src[c] + q * color;
                            *removed = (1.0 - q) * *removed + q * removal;
                        }
                        src[n] = (1.0 - q) * a + q * replacement;
                        if let Some(shape) = &mut target.shape {
                            shape[pixel] =
                                (1.0 - q) * shape[pixel] + q * shape_field.as_ref().unwrap()[pixel];
                        }
                    } else {
                        let previous_shape = target.shape.as_ref().map(|s| s[pixel]);
                        target.paint(pixel, values, addressed, q * field[pixel]);
                        if let (Some(shape), Some(before)) = (&mut target.shape, previous_shape) {
                            shape[pixel] =
                                before + (1.0 - before) * q * shape_field.as_ref().unwrap()[pixel];
                        }
                    }
                })?;
            }
            if phase == 1 {
                self.combine(&mut behind, surface, Composition::Over)?;
                std::mem::swap(&mut behind, surface);
            }
        }
        if let Some(shape) = &mut surface.shape {
            for (pixel, (f, src)) in shape
                .iter_mut()
                .zip(surface.values.chunks_exact(n + 1))
                .enumerate()
            {
                if pixel.is_multiple_of(4096) {
                    self.control.check()?;
                }
                *f = f.max(src[n]);
            }
        }
        if item.content.is_isolated() {
            for (pixel, (src, removed)) in surface
                .values
                .chunks_exact(n + 1)
                .zip(surface.removal.chunks_exact_mut(n))
                .enumerate()
            {
                if pixel.is_multiple_of(4096) {
                    self.control.check()?;
                }
                removed.fill(src[n]);
            }
        }
        Ok(())
    }
}
