//! Certified determinant decisions and inverse coefficients for finite matrices.
use crate::{Error, model::*};
use num_rational::BigRational as R;
use num_traits::{Signed, ToPrimitive};

pub(crate) const MIN_DETERMINANT: f64 = 1e-8;
// Coefficient error applied to any point in the accepted world-coordinate box.
// This does not include subsequent point arithmetic or renderer quantization.
pub(crate) const MAX_FAST_POINT_ERROR: f64 = 1e-9;

#[derive(Clone, Copy)]
struct Estimate {
    value: f64,
    error: f64,
}

fn add_bound(a: f64, b: f64) -> f64 {
    if a == 0.0 {
        b
    } else if b == 0.0 {
        a
    } else {
        (a + b).next_up()
    }
}
fn product_bound(a: f64, b: f64) -> f64 {
    if a == 0.0 || b == 0.0 {
        0.0
    } else {
        (a * b).next_up()
    }
}
fn product_error(a: f64, b: f64, product: f64) -> f64 {
    if a == 0.0 || b == 0.0 {
        0.0
    } else {
        // One upward step covers an underflowed fused residual as well.
        a.mul_add(b, -product).abs().next_up()
    }
}
fn difference(a: f64, b: f64, c: f64, d: f64) -> Estimate {
    let p = a * b;
    let q = -(c * d);
    let value = p + q;
    let q_part = value - p;
    let sum_error = ((p - (value - q_part)) + (q - q_part)).abs();
    Estimate {
        value,
        error: add_bound(
            add_bound(product_error(a, b, p), product_error(c, d, -q)),
            sum_error,
        ),
    }
}
fn rational(value: f64) -> R {
    R::from_float(value).expect("finite affine coefficient")
}
fn determinant(m: &[R; 6]) -> R {
    &m[0] * &m[3] - &m[1] * &m[2]
}
pub(super) fn determinant_supported(m: Matrix) -> bool {
    let d = difference(m[0], m[3], m[1], m[2]);
    if (d.value.abs() - d.error).next_down() >= MIN_DETERMINANT {
        true
    } else if add_bound(d.value.abs(), d.error) < MIN_DETERMINANT {
        false
    } else {
        // Compare the exact stored binary64 values with the unchanged binary64
        // threshold. Cancellation must not move a matrix across this boundary.
        determinant(&m.map(rational)).abs() >= rational(MIN_DETERMINANT)
    }
}
fn quotient(n: Estimate, d: Estimate) -> Estimate {
    let value = n.value / d.value;
    let lower = (d.value.abs() - d.error).next_down();
    if lower <= 0.0 || !value.is_finite() {
        return Estimate {
            value,
            error: f64::INFINITY,
        };
    }
    // For exact N,D in the estimated intervals:
    // |value - N/D| <= (|value*d-n| + error_n + |value|*error_d) / lower_D.
    let residual = value.mul_add(d.value, -n.value).abs().next_up();
    let numerator = add_bound(
        add_bound(residual, n.error),
        product_bound(value.abs(), d.error),
    );
    Estimate {
        value,
        error: (numerator / lower).next_up(),
    }
}
fn fast_inverse(m: Matrix) -> Option<Matrix> {
    let d = difference(m[0], m[3], m[1], m[2]);
    let numerators = [
        Estimate {
            value: m[3],
            error: 0.0,
        },
        Estimate {
            value: -m[1],
            error: 0.0,
        },
        Estimate {
            value: -m[2],
            error: 0.0,
        },
        Estimate {
            value: m[0],
            error: 0.0,
        },
        difference(m[2], m[5], m[3], m[4]),
        difference(m[1], m[4], m[0], m[5]),
    ];
    let result = numerators.map(|n| quotient(n, d));
    for axis in 0..2 {
        let error = add_bound(
            product_bound(
                add_bound(result[axis].error, result[axis + 2].error),
                2.0 * MAX_COORDINATE,
            ),
            result[axis + 4].error,
        );
        if !error.is_finite() || error > MAX_FAST_POINT_ERROR {
            return None;
        }
    }
    Some(result.map(|v| v.value))
}
fn rounded(value: &R) -> Result<f64, Error> {
    let out = value
        .to_f64()
        .filter(|v| v.is_finite())
        .ok_or_else(|| invalid("Inverse transform is not finite"))?;
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
                "Exact inverse coefficient could not be rounded to nearest binary64",
            ));
        }
    }
    Ok(out)
}
pub(super) fn inverse(m: Matrix) -> Result<Matrix, Error> {
    if let Some(result) = fast_inverse(m) {
        return Ok(result);
    }
    let m = m.map(rational);
    let d = determinant(&m);
    let numerators = [
        m[3].clone(),
        -&m[1],
        -&m[2],
        m[0].clone(),
        &m[2] * &m[5] - &m[3] * &m[4],
        &m[1] * &m[4] - &m[0] * &m[5],
    ];
    let mut result = [0.0; 6];
    for (out, numerator) in result.iter_mut().zip(numerators) {
        *out = rounded(&(numerator / &d))?;
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn product_difference_intervals_enclose_exact_values() {
        let values = [
            -32768.,
            -0.1,
            -1e-300,
            -f64::from_bits(1),
            0.,
            f64::from_bits(1),
            1e-300,
            0.3,
            32768.,
        ];
        for &a in &values {
            for &b in &values {
                for &c in &values {
                    let d = 0.1234567890123456;
                    let actual = difference(a, b, c, d);
                    let expected = rational(a) * rational(b) - rational(c) * rational(d);
                    assert!((rational(actual.value) - expected).abs() <= rational(actual.error));
                }
            }
        }
    }

    #[test]
    fn division_bounds_enclose_all_exact_interval_corners() {
        for n in [-1e9, -0.1, -1e-300, 0., f64::from_bits(1), 1e-300, 0.3, 1e9] {
            for d in [-1e9, -0.1, 1e-8, 0.1, 1e9] {
                let numerator = Estimate {
                    value: n,
                    error: 1e-18,
                };
                let divisor = Estimate {
                    value: d,
                    error: 1e-19,
                };
                let actual = quotient(numerator, divisor);
                for sn in [-1, 1] {
                    for sd in [-1, 1] {
                        let exact_n =
                            rational(n) + rational(numerator.error) * R::from_integer(sn.into());
                        let exact_d =
                            rational(d) + rational(divisor.error) * R::from_integer(sd.into());
                        assert!(
                            (rational(actual.value) - exact_n / exact_d).abs()
                                <= rational(actual.error)
                        );
                    }
                }
            }
        }
    }

    #[test]
    fn exact_boundary_and_neighbors_preserve_the_existing_minimum() {
        for d in [
            MIN_DETERMINANT.next_down(),
            MIN_DETERMINANT,
            MIN_DETERMINANT.next_up(),
        ] {
            for sign in [-1., 1.] {
                assert_eq!(
                    determinant_supported([1., 0., 0., sign * d, 0., 0.]),
                    d >= MIN_DETERMINANT
                );
            }
        }
        assert!(!determinant_supported([
            32768., 16384., 16384., 8192., 0., 0.
        ]));
    }

    #[test]
    fn cancelled_inverse_matches_independent_fraction_bit_patterns() {
        // Generated independently using Python Fraction from the exact input
        // floats, then Python's correctly rounded Fraction-to-float conversion.
        let m = [
            28082.236328125,
            19869.3466796875,
            21177.486328125,
            14983.94973752266,
            12345.25,
            -23456.5,
        ];
        assert_eq!(m[0] * m[3] - m[1] * m[2], 0.0);
        assert!(fast_inverse(m).is_none());
        assert_eq!(
            crate::geometry::inverse(m).unwrap().map(f64::to_bits),
            [
                0x4275542a3565b3cd,
                0xc27c48686fbaeba0,
                0xc27e251860f52af4,
                0x4283fc98a057361d,
                0xc36d9d45d166e55e,
                0x4373a28b03ad168f,
            ]
        );
    }

    #[test]
    fn ordinary_inverses_keep_fast_path_and_bound_exact_point_error() {
        for m in [
            identity(),
            [1.1, 0.03, -0.04, 0.9, 12.25, -23.5],
            [2., 0.5, -1., 1., 20., 4.],
            [-1., 0., 0., 1., 32768., -32768.],
        ] {
            let result = fast_inverse(m).expect("ordinary transform uses certified fast path");
            let r = m.map(rational);
            let d = determinant(&r);
            for x in [-65536., 65536.] {
                for y in [-65536., 65536.] {
                    let px = rational(x) - &r[4];
                    let py = rational(y) - &r[5];
                    let exact = [
                        (&r[3] * &px - &r[2] * &py) / &d,
                        (-&r[1] * &px + &r[0] * &py) / &d,
                    ];
                    for axis in 0..2 {
                        let actual = rational(result[axis]) * rational(x)
                            + rational(result[axis + 2]) * rational(y)
                            + rational(result[axis + 4]);
                        assert!((actual - &exact[axis]).abs() <= rational(MAX_FAST_POINT_ERROR));
                    }
                }
            }
        }
    }

    #[test]
    fn exact_rounding_handles_ties_and_subnormals() {
        for x in [
            0.,
            f64::from_bits(1),
            f64::from_bits(2),
            1.,
            1.0000000000000002,
            32768.,
        ] {
            let midpoint = (rational(x) + rational(x.next_up())) / R::from_integer(2.into());
            let expected = if x.to_bits() & 1 == 0 { x } else { x.next_up() };
            assert_eq!(rounded(&midpoint).unwrap(), expected);
            assert_eq!(rounded(&-midpoint).unwrap(), -expected);
        }
    }
}
