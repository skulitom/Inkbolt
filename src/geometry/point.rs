//! Bound point arithmetic separately from the construction of its input matrix.
use num_rational::BigRational as R;
use num_traits::ToPrimitive;

pub(crate) const MAX_ROUNDOFF: f64 = 1e-9;

// With rounded-product magnitudes summing to at most 2^20, the two products
// and two additions have absolute forward error below 2^-31, including gradual
// underflow. The factor-of-two margin covers the magnitude sum's own rounding.
const SMALL_TERMS: f64 = 1_048_576.0;

fn sum(a: f64, b: f64) -> (f64, f64) {
    let value = a + b;
    let part = value - a;
    (value, (a - (value - part)) + (b - part))
}
fn bound(a: f64, b: f64) -> f64 {
    (a + b).next_up()
}

pub(super) fn axis(a: f64, x: f64, b: f64, y: f64, t: f64) -> f64 {
    let ax = a * x;
    let by = b * y;
    let first = ax + by;
    let ordinary = first + t;
    if ax.abs() + by.abs() + t.abs() <= SMALL_TERMS {
        return ordinary;
    }
    if [ax, by, first, ordinary].iter().all(|v| v.is_finite()) {
        // Recover both product and addition residuals before adding the small
        // correction. Fused product residuals can underflow; their combined
        // uncertainty is covered by two least subnormal values.
        let (_, e1) = sum(ax, by);
        let (_, e2) = sum(first, t);
        let (c1, r1) = sum(a.mul_add(x, -ax), b.mul_add(y, -by));
        let (c2, r2) = sum(c1, e1);
        let (correction, r3) = sum(c2, e2);
        let (value, r4) = sum(ordinary, correction);
        let error = [r1, r2, r3, r4]
            .into_iter()
            .fold(f64::from_bits(2), |error, residual| {
                bound(error, residual.abs())
            });
        let half_spacing = ((value - value.next_down()).min(value.next_up() - value)) * 0.5;
        if value.is_finite() && (error <= MAX_ROUNDOFF || error < half_spacing) {
            return value;
        }
    }
    if ![a, x, b, y, t].iter().all(|v| v.is_finite()) {
        // Public arithmetic historically propagates nonfinite arguments. Engine
        // validation still rejects them; do not turn them into a rational panic.
        return ordinary;
    }
    // Ambiguous rounding and overflowing intermediate products retain the
    // complete finite expression. The result is rounded once, ties to even;
    // a genuinely unrepresentable result retains IEEE overflow behavior.
    let q = |v| R::from_float(v).expect("finite point argument");
    (q(a) * q(x) + q(b) * q(y) + q(t))
        .to_f64()
        .expect("finite rational has a rounded binary64 result")
}

#[cfg(test)]
mod tests {
    use super::*;
    use num_traits::Signed;

    fn exact(v: [f64; 5]) -> R {
        let [a, x, b, y, t] = v.map(|v| R::from_float(v).unwrap());
        a * x + b * y + t
    }
    fn check(v: [f64; 5]) {
        let wanted = exact(v);
        let [a, x, b, y, t] = v;
        let actual = axis(a, x, b, y, t);
        let nearest = wanted.to_f64().unwrap();
        assert!(
            actual == nearest
                || actual.is_finite()
                    && (R::from_float(actual).unwrap() - wanted).abs()
                        <= R::from_float(MAX_ROUNDOFF).unwrap(),
            "{v:?}: {actual:?}, nearest {nearest:?}"
        );
    }
    #[test]
    fn cancelled_products_overflow_and_halfway_rounding_match_exact_expressions() {
        for v in [
            [32767.1, 30000.0001, -32767.1, 30000., 6.125],
            [
                1.1 * 2f64.powi(40),
                10000. + 2f64.powi(-38),
                -1.1 * 2f64.powi(40),
                10000.,
                6.125,
            ],
            [1e308, 2., -1e308, 2., 7.],
            [1e308, 2., 1e308, 2., -1e308],
            [2f64.powi(53), 1., 1., 1., 0.],
            [2f64.powi(53), 1., 1., 1., f64::from_bits(1)],
            [2f64.powi(53), 1., 1., 1., -f64::from_bits(1)],
            [
                f64::MIN_POSITIVE,
                0.1,
                -f64::MIN_POSITIVE,
                0.1,
                f64::from_bits(1),
            ],
        ] {
            check(v);
            check(v.map(|v| -v));
        }
        assert_eq!(axis(1e308, 2., -1e308, 2., 7.), 7.);
        assert_eq!(
            axis(2f64.powi(53), 1., 1., 1., f64::from_bits(1)),
            2f64.powi(53) + 2.
        );
        assert!(axis(f64::INFINITY, 0., 1., 1., 0.).is_nan());
    }
    #[test]
    fn seeded_finite_expressions_keep_absolute_or_nearest_rounding_contract() {
        let mut state = 0x8c41_235b_7c12_946du64;
        let mut next = || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            // Every finite exponent, both signs, and independent mantissas.
            f64::from_bits((state & !(0x7ff << 52)) | ((state % 2047) << 52))
        };
        for _ in 0..768 {
            let a = next();
            let x = next();
            let t = next();
            check([a, x, -a, x.next_down(), t]);
            check([a, x, next(), next(), t]);
        }
        for i in 0..256 {
            let a = 32768. - i as f64 / 13.;
            let x = 30000. + i as f64 / 71.;
            check([a, x, -a, x.next_up(), 6.125]);
            check([a, 7.125, -19., 11.25, 1024.]);
        }
    }
}
