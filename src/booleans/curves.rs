//! Canonical rational parameterization and shared subdivision of coincident curves.
use super::*;

type Polynomial = [P; 4];

fn value(p: &Polynomial, t: &R) -> P {
    std::array::from_fn(|i| ((&p[3][i] * t + &p[2][i]) * t + &p[1][i]) * t + &p[0][i])
}
fn derivative(p: &Polynomial, t: &R) -> P {
    std::array::from_fn(|i| (&p[3][i] * t * n(3) + &p[2][i] * n(2)) * t + &p[1][i])
}
pub(super) fn coefficients(c: &Cubic) -> Polynomial {
    [
        c[0].clone(),
        std::array::from_fn(|i| (&c[1][i] - &c[0][i]) * n(3)),
        std::array::from_fn(|i| (&c[0][i] - &c[1][i] * n(2) + &c[2][i]) * n(3)),
        std::array::from_fn(|i| -&c[0][i] + &c[1][i] * n(3) - &c[2][i] * n(3) + &c[3][i]),
    ]
}
fn nonzero(p: &P) -> Option<usize> {
    p.iter().position(|v| !v.is_zero())
}

// For a noncollinear polynomial, normalize P(a + b*u). Under t=alpha+beta*s,
// a changes to (a-alpha)/beta and b to b/beta, so every coefficient is invariant.
fn canonical(c: &Cubic) -> Option<(Polynomial, R, R)> {
    let p = coefficients(c);
    if cross(&p[1], &p[2]).is_zero()
        && cross(&p[1], &p[3]).is_zero()
        && cross(&p[2], &p[3]).is_zero()
    {
        return None;
    }
    let degree = if nonzero(&p[3]).is_some() { 3 } else { 2 };
    let axis = nonzero(&p[degree]).expect("noncollinear polynomial has degree at least two");
    let a = -&p[degree - 1][axis] / (&p[degree][axis] * n(degree as i32));
    let first = derivative(&p, &a);
    let second: P = std::array::from_fn(|i| &p[2][i] + &p[3][i] * &a * n(3));
    let b = if let Some(k) = nonzero(&first) {
        n(1) / &first[k]
    } else {
        // A cubic stationary point may have no first-order coefficient. The
        // ratio of a second- to third-order coefficient has the required scale.
        &second[nonzero(&second).expect("noncollinear stationary cubic")] / &p[3][axis]
    };
    let b2 = &b * &b;
    let b3 = &b2 * &b;
    let normalized = [
        value(&p, &a),
        first.map(|v| v * &b),
        second.map(|v| v * &b2),
        p[3].clone().map(|v| v * b3.clone()),
    ];
    Some((normalized, -&a / &b, (n(1) - a) / b))
}

pub(super) fn restricted(p: &Polynomial, a: &R, b: &R) -> Cubic {
    let start = value(p, a);
    let end = value(p, b);
    let scale = (b - a) / n(3);
    let d0 = derivative(p, a);
    let d1 = derivative(p, b);
    [
        start.clone(),
        std::array::from_fn(|i| &start[i] + &d0[i] * &scale),
        std::array::from_fn(|i| &end[i] - &d1[i] * &scale),
        end,
    ]
}

pub(super) fn evaluate(
    inputs: &mut [Operand],
    tolerance: &R,
    budget: &mut Budget,
) -> Result<Value, Error> {
    if inputs
        .iter()
        .map(|v| v.edges.len() + v.cubics.len())
        .sum::<usize>()
        > MAX_EDGES
    {
        return Err(limit("Boolean inputs exceed 512 aggregate source edges"));
    }
    let count = inputs.len();
    let mut arcs = Vec::new();
    let mut groups: BTreeMap<Polynomial, BTreeMap<R, Vec<i32>>> = BTreeMap::new();
    let mut source_cubics = 0;
    let mut collinear_cubics = 0;
    for (source, input) in inputs.iter_mut().enumerate() {
        for c in std::mem::take(&mut input.cubics) {
            source_cubics += 1;
            budget.spend(128)?;
            if let Some((p, from, to)) = canonical(&c) {
                let events = groups.entry(p).or_default();
                let (lo, hi, sign) = if from < to {
                    (from, to, 1)
                } else {
                    (to, from, -1)
                };
                events.entry(lo).or_insert_with(|| vec![0; count])[source] += sign;
                events.entry(hi).or_insert_with(|| vec![0; count])[source] -= sign;
            } else {
                collinear_cubics += 1;
                // A trace on a line contributes exactly the signed endpoint
                // interval to filled winding; any backtracking cancels.
                emit_edge(&mut input.edges, c[0].clone(), c[3].clone())?;
            }
        }
    }
    let canonical_groups = groups.len();
    let mut removed_knots = 0;
    let mut shared_runs = 0;
    for (p, mut events) in groups {
        let before = events.len();
        events.retain(|_, delta| delta.iter().any(|v| *v != 0));
        removed_knots += before - events.len();
        let events: Vec<_> = events.into_iter().collect();
        let mut weights = vec![0; count];
        for pair in events.windows(2) {
            budget.spend(count)?;
            for (w, delta) in weights.iter_mut().zip(&pair[0].1) {
                *w += delta;
            }
            if weights.iter().all(|v| *v == 0) {
                continue;
            }
            shared_runs += 1;
            let c = restricted(&p, &pair[0].0, &pair[1].0);
            arcs.push(topology::Arc::curved(c, weights.clone()));
        }
    }
    let topology = topology::evaluate(inputs, arcs, tolerance, budget)?;
    Ok(json!({
        "source_cubics": source_cubics,
        "canonical_groups": canonical_groups,
        "collinear_cubics": collinear_cubics,
        "removed_parameter_knots": removed_knots,
        "shared_runs": shared_runs,
        "topology": topology,
        "collinear_model": "exact_filled_winding_endpoint_reduction",
        "coincidence": "exact_polynomial_coefficients_under_affine_parameter_changes",
        "subdivision": "per_operand_signed_multiplicity_events_then_shared_chords"
    }))
}
