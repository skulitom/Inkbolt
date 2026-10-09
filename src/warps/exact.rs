//! Original homogeneous Bernstein composition and exact chord certificates.
use super::*;
use num_rational::BigRational as R;
use num_traits::{One, Signed, ToPrimitive, Zero};
pub(super) type H = [R; 3];
pub(super) type Curve = Vec<H>;
type Poly = Vec<R>;
pub(super) fn r(x: f64) -> R {
    R::from_float(x).expect("validated finite warp coordinate")
}
fn integer(x: usize) -> R {
    R::from_integer(x.into())
}
fn h(p: Point) -> H {
    [r(p[0]), r(p[1]), R::one()]
}
#[derive(Default)]
pub(super) struct Budget {
    pub used: usize,
    control: crate::control::Control,
}
impl Budget {
    pub fn controlled(control: crate::control::Control) -> Self {
        Self { used: 0, control }
    }
    pub fn spend(&mut self, n: usize) -> Result<(), Error> {
        let previous = self.used;
        self.used = self.used.saturating_add(n);
        if self.used > MAX_WORK {
            return Err(limit("Warp exceeds its exact arithmetic work budget"));
        }
        if previous / 1024 != self.used / 1024 {
            self.control.check()?;
        }
        Ok(())
    }
    fn scalar(&mut self, v: &R) -> Result<(), Error> {
        self.spend(1)?;
        if v.numer().bits() > MAX_BITS || v.denom().bits() > MAX_BITS {
            return Err(limit(
                "Warp exact coefficients exceed the rational bit limit",
            ));
        }
        Ok(())
    }
    fn curve(&mut self, c: &Curve) -> Result<(), Error> {
        if c.len() > MAX_DEGREE + 1 {
            return Err(limit("Nested warp exceeds the polynomial degree limit"));
        }
        for p in c {
            for v in p {
                self.scalar(v)?;
            }
        }
        Ok(())
    }
}
fn binomial(n: usize, k: usize) -> R {
    let k = k.min(n - k);
    let mut out = R::one();
    for i in 0..k {
        out *= R::new((n - i).into(), (i + 1).into());
    }
    out
}
fn product(a: &Poly, b: &Poly, budget: &mut Budget) -> Result<Poly, Error> {
    let n = a.len() - 1;
    let m = b.len() - 1;
    if n + m > MAX_DEGREE {
        return Err(limit("Nested warp exceeds the polynomial degree limit"));
    }
    budget.spend(a.len() * b.len())?;
    let mut out = vec![R::zero(); n + m + 1];
    let ca: Vec<_> = (0..=n).map(|i| binomial(n, i)).collect();
    let cb: Vec<_> = (0..=m).map(|i| binomial(m, i)).collect();
    let cc: Vec<_> = (0..=n + m).map(|i| binomial(n + m, i)).collect();
    for (i, x) in a.iter().enumerate() {
        if x.is_zero() {
            continue;
        }
        for (j, y) in b.iter().enumerate() {
            if y.is_zero() {
                continue;
            }
            out[i + j] += x * y * &ca[i] * &cb[j] / &cc[i + j];
            budget.scalar(&out[i + j])?;
        }
    }
    Ok(out)
}
fn basis(u: &Poly, w: &Poly, budget: &mut Budget) -> Result<[Poly; 4], Error> {
    let v: Poly = w.iter().zip(u).map(|(w, u)| w - u).collect();
    let u2 = product(u, u, budget)?;
    let v2 = product(&v, &v, budget)?;
    let b0 = product(&v2, &v, budget)?;
    let b1 = product(&v2, u, budget)?
        .into_iter()
        .map(|v| v * integer(3))
        .collect();
    let b2 = product(&u2, &v, budget)?
        .into_iter()
        .map(|v| v * integer(3))
        .collect();
    let b3 = product(&u2, u, budget)?;
    Ok([b0, b1, b2, b3])
}
pub(super) enum Prepared {
    Affine(Matrix),
    Perspective {
        domain: [R; 4],
        matrix: Box<[R; 9]>,
    },
    Envelope {
        domain: [R; 4],
        points: Box<[[[R; 2]; 4]; 4]>,
    },
}
pub(super) fn homography(corners: &[Point; 4]) -> Result<[R; 9], Error> {
    let q = corners.map(|p| p.map(r));
    let cross = |a: &[R; 2], b: &[R; 2], c: &[R; 2]| {
        (&b[0] - &a[0]) * (&c[1] - &b[1]) - (&b[1] - &a[1]) * (&c[0] - &b[0])
    };
    let turns: Vec<_> = (0..4)
        .map(|i| cross(&q[i], &q[(i + 1) % 4], &q[(i + 2) % 4]))
        .collect();
    if turns
        .iter()
        .any(|v| v.is_zero() || v.is_positive() != turns[0].is_positive())
    {
        return Err(invalid(
            "Perspective corners must form a strictly convex ordered quadrilateral",
        ));
    }
    let dx1 = &q[1][0] - &q[2][0];
    let dx2 = &q[3][0] - &q[2][0];
    let dx3 = &q[0][0] - &q[1][0] + &q[2][0] - &q[3][0];
    let dy1 = &q[1][1] - &q[2][1];
    let dy2 = &q[3][1] - &q[2][1];
    let dy3 = &q[0][1] - &q[1][1] + &q[2][1] - &q[3][1];
    let (g, h) = if dx3.is_zero() && dy3.is_zero() {
        (R::zero(), R::zero())
    } else {
        let denominator = &dx1 * &dy2 - &dx2 * &dy1;
        if denominator.is_zero() {
            return Err(invalid("Perspective corner system is singular"));
        }
        (
            (&dx3 * &dy2 - &dx2 * &dy3) / &denominator,
            (&dx1 * &dy3 - &dx3 * &dy1) / denominator,
        )
    };
    for w in [R::one(), R::one() + &g, R::one() + &g + &h, R::one() + &h] {
        if w < R::new(1.into(), 1024.into()) || w > integer(1024) {
            return Err(Error::new(
                "UNSUPPORTED",
                "Perspective weights exceed the supported conditioning interval",
            ));
        }
    }
    Ok([
        &q[1][0] - &q[0][0] + &g * &q[1][0],
        &q[3][0] - &q[0][0] + &h * &q[3][0],
        q[0][0].clone(),
        &q[1][1] - &q[0][1] + &g * &q[1][1],
        &q[3][1] - &q[0][1] + &h * &q[3][1],
        q[0][1].clone(),
        g,
        h,
        R::one(),
    ])
}
pub(super) fn prepare(maps: &[Map], budget: &mut Budget) -> Result<Vec<Prepared>, Error> {
    maps.iter()
        .map(|m| {
            let p = match m {
                Map::Affine { matrix } => Prepared::Affine(*matrix),
                Map::Perspective { domain, corners } => Prepared::Perspective {
                    domain: domain.map(r),
                    matrix: Box::new(homography(corners)?),
                },
                Map::Envelope { domain, points } => Prepared::Envelope {
                    domain: domain.map(r),
                    points: Box::new(points.map(|row| row.map(|p| p.map(r)))),
                },
            };
            if let Prepared::Perspective { matrix, .. } = &p {
                for v in matrix.iter() {
                    budget.scalar(v)?;
                }
            }
            Ok(p)
        })
        .collect()
}
pub(super) fn source(e: &crate::paths::Edge) -> Curve {
    if let Some([a, b]) = e.controls {
        vec![h(e.from), h(a), h(b), h(e.to)]
    } else {
        vec![h(e.from), h(e.to)]
    }
}
fn unit(c: &Curve, domain: &[R; 4], budget: &mut Budget) -> Result<[Poly; 3], Error> {
    budget.spend(c.len() * 8)?;
    let mut u = Vec::with_capacity(c.len());
    let mut v = Vec::with_capacity(c.len());
    let mut w = Vec::with_capacity(c.len());
    for p in c {
        if p[2] <= R::zero() {
            return Err(invalid("Warp curve has nonpositive homogeneous weights"));
        }
        let a = (&p[0] - &domain[0] * &p[2]) / &domain[2];
        let b = (&p[1] - &domain[1] * &p[2]) / &domain[3];
        if a < R::zero() || b < R::zero() || a > p[2] || b > p[2] {
            return Err(Error::new(
                "WARP_DOMAIN",
                "Curve control hull lies outside a warp's declared source domain",
            ));
        }
        u.push(a);
        v.push(b);
        w.push(p[2].clone());
    }
    Ok([u, v, w])
}
pub(super) fn apply(mut c: Curve, maps: &[Prepared], budget: &mut Budget) -> Result<Curve, Error> {
    let mut degree = c.len() - 1;
    for m in maps {
        if matches!(m, Prepared::Envelope { .. }) {
            degree *= 6;
        }
        if degree > MAX_DEGREE {
            return Err(limit("Nested warp exceeds the polynomial degree limit"));
        }
    }
    budget.curve(&c)?;
    for m in maps {
        c = match m {
            Prepared::Affine(m) => c
                .iter()
                .map(|p| {
                    [
                        &p[0] * r(m[0]) + &p[1] * r(m[2]) + &p[2] * r(m[4]),
                        &p[0] * r(m[1]) + &p[1] * r(m[3]) + &p[2] * r(m[5]),
                        p[2].clone(),
                    ]
                })
                .collect(),
            Prepared::Perspective { domain, matrix: m } => {
                let [u, v, w] = unit(&c, domain, budget)?;
                (0..c.len())
                    .map(|i| {
                        std::array::from_fn(|k| {
                            &m[k * 3] * &u[i] + &m[k * 3 + 1] * &v[i] + &m[k * 3 + 2] * &w[i]
                        })
                    })
                    .collect()
            }
            Prepared::Envelope { domain, points } => {
                let [u, v, w] = unit(&c, domain, budget)?;
                let bu = basis(&u, &w, budget)?;
                let bv = basis(&v, &w, budget)?;
                let mut out: Curve = vec![[R::zero(), R::zero(), R::zero()]; 6 * (c.len() - 1) + 1];
                for (row, by) in bv.iter().enumerate() {
                    for (col, bx) in bu.iter().enumerate() {
                        let weights = product(bx, by, budget)?;
                        for (p, weight) in out.iter_mut().zip(weights) {
                            p[0] += &weight * &points[row][col][0];
                            p[1] += &weight * &points[row][col][1];
                            p[2] += weight;
                        }
                    }
                }
                out
            }
        };
        budget.curve(&c)?;
    }
    Ok(c)
}
pub(super) fn point(p: Point, maps: &[Prepared], budget: &mut Budget) -> Result<Point, Error> {
    let curve = apply(vec![h(p)], maps, budget)?;
    encode(&curve[0])
}
pub(super) fn encode(p: &H) -> Result<Point, Error> {
    if p[2] <= R::zero() {
        return Err(invalid("Warp curve has nonpositive homogeneous weights"));
    }
    let out = std::array::from_fn(|k| (&p[k] / &p[2]).to_f64().unwrap_or(f64::NAN));
    finite_point(out)?;
    Ok(out)
}
fn split(c: &Curve, budget: &mut Budget) -> Result<(Curve, Curve), Error> {
    budget.spend(c.len() * c.len() * 3)?;
    let mut row = c.clone();
    let mut left = vec![row[0].clone()];
    let mut right = vec![row.last().unwrap().clone()];
    while row.len() > 1 {
        row = row
            .windows(2)
            .map(|w| std::array::from_fn(|k| (&w[0][k] + &w[1][k]) / integer(2)))
            .collect();
        budget.curve(&row)?;
        left.push(row[0].clone());
        right.push(row.last().unwrap().clone());
    }
    right.reverse();
    Ok((left, right))
}
fn certificate(c: &Curve, a: Point, b: Point, budget: &mut Budget) -> Result<R, Error> {
    budget.spend(c.len() * 20)?;
    let n = c.len() - 1;
    let minimum = c.iter().map(|p| &p[2]).min().unwrap();
    if minimum <= &R::zero() {
        return Err(invalid(
            "Warp certificate requires positive homogeneous weights",
        ));
    }
    let mut bound = [R::zero(), R::zero()];
    for k in 0..=n + 1 {
        let f = R::new(k.into(), (n + 1).into());
        let u = R::one() - &f;
        for axis in 0..2 {
            let mut value = R::zero();
            if k <= n {
                value += &u * (&c[k][axis] - &c[k][2] * r(a[axis]));
            }
            if k > 0 {
                value += &f * (&c[k - 1][axis] - &c[k - 1][2] * r(b[axis]));
            }
            bound[axis] = bound[axis].clone().max(value.abs());
        }
    }
    let squared = (&bound[0] * &bound[0] + &bound[1] * &bound[1]) / (minimum * minimum);
    budget.scalar(&squared)?;
    Ok(squared)
}
fn upper_root(v: &R) -> f64 {
    if v.is_zero() {
        return 0.;
    }
    // A subnormal squared error can underflow during conversion. Starting at
    // the square root of the smallest normal value is still a valid upper
    // bound, and avoids an unbounded walk through representable floats.
    let encoded = v.to_f64().unwrap_or(f64::INFINITY);
    let mut value = if encoded == 0. {
        f64::MIN_POSITIVE.sqrt()
    } else {
        encoded.sqrt().next_up()
    };
    while value.is_finite() && r(value) * r(value) < *v {
        value = value.next_up();
    }
    value
}
pub(super) fn flatten(
    c: Curve,
    tolerance: f64,
    contour: usize,
    edge: usize,
    budget: &mut Budget,
    out: &mut Vec<Segment>,
    observer: &mut dyn FnMut(&Segment) -> Result<(), Error>,
) -> Result<(), Error> {
    struct Walk<'a> {
        tolerance: R,
        encoded_tolerance: f64,
        contour: usize,
        edge: usize,
        budget: &'a mut Budget,
        out: &'a mut Vec<Segment>,
        observer: &'a mut dyn FnMut(&Segment) -> Result<(), Error>,
    }
    impl Walk<'_> {
        fn visit(&mut self, c: Curve, lo: f64, hi: f64, depth: usize) -> Result<(), Error> {
            let a = encode(&c[0])?;
            let b = encode(c.last().unwrap())?;
            let error = certificate(&c, a, b, self.budget)?;
            if error <= self.tolerance {
                if self.out.len() == MAX_SEGMENTS {
                    return Err(limit("Warp expansion exceeds 4096 certified segments"));
                }
                let segment = Segment {
                    contour: self.contour,
                    edge: self.edge,
                    parameter: [lo, hi],
                    from: a,
                    to: b,
                    // The exact acceptance comparison also certifies the
                    // caller's encoded tolerance as an upper bound.
                    error_bound: upper_root(&error).min(self.encoded_tolerance),
                    degree: c.len() - 1,
                };
                (self.observer)(&segment)?;
                self.out.push(segment);
                return Ok(());
            }
            if depth == MAX_DEPTH {
                return Err(limit(
                    "Warp expansion cannot certify the requested tolerance within subdivision depth",
                ));
            }
            let (left, right) = split(&c, self.budget)?;
            let mid = (lo + hi) / 2.;
            self.visit(left, lo, mid, depth + 1)?;
            self.visit(right, mid, hi, depth + 1)
        }
    }
    Walk {
        tolerance: r(tolerance) * r(tolerance),
        encoded_tolerance: tolerance,
        contour,
        edge,
        budget,
        out,
        observer,
    }
    .visit(c, 0., 1., 0)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exact_limits_and_underflow_certificate_are_bounded() {
        let tiny = r(1e-300) * r(1e-300);
        let upper = upper_root(&tiny);
        assert!(upper.is_finite() && r(upper) * r(upper) >= tiny && upper < 1e-6);
        let huge = R::from_integer(r(1.).numer() << 8193usize);
        assert!(Budget::default().scalar(&huge).is_err());
        let mut b = Budget::default();
        assert!(b.spend(MAX_WORK + 1).is_err());
        let mut b = Budget::default();
        assert!(b.curve(&vec![h([0., 0.]); MAX_DEGREE + 2]).is_err());
        let control = crate::control::Control::default();
        control.cancel();
        assert!(Budget::controlled(control).spend(1024).is_err());
    }
}
