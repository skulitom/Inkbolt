//! Project-owned parametric shapes and explicit cubic/linear expansion.
use crate::{Error, model::*};
pub const MAX_POLYGON_POINTS: usize = 1024;
pub const MAX_SIDES: u32 = 256;
pub const MAX_STAR_POINTS: u32 = 128;
pub fn parametric(g: &Geometry) -> bool {
    matches!(
        g,
        Geometry::RoundedRect { .. }
            | Geometry::Polygon { .. }
            | Geometry::RegularPolygon { .. }
            | Geometry::Star { .. }
    )
}
fn finite(value: f64) -> bool {
    value.is_finite() && value.abs() <= MAX_COORDINATE
}
fn radius(value: f64) -> bool {
    finite(value) && value >= 0.001
}
fn three_distinct(points: &[Point]) -> bool {
    let mut distinct = Vec::new();
    for &p in points {
        if !distinct.contains(&p) {
            distinct.push(p);
            if distinct.len() == 3 {
                return true;
            }
        }
    }
    false
}
pub fn validate(g: &Geometry) -> Result<(), Error> {
    let valid = match g {
        Geometry::RoundedRect {
            x,
            y,
            width,
            height,
            radii,
        } => {
            finite(*x)
                && finite(*y)
                && radius(*width)
                && radius(*height)
                && radii.iter().all(|&r| finite(r) && r >= 0.0)
        }
        Geometry::Polygon { points } => {
            (3..=MAX_POLYGON_POINTS).contains(&points.len())
                && three_distinct(points)
                && points.iter().flatten().all(|&v| finite(v))
        }
        Geometry::RegularPolygon {
            cx,
            cy,
            radius: r,
            sides,
            rotation,
        } => {
            finite(*cx)
                && finite(*cy)
                && radius(*r)
                && (3..=MAX_SIDES).contains(sides)
                && rotation.is_finite()
                && rotation.abs() <= 360000.0
        }
        Geometry::Star {
            cx,
            cy,
            outer_radius,
            inner_radius,
            points,
            rotation,
        } => {
            finite(*cx)
                && finite(*cy)
                && radius(*outer_radius)
                && radius(*inner_radius)
                && inner_radius <= outer_radius
                && (3..=MAX_STAR_POINTS).contains(points)
                && rotation.is_finite()
                && rotation.abs() <= 360000.0
        }
        _ => true,
    };
    if !valid {
        return Err(invalid(
            "Primitive parameters exceed coordinate, radius, side-count or rotation limits",
        ));
    }
    Ok(())
}
pub fn effective_radii(width: f64, height: f64, radii: [f64; 4]) -> [f64; 4] {
    let mut scale = 1.0_f64;
    for (size, sum) in [
        (width, radii[0] + radii[1]),
        (height, radii[1] + radii[2]),
        (width, radii[2] + radii[3]),
        (height, radii[3] + radii[0]),
    ] {
        if sum > 0.0 {
            scale = scale.min(size / sum);
        }
    }
    radii.map(|r| r * scale)
}
fn polygon(points: Vec<Point>) -> Vec<PathCommand> {
    std::iter::once(PathCommand::Move { to: points[0] })
        .chain(points[1..].iter().map(|&to| PathCommand::Line { to }))
        .chain(std::iter::once(PathCommand::Close {}))
        .collect()
}
/// Includes legacy rectangles/ellipses for explicit path conversion. Circular arcs use four cubics.
pub fn expand(g: &Geometry) -> Result<Geometry, Error> {
    validate(g)?;
    if !parametric(g) {
        crate::geometry::validate_geometry(g)?;
    }
    let k = 4.0 * (2.0_f64.sqrt() - 1.0) / 3.0;
    let commands = match g {
        Geometry::Compound { .. } => {
            return Err(Error::new(
                "UNSUPPORTED",
                "Retained compound regions cannot be implicitly flattened to ordinary paths",
            ));
        }
        Geometry::Path { commands } => commands.clone(),
        Geometry::Rect {
            x,
            y,
            width,
            height,
        } => polygon(vec![
            [*x, *y],
            [x + width, *y],
            [x + width, y + height],
            [*x, y + height],
        ]),
        Geometry::Ellipse { cx, cy, rx, ry } => vec![
            PathCommand::Move { to: [cx + rx, *cy] },
            PathCommand::Cubic {
                control1: [cx + rx, cy + k * ry],
                control2: [cx + k * rx, cy + ry],
                to: [*cx, cy + ry],
            },
            PathCommand::Cubic {
                control1: [cx - k * rx, cy + ry],
                control2: [cx - rx, cy + k * ry],
                to: [cx - rx, *cy],
            },
            PathCommand::Cubic {
                control1: [cx - rx, cy - k * ry],
                control2: [cx - k * rx, cy - ry],
                to: [*cx, cy - ry],
            },
            PathCommand::Cubic {
                control1: [cx + k * rx, cy - ry],
                control2: [cx + rx, cy - k * ry],
                to: [cx + rx, *cy],
            },
            PathCommand::Close {},
        ],
        Geometry::Polygon { points } => polygon(points.clone()),
        Geometry::RegularPolygon {
            cx,
            cy,
            radius,
            sides,
            rotation,
        } => polygon(
            (0..*sides)
                .map(|i| {
                    let a = rotation.rem_euclid(360.0).to_radians()
                        + std::f64::consts::TAU * i as f64 / *sides as f64;
                    [cx + radius * a.cos(), cy + radius * a.sin()]
                })
                .collect(),
        ),
        Geometry::Star {
            cx,
            cy,
            outer_radius,
            inner_radius,
            points,
            rotation,
        } => polygon(
            (0..points * 2)
                .map(|i| {
                    let a = rotation.rem_euclid(360.0).to_radians()
                        + std::f64::consts::PI * i as f64 / *points as f64;
                    let r = if i % 2 == 0 {
                        *outer_radius
                    } else {
                        *inner_radius
                    };
                    [cx + r * a.cos(), cy + r * a.sin()]
                })
                .collect(),
        ),
        Geometry::RoundedRect {
            x,
            y,
            width,
            height,
            radii,
        } => {
            let [a, b, c, d] = effective_radii(*width, *height, *radii);
            let right = x + width;
            let bottom = y + height;
            let mut out = vec![
                PathCommand::Move { to: [x + a, *y] },
                PathCommand::Line {
                    to: [right - b, *y],
                },
            ];
            if b > 0.0 {
                out.push(PathCommand::Cubic {
                    control1: [right - b + k * b, *y],
                    control2: [right, y + b - k * b],
                    to: [right, y + b],
                });
            }
            out.push(PathCommand::Line {
                to: [right, bottom - c],
            });
            if c > 0.0 {
                out.push(PathCommand::Cubic {
                    control1: [right, bottom - c + k * c],
                    control2: [right - c + k * c, bottom],
                    to: [right - c, bottom],
                });
            }
            out.push(PathCommand::Line {
                to: [x + d, bottom],
            });
            if d > 0.0 {
                out.push(PathCommand::Cubic {
                    control1: [x + d - k * d, bottom],
                    control2: [*x, bottom - d + k * d],
                    to: [*x, bottom - d],
                });
            }
            out.push(PathCommand::Line { to: [*x, y + a] });
            if a > 0.0 {
                out.push(PathCommand::Cubic {
                    control1: [*x, y + a - k * a],
                    control2: [x + a - k * a, *y],
                    to: [x + a, *y],
                });
            }
            out.push(PathCommand::Close {});
            out
        }
    };
    let result = Geometry::Path { commands };
    crate::geometry::validate_geometry(&result)?;
    Ok(result)
}
