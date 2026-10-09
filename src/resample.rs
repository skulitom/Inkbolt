//! Original bounded separable reconstruction from public mathematical kernels.
use crate::{
    Error,
    assets::{Crop, Sampling},
    geometry,
    model::*,
};

pub const MAX_AXIS_TAPS: u64 = 65_536;
pub const MAX_WORK: u64 = 67_108_864;

#[derive(Clone, Copy)]
pub(crate) struct Plan {
    pub method: Sampling,
    widths: [f64; 2],
    taps: [u64; 2],
}
impl Plan {
    pub fn new(method: Sampling, footprint: [f64; 2]) -> Result<Self, Error> {
        let widths = footprint.map(|v| match method {
            Sampling::Area => v,
            Sampling::Bicubic | Sampling::Lanczos3 => v.max(1.0),
            _ => 1.0,
        });
        if footprint.iter().any(|v| !v.is_finite() || *v <= 0.0) {
            return Err(invalid("Resampling footprint must be finite and positive"));
        }
        let support = match method {
            Sampling::Nearest => 0.0,
            Sampling::Bilinear => 1.0,
            Sampling::Area => 0.5,
            Sampling::Bicubic => 2.0,
            Sampling::Lanczos3 => 3.0,
        };
        let spans = widths.map(|w| (2.0 * support * w).ceil() + 2.0);
        if spans.iter().any(|v| *v > MAX_AXIS_TAPS as f64) {
            return Err(limit("Resampling kernel exceeds per-axis tap limit"));
        }
        let taps = match method {
            Sampling::Nearest => [1, 1],
            Sampling::Bilinear => [2, 2],
            _ => spans.map(|v| v as u64),
        };
        Ok(Self {
            method,
            widths,
            taps,
        })
    }
    pub fn work(self) -> u64 {
        self.taps[0] * self.taps[1] + 4 * (self.taps[0] + self.taps[1])
    }
    fn weights(self, point: f64, axis: usize) -> Result<Vec<(i64, f64)>, Error> {
        if !point.is_finite() || point.abs() > 1e12 {
            return Err(Error::new(
                "RENDER_ERROR",
                "Resampling coordinates exceed stable indexing range",
            ));
        }
        let width = self.widths[axis];
        let radius = width
            * match self.method {
                Sampling::Area => 0.5,
                Sampling::Bicubic => 2.0,
                Sampling::Lanczos3 => 3.0,
                _ => unreachable!("Legacy sampling uses its existing evaluator"),
            };
        let first = (point - radius - 0.5).floor() as i64;
        let last = (point + radius - 0.5).ceil() as i64;
        // Area weights describe unit cells, so include the cell crossing the
        // lower boundary even when its center lies outside the footprint.
        let (first, last) = if self.method == Sampling::Area {
            (
                (point - radius).floor() as i64,
                (point + radius).ceil() as i64 - 1,
            )
        } else {
            (first, last)
        };
        if last < first || (last - first + 1) as u64 > self.taps[axis] {
            return Err(Error::new(
                "RENDER_ERROR",
                "Resampling interval lost precision",
            ));
        }
        let mut result = Vec::with_capacity((last - first + 1) as usize);
        let mut sum = 0.0;
        for i in first..=last {
            let weight = match self.method {
                Sampling::Area => {
                    ((point + radius).min(i as f64 + 1.0) - (point - radius).max(i as f64)).max(0.0)
                }
                Sampling::Bicubic => {
                    let x = ((i as f64 + 0.5 - point) / width).abs();
                    if x < 1.0 {
                        (1.5 * x - 2.5) * x * x + 1.0
                    } else if x < 2.0 {
                        ((-0.5 * x + 2.5) * x - 4.0) * x + 2.0
                    } else {
                        0.0
                    }
                }
                Sampling::Lanczos3 => {
                    let x = (i as f64 + 0.5 - point) / width;
                    if x.abs() < 3.0 {
                        sinc(x) * sinc(x / 3.0)
                    } else {
                        0.0
                    }
                }
                _ => unreachable!(),
            };
            if weight != 0.0 {
                result.push((i, weight));
                sum += weight;
            }
        }
        if !sum.is_finite() || sum <= 0.0 {
            return Err(Error::new(
                "RENDER_ERROR",
                "Resampling weights cannot be normalized",
            ));
        }
        for (_, weight) in &mut result {
            *weight /= sum;
        }
        Ok(result)
    }
    pub fn sample<const N: usize>(
        self,
        point: Point,
        at: impl Fn(i64, i64) -> [f64; N],
    ) -> Result<[f64; N], Error> {
        let xs = self.weights(point[0], 0)?;
        let ys = self.weights(point[1], 1)?;
        let mut value = [0.0; N];
        for (y, wy) in ys {
            for &(x, wx) in &xs {
                let p = at(x, y);
                for c in 0..N {
                    value[c] += p[c] * wx * wy;
                }
            }
        }
        Ok(value)
    }
}
fn sinc(x: f64) -> f64 {
    if x == 0.0 {
        1.0
    } else if x.fract() == 0.0 {
        0.0
    } else {
        let p = std::f64::consts::PI * x;
        p.sin() / p
    }
}

/// The source-axis bounding rectangle of an inverse-mapped output pixel.
/// Exact for axis-aligned/right-angle placement; conservative for shear/rotation.
pub(crate) fn footprint(
    crop: Crop,
    frame: [f64; 2],
    world: Matrix,
    scale: u32,
) -> Result<[f64; 2], Error> {
    let m = geometry::inverse(world)?;
    Ok([
        (m[0].abs() + m[2].abs()) * crop.width as f64 / frame[0] / scale as f64,
        (m[1].abs() + m[3].abs()) * crop.height as f64 / frame[1] / scale as f64,
    ])
}

