//! Bounded exact rational-root discovery; no floating root is accepted.
use super::*;
use num_traits::Signed;

pub(super) const MAX_ROOT_DEPTH: usize = 96;
pub(super) const MAX_COEFFICIENT_BITS: u64 = 4096;

pub(super) fn bounded(p: &[R]) -> Result<(), Error> {
    if p.len() > 19
        || p.iter().any(|v| {
            v.numer().bits() > MAX_COEFFICIENT_BITS || v.denom().bits() > MAX_COEFFICIENT_BITS
        })
    {
        return Err(limit(
            "Boolean contact polynomials exceed degree 18 or 4096-bit coefficients",
        ));
    }
    Ok(())
}

pub(super) fn multiply(a: &[R], b: &[R], budget: &mut Budget) -> Result<Poly, Error> {
    bounded(a)?;
    bounded(b)?;
    if a.is_empty() || b.is_empty() {
        return Ok(vec![]);
    }
    budget.spend(a.len() * b.len())?;
    let mut out = vec![n(0); a.len() + b.len() - 1];
    for (i, x) in a.iter().enumerate() {
        for (j, y) in b.iter().enumerate() {
            out[i + j] += x * y;
        }
    }
    bounded(&out)?;
    Ok(trim(out))
}

pub(super) fn subtract(mut a: Poly, b: &[R]) -> Poly {
    a.resize(a.len().max(b.len()), n(0));
    for (x, y) in a.iter_mut().zip(b) {
        *x -= y;
    }
    trim(a)
}

pub(super) fn quotient(mut a: Poly, b: &[R], budget: &mut Budget) -> Result<Poly, Error> {
    assert!(!b.is_empty());
    bounded(&a)?;
    bounded(b)?;
    let mut out = vec![n(0); a.len().saturating_sub(b.len()) + 1];
    while !a.is_empty() && a.len() >= b.len() {
        budget.spend(b.len())?;
        let offset = a.len() - b.len();
        let scale = a.last().unwrap() / b.last().unwrap();
        out[offset] = scale.clone();
        for (i, v) in b.iter().enumerate() {
            a[offset + i] -= v * &scale;
        }
        a = trim(a);
        bounded(&a)?;
    }
    if !a.is_empty() {
        return Err(Error::new(
            "INTERNAL",
            "Inexact polynomial contact division",
        ));
    }
    bounded(&out)?;
    Ok(trim(out))
}

fn binomial(n: usize, k: usize) -> R {
    (0..k).fold(super::n(1), |v, i| {
        v * super::n((n - i) as i32) / super::n((i + 1) as i32)
    })
}

fn bernstein(p: &[R]) -> Poly {
    let degree = p.len() - 1;
    (0..=degree)
        .map(|k| {
            (0..=k)
                .map(|i| &p[i] * binomial(k, i) / binomial(degree, i))
                .sum()
        })
        .collect()
}

fn variations(p: &[R]) -> usize {
    let signs: Vec<_> = p
        .iter()
        .filter(|v| !v.is_zero())
        .map(|v| *v > n(0))
        .collect();
    signs.windows(2).filter(|v| v[0] != v[1]).count()
}

fn halve(mut p: Poly) -> (Poly, Poly) {
    let mut left = vec![p[0].clone()];
    let mut right = vec![p.last().unwrap().clone()];
    while p.len() > 1 {
        p = p.windows(2).map(|v| (&v[0] + &v[1]) / n(2)).collect();
        left.push(p[0].clone());
        right.push(p.last().unwrap().clone());
    }
    right.reverse();
    (left, right)
}

// If a root r=p/q lies within 1/(2q²) of the midpoint, it is one of these
// convergents. Earlier candidates are harmless: every one is substituted exactly.
fn candidate(p: &[R], lo: &R, hi: &R, budget: &mut Budget) -> Result<Option<R>, Error> {
    let middle = (lo + hi) / n(2);
    let (mut a, mut b) = (middle.numer().clone(), middle.denom().clone());
    let (mut pn, mut pp) = (n(1).numer().clone(), n(0).numer().clone());
    let (mut qn, mut qp) = (n(0).numer().clone(), n(1).numer().clone());
    while !b.is_zero() {
        budget.spend(p.len() + 1)?;
        let k = &a / &b;
        let next_p = &k * &pn + pp;
        let next_q = &k * &qn + qp;
        let t = R::new(next_p.clone(), next_q.clone());
        if &t > lo && &t < hi && value(p, &t).is_zero() {
            return Ok(Some(t));
        }
        (pp, pn) = (pn, next_p);
        (qp, qn) = (qn, next_q);
        (a, b) = (b.clone(), a % b);
    }
    Ok(None)
}

