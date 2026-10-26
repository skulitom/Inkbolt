//! Bounded approximation of canonical curves, followed by the exact line arrangement.
use super::*;

pub(super) fn grid(tolerance: f64) -> R {
    // Construct the power of two as a rational, including subnormal tolerances.
    let bits = tolerance.to_bits();
    let exponent = ((bits >> 52) & 0x7ff) as i32;
    let power = if exponent == 0 {
        63 - bits.leading_zeros() as i32 - 1074
    } else {
        exponent - 1023
    } - 3;
    n(2).pow(power)
}

fn snap(p: &P, grid: &R) -> P {
    std::array::from_fn(|i| (&p[i] / grid).round() * grid)
}

fn deviation(c: &Cubic) -> R {
    (1..=2)
        .map(|i| {
            let chord = lerp(&c[0], &c[3], &R::new(i.into(), 3.into()));
            let delta = sub(&c[i as usize], &chord);
            dot(&delta, &delta)
        })
        .max()
        .unwrap()
}

pub(super) fn evaluate(
    inputs: &mut [Operand],
    tolerance: &R,
    grid: &R,
    budget: &mut Budget,
) -> Result<Value, Error> {
    let (arcs, mut summary) = curves::prepare(inputs, budget)?;
    let bound = tolerance * tolerance / n(4);
    let mut count: usize = inputs.iter().map(|input| input.edges.len()).sum();
    let mut flattened = 0;
    for (c, weights) in arcs {
        let mut pending = vec![(c, 0)];
        while let Some((c, depth)) = pending.pop() {
            budget.spend(1)?;
            let distance = deviation(&c);
            if distance > bound {
                if depth == crate::limits::booleans::MAX_TOPOLOGY_DEPTH {
                    return Err(limit(
                        "Boolean tolerance flattening exceeds geometric depth",
                    ));
                }
                let (a, b) = split(&c);
                pending.push((b, depth + 1));
                pending.push((a, depth + 1));
                continue;
            }
            flattened += 1;
            if flattened > MAX_EDGES {
                return Err(limit(
                    "Boolean tolerance flattening exceeds evaluated arc limit",
                ));
            }
            for (input, weight) in inputs.iter_mut().zip(&weights) {
                if *weight == 0 {
                    continue;
                }
                input.maximum = input.maximum.clone().max(distance.clone());
                for _ in 0..weight.unsigned_abs() {
                    budget.spend(1)?;
                    if c[0] != c[3] {
                        count += 1;
                        if count > MAX_EDGES {
                            return Err(limit(
                                "Boolean tolerance flattening exceeds aggregate edge limit",
                            ));
                        }
                        let (a, b) = if *weight > 0 {
                            (&c[0], &c[3])
                        } else {
                            (&c[3], &c[0])
                        };
                        emit_edge(&mut input.edges, a.clone(), b.clone())?;
                    }
                }
            }
        }
    }
    for input in inputs {
        let mut edges = Vec::new();
        for edge in &input.edges {
            budget.spend(1)?;
            let snapped = edge.each_ref().map(|p| {
                let q = snap(p, grid);
                let d = sub(p, &q);
                input.snapping = input.snapping.clone().max(dot(&d, &d));
                q
            });
            emit_edge(&mut edges, snapped[0].clone(), snapped[1].clone())?;
        }
        input.edges = edges;
    }
    summary["topology"] = json!({
        "certificate":"exact_arrangement_of_snapped_chords",
        "source_topology_preserved":false,
        "curve_arcs":flattened,
        "flattening_limit_squared":bound.to_string(),
        "grid_spacing":grid.to_string(),
        "snapping_limit_squared":(grid * grid / n(2)).to_string()
    });
    Ok(summary)
}

pub(super) fn repair(
    loops: &[Vec<P>],
    grid: &R,
    budget: &mut Budget,
) -> Result<(Arrangement, R), Error> {
    let mut input = Operand {
        edges: vec![],
        cubics: vec![],
        rule: FillRule::Nonzero,
        maximum: R::zero(),
        snapping: R::zero(),
        conversion: None,
    };
    let mut maximum = R::zero();
    for contour in loops {
        let mut points = Vec::new();
        for p in contour {
            budget.spend(1)?;
            let q = snap(p, grid);
            let d = sub(p, &q);
            maximum = maximum.max(dot(&d, &d));
            points.push(q);
        }
        for [a, b] in loop_edges(&points) {
            emit_edge(&mut input.edges, a, b)?;
        }
    }
    Ok((arrange(&[input], Mode::Union, budget)?, maximum))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn snap_union_removes_an_unrepresentable_sliver_and_keeps_a_separate_region() {
        let tiny = n(2).pow(-100);
        let loops = vec![
            vec![
                [n(1), n(1)],
                [n(1) + &tiny, n(1)],
                [n(1) + tiny, n(2)],
                [n(1), n(2)],
            ],
            vec![[n(3), n(3)], [n(5), n(3)], [n(5), n(5)], [n(3), n(5)]],
        ];
        let mut budget = Budget::default();
        assert_eq!(
            rounding(&loops, &mut budget).unwrap_err().code,
            "PRECISION_LOSS"
        );
        let (result, distance) = repair(&loops, &grid(0.125), &mut budget).unwrap();
        assert!(distance > R::zero());
        assert_eq!(result.loops.len(), 1);
        assert_eq!(area(&result.loops[0]), n(4));
        assert!(rounding(&result.loops, &mut budget).is_ok());
        let mut exhausted = Budget {
            used: MAX_WORK,
            ..Budget::default()
        };
        assert_eq!(
            repair(&loops, &grid(0.125), &mut exhausted)
                .err()
                .unwrap()
                .code,
            "RESOURCE_LIMIT"
        );
    }

    #[test]
    fn grid_and_tie_rounding_cover_normal_and_subnormal_tolerances() {
        for t in [f64::from_bits(1), f64::MIN_POSITIVE, 0.1, 0.125, 64.] {
            let g = grid(t);
            assert!(g <= r(t) / n(8));
            assert!(g > r(t) / n(16));
            for i in -9..=9 {
                let p = [
                    &g * R::new(i.into(), 2.into()),
                    &g * R::new((i + 1).into(), 3.into()),
                ];
                let q = snap(&p, &g);
                let d = sub(&p, &q);
                assert!(dot(&d, &d) <= &g * &g / n(2));
                assert!((&q[0] / &g).is_integer());
                assert!((&q[1] / &g).is_integer());
            }
        }
    }
}
