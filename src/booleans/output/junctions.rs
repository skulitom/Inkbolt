//! Enclose the unique true crossing already proved by the strict topology solver.
use super::*;

#[derive(Clone)]
pub(super) struct Interval {
    lo: R,
    hi: R,
}
impl Interval {
    fn point(t: &R) -> Self {
        Self {
            lo: t.clone(),
            hi: t.clone(),
        }
    }
    fn reverse(&self) -> Self {
        Self {
            lo: n(1) - &self.hi,
            hi: n(1) - &self.lo,
        }
    }
    pub(super) fn mid(&self) -> R {
        (&self.lo + &self.hi) / n(2)
    }
    pub(super) fn radius(&self) -> R {
        (&self.hi - &self.lo) / n(2)
    }
}

#[derive(Clone)]
struct Part {
    c: Cubic,
    interval: Interval,
    lo: P,
    hi: P,
}
impl Part {
    fn new(c: Cubic, interval: Interval, error: &R) -> Self {
        let lo = std::array::from_fn(|k| c.iter().map(|p| &p[k]).min().unwrap() - error);
        let hi = std::array::from_fn(|k| c.iter().map(|p| &p[k]).max().unwrap() + error);
        Self {
            c,
            interval,
            lo,
            hi,
        }
    }
    fn halves(&self, error: &R) -> [Self; 2] {
        let mid = self.interval.mid();
        let (left, right) = split(&self.c);
        [
            Self::new(
                left,
                Interval {
                    lo: self.interval.lo.clone(),
                    hi: mid.clone(),
                },
                error,
            ),
            Self::new(
                right,
                Interval {
                    lo: mid,
                    hi: self.interval.hi.clone(),
                },
                error,
            ),
        ]
    }
    fn overlap(&self, b: &Self) -> bool {
        (0..2).all(|k| self.lo[k] <= b.hi[k] && b.lo[k] <= self.hi[k])
    }
}
fn isolate(
    a: SourceCubic,
    b: SourceCubic,
    budget: &mut Budget,
) -> Result<(P, Interval, Interval), Error> {
    let unit = Interval { lo: n(0), hi: n(1) };
    let mut pairs = vec![(
        Part::new(a.controls, unit.clone(), &a.radius),
        Part::new(b.controls, unit, &b.radius),
    )];
    for depth in 0..=crate::limits::booleans_topology_algebraic_roots::MAX_ROOT_DEPTH {
        budget.spend(pairs.len())?;
        // Each retained cell is a possible contact. Take the union of their
        // intersections, never a single arbitrarily chosen overlapping cell.
        let lower: P = std::array::from_fn(|k| {
            pairs
                .iter()
                .map(|(a, b)| (&a.lo[k]).max(&b.lo[k]))
                .min()
                .unwrap()
                .clone()
        });
        let upper: P = std::array::from_fn(|k| {
            pairs
                .iter()
                .map(|(a, b)| (&a.hi[k]).min(&b.hi[k]))
                .max()
                .unwrap()
                .clone()
        });
        if let Ok(point) = to_point(&lower)
            && to_point(&upper).is_ok_and(|end| end == point)
        {
            let parameters = |first: bool| {
                let intervals = pairs
                    .iter()
                    .map(|(a, b)| if first { &a.interval } else { &b.interval });
                Interval {
                    lo: intervals.clone().map(|i| &i.lo).min().unwrap().clone(),
                    hi: intervals.map(|i| &i.hi).max().unwrap().clone(),
                }
            };
            return Ok((point.map(r), parameters(true), parameters(false)));
        }
        if depth == crate::limits::booleans_topology_algebraic_roots::MAX_ROOT_DEPTH {
            break;
        }
        let mut children = Vec::new();
        for (left, right) in pairs {
            budget.spend(4)?;
            let right = right.halves(&b.radius);
            for x in left.halves(&a.radius) {
                for y in &right {
                    if x.overlap(y) {
                        if children.len() == MAX_ATOMS {
                            return Err(limit(
                                "Boolean crossing enclosure exceeds its candidate-cell limit",
                            ));
                        }
                        children.push((x.clone(), y.clone()));
                    }
                }
            }
        }
        if children.is_empty() {
            return Err(unresolved("No contact enclosure survived subdivision"));
        }
        pairs = children;
    }
    Err(unresolved(
        "True curve junction could not be rounded uniquely within the root isolation depth",
    ))
}

