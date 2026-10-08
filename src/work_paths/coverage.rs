//! f64 scanline coverage of filled paths, independent of display edge quantization.
use crate::{Error, geometry, model::*, paths, selections};

enum Edge {
    Line([Point; 2]),
    Cubic {
        points: [Point; 4],
        interval: [f64; 2],
        ends: [Point; 2],
    },
}
fn cubic(mut p: [Point; 4], t: f64) -> Point {
    for n in (1..4).rev() {
        for i in 0..n {
            p[i] = std::array::from_fn(|axis| p[i][axis] * (1.0 - t) + p[i + 1][axis] * t);
        }
    }
    p[0]
}
fn turns(p: [Point; 4]) -> Vec<f64> {
    let d = [p[1][1] - p[0][1], p[2][1] - p[1][1], p[3][1] - p[2][1]];
    let (a, b, c) = (d[0] - 2.0 * d[1] + d[2], 2.0 * (d[1] - d[0]), d[0]);
    let mut roots = vec![0.0, 1.0];
    let mut add = |t: f64| {
        if t > 0.0 && t < 1.0 {
            roots.push(t);
        }
    };
    if a == 0.0 {
        if b != 0.0 {
            add(-c / b);
        }
    } else {
        let discriminant = b * b - 4.0 * a * c;
        if discriminant >= 0.0 {
            let q = -0.5 * (b + discriminant.sqrt().copysign(b));
            if q == 0.0 {
                add(-b / (2.0 * a));
            } else {
                add(q / a);
                add(c / q);
            }
        }
    }
    roots.sort_by(f64::total_cmp);
    roots.dedup();
    roots
}
impl Edge {
    fn ends(&self) -> [Point; 2] {
        match self {
            Self::Line(p) => *p,
            Self::Cubic { ends, .. } => *ends,
        }
    }
    fn crossing(&self, y: f64) -> Option<(f64, i32)> {
        let [a, b] = self.ends();
        // Half-open y intervals count common vertices once. Horizontal edges
        // contribute no winding; extrema contribute opposite signed crossings.
        if !((a[1] <= y && y < b[1]) || (b[1] <= y && y < a[1])) {
            return None;
        }
        let up = b[1] > a[1];
        let x = match self {
            Self::Line(_) => a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]),
            Self::Cubic {
                points, interval, ..
            } => {
                let [mut lo, mut hi] = *interval;
                // Monotone intervals isolate each root. The bound is on work,
                // not a claim of exact algebraic geometry or exact pixel area.
                for _ in 0..56 {
                    let mid = lo + (hi - lo) * 0.5;
                    if mid == lo || mid == hi {
                        break;
                    }
                    if (cubic(*points, mid)[1] < y) == up {
                        lo = mid;
                    } else {
                        hi = mid;
                    }
                }
                cubic(*points, lo + (hi - lo) * 0.5)[0]
            }
        };
        Some((x, if up { 1 } else { -1 }))
    }
}