pub(crate) fn document_work(document: &Document, scale: u32) -> Result<u64, Error> {
    document_work_for_pixels(document, scale, None)
}
pub(crate) fn document_work_for_pixels(
    document: &Document,
    scale: u32,
    regional_pixels: Option<&[u64]>,
) -> Result<u64, Error> {
    let mut work = 0u64;
    let count = document.width as u64 * document.height as u64 * scale as u64 * scale as u64;
    for (i, item) in document.items.iter().enumerate() {
        let (crop, frame, sampling) = match &item.content {
            Content::Raw { raw } => (
                Crop {
                    x: 0,
                    y: 0,
                    width: raw.recipe.capture.width,
                    height: raw.recipe.capture.height,
                },
                [
                    raw.recipe.capture.width as f64,
                    raw.recipe.capture.height as f64,
                ],
                raw.sampling,
            ),
            Content::Object { object } => {
                let d = object.document()?;
                (
                    Crop {
                        x: 0,
                        y: 0,
                        width: d.width * object.surface_scale,
                        height: d.height * object.surface_scale,
                    },
                    [object.width, object.height],
                    object.sampling,
                )
            }
            Content::Samples { grid } => (
                Crop {
                    x: 0,
                    y: 0,
                    width: grid.width,
                    height: grid.height,
                },
                [grid.width as f64, grid.height as f64],
                grid.sampling,
            ),
            Content::StoredSamples { grid } => (
                Crop {
                    x: 0,
                    y: 0,
                    width: grid.base.spec.width,
                    height: grid.base.spec.height,
                },
                [grid.base.spec.width as f64, grid.base.spec.height as f64],
                grid.sampling,
            ),
            Content::Raster {
                width,
                height,
                sampling,
                ..
            } => (
                Crop {
                    x: 0,
                    y: 0,
                    width: *width,
                    height: *height,
                },
                [*width as f64, *height as f64],
                *sampling,
            ),
            Content::Image {
                asset_id,
                width,
                height,
                crop,
                sampling,
            } => {
                let a = &document.assets[asset_id];
                (
                    crate::assets::crop(a.width, a.height, *crop)?,
                    [*width, *height],
                    *sampling,
                )
            }
            _ => continue,
        };
        if !sampling.advanced() {
            continue;
        }
        let plan = Plan::new(
            sampling,
            footprint(
                crop,
                frame,
                crate::scene::world_transform(document, i)?,
                scale,
            )?,
        )
        .map_err(|e| e.at_item(&item.id))?;
        work = work.saturating_add(
            regional_pixels
                .map_or(count, |pixels| pixels[i])
                .saturating_mul(plan.work()),
        );
        if work > MAX_WORK {
            return Err(limit("Render exceeds aggregate reconstruction work limit"));
        }
    }
    Ok(work)
}

/// Shared premultiplied reconstruction followed by straight-alpha recovery.
pub(crate) fn straight(
    point: Point,
    plan: &Plan,
    get: impl Fn(i64, i64) -> [f64; 4],
) -> Result<[f64; 4], Error> {
    straight_range(point, plan, false, get)
}
pub(crate) fn straight_range(
    point: Point,
    plan: &Plan,
    linear: bool,
    get: impl Fn(i64, i64) -> [f64; 4],
) -> Result<[f64; 4], Error> {
    let mut c = associated(point, plan, get)?;
    // Negative-lobed kernels can ring. Project the complete 2D result into
    // valid premultiplied RGBA once, before returning straight color.
    if plan.method.advanced() {
        let alpha = c[3];
        c[3] = c[3].clamp(0.0, 1.0);
        if linear && alpha > 0.0 && alpha != c[3] {
            let ratio = c[3] / alpha;
            for v in &mut c[..3] {
                *v *= ratio;
            }
        }
        if !linear {
            for i in 0..3 {
                c[i] = c[i].clamp(0.0, c[3]);
            }
        }
    }
    if c[3] == 0.0 {
        Ok([0.0; 4])
    } else {
        Ok([c[0] / c[3], c[1] / c[3], c[2] / c[3], c[3]])
    }
}

/// Original separable reconstruction over an associated bounded channel tuple.
pub(crate) fn associated<const N: usize>(
    point: Point,
    plan: &Plan,
    get: impl Fn(i64, i64) -> [f64; N],
) -> Result<[f64; N], Error> {
    Ok(match plan.method {
        Sampling::Nearest => get(
            crate::assets::pixel_index(point[0]),
            crate::assets::pixel_index(point[1]),
        ),
        Sampling::Bilinear => {
            let x = point[0] - 0.5;
            let y = point[1] - 0.5;
            let ix = x.floor() as i64;
            let iy = y.floor() as i64;
            let fx = x - x.floor();
            let fy = y - y.floor();
            let mut c = [0.0; N];
            for (p, w) in [
                (get(ix, iy), (1.0 - fx) * (1.0 - fy)),
                (get(ix + 1, iy), fx * (1.0 - fy)),
                (get(ix, iy + 1), (1.0 - fx) * fy),
                (get(ix + 1, iy + 1), fx * fy),
            ] {
                for i in 0..N {
                    c[i] += p[i] * w;
                }
            }
            c
        }
        _ => plan.sample(point, get)?,
    })
}
