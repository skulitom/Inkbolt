//! Original curve reduction with exact rational deviation and swept-hull certificates.
use crate::{
    Error,
    model::*,
    paths::{self, Edge},
};
use num_rational::BigRational as R;
use num_traits::{ToPrimitive, Zero};
use serde_json::{Value, json};
use std::collections::HashSet;

pub const MAX_SPAN: usize = 32;
pub const MAX_WORK: usize = 400_000;
pub fn default_span() -> usize {
    8
}
type P = [R; 2];
type C = [P; 4];
fn r(x: f64) -> R {
    R::from_float(x).expect("finite validated coordinate")
}
fn integer(x: usize) -> R {
    R::from_integer(x.into())
}
fn point(p: Point) -> P {
    p.map(r)
}
fn sub(a: &P, b: &P) -> P {
    [&a[0] - &b[0], &a[1] - &b[1]]
}
fn dot(a: &P, b: &P) -> R {
    &a[0] * &b[0] + &a[1] * &b[1]
}
fn lerp(a: &P, b: &P, t: &R) -> P {
    std::array::from_fn(|i| &a[i] + (&b[i] - &a[i]) * t)
}
fn cubic(e: &Edge) -> C {
    let a = point(e.from);
    let b = point(e.to);
    if let Some([c, d]) = e.controls {
        [a, point(c), point(d), b]
    } else {
        let c = lerp(&a, &b, &R::new(1.into(), 3.into()));
        let d = lerp(&a, &b, &R::new(2.into(), 3.into()));
        [a, c, d, b]
    }
}
fn split(c: &C, t: &R) -> (C, C) {
    let a = lerp(&c[0], &c[1], t);
    let b = lerp(&c[1], &c[2], t);
    let d = lerp(&c[2], &c[3], t);
    let e = lerp(&a, &b, t);
    let f = lerp(&b, &d, t);
    let g = lerp(&e, &f, t);
    ([c[0].clone(), a, e, g.clone()], [g, f, d, c[3].clone()])
}
fn restrict(c: &C, a: &R, b: &R) -> C {
    let left = if b == &integer(1) {
        c.clone()
    } else {
        split(c, b).0
    };
    if a.is_zero() {
        left
    } else {
        split(&left, &(a / b)).1
    }
}
struct Budget {
    used: usize,
}
impl Budget {
    fn spend(&mut self, n: usize) -> Result<(), Error> {
        self.used = self.used.saturating_add(n);
        if self.used > MAX_WORK {
            Err(limit(
                "Curve simplification exceeds its exact-certificate work budget; use fewer contours or a smaller max_span",
            ))
        } else {
            Ok(())
        }
    }
}
fn orient(a: &P, b: &P, c: &P) -> R {
    let u = sub(b, a);
    let v = sub(c, a);
    &u[0] * &v[1] - &u[1] * &v[0]
}
fn hull(mut p: Vec<P>, budget: &mut Budget) -> Result<Vec<P>, Error> {
    budget.spend(p.len() * 8)?;
    p.sort();
    p.dedup();
    if p.len() < 3 {
        return Ok(p);
    }
    let mut lower: Vec<P> = Vec::new();
    let mut upper: Vec<P> = Vec::new();
    for (chain, iter) in [
        (&mut lower, p.iter().collect::<Vec<_>>()),
        (&mut upper, p.iter().rev().collect()),
    ] {
        for v in iter {
            while chain.len() >= 2
                && orient(&chain[chain.len() - 2], &chain[chain.len() - 1], v) <= R::zero()
            {
                chain.pop();
            }
            chain.push(v.clone());
        }
        chain.pop();
    }
    lower.extend(upper);
    Ok(lower)
}
// A separating line proves either disjoint hulls or contact at just one fixed shared endpoint.
fn separated(a: &[P], b: &[P], shared: &[P], budget: &mut Budget) -> Result<bool, Error> {
    let mut normals = vec![[integer(1), R::zero()], [R::zero(), integer(1)]];
    for polygon in [a, b] {
        if polygon.len() > 1 {
            for (p, q) in polygon
                .iter()
                .zip(polygon.iter().cycle().skip(1))
                .take(polygon.len())
            {
                let v = sub(q, p);
                normals.push([-v[1].clone(), v[0].clone()]);
            }
        }
    }
    for n in normals {
        budget.spend(a.len() + b.len())?;
        let ap: Vec<_> = a.iter().map(|p| dot(p, &n)).collect();
        let bp: Vec<_> = b.iter().map(|p| dot(p, &n)).collect();
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
            let tangent = [-n[1].clone(), n[0].clone()];
            let fa: Vec<_> = a
                .iter()
                .zip(&ap)
                .filter(|(_, v)| *v == plane)
                .map(|(p, _)| dot(p, &tangent))
                .collect();
            let fb: Vec<_> = b
                .iter()
                .zip(&bp)
                .filter(|(_, v)| *v == plane)
                .map(|(p, _)| dot(p, &tangent))
                .collect();
            let lo = fa.iter().min().unwrap().max(fb.iter().min().unwrap());
            let hi = fa.iter().max().unwrap().min(fb.iter().max().unwrap());
            if lo > hi
                || (lo == hi
                    && shared
                        .iter()
                        .any(|p| dot(p, &n) == *plane && dot(p, &tangent) == *lo))
            {
                return Ok(true);
            }
        }
    }
    Ok(false)
}
fn monotone(c: &C, direction: &P) -> bool {
    dot(&sub(&c[3], &c[0]), direction) > R::zero()
        && c.windows(2)
            .all(|v| dot(&sub(&v[1], &v[0]), direction) >= R::zero())
}
fn metric_delta(p: &P, m: Matrix) -> P {
    [
        &p[0] * r(m[0]) + &p[1] * r(m[2]),
        &p[0] * r(m[1]) + &p[1] * r(m[3]),
    ]
}
fn bound(
    original: &[C],
    candidate: &C,
    times: &[R],
    metric: Matrix,
    budget: &mut Budget,
) -> Result<R, Error> {
    let mut maximum = R::zero();
    for (i, c) in original.iter().enumerate() {
        budget.spend(64)?;
        let q = restrict(candidate, &times[i], &times[i + 1]);
        for j in 0..4 {
            let delta = metric_delta(&sub(&c[j], &q[j]), metric);
            maximum = maximum.max(dot(&delta, &delta));
        }
    }
    Ok(maximum)
}
fn evaluate(c: &C, t: f64) -> Point {
    let weights = [
        (1.0 - t).powi(3),
        3.0 * (1.0 - t).powi(2) * t,
        3.0 * (1.0 - t) * t * t,
        t * t * t,
    ];
    std::array::from_fn(|k| {
        c.iter()
            .zip(weights)
            .map(|(p, w)| p[k].to_f64().unwrap() * w)
            .sum()
    })
}
// Least squares proposes a cubic. It cannot authorize an edit: all certificates use its exact encoded f64 values.
fn fit(edges: &[Edge], curves: &[C], times: &[R]) -> Option<Edge> {
    let from = edges[0].from;
    let to = edges.last()?.to;
    let mut aa = 0.0;
    let mut ab = 0.0;
    let mut bb = 0.0;
    let mut ay = [0.0; 2];
    let mut by = [0.0; 2];
    for (i, c) in curves.iter().enumerate() {
        let t0 = times[i].to_f64()?;
        let t1 = times[i + 1].to_f64()?;
        for s in [0.25, 0.5, 0.75] {
            let t = t0 + (t1 - t0) * s;
            let a = 3.0 * (1.0 - t).powi(2) * t;
            let b = 3.0 * (1.0 - t) * t * t;
            let p = evaluate(c, s);
            aa += a * a;
            ab += a * b;
            bb += b * b;
            for k in 0..2 {
                let y = p[k] - (1.0 - t).powi(3) * from[k] - t.powi(3) * to[k];
                ay[k] += a * y;
                by[k] += b * y;
            }
        }
    }
    let determinant = aa * bb - ab * ab;
    if determinant <= 0.0 {
        return None;
    }
    let controls = [
        std::array::from_fn(|k| (bb * ay[k] - ab * by[k]) / determinant),
        std::array::from_fn(|k| (aa * by[k] - ab * ay[k]) / determinant),
    ];
    if controls
        .iter()
        .flatten()
        .any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE)
    {
        return None;
    }
    Some(Edge {
        from,
        to,
        controls: Some(controls),
    })
}
#[derive(Default)]
struct Rejections {
    monotonicity: usize,
    deviation: usize,
    topology: usize,
}
fn proposal(
    edges: &[Edge],
    obstacles: &[(C, Vec<P>)],
    tolerance: &R,
    metric: Matrix,
    budget: &mut Budget,
    rejections: &mut Rejections,
) -> Result<Option<(Edge, R, Vec<R>)>, Error> {
    let original: Vec<_> = edges.iter().map(cubic).collect();
    let start = original[0][0].clone();
    let end = original.last().unwrap()[3].clone();
    let direction = sub(&end, &start);
    budget.spend(original.len() * 16)?;
    if !original.iter().all(|c| monotone(c, &direction)) {
        rejections.monotonicity += 1;
        return Ok(None);
    }
    let length = dot(&direction, &direction);
    let mut projected = vec![R::zero()];
    for c in &original {
        projected.push(dot(&sub(&c[3], &start), &direction) / &length);
    }
    let uniform: Vec<_> = (0..=original.len())
        .map(|i| R::new(i.into(), original.len().into()))
        .collect();
    let line = Edge {
        from: edges[0].from,
        to: edges.last().unwrap().to,
        controls: None,
    };
    let mut choices = vec![(line, projected.clone())];
    if edges.len() > 1 {
        for times in [uniform, projected] {
            if let Some(c) = fit(edges, &original, &times) {
                choices.push((c, times));
            }
        }
    }
    for (candidate, times) in choices {
        let curve = cubic(&candidate);
        if !monotone(&curve, &direction) {
            rejections.monotonicity += 1;
            continue;
        }
        let deviation = bound(&original, &curve, &times, metric, budget)?;
        if deviation > *tolerance {
            rejections.deviation += 1;
            continue;
        }
        let swept = hull(
            original
                .iter()
                .flatten()
                .chain(curve.iter())
                .cloned()
                .collect(),
            budget,
        )?;
        let mut safe = true;
        for (other, h) in obstacles {
            let shared: Vec<_> = [start.clone(), end.clone()]
                .into_iter()
                .filter(|p| p == &other[0] || p == &other[3])
                .collect();
            if !separated(&swept, h, &shared, budget)? {
                safe = false;
                break;
            }
        }
        if safe {
            return Ok(Some((candidate, deviation, times)));
        }
        rejections.topology += 1;
    }
    Ok(None)
}
pub(crate) fn run(
    commands: &[PathCommand],
    tolerance: f64,
    metric: Matrix,
    selected: &[usize],
    max_span: usize,
    filled: bool,
) -> Result<(Vec<PathCommand>, Value), Error> {
    if !tolerance.is_finite()
        || !(0.0..=MAX_COORDINATE).contains(&tolerance)
        || !(2..=MAX_SPAN).contains(&max_span)
    {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Simplification requires tolerance in 0..=32768 and max_span in 2..=32",
        ));
    }
    let mut contours = paths::parse(commands);
    let mut selection = HashSet::new();
    for &i in selected {
        if i >= contours.len() || !selection.insert(i) {
            return Err(Error::new(
                "INVALID_OPERATION",
                "Simplification contour indices must be distinct and in range",
            ));
        }
    }
    if selected.is_empty() {
        selection.extend(0..contours.len());
    }
    let before: usize = contours.iter().map(|c| c.edges.len()).sum();
    let mut budget = Budget { used: 0 };
    let tol = r(tolerance);
    let tol2 = &tol * &tol;
    let mut rejections = Rejections::default();
    let mut reductions = Vec::new();
    let mut max_bound = R::zero();
    let mut originals: Vec<Vec<Vec<usize>>> = contours
        .iter()
        .map(|c| (0..c.edges.len()).map(|i| vec![i]).collect())
        .collect();
    for ci in 0..contours.len() {
        if !selection.contains(&ci) {
            continue;
        }
        let mut i = 0;
        while i < contours[ci].edges.len() {
            let max = max_span.min(contours[ci].edges.len() - i);
            let mut chosen = None;
            for span in (1..=max).rev() {
                if span == 1 && contours[ci].edges[i].controls.is_none() {
                    continue;
                }
                let mut obstacles = Vec::new();
                for (oi, c) in contours.iter().enumerate() {
                    for (j, e) in c.edges.iter().enumerate() {
                        if oi == ci && (i..i + span).contains(&j) {
                            continue;
                        }
                        let curve = cubic(e);
                        let h = hull(curve.to_vec(), &mut budget)?;
                        obstacles.push((curve, h));
                    }
                    let end = c.edges.last().unwrap().to;
                    if (c.closed || filled) && end != c.start {
                        let curve = cubic(&Edge {
                            from: end,
                            to: c.start,
                            controls: None,
                        });
                        let h = hull(curve.to_vec(), &mut budget)?;
                        obstacles.push((curve, h));
                    }
                }
                if let Some((edge, bound, times)) = proposal(
                    &contours[ci].edges[i..i + span],
                    &obstacles,
                    &tol2,
                    metric,
                    &mut budget,
                    &mut rejections,
                )? {
                    chosen = Some((span, edge, bound, times));
                    break;
                }
            }
            if let Some((span, edge, bound, times)) = chosen {
                let indices: Vec<_> = originals[ci][i..i + span]
                    .iter()
                    .flatten()
                    .copied()
                    .collect();
                max_bound = max_bound.max(bound.clone());
                reductions.push(json!({"contour_index":ci,"source_edge_indices":indices,"output_edge_index":i,"output_type":if edge.controls.is_some(){"cubic"}else{"line"},"deviation_squared":bound.to_string(),"source_parameter_boundaries":times.iter().map(ToString::to_string).collect::<Vec<_>>() }));
                contours[ci].edges.splice(i..i + span, [edge]);
                originals[ci].splice(i..i + span, [indices]);
            }
            i += 1;
        }
    }
    let after: usize = contours.iter().map(|c| c.edges.len()).sum();
    let mut bound = if max_bound.is_zero() {
        0.0
    } else {
        max_bound
            .to_f64()
            .unwrap()
            .next_up()
            .sqrt()
            .next_up()
            .min(tolerance)
    };
    // The displayed floating bound must also be an upper bound; never trust conversion rounding.
    if r(bound) * r(bound) < max_bound {
        bound = tolerance;
    }
    let report = json!({"changed":!reductions.is_empty(),"input_edges":before,"output_edges":after,"removed_edges":before-after,"tolerance":tolerance,"metric_matrix":metric,"deviation_bound":bound,"maximum_deviation_squared":max_bound.to_string(),"certificate":"exact_rational_bernstein_and_separating_hulls","topology_scope":"this_compound_path_including_fill_closure","retained_candidates":{"monotonicity":rejections.monotonicity,"deviation":rejections.deviation,"topology":rejections.topology},"work_units":budget.used,"reductions":reductions});
    Ok((paths::emit(&contours), report))
}
