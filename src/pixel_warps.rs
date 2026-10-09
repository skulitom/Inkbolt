//! Retained image-plane deformation with unique inverse sampling.
use crate::{Error, geometry as geo, model::*};
use num_rational::BigRational as R;
use num_traits::{Signed, ToPrimitive, Zero};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
pub const MAX_AXIS: usize = 16;
pub const MAX_JOINTS: usize = 16;
pub const MAX_SAMPLES: usize = 256;
pub const MAX_WORK: u64 = 67_108_864;
const MIN_ALTITUDE: f64 = 1. / 1024.;
const MIN_RELATIVE_AREA: f64 = 1. / 1_048_576.;
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Joint {
    pub parent: Option<usize>,
    pub pivot: Point,
    pub angle: f64,
    #[serde(default)]
    pub translation: Point,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Spec {
    Perspective {
        corners: [Point; 4],
    },
    Mesh {
        columns: usize,
        rows: usize,
        points: Vec<Point>,
    },
    Articulated {
        columns: usize,
        rows: usize,
        joints: Vec<Joint>,
        weights: Vec<Vec<f64>>,
    },
}
fn invalid(m: &str) -> Error {
    Error::new("INVALID_PIXEL_WARP", m)
}
fn limit(m: &str) -> Error {
    Error::new("RESOURCE_LIMIT", m)
}
fn finite(p: Point) -> Result<(), Error> {
    if p.iter().any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE) {
        return Err(invalid(
            "Pixel warp coordinates must be finite within +/-32768",
        ));
    }
    Ok(())
}
fn rational(v: f64) -> R {
    R::from_float(v).expect("validated finite pixel warp point")
}
fn cross(a: Point, b: Point, c: Point) -> f64 {
    (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
}
fn orientation(a: Point, b: Point, c: Point) -> i8 {
    let x = (b[0] - a[0]) * (c[1] - a[1]);
    let y = (b[1] - a[1]) * (c[0] - a[0]);
    let v = x - y;
    if v.abs() > 16. * f64::EPSILON * (x.abs() + y.abs()) {
        return if v > 0. { 1 } else { -1 };
    }
    let v = (rational(b[0]) - rational(a[0])) * (rational(c[1]) - rational(a[1]))
        - (rational(b[1]) - rational(a[1])) * (rational(c[0]) - rational(a[0]));
    if v.is_zero() {
        0
    } else if v.is_positive() {
        1
    } else {
        -1
    }
}
fn on_segment(a: Point, b: Point, p: Point) -> bool {
    (0..2).all(|k| p[k] >= a[k].min(b[k]) && p[k] <= a[k].max(b[k]))
}
fn intersects(a: Point, b: Point, c: Point, d: Point) -> bool {
    let x = orientation(a, b, c);
    let y = orientation(a, b, d);
    let z = orientation(c, d, a);
    let w = orientation(c, d, b);
    (x * y < 0 && z * w < 0)
        || (x == 0 && on_segment(a, b, c))
        || (y == 0 && on_segment(a, b, d))
        || (z == 0 && on_segment(c, d, a))
        || (w == 0 && on_segment(c, d, b))
}
fn inverse_matrix(m: &[R; 9]) -> Result<[f64; 9], Error> {
    let cof: [R; 9] = std::array::from_fn(|k| {
        let row = k % 3;
        let col = k / 3;
        let rs: Vec<_> = (0..3).filter(|v| *v != row).collect();
        let cs: Vec<_> = (0..3).filter(|v| *v != col).collect();
        let v = &m[rs[0] * 3 + cs[0]] * &m[rs[1] * 3 + cs[1]]
            - &m[rs[0] * 3 + cs[1]] * &m[rs[1] * 3 + cs[0]];
        if (row + col) % 2 == 0 { v } else { -v }
    });
    let det = &m[0] * &cof[0] + &m[1] * &cof[3] + &m[2] * &cof[6];
    if det.is_zero() {
        return Err(invalid("Projective inverse is singular"));
    }
    let out = std::array::from_fn(|k| (&cof[k] / &det).to_f64().unwrap_or(f64::NAN));
    if out.iter().any(|v| !v.is_finite()) {
        return Err(invalid("Projective inverse exceeds finite precision"));
    }
    Ok(out)
}
fn project(m: &[f64; 9], p: Point) -> Point {
    let w = m[6] * p[0] + m[7] * p[1] + m[8];
    [
        (m[0] * p[0] + m[1] * p[1] + m[2]) / w,
        (m[3] * p[0] + m[4] * p[1] + m[5]) / w,
    ]
}
fn weights(p: Point, t: [Point; 3]) -> [f64; 3] {
    let det = cross(t[0], t[1], t[2]);
    let b = cross(t[0], p, t[2]) / det;
    let c = cross(t[0], t[1], p) / det;
    [1. - b - c, b, c]
}
fn interpolate(t: [Point; 3], w: [f64; 3]) -> Point {
    std::array::from_fn(|k| t[0][k] + w[1] * (t[1][k] - t[0][k]) + w[2] * (t[2][k] - t[0][k]))
}
fn contains(t: [Point; 3], p: Point) -> bool {
    if (0..2).any(|k| {
        p[k] < t.iter().map(|q| q[k]).fold(f64::INFINITY, f64::min)
            || p[k] > t.iter().map(|q| q[k]).fold(f64::NEG_INFINITY, f64::max)
    }) {
        return false;
    }
    let o = orientation(t[0], t[1], t[2]);
    (0..3).all(|k| orientation(t[k], t[(k + 1) % 3], p) * o >= 0)
}
fn grid(columns: usize, rows: usize, frame: Point) -> Result<Vec<Point>, Error> {
    if !(1..=MAX_AXIS).contains(&columns) || !(1..=MAX_AXIS).contains(&rows) {
        return Err(limit("Pixel warp grid requires 1..16 intervals per axis"));
    }
    Ok((0..=rows)
        .flat_map(|r| {
            (0..=columns).map(move |c| {
                [
                    frame[0] * (c as f64 / columns as f64),
                    frame[1] * (r as f64 / rows as f64),
                ]
            })
        })
        .collect())
}
fn pose(joints: &[Joint]) -> Result<Vec<Matrix>, Error> {
    if joints.is_empty() || joints.len() > MAX_JOINTS {
        return Err(limit("Articulated warps require 1..16 ordered joints"));
    }
    let mut out = vec![];
    for (i, j) in joints.iter().enumerate() {
        finite(j.pivot)?;
        finite(j.translation)?;
        if !j.angle.is_finite() || j.angle.abs() > 360. || j.parent.is_some_and(|p| p >= i) {
            return Err(invalid(
                "Joint angles require +/-360 degrees and parents must precede children",
            ));
        }
        let (s, c) = if j.angle % 90. == 0. {
            match (j.angle as i32 / 90).rem_euclid(4) {
                0 => (0., 1.),
                1 => (1., 0.),
                2 => (0., -1.),
                _ => (-1., 0.),
            }
        } else {
            j.angle.to_radians().sin_cos()
        };
        let [x, y] = j.pivot;
        let m = [
            c,
            s,
            -s,
            c,
            x - c * x + s * y + j.translation[0],
            y - s * x - c * y + j.translation[1],
        ];
        let m = if let Some(p) = j.parent {
            geo::multiply(out[p], m)
        } else {
            m
        };
        geo::validate_matrix(m)?;
        out.push(m);
    }
    Ok(out)
}
pub(crate) struct Plan {
    pub source: Vec<Point>,
    pub destination: Vec<Point>,
    pub triangles: Vec<[usize; 3]>,
    pub boundary: Vec<usize>,
    pub joint_matrices: Vec<Matrix>,
    projective: Option<([f64; 9], [f64; 9])>,
    frame: Point,
}
impl Plan {
    pub fn new(spec: &Spec, frame: Point) -> Result<Self, Error> {
        finite(frame)?;
        if frame.iter().any(|v| *v < 0.001) {
            return Err(invalid("Pixel warp source dimensions require .001..32768"));
        }
        let mut projective = None;
        let mut joint_matrices = vec![];
        let (columns, rows, source, destination) = match spec {
            Spec::Perspective { corners } => {
                let m = crate::warps::projective_coefficients(corners)?;
                let inv = inverse_matrix(&m)?;
                let f = std::array::from_fn(|k| m[k].to_f64().unwrap_or(f64::NAN));
                if f.iter().any(|v| !v.is_finite()) {
                    return Err(invalid("Projective map exceeds finite precision"));
                }
                projective = Some((f, inv));
                (
                    1,
                    1,
                    grid(1, 1, frame)?,
                    vec![corners[0], corners[1], corners[3], corners[2]],
                )
            }
            Spec::Mesh {
                columns,
                rows,
                points,
            } => {
                let src = grid(*columns, *rows, frame)?;
                if src.len() != points.len() {
                    return Err(invalid(
                        "Mesh requires (columns+1)*(rows+1) row-major points",
                    ));
                }
                (*columns, *rows, src, points.clone())
            }
            Spec::Articulated {
                columns,
                rows,
                joints,
                weights,
            } => {
                let src = grid(*columns, *rows, frame)?;
                joint_matrices = pose(joints)?;
                if weights.len() != src.len() {
                    return Err(invalid(
                        "Articulated weights require one row per grid vertex",
                    ));
                }
                let mut points = Vec::with_capacity(src.len());
                for (p, w) in src.iter().zip(weights) {
                    if w.len() != joints.len()
                        || w.iter().any(|v| !v.is_finite() || !(0.0..=1.).contains(v))
                    {
                        return Err(invalid(
                            "Each weight row requires one 0..1 weight per joint",
                        ));
                    }
                    let sum: f64 = w.iter().sum();
                    if (sum - 1.).abs() > 1e-10 {
                        return Err(invalid("Joint weights must sum to one within 1e-10"));
                    }
                    let mut q = [0.; 2];
                    for (m, w) in joint_matrices.iter().zip(w) {
                        let t = geo::map(*m, *p);
                        for k in 0..2 {
                            q[k] += t[k] * (*w / sum);
                        }
                    }
                    points.push(q);
                }
                (*columns, *rows, src, points)
            }
        };
        for p in &destination {
            finite(*p)?;
        }
        let mut triangles = vec![];
        for r in 0..rows {
            for c in 0..columns {
                let a = r * (columns + 1) + c;
                let b = a + 1;
                let d = a + columns + 1;
                let e = d + 1;
                triangles.extend([[a, b, e], [a, e, d]]);
            }
        }
        let mut sign = 0;
        for ids in &triangles {
            let t = ids.map(|i| destination[i]);
            let o = orientation(t[0], t[1], t[2]);
            if o == 0 || sign != 0 && o != sign {
                return Err(Error::new(
                    "NONINVERTIBLE_WARP",
                    "Mesh triangles must be nondegenerate with consistent orientation",
                ));
            }
            sign = o;
            let edge = (0..3)
                .map(|k| (t[k][0] - t[(k + 1) % 3][0]).hypot(t[k][1] - t[(k + 1) % 3][1]))
                .fold(0f64, f64::max);
            let area = cross(t[0], t[1], t[2]).abs();
            if area / edge < MIN_ALTITUDE || area / (edge * edge) < MIN_RELATIVE_AREA {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "Pixel warp triangles exceed the supported inverse conditioning",
                ));
            }
        }
        let mut boundary: Vec<_> = (0..=columns).collect();
        boundary.extend((1..=rows).map(|r| r * (columns + 1) + columns));
        boundary.extend((0..columns).rev().map(|c| rows * (columns + 1) + c));
        boundary.extend((1..rows).rev().map(|r| r * (columns + 1)));
        for k in 0..boundary.len() {
            let a = destination[boundary[(k + boundary.len() - 1) % boundary.len()]];
            let b = destination[boundary[k]];
            let c = destination[boundary[(k + 1) % boundary.len()]];
            if orientation(a, b, c) == 0 && (on_segment(a, b, c) || on_segment(b, c, a)) {
                return Err(Error::new(
                    "NONINVERTIBLE_WARP",
                    "Adjacent mesh boundary edges must not overlap",
                ));
            }
        }
        for a in 0..boundary.len() {
            for b in a + 1..boundary.len() {
                if b == a + 1 || (a == 0 && b + 1 == boundary.len()) {
                    continue;
                }
                let next = |v| destination[boundary[(v + 1) % boundary.len()]];
                if intersects(
                    destination[boundary[a]],
                    next(a),
                    destination[boundary[b]],
                    next(b),
                ) {
                    return Err(Error::new(
                        "NONINVERTIBLE_WARP",
                        "Mesh boundary must be simple without contacts or overlaps",
                    ));
                }
            }
        }
        Ok(Self {
            source,
            destination,
            triangles,
            boundary,
            joint_matrices,
            projective,
            frame,
        })
    }
    pub fn geometry(&self) -> Geometry {
        Geometry::Path {
            commands: self
                .boundary
                .iter()
                .enumerate()
                .map(|(n, i)| {
                    if n == 0 {
                        PathCommand::Move {
                            to: self.destination[*i],
                        }
                    } else {
                        PathCommand::Line {
                            to: self.destination[*i],
                        }
                    }
                })
                .chain([PathCommand::Close {}])
                .collect(),
        }
    }
    pub fn forward(&self, p: Point) -> Option<Point> {
        if p[0] < 0. || p[1] < 0. || p[0] > self.frame[0] || p[1] > self.frame[1] {
            return None;
        }
        if let Some((m, _)) = &self.projective {
            if let Some(i) = self.source.iter().position(|q| *q == p) {
                return Some(self.destination[i]);
            }
            return Some(project(m, [p[0] / self.frame[0], p[1] / self.frame[1]]));
        }
        self.triangles.iter().find_map(|ids| {
            let t = ids.map(|i| self.source[i]);
            contains(t, p).then(|| {
                if let Some(i) = ids.iter().find(|i| self.source[**i] == p) {
                    self.destination[*i]
                } else {
                    interpolate(ids.map(|i| self.destination[i]), weights(p, t))
                }
            })
        })
    }
    pub fn inverse(&self, p: Point) -> Option<Point> {
        let ids = self
            .triangles
            .iter()
            .find(|ids| contains(ids.map(|i| self.destination[i]), p))?;
        if let Some(i) = ids.iter().find(|i| self.destination[**i] == p) {
            return Some(self.source[*i]);
        }
        let q = if let Some((_, m)) = &self.projective {
            let v = project(m, p);
            [v[0] * self.frame[0], v[1] * self.frame[1]]
        } else {
            interpolate(
                ids.map(|i| self.source[i]),
                weights(p, ids.map(|i| self.destination[i])),
            )
        };
        Some([q[0].clamp(0., self.frame[0]), q[1].clamp(0., self.frame[1])])
    }
    pub fn inverse_edge_clamped(&self, p: Point) -> Point {
        if let Some(q) = self.inverse(p) {
            return q;
        }
        let mut best = (f64::INFINITY, [0., 0.]);
        for k in 0..self.boundary.len() {
            let a = self.boundary[k];
            let b = self.boundary[(k + 1) % self.boundary.len()];
            let x = self.destination[a];
            let y = self.destination[b];
            let d = [y[0] - x[0], y[1] - x[1]];
            let t = (((p[0] - x[0]) * d[0] + (p[1] - x[1]) * d[1]) / (d[0] * d[0] + d[1] * d[1]))
                .clamp(0., 1.);
            let q = [x[0] + t * d[0], x[1] + t * d[1]];
            let distance = (q[0] - p[0]).hypot(q[1] - p[1]);
            if distance < best.0 {
                let source = if let Some((_, m)) = &self.projective {
                    let p = project(m, q);
                    [
                        (p[0] * self.frame[0]).clamp(0., self.frame[0]),
                        (p[1] * self.frame[1]).clamp(0., self.frame[1]),
                    ]
                } else {
                    std::array::from_fn(|j| {
                        self.source[a][j] + t * (self.source[b][j] - self.source[a][j])
                    })
                };
                best = (distance, source);
            }
        }
        best.1
    }
}
pub(crate) fn frame(item: &Item) -> Result<Point, Error> {
    match item.content {
        Content::Object { ref object } => Ok([object.width, object.height]),
        Content::Samples { ref grid } => Ok([grid.width as f64, grid.height as f64]),
        Content::StoredSamples { ref grid } => {
            Ok([grid.base.spec.width as f64, grid.base.spec.height as f64])
        }
        Content::Raw { ref raw } => Ok([
            raw.recipe.capture.width as f64,
            raw.recipe.capture.height as f64,
        ]),
        Content::Raster { width, height, .. } => Ok([width as f64, height as f64]),
        Content::Image { width, height, .. } => Ok([width, height]),
        _ => Err(Error::new(
            "UNSUPPORTED",
            "Pixel deformation requires an image or inline pixel layer",
        )),
    }
}
pub(crate) fn plan(item: &Item) -> Result<Option<Plan>, Error> {
    item.pixel_warp
        .as_ref()
        .map(|s| Plan::new(s, frame(item)?))
        .transpose()
}
pub(crate) fn validate(item: &Item, world: Matrix) -> Result<usize, Error> {
    let Some(p) = plan(item)? else { return Ok(0) };
    if matches!(item.content,Content::Raster{sampling,..}|Content::Image{sampling,..} if sampling.advanced())
        || matches!(&item.content, Content::Samples{grid} if grid.sampling.advanced())
        || matches!(&item.content, Content::StoredSamples{grid} if grid.sampling.advanced())
        || matches!(&item.content, Content::Raw{raw} if raw.sampling.advanced())
        || matches!(&item.content, Content::Object{object} if object.sampling.advanced())
    {
        return Err(Error::new(
            "UNSUPPORTED",
            "Pixel deformation currently requires explicit nearest or bilinear sampling",
        ));
    }
    validate_world_geometry(&p.geometry(), world)?;
    Ok(p.destination.len()
        + match item.pixel_warp.as_deref() {
            Some(Spec::Articulated {
                joints, weights, ..
            }) => joints.len() + weights.iter().map(Vec::len).sum::<usize>(),
            _ => 0,
        })
}
pub(crate) fn reject_native(item: &Item) -> Result<(), Error> {
    if item.pixel_warp.is_some() {
        return Err(Error::new(
            "UNSUPPORTED",
            "Clear retained pixel deformation before native-grid editing or mask baking; preserve and reapply its controls after editing the source",
        ));
    }
    Ok(())
}
pub(crate) fn work(document: &Document, scale: u32) -> Result<u64, Error> {
    let mut units = 0u64;
    for i in &document.items {
        if let Some(s) = &i.pixel_warp {
            let (c, r) = match s.as_ref() {
                Spec::Perspective { .. } => (1, 1),
                Spec::Mesh { columns, rows, .. } | Spec::Articulated { columns, rows, .. } => {
                    (*columns, *rows)
                }
            };
            units += (2 * c * r + 2 * c + 2 * r + 4) as u64;
        }
    }
    let work = units * document.width as u64 * document.height as u64 * scale as u64 * scale as u64;
    if work > MAX_WORK {
        return Err(limit(
            "Pixel deformation exceeds inverse sampling work limit",
        ));
    }
    Ok(work)
}
/// Conservative simultaneously live plan, outer path and construction scratch,
/// measured in eight-byte values. Plans are built and consumed one item at a time.
pub(crate) fn buffer_values(spec: &Spec) -> u64 {
    let (columns, rows, joints) = match spec {
        Spec::Perspective { .. } => (1, 1, 0),
        Spec::Mesh { columns, rows, .. } => (*columns, *rows, 0),
        Spec::Articulated {
            columns,
            rows,
            joints,
            ..
        } => (*columns, *rows, joints.len()),
    };
    // Source/destination vertices, outer path commands, triangle indices and
    // vector capacity growth; fixed projective coefficients and joint matrices.
    (32 * (columns + 1) * (rows + 1) + 16 * columns * rows + 16 * joints + 128) as u64
}
pub fn inspect(
    spec: &Spec,
    frame: Point,
    samples: &[Point],
    inverse_samples: &[Point],
    include_mesh: bool,
    control: &crate::control::Control,
) -> Result<serde_json::Value, Error> {
    control.check()?;
    if samples.len() + inverse_samples.len() > MAX_SAMPLES {
        return Err(limit("Pixel warp inspection exceeds256samples"));
    }
    for p in samples.iter().chain(inverse_samples) {
        finite(*p)?;
    }
    let p = Plan::new(spec, frame)?;
    let forward:Vec<_>=samples.iter().map(|q|{let mapped=p.forward(*q);serde_json::json!({"source":q,"mapped":mapped,"inverse":mapped.and_then(|q|p.inverse(q))})}).collect();
    let inverse:Vec<_>=inverse_samples.iter().map(|q|{let source=p.inverse(*q);serde_json::json!({"destination":q,"source":source,"forward":source.and_then(|q|p.forward(q))})}).collect();
    control.check()?;
    Ok(
        serde_json::json!({"warp":spec,"frame":frame,"samples":forward,"inverse_samples":inverse,"source_points":include_mesh.then_some(&p.source),"destination_points":include_mesh.then_some(&p.destination),"triangles":include_mesh.then_some(&p.triangles),"boundary":include_mesh.then_some(&p.boundary),"joint_matrices":p.joint_matrices,"bounds":geo::bounds(&p.geometry(),identity()),"coordinates":"image_local_before_item_and_ancestors","mesh_interpolation":"piecewise_affine_fixed_top_left_bottom_right_diagonal","inverse":"unique_inside_simple_consistently_oriented_mesh","outside":"transparent_with_nearest_boundary_color_for_antialias_coverage","source_retained":true}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn direct_library_rejects_nonfinite_dimensions_points_and_joint_controls() {
        let corners = [[0., 0.], [8., 0.], [8., 8.], [0., 8.]];
        for v in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            assert!(Plan::new(&Spec::Perspective { corners }, [v, 8.]).is_err());
            let mut c = corners;
            c[1][0] = v;
            assert!(Plan::new(&Spec::Perspective { corners: c }, [8., 8.]).is_err());
            assert!(
                Plan::new(
                    &Spec::Mesh {
                        columns: 1,
                        rows: 1,
                        points: vec![[v, 0.]; 4]
                    },
                    [8., 8.]
                )
                .is_err()
            );
            let j = Joint {
                parent: None,
                pivot: [0., 0.],
                angle: v,
                translation: [0., 0.],
            };
            assert!(pose(&[j]).is_err());
            let j = Joint {
                parent: None,
                pivot: [v, 0.],
                angle: 0.,
                translation: [0., 0.],
            };
            assert!(pose(&[j]).is_err());
            let j = Joint {
                parent: None,
                pivot: [0., 0.],
                angle: 0.,
                translation: [v, 0.],
            };
            assert!(pose(&[j]).is_err());
            let j = Joint {
                parent: None,
                pivot: [0., 0.],
                angle: 0.,
                translation: [0., 0.],
            };
            assert!(
                Plan::new(
                    &Spec::Articulated {
                        columns: 1,
                        rows: 1,
                        joints: vec![j],
                        weights: vec![vec![v]; 4]
                    },
                    [8., 8.]
                )
                .is_err()
            );
        }
    }
}
