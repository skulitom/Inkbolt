//! Exact certificates for simultaneous deformation of curve arcs to chords.
use super::*;
mod algebraic;

pub(super) struct Arc {
    c: Cubic,
    weights: Vec<i32>,
    depth: usize,
    curved: bool,
}
impl Arc {
    pub(super) fn curved(c: Cubic, weights: Vec<i32>) -> Self {
        Self {
            c,
            weights,
            depth: 0,
            curved: true,
        }
    }
    fn line(e: Segment, weights: Vec<i32>) -> Self {
        let c = [
            e[0].clone(),
            lerp(&e[0], &e[1], &R::new(1.into(), 3.into())),
            lerp(&e[0], &e[1], &R::new(2.into(), 3.into())),
            e[1].clone(),
        ];
        Self {
            c,
            weights,
            depth: 0,
            curved: false,
        }
    }
    fn chord(&self) -> Segment {
        [self.c[0].clone(), self.c[3].clone()]
    }
}
fn bound(c: &Cubic) -> R {
    (0..4)
        .map(|i| {
            let d = sub(&c[i], &lerp(&c[0], &c[3], &R::new(i.into(), 3.into())));
            dot(&d, &d)
        })
        .max()
        .unwrap()
}
fn monotone(c: &Cubic, direction: &P) -> bool {
    dot(&sub(&c[3], &c[0]), direction) > R::zero()
        && c.windows(2)
            .all(|p| dot(&sub(&p[1], &p[0]), direction) >= R::zero())
}
fn endpoints(c: &Cubic) -> [&P; 2] {
    [&c[0], &c[3]]
}

// Exact separating-axis checks enclose every intermediate curve in its control
// hull. On a touching plane, a monotone curve/chord family can only reach the
// interval between the endpoints on that plane, not arbitrary control points.
fn separated(a: &Cubic, b: &Cubic, budget: &mut Budget) -> Result<bool, Error> {
    let mut normals = vec![[n(1), n(0)], [n(0), n(1)]];
    for c in [a, b] {
        for i in 0..4 {
            for j in i + 1..4 {
                let v = sub(&c[j], &c[i]);
                if v != [R::zero(), R::zero()] {
                    normals.push([-v[1].clone(), v[0].clone()]);
                }
            }
        }
    }
    for normal in normals {
        budget.spend(8)?;
        let ap = a.clone().map(|p| dot(&p, &normal));
        let bp = b.clone().map(|p| dot(&p, &normal));
        let amin = ap.iter().min().unwrap();
        let amax = ap.iter().max().unwrap();
        let bmin = bp.iter().min().unwrap();
        let bmax = bp.iter().max().unwrap();
        if amax < bmin || bmax < amin {
            return Ok(true);
        }
        let plane = if amax == bmin {
            Some(amax)
        } else if bmax == amin {
            Some(bmax)
        } else {
            None
        };
        if let Some(plane) = plane {
            let tangent = [-normal[1].clone(), normal[0].clone()];
            let af: Vec<_> = endpoints(a)
                .into_iter()
                .filter(|p| dot(p, &normal) == *plane)
                .map(|p| dot(p, &tangent))
                .collect();
            let bf: Vec<_> = endpoints(b)
                .into_iter()
                .filter(|p| dot(p, &normal) == *plane)
                .map(|p| dot(p, &tangent))
                .collect();
            if af.is_empty() || bf.is_empty() {
                return Ok(true);
            }
            let lo = af.iter().min().unwrap().max(bf.iter().min().unwrap());
            let hi = af.iter().max().unwrap().min(bf.iter().max().unwrap());
            if lo > hi {
                return Ok(true);
            }
            if lo == hi
                && endpoints(a).iter().any(|p| {
                    endpoints(b).contains(p) && dot(p, &normal) == *plane && dot(p, &tangent) == *lo
                })
            {
                return Ok(true);
            }
        }
    }
    Ok(false)
}

