//! Irrational cubic-node parameters with exact rational world junctions.
use super::*;
mod contacts;
mod predicates;
mod scalar;
use scalar::{Q, bounded, root_enclosure};
type PointQ = [Q; 2];
type CubicQ = [PointQ; 4];

pub(super) struct Span {
    source: Cubic,
    from: Q,
    to: Q,
    d: R,
    controls: CubicQ,
    root: (R, R),
    endpoints: Segment,
}

fn value(p: &Cubic, t: &Q, d: &R) -> PointQ {
    std::array::from_fn(|axis| {
        p.iter().rev().fold(Q::rational(n(0)), |v, c| {
            v.mul(t, d).add(&Q::rational(c[axis].clone()))
        })
    })
}
fn derivative(p: &Cubic, t: &Q, d: &R) -> PointQ {
    std::array::from_fn(|axis| {
        (1..4).rev().fold(Q::rational(n(0)), |v, i| {
            v.mul(t, d).add(&Q::rational(&p[i][axis] * n(i as i32)))
        })
    })
}
fn rational_point(p: &PointQ) -> Result<P, Error> {
    Ok([p[0].rational_value()?, p[1].rational_value()?])
}
fn projected(p: &PointQ, direction: &P) -> Q {
    p[0].scale(&direction[0]).add(&p[1].scale(&direction[1]))
}
fn difference(a: &PointQ, b: &PointQ) -> PointQ {
    std::array::from_fn(|i| a[i].sub(&b[i]))
}

fn geometry(source: Cubic, from: Q, to: Q, d: R, depth: usize) -> Result<Curve, Error> {
    if from.b.is_zero() && to.b.is_zero() {
        return Ok(Curve::Rational(Box::new(curves::restricted(
            &source, &from.a, &to.a,
        ))));
    }
    bounded(&d)?;
    from.checked()?;
    to.checked()?;
    let start = value(&source, &from, &d);
    let end = value(&source, &to, &d);
    let scale = to.sub(&from).scale(&(n(1) / n(3)));
    let first = derivative(&source, &from, &d);
    let last = derivative(&source, &to, &d);
    let controls = [
        start.clone(),
        std::array::from_fn(|i| start[i].add(&first[i].mul(&scale, &d))),
        std::array::from_fn(|i| end[i].sub(&last[i].mul(&scale, &d))),
        end.clone(),
    ];
    for p in &controls {
        for v in p {
            v.checked()?;
        }
    }
    let endpoints = [rational_point(&start)?, rational_point(&end)?];
    let root = root_enclosure(&d, 128 + 16 * depth);
    Ok(Curve::Quadratic(Box::new(Span {
        source,
        from,
        to,
        d,
        controls,
        root,
        endpoints,
    })))
}

impl Span {
    pub fn chord(&self) -> Segment {
        self.endpoints.clone()
    }
    pub fn deviation(&self) -> R {
        let mut maximum = Q::rational(n(0));
        for (i, p) in self.controls.iter().enumerate() {
            let chord = lerp(
                &self.endpoints[0],
                &self.endpoints[1],
                &(n(i as i32) / n(3)),
            );
            let delta: PointQ = std::array::from_fn(|j| p[j].sub(&Q::rational(chord[j].clone())));
            let squared = delta[0]
                .mul(&delta[0], &self.d)
                .add(&delta[1].mul(&delta[1], &self.d));
            if squared.cmp(&maximum, &self.d) == Ordering::Greater {
                maximum = squared;
            }
        }
        maximum.enclosure(&self.root).1
    }
    pub fn monotone(&self) -> bool {
        let direction = sub(&self.endpoints[1], &self.endpoints[0]);
        dot(&direction, &direction) > n(0)
            && self.controls.windows(2).all(|v| {
                projected(&difference(&v[1], &v[0]), &direction).sign(&self.d) != Ordering::Less
            })
    }
    pub fn split(&self, depth: usize, budget: &mut Budget) -> Result<[Curve; 2], Error> {
        let mid = self.from.add(&self.to).scale(&(n(1) / n(2)));
        let lower = self.from.scale(&n(3)).add(&self.to).scale(&(n(1) / n(4)));
        let upper = self.from.add(&self.to.scale(&n(3))).scale(&(n(1) / n(4)));
        let mut bits = 4;
        use crate::limits::booleans_topology_quadratic::MAX_PARAMETER_BITS;
        loop {
            budget.spend(bits / 8 + 128)?;
            let enclosure = mid.enclosure(&root_enclosure(&self.d, 128.max(bits + 32)));
            let denominator = n(1).numer() << bits;
            let approximate =
                (enclosure.0 + enclosure.1) * R::from_integer(denominator.clone()) / n(2);
            let floor = approximate.to_integer();
            // A coarse dyadic cut keeps rational child curves inexpensive.
            // Exact comparisons require it inside the central half, so neither
            // child can retain more than three quarters of the parameter span.
            for numerator in [floor.clone(), floor + n(1).numer()] {
                let cut = Q::rational(R::new(numerator, denominator.clone()));
                if cut.cmp(&lower, &self.d) == Ordering::Greater
                    && cut.cmp(&upper, &self.d) == Ordering::Less
                {
                    return Ok([
                        geometry(
                            self.source.clone(),
                            self.from.clone(),
                            cut.clone(),
                            self.d.clone(),
                            depth,
                        )?,
                        geometry(
                            self.source.clone(),
                            cut,
                            self.to.clone(),
                            self.d.clone(),
                            depth,
                        )?,
                    ]);
                }
            }
            if bits >= MAX_PARAMETER_BITS {
                return Err(limit(&format!(
                    "Quadratic parameter separation exceeds {MAX_PARAMETER_BITS} dyadic parameter bits"
                )));
            }
            bits = (bits * 2).min(MAX_PARAMETER_BITS);
        }
    }
}

