//! Exact topology checks on the generated polygonal profile; no borrowed triangulator.
use super::*;
use num_rational::BigRational as R;
use num_traits::{Signed, Zero};
type Q = [R; 2];
pub(super) struct Profile {
    pub contours: Vec<Vec<Point>>,
    pub edges: usize,
    pub error: f64,
}
fn q(p: Point) -> Q {
    p.map(|v| R::from_float(v).unwrap())
}
fn cross(a: &Q, b: &Q, c: &Q) -> R {
    (&b[0] - &a[0]) * (&c[1] - &a[1]) - (&b[1] - &a[1]) * (&c[0] - &a[0])
}
fn on(a: &Q, b: &Q, p: &Q) -> bool {
    (0..2).all(|i| p[i] >= a[i].clone().min(b[i].clone()) && p[i] <= a[i].clone().max(b[i].clone()))
}
/// A strict interior turn cannot disappear when redundant points on straight
/// segments are removed. Count only those proven vertices while flattening;
/// the first/last points of each contour deliberately contribute nothing here.
#[derive(Default)]
struct TurnBudget {
    contour: Option<usize>,
    previous: Vec<(Point, Q)>,
    confirmed: usize,
}
impl TurnBudget {
    fn point(&mut self, point: Point) -> Result<(), Error> {
        if self.previous.last().is_some_and(|p| p.0 == point) {
            return Ok(());
        }
        let exact = q(point);
        if self.previous.len() == 2 {
            let [a, b] = [&self.previous[0].1, &self.previous[1].1];
            if !cross(a, b, &exact).is_zero() || !on(a, &exact, b) {
                self.confirmed += 1;
                if self.confirmed > MAX_EDGES {
                    return Err(limit("Volume polygonal profiles support at most 128 edges"));
                }
            }
            self.previous.remove(0);
        }
        self.previous.push((point, exact));
        Ok(())
    }
    fn segment(&mut self, segment: &crate::warps::Segment) -> Result<(), Error> {
        if self.contour != Some(segment.contour) {
            self.contour = Some(segment.contour);
            self.previous.clear();
            self.point(segment.from)?;
        }
        self.point(segment.to)
    }
}
fn intersects(a: &Q, b: &Q, c: &Q, d: &Q) -> bool {
    let (u, v, w, z) = (
        cross(a, b, c),
        cross(a, b, d),
        cross(c, d, a),
        cross(c, d, b),
    );
    (u.is_zero() && on(a, b, c))
        || (v.is_zero() && on(a, b, d))
        || (w.is_zero() && on(c, d, a))
        || (z.is_zero() && on(c, d, b))
        || (u.signum() != v.signum()
            && !u.is_zero()
            && !v.is_zero()
            && w.signum() != z.signum()
            && !w.is_zero()
            && !z.is_zero())
}
fn winding(c: &[Q], p: &Q) -> i32 {
    let mut n = 0;
    for (i, a) in c.iter().enumerate() {
        let b = &c[(i + 1) % c.len()];
        let side = cross(a, b, p);
        if a[1] <= p[1] && p[1] < b[1] && side.is_positive() {
            n += 1;
        }
        if b[1] <= p[1] && p[1] < a[1] && side.is_negative() {
            n -= 1;
        }
    }
    n
}
pub(super) fn build(s: &Spec, control: &crate::control::Control) -> Result<Profile, Error> {
    let spec = crate::warps::Spec {
        geometry: s.geometry.clone(),
        fill: Some(Paint::Solid([0, 0, 0, 255])),
        stroke: None,
        fill_rule: s.fill_rule,
        maps: vec![crate::warps::Map::Affine { matrix: identity() }],
        tolerance: s.tolerance,
    };
    let mut turns = TurnBudget::default();
    let flat = crate::warps::plan_observed(&spec, control, &mut |s| turns.segment(s))?;
    let error = flat
        .segments
        .iter()
        .map(|v| v.error_bound)
        .fold(0., f64::max);
    let Geometry::Path { commands } = flat.geometry else {
        unreachable!()
    };
    let mut contours = vec![];
    let mut exact = vec![];
    for c in crate::paths::parse(&commands) {
        control.check()?;
        if !c.closed {
            return Err(invalid("Volume profiles must be explicitly closed"));
        }
        let mut p = vec![c.start];
        p.extend(c.edges.into_iter().map(|e| e.to));
        p.dedup();
        if p.last() == p.first() {
            p.pop();
        }
        let mut values: Vec<_> = p.iter().copied().map(q).collect();
        loop {
            control.check()?;
            if p.len() < 3 {
                return Err(invalid("Volume contours must enclose nonzero area"));
            }
            let redundant = (0..p.len()).find(|&i| {
                cross(
                    &values[(i + p.len() - 1) % p.len()],
                    &values[i],
                    &values[(i + 1) % p.len()],
                )
                .is_zero()
                    && on(
                        &values[(i + p.len() - 1) % p.len()],
                        &values[(i + 1) % p.len()],
                        &values[i],
                    )
            });
            if let Some(i) = redundant {
                p.remove(i);
                values.remove(i);
            } else {
                break;
            }
        }
        contours.push(p);
        exact.push(values);
    }
    let edges: usize = contours.iter().map(Vec::len).sum();
    if edges > MAX_EDGES {
        return Err(limit("Volume polygonal profiles support at most 128 edges"));
    }
    for (ci, c) in exact.iter().enumerate() {
        for (i, a) in c.iter().enumerate() {
            control.check()?;
            let b = &c[(i + 1) % c.len()];
            for (cj, d) in exact.iter().enumerate().skip(ci) {
                for (j, u) in d.iter().enumerate() {
                    if ci == cj && (j <= i || j == i + 1 || (i == 0 && j + 1 == c.len())) {
                        continue;
                    }
                    if intersects(a, b, u, &d[(j + 1) % d.len()]) {
                        return Err(Error::new(
                            "UNSUPPORTED",
                            "Volume polygonal contours may be nested or disjoint but cannot intersect or touch",
                        ));
                    }
                }
            }
        }
    }
    let mut active = vec![];
    for (ci, c) in exact.iter().enumerate() {
        control.check()?;
        let area: R = (0..c.len())
            .map(|i| &c[i][0] * &c[(i + 1) % c.len()][1] - &c[i][1] * &c[(i + 1) % c.len()][0])
            .sum();
        if area.is_zero() {
            return Err(invalid("Volume contour has zero signed area"));
        }
        let sign = if area.is_positive() { 1 } else { -1 };
        let outside: i32 = exact
            .iter()
            .enumerate()
            .filter(|(i, _)| *i != ci)
            .map(|(_, other)| winding(other, &c[0]))
            .sum();
        let filled = |n: i32| match s.fill_rule {
            FillRule::Nonzero => n != 0,
            FillRule::EvenOdd => n % 2 != 0,
        };
        if filled(outside) == filled(outside + sign) {
            continue;
        }
        let mut p = contours[ci].clone();
        let desired = if filled(outside) { -1 } else { 1 };
        if sign != desired {
            p.reverse();
        }
        active.push(p);
    }
    if active.is_empty() {
        return Err(invalid("Volume profile has no filled region"));
    }
    Ok(Profile {
        contours: active,
        edges,
        error,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn streaming_turn_count_is_a_lower_bound_on_closed_integer_contours() {
        let mut state = 19u64;
        for length in 3..=48 {
            for _ in 0..12 {
                let mut points = Vec::new();
                for _ in 0..length {
                    state = state.wrapping_mul(6364136223846793005).wrapping_add(1);
                    points.push([((state >> 32) % 9) as i64, ((state >> 40) % 9) as i64]);
                }
                let mut turns = TurnBudget::default();
                for p in points.iter().chain(points.first()) {
                    turns.point(p.map(|v| v as f64)).unwrap();
                }
                // Independent integer elimination includes the closing seam
                // and repeated endpoints, unlike the streaming lower bound.
                points.dedup();
                if points.len() > 1 && points.first() == points.last() {
                    points.pop();
                }
                loop {
                    if points.len() < 3 {
                        break;
                    }
                    let n = points.len();
                    let redundant = (0..n).find(|&i| {
                        let (a, b, c) = (points[(i + n - 1) % n], points[i], points[(i + 1) % n]);
                        (b[0] - a[0]) * (c[1] - a[1]) == (b[1] - a[1]) * (c[0] - a[0])
                            && (0..2).all(|k| a[k].min(c[k]) <= b[k] && b[k] <= a[k].max(c[k]))
                    });
                    match redundant {
                        Some(i) => {
                            points.remove(i);
                        }
                        None => break,
                    }
                }
                assert!(turns.confirmed <= points.len());
            }
        }
    }
}
