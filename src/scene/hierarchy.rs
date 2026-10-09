//! Error-bounded hierarchy composition with an exact fallback for cancellation.
use crate::{Error, model::*};
use num_rational::BigRational as R;
use num_traits::ToPrimitive;

// The fast result's composition error, applied to any stored control point.
pub(crate) const MAX_FAST_POINT_ERROR: f64 = 1e-9;

fn add_bound(a: f64, b: f64) -> f64 {
    if a == 0.0 {
        return b;
    }
    if b == 0.0 {
        return a;
    }
    (a + b).next_up()
}
fn product_bound(a: f64, b: f64) -> f64 {
    if a == 0.0 || b == 0.0 {
        return 0.0;
    }
    (a * b).next_up()
}
fn sum_error(a: f64, b: f64, sum: f64) -> f64 {
    // Recover the rounding residual without changing the ordinary result.
    let b_part = sum - a;
    ((a - (sum - b_part)) + (b - b_part)).abs()
}
fn product_error(a: f64, b: f64, product: f64) -> f64 {
    if a == 0.0 || b == 0.0 {
        return 0.0;
    }
    // The fused residual is exact unless it underflows. One upward step also
    // bounds a residual smaller than the least subnormal value.
    a.mul_add(b, -product).abs().next_up()
}
fn dot(a: f64, b: f64, x: f64, y: f64, t: f64, errors: [f64; 2]) -> (f64, f64) {
    let ax = a * x;
    let by = b * y;
    let sum = ax + by;
    let value = sum + t;
    if ![ax, by, sum, value].iter().all(|v| v.is_finite()) {
        return (value, f64::INFINITY);
    }
    let error = [
        product_bound(a.abs(), errors[0]),
        product_bound(b.abs(), errors[1]),
        product_error(a, x, ax),
        product_error(b, y, by),
        sum_error(ax, by, sum),
        sum_error(sum, t, value),
    ]
    .into_iter()
    .fold(0.0, add_bound);
    (value, error)
}
fn step(left: Matrix, right: Matrix, errors: Matrix) -> (Matrix, Matrix) {
    let mut result = [0.0; 6];
    let mut bounds = [0.0; 6];
    for column in 0..3 {
        for row in 0..2 {
            let i = column * 2 + row;
            (result[i], bounds[i]) = dot(
                left[row],
                left[row + 2],
                right[column * 2],
                right[column * 2 + 1],
                if column == 2 { left[row + 4] } else { 0.0 },
                [errors[column * 2], errors[column * 2 + 1]],
            );
        }
    }
    (result, bounds)
}
fn point_error(bounds: Matrix) -> f64 {
    (0..2)
        .map(|axis| {
            add_bound(
                product_bound(add_bound(bounds[axis], bounds[axis + 2]), MAX_COORDINATE),
                bounds[axis + 4],
            )
        })
        .fold(0.0, f64::max)
}
fn rational(x: f64) -> R {
    R::from_float(x).expect("finite hierarchy coefficient")
}
fn rounded(value: &R) -> Result<f64, Error> {
    let out = value
        .to_f64()
        .filter(|v| v.is_finite())
        .ok_or_else(|| invalid("Hierarchy transform is not finite"))?;
    // Certify nearest binary64 rounding independently of the conversion helper.
    // Exact midpoint ties choose the even significand, including subnormals.
    let encoded = rational(out);
    for adjacent in [out.next_down(), out.next_up()] {
        if !adjacent.is_finite() {
            continue;
        }
        let midpoint = (&encoded + rational(adjacent)) / R::from_integer(2.into());
        if (adjacent < out && value < &midpoint)
            || (adjacent > out && value > &midpoint)
            || (value == &midpoint && out.to_bits() & 1 != 0)
        {
            return Err(Error::new(
                "NUMERIC_ERROR",
                "Exact hierarchy coefficient could not be rounded to nearest binary64",
            ));
        }
    }
    Ok(out)
}
fn exact(local: Matrix, parents: &[Matrix]) -> Result<Matrix, Error> {
    let mut world = local.map(rational);
    for parent in parents {
        let m = parent.map(rational);
        world = std::array::from_fn(|i| {
            let column = i / 2;
            let row = i % 2;
            let value = &m[row] * &world[column * 2] + &m[row + 2] * &world[column * 2 + 1];
            if column == 2 {
                value + &m[row + 4]
            } else {
                value
            }
        });
    }
    let mut result = [0.0; 6];
    for (out, value) in result.iter_mut().zip(&world) {
        *out = rounded(value)?;
    }
    Ok(result)
}
pub(super) fn compose(local: Matrix, parents: &[Matrix]) -> Result<Matrix, Error> {
    if local
        .iter()
        .chain(parents.iter().flatten())
        .any(|v| !v.is_finite())
    {
        return Err(invalid("Hierarchy transforms must be finite"));
    }
    let mut world = local;
    let mut errors = [0.0; 6];
    for &parent in parents {
        (world, errors) = step(parent, world, errors);
        if world.iter().chain(&errors).any(|v| !v.is_finite()) {
            return exact(local, parents);
        }
    }
    if point_error(errors) <= MAX_FAST_POINT_ERROR {
        Ok(world)
    } else {
        exact(local, parents)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use num_traits::Signed;

    #[test]
    fn dot_error_bound_encloses_independent_exact_arithmetic() {
        let values = [
            -32768.,
            -30000.125,
            -1.1,
            -1e-300,
            -f64::from_bits(1),
            0.,
            f64::from_bits(1),
            1e-300,
            0.1,
            1.,
            8192.,
            32768.,
        ];
        for &a in &values {
            for &x in &values {
                for &b in &values {
                    let y = 0.1234567890123456;
                    let t = -8192.03125;
                    let (actual, bound) = dot(a, b, x, y, t, [0., 0.]);
                    let expected =
                        rational(a) * rational(x) + rational(b) * rational(y) + rational(t);
                    assert!((rational(actual) - expected).abs() <= rational(bound));
                }
            }
        }
    }

    #[test]
    fn exact_rounding_preserves_midpoint_ties_and_subnormal_results() {
        for x in [
            0.,
            f64::from_bits(1),
            f64::from_bits(2),
            1.,
            1.0000000000000002,
            32768.,
        ] {
            assert_eq!(rounded(&rational(x)).unwrap(), x);
            let midpoint = (rational(x) + rational(x.next_up())) / R::from_integer(2.into());
            let expected = if x.to_bits() & 1 == 0 { x } else { x.next_up() };
            assert_eq!(rounded(&midpoint).unwrap(), expected);
            assert_eq!(rounded(&-midpoint).unwrap(), -expected);
        }
    }

    #[test]
    fn propagated_coordinate_intervals_include_all_exact_corners() {
        for a in [-32768., -0.1, 0., 1.1, 8192.] {
            for b in [-8192., -0.3, 0., 0.2, 32768.] {
                let (x, y, t) = (30000.125, 30000.25, -30000.);
                let errors = [1e-12, 3e-12];
                let (actual, bound) = dot(a, b, x, y, t, errors);
                for sx in [-1, 1] {
                    for sy in [-1, 1] {
                        let exact_x =
                            rational(x) + rational(errors[0]) * R::from_integer(sx.into());
                        let exact_y =
                            rational(y) + rational(errors[1]) * R::from_integer(sy.into());
                        let expected = rational(a) * exact_x + rational(b) * exact_y + rational(t);
                        assert!((rational(actual) - expected).abs() <= rational(bound));
                    }
                }
            }
        }
    }

    #[test]
    fn fast_path_retains_ordinary_arithmetic_with_certified_propagation() {
        let local = [
            1.1,
            0.03,
            -0.04,
            0.9,
            -0.12345678901234567,
            0.9876543210987654,
        ];
        let parents = [
            [0.9375, -0.125, 0.25, 1.0625, -0.3125, 0.1875],
            [1.125, 0.03125, -0.0625, 0.875, 19.125, 12.625],
        ];
        let mut expected = local;
        for p in parents {
            expected = crate::geometry::multiply(p, expected);
        }
        assert_eq!(compose(local, &parents).unwrap(), expected);
    }
}
