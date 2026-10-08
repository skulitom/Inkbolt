//! Native spatial filters transport ink, coverage and replacement independently.
use super::{Context, Surface};
use crate::{Error, filters::transport, scene};
mod nonlinear;
pub(super) use nonlinear::scratch;

impl Context<'_> {
    pub(super) fn filter(&self, i: usize, surface: &mut Surface) -> Result<(), Error> {
        let item = &self.document.items[i];
        let world = scene::world_transform(self.document, i)?;
        let size = [self.width, self.height, self.scale];
        let n = self.channels();
        for f in item
            .filters
            .iter()
            .filter(|f| f.enabled && f.opacity != 0.0)
        {
            self.control.check()?;
            let mut filtered = if transport::supports(&f.operator) {
                Surface {
                    values: transport::evaluate(
                        &surface.values,
                        size,
                        world,
                        &f.operator,
                        f.border,
                        Some(self.control),
                    )?,
                    removal: transport::evaluate(
                        &surface.removal,
                        size,
                        world,
                        &f.operator,
                        f.border,
                        Some(self.control),
                    )?,
                    shape: surface
                        .shape
                        .as_ref()
                        .map(|s| {
                            transport::evaluate(
                                s,
                                size,
                                world,
                                &f.operator,
                                f.border,
                                Some(self.control),
                            )
                        })
                        .transpose()?,
                    channels: n,
                }
            } else {
                self.nonlinear_filter(surface, &f.operator, f.border, world)?
            };
            // A non-Normal replacement is the native implicit-group blend
            // against the original intrinsic content on transparency. It
            // closes its replacement inks; Normal preserves partial addressing.
            self.apply_blend(&mut filtered, surface, None, f.blend, false)?;
            let mask = f
                .mask
                .as_ref()
                .filter(|m| m.enabled)
                .map(|m| crate::masks::prepare(m, world))
                .transpose()?;
            for (pixel, (dst, src)) in surface
                .values
                .chunks_exact_mut(n + 1)
                .zip(filtered.values.chunks_exact(n + 1))
                .enumerate()
            {
                if pixel.is_multiple_of(4096) {
                    self.control.check()?;
                }
                let q = f.opacity * mask.as_ref().map_or(1.0, |m| m.sample(self.point(pixel)));
                for c in 0..=n {
                    dst[c] = (1.0 - q) * dst[c] + q * src[c];
                }
                // Numerical kernel sums can stray by a few ulps at opaque
                // boundaries. Retain the normalized affine paint invariants.
                dst[n] = dst[n].clamp(0.0, 1.0);
                for c in 0..n {
                    let at = pixel * n + c;
                    surface.removal[at] = ((1.0 - q) * surface.removal[at]
                        + q * filtered.removal[at])
                        .clamp(0.0, dst[n]);
                    dst[c] = dst[c].clamp(0.0, surface.removal[at]);
                }
                if let (Some(shape), Some(after)) = (&mut surface.shape, &filtered.shape) {
                    shape[pixel] = ((1.0 - q) * shape[pixel] + q * after[pixel]).clamp(dst[n], 1.0);
                }
            }
        }
        Ok(())
    }
}