// Curves sharing one strictly monotone coordinate have the same parameter at
// a possible intersection. A fixed sign of the other coordinate's difference,
// including its endpoint chord, excludes interior intersections throughout.
fn paired_coordinate(a: &Cubic, b: &Cubic, budget: &mut Budget) -> Result<bool, Error> {
    for reverse in [false, true] {
        let b: Cubic = std::array::from_fn(|i| b[if reverse { 3 - i } else { i }].clone());
        let mut directions = vec![[n(1), n(0)], [n(0), n(1)]];
        for i in [0, 3] {
            let d = sub(&b[i], &a[i]);
            if d != [n(0), n(0)] {
                directions.push([-d[1].clone(), d[0].clone()]);
            }
        }
        for mut direction in directions {
            budget.spend(24)?;
            if dot(&sub(&a[3], &a[0]), &direction) < R::zero() {
                direction = direction.map(|v| -v);
            }
            if !monotone(a, &direction)
                || !(0..4).all(|i| dot(&a[i], &direction) == dot(&b[i], &direction))
            {
                continue;
            }
            let normal = [-direction[1].clone(), direction[0].clone()];
            let delta: [R; 4] = std::array::from_fn(|i| dot(&sub(&b[i], &a[i]), &normal));
            if (delta.iter().all(|v| *v >= R::zero()) || delta.iter().all(|v| *v <= R::zero()))
                && (!delta[0].is_zero() || !delta[3].is_zero())
            {
                return Ok(true);
            }
        }
    }
    Ok(false)
}

fn outside(p: &P, c: &Cubic, budget: &mut Budget) -> Result<bool, Error> {
    // For this predicate the complete control hull matters, including faces.
    let mut points = c.to_vec();
    points.sort();
    points.dedup();
    let mut directions = vec![[n(1), n(0)], [n(0), n(1)]];
    for i in 0..points.len() {
        for j in i + 1..points.len() {
            let d = sub(&points[j], &points[i]);
            directions.push([-d[1].clone(), d[0].clone()]);
        }
    }
    for direction in directions {
        budget.spend(5)?;
        let q = dot(p, &direction);
        let values: Vec<_> = points.iter().map(|v| dot(v, &direction)).collect();
        if q < *values.iter().min().unwrap() || q > *values.iter().max().unwrap() {
            return Ok(true);
        }
    }
    Ok(false)
}

// If every derivative cross product has one sign, the difference map has a
// nonzero Jacobian in the parameter-square interior for the whole homotopy.
// Endpoints outside the opposite control hull keep its boundary away from zero.
// The chord boundary degree therefore counts exactly zero or one intersection.
fn transverse(a: &Cubic, b: &Cubic, budget: &mut Budget) -> Result<Option<bool>, Error> {
    budget.spend(9)?;
    let values: Vec<_> = a
        .windows(2)
        .flat_map(|u| {
            b.windows(2)
                .map(move |v| cross(&sub(&u[1], &u[0]), &sub(&v[1], &v[0])))
        })
        .collect();
    if values.iter().all(|v| v.is_zero())
        || !(values.iter().all(|v| *v >= R::zero()) || values.iter().all(|v| *v <= R::zero()))
    {
        return Ok(None);
    }
    for p in endpoints(a) {
        if !outside(p, b, budget)? {
            return Ok(None);
        }
    }
    for p in endpoints(b) {
        if !outside(p, a, budget)? {
            return Ok(None);
        }
    }
    let hits = intersections(&[a[0].clone(), a[3].clone()], &[b[0].clone(), b[3].clone()]);
    if hits.is_empty() {
        return Ok(Some(false));
    }
    if hits.len() == 1
        && hits
            .iter()
            .all(|(a, b)| *a > R::zero() && *a < n(1) && *b > R::zero() && *b < n(1))
    {
        return Ok(Some(true));
    }
    Ok(None)
}

