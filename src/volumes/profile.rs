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
pub(super) fn build(s: &Spec) -> Result<Profile, Error> {
    let spec = crate::warps::Spec {
        geometry: s.geometry.clone(),
        fill: Some(Paint::Solid([0, 0, 0, 255])),
        stroke: None,
        fill_rule: s.fill_rule,
        maps: vec![crate::warps::Map::Affine { matrix: identity() }],
        tolerance: s.tolerance,
    };
    let flat = crate::warps::plan(&spec)?;
    let error = flat
        .segments
        .iter()
        .map(|v| v.error_bound)
        .fold(0., f64::max);
    let Geometry::Path { commands } = flat.geometry else {
        unreachable!()
    };
    let mut contours = vec![];
    for c in crate::paths::parse(&commands) {
        if !c.closed {
            return Err(invalid("Volume profiles must be explicitly closed"));
        }
        let mut p = vec![c.start];
        p.extend(c.edges.into_iter().map(|e| e.to));
        p.dedup();
        if p.last() == p.first() {
            p.pop();
        }
        loop {
            if p.len() < 3 {
                return Err(invalid("Volume contours must enclose nonzero area"));
            }
            let redundant = (0..p.len()).find(|&i| {
                cross(
                    &q(p[(i + p.len() - 1) % p.len()]),
                    &q(p[i]),
                    &q(p[(i + 1) % p.len()]),
                )
                .is_zero()
                    && on(
                        &q(p[(i + p.len() - 1) % p.len()]),
                        &q(p[(i + 1) % p.len()]),
                        &q(p[i]),
                    )
            });
            if let Some(i) = redundant {
                p.remove(i);
            } else {
                break;
            }
        }
        contours.push(p);
    }
    let edges: usize = contours.iter().map(Vec::len).sum();
    if edges > MAX_EDGES {
        return Err(limit("Volume polygonal profiles support at most 128 edges"));
    }
    let exact: Vec<Vec<Q>> = contours
        .iter()
        .map(|c| c.iter().copied().map(q).collect())
        .collect();
    for (ci, c) in exact.iter().enumerate() {
        for (i, a) in c.iter().enumerate() {
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
