//! Exact signs in one or two real quadratic extensions.
use super::*;

#[derive(Clone, Debug)]
pub(super) struct Q {
    pub a: R,
    pub b: R,
}
impl Q {
    pub fn rational(a: R) -> Self {
        Self { a, b: n(0) }
    }
    pub fn add(&self, v: &Self) -> Self {
        Self {
            a: &self.a + &v.a,
            b: &self.b + &v.b,
        }
    }
    pub fn sub(&self, v: &Self) -> Self {
        Self {
            a: &self.a - &v.a,
            b: &self.b - &v.b,
        }
    }
    pub fn scale(&self, v: &R) -> Self {
        Self {
            a: &self.a * v,
            b: &self.b * v,
        }
    }
    pub fn mul(&self, v: &Self, d: &R) -> Self {
        Self {
            a: &self.a * &v.a + &self.b * &v.b * d,
            b: &self.a * &v.b + &self.b * &v.a,
        }
    }
    pub fn div(&self, v: &Self, d: &R) -> Result<Self, Error> {
        let norm = &v.a * &v.a - &v.b * &v.b * d;
        if norm.is_zero() {
            return Err(Error::new("INTERNAL", "Zero quadratic contact divisor"));
        }
        let result = self
            .mul(
                &Self {
                    a: v.a.clone(),
                    b: -v.b.clone(),
                },
                d,
            )
            .scale(&(n(1) / norm));
        result.checked()?;
        Ok(result)
    }
    pub fn sign(&self, d: &R) -> Ordering {
        let a = self.a.cmp(&n(0));
        let b = if d.is_zero() {
            Ordering::Equal
        } else {
            self.b.cmp(&n(0))
        };
        if a == Ordering::Equal {
            return b;
        }
        if b == Ordering::Equal || a == b {
            return a;
        }
        let squares = (&self.a * &self.a).cmp(&(&self.b * &self.b * d));
        if a == Ordering::Greater {
            squares
        } else {
            squares.reverse()
        }
    }
    pub fn cmp(&self, v: &Self, d: &R) -> Ordering {
        self.sub(v).sign(d)
    }
    pub fn checked(&self) -> Result<(), Error> {
        for v in [&self.a, &self.b] {
            bounded(v)?;
        }
        Ok(())
    }
    pub fn rational_value(&self) -> Result<R, Error> {
        if self.b.is_zero() {
            Ok(self.a.clone())
        } else {
            Err(Error::new(
                "INTERNAL",
                "Quadratic contact endpoint is not rational",
            ))
        }
    }
    pub fn enclosure(&self, root: &(R, R)) -> (R, R) {
        let lo = &self.a + &self.b * &root.0;
        let hi = &self.a + &self.b * &root.1;
        if self.b < n(0) { (hi, lo) } else { (lo, hi) }
    }
}

pub(super) fn bounded(v: &R) -> Result<(), Error> {
    if v.numer().bits() > crate::limits::booleans_topology_quadratic::MAX_COEFFICIENT_BITS
        || v.denom().bits() > crate::limits::booleans_topology_quadratic::MAX_COEFFICIENT_BITS
    {
        Err(limit(&format!(
            "Quadratic contact coefficients exceed {} bits",
            crate::limits::booleans_topology_quadratic::MAX_COEFFICIENT_BITS
        )))
    } else {
        Ok(())
    }
}

// Sign of x+y*sqrt(e), where x and y are in Q(sqrt(d)). Comparing
// squares is valid only after their signs establish which side is positive.
pub(super) fn combined_sign(x: &Q, y: &Q, d: &R, e: &R) -> Ordering {
    let sx = x.sign(d);
    let sy = if e.is_zero() {
        Ordering::Equal
    } else {
        y.sign(d)
    };
    if sx == Ordering::Equal {
        return sy;
    }
    if sy == Ordering::Equal || sx == sy {
        return sx;
    }
    let squares = x.mul(x, d).sub(&y.mul(y, d).scale(e)).sign(d);
    if sx == Ordering::Greater {
        squares
    } else {
        squares.reverse()
    }
}

pub(super) fn compare(a: &Q, d: &R, b: &Q, e: &R) -> Ordering {
    combined_sign(
        &a.sub(&Q::rational(b.a.clone())),
        &Q::rational(-b.b.clone()),
        d,
        e,
    )
}

pub(super) fn root_enclosure(d: &R, bits: usize) -> (R, R) {
    let denominator = n(1).numer() << bits;
    let numerator = ((d.numer() << (2 * bits)) / d.denom()).sqrt();
    let lo = R::new(numerator.clone(), denominator.clone());
    if &lo * &lo == *d {
        return (lo.clone(), lo);
    }
    (lo, R::new(numerator + n(1).numer(), denominator))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn signs_preserve_conjugate_cancellation_without_float_rounding() {
        let root = Q { a: n(0), b: n(1) };
        assert_eq!(compare(&root, &n(2), &root, &n(3)), Ordering::Less);
        assert_eq!(
            compare(&root.scale(&n(2)), &n(2), &root, &n(8)),
            Ordering::Equal
        );
        let x = Q { a: n(1), b: n(1) };
        assert_eq!(
            combined_sign(&x, &x.scale(&n(-1)), &n(2), &n(3)),
            Ordering::Less
        );
        let huge = R::from_integer(n(1).numer() << 200usize);
        let near = Q {
            a: huge.clone(),
            b: -n(1),
        };
        assert_eq!(near.sign(&(&huge * &huge + n(1))), Ordering::Less);
        assert_eq!(near.sign(&(&huge * &huge - n(1))), Ordering::Greater);
    }
    #[test]
    fn root_intervals_are_outward_and_tight_even_at_extreme_scales() {
        for d in [
            n(2),
            n(1) / n(131),
            R::from_integer(n(1).numer() << 201usize),
        ] {
            let (lo, hi) = root_enclosure(&d, 128);
            assert!(&lo * &lo <= d && &hi * &hi >= d);
            assert!(hi - lo <= R::new(n(1).numer().clone(), n(1).numer() << 128usize));
        }
    }
}