enum Region {
    Leaf(usize, FillRule),
    Combine(crate::booleans::Mode, Vec<Region>),
}
impl Region {
    fn contains(&self, windings: &[i32]) -> bool {
        match self {
            Self::Leaf(i, FillRule::Nonzero) => windings[*i] != 0,
            Self::Leaf(i, FillRule::EvenOdd) => windings[*i] % 2 != 0,
            Self::Combine(mode, children) => match mode {
                crate::booleans::Mode::Union => children.iter().any(|v| v.contains(windings)),
                crate::booleans::Mode::Intersection => {
                    children.iter().all(|v| v.contains(windings))
                }
                crate::booleans::Mode::Difference => {
                    children[0].contains(windings)
                        && !children[1..].iter().any(|v| v.contains(windings))
                }
                crate::booleans::Mode::Xor => {
                    children.iter().filter(|v| v.contains(windings)).count() % 2 != 0
                }
            },
        }
    }
}
fn leaf_edges(g: &Geometry, world: Matrix) -> Result<Vec<Edge>, Error> {
    let Geometry::Path { commands } = crate::primitives::expand(g)? else {
        unreachable!()
    };
    let mut edges = Vec::new();
    for contour in paths::parse(&commands) {
        let mut current = geometry::map(world, contour.start);
        let start = current;
        for edge in contour.edges {
            match edge.controls {
                None => {
                    let end = geometry::map(world, edge.to);
                    edges.push(Edge::Line([current, end]));
                    current = end;
                }
                Some([c1, c2]) => {
                    let p = [
                        current,
                        geometry::map(world, c1),
                        geometry::map(world, c2),
                        geometry::map(world, edge.to),
                    ];
                    for interval in turns(p).windows(2) {
                        edges.push(Edge::Cubic {
                            points: p,
                            interval: [interval[0], interval[1]],
                            ends: [cubic(p, interval[0]), cubic(p, interval[1])],
                        });
                    }
                    current = p[3];
                }
            }
        }
        // Filled paths close every contour, including intentionally open ones.
        edges.push(Edge::Line([current, start]));
    }
    Ok(edges)
}
fn compile(
    g: &Geometry,
    rule: FillRule,
    world: Matrix,
    edges: &mut Vec<(Edge, usize)>,
    leaves: &mut usize,
) -> Result<Region, Error> {
    if let Geometry::Compound { mode, operands } = g {
        let children = operands
            .iter()
            .map(|v| {
                compile(
                    &v.geometry,
                    v.fill_rule,
                    geometry::multiply(world, v.transform),
                    edges,
                    leaves,
                )
            })
            .collect::<Result<Vec<_>, _>>()?;
        Ok(Region::Combine(*mode, children))
    } else {
        let index = *leaves;
        *leaves += 1;
        edges.extend(leaf_edges(g, world)?.into_iter().map(|v| (v, index)));
        Ok(Region::Leaf(index, rule))
    }
}
pub(crate) fn evaluate(
    geometry: &Geometry,
    rule: FillRule,
    world: Matrix,
    width: u32,
    height: u32,
    antialias: bool,
) -> Result<Vec<u8>, Error> {
    let count = selections::check_size(width, height)?;
    let mut edges = Vec::new();
    let mut leaves = 0;
    let region = compile(geometry, rule, world, &mut edges, &mut leaves)?;
    let min_y = edges
        .iter()
        .flat_map(|(e, _)| e.ends())
        .map(|p| p[1])
        .fold(f64::INFINITY, f64::min);
    let max_y = edges
        .iter()
        .flat_map(|(e, _)| e.ends())
        .map(|p| p[1])
        .fold(f64::NEG_INFINITY, f64::max);
    let top = min_y.floor().clamp(0.0, height as f64) as u32;
    let bottom = max_y.ceil().clamp(0.0, height as f64) as u32;
    let subrows = if antialias {
        selections::COVERAGE_SUBROWS
    } else {
        1
    };
    let weighted: u64 = edges
        .iter()
        .map(|(e, _)| if matches!(e, Edge::Line(_)) { 1 } else { 57 })
        .sum();
    let sorting = edges.len() as u64 * (edges.len().max(1).ilog2() as u64 + 2);
    let predicates = if leaves > 1 {
        edges.len() as u64 * (leaves * 2) as u64
    } else {
        0
    };
    if (bottom - top) as u64 * subrows as u64 * (width as u64 + weighted + sorting + predicates)
        > selections::MAX_WORK
    {
        return Err(limit(
            "Path selection subrow integration exceeds work budget",
        ));
    }
    let mut values = vec![0.0_f64; count];
    let mut crossings = Vec::with_capacity(edges.len());
    for py in top..bottom {
        let row = &mut values[(py * width) as usize..((py + 1) * width) as usize];
        for sub in 0..subrows {
            let y = py as f64 + (sub as f64 + 0.5) / subrows as f64;
            crossings.clear();
            crossings.extend(
                edges
                    .iter()
                    .filter_map(|(e, i)| e.crossing(y).map(|(x, delta)| (x, delta, *i))),
            );
            crossings.sort_by(|a, b| a.0.total_cmp(&b.0));
            let mut windings = vec![0i32; leaves];
            let mut previous = 0.0_f64;
            for &(x, delta, leaf) in &crossings {
                if region.contains(&windings) {
                    let a = previous.clamp(0.0, width as f64);
                    let b = x.clamp(0.0, width as f64);
                    for (px, value) in row
                        .iter_mut()
                        .enumerate()
                        .take(b.ceil() as usize)
                        .skip(a.floor() as usize)
                    {
                        let amount = if antialias {
                            ((px as f64 + 1.0).min(b) - (px as f64).max(a)).max(0.0)
                        } else {
                            f64::from(px as f64 + 0.5 >= a && px as f64 + 0.5 < b)
                        };
                        *value += amount / subrows as f64;
                    }
                }
                windings[leaf] += delta;
                previous = x;
            }
        }
    }
    Ok(values
        .into_iter()
        .map(|v| (v.clamp(0.0, 1.0) * 255.0).round() as u8)
        .collect())
}