fn lines(inputs: &mut [Operand], budget: &mut Budget) -> Result<Vec<Arc>, Error> {
    let raw: Vec<_> = inputs
        .iter_mut()
        .enumerate()
        .flat_map(|(source, v)| {
            std::mem::take(&mut v.edges)
                .into_iter()
                .map(move |e| (source, e))
        })
        .collect();
    let mut cuts = vec![BTreeSet::from([n(0), n(1)]); raw.len()];
    for i in 0..raw.len() {
        for j in i + 1..raw.len() {
            budget.spend(1)?;
            for (a, b) in intersections(&raw[i].1, &raw[j].1) {
                cuts[i].insert(a);
                cuts[j].insert(b);
            }
        }
    }
    let mut atoms: BTreeMap<Segment, Vec<i32>> = BTreeMap::new();
    for ((source, e), times) in raw.into_iter().zip(cuts) {
        let points: Vec<_> = times.iter().map(|t| lerp(&e[0], &e[1], t)).collect();
        for pair in points.windows(2) {
            budget.spend(1)?;
            let (key, sign) = if pair[0] < pair[1] {
                ([pair[0].clone(), pair[1].clone()], 1)
            } else {
                ([pair[1].clone(), pair[0].clone()], -1)
            };
            atoms.entry(key).or_insert_with(|| vec![0; inputs.len()])[source] += sign;
            if atoms.len() > MAX_ATOMS {
                return Err(limit(
                    "Curve certificate line arrangement exceeds 4096 atomic edges",
                ));
            }
        }
    }
    Ok(atoms
        .into_iter()
        .filter(|(_, w)| w.iter().any(|v| *v != 0))
        .map(|(e, w)| Arc::line(e, w))
        .collect())
}
fn contacts(arcs: Vec<Arc>, budget: &mut Budget) -> Result<Vec<Arc>, Error> {
    let points: BTreeSet<_> = arcs
        .iter()
        .filter(|v| v.curved)
        .flat_map(|v| [v.c[0].clone(), v.c[3].clone()])
        .collect();
    let mut out = Vec::new();
    for arc in arcs {
        if arc.curved {
            out.push(arc);
            if out.len() > MAX_EDGES {
                return Err(limit("Curve contacts exceed 512 evaluated edges"));
            }
            continue;
        }
        let e = arc.chord();
        let mut cuts = BTreeSet::from([n(0), n(1)]);
        for p in &points {
            budget.spend(1)?;
            if cross(&sub(&e[1], &e[0]), &sub(p, &e[0])).is_zero() {
                let t = parameter(p, &e);
                if unit(&t) {
                    cuts.insert(t);
                }
            }
        }
        let points: Vec<_> = cuts.iter().map(|t| lerp(&e[0], &e[1], t)).collect();
        for pair in points.windows(2) {
            out.push(Arc::line(
                [pair[0].clone(), pair[1].clone()],
                arc.weights.clone(),
            ));
            if out.len() > MAX_EDGES {
                return Err(limit("Curve contacts exceed 512 evaluated edges"));
            }
        }
    }
    Ok(out)
}
fn refine(arcs: Vec<Arc>, marked: &BTreeSet<usize>) -> Result<Vec<Arc>, Error> {
    let mut out = Vec::new();
    for (i, arc) in arcs.into_iter().enumerate() {
        if !marked.contains(&i) {
            out.push(arc);
            continue;
        }
        if arc.depth == 20 {
            return Err(Error::new(
                "CURVE_TOPOLOGY_UNRESOLVED",
                "Curve topology cannot be certified within subdivision depth 20",
            ));
        }
        let (a, b) = split(&arc.c);
        for c in [a, b] {
            out.push(Arc {
                c,
                weights: arc.weights.clone(),
                depth: arc.depth + 1,
                curved: true,
            });
        }
    }
    Ok(out)
}

