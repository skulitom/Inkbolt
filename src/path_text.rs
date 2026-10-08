//! Original bounded distance tables for editable one-contour text baselines.
use crate::{Error, geometry, model::*};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

pub const MAX_COMMANDS: usize = 1024;
pub const MAX_LEAVES: usize = 32768;
pub const MAX_DOCUMENT_LEAVES: usize = 65536;
fn tolerance() -> f64 {
    0.001
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Baseline {
    pub geometry: Geometry,
    #[serde(default)]
    pub start_offset: f64,
    #[serde(default)]
    pub normal_offset: f64,
    #[serde(default)]
    pub flip: bool,
    #[serde(default = "tolerance")]
    pub tolerance: f64,
}
#[derive(Clone, Debug, Serialize)]
pub struct Report {
    pub geometry_interpretation: &'static str,
    pub length: f64,
    pub length_interval: [f64; 2],
    pub baseline_position_error_bound: f64,
    pub leaves: usize,
    pub closed: bool,
    pub flip: bool,
    pub start: f64,
    pub normal_offset: f64,
}
#[derive(Clone, Debug, Serialize)]
pub struct Placement {
    pub distance: f64,
    pub point: Point,
    pub tangent: Point,
    pub transform: Matrix,
    pub drawn: bool,
}
type Curve = [Point; 4];
#[derive(Clone)]
struct Leaf {
    curve: Curve,
    start: f64,
    length: f64,
}
pub struct Measured {
    leaves: Vec<Leaf>,
    pub report: Report,
}
fn sub(a: Point, b: Point) -> Point {
    [a[0] - b[0], a[1] - b[1]]
}
fn norm(a: Point) -> f64 {
    a[0].hypot(a[1])
}
fn mix(a: Point, b: Point, t: f64) -> Point {
    [a[0] * (1.0 - t) + b[0] * t, a[1] * (1.0 - t) + b[1] * t]
}
fn split(c: Curve) -> (Curve, Curve) {
    let a = mix(c[0], c[1], 0.5);
    let b = mix(c[1], c[2], 0.5);
    let d = mix(c[2], c[3], 0.5);
    let e = mix(a, b, 0.5);
    let f = mix(b, d, 0.5);
    let g = mix(e, f, 0.5);
    ([c[0], a, e, g], [g, f, d, c[3]])
}
fn evaluate(c: Curve, t: f64) -> Point {
    mix(
        mix(mix(c[0], c[1], t), mix(c[1], c[2], t), t),
        mix(mix(c[1], c[2], t), mix(c[2], c[3], t), t),
        t,
    )
}
fn tangent(c: Curve, t: f64) -> Result<Point, Error> {
    let a = sub(c[1], c[0]);
    let b = sub(c[2], c[1]);
    let d = sub(c[3], c[2]);
    let mut v = mix(mix(a, b, t), mix(b, d, t), t);
    if norm(v) == 0.0 {
        let candidates = if t == 0.0 {
            [a, sub(c[2], c[0]), sub(c[3], c[0])]
        } else if t == 1.0 {
            [d, sub(c[3], c[1]), sub(c[3], c[0])]
        } else {
            return Err(Error::new(
                "PATH_TEXT_TANGENT",
                "A glyph midpoint has no defined baseline tangent",
            ));
        };
        v = candidates
            .into_iter()
            .find(|p| norm(*p) > 0.0)
            .ok_or_else(|| invalid("Text baseline is collapsed"))?;
    }
    let n = norm(v);
    Ok([v[0] / n, v[1] / n])
}
fn commands(path: &Baseline) -> Result<Vec<PathCommand>, Error> {
    geometry::validate_geometry(&path.geometry)?;
    let Geometry::Path { commands } = crate::primitives::expand(&path.geometry)? else {
        unreachable!()
    };
    if commands.len() > MAX_COMMANDS {
        return Err(limit("Text baseline exceeds 1024 expanded commands"));
    }
    if commands
        .iter()
        .filter(|c| matches!(c, PathCommand::Move { .. }))
        .count()
        != 1
    {
        return Err(Error::new(
            "UNSUPPORTED",
            "Text baseline requires one contiguous contour",
        ));
    }
    Ok(commands)
}
pub fn validate(path: &Baseline) -> Result<usize, Error> {
    if !path.start_offset.is_finite()
        || path.start_offset.abs() > MAX_COORDINATE
        || !path.normal_offset.is_finite()
        || path.normal_offset.abs() > MAX_COORDINATE
    {
        return Err(invalid(
            "Text baseline offsets must be finite and within coordinate limits",
        ));
    }
    if !path.tolerance.is_finite() || !(0.000001..=0.25).contains(&path.tolerance) {
        return Err(invalid(
            "Text baseline tolerance must be in 0.000001..=0.25",
        ));
    }
    Ok(commands(path)?.len())
}
struct Build {
    leaves: Vec<Leaf>,
    lower: f64,
    upper: f64,
    deviation: f64,
}
impl Build {
    fn visit(&mut self, c: Curve, error: f64, position: f64, depth: usize) -> Result<(), Error> {
        let chord = norm(sub(c[3], c[0]));
        let polygon = norm(sub(c[1], c[0])) + norm(sub(c[2], c[1])) + norm(sub(c[3], c[2]));
        if polygon == 0.0 {
            return Ok(());
        }
        let deviation = norm(sub(c[1], mix(c[0], c[3], 1.0 / 3.0)))
            .max(norm(sub(c[2], mix(c[0], c[3], 2.0 / 3.0))));
        if polygon - chord > error || deviation > position || chord == 0.0 {
            if depth >= 24 || self.leaves.len() >= MAX_LEAVES {
                return Err(limit("Text baseline subdivision exceeds bounded work"));
            }
            let (left, right) = split(c);
            self.visit(left, error / 2.0, position, depth + 1)?;
            self.visit(right, error / 2.0, position, depth + 1)?;
        } else {
            if self.leaves.len() >= MAX_LEAVES {
                return Err(limit("Text baseline exceeds 32768 distance-table entries"));
            }
            self.leaves.push(Leaf {
                curve: c,
                start: self.lower,
                length: chord,
            });
            self.lower += chord;
            self.upper += polygon;
            self.deviation = self.deviation.max(deviation);
        }
        Ok(())
    }
}
impl Measured {
    pub fn new(path: &Baseline) -> Result<Self, Error> {
        validate(path)?;
        let mut curves = Vec::new();
        let mut at = [0.0; 2];
        let mut start = at;
        let mut closed = false;
        for command in commands(path)? {
            let to = match command {
                PathCommand::Move { to } => {
                    at = to;
                    start = to;
                    continue;
                }
                PathCommand::Line { to } => to,
                PathCommand::Cubic {
                    control1,
                    control2,
                    to,
                } => {
                    curves.push([at, control1, control2, to]);
                    at = to;
                    continue;
                }
                PathCommand::Close {} => {
                    closed = true;
                    start
                }
            };
            curves.push([at, mix(at, to, 1.0 / 3.0), mix(at, to, 2.0 / 3.0), to]);
            at = to;
        }
        let mut build = Build {
            leaves: Vec::new(),
            lower: 0.0,
            upper: 0.0,
            deviation: 0.0,
        };
        let error = path.tolerance / 8.0 / curves.len().max(1) as f64;
        for curve in curves {
            build.visit(curve, error, path.tolerance / 8.0, 0)?;
        }
        if build.lower < 0.001 {
            return Err(invalid("Text baseline must have at least 0.001 length"));
        }
        // Include a conservative f64 accumulation/subdivision allowance. The
        // geometric interval is chord length through control-polygon length.
        let rounding = 256.0 * f64::EPSILON * MAX_COORDINATE * build.leaves.len() as f64;
        let report = Report {
            geometry_interpretation: if matches!(path.geometry, Geometry::Ellipse { .. }) {
                "four_cubic_ellipse; distance_table_error_excludes_analytic_ellipse_conversion"
            } else {
                "expanded_line_cubic_geometry"
            },
            length: build.lower,
            length_interval: [(build.lower - rounding).max(0.0), build.upper + rounding],
            baseline_position_error_bound: 3.0 * (build.upper - build.lower)
                + build.deviation
                + 4.0 * rounding,
            leaves: build.leaves.len(),
            closed,
            flip: path.flip,
            start: 0.0,
            normal_offset: path.normal_offset,
        };
        Ok(Self {
            leaves: build.leaves,
            report,
        })
    }
    pub fn sample(&self, distance: f64) -> Result<(Point, Point), Error> {
        let total = self.report.length;
        let d = if self.report.flip {
            total - distance
        } else {
            distance
        };
        let clamped = d.clamp(0.0, total);
        let index = if self.report.flip {
            self.leaves
                .partition_point(|l| l.start + l.length < clamped)
        } else {
            self.leaves
                .partition_point(|l| l.start + l.length <= clamped)
        }
        .min(self.leaves.len() - 1);
        let leaf = &self.leaves[index];
        let t = if clamped == 0.0 {
            0.0
        } else if clamped == total {
            1.0
        } else {
            ((clamped - leaf.start) / leaf.length).clamp(0.0, 1.0)
        };
        let mut p = evaluate(leaf.curve, t);
        let mut tangent = tangent(leaf.curve, t)?;
        for c in 0..2 {
            p[c] += tangent[c] * (d - clamped);
            if self.report.flip {
                tangent[c] = -tangent[c];
            }
        }
        Ok((p, tangent))
    }
    pub fn placement(&self, center: f64, distance: f64, drawn: bool) -> Result<Placement, Error> {
        let (point, tangent) = self.sample(distance)?;
        let [x, y] = tangent;
        let offset = self.report.normal_offset;
        let transform = [
            x,
            y,
            -y,
            x,
            point[0] - y * offset - x * center,
            point[1] + x * offset - y * center,
        ];
        Ok(Placement {
            distance,
            point,
            tangent,
            transform,
            drawn,
        })
    }
}
pub fn map_geometry(geometry: &mut Geometry, matrix: Matrix) {
    let Geometry::Path { commands } = geometry else {
        unreachable!()
    };
    for command in commands {
        match command {
            PathCommand::Move { to } | PathCommand::Line { to } => *to = geometry::map(matrix, *to),
            PathCommand::Cubic {
                control1,
                control2,
                to,
            } => {
                *control1 = geometry::map(matrix, *control1);
                *control2 = geometry::map(matrix, *control2);
                *to = geometry::map(matrix, *to);
            }
            PathCommand::Close {} => {}
        }
    }
}
