//! Exact rational contact discovery and synchronization before topology certificates.
use super::*;
mod resultant;
mod roots;

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
    roots::bounded(&a)?;
    roots::bounded(b)?;
    while !a.is_empty() && a.len() >= b.len() {
        budget.spend(b.len())?;
        let offset = a.len() - b.len();
        let scale = a.last().unwrap() / b.last().unwrap();
        for (i, v) in b.iter().enumerate() {
            a[offset + i] -= v * &scale;
        }
        a = trim(a);
        roots::bounded(&a)?;
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
    roots::bounded(&a)?;
    roots::bounded(&b)?;
    let (mut a, mut b) = (monic(trim(a)), monic(trim(b)));
    while !b.is_empty() {
        let next = monic(remainder(a, &b, budget)?);
        a = b;
        b = next;
    }
    Ok(a)
}
pub(super) fn square_root(v: &R) -> Option<R> {
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
// Low-degree roots have direct exact formulas; higher degrees use bounded
// rational reconstruction in [0,1]. Missing roots never imply disjoint curves.
fn rational_roots(p: &[R], budget: &mut Budget) -> Result<Vec<R>, Error> {
    budget.spend(32)?;
    let p = trim(p.to_vec());
    roots::bounded(&p)?;
    let mut out = Vec::new();
    match p.len() {
        2 => out.push(-&p[0] / &p[1]),
        3 => {
            if let Some(d) = square_root(&(&p[1] * &p[1] - n(4) * &p[2] * &p[0])) {
                out.push((-&p[1] - &d) / (n(2) * &p[2]));
                out.push((-&p[1] + d) / (n(2) * &p[2]));
            }
        }
        4.. => out.extend(roots::in_unit_interval(&p, budget)?),
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
pub(super) fn preimages(c: &Cubic, point: &P, budget: &mut Budget) -> Result<Vec<R>, Error> {
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
// A shared quadratic coordinate can have different parameter origins, scales
// or traversal directions. Match complete coefficients, never sampled values.
fn quadratic_coordinate(
    a: &Cubic,
    b: &Cubic,
    known: &[P],
    budget: &mut Budget,
) -> Result<Option<(P, R, R)>, Error> {
    let ap = curves::coefficients(a);
    let bp = curves::coefficients(b);
    if !cross(&ap[3], &bp[3]).is_zero() {
        return Ok(None);
    }
    let mut directions = vec![[n(1), n(0)], [n(0), n(1)]];
    directions.extend_from_slice(known);
    for p in [&ap[3], &bp[3]] {
        if *p != [n(0), n(0)] {
            directions.push([-p[1].clone(), p[0].clone()]);
        }
    }
    for a in endpoints(a) {
        for b in endpoints(b) {
            let p = sub(a, b);
            if p != [n(0), n(0)] {
                directions.push([-p[1].clone(), p[0].clone()]);
            }
        }
    }
    for direction in directions {
        budget.spend(32)?;
        let av = trim(ap.iter().map(|p| dot(p, &direction)).collect());
        let bv = trim(bp.iter().map(|p| dot(p, &direction)).collect());
        roots::bounded(&av)?;
        roots::bounded(&bv)?;
        if av.len() != 3 || bv.len() != 3 {
            continue;
        }
        let Some(scale) = square_root(&(&av[2] / &bv[2])) else {
            continue;
        };
        for scale in [scale.clone(), -scale] {
            let offset = (&av[1] / &scale - &bv[1]) / (n(2) * &bv[2]);
            let end = &offset + &scale;
            let composed = compose(&bv, &offset, &scale);
            roots::bounded(&composed)?;
            if offset.clone().max(end.clone()) >= n(0)
                && offset.clone().min(end) <= n(1)
                && composed == av
            {
                return Ok(Some((direction, offset, scale)));
            }
        }
    }
    Ok(None)
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
    coordinate_contacts(a, b, direction, &offset, &scale, budget)
}
fn coordinate_contacts(
    a: &Cubic,
    b: &Cubic,
    direction: &P,
    offset: &R,
    scale: &R,
    budget: &mut Budget,
) -> Result<Vec<(R, R)>, Error> {
    let ap = curves::coefficients(a);
    let bp = curves::coefficients(b);
    let normal = [-direction[1].clone(), direction[0].clone()];
    let av: Poly = ap.iter().map(|p| dot(p, &normal)).collect();
    let bv: Poly = bp.iter().map(|p| dot(p, &normal)).collect();
    let mut difference = compose(&bv, offset, scale);
    difference.resize(4, n(0));
    for (v, a) in difference.iter_mut().zip(av) {
        *v -= a;
    }
    Ok(rational_roots(&difference, budget)?
        .into_iter()
        .map(|t| {
            let u = offset + scale * &t;
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
            let p = curves::coefficients(arc.rational().expect("rational contact preparation"));
            let times: Vec<_> = times.into_iter().collect();
            for pair in times.windows(2) {
                out.push(Arc {
                    curve: Curve::Rational(Box::new(curves::restricted(&p, &pair[0], &pair[1]))),
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
pub(super) fn prepare(
    arcs: Vec<Arc>,
    budget: &mut Budget,
) -> Result<(Vec<Arc>, Value, Vec<P>), Error> {
    let mut cuts = vec![BTreeSet::from([n(0), n(1)]); arcs.len()];
    let mut points = BTreeSet::new();
    let mut self_points = BTreeSet::new();
    let mut stationary_points = BTreeSet::new();
    let mut quadratic_directions = BTreeSet::new();
    for (i, arc) in arcs.iter().enumerate().filter(|(_, a)| a.curved) {
        budget.spend(32)?;
        let p = curves::coefficients(arc.rational().expect("rational contact preparation"));
        let x: Poly = p.iter().map(|v| v[0].clone()).collect();
        let y: Poly = p.iter().map(|v| v[1].clone()).collect();
        for t in rational_roots(&gcd(derivative(&x), derivative(&y), budget)?, budget)? {
            if t > n(0) && t < n(1) {
                stationary_points.insert(at(
                    arc.rational().expect("rational contact preparation"),
                    &t,
                ));
                cuts[i].insert(t);
            }
        }
        // P(t)-P(u)=(t-u)[p1+p2(t+u)+p3((t+u)^2-tu)].
        // The two vector equations determine the sum and product exactly.
        let determinant = cross(&p[2], &p[3]);
        if !determinant.is_zero() {
            let sum = -cross(&p[1], &p[3]) / &determinant;
            let product = &sum * &sum - cross(&p[1], &p[2]) / determinant;
            let roots = rational_roots(&[product, -sum, n(1)], budget)?;
            if roots.len() == 2
                && roots.iter().all(unit)
                && at(
                    arc.rational().expect("rational contact preparation"),
                    &roots[0],
                ) == at(
                    arc.rational().expect("rational contact preparation"),
                    &roots[1],
                )
            {
                if roots.iter().any(|t| *t > n(0) && *t < n(1)) {
                    self_points.insert(at(
                        arc.rational().expect("rational contact preparation"),
                        &roots[0],
                    ));
                }
                cuts[i].extend(roots);
            }
        }
    }
    points.extend(self_points.iter().cloned());
    points.extend(stationary_points.iter().cloned());
    for i in 0..arcs.len() {
        for j in i + 1..arcs.len() {
            let a = &arcs[i];
            let b = &arcs[j];
            let (Some(ac), Some(bc)) = (a.rational(), b.rational()) else {
                continue;
            };
            budget.spend(8)?;
            if (!a.curved && !b.curved) || !overlaps(ac, bc) {
                continue;
            }
            let mut candidates = Vec::new();
            for (at_index, t) in [(0, n(0)), (3, n(1))] {
                for u in preimages(bc, &ac[at_index], budget)? {
                    candidates.push((t.clone(), u));
                }
                for u in preimages(ac, &bc[at_index], budget)? {
                    candidates.push((u, t.clone()));
                }
            }
            if !a.curved || !b.curved {
                let (curve, line, reverse) = if a.curved {
                    (ac, bc, false)
                } else {
                    (bc, ac, true)
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
            } else if let Some(direction) = linear_coordinate(ac, bc) {
                candidates.extend(graph_contacts(ac, bc, &direction, budget)?);
            } else {
                if let Some((direction, _, _)) = quadratic_coordinate(ac, bc, &[], budget)? {
                    let axis = usize::from(direction[0].is_zero());
                    let scale = direction[axis].clone();
                    quadratic_directions.insert(direction.map(|v| v / &scale));
                    if quadratic_directions.len() > MAX_EDGES {
                        return Err(limit(
                            "Quadratic contact synchronization exceeds 512 projections",
                        ));
                    }
                }
                candidates.extend(resultant::contacts(ac, bc, budget)?);
            }
            for (t, u) in candidates {
                if unit(&t) && unit(&u) && at(ac, &t) == at(bc, &u) {
                    if (t > n(0) && t < n(1)) || (u > n(0) && u < n(1)) {
                        points.insert(at(ac, &t));
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
        json!({"method":"exact_resultants_gcd_and_verified_rational_roots","contact_points":points.len(),"self_contact_points":self_points.len(),"stationary_points":stationary_points.len(),"parameter_splits":split_count,"root_isolation_maximum_depth":roots::MAX_ROOT_DEPTH,"coefficient_maximum_bits":roots::MAX_COEFFICIENT_BITS,"all_algebraic_contacts_located":false}),
        quadratic_directions.into_iter().collect(),
    ))
}
pub(super) fn synchronize(
    arcs: Vec<Arc>,
    quadratic_directions: &[P],
    budget: &mut Budget,
) -> Result<Vec<Arc>, Error> {
    let mut cuts = vec![BTreeSet::from([n(0), n(1)]); arcs.len()];
    for i in 0..arcs.len() {
        for j in i + 1..arcs.len() {
            let a = &arcs[i];
            let b = &arcs[j];
            let (Some(ac), Some(bc)) = (a.rational(), b.rational()) else {
                continue;
            };
            budget.spend(8)?;
            if (!a.curved && !b.curved) || !overlaps(ac, bc) {
                continue;
            }
            if let Some(direction) = linear_coordinate(ac, bc) {
                budget.spend(64)?;
                for (from, to, index) in [(ac, bc, j), (bc, ac, i)] {
                    let start = dot(&to[0], &direction);
                    let delta = dot(&sub(&to[3], &to[0]), &direction);
                    for p in endpoints(from) {
                        let t = (dot(p, &direction) - &start) / &delta;
                        if unit(&t) {
                            cuts[index].insert(t);
                        }
                    }
                }
            } else if let Some((_, offset, scale)) =
                quadratic_coordinate(ac, bc, quadratic_directions, budget)?
            {
                budget.spend(64)?;
                for t in [n(0), n(1)] {
                    let u = &offset + &scale * &t;
                    if unit(&u) {
                        cuts[j].insert(u);
                    }
                    let u = (&t - &offset) / &scale;
                    if unit(&u) {
                        cuts[i].insert(u);
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
    fn low_degree_root_entry_has_the_same_coefficient_limit() {
        let huge = R::from_integer(n(1).numer() << 4097usize);
        let mut budget = Budget::default();
        for p in [vec![-n(1), huge.clone()], vec![-n(1), n(0), huge]] {
            assert_eq!(
                rational_roots(&p, &mut budget).unwrap_err().code,
                "RESOURCE_LIMIT"
            );
        }
    }
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
