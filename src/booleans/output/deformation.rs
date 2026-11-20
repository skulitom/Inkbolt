//! Certify disjoint rounded spans throughout their simultaneous straight-to-cubic deformation.
use super::*;

struct Family {
    ends: [Cubic; 2],
    original_endpoint: [bool; 2],
}

impl Family {
    fn new(curve: &Cubic) -> Self {
        Self {
            ends: [line_controls(&curve[0], &curve[3]), curve.clone()],
            original_endpoint: [true, true],
        }
    }

    fn split_parameter(&self) -> [Self; 2] {
        let [(a, b), (c, d)] = self.ends.each_ref().map(split);
        [
            Self {
                ends: [a, c],
                original_endpoint: [self.original_endpoint[0], false],
            },
            Self {
                ends: [b, d],
                original_endpoint: [false, self.original_endpoint[1]],
            },
        ]
    }

    fn split_time(&self) -> [Self; 2] {
        let middle: Cubic =
            std::array::from_fn(|i| lerp(&self.ends[0][i], &self.ends[1][i], &(n(1) / n(2))));
        [
            Self {
                ends: [self.ends[0].clone(), middle.clone()],
                original_endpoint: self.original_endpoint,
            },
            Self {
                ends: [middle, self.ends[1].clone()],
                original_endpoint: self.original_endpoint,
            },
        ]
    }
}

// For the two curve parameters and the shared deformation time, A(t,h)-B(u,h)
// is a tensor Bernstein polynomial of degree (3,3,1). If all its nonzero
// coefficients lie in an open half-plane through the origin, their convex
// combinations cannot vanish while any such coefficient has positive weight.
fn separated_cell(a: &Family, b: &Family, budget: &mut Budget) -> Result<bool, Error> {
    let terms = a.ends.len() * a.ends[0].len() * b.ends[0].len();
    budget.spend(terms * (terms.ilog2() as usize + 2))?;
    let mut directions = Vec::with_capacity(terms);
    for (ac, bc) in a.ends.iter().zip(&b.ends) {
        for (i, p) in ac.iter().enumerate() {
            for (j, q) in bc.iter().enumerate() {
                if p != q {
                    directions.push(sub(p, q));
                } else if (i == 0 || i == 3)
                    && (j == 0 || j == 3)
                    && !(a.original_endpoint[i / 3] && b.original_endpoint[j / 3])
                {
                    return Ok(false);
                }
            }
        }
    }
    // In a parameter interior all four basis weights are positive. An entire
    // row or column of zero coefficients would require a constant span. The
    // chord and rounded curve are monotone with distinct ends, as are their
    // subdivisions and interpolants. Only shared original endpoints may touch.
    // A gap larger than half a turn puts every direction in one open
    // half-plane. A single ray also qualifies; opposite rays do not.
    directions.sort_unstable_by(angle);
    Ok(directions
        .first()
        .zip(directions.last())
        .is_some_and(|(first, last)| {
            angle(first, last).is_eq()
                || directions
                    .iter()
                    .zip(directions.iter().cycle().skip(1))
                    .any(|(p, q)| cross(p, q) < R::zero())
        }))
}

fn visit(a: &Family, b: &Family, depth: usize, budget: &mut Budget) -> Result<bool, Error> {
    if separated_cell(a, b, budget)? {
        return Ok(true);
    }
    if depth == crate::limits::booleans::MAX_TOPOLOGY_DEPTH {
        return Ok(false);
    }
    // Bisect each parameter and the common time in turn. Both children must
    // certify; an unresolved or over-budget cell cannot authorize an output.
    match depth % 3 {
        0 => {
            let [lo, hi] = a.split_parameter();
            Ok(visit(&lo, b, depth + 1, budget)? && visit(&hi, b, depth + 1, budget)?)
        }
        1 => {
            let [lo, hi] = b.split_parameter();
            Ok(visit(a, &lo, depth + 1, budget)? && visit(a, &hi, depth + 1, budget)?)
        }
        _ => {
            let [a0, a1] = a.split_time();
            let [b0, b1] = b.split_time();
            Ok(visit(&a0, &b0, depth + 1, budget)? && visit(&a1, &b1, depth + 1, budget)?)
        }
    }
}

pub(super) fn separated(a: &Cubic, b: &Cubic, budget: &mut Budget) -> Result<bool, Error> {
    visit(&Family::new(a), &Family::new(b), 0, budget)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_crossings_coincidence_and_temporary_subdivision_endpoints() {
        let point = |x, y| [n(x), n(y)];
        let line = line_controls(&point(0, 0), &point(6, 0));
        let crossing = line_controls(&point(3, -2), &point(3, 2));
        // The parabola y=3(2t-1)^2 first touches the line at the final
        // deformation time. Their midpoints become cell corners after bisection.
        let tangent = [point(0, 3), point(2, -1), point(4, -1), point(6, 3)];
        for other in [&line, &crossing, &tangent] {
            assert!(!separated(&line, other, &mut Budget::default()).unwrap());
        }
        let budget = &mut Budget {
            used: MAX_WORK,
            maximum: MAX_WORK,
        };
        assert_eq!(
            separated(&line, &tangent, budget).unwrap_err().code,
            "RESOURCE_LIMIT"
        );
    }
}