pub(super) enum Pair {
    Separated,
    Paired,
    Transverse(bool),
}
pub(super) fn pair(a: &Arc, b: &Arc, budget: &mut Budget) -> Result<Option<Pair>, Error> {
    predicates::pair(a, b, budget)
}

pub(super) fn reject_unrepresented_tangent(
    a: &Cubic,
    b: &Cubic,
    factor: &[R],
    budget: &mut Budget,
) -> Result<(), Error> {
    contacts::reject(a, b, factor, budget)
}

// Each noncollinear rational cubic has at most one ordinary node. Its
// parameters solve a rational quadratic, and its shared world point is rational.
pub(super) fn prepare(arcs: Vec<Arc>, budget: &mut Budget) -> Result<(Vec<Arc>, Value), Error> {
    let mut fields = vec![n(0); arcs.len()];
    let mut nodes: BTreeMap<P, Vec<(usize, Q)>> = BTreeMap::new();
    for (i, arc) in arcs.iter().enumerate().filter(|(_, a)| a.curved) {
        budget.spend(128)?;
        let p = curves::coefficients(
            arc.rational()
                .expect("quadratic preparation starts with rational curves"),
        );
        let determinant = cross(&p[2], &p[3]);
        if determinant.is_zero() {
            continue;
        }
        let sum = -cross(&p[1], &p[3]) / &determinant;
        let product = &sum * &sum - cross(&p[1], &p[2]) / determinant;
        let d = &sum * &sum - n(4) * product;
        if d <= n(0) || algebraic::square_root(&d).is_some() {
            continue;
        }
        bounded(&d)?;
        for sign in [-1, 1] {
            let t = Q {
                a: &sum / n(2),
                b: n(sign) / n(2),
            };
            if t.sign(&d) != Ordering::Greater || t.cmp(&Q::rational(n(1)), &d) != Ordering::Less {
                continue;
            }
            let point = rational_point(&value(&p, &t, &d))?;
            fields[i] = d.clone();
            nodes.entry(point).or_default().push((i, t));
        }
    }
    let mut cuts = vec![vec![Q::rational(n(0)), Q::rational(n(1))]; arcs.len()];
    let mut contacts = 0;
    let mut irrational_splits = 0;
    for (point, preimages) in nodes {
        let mut rational = vec![];
        for (i, arc) in arcs.iter().enumerate() {
            budget.spend(8)?;
            for t in algebraic::preimages(
                arc.rational().expect("rational preparation input"),
                &point,
                budget,
            )?
            .into_iter()
            .filter(unit)
            {
                rational.push((i, t));
            }
        }
        if preimages.len() + rational.len() < 2 {
            continue;
        }
        contacts += 1;
        irrational_splits += preimages.len();
        for (i, t) in preimages {
            cuts[i].push(t);
        }
        for (i, t) in rational {
            cuts[i].push(Q::rational(t));
        }
    }
    let mut out = vec![];
    let mut split_count = 0;
    for ((arc, mut times), d) in arcs.into_iter().zip(cuts).zip(fields) {
        times.sort_by(|a, b| a.cmp(b, &d));
        times.dedup_by(|a, b| a.cmp(b, &d) == Ordering::Equal);
        if times.len() == 2 {
            out.push(arc);
            if out.len() > MAX_EDGES {
                return Err(limit(&format!(
                    "Quadratic contacts exceed {MAX_EDGES} evaluated arcs"
                )));
            }
            continue;
        }
        if arc.depth == crate::limits::booleans::MAX_TOPOLOGY_DEPTH {
            return Err(Error::new(
                "CURVE_TOPOLOGY_UNRESOLVED",
                format!(
                    "Quadratic contact cuts exceed geometric depth {}",
                    crate::limits::booleans::MAX_TOPOLOGY_DEPTH
                ),
            ));
        }
        split_count += times.len() - 2;
        let source = curves::coefficients(arc.rational().expect("rational preparation input"));
        for pair in times.windows(2) {
            budget.spend(128)?;
            out.push(Arc {
                curve: geometry(
                    source.clone(),
                    pair[0].clone(),
                    pair[1].clone(),
                    d.clone(),
                    arc.depth + 1,
                )?,
                weights: arc.weights.clone(),
                depth: arc.depth + 1,
                curved: arc.curved,
            });
            if out.len() > MAX_EDGES {
                return Err(limit(&format!(
                    "Quadratic contacts exceed {MAX_EDGES} evaluated arcs"
                )));
            }
        }
    }
    let count = out.iter().filter(|a| a.rational().is_none()).count();
    Ok((
        out,
        json!({"method":"exact_quadratic_parameters_with_rational_junctions","contact_points":contacts,"irrational_parameter_splits":irrational_splits,"parameter_splits":split_count,"initial_algebraic_arcs":count,"minimum_root_enclosure_bits":128,"all_algebraic_contacts_located":false}),
    ))
}
