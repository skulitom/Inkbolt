//! The ordinary homotopy predicates, evaluated in exact quadratic fields.
use super::*;
use scalar::{combined_sign, compare};

struct View {
    c: CubicQ,
    d: R,
    chord: Segment,
    suggestions: Cubic,
}
impl View {
    fn new(arc: &Arc) -> Self {
        let (c, d, root) = match &arc.curve {
            Curve::Rational(c) => (
                (**c).clone().map(|p| p.map(Q::rational)),
                n(0),
                (n(0), n(0)),
            ),
            Curve::Quadratic(span) => (span.controls.clone(), span.d.clone(), span.root.clone()),
        };
        // Midpoints supply candidate separating directions only. Every proposed
        // direction is subsequently checked against all exact control values.
        let suggestions = std::array::from_fn(|i| {
            std::array::from_fn(|j| {
                let bounds = c[i][j].enclosure(&root);
                (bounds.0 + bounds.1) / n(2)
            })
        });
        Self {
            c,
            d,
            chord: arc.chord(),
            suggestions,
        }
    }
    fn monotone(&self, direction: &P) -> bool {
        dot(&sub(&self.chord[1], &self.chord[0]), direction) > n(0)
            && self.c.windows(2).all(|v| {
                projected(&difference(&v[1], &v[0]), direction).sign(&self.d) != Ordering::Less
            })
    }
    fn projections(&self, direction: &P) -> (Q, Q) {
        let values = self.c.clone().map(|p| projected(&p, direction));
        (
            values
                .iter()
                .min_by(|a, b| a.cmp(b, &self.d))
                .unwrap()
                .clone(),
            values
                .iter()
                .max_by(|a, b| a.cmp(b, &self.d))
                .unwrap()
                .clone(),
        )
    }
}
fn directions(views: &[&View]) -> Vec<P> {
    let mut out = vec![[n(1), n(0)], [n(0), n(1)]];
    for view in views {
        for i in 0..4 {
            for j in i + 1..4 {
                let v = sub(&view.suggestions[j], &view.suggestions[i]);
                if v != [n(0), n(0)] {
                    out.push([-v[1].clone(), v[0].clone()]);
                }
            }
        }
    }
    out
}
fn separated(a: &View, b: &View, budget: &mut Budget) -> Result<bool, Error> {
    for normal in directions(&[a, b]) {
        budget.spend(crate::limits::booleans_quadratic_predicates::SEPARATING_AXIS_WORK)?;
        let (amin, amax) = a.projections(&normal);
        let (bmin, bmax) = b.projections(&normal);
        let ab = compare(&amax, &a.d, &bmin, &b.d);
        let ba = compare(&bmax, &b.d, &amin, &a.d);
        if ab == Ordering::Less || ba == Ordering::Less {
            return Ok(true);
        }
        let plane = if ab == Ordering::Equal {
            Some((&amax, &a.d))
        } else if ba == Ordering::Equal {
            Some((&amin, &a.d))
        } else {
            None
        };
        if let Some((plane, d)) = plane {
            let tangent = [-normal[1].clone(), normal[0].clone()];
            let face = |view: &View| {
                view.chord
                    .iter()
                    .filter(|p| {
                        compare(&Q::rational(dot(p, &normal)), &n(0), plane, d) == Ordering::Equal
                    })
                    .map(|p| dot(p, &tangent))
                    .collect::<Vec<_>>()
            };
            let af = face(a);
            let bf = face(b);
            if af.is_empty() || bf.is_empty() {
                return Ok(true);
            }
            let lo = af.iter().min().unwrap().max(bf.iter().min().unwrap());
            let hi = af.iter().max().unwrap().min(bf.iter().max().unwrap());
            if lo > hi {
                return Ok(true);
            }
            if lo == hi
                && a.chord.iter().any(|p| {
                    b.chord.contains(p)
                        && compare(&Q::rational(dot(p, &normal)), &n(0), plane, d)
                            == Ordering::Equal
                        && dot(p, &tangent) == *lo
                })
            {
                return Ok(true);
            }
        }
    }
    Ok(false)
}
fn paired(a: &View, b: &View, budget: &mut Budget) -> Result<bool, Error> {
    for reverse in [false, true] {
        let mut b = View {
            c: b.c.clone(),
            d: b.d.clone(),
            chord: b.chord.clone(),
            suggestions: b.suggestions.clone(),
        };
        if reverse {
            b.c.reverse();
            b.chord.reverse();
            b.suggestions.reverse();
        }
        let mut directions = vec![[n(1), n(0)], [n(0), n(1)]];
        for i in 0..2 {
            let delta = sub(&b.chord[i], &a.chord[i]);
            if delta != [n(0), n(0)] {
                directions.push([-delta[1].clone(), delta[0].clone()]);
            }
        }
        for mut direction in directions {
            budget.spend(crate::limits::booleans_quadratic_predicates::PAIRED_COORDINATE_WORK)?;
            if dot(&sub(&a.chord[1], &a.chord[0]), &direction) < n(0) {
                direction = direction.map(|v| -v);
            }
            if !a.monotone(&direction)
                || !(0..4).all(|i| {
                    compare(
                        &projected(&a.c[i], &direction),
                        &a.d,
                        &projected(&b.c[i], &direction),
                        &b.d,
                    ) == Ordering::Equal
                })
            {
                continue;
            }
            let normal = [-direction[1].clone(), direction[0].clone()];
            let signs: [Ordering; 4] = std::array::from_fn(|i| {
                compare(
                    &projected(&b.c[i], &normal),
                    &b.d,
                    &projected(&a.c[i], &normal),
                    &a.d,
                )
            });
            if (signs.iter().all(|s| *s != Ordering::Less)
                || signs.iter().all(|s| *s != Ordering::Greater))
                && (signs[0] != Ordering::Equal || signs[3] != Ordering::Equal)
            {
                return Ok(true);
            }
        }
    }
    Ok(false)
}
fn outside(p: &P, view: &View, budget: &mut Budget) -> Result<bool, Error> {
    for direction in directions(&[view]) {
        budget.spend(crate::limits::booleans_quadratic_predicates::OUTSIDE_HULL_WORK)?;
        let projected = Q::rational(dot(p, &direction));
        let (lo, hi) = view.projections(&direction);
        if projected.cmp(&lo, &view.d) == Ordering::Less
            || projected.cmp(&hi, &view.d) == Ordering::Greater
        {
            return Ok(true);
        }
    }
    Ok(false)
}
fn cross_sign(a: &PointQ, d: &R, b: &PointQ, e: &R) -> Ordering {
    let x = a[0].scale(&b[1].a).sub(&a[1].scale(&b[0].a));
    let y = a[0].scale(&b[1].b).sub(&a[1].scale(&b[0].b));
    combined_sign(&x, &y, d, e)
}
fn transverse(a: &View, b: &View, budget: &mut Budget) -> Result<Option<bool>, Error> {
    budget.spend(crate::limits::booleans_quadratic_predicates::TRANSVERSE_WORK)?;
    let mut signs = vec![];
    for aa in a.c.windows(2) {
        for bb in b.c.windows(2) {
            signs.push(cross_sign(
                &difference(&aa[1], &aa[0]),
                &a.d,
                &difference(&bb[1], &bb[0]),
                &b.d,
            ));
        }
    }
    if signs.iter().all(|s| *s == Ordering::Equal)
        || !(signs.iter().all(|s| *s != Ordering::Less)
            || signs.iter().all(|s| *s != Ordering::Greater))
    {
        return Ok(None);
    }
    for p in &a.chord {
        if !outside(p, b, budget)? {
            return Ok(None);
        }
    }
    for p in &b.chord {
        if !outside(p, a, budget)? {
            return Ok(None);
        }
    }
    let hits = intersections(&a.chord, &b.chord);
    if hits.is_empty() {
        return Ok(Some(false));
    }
    if hits.len() == 1
        && hits
            .iter()
            .all(|(a, b)| *a > n(0) && *a < n(1) && *b > n(0) && *b < n(1))
    {
        return Ok(Some(true));
    }
    Ok(None)
}
pub(super) fn pair(a: &Arc, b: &Arc, budget: &mut Budget) -> Result<Option<Pair>, Error> {
    budget.spend(crate::limits::booleans_quadratic_predicates::PAIR_SETUP_WORK)?;
    let a = View::new(a);
    let b = View::new(b);
    if separated(&a, &b, budget)? {
        return Ok(Some(Pair::Separated));
    }
    if paired(&a, &b, budget)? {
        return Ok(Some(Pair::Paired));
    }
    Ok(transverse(&a, &b, budget)?.map(Pair::Transverse))
}