#[derive(Default)]
pub(in crate::booleans) struct Junctions {
    pub(in crate::booleans) positions: BTreeMap<P, P>,
    cuts: BTreeMap<(Segment, R), Interval>,
    partners: BTreeMap<(Segment, R), (Segment, R)>,
}
fn canonical(edge: &Segment, t: &R) -> (Segment, R) {
    if edge[0] <= edge[1] {
        (edge.clone(), t.clone())
    } else {
        ([edge[1].clone(), edge[0].clone()], n(1) - t)
    }
}
impl Junctions {
    pub(in crate::booleans) fn resolve(
        &mut self,
        sources: &Map,
        a: &Segment,
        b: &Segment,
        t: &R,
        u: &R,
        budget: &mut Budget,
    ) -> Result<(), Error> {
        if [t, u].iter().any(|x| x.is_zero() || **x == n(1)) {
            return Ok(());
        }
        let origins = [lookup(sources, a)?, lookup(sources, b)?];
        if origins.iter().all(|o| matches!(o, Origin::Line)) {
            return Ok(());
        }
        let keys = [canonical(a, t), canonical(b, u)];
        if self.partners.get(&keys[0]) == Some(&keys[1]) {
            return Ok(());
        }
        if keys.iter().any(|key| self.partners.contains_key(key)) {
            return Err(unresolved(
                "More than two source spans meet inside a transverse junction",
            ));
        }
        if self.positions.len() >= MAX_ATOMS {
            return Err(limit(
                "Boolean curve junction count exceeds its atomic edge limit",
            ));
        }
        let curve = |origin, e: &Segment| match origin {
            Origin::Cubic(c) => Ok(*c),
            Origin::Line => Ok(SourceCubic {
                controls: line_controls(&e[0], &e[1]),
                radius: n(0),
            }),
            Origin::Unavailable => Err(unresolved("A crossing has ambiguous curve provenance")),
        };
        let [left, right] = origins;
        let (position, ta, tb) = isolate(curve(left, a)?, curve(right, b)?, budget)?;
        let old = lerp(&a[0], &a[1], t);
        if self
            .positions
            .insert(old, position.clone())
            .is_some_and(|p| p != position)
        {
            return Err(unresolved(
                "A polygon junction corresponds to distinct curve crossings",
            ));
        }
        self.partners.insert(keys[0].clone(), keys[1].clone());
        self.partners.insert(keys[1].clone(), keys[0].clone());
        for ((edge, key), interval) in [a, b].into_iter().zip(keys).zip([ta, tb]) {
            self.cuts.insert(
                key,
                if edge[0] <= edge[1] {
                    interval
                } else {
                    interval.reverse()
                },
            );
        }
        Ok(())
    }
    pub(super) fn parameters(
        &self,
        edge: &Segment,
        cuts: &BTreeSet<R>,
        points: &[P],
    ) -> Result<Vec<Interval>, Error> {
        let mut previous: Option<R> = None;
        let mut intervals = Vec::new();
        for (t, p) in cuts.iter().zip(points) {
            let interval = if let Some(i) = self.cuts.get(&canonical(edge, t)) {
                if edge[0] <= edge[1] {
                    i.clone()
                } else {
                    i.reverse()
                }
            } else {
                if self.positions.get(p).is_some_and(|new| new != p) {
                    return Err(unresolved(
                        "A moving crossing coincides with a fixed boundary junction",
                    ));
                }
                Interval::point(t)
            };
            if previous.as_ref().is_some_and(|last| last >= &interval.lo) {
                return Err(unresolved(
                    "True crossings cannot be ordered on the source edge",
                ));
            }
            previous = Some(interval.hi.clone());
            intervals.push(interval);
        }
        Ok(intervals)
    }
}
