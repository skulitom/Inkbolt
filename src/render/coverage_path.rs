//! Convert original controls to output space before the coverage backend rounds.
use super::*;

pub(super) fn path(g: &Geometry, matrix: Matrix) -> Result<tiny_skia::Path, Error> {
    if crate::primitives::parametric(g) {
        return path(&crate::primitives::expand(g)?, matrix);
    }
    let point = |p: Point| geometry::map(matrix, p).map(|v| v as f32);
    let mut builder = tiny_skia::PathBuilder::new();
    let move_to = |b: &mut tiny_skia::PathBuilder, p| {
        let [x, y] = point(p);
        b.move_to(x, y);
    };
    let line_to = |b: &mut tiny_skia::PathBuilder, p| {
        let [x, y] = point(p);
        b.line_to(x, y);
    };
    let cubic_to = |b: &mut tiny_skia::PathBuilder, a, c, p| {
        let [ax, ay] = point(a);
        let [cx, cy] = point(c);
        let [px, py] = point(p);
        b.cubic_to(ax, ay, cx, cy, px, py);
    };
    match g {
        Geometry::Rect {
            x,
            y,
            width,
            height,
        } => {
            move_to(&mut builder, [*x, *y]);
            line_to(&mut builder, [x + width, *y]);
            line_to(&mut builder, [x + width, y + height]);
            line_to(&mut builder, [*x, y + height]);
            builder.close();
        }
        Geometry::Ellipse { cx, cy, rx, ry } => {
            // Original tangent-matched arcs: evaluating in binary64 also keeps
            // small radii around a large local center until placement is known.
            let step = std::f64::consts::TAU / 32.0;
            let k = 4.0 / 3.0 * (step / 4.0).tan();
            move_to(&mut builder, [cx + rx, *cy]);
            for n in 0..32 {
                let (sa, ca) = (n as f64 * step).sin_cos();
                let (sb, cb) = ((n + 1) as f64 * step).sin_cos();
                cubic_to(
                    &mut builder,
                    [cx + rx * (ca - k * sa), cy + ry * (sa + k * ca)],
                    [cx + rx * (cb + k * sb), cy + ry * (sb - k * cb)],
                    [cx + rx * cb, cy + ry * sb],
                );
            }
            builder.close();
        }
        Geometry::Path { commands } => {
            for command in commands {
                match command {
                    PathCommand::Move { to } => move_to(&mut builder, *to),
                    PathCommand::Line { to } => line_to(&mut builder, *to),
                    PathCommand::Cubic {
                        control1,
                        control2,
                        to,
                    } => {
                        cubic_to(&mut builder, *control1, *control2, *to);
                    }
                    PathCommand::Close {} => builder.close(),
                }
            }
        }
        _ => unreachable!("Parametric geometry was expanded above"),
    }
    builder.finish().ok_or_else(|| {
        Error::new(
            "RENDER_ERROR",
            "Geometry cannot be represented in output space by the renderer",
        )
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use num_rational::BigRational as Rational;
    use num_traits::Signed;

    fn r(value: f64) -> Rational {
        Rational::from_float(value).unwrap()
    }

    #[test]
    fn final_controls_agree_with_exact_rational_affine_arithmetic_at_extremes() {
        for origin in [-30000.0, -10000.0, 10000.0, 30000.0] {
            for scale in [-8192.0, -256.0, 1.0 / 1024.0, 1.0, 256.0, 8192.0, 32768.0] {
                let matrix = [
                    scale,
                    scale,
                    -scale,
                    1.0 - scale,
                    6.123456789,
                    6.123456789 - origin,
                ];
                let points = [
                    [origin, origin],
                    [origin + 5.7654321 / scale, origin],
                    [origin + 2.654321 / scale + 3.12345, origin + 3.12345],
                    [origin + 5.7654321, origin + 5.7654321],
                ];
                let g = Geometry::Path {
                    commands: vec![
                        PathCommand::Move { to: points[0] },
                        PathCommand::Cubic {
                            control1: points[1],
                            control2: points[2],
                            to: points[3],
                        },
                    ],
                };
                let output = path(&g, matrix).unwrap();
                assert_eq!(output.points().len(), points.len());
                for (point, actual) in points.iter().zip(output.points()) {
                    for (axis, observed) in [actual.x, actual.y].iter().enumerate() {
                        let exact = r(matrix[axis]) * r(point[0])
                            + r(matrix[axis + 2]) * r(point[1])
                            + r(matrix[axis + 4]);
                        assert!((r(*observed as f64) - exact).abs() <= r(0.00001));
                    }
                }
            }
        }
    }

    #[test]
    fn rectangle_endpoint_addition_precedes_coverage_rounding() {
        let g = Geometry::Rect {
            x: 16.006123456789,
            y: -15.991123456789,
            width: 0.0057654321,
            height: 0.0061234567,
        };
        let matrix = [1024.0, 0.0, 0.0, 1024.0, -16384.0, 16384.0];
        let output = path(&g, matrix).unwrap();
        let expected = [
            [16.006123456789, -15.991123456789],
            [16.006123456789 + 0.0057654321, -15.991123456789],
            [
                16.006123456789 + 0.0057654321,
                -15.991123456789 + 0.0061234567,
            ],
            [16.006123456789, -15.991123456789 + 0.0061234567],
        ];
        for (point, actual) in expected.iter().zip(output.points()) {
            for (axis, observed) in [actual.x, actual.y].iter().enumerate() {
                let exact = r(matrix[axis]) * r(point[0])
                    + r(matrix[axis + 2]) * r(point[1])
                    + r(matrix[axis + 4]);
                assert!((r(*observed as f64) - exact).abs() <= r(0.000001));
            }
        }
    }
}
