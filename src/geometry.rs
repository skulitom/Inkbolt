use crate::{Error, model::*};

mod affine;
pub(crate) use affine::{
    MAX_FAST_POINT_ERROR as MAX_FAST_INVERSE_POINT_ERROR, MAX_RELATIVE_FACTORS,
    MAX_TRANSFORM_FACTORS, MIN_DETERMINANT, TransformFactor,
};

pub type Bounds = [f64; 4]; // min x, min y, max x, max y; geometry only
pub fn map(m: Matrix, p: Point) -> Point {
    [
        m[0] * p[0] + m[2] * p[1] + m[4],
        m[1] * p[0] + m[3] * p[1] + m[5],
    ]
}
/// Column-vector composition: apply right, then left.
pub fn multiply(left: Matrix, right: Matrix) -> Matrix {
    let x = map(
        [left[0], left[1], left[2], left[3], 0.0, 0.0],
        [right[0], right[1]],
    );
    let y = map(
        [left[0], left[1], left[2], left[3], 0.0, 0.0],
        [right[2], right[3]],
    );
    let t = map(left, [right[4], right[5]]);
    [x[0], x[1], y[0], y[1], t[0], t[1]]
}
pub fn inverse(m: Matrix) -> Result<Matrix, Error> {
    validate_matrix(m)?;
    affine::inverse(m)
}
/// Certify the complete inverse-parent product, including intermediate roundoff.
/// The exact fallback rounds only its final coefficients.
pub(crate) fn relative_transform(parent: Matrix, factors: &[Matrix]) -> Result<Matrix, Error> {
    validate_matrix(parent)?;
    affine::relative_transform(parent, factors)
}
/// Compose forward and inverse factors, preserving the complete expression for
/// the exact fallback. Inverted inputs keep the ordinary matrix admission rules.
pub(crate) fn transform_expression(factors: &[TransformFactor]) -> Result<Matrix, Error> {
    for factor in factors {
        if let TransformFactor::Inverse(matrix) = factor {
            validate_matrix(*matrix)?;
        }
    }
    affine::transform_expression(factors)
}
pub(crate) fn inverse_point(matrix: Matrix, point: Point) -> Result<Point, Error> {
    let out = relative_transform(matrix, &[[1.0, 0.0, 0.0, 1.0, point[0], point[1]]])?;
    Ok([out[4], out[5]])
}
pub(crate) fn translated_local(
    parent: Matrix,
    local: Matrix,
    delta: Point,
) -> Result<Matrix, Error> {
    let mut result = relative_transform(
        parent,
        &[[1.0, 0.0, 0.0, 1.0, delta[0], delta[1]], parent, local],
    )?;
    // A world translation cannot change the local linear part.
    result[..4].copy_from_slice(&local[..4]);
    Ok(result)
}
pub(crate) fn validate_matrix(m: Matrix) -> Result<(), Error> {
    if m.iter().any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE) {
        return Err(invalid(
            "Transform values must be finite and within coordinate limits",
        ));
    }
    if !affine::determinant_supported(m) {
        return Err(Error::new(
            "UNSUPPORTED",
            "Singular or near-singular transforms are not supported",
        ));
    }
    let raster_matrix = m.map(|v| v as f32);
    if raster_matrix[0] * raster_matrix[3] - raster_matrix[1] * raster_matrix[2] == 0.0 {
        return Err(Error::new(
            "UNSUPPORTED",
            "Transform becomes singular at renderer precision",
        ));
    }
    Ok(())
}
pub(crate) fn control_points(g: &Geometry) -> Vec<Point> {
    match g {
        Geometry::Compound { operands, .. } => operands
            .iter()
            .flat_map(|v| {
                control_points(&v.geometry)
                    .into_iter()
                    .map(|p| map(v.transform, p))
            })
            .collect(),
        Geometry::RoundedRect { .. }
        | Geometry::Polygon { .. }
        | Geometry::RegularPolygon { .. }
        | Geometry::Star { .. } => crate::primitives::expand(g)
            .map(|path| control_points(&path))
            .unwrap_or_default(),
        Geometry::Rect {
            x,
            y,
            width,
            height,
        } => vec![
            [*x, *y],
            [x + width, *y],
            [x + width, y + height],
            [*x, y + height],
        ],
        Geometry::Ellipse { cx, cy, rx, ry } => vec![
            [cx - rx, cy - ry],
            [cx + rx, cy - ry],
            [cx + rx, cy + ry],
            [cx - rx, cy + ry],
        ],
        Geometry::Path { commands } => commands
            .iter()
            .flat_map(|c| match c {
                PathCommand::Move { to } | PathCommand::Line { to } => vec![*to],
                PathCommand::Cubic {
                    control1,
                    control2,
                    to,
                } => vec![*control1, *control2, *to],
                PathCommand::Close {} => vec![],
            })
            .collect(),
    }
}
pub(crate) fn validate_geometry(g: &Geometry) -> Result<usize, Error> {
    if matches!(g, Geometry::Compound { .. }) {
        return crate::work_paths::validate_compound(g);
    }
    if crate::primitives::parametric(g) {
        return validate_geometry(&crate::primitives::expand(g)?);
    }
    if let Geometry::Path { commands } = g
        && commands.len() > MAX_SEGMENTS
    {
        return Err(limit("Path exceeds 4096 commands"));
    }
    if control_points(g)
        .iter()
        .flatten()
        .any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE)
    {
        return Err(invalid(
            "Geometry coordinates must be finite and within +/-32768",
        ));
    }
    match g {
        Geometry::Rect { width, height, .. }
            if !width.is_finite() || !height.is_finite() || *width < 0.001 || *height < 0.001 =>
        {
            Err(invalid("Rectangle dimensions must be at least 0.001"))
        }
        Geometry::Ellipse { rx, ry, .. }
            if !rx.is_finite() || !ry.is_finite() || *rx < 0.001 || *ry < 0.001 =>
        {
            Err(invalid("Ellipse radii must be at least 0.001"))
        }
        Geometry::Path { commands } => {
            let mut active = false;
            let mut drawn = false;
            for command in commands {
                match command {
                    PathCommand::Move { .. } => {
                        if active && !drawn {
                            return Err(invalid("Each contour needs a line or cubic segment"));
                        }
                        active = true;
                        drawn = false;
                    }
                    PathCommand::Line { .. } | PathCommand::Cubic { .. } => {
                        if !active {
                            return Err(invalid("A contour must start with move"));
                        }
                        drawn = true;
                    }
                    PathCommand::Close {} => {
                        if !active || !drawn {
                            return Err(invalid("Close requires a nonempty open contour"));
                        }
                        active = false;
                    }
                }
            }
            if commands.is_empty() || (active && !drawn) {
                return Err(invalid("Path requires drawable segments"));
            }
            Ok(commands.len())
        }
        Geometry::Rect { .. } | Geometry::Ellipse { .. } => Ok(4),
        _ => unreachable!("Parametric geometry was validated above"),
    }
}
fn include(bounds: &mut Bounds, p: Point) {
    bounds[0] = bounds[0].min(p[0]);
    bounds[1] = bounds[1].min(p[1]);
    bounds[2] = bounds[2].max(p[0]);
    bounds[3] = bounds[3].max(p[1]);
}
fn cubic(p: [Point; 4], t: f64) -> Point {
    let u = 1.0 - t;
    std::array::from_fn(|i| {
        u * u * u * p[0][i]
            + 3.0 * u * u * t * p[1][i]
            + 3.0 * u * t * t * p[2][i]
            + t * t * t * p[3][i]
    })
}
fn cubic_bounds(bounds: &mut Bounds, p: [Point; 4]) {
    include(bounds, p[0]);
    include(bounds, p[3]);
    for axis in 0..2 {
        let a = -p[0][axis] + 3.0 * p[1][axis] - 3.0 * p[2][axis] + p[3][axis];
        let b = 2.0 * (p[0][axis] - 2.0 * p[1][axis] + p[2][axis]);
        let c = p[1][axis] - p[0][axis];
        let mut roots = Vec::new();
        if a.abs() < 1e-12 {
            if b.abs() >= 1e-12 {
                roots.push(-c / b);
            }
        } else {
            let discriminant = b * b - 4.0 * a * c;
            if discriminant >= 0.0 {
                let d = discriminant.sqrt();
                let q = -0.5 * (b + d.copysign(b));
                if q.abs() > 0.0 {
                    roots.extend([q / a, c / q]);
                } else {
                    roots.push(-b / (2.0 * a));
                }
            }
        }
        for t in roots {
            if t > 0.0 && t < 1.0 {
                include(bounds, cubic(p, t));
            }
        }
    }
}
pub fn bounds(g: &Geometry, m: Matrix) -> Bounds {
    let mut result = [
        f64::INFINITY,
        f64::INFINITY,
        f64::NEG_INFINITY,
        f64::NEG_INFINITY,
    ];
    match g {
        Geometry::Compound { operands, .. } => {
            for operand in operands {
                let b = bounds(&operand.geometry, multiply(m, operand.transform));
                include(&mut result, [b[0], b[1]]);
                include(&mut result, [b[2], b[3]]);
            }
        }
        Geometry::RoundedRect { .. }
        | Geometry::Polygon { .. }
        | Geometry::RegularPolygon { .. }
        | Geometry::Star { .. } => {
            return crate::primitives::expand(g).map_or([f64::NAN; 4], |path| bounds(&path, m));
        }
        Geometry::Ellipse { cx, cy, rx, ry } => {
            let center = map(m, [*cx, *cy]);
            let ex = (m[0] * rx).hypot(m[2] * ry);
            let ey = (m[1] * rx).hypot(m[3] * ry);
            result = [
                center[0] - ex,
                center[1] - ey,
                center[0] + ex,
                center[1] + ey,
            ];
        }
        Geometry::Rect { .. } => {
            for p in control_points(g) {
                include(&mut result, map(m, p));
            }
        }
        Geometry::Path { commands } => {
            let mut current = [0.0; 2];
            let mut start = current;
            for command in commands {
                match command {
                    PathCommand::Move { to } => {
                        current = map(m, *to);
                        start = current;
                        include(&mut result, current);
                    }
                    PathCommand::Line { to } => {
                        current = map(m, *to);
                        include(&mut result, current);
                    }
                    PathCommand::Cubic {
                        control1,
                        control2,
                        to,
                    } => {
                        let end = map(m, *to);
                        cubic_bounds(
                            &mut result,
                            [current, map(m, *control1), map(m, *control2), end],
                        );
                        current = end;
                    }
                    PathCommand::Close {} => {
                        current = start;
                    }
                }
            }
        }
    }
    result
}
/// Bounds relative to the parent. Use scene::bounds for world or group bounds.
pub fn item_bounds(item: &Item) -> Result<Bounds, Error> {
    if let Some(p) = crate::pixel_warps::plan(item)? {
        return Ok(bounds(&p.geometry(), item.transform));
    }
    match &item.content {
        Content::Volume { volume } => crate::volumes::bounds(volume, item.transform),
        Content::Appearance { appearance } => crate::appearance::bounds(appearance, item.transform),
        Content::Warp { warp } => Ok(bounds(&crate::warps::plan(warp)?.geometry, item.transform)),
        Content::Repeat { repeat } => {
            Ok(bounds(&crate::repeats::geometry(repeat)?, item.transform))
        }
        Content::Interpolation { interpolation } => {
            crate::interpolation::bounds(interpolation, item.transform)
        }
        Content::Adjustment { .. }
        | Content::MaskSource {}
        | Content::ComponentSource {}
        | Content::Instance { .. }
        | Content::StoryFrame { .. } => Err(Error::new(
            "INVALID_OPERATION",
            "Nonprinting mask sources and adjustment layers have no intrinsic geometry bounds",
        )),
        Content::Group { .. } => Err(Error::new(
            "INVALID_OPERATION",
            "Group bounds require document context; use scene::bounds",
        )),
        Content::Vector { geometry, .. } | Content::WorkPath { geometry, .. } => {
            Ok(bounds(geometry, item.transform))
        }
        Content::Frame { frame } => Ok(bounds(&frame.geometry(), item.transform)),
        Content::Text { frame } => Ok(bounds(&crate::text::frame_geometry(frame), item.transform)),
        Content::Image { width, height, .. } => Ok(bounds(
            &Geometry::Rect {
                x: 0.0,
                y: 0.0,
                width: *width,
                height: *height,
            },
            item.transform,
        )),
        Content::Object { object } => Ok(bounds(&object.geometry(), item.transform)),
        Content::Samples { grid } => Ok(bounds(&grid.geometry(), item.transform)),
        Content::StoredSamples { grid } => Ok(bounds(&grid.geometry(), item.transform)),
        Content::Raw { raw } => Ok(bounds(&raw.geometry(), item.transform)),
        Content::Raster { width, height, .. } | Content::Fill { width, height, .. } => Ok(bounds(
            &Geometry::Rect {
                x: 0.0,
                y: 0.0,
                width: *width as f64,
                height: *height as f64,
            },
            item.transform,
        )),
    }
}
