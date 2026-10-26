//! A separate error certificate for the existing four-cubic ellipse expansion.
use super::*;
use num_traits::Signed;

fn radial_bound(k: &R) -> R {
    // For the unit quarter cubic, x(t)^2+y(t)^2-1 = u^2*(a+b*u),
    // u=t*(1-t) in [0,1/4]. Its only interior stationary point is -2a/(3b).
    // These identities hold for the encoded coefficient, not an ideal sqrt(2).
    let a = k * k * n(9) + k * n(6) - n(6);
    let q = k * n(3) - n(2);
    let b = -&q * &q * n(2);
    let value = |u: &R| u * u * (&a + &b * u);
    let quarter = R::new(1.into(), 4.into());
    let end = value(&quarter);
    let mut minimum = R::zero().min(end.clone());
    let mut maximum = R::zero().max(end);
    if !b.is_zero() {
        let stationary = -&a * n(2) / (&b * n(3));
        if stationary > R::zero() && stationary < quarter {
            let v = value(&stationary);
            minimum = minimum.min(v.clone());
            maximum = maximum.max(v);
        }
    }
    // sqrt(1+e)+1 >= 2+min(e,0), since the fixed coefficient has e > -1.
    maximum.max(minimum.abs()) / (n(2) + minimum)
}

pub(super) fn certificate(geometry: &Geometry, world: Matrix, actual: &[Cubic]) -> Option<Value> {
    let Geometry::Ellipse { cx, cy, rx, ry } = geometry else {
        return None;
    };
    let k = r(crate::primitives::circular_tangent());
    let radial = radial_bound(&k);
    let (cx, cy, rx, ry) = (r(*cx), r(*cy), r(*rx), r(*ry));
    let mut unit = [[n(1), n(0)], [n(1), k.clone()], [k, n(1)], [n(0), n(1)]];
    let mut construction = R::zero();
    for cubic in actual {
        for (encoded, ideal) in cubic.iter().zip(&unit) {
            let expected = mapped_r(&[&cx + &rx * &ideal[0], &cy + &ry * &ideal[1]], world);
            let error = sub(encoded, &expected);
            construction = construction.max(dot(&error, &error));
        }
        unit = unit.map(|p| [-p[1].clone(), p[0].clone()]);
    }
    // Frobenius norm bounds the affine image of a unit radial displacement.
    let linear = [
        r(world[0]) * &rx,
        r(world[1]) * &rx,
        r(world[2]) * &ry,
        r(world[3]) * &ry,
    ];
    let norm2: R = linear.iter().map(|v| v * v).sum();
    let radial_world = &radial * &radial * norm2;
    // (a+b)^2 <= 2(a^2+b^2); avoid introducing an uncertified floating sqrt.
    let total = if construction.is_zero() {
        radial_world
    } else {
        (radial_world + &construction) * n(2)
    };
    Some(json!({
        "method":"four_tangent_cubics",
        "coefficient":crate::primitives::circular_tangent(),
        "unit_radial_deviation_bound":radial.to_string(),
        "world_control_construction_deviation_squared":construction.to_string(),
        "world_space_deviation_squared":total.to_string(),
        "scope":"analytic_ellipse_to_expanded_cubics;separate_from_flattening_snapping_and_rounding",
        "topology":"curve_certificates_apply_to_expanded_cubics_not_analytic_ellipse_contacts"
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn encoded_quarter_cubic_radial_bound_is_positive_and_small() {
        let k = r(crate::primitives::circular_tangent());
        let bound = radial_bound(&k);
        assert!(bound > R::new(272.into(), 1_000_000.into()));
        assert!(bound < R::new(273.into(), 1_000_000.into()));
        // Independent Bernstein evaluation, including every non-dyadic i/1000.
        for i in 0..=1000 {
            let t = R::new(i.into(), 1000.into());
            let s = n(1) - &t;
            let x = &s * &s * &s + n(3) * &s * &s * &t + n(3) * &k * &s * &t * &t;
            let y = n(3) * &k * &s * &s * &t + n(3) * &s * &t * &t + &t * &t * &t;
            let square = &x * &x + &y * &y;
            assert!(square >= (n(1) - &bound) * (n(1) - &bound));
            assert!(square <= (n(1) + &bound) * (n(1) + &bound));
        }
    }
}
