//! Prove a still-unrepresented non-rational tangency before futile refinement.
use super::*;

type PolyQ = Vec<Q>;
fn zero(v: &Q) -> bool {
    v.a.is_zero() && v.b.is_zero()
}
fn trim(mut p: PolyQ) -> PolyQ {
    while p.last().is_some_and(zero) {
        p.pop();
    }
    p
}
fn monic(mut p: PolyQ, d: &R, budget: &mut Budget) -> Result<PolyQ, Error> {
    if let Some(top) = p.last().cloned() {
        budget.spend(16 * p.len())?;
        for v in &mut p {
            *v = v.div(&top, d)?;
        }
    }
    Ok(p)
}
fn gcd(a: PolyQ, b: PolyQ, d: &R, budget: &mut Budget) -> Result<PolyQ, Error> {
    let (mut a, mut b) = (monic(trim(a), d, budget)?, monic(trim(b), d, budget)?);
    while !b.is_empty() {
        while !a.is_empty() && a.len() >= b.len() {
            budget.spend(32 * b.len())?;
            let offset = a.len() - b.len();
            let scale = a.last().unwrap().div(b.last().unwrap(), d)?;
            for (i, v) in b.iter().enumerate() {
                a[offset + i] = a[offset + i].sub(&v.mul(&scale, d));
                a[offset + i].checked()?;
            }
            a = trim(a);
        }
        let next = monic(a, d, budget)?;
        a = b;
        b = next;
    }
    Ok(a)
}

pub(super) fn reject(a: &Cubic, b: &Cubic, factor: &[R], budget: &mut Budget) -> Result<(), Error> {
    if factor.len() != 3 {
        return Ok(());
    }
    let d = &factor[1] * &factor[1] - n(4) * &factor[0] * &factor[2];
    if d <= n(0) || algebraic::square_root(&d).is_some() {
        return Ok(());
    }
    bounded(&d)?;
    let ap = curves::coefficients(a);
    let bp = curves::coefficients(b);
    for sign in [-1, 1] {
        budget.spend(256)?;
        let t = Q {
            a: -&factor[1] / (n(2) * &factor[2]),
            b: n(sign) / (n(2) * &factor[2]),
        };
        if t.sign(&d) != Ordering::Greater || t.cmp(&Q::rational(n(1)), &d) != Ordering::Less {
            continue;
        }
        let point = value(&ap, &t, &d);
        if point.iter().all(|v| v.b.is_zero()) {
            continue;
        }
        let equations: [PolyQ; 2] = std::array::from_fn(|axis| {
            let mut p: PolyQ = bp.iter().map(|p| Q::rational(p[axis].clone())).collect();
            p[0] = p[0].sub(&point[axis]);
            p
        });
        let common = gcd(equations[0].clone(), equations[1].clone(), &d, budget)?;
        if common.len() != 2 {
            continue;
        }
        let u = common[0].scale(&n(-1)).div(&common[1], &d)?;
        if u.sign(&d) != Ordering::Greater || u.cmp(&Q::rational(n(1)), &d) != Ordering::Less {
            continue;
        }
        let other = value(&bp, &u, &d);
        if !(0..2).all(|i| zero(&other[i].sub(&point[i]))) {
            continue;
        }
        let ad = derivative(&ap, &t, &d);
        let bd = derivative(&bp, &u, &d);
        let determinant = ad[0].mul(&bd[1], &d).sub(&ad[1].mul(&bd[0], &d));
        if !zero(&determinant) || ad.iter().all(zero) || bd.iter().all(zero) {
            continue;
        }
        // Both parameters and the common point are verified, both tangents are
        // nonzero and parallel, and at least one world coordinate is irrational.
        // Current flattened certificates cannot fix that shared junction.
        return Err(Error::new(
            "CURVE_TOPOLOGY_UNRESOLVED",
            "Exact quadratic tangency needs a non-rational world junction",
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn division_and_field_gcd_keep_exact_roots() {
        let d = n(2);
        let root = Q { a: n(0), b: n(1) };
        let one = Q::rational(n(1));
        let quotient = one.div(&one.add(&root), &d).unwrap();
        assert!(zero(&quotient.sub(&root.sub(&one))));
        let factor = vec![root.scale(&n(-1)), one.clone()];
        let expanded = vec![Q::rational(n(-2)), Q::rational(n(0)), one];
        let common = gcd(expanded, factor, &d, &mut Budget::default()).unwrap();
        assert_eq!(common.len(), 2);
        assert!(zero(&common[0].add(&root)));
    }
}
