//! Original bounded ribbon, join, cap and endpoint geometry.
use super::*;
use crate::paths::{Contour, Edge};
use std::f64::consts::{PI, TAU};

pub const MAX_OUTLINE_COMMANDS: usize = 65_536;
const MAX_POINTS: usize = 16_384;
fn limit() -> Error {
    Error::new(
        "LIMIT_EXCEEDED",
        "Stroke outline exceeds subdivision or generated-command limits",
    )
}
fn add(a: Point, b: Point) -> Point {
    [a[0] + b[0], a[1] + b[1]]
}
fn sub(a: Point, b: Point) -> Point {
    [a[0] - b[0], a[1] - b[1]]
}
fn mul(a: Point, f: f64) -> Point {
    a.map(|v| v * f)
}
fn cross(a: Point, b: Point) -> f64 {
    a[0] * b[1] - a[1] * b[0]
}
fn dot(a: Point, b: Point) -> f64 {
    a[0] * b[0] + a[1] * b[1]
}
fn unit(a: Point) -> Point {
    let l = a[0].hypot(a[1]);
    if l == 0.0 {
        [1.0, 0.0]
    } else {
        a.map(|v| v / l)
    }
}
fn normal(a: Point) -> Point {
    [-a[1], a[0]]
}
fn midpoint(a: Point, b: Point) -> Point {
    mul(add(a, b), 0.5)
}
fn point_segment(p: Point, a: Point, b: Point) -> f64 {
    let v = sub(b, a);
    let length = dot(v, v);
    if length == 0.0 {
        distance(p, a)
    } else {
        distance(
            p,
            add(a, mul(v, (dot(sub(p, a), v) / length).clamp(0.0, 1.0))),
        )
    }
}
fn push(points: &mut Vec<Point>, p: Point) -> Result<(), Error> {
    if points.last() != Some(&p) {
        points.push(p);
    }
    if points.len() > MAX_POINTS {
        return Err(limit());
    }
    Ok(())
}
fn flatten(
    c: [Point; 4],
    tolerance: f64,
    length_error: f64,
    depth: u8,
    points: &mut Vec<Point>,
) -> Result<(), Error> {
    let chord = distance(c[0], c[3]);
    let polygon = distance(c[0], c[1]) + distance(c[1], c[2]) + distance(c[2], c[3]);
    if point_segment(c[1], c[0], c[3]).max(point_segment(c[2], c[0], c[3])) <= tolerance
        && polygon - chord <= length_error
    {
        return push(points, c[3]);
    }
    if depth == 24 {
        return Err(limit());
    }
    let a = midpoint(c[0], c[1]);
    let b = midpoint(c[1], c[2]);
    let d = midpoint(c[2], c[3]);
    let e = midpoint(a, b);
    let f = midpoint(b, d);
    let m = midpoint(e, f);
    flatten(
        [c[0], a, e, m],
        tolerance,
        length_error / 2.0,
        depth + 1,
        points,
    )?;
    flatten(
        [m, f, d, c[3]],
        tolerance,
        length_error / 2.0,
        depth + 1,
        points,
    )
}
pub(super) struct Centerline {
    pub(super) points: Vec<Point>,
    pub(super) lengths: Vec<f64>,
    pub(super) anchors: Vec<usize>,
    closed: bool,
}
impl Centerline {
    pub(super) fn new(c: &Contour, tolerance: f64) -> Result<Self, Error> {
        let mut points = vec![c.start];
        let mut anchors = vec![0];
        let curves = c
            .edges
            .iter()
            .filter(|e| e.controls.is_some())
            .count()
            .max(1);
        for e in &c.edges {
            if let Some([a, b]) = e.controls {
                flatten(
                    [e.from, a, b, e.to],
                    tolerance,
                    tolerance / curves as f64,
                    0,
                    &mut points,
                )?;
            } else {
                push(&mut points, e.to)?;
            }
            if anchors.last() != Some(&(points.len() - 1)) {
                anchors.push(points.len() - 1);
            }
        }
        if c.closed {
            push(&mut points, c.start)?;
        }
        let mut lengths = vec![0.0];
        for pair in points.windows(2) {
            let previous = *lengths.last().unwrap();
            let next = previous + distance(pair[0], pair[1]);
            if next == previous {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "Stroke segments are below path-length precision",
                ));
            }
            lengths.push(next);
        }
        Ok(Self {
            points,
            lengths,
            anchors,
            closed: c.closed,
        })
    }
    pub(super) fn length(&self) -> f64 {
        *self.lengths.last().unwrap()
    }
    pub(super) fn direction(&self, s: f64) -> Point {
        if self.points.len() < 2 {
            return [1.0, 0.0];
        }
        let i = self
            .lengths
            .partition_point(|&v| v <= s)
            .clamp(1, self.points.len() - 1);
        unit(sub(self.points[i], self.points[i - 1]))
    }
    pub(super) fn at(&self, s: f64) -> Point {
        let i = self.lengths.partition_point(|&v| v < s);
        if i == 0 {
            return self.points[0];
        }
        if i == self.lengths.len() {
            return *self.points.last().unwrap();
        }
        if self.lengths[i] == s {
            return self.points[i];
        }
        let t = (s - self.lengths[i - 1]) / (self.lengths[i] - self.lengths[i - 1]);
        add(
            self.points[i - 1],
            mul(sub(self.points[i], self.points[i - 1]), t),
        )
    }
    fn nodes(&self, a: f64, b: f64, stroke: &Stroke) -> Result<Vec<Node>, Error> {
        let lo = self.lengths.partition_point(|&v| v <= a);
        let hi = self.lengths.partition_point(|&v| v < b);
        // Authored cuts/knots take precedence over a subdivision vertex that
        // rounds to the same point. Distinct authored cuts must remain distinct.
        let mut positions = vec![(a, true), (b, true)];
        positions.extend(self.lengths[lo..hi.max(lo)].iter().map(|&s| (s, false)));
        positions.extend(
            stroke
                .width_profile
                .iter()
                .map(|p| p[0] * self.length())
                .filter(|&s| s > a && s < b)
                .map(|s| (s, true)),
        );
        positions.sort_by(|a, b| a.0.total_cmp(&b.0).then_with(|| b.1.cmp(&a.1)));
        positions.dedup_by(|a, b| a.0 == b.0);
        let mut nodes: Vec<(Node, f64, bool)> = Vec::new();
        for (s, authored) in positions {
            let node = Node {
                p: self.at(s),
                r: radius(
                    stroke,
                    if self.length() == 0.0 {
                        0.0
                    } else {
                        s / self.length()
                    },
                ),
            };
            if let Some((previous, at, previous_authored)) = nodes.last_mut()
                && previous.p == node.p
            {
                let coordinate_error =
                    8.0 * f64::EPSILON * (node.p[0].abs().max(node.p[1].abs()) + self.length());
                let radius_error = 8.0 * f64::EPSILON * previous.r.max(node.r).max(stroke.width);
                if authored == *previous_authored
                    || (s - *at).abs() > coordinate_error
                    || (previous.r - node.r).abs() > radius_error
                {
                    return Err(Error::new(
                        "UNSUPPORTED",
                        "Stroke cuts are below coordinate precision",
                    ));
                }
                if authored {
                    *previous = node;
                    *at = s;
                    *previous_authored = true;
                }
            } else {
                nodes.push((node, s, authored));
            }
        }
        Ok(nodes.into_iter().map(|(node, _, _)| node).collect())
    }
}
#[derive(Clone, Copy)]
struct Node {
    p: Point,
    r: f64,
}
pub(super) fn radius(s: &Stroke, t: f64) -> f64 {
    if s.width_profile.is_empty() {
        return s.width / 2.0;
    }
    let p = &s.width_profile;
    let i = p.partition_point(|v| v[0] < t);
    let factor = if i == 0 {
        p[0][1]
    } else if i == p.len() {
        p.last().unwrap()[1]
    } else {
        let f = (t - p[i - 1][0]) / (p[i][0] - p[i - 1][0]);
        p[i - 1][1] * (1.0 - f) + p[i][1] * f
    };
    s.width * factor / 2.0
}
fn ranges(s: &Stroke, length: f64) -> Result<Vec<(f64, f64)>, Error> {
    let Some(d) = &s.dash else {
        return Ok(vec![(0.0, length)]);
    };
    let mut array = d.array.clone();
    if array.iter().all(|&v| v == 0.0) {
        return Ok(vec![(0.0, length)]);
    }
    if array.len() % 2 == 1 {
        array.extend_from_within(..);
    }
    let period = array.iter().sum::<f64>();
    let mut phase = d.offset.rem_euclid(period);
    let mut i = 0;
    while phase > array[i] {
        phase -= array[i];
        i = (i + 1) % array.len();
    }
    let mut remaining = array[i] - phase;
    let mut at = 0.0;
    let mut out = vec![];
    for _ in 0..MAX_DOCUMENT_WORK {
        let next = (at + remaining).min(length);
        if remaining > 0.0 && next == at && at < length {
            return Err(Error::new(
                "UNSUPPORTED",
                "Dash intervals are below path-length precision",
            ));
        }
        if i % 2 == 0 {
            out.push((at, next));
        }
        if next == length {
            return Ok(out);
        }
        at = next;
        i = (i + 1) % array.len();
        remaining = array[i];
    }
    Err(limit())
}
struct Builder {
    commands: Vec<PathCommand>,
    tolerance: f64,
}
impl Builder {
    fn polygon(&mut self, mut p: Vec<Point>) -> Result<(), Error> {
        self.contour(&mut p, true)
    }
    fn contour(&mut self, p: &mut Vec<Point>, positive: bool) -> Result<(), Error> {
        p.dedup();
        if p.len() > 1 && p.first() == p.last() {
            p.pop();
        }
        if p.len() < 3 {
            return Ok(());
        }
        let area = p[1..]
            .windows(2)
            .map(|w| cross(sub(w[0], p[0]), sub(w[1], p[0])))
            .sum::<f64>();
        if !area.is_finite() || p.iter().flatten().any(|v| !v.is_finite()) {
            return Err(Error::new("UNSUPPORTED", "Stroke outline is not finite"));
        }
        if positive && area == 0.0 {
            return Ok(());
        }
        if positive && area < 0.0 {
            p.reverse();
        }
        if self.commands.len() + p.len() + 1 > MAX_OUTLINE_COMMANDS {
            return Err(limit());
        }
        self.commands.push(PathCommand::Move { to: p[0] });
        self.commands
            .extend(p[1..].iter().map(|&to| PathCommand::Line { to }));
        self.commands.push(PathCommand::Close {});
        Ok(())
    }
    fn arc_steps(&self, r: f64, angle: f64) -> Result<usize, Error> {
        let n = (angle.abs() / (8.0 * self.tolerance / r).sqrt())
            .ceil()
            .max((angle.abs() / (PI / 2.0)).ceil()) as usize;
        if n > MAX_OUTLINE_COMMANDS {
            return Err(limit());
        }
        Ok(n.max(1))
    }
    fn arc_points(
        &self,
        p: Point,
        r: f64,
        start: Point,
        end: Point,
        angle: f64,
    ) -> Result<Vec<Point>, Error> {
        if r == 0.0 {
            return Ok(vec![p]);
        }
        let n = self.arc_steps(r, angle)?;
        let theta = start[1].atan2(start[0]);
        let mut points = vec![add(p, mul(start, r))];
        for i in 1..n {
            let a = theta + angle * i as f64 / n as f64;
            points.push(add(p, [r * a.cos(), r * a.sin()]));
        }
        points.push(add(p, mul(end, r)));
        Ok(points)
    }
    fn side_join(
        &self,
        p: Node,
        u: Point,
        v: Point,
        side: f64,
        s: &Stroke,
    ) -> Result<Vec<Point>, Error> {
        let turn = cross(u, v);
        let cosine = dot(u, v);
        let a = mul(normal(u), side);
        let b = mul(normal(v), side);
        let q = add(p.p, mul(a, p.r));
        let r = add(p.p, mul(b, p.r));
        if p.r == 0.0 || (turn == 0.0 && cosine >= 0.0) {
            return Ok(vec![q]);
        }
        if turn * side > 0.0 {
            // Retain the center vertex on the inner side. A direct chord
            // would subtract a triangle and can create holes when the ribbon
            // folds or is wider than its centerline segments.
            return Ok(vec![q, p.p, r]);
        }
        match s.join {
            Join::Round => self.arc_points(
                p.p,
                p.r,
                a,
                b,
                if turn == 0.0 {
                    -side * PI
                } else {
                    turn.atan2(cosine)
                },
            ),
            Join::Miter => {
                if turn == 0.0 {
                    return Ok(vec![q, r]);
                }
                let m = add(q, mul(u, cross(sub(r, q), v) / turn));
                if distance(m, p.p) / p.r <= s.miter_limit {
                    Ok(vec![q, m, r])
                } else {
                    Ok(vec![q, r])
                }
            }
            Join::Bevel => Ok(vec![q, r]),
        }
    }
    fn cap_points(&self, p: Node, outward: Point, cap: Cap) -> Result<Vec<Point>, Error> {
        let n = normal(outward);
        let a = sub(p.p, mul(n, p.r));
        let b = add(p.p, mul(n, p.r));
        if p.r == 0.0 || cap == Cap::Butt {
            return Ok(vec![a, b]);
        }
        if cap == Cap::Round {
            self.arc_points(p.p, p.r, mul(n, -1.0), n, PI)
        } else {
            let v = mul(outward, p.r);
            Ok(vec![a, add(a, v), add(b, v), b])
        }
    }
    fn run(
        &mut self,
        nodes: &[Node],
        closed: bool,
        s: &Stroke,
        tangent: Point,
        caps: [Cap; 2],
    ) -> Result<(), Error> {
        if nodes.iter().all(|n| n.r == 0.0) {
            return Ok(());
        }
        if nodes.len() == 1 {
            let mut p = self.cap_points(nodes[0], tangent, caps[1])?;
            p.extend(self.cap_points(nodes[0], mul(tangent, -1.0), caps[0])?);
            self.polygon(p)?;
            return Ok(());
        }
        let directions: Vec<_> = nodes
            .windows(2)
            .map(|w| unit(sub(w[1].p, w[0].p)))
            .collect();
        let mut sides = [vec![], vec![]];
        for (side, points) in [-1.0, 1.0].into_iter().zip(&mut sides) {
            if closed {
                points.extend(self.side_join(
                    nodes[0],
                    *directions.last().unwrap(),
                    directions[0],
                    side,
                    s,
                )?);
            } else {
                points.push(add(
                    nodes[0].p,
                    mul(normal(directions[0]), side * nodes[0].r),
                ));
            }
            for i in 1..nodes.len() - 1 {
                points.extend(self.side_join(
                    nodes[i],
                    directions[i - 1],
                    directions[i],
                    side,
                    s,
                )?);
                if points.len() > MAX_OUTLINE_COMMANDS {
                    return Err(limit());
                }
            }
            if !closed {
                let p = nodes.last().unwrap();
                points.push(add(
                    p.p,
                    mul(normal(*directions.last().unwrap()), side * p.r),
                ));
            }
        }
        let [mut right, mut left] = sides;
        left.reverse();
        if closed {
            self.contour(&mut right, false)?;
            self.contour(&mut left, false)?;
        } else {
            right.extend(self.cap_points(
                *nodes.last().unwrap(),
                *directions.last().unwrap(),
                caps[1],
            )?);
            right.extend(left);
            right.extend(self.cap_points(nodes[0], mul(directions[0], -1.0), caps[0])?);
            self.polygon(right)?;
        }
        Ok(())
    }
    fn arrow(&mut self, tip: Point, direction: Point, a: &Arrow) -> Result<(), Error> {
        let l = a.length;
        let w = a.width / 2.0;
        let points = match a.kind {
            ArrowKind::Triangle => vec![[0.0, 0.0], [-l, w], [-l, -w]],
            ArrowKind::Chevron => vec![[0.0, 0.0], [-l, w], [-0.65 * l, 0.0], [-l, -w]],
            ArrowKind::Diamond => vec![[0.0, 0.0], [-l / 2.0, w], [-l, 0.0], [-l / 2.0, -w]],
            ArrowKind::Bar => vec![[0.0, w], [-l, w], [-l, -w], [0.0, -w]],
            ArrowKind::Ellipse => {
                let n = self.arc_steps((l / 2.0).max(w), TAU)?;
                (0..n)
                    .map(|i| {
                        let t = TAU * i as f64 / n as f64;
                        [-l / 2.0 + l / 2.0 * t.cos(), w * t.sin()]
                    })
                    .collect()
            }
        };
        let n = normal(direction);
        self.polygon(
            points
                .into_iter()
                .map(|p| add(tip, add(mul(direction, p[0]), mul(n, p[1]))))
                .collect(),
        )
    }
}
fn tangent(edges: &[Edge], start: Point, reverse: bool) -> Point {
    let points: Vec<_> = if reverse {
        edges
            .iter()
            .rev()
            .flat_map(|e| match e.controls {
                Some([a, b]) => vec![b, a, e.from],
                None => vec![e.from],
            })
            .collect()
    } else {
        edges
            .iter()
            .flat_map(|e| match e.controls {
                Some([a, b]) => vec![a, b, e.to],
                None => vec![e.to],
            })
            .collect()
    };
    unit(
        points
            .into_iter()
            .find(|&p| p != start)
            .map_or([1.0, 0.0], |p| sub(p, start)),
    )
}
pub(crate) fn generate(
    g: &Geometry,
    s: &Stroke,
    tolerance: f64,
) -> Result<Option<Geometry>, Error> {
    validate_controls(s)?;
    if !tolerance.is_finite() || tolerance <= 0.0 || tolerance > s.curve_tolerance {
        return Err(invalid(
            "Internal stroke refinement must retain a positive bounded tolerance",
        ));
    }
    if let Some(brush) = &s.brush {
        return super::brush::generate(g, s, brush, tolerance);
    }
    let contours = contours(g)?;
    let mut builder = Builder {
        commands: vec![],
        tolerance,
    };
    for contour in &contours {
        if contour.closed
            && !s.width_profile.is_empty()
            && s.width_profile[0][1] != s.width_profile.last().unwrap()[1]
        {
            return Err(invalid(
                "Closed-contour width profiles must have equal endpoint factors",
            ));
        }
        let center = Centerline::new(contour, tolerance)?;
        let length = center.length();
        // Attach the shaft halfway into an endpoint arrow. Clipping here is
        // independent of dash phase and profile position; forced cuts are butt
        // caps so a round/square line end cannot project beyond the arrow tip.
        let lo = s
            .start_arrow
            .as_ref()
            .map_or(0.0, |a| (a.length / 2.0).min(length));
        let hi = s
            .end_arrow
            .as_ref()
            .map_or(length, |a| (length - a.length / 2.0).max(0.0));
        let ranges: Vec<_> = ranges(s, length)?
            .into_iter()
            .filter_map(|(a, b)| {
                let a = a.max(lo);
                let b = b.min(hi);
                (a <= b).then_some((a, b))
            })
            .collect();
        let first = tangent(&contour.edges, contour.start, false);
        let mut runs: Vec<_> = ranges
            .iter()
            .map(|&(a, b)| {
                Ok((
                    center.nodes(a, b, s)?,
                    center.direction(a),
                    [
                        if s.start_arrow.is_some() && a == lo {
                            Cap::Butt
                        } else {
                            s.cap
                        },
                        if s.end_arrow.is_some() && b == hi {
                            Cap::Butt
                        } else {
                            s.cap
                        },
                    ],
                ))
            })
            .collect::<Result<_, Error>>()?;
        if center.closed
            && ranges.len() > 1
            && ranges[0].0 == 0.0
            && ranges[0].1 > 0.0
            && ranges.last().unwrap().1 == length
            && ranges.last().unwrap().0 < length
        {
            let first = runs.remove(0);
            let mut last = runs.pop().unwrap();
            last.0.extend_from_slice(&first.0[1..]);
            last.2[1] = first.2[1];
            runs.insert(0, last);
        }
        let closed =
            center.closed && ranges.len() == 1 && ranges[0] == (0.0, length) && length > 0.0;
        for (nodes, tangent, caps) in runs {
            builder.run(&nodes, closed, s, tangent, caps)?;
        }
        if let Some(a) = &s.start_arrow {
            builder.arrow(contour.start, mul(first, -1.0), a)?;
        }
        if let Some(a) = &s.end_arrow {
            let end = *center.points.last().unwrap();
            let direction = if length == 0.0 {
                first
            } else if contour.closed && contour.edges.last().is_some_and(|e| e.to != contour.start)
            {
                unit(sub(contour.start, contour.edges.last().unwrap().to))
            } else {
                mul(tangent(&contour.edges, end, true), -1.0)
            };
            builder.arrow(end, direction, a)?;
        }
    }
    Ok((!builder.commands.is_empty()).then_some(Geometry::Path {
        commands: builder.commands,
    }))
}
pub(crate) fn generated_work(document: &Document) -> Result<u64, Error> {
    let mut count = 0;
    for (i, item) in document.items.iter().enumerate() {
        count += generated_item_work(item, crate::scene::world_transform(document, i)?)?;
        if count > MAX_OUTLINE_COMMANDS as u64 {
            return Err(crate::model::limit(
                "Document exceeds generated stroke-outline command limit at delivery scale",
            ));
        }
    }
    Ok(count)
}
pub(crate) fn generated_item_work(item: &Item, world: Matrix) -> Result<u64, Error> {
    if let Content::Vector {
        geometry,
        stroke: Some(s),
        ..
    } = &item.content
        && let Some(Geometry::Path { commands }) = generate_placed(geometry, s, world)?
    {
        Ok(commands.len() as u64)
    } else {
        Ok(0)
    }
}
