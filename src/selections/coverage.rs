//! Original subrow coverage evaluated one row at a time in the same sum order.
use super::*;

pub(super) struct Rasterizer<'a> {
    boundary: &'a Boundary,
    width: u32,
    height: u32,
    bounds: [u32; 4],
    antialias: bool,
    rule: FillRule,
    subrows: u32,
    values: Vec<f64>,
    crossings: Vec<(f64, i32)>,
}
impl<'a> Rasterizer<'a> {
    pub(super) fn new(
        boundary: &'a Boundary,
        width: u32,
        height: u32,
        antialias: bool,
        rule: FillRule,
        max_work: u64,
    ) -> Result<Self, Error> {
        let g = boundary.geometry()?;
        geometry::validate_geometry(&g)?;
        let b = geometry::bounds(&g, identity());
        let bounds = [
            b[0].floor().clamp(0.0, width as f64) as u32,
            b[1].floor().clamp(0.0, height as f64) as u32,
            b[2].ceil().clamp(0.0, width as f64) as u32,
            b[3].ceil().clamp(0.0, height as f64) as u32,
        ];
        let subrows = if antialias { COVERAGE_SUBROWS } else { 1 };
        let edges = match boundary {
            Boundary::Polygon { points } => points.len() as u64,
            _ => 2,
        };
        if !matches!(boundary, Boundary::Rect { .. }) {
            let work = (bounds[3] - bounds[1]) as u64
                * subrows as u64
                * ((bounds[2] - bounds[0]) as u64 + edges * (edges.ilog2() as u64 + 2));
            if work > max_work {
                return Err(limit("Selection subrow integration exceeds work budget"));
            }
        }
        Ok(Self {
            boundary,
            width,
            height,
            bounds,
            antialias,
            rule,
            subrows,
            values: vec![0.0; width as usize],
            crossings: Vec::with_capacity(edges as usize),
        })
    }
    pub(super) fn read(&mut self, py: u32, output: &mut [u8]) -> Result<(), Error> {
        if py >= self.height || output.len() != self.width as usize {
            return Err(invalid("Selection coverage row is outside the canvas"));
        }
        self.values.fill(0.0);
        let [left, top, right, bottom] = self.bounds;
        if py >= top && py < bottom {
            if let Boundary::Rect {
                x,
                y,
                width: w,
                height: h,
            } = self.boundary
            {
                for px in left..right {
                    self.values[px as usize] = if self.antialias {
                        ((px as f64 + 1.0).min(x + w) - (px as f64).max(*x)).max(0.0)
                            * ((py as f64 + 1.0).min(y + h) - (py as f64).max(*y)).max(0.0)
                    } else {
                        f64::from(
                            px as f64 + 0.5 >= *x
                                && px as f64 + 0.5 < x + w
                                && py as f64 + 0.5 >= *y
                                && py as f64 + 0.5 < y + h,
                        )
                    };
                }
            } else {
                for sub in 0..self.subrows {
                    let y = py as f64 + (sub as f64 + 0.5) / self.subrows as f64;
                    let mut span = |a: f64, b: f64| {
                        let a = a.max(0.0);
                        let b = b.min(self.width as f64);
                        if b <= a {
                            return;
                        }
                        for (x, value) in self
                            .values
                            .iter_mut()
                            .enumerate()
                            .take(b.ceil() as usize)
                            .skip(a.floor() as usize)
                        {
                            let amount = if self.antialias {
                                ((x as f64 + 1.0).min(b) - (x as f64).max(a)).max(0.0)
                            } else {
                                f64::from(x as f64 + 0.5 >= a && x as f64 + 0.5 < b)
                            };
                            *value += amount / self.subrows as f64;
                        }
                    };
                    match self.boundary {
                        Boundary::Ellipse { cx, cy, rx, ry } => {
                            let t = 1.0 - ((y - cy) / ry).powi(2);
                            if t > 0.0 {
                                let r = rx * t.sqrt();
                                span(cx - r, cx + r);
                            }
                        }
                        Boundary::Polygon { points } => {
                            self.crossings.clear();
                            for (a, b) in points
                                .iter()
                                .zip(points.iter().cycle().skip(1))
                                .take(points.len())
                            {
                                if (a[1] <= y && y < b[1]) || (b[1] <= y && y < a[1]) {
                                    self.crossings.push((
                                        a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]),
                                        if b[1] > a[1] { 1 } else { -1 },
                                    ));
                                }
                            }
                            self.crossings.sort_by(|a, b| a.0.total_cmp(&b.0));
                            let mut winding = 0i32;
                            let mut previous = 0.0;
                            for &(x, delta) in &self.crossings {
                                if match self.rule {
                                    FillRule::Nonzero => winding != 0,
                                    FillRule::EvenOdd => winding % 2 != 0,
                                } {
                                    span(previous, x);
                                }
                                winding += delta;
                                previous = x;
                            }
                        }
                        _ => unreachable!(),
                    }
                }
            }
        }
        for (out, v) in output.iter_mut().zip(&self.values) {
            *out = (v.clamp(0.0, 1.0) * 255.0).round() as u8;
        }
        Ok(())
    }
}
