//! Exact rational contact discovery and synchronization before topology certificates.
use super::*;

type Poly = Vec<R>;
fn trim(mut p: Poly) -> Poly {
    while p.last().is_some_and(Zero::is_zero) {
        p.pop();
    }
    p
}
fn value(p: &[R], t: &R) -> R {
    p.iter().rev().fold(n(0), |v, a| v * t + a)
}
fn derivative(p: &[R]) -> Poly {
    p.iter()
        .enumerate()
        .skip(1)
        .map(|(i, v)| v * n(i as i32))
        .collect()
}
fn remainder(mut a: Poly, b: &[R], budget: &mut Budget) -> Result<Poly, Error> {
    while !a.is_empty() && a.len() >= b.len() {
        budget.spend(b.len())?;
        let offset = a.len() - b.len();
        let scale = a.last().unwrap() / b.last().unwrap();
        for (i, v) in b.iter().enumerate() {
            a[offset + i] -= v * &scale;
        }
        a = trim(a);
    }
    Ok(a)
}
fn monic(mut p: Poly) -> Poly {
    if let Some(top) = p.last().cloned() {
        for v in &mut p {
            *v /= &top;
        }
    }
    p
}
fn gcd(a: Poly, b: Poly, budget: &mut Budget) -> Result<Poly, Error> {
    let (mut a, mut b) = (monic(trim(a)), monic(trim(b)));
    while !b.is_empty() {
        let next = monic(remainder(a, &b, budget)?);
        a = b;
        b = next;
    }
    Ok(a)
}
fn square_root(v: &R) -> Option<R> {
    if *v < n(0) {
        return None;
    }
    let a = v.numer().sqrt();
    let b = v.denom().sqrt();
    if &a * &a == *v.numer() && &b * &b == *v.denom() {
        Some(R::new(a, b))
    } else {
        None
    }
}
// These are verified rational roots, not an assertion that irrational roots are absent.
// A repeated root of a rational cubic is rational; its gcd with the derivative
// has degree one, or degree two for a triple root.
fn rational_roots(p: &[R], budget: &mut Budget) -> Result<Vec<R>, Error> {
    budget.spend(32)?;
    let p = trim(p.to_vec());
    let mut out = Vec::new();
    match p.len() {
        2 => out.push(-&p[0] / &p[1]),
        3 => {
            if let Some(d) = square_root(&(&p[1] * &p[1] - n(4) * &p[2] * &p[0])) {
                out.push((-&p[1] - &d) / (n(2) * &p[2]));
                out.push((-&p[1] + d) / (n(2) * &p[2]));
            }
        }
        4 => {
            let g = gcd(p.clone(), derivative(&p), budget)?;
            if g.len() > 1 {
                out.extend(rational_roots(&g, budget)?);
            }
        }
        _ => {}
    }
    out.sort();
    out.dedup();
    out.retain(|t| value(&p, t).is_zero());
    Ok(out)
}
fn overlaps(a: &Cubic, b: &Cubic) -> bool {
    (0..2).all(|axis| {
        let av: Vec<_> = a.iter().map(|p| &p[axis]).collect();
        let bv: Vec<_> = b.iter().map(|p| &p[axis]).collect();
        av.iter().max().unwrap() >= bv.iter().min().unwrap()
            && bv.iter().max().unwrap() >= av.iter().min().unwrap()
    })
}
fn at(c: &Cubic, t: &R) -> P {
    let p = curves::coefficients(c);
    std::array::from_fn(|i| ((&p[3][i] * t + &p[2][i]) * t + &p[1][i]) * t + &p[0][i])
}
fn preimages(c: &Cubic, point: &P, budget: &mut Budget) -> Result<Vec<R>, Error> {
    let p = curves::coefficients(c);
    let mut x: Poly = p.iter().map(|v| v[0].clone()).collect();
    x[0] -= &point[0];
    let mut y: Poly = p.iter().map(|v| v[1].clone()).collect();
    y[0] -= &point[1];
    rational_roots(&gcd(x, y, budget)?, budget)
}
fn linear_coordinate(a: &Cubic, b: &Cubic) -> Option<P> {
    let ap = curves::coefficients(a);
    let bp = curves::coefficients(b);
    let mut directions = vec![[n(1), n(0)], [n(0), n(1)]];
    for p in [&ap[2], &ap[3], &bp[2], &bp[3]] {
        if *p != [n(0), n(0)] {
            directions.push([-p[1].clone(), p[0].clone()]);
        }
    }
    directions.into_iter().find(|d| {
        [&ap, &bp]
            .iter()
            .all(|p| dot(&p[2], d).is_zero() && dot(&p[3], d).is_zero() && !dot(&p[1], d).is_zero())
    })
}
fn compose(p: &[R], a: &R, b: &R) -> Poly {
    let mut out = vec![n(0); 4];
    for (i, v) in p.iter().enumerate() {
        let mut power = vec![n(1)];
        for _ in 0..i {
            let mut next = vec![n(0); power.len() + 1];
            for (j, w) in power.iter().enumerate() {
                next[j] += w * a;
                next[j + 1] += w * b;
            }
            power = next;
        }
        for (j, w) in power.into_iter().enumerate() {
            out[j] += v * w;
        }
    }
    trim(out)
}
fn graph_contacts(
    a: &Cubic,
    b: &Cubic,
    direction: &P,
    budget: &mut Budget,
) -> Result<Vec<(R, R)>, Error> {
    let ap = curves::coefficients(a);
    let bp = curves::coefficients(b);
    let offset = (dot(&ap[0], direction) - dot(&bp[0], direction)) / dot(&bp[1], direction);
    let scale = dot(&ap[1], direction) / dot(&bp[1], direction);
    let normal = [-direction[1].clone(), direction[0].clone()];
    let av: Poly = ap.iter().map(|p| dot(p, &normal)).collect();
    let bv: Poly = bp.iter().map(|p| dot(p, &normal)).collect();
    let mut difference = compose(&bv, &offset, &scale);
    difference.resize(4, n(0));
    for (v, a) in difference.iter_mut().zip(av) {
        *v -= a;
    }
    Ok(rational_roots(&difference, budget)?
        .into_iter()
        .map(|t| {
            let u = &offset + &scale * &t;
            (t, u)
        })
        .collect())
}
fn apply(arcs: Vec<Arc>, cuts: Vec<BTreeSet<R>>) -> Result<Vec<Arc>, Error> {
    let mut out = Vec::new();
    for (arc, times) in arcs.into_iter().zip(cuts) {
        if times.len() == 2 {
            out.push(arc);
        } else {
            if arc.curved && arc.depth == 20 {
                return Err(Error::new(
                    "CURVE_TOPOLOGY_UNRESOLVED",
                    "Algebraic contact synchronization exceeds subdivision depth 20",
                ));
            }
            let p = curves::coefficients(&arc.c);
            let times: Vec<_> = times.into_iter().collect();
            for pair in times.windows(2) {
                out.push(Arc {
                    c: curves::restricted(&p, &pair[0], &pair[1]),
                    weights: arc.weights.clone(),
                    depth: arc.depth + 1,
                    curved: arc.curved,
                });
                if out.len() > MAX_EDGES {
                    return Err(limit("Algebraic contacts exceed 512 evaluated edges"));
                }
            }
        }
        if out.len() > MAX_EDGES {
            return Err(limit("Algebraic contacts exceed 512 evaluated edges"));
        }
    }
    Ok(out)
}
pub(super) fn prepare(arcs: Vec<Arc>, budget: &mut Budget) -> Result<(Vec<Arc>, Value), Error> {
    let mut cuts = vec![BTreeSet::from([n(0), n(1)]); arcs.len()];
    let mut points = BTreeSet::new();
    for i in 0..arcs.len() {
        for j in i + 1..arcs.len() {
            let a = &arcs[i];
            let b = &arcs[j];
            budget.spend(8)?;
            if (!a.curved && !b.curved) || !overlaps(&a.c, &b.c) {
                continue;
            }
            let mut candidates = Vec::new();
            for (at_index, t) in [(0, n(0)), (3, n(1))] {
                for u in preimages(&b.c, &a.c[at_index], budget)? {
                    candidates.push((t.clone(), u));
                }
                for u in preimages(&a.c, &b.c[at_index], budget)? {
                    candidates.push((u, t.clone()));
                }
            }
            if !a.curved || !b.curved {
                let (curve, line, reverse) = if a.curved {
                    (&a.c, &b.c, false)
                } else {
                    (&b.c, &a.c, true)
                };
                let direction = sub(&line[3], &line[0]);
                let p = curves::coefficients(curve);
                let mut scalar: Poly = p.iter().map(|v| cross(v, &direction)).collect();
                scalar[0] -= cross(&line[0], &direction);
                for t in rational_roots(&scalar, budget)? {
                    let q = at(curve, &t);
                    let u = parameter(&q, &[line[0].clone(), line[3].clone()]);
                    candidates.push(if reverse { (u, t) } else { (t, u) });
                }
            } else if let Some(direction) = linear_coordinate(&a.c, &b.c) {
                candidates.extend(graph_contacts(&a.c, &b.c, &direction, budget)?);
            }
            for (t, u) in candidates {
                if unit(&t) && unit(&u) && at(&a.c, &t) == at(&b.c, &u) {
                    if (t > n(0) && t < n(1)) || (u > n(0) && u < n(1)) {
                        points.insert(at(&a.c, &t));
                    }
                    cuts[i].insert(t);
                    cuts[j].insert(u);
                }
            }
        }
    }
    let split_count: usize = cuts.iter().map(|c| c.len() - 2).sum();
    Ok((
        apply(arcs, cuts)?,
        json!({"method":"exact_polynomial_gcd_and_verified_rational_roots","contact_points":points.len(),"parameter_splits":split_count}),
    ))
}
pub(super) fn synchronize(arcs: Vec<Arc>, budget: &mut Budget) -> Result<Vec<Arc>, Error> {
    let mut cuts = vec![BTreeSet::from([n(0), n(1)]); arcs.len()];
    for i in 0..arcs.len() {
        for j in i + 1..arcs.len() {
            let a = &arcs[i];
            let b = &arcs[j];
            budget.spend(8)?;
            if (!a.curved && !b.curved) || !overlaps(&a.c, &b.c) {
                continue;
            }
            if let Some(direction) = linear_coordinate(&a.c, &b.c) {
                budget.spend(64)?;
                for (from, to, index) in [(&a.c, &b.c, j), (&b.c, &a.c, i)] {
                    let start = dot(&to[0], &direction);
                    let delta = dot(&sub(&to[3], &to[0]), &direction);
                    for p in endpoints(from) {
                        let t = (dot(p, &direction) - &start) / &delta;
                        if unit(&t) {
                            cuts[index].insert(t);
                        }
                    }
                }
            }
        }
    }
    apply(arcs, cuts)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn repeated_and_rational_quadratic_roots_are_exact() {
        let mut b = Budget::default();
        assert_eq!(
            rational_roots(&[n(-1), n(9), n(-27), n(27)], &mut b).unwrap(),
            vec![R::new(1.into(), 3.into())]
        );
        assert_eq!(
            rational_roots(&[n(1), n(-4), n(-3), n(18)], &mut b).unwrap(),
            vec![R::new(1.into(), 3.into())]
        );
        assert_eq!(
            rational_roots(&[n(2), n(-9), n(9)], &mut b).unwrap(),
            vec![R::new(1.into(), 3.into()), R::new(2.into(), 3.into())]
        );
        assert!(
            rational_roots(&[n(-2), n(0), n(1)], &mut b)
                .unwrap()
                .is_empty()
        );
    }
}
