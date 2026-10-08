//! Exact boundary integrals and rational enclosures of authored contour length.
use crate::{Error, control::Control, model::*, paths};
use num_rational::BigRational as R;
use num_traits::{Signed, ToPrimitive, Zero};
use serde_json::{Value, json};

type P = [R; 2];
type C = [P; 4];
pub(super) fn r(v: f64) -> R {
    R::from_float(v).expect("validated finite coordinate")
}
fn n(v: i64) -> R {
    R::from_integer(v.into())
}
fn sub(a: &P, b: &P) -> P {
    [&a[0] - &b[0], &a[1] - &b[1]]
}
fn cross(a: &P, b: &P) -> R {
    &a[0] * &b[1] - &a[1] * &b[0]
}
fn mapped(p: &P, m: Matrix) -> P {
    [
        &p[0] * r(m[0]) + &p[1] * r(m[2]) + r(m[4]),
        &p[0] * r(m[1]) + &p[1] * r(m[3]) + r(m[5]),
    ]
}
fn norm(p: &P) -> (R, R) {
    let squared = &p[0] * &p[0] + &p[1] * &p[1];
    let scale = n(1).numer() << 64usize;
    let floor = ((squared.numer() * &scale * &scale) / squared.denom()).sqrt();
    let lo = R::new(floor.clone(), scale.clone());
    let hi = if &lo * &lo == squared {
        lo.clone()
    } else {
        R::new(floor + 1, scale)
    };
    (lo, hi)
}
fn distance(a: &P, b: &P) -> (R, R) {
    norm(&sub(a, b))
}
fn half(a: &P, b: &P) -> P {
    std::array::from_fn(|i| (&a[i] + &b[i]) / n(2))
}
fn split(c: &C) -> (C, C) {
    let a = half(&c[0], &c[1]);
    let b = half(&c[1], &c[2]);
    let d = half(&c[2], &c[3]);
    let e = half(&a, &b);
    let f = half(&b, &d);
    let g = half(&e, &f);
    ([c[0].clone(), a, e, g.clone()], [g, f, d, c[3].clone()])
}
fn area(c: &C) -> R {
    let power = |axis: usize| {
        [
            &c[0][axis] + n(0),
            n(3) * (&c[1][axis] - &c[0][axis]),
            n(3) * (&c[0][axis] - n(2) * &c[1][axis] + &c[2][axis]),
            &c[3][axis] - &c[0][axis] + n(3) * (&c[1][axis] - &c[2][axis]),
        ]
    };
    let x = power(0);
    let y = power(1);
    let mut sum = R::zero();
    for i in 0..4 {
        for j in 1..4 {
            sum += (&x[i] * &y[j] - &y[i] * &x[j]) * n(j as i64) / n((i + j) as i64);
        }
    }
    sum / n(2)
}
pub(super) struct Budget<'a> {
    pub used: usize,
    pub control: &'a Control,
}
impl Budget<'_> {
    fn step(&mut self) -> Result<(), Error> {
        self.used += 1;
        if self.used > super::MAX_WORK {
            return Err(limit(
                "Geometry measurement exceeds certified subdivision budget",
            ));
        }
        if self.used % 32 == 1 {
            self.control.check()?;
        }
        Ok(())
    }
}
fn cubic_length(c: C, tol: R, budget: &mut Budget<'_>) -> Result<(R, R), Error> {
    let mut stack = vec![(c, tol, 0)];
    let mut lower = R::zero();
    let mut upper = R::zero();
    while let Some((c, tol, depth)) = stack.pop() {
        budget.step()?;
        let lo = distance(&c[0], &c[3]).0;
        let hi: R = c.windows(2).map(|p| distance(&p[0], &p[1]).1).sum();
        if &hi - &lo <= tol {
            lower += lo;
            upper += hi;
        } else {
            if depth == 32 {
                return Err(limit(
                    "Curve length cannot meet tolerance within subdivision depth",
                ));
            }
            let (a, b) = split(&c);
            let half = tol / n(2);
            stack.push((b, half.clone(), depth + 1));
            stack.push((a, half, depth + 1));
        }
    }
    Ok((lower, upper))
}
// A rational parametrization of a circular quadrant, followed by the exact
// authored affine map. Tangent intersections enclose each convex elliptical arc.
fn ellipse_point(t: &R, q: usize, center: &P, axes: &[P; 2]) -> (P, P) {
    let denom = n(1) + t * t;
    let x = (n(1) - t * t) / &denom;
    let y = n(2) * t / denom;
    let p = match q {
        0 => [x, y],
        1 => [-y, x],
        2 => [-x, -y],
        _ => [y, -x],
    };
    let d = [-&p[1], p[0].clone()];
    (
        std::array::from_fn(|i| &center[i] + &axes[0][i] * &p[0] + &axes[1][i] * &p[1]),
        std::array::from_fn(|i| &axes[0][i] * &d[0] + &axes[1][i] * &d[1]),
    )
}
fn ellipse_length(
    center: P,
    axes: [P; 2],
    tol: R,
    budget: &mut Budget<'_>,
) -> Result<(R, R), Error> {
    let mut stack: Vec<_> = (0..4).map(|q| (q, n(0), n(1), &tol / n(4), 0)).collect();
    let mut lower = R::zero();
    let mut upper = R::zero();
    while let Some((q, a, b, tol, depth)) = stack.pop() {
        budget.step()?;
        let (pa, da) = ellipse_point(&a, q, &center, &axes);
        let (pb, db) = ellipse_point(&b, q, &center, &axes);
        let f = cross(&sub(&pb, &pa), &db) / cross(&da, &db);
        let corner = std::array::from_fn(|i| &pa[i] + &da[i] * &f);
        let lo = distance(&pa, &pb).0;
        let hi = distance(&pa, &corner).1 + distance(&corner, &pb).1;
        if &hi - &lo <= tol {
            lower += lo;
            upper += hi;
        } else {
            if depth == 32 {
                return Err(limit(
                    "Ellipse length cannot meet tolerance within subdivision depth",
                ));
            }
            let mid = (&a + &b) / n(2);
            let half = tol / n(2);
            stack.push((q, mid.clone(), b, half.clone(), depth + 1));
            stack.push((q, a, mid, half, depth + 1));
        }
    }
    Ok((lower, upper))
}
fn pi() -> (R, R) {
    let atan = |den: i64| {
        let x = n(1) / n(den);
        let mut power = x.clone();
        let mut sum = R::zero();
        for k in 0..32 {
            let v = &power / n(2 * k + 1);
            if k % 2 == 0 {
                sum += v
            } else {
                sum -= v
            };
            power *= &x * &x;
        }
        (sum.clone(), sum + power / n(65))
    };
    let (a, b) = atan(5);
    let (c, d) = atan(239);
    (n(16) * a - n(4) * d, n(16) * b - n(4) * c)
}
pub(super) struct Metric {
    pub lower: R,
    pub upper: R,
    pub area: Option<(R, R)>,
    pub contours: usize,
    pub closed: usize,
}
pub(super) fn measure(
    g: &Geometry,
    m: Matrix,
    tol: &R,
    budget: &mut Budget<'_>,
) -> Result<Metric, Error> {
    if let Geometry::Rect { width, height, .. } = *g {
        budget.step()?;
        let axes = [
            [r(width) * r(m[0]), r(width) * r(m[1])],
            [r(height) * r(m[2]), r(height) * r(m[3])],
        ];
        let (a, b) = norm(&axes[0]);
        let (c, d) = norm(&axes[1]);
        let signed = cross(&axes[0], &axes[1]);
        return Ok(Metric {
            lower: n(2) * (a + c),
            upper: n(2) * (b + d),
            area: Some((signed.clone(), signed)),
            contours: 1,
            closed: 1,
        });
    }
    if let Geometry::Ellipse { cx, cy, rx, ry } = *g {
        let center = mapped(&[r(cx), r(cy)], m);
        let axes = [
            [r(rx) * r(m[0]), r(rx) * r(m[1])],
            [r(ry) * r(m[2]), r(ry) * r(m[3])],
        ];
        let factor = cross(&axes[0], &axes[1]);
        let (a, b) = pi();
        let (a, b) = (a * &factor, b * &factor);
        let area = Some(if a <= b { (a, b) } else { (b, a) });
        let (lower, upper) = ellipse_length(center, axes, tol.clone(), budget)?;
        return Ok(Metric {
            lower,
            upper,
            area,
            contours: 1,
            closed: 1,
        });
    }
    let Geometry::Path { commands } = crate::primitives::expand(g)? else {
        unreachable!()
    };
    let contours = paths::parse(&commands);
    let count: usize = contours
        .iter()
        .map(|c| c.edges.len() + usize::from(c.closed))
        .sum();
    let tolerance = tol / n(count.max(1) as i64);
    let mut result = Metric {
        lower: n(0),
        upper: n(0),
        area: Some((n(0), n(0))),
        contours: contours.len(),
        closed: 0,
    };
    for c in contours {
        if c.closed {
            result.closed += 1;
        } else {
            result.area = None;
        }
        let mut signed = n(0);
        for e in &c.edges {
            budget.step()?;
            let a = mapped(&e.from.map(r), m);
            let b = mapped(&e.to.map(r), m);
            let (lo, hi) = if let Some([p, q]) = e.controls {
                let curve = [a, mapped(&p.map(r), m), mapped(&q.map(r), m), b];
                signed += area(&curve);
                cubic_length(curve, tolerance.clone(), budget)?
            } else {
                signed += cross(&a, &b) / n(2);
                distance(&a, &b)
            };
            result.lower += lo;
            result.upper += hi;
        }
        if c.closed {
            let a = mapped(&c.edges.last().unwrap().to.map(r), m);
            let b = mapped(&c.start.map(r), m);
            let (lo, hi) = distance(&a, &b);
            result.lower += lo;
            result.upper += hi;
            signed += cross(&a, &b) / n(2);
            if let Some((a, b)) = &mut result.area {
                *a += &signed;
                *b += signed;
            }
        }
    }
    Ok(result)
}
pub(super) fn interval(lower: R, upper: R, tolerance: Option<&R>) -> Result<Value, Error> {
    let mut a = lower
        .to_f64()
        .ok_or_else(|| limit("Metric exceeds number range"))?;
    let mut b = upper
        .to_f64()
        .ok_or_else(|| limit("Metric exceeds number range"))?;
    if r(a) > lower {
        a = a.next_down();
    }
    if r(b) < upper {
        b = b.next_up();
    }
    let value = ((&lower + &upper) / n(2))
        .to_f64()
        .ok_or_else(|| limit("Metric exceeds number range"))?;
    let error = (&lower - r(value)).abs().max((&upper - r(value)).abs());
    if tolerance.is_some_and(|t| error > *t) {
        return Err(Error::new(
            "NUMERIC_PRECISION",
            "Requested metric tolerance is below representable output precision",
        ));
    }
    let mut bound = error.to_f64().unwrap();
    if r(bound) < error {
        bound = bound.next_up();
    }
    Ok(
        json!({"value":value,"absolute_error_bound":bound,"lower":a,"upper":b,"lower_exact":lower.to_string(),"upper_exact":upper.to_string()}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn measurement_budget_and_cancellation_return_structured_errors() {
        let control = Control::default();
        let geometry = Geometry::Rect {
            x: 0.0,
            y: 0.0,
            width: 3.0,
            height: 4.0,
        };
        let matrix = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0];
        let mut budget = Budget {
            used: crate::dimensions::MAX_WORK - 1,
            control: &control,
        };
        assert!(measure(&geometry, matrix, &r(0.0001), &mut budget).is_ok());
        let error = measure(&geometry, matrix, &r(0.0001), &mut budget)
            .err()
            .unwrap();
        assert_eq!(error.code, "RESOURCE_LIMIT");
        control.cancel();
        let mut budget = Budget {
            used: 0,
            control: &control,
        };
        let curve = Geometry::Ellipse {
            cx: 0.0,
            cy: 0.0,
            rx: 100.0,
            ry: 1.0,
        };
        let error = measure(&curve, matrix, &r(0.000001), &mut budget)
            .err()
            .unwrap();
        assert_eq!(error.code, "CANCELLED");
    }

    #[test]
    fn unrepresentable_tolerance_fails_instead_of_false_certificate() {
        let exact = n(1_000_000_000) + n(1) / n(3);
        assert_eq!(
            interval(exact.clone(), exact.clone(), Some(&r(1e-9)))
                .unwrap_err()
                .code,
            "NUMERIC_PRECISION"
        );
        let result = interval(exact.clone(), exact.clone(), Some(&r(1e-6))).unwrap();
        assert!(r(result["lower"].as_f64().unwrap()) <= exact);
        assert!(r(result["upper"].as_f64().unwrap()) >= exact);
        assert!(r(result["absolute_error_bound"].as_f64().unwrap()) <= r(1e-6));
    }
}