pub(super) fn evaluate(
    inputs: &mut [Operand],
    mut arcs: Vec<Arc>,
    tolerance: &R,
    budget: &mut Budget,
) -> Result<Value, Error> {
    if arcs.is_empty() {
        return Ok(json!({"certificate":"exact_polygon_winding","curve_arcs":0}));
    }
    let mut base = lines(inputs, budget)?;
    base.append(&mut arcs);
    let (prepared, algebraic) = algebraic::prepare(base, budget)?;
    arcs = prepared;
    let mut refinements = 0;
    let mut aligned_splits = 0;
    loop {
        let before = arcs.len();
        arcs = algebraic::synchronize(arcs, budget)?;
        aligned_splits += arcs.len() - before;
        if arcs.len() > MAX_EDGES {
            return Err(limit(
                "Curve topology refinement exceeds 512 evaluated edges",
            ));
        }
        let mut marked = BTreeSet::new();
        for (i, a) in arcs.iter().enumerate().filter(|(_, a)| a.curved) {
            budget.spend(24)?;
            let deviation = bound(&a.c);
            if tolerance.is_zero() && !deviation.is_zero() {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "A nonstraight cubic needs a positive curve_tolerance",
                ));
            }
            if deviation > *tolerance || !monotone(&a.c, &sub(&a.c[3], &a.c[0])) {
                marked.insert(i);
            }
        }
        if !marked.is_empty() {
            refinements += marked.len();
            arcs = refine(arcs, &marked)?;
            continue;
        }
        arcs = contacts(arcs, budget)?;
        if arcs.len() > MAX_EDGES {
            return Err(limit("Curve contacts exceed 512 evaluated edges"));
        }
        let mut crossings = vec![0usize; arcs.len()];
        let mut separated_pairs = 0;
        let mut paired_coordinates = 0;
        let mut transverse_pairs = 0;
        for i in 0..arcs.len() {
            for j in i + 1..arcs.len() {
                let a = &arcs[i];
                let b = &arcs[j];
                if !a.curved && !b.curved {
                    continue;
                }
                if separated(&a.c, &b.c, budget)? {
                    separated_pairs += 1;
                    continue;
                }
                if paired_coordinate(&a.c, &b.c, budget)? {
                    paired_coordinates += 1;
                    continue;
                }
                if let Some(crosses) = transverse(&a.c, &b.c, budget)? {
                    if crosses {
                        crossings[i] += 1;
                        crossings[j] += 1;
                        transverse_pairs += 1;
                    }
                } else {
                    if a.curved {
                        marked.insert(i);
                    }
                    if b.curved {
                        marked.insert(j);
                    }
                }
            }
        }
        for (i, &count) in crossings.iter().enumerate() {
            if arcs[i].curved && count > 1 {
                marked.insert(i);
            }
        }
        if !marked.is_empty() {
            refinements += marked.len();
            arcs = refine(arcs, &marked)?;
            continue;
        }
        for arc in &arcs {
            let deviation = if arc.curved { bound(&arc.c) } else { R::zero() };
            for (input, &weight) in inputs.iter_mut().zip(&arc.weights) {
                if weight == 0 {
                    continue;
                }
                input.maximum = input.maximum.clone().max(deviation.clone());
                for _ in 0..weight.unsigned_abs() {
                    budget.spend(1)?;
                    if weight > 0 {
                        emit_edge(&mut input.edges, arc.c[0].clone(), arc.c[3].clone())?;
                    } else {
                        emit_edge(&mut input.edges, arc.c[3].clone(), arc.c[0].clone())?;
                    }
                }
            }
        }
        return Ok(
            json!({"certificate":"exact_simultaneous_curve_to_chord_homotopy","curve_arcs":arcs.iter().filter(|a|a.curved).count(),"line_arcs":arcs.iter().filter(|a|!a.curved).count(),"subdivisions":refinements,"algebraic_contacts":algebraic,"aligned_splits":aligned_splits,"separated_pairs":separated_pairs,"paired_coordinate_pairs":paired_coordinates,"transverse_crossings":transverse_pairs,"crossings_per_curved_arc_maximum":crossings.iter().zip(&arcs).filter(|(_,a)|a.curved).map(|(n,_)|*n).max().unwrap_or(0)}),
        );
    }
}