pub(super) fn in_unit_interval(p: &[R], budget: &mut Budget) -> Result<Vec<R>, Error> {
    let common = gcd(p.to_vec(), derivative(p), budget)?;
    let p = quotient(p.to_vec(), &common, budget)?;
    if p.len() <= 1 {
        return Ok(vec![]);
    }
    // Removing repeated factors can leave a linear or quadratic equation.
    // Its exact formula also proves irrational roots are not rational candidates.
    if p.len() <= 3 {
        return Ok(rational_roots(&p, budget)?
            .into_iter()
            .filter(unit)
            .collect());
    }
    // Clearing all denominators gives an integer leading coefficient Q.
    // The rational-root theorem bounds a reduced root denominator by Q.
    // Not removing integer content only makes this bound more conservative.
    let mut denominator_bound = p.last().unwrap().clone().abs();
    for v in &p {
        denominator_bound *= R::from_integer(v.denom().clone());
    }
    let minimum_width = n(1) / (&denominator_bound * &denominator_bound);
    let mut out: Vec<_> = [n(0), n(1)]
        .into_iter()
        .filter(|t| value(&p, t).is_zero())
        .collect();
    let mut pending = vec![(bernstein(&p), n(0), n(1), 0)];
    while let Some((coefficients, lo, hi, depth)) = pending.pop() {
        bounded(&coefficients)?;
        budget.spend(coefficients.len() * coefficients.len())?;
        let count = variations(&coefficients);
        if count == 0 {
            continue;
        }
        if count == 1 {
            if let Some(t) = candidate(&p, &lo, &hi, budget)? {
                out.push(t);
                continue;
            }
            if &hi - &lo < minimum_width {
                continue;
            }
        }
        if depth == MAX_ROOT_DEPTH {
            // Discovery is incomplete here. The independent topology certificate
            // must still succeed, otherwise the command fails without geometry.
            continue;
        }
        let middle = (&lo + &hi) / n(2);
        let (left, right) = halve(coefficients);
        if left.last().unwrap().is_zero() {
            out.push(middle.clone());
        }
        pending.push((right, middle.clone(), hi, depth + 1));
        pending.push((left, lo, middle, depth + 1));
    }
    out.sort();
    out.dedup();
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn separated_repeated_endpoint_and_irrational_factors() {
        let mut budget = Budget::default();
        let mut p = vec![n(1)];
        for factor in [
            vec![n(0), n(1)],
            vec![n(-1), n(1)],
            vec![n(-1), n(3)],
            vec![n(-1), n(3)],
            vec![n(-2), n(5)],
            vec![n(-1), n(0), n(2)],
        ] {
            p = multiply(&p, &factor, &mut budget).unwrap();
        }
        assert_eq!(
            in_unit_interval(&p, &mut budget).unwrap(),
            vec![n(0), n(1) / n(3), n(2) / n(5), n(1)]
        );
        let negative: Poly = p.iter().map(|v| -v * n(17) / n(11)).collect();
        assert_eq!(
            in_unit_interval(&negative, &mut budget).unwrap(),
            in_unit_interval(&p, &mut budget).unwrap()
        );
    }

    #[test]
    fn close_rational_roots_are_distinct_and_exact() {
        let mut budget = Budget::default();
        let a = n(1) / n(997);
        let b = n(1) / n(991);
        let mut p = multiply(&[-a.clone(), n(1)], &[-b.clone(), n(1)], &mut budget).unwrap();
        p = multiply(&p, &[n(-1), n(0), n(2)], &mut budget).unwrap();
        assert_eq!(in_unit_interval(&p, &mut budget).unwrap(), vec![a, b]);
    }

    #[test]
    fn algebraic_roots_are_not_rounded_into_rationals() {
        let mut budget = Budget::default();
        assert!(
            in_unit_interval(&[n(-1), n(0), n(0), n(2)], &mut budget)
                .unwrap()
                .is_empty()
        );
        assert!(
            in_unit_interval(&[n(1), n(0), n(0), n(1)], &mut budget)
                .unwrap()
                .is_empty()
        );
        assert!(in_unit_interval(&[n(1)], &mut budget).unwrap().is_empty());
        let mut exhausted = Budget { used: MAX_WORK };
        assert_eq!(
            in_unit_interval(&[n(-1), n(0), n(0), n(2)], &mut exhausted)
                .unwrap_err()
                .code,
            "RESOURCE_LIMIT"
        );
        let too_large = R::from_integer(n(1).numer() << 4097usize);
        assert_eq!(
            in_unit_interval(&[-too_large, n(0), n(0), n(1)], &mut budget)
                .unwrap_err()
                .code,
            "RESOURCE_LIMIT"
        );
    }
}
