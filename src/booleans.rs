//! Original exact planar arrangements over a declared curve-flattening model.
use crate::{Error, model::*, paths, scene};
use num_rational::BigRational as R;
use num_traits::{ToPrimitive, Zero};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    cmp::Ordering,
    collections::{BTreeMap, BTreeSet},
};
mod curves;
mod topology;

pub const MAX_INPUTS: usize = 16;
pub const MAX_EDGES: usize = 512;
pub const MAX_ATOMS: usize = 4096;
pub const MAX_WORK: usize = 2_000_000;
pub fn default_tolerance() -> f64 {
    0.125
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Mode {
    Union,
    Intersection,
    Difference,
    Xor,
}
type P = [R; 2];
type Segment = [P; 2];
type Cubic = [P; 4];
struct Operand {
    edges: Vec<Segment>,
    cubics: Vec<Cubic>,
    rule: FillRule,
    maximum: R,
}
fn r(x: f64) -> R {
    R::from_float(x).expect("validated finite coordinates")
}
fn n(x: i32) -> R {
    R::from_integer(x.into())
}
fn sub(a: &P, b: &P) -> P {
    [&a[0] - &b[0], &a[1] - &b[1]]
}
fn cross(a: &P, b: &P) -> R {
    &a[0] * &b[1] - &a[1] * &b[0]
}
fn dot(a: &P, b: &P) -> R {
    &a[0] * &b[0] + &a[1] * &b[1]
}
fn lerp(a: &P, b: &P, t: &R) -> P {
    std::array::from_fn(|i| &a[i] + (&b[i] - &a[i]) * t)
}
fn mapped(p: Point, m: Matrix) -> P {
    mapped_r(&p.map(r), m)
}
fn mapped_r(p: &P, m: Matrix) -> P {
    [
        &p[0] * r(m[0]) + &p[1] * r(m[2]) + r(m[4]),
        &p[0] * r(m[1]) + &p[1] * r(m[3]) + r(m[5]),
    ]
}
fn split(c: &Cubic) -> (Cubic, Cubic) {
    let t = R::new(1.into(), 2.into());
    let a = lerp(&c[0], &c[1], &t);
    let b = lerp(&c[1], &c[2], &t);
    let d = lerp(&c[2], &c[3], &t);
    let e = lerp(&a, &b, &t);
    let f = lerp(&b, &d, &t);
    let g = lerp(&e, &f, &t);
    ([c[0].clone(), a, e, g.clone()], [g, f, d, c[3].clone()])
}
#[derive(Default)]
struct Budget {
    used: usize,
}
impl Budget {
    fn spend(&mut self, v: usize) -> Result<(), Error> {
        self.used = self.used.saturating_add(v);
        if self.used > MAX_WORK {
            Err(limit("Boolean arrangement exceeds its exact-work budget"))
        } else {
            Ok(())
        }
    }
}
fn emit_edge(edges: &mut Vec<Segment>, a: P, b: P) -> Result<(), Error> {
    if a != b {
        edges.push([a, b]);
        if edges.len() > MAX_EDGES {
            return Err(limit("Boolean input exceeds 512 flattened edges"));
        }
    }
    Ok(())
}
fn input(document: &Document, index: usize) -> Result<Operand, Error> {
    let (Content::Vector {
        geometry,
        fill_rule,
        ..
    }
    | Content::WorkPath {
        geometry,
        fill_rule,
    }) = &document.items[index].content
    else {
        return Err(Error::new(
            "UNSUPPORTED",
            "Boolean operands must be vector geometry or work paths",
        ));
    };
    let m = scene::world_transform(document, index)?;
    if let Geometry::Rect {
        x,
        y,
        width,
        height,
    } = geometry
    {
        let (x, y, w, h) = (r(*x), r(*y), r(*width), r(*height));
        let points = [
            [x.clone(), y.clone()],
            [&x + &w, y.clone()],
            [&x + &w, &y + &h],
            [x, &y + &h],
        ];
        let points = points.map(|p| mapped_r(&p, m));
        return Ok(Operand {
            edges: (0..4)
                .map(|i| [points[i].clone(), points[(i + 1) % 4].clone()])
                .collect(),
            cubics: vec![],
            rule: *fill_rule,
            maximum: R::zero(),
        });
    }
    if matches!(geometry, Geometry::Ellipse { .. }) {
        return Err(Error::new(
            "UNSUPPORTED",
            "Convert analytic ellipses explicitly to paths before combining; quarter-cubic conversion has its own disclosed error",
        ));
    }
    let Geometry::Path { commands } = crate::primitives::expand(geometry)? else {
        unreachable!()
    };
    let mut out = Vec::new();
    let mut cubics = Vec::new();
    for c in paths::parse(&commands) {
        for e in &c.edges {
            if let Some([a, b]) = e.controls {
                cubics.push([
                    mapped(e.from, m),
                    mapped(a, m),
                    mapped(b, m),
                    mapped(e.to, m),
                ]);
            } else {
                emit_edge(&mut out, mapped(e.from, m), mapped(e.to, m))?;
            }
            if out.len() + cubics.len() > MAX_EDGES {
                return Err(limit("Boolean input exceeds 512 source edges"));
            }
        }
        let end = c.edges.last().unwrap().to;
        emit_edge(&mut out, mapped(end, m), mapped(c.start, m))?;
    }
    Ok(Operand {
        edges: out,
        cubics,
        rule: *fill_rule,
        maximum: R::zero(),
    })
}
fn unit(t: &R) -> bool {
    t >= &R::zero() && t <= &n(1)
}
fn parameter(p: &P, e: &Segment) -> R {
    let axis = usize::from(e[0][0] == e[1][0]);
    (&p[axis] - &e[0][axis]) / (&e[1][axis] - &e[0][axis])
}
fn intersections(a: &Segment, b: &Segment) -> Vec<(R, R)> {
    let u = sub(&a[1], &a[0]);
    let v = sub(&b[1], &b[0]);
    let offset = sub(&b[0], &a[0]);
    let determinant = cross(&u, &v);
    if !determinant.is_zero() {
        let t = cross(&offset, &v) / &determinant;
        let s = cross(&offset, &u) / determinant;
        return if unit(&t) && unit(&s) {
            vec![(t, s)]
        } else {
            vec![]
        };
    }
    if !cross(&offset, &u).is_zero() {
        return vec![];
    }
    let mut out: BTreeSet<(R, R)> = BTreeSet::new();
    for p in a.iter().chain(b.iter()) {
        let t = parameter(p, a);
        let s = parameter(p, b);
        if unit(&t) && unit(&s) {
            out.insert((t, s));
        }
    }
    out.into_iter().collect()
}
fn winding(point: &P, edges: &[Segment]) -> i32 {
    let mut value = 0;
    for e in edges {
        let side = cross(&sub(&e[1], &e[0]), &sub(point, &e[0]));
        if e[0][1] <= point[1] && point[1] < e[1][1] && side > R::zero() {
            value += 1;
        }
        if e[1][1] <= point[1] && point[1] < e[0][1] && side < R::zero() {
            value -= 1;
        }
    }
    value
}
fn inside(w: i32, rule: FillRule) -> bool {
    match rule {
        FillRule::Nonzero => w != 0,
        FillRule::EvenOdd => w % 2 != 0,
    }
}
fn truth(states: &[bool], mode: Mode) -> bool {
    match mode {
        Mode::Union => states.iter().any(|v| *v),
        Mode::Intersection => states.iter().all(|v| *v),
        Mode::Difference => states[0] && !states[1..].iter().any(|v| *v),
        Mode::Xor => states.iter().filter(|v| **v).count() % 2 != 0,
    }
}
// Pick a rational point strictly in the edge's left face, before the nearest normal-ray event.
fn left_sample(edge: &Segment, raw: &[Segment], budget: &mut Budget) -> Result<P, Error> {
    let mid = lerp(&edge[0], &edge[1], &R::new(1.into(), 2.into()));
    let d = sub(&edge[1], &edge[0]);
    let normal = [-d[1].clone(), d[0].clone()];
    let square = dot(&normal, &normal);
    let mut nearest: Option<R> = None;
    for other in raw {
        budget.spend(1)?;
        let v = sub(&other[1], &other[0]);
        let offset = sub(&other[0], &mid);
        let determinant = cross(&normal, &v);
        let candidates = if determinant.is_zero() {
            if cross(&offset, &normal).is_zero() {
                other
                    .iter()
                    .map(|p| dot(&sub(p, &mid), &normal) / &square)
                    .collect()
            } else {
                vec![]
            }
        } else {
            let t = cross(&offset, &v) / &determinant;
            let s = cross(&offset, &normal) / determinant;
            if unit(&s) { vec![t] } else { vec![] }
        };
        for t in candidates {
            if t > R::zero() && nearest.as_ref().is_none_or(|v| t < *v) {
                nearest = Some(t);
            }
        }
    }
    let step = nearest.map_or(n(1), |v| v / n(2));
    Ok([&mid[0] + &normal[0] * &step, &mid[1] + &normal[1] * step])
}
fn half(p: &P) -> bool {
    p[1] < R::zero() || (p[1].is_zero() && p[0] < R::zero())
}
fn angle(a: &P, b: &P) -> Ordering {
    half(a)
        .cmp(&half(b))
        .then_with(|| cross(b, a).cmp(&R::zero()))
}
fn area(points: &[P]) -> R {
    points
        .iter()
        .zip(points.iter().cycle().skip(1))
        .take(points.len())
        .map(|(a, b)| cross(a, b))
        .sum::<R>()
        / n(2)
}
fn topology(message: &str) -> Error {
    Error::new("TOPOLOGY_ERROR", message)
}
fn trace(boundary: &[Segment], budget: &mut Budget) -> Result<Vec<Vec<P>>, Error> {
    let mut outgoing: BTreeMap<P, Vec<usize>> = BTreeMap::new();
    let mut degree: BTreeMap<P, usize> = BTreeMap::new();
    for (i, e) in boundary.iter().enumerate() {
        outgoing.entry(e[0].clone()).or_default().push(i);
        for p in e {
            *degree.entry(p.clone()).or_default() += 1;
        }
    }
    let mut next = vec![0; boundary.len()];
    let mut chosen = BTreeSet::new();
    for (i, e) in boundary.iter().enumerate() {
        let reverse = sub(&e[0], &e[1]);
        let candidates = outgoing
            .get(&e[1])
            .ok_or_else(|| topology("Boolean boundary is open"))?;
        budget.spend(candidates.len())?;
        let j = *candidates
            .iter()
            .max_by(|&&a, &&b| {
                let a = sub(&boundary[a][1], &e[1]);
                let b = sub(&boundary[b][1], &e[1]);
                angle(
                    &[dot(&reverse, &a), cross(&reverse, &a)],
                    &[dot(&reverse, &b), cross(&reverse, &b)],
                )
            })
            .unwrap();
        if !chosen.insert(j) {
            return Err(topology("Boolean boundary has ambiguous face adjacency"));
        }
        next[i] = j;
    }
    let mut used = vec![false; boundary.len()];
    let mut loops = Vec::new();
    for start in 0..boundary.len() {
        if used[start] {
            continue;
        }
        let mut i = start;
        let mut points = Vec::new();
        loop {
            if used[i] {
                if i != start {
                    return Err(topology("Boundary traversal joined a different cycle"));
                }
                break;
            }
            used[i] = true;
            points.push(boundary[i][0].clone());
            i = next[i];
        }
        loop {
            let remove = (0..points.len()).find(|&i| {
                let prev = &points[(i + points.len() - 1) % points.len()];
                let p = &points[i];
                let next = &points[(i + 1) % points.len()];
                let a = sub(p, prev);
                let b = sub(next, p);
                degree[p] == 2 && cross(&a, &b).is_zero() && dot(&a, &b) > R::zero()
            });
            if let Some(i) = remove {
                points.remove(i);
            } else {
                break;
            }
        }
        if points.len() < 3 || area(&points).is_zero() {
            return Err(topology("Boolean boundary has a degenerate face"));
        }
        let start = points.iter().enumerate().min_by_key(|(_, p)| *p).unwrap().0;
        points.rotate_left(start);
        loops.push(points);
    }
    loops.sort();
    Ok(loops)
}
fn loop_edges(points: &[P]) -> Vec<Segment> {
    points
        .iter()
        .zip(points.iter().cycle().skip(1))
        .take(points.len())
        .map(|(a, b)| [a.clone(), b.clone()])
        .collect()
}
fn on_boundary(p: &P, edges: &[Segment]) -> bool {
    edges
        .iter()
        .any(|e| cross(&sub(&e[1], &e[0]), &sub(p, &e[0])).is_zero() && unit(&parameter(p, e)))
}
fn rounding(loops: &[Vec<P>], budget: &mut Budget) -> Result<(Vec<Vec<Point>>, R), Error> {
    let error = || {
        Error::new(
            "PRECISION_LOSS",
            "Boolean topology cannot be retained in f64 output coordinates",
        )
    };
    let mut mapping: BTreeMap<P, P> = BTreeMap::new();
    let mut reverse: BTreeMap<P, P> = BTreeMap::new();
    let mut largest = R::zero();
    let mut result = Vec::new();
    let mut exact = Vec::new();
    for points in loops {
        let mut output = Vec::new();
        let mut rational = Vec::new();
        for p in points {
            let q = [
                p[0].to_f64().ok_or_else(error)?,
                p[1].to_f64().ok_or_else(error)?,
            ];
            if q.iter().any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE) {
                return Err(invalid(
                    "Boolean output exceeds root geometry coordinate limits",
                ));
            }
            let qp = q.map(r);
            if reverse.get(&qp).is_some_and(|other| other != p) {
                return Err(error());
            }
            reverse.insert(qp.clone(), p.clone());
            mapping.insert(p.clone(), qp.clone());
            let d = sub(p, &qp);
            largest = largest.max(dot(&d, &d));
            output.push(q);
            rational.push(qp);
        }
        if area(points).cmp(&R::zero()) != area(&rational).cmp(&R::zero()) {
            return Err(error());
        }
        result.push(output);
        exact.push(rational);
    }
    let old_edges: Vec<_> = loops.iter().flat_map(|p| loop_edges(p)).collect();
    let new_edges: Vec<_> = exact.iter().flat_map(|p| loop_edges(p)).collect();
    for i in 0..new_edges.len() {
        for j in i + 1..new_edges.len() {
            budget.spend(1)?;
            let intersections = intersections(&new_edges[i], &new_edges[j]);
            if intersections.len() > 1 {
                return Err(error());
            }
            for (t, u) in intersections {
                if !(t.is_zero() || t == n(1)) || !(u.is_zero() || u == n(1)) {
                    return Err(error());
                }
            }
        }
    }
    // Preserve cyclic ray order at shared vertices, not just intersection counts.
    let mut rays: BTreeMap<P, Vec<P>> = BTreeMap::new();
    for e in &old_edges {
        rays.entry(e[0].clone()).or_default().push(e[1].clone());
        rays.entry(e[1].clone()).or_default().push(e[0].clone());
    }
    for (p, neighbors) in rays {
        let mut old: Vec<_> = (0..neighbors.len()).collect();
        let mut new = old.clone();
        budget.spend(neighbors.len() * 8)?;
        old.sort_by(|&a, &b| angle(&sub(&neighbors[a], &p), &sub(&neighbors[b], &p)));
        new.sort_by(|&a, &b| {
            angle(
                &sub(&mapping[&neighbors[a]], &mapping[&p]),
                &sub(&mapping[&neighbors[b]], &mapping[&p]),
            )
        });
        if let Some(k) = new.iter().position(|v| *v == old[0]) {
            new.rotate_left(k);
        }
        if old != new {
            return Err(error());
        }
    }
    for i in 0..loops.len() {
        for j in 0..loops.len() {
            if i == j {
                continue;
            }
            let a = loop_edges(&loops[j]);
            let b = loop_edges(&exact[j]);
            budget.spend(a.len() * loops[i].len())?;
            if let Some(k) = loops[i].iter().position(|p| !on_boundary(p, &a))
                && winding(&loops[i][k], &a) != winding(&exact[i][k], &b)
            {
                return Err(error());
            }
        }
    }
    Ok((result, largest))
}
pub fn compute(
    document: &Document,
    ids: &[String],
    mode: Mode,
    curve_tolerance: f64,
) -> Result<Value, Error> {
    crate::validate(document)?;
    if !(2..=MAX_INPUTS).contains(&ids.len())
        || !curve_tolerance.is_finite()
        || !(0.0..=64.0).contains(&curve_tolerance)
    {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Boolean requires 2..=16 distinct vector IDs and curve_tolerance in 0..=64",
        ));
    }
    let mut unique = BTreeSet::new();
    let mut inputs = Vec::new();
    let mut summaries = Vec::new();
    let mut budget = Budget::default();
    let tol = r(curve_tolerance);
    let tol2 = &tol * &tol;
    for id in ids {
        if !unique.insert(id) {
            return Err(Error::new(
                "INVALID_REQUEST",
                "Boolean source IDs must be distinct",
            ));
        }
        let index = scene::index(document, id)?;
        inputs.push(input(document, index)?);
    }
    let curves = curves::evaluate(&mut inputs, &tol2, &mut budget)?;
    for (id, input) in ids.iter().zip(&inputs) {
        summaries.push(json!({"id":id,"flattened_edges":input.edges.len(),"flattening_deviation_squared":input.maximum.to_string(),"fill_rule":input.rule}));
    }
    let raw: Vec<_> = inputs.iter().flat_map(|v| v.edges.clone()).collect();
    if raw.len() > MAX_EDGES {
        return Err(limit("Boolean inputs exceed 512 aggregate flattened edges"));
    }
    let mut cuts = vec![BTreeSet::from([R::zero(), n(1)]); raw.len()];
    for i in 0..raw.len() {
        for j in i + 1..raw.len() {
            budget.spend(1)?;
            for (a, b) in intersections(&raw[i], &raw[j]) {
                cuts[i].insert(a);
                cuts[j].insert(b);
            }
        }
    }
    let mut atoms: BTreeMap<Segment, Vec<i32>> = BTreeMap::new();
    let mut index = 0;
    for (source, input) in inputs.iter().enumerate() {
        for e in &input.edges {
            let points: Vec<_> = cuts[index].iter().map(|t| lerp(&e[0], &e[1], t)).collect();
            index += 1;
            for pair in points.windows(2) {
                let (key, sign) = if pair[0] < pair[1] {
                    ([pair[0].clone(), pair[1].clone()], 1)
                } else {
                    ([pair[1].clone(), pair[0].clone()], -1)
                };
                atoms.entry(key).or_insert_with(|| vec![0; inputs.len()])[source] += sign;
            }
            if atoms.len() > MAX_ATOMS {
                return Err(limit("Boolean arrangement exceeds 4096 atomic edges"));
            }
        }
    }
    let atom_count = atoms.len();
    let mut boundary = Vec::new();
    for (edge, weights) in atoms {
        if weights.iter().all(|v| *v == 0) {
            continue;
        }
        let sample = left_sample(&edge, &raw, &mut budget)?;
        budget.spend(raw.len())?;
        let left: Vec<_> = inputs.iter().map(|v| winding(&sample, &v.edges)).collect();
        let a: Vec<_> = left
            .iter()
            .zip(&inputs)
            .map(|(&w, input)| inside(w, input.rule))
            .collect();
        let b: Vec<_> = left
            .iter()
            .zip(&weights)
            .zip(&inputs)
            .map(|((&w, &delta), input)| inside(w - delta, input.rule))
            .collect();
        let a = truth(&a, mode);
        let b = truth(&b, mode);
        if a != b {
            boundary.push(if a {
                edge
            } else {
                [edge[1].clone(), edge[0].clone()]
            });
        }
    }
    let loops = trace(&boundary, &mut budget)?;
    let exact_area: R = loops.iter().map(|p| area(p)).sum();
    let (rounded, rounding) = rounding(&loops, &mut budget)?;
    let mut commands = Vec::new();
    for points in &rounded {
        commands.push(PathCommand::Move { to: points[0] });
        commands.extend(points[1..].iter().map(|p| PathCommand::Line { to: *p }));
        commands.push(PathCommand::Close {});
    }
    let geometry = if commands.is_empty() {
        None
    } else {
        let g = Geometry::Path { commands };
        crate::geometry::validate_geometry(&g)?;
        Some(g)
    };
    Ok(
        json!({"document_id":document.id,"revision":document.revision,"source_ids":ids,"mode":mode,"geometry":geometry,"fill_rule":"nonzero","coordinates":"document_root","empty":loops.is_empty(),"area_exact":exact_area.to_string(),"area":exact_area.to_f64(),"positive_contours":loops.iter().filter(|p|area(p)>R::zero()).count(),"negative_contours":loops.iter().filter(|p|area(p)<R::zero()).count(),"input_model":"world_space_closed_geometry_with_exact_certified_cubic_flattening","curve_tolerance":curve_tolerance,"inputs":summaries,"curves":curves,"rounding_deviation_squared":rounding.to_string(),"atomic_edges":atom_count,"boundary_edges":boundary.len(),"work_units":budget.used,"losses":["This is a geometry-only result. Paint, strokes, masks, clips, filters, visibility and opacity do not define operands. Sources are unchanged.","Curved boundaries become chords only after an exact simultaneous-deformation certificate. Tolerance bounds each input arc, not movement of intersection vertices or the final boolean boundary. Collinear retracing is reduced by exact filled winding; source strokes and zero-area traces are not retained.","Output vertices are rounded to f64 with explicit planarity, winding, nesting and adjacency checks. Exact area refers to the rational arrangement before this rounding."]}),
    )
}
