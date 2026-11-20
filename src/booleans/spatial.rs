//! Conservative exact boxes; candidates still require the original predicates.
use super::*;

#[derive(Clone)]
pub(super) struct Bounds {
    lo: P,
    hi: P,
}
impl Bounds {
    pub(super) fn points(points: &[P]) -> Self {
        Self {
            lo: std::array::from_fn(|axis| points.iter().map(|p| &p[axis]).min().unwrap().clone()),
            hi: std::array::from_fn(|axis| points.iter().map(|p| &p[axis]).max().unwrap().clone()),
        }
    }
    pub(super) fn union(&self, other: &Self) -> Self {
        Self {
            lo: std::array::from_fn(|i| self.lo[i].clone().min(other.lo[i].clone())),
            hi: std::array::from_fn(|i| self.hi[i].clone().max(other.hi[i].clone())),
        }
    }
    pub(super) fn overlaps(&self, other: &Self) -> bool {
        (0..2).all(|i| self.lo[i] <= other.hi[i] && other.lo[i] <= self.hi[i])
    }
    pub(super) fn winding_ray(&self, point: &P, axis: usize) -> bool {
        self.lo[axis] <= point[axis]
            && point[axis] <= self.hi[axis]
            && point[1 - axis] <= self.hi[1 - axis]
    }
    pub(super) fn ray(&self, origin: &P, direction: &P, maximum: Option<&R>) -> bool {
        let mut entry = n(0);
        let mut exit = maximum.cloned();
        for axis in 0..2 {
            if direction[axis].is_zero() {
                if origin[axis] < self.lo[axis] || origin[axis] > self.hi[axis] {
                    return false;
                }
                continue;
            }
            let a = (&self.lo[axis] - &origin[axis]) / &direction[axis];
            let b = (&self.hi[axis] - &origin[axis]) / &direction[axis];
            let (a, b) = if a <= b { (a, b) } else { (b, a) };
            entry = entry.max(a);
            exit = Some(exit.map_or_else(|| b.clone(), |old| old.min(b.clone())));
            if exit.as_ref().is_some_and(|end| *end < entry) {
                return false;
            }
        }
        true
    }
}

enum Kind {
    Leaf(usize),
    Branch([usize; 2]),
}
struct Node {
    bounds: Bounds,
    kind: Kind,
}
pub(super) struct Index {
    boxes: Vec<Bounds>,
    nodes: Vec<Node>,
}
impl Index {
    pub(super) fn new(boxes: Vec<Bounds>, budget: &mut Budget) -> Result<Self, Error> {
        let mut result = Self {
            boxes,
            nodes: vec![],
        };
        let mut ids: Vec<_> = (0..result.boxes.len()).collect();
        if !ids.is_empty() {
            result.build(&mut ids, budget)?;
        }
        Ok(result)
    }
    fn build(&mut self, ids: &mut [usize], budget: &mut Budget) -> Result<usize, Error> {
        budget.spend(ids.len())?;
        let bounds = ids[1..]
            .iter()
            .fold(self.boxes[ids[0]].clone(), |b, &i| b.union(&self.boxes[i]));
        let node = self.nodes.len();
        self.nodes.push(Node {
            bounds: bounds.clone(),
            kind: Kind::Leaf(ids[0]),
        });
        if ids.len() > 1 {
            let axis = usize::from(&bounds.hi[1] - &bounds.lo[1] > &bounds.hi[0] - &bounds.lo[0]);
            let mut comparisons = 0;
            ids.sort_unstable_by(|&a, &b| {
                comparisons += 1;
                self.boxes[a].lo[axis]
                    .cmp(&self.boxes[b].lo[axis])
                    .then(a.cmp(&b))
            });
            budget.spend(comparisons)?;
            let (left, right) = ids.split_at_mut(ids.len() / 2);
            let children = [self.build(left, budget)?, self.build(right, budget)?];
            self.nodes[node].kind = Kind::Branch(children);
        }
        Ok(node)
    }
    pub(super) fn bounds(&self, i: usize) -> &Bounds {
        &self.boxes[i]
    }
    pub(super) fn winding_axis(&self) -> usize {
        self.nodes.first().map_or(1, |node| {
            usize::from(
                &node.bounds.hi[0] - &node.bounds.lo[0] <= &node.bounds.hi[1] - &node.bounds.lo[1],
            )
        })
    }
    pub(super) fn query(
        &self,
        accept: impl Fn(&Bounds) -> bool,
        budget: &mut Budget,
    ) -> Result<Vec<usize>, Error> {
        let mut result = Vec::new();
        let mut pending = if self.nodes.is_empty() {
            vec![]
        } else {
            vec![0]
        };
        while let Some(i) = pending.pop() {
            budget.spend(1)?;
            let node = &self.nodes[i];
            if !accept(&node.bounds) {
                continue;
            }
            match node.kind {
                Kind::Leaf(id) => result.push(id),
                Kind::Branch(children) => pending.extend(children),
            }
        }
        Ok(result)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn both_winding_rays_agree_with_independent_rectangle_membership() {
        let corners = [[n(-2), n(-1)], [n(5), n(-1)], [n(5), n(3)], [n(-2), n(3)]];
        let edges = loop_edges(&corners);
        for x in -5..9 {
            for y in -4..7 {
                for offset in [n(0), n(1) / n(3)] {
                    let p = [n(x) + &offset, n(y) + &offset];
                    if on_boundary(&p, &edges) {
                        continue;
                    }
                    let expected = i32::from((-2..5).contains(&x) && (-1..3).contains(&y));
                    for axis in 0..2 {
                        assert_eq!(winding_axis(&p, &edges, axis), expected);
                        let reversed: Vec<_> =
                            edges.iter().map(|e| [e[1].clone(), e[0].clone()]).collect();
                        assert_eq!(winding_axis(&p, &reversed, axis), -expected);
                    }
                }
            }
        }
        let bounds = Bounds::points(&corners);
        assert!(!bounds.ray(&[n(-10), n(0)], &[n(1), n(0)], Some(&n(2))));
        assert!(bounds.ray(&[n(-4), n(0)], &[n(1), n(0)], Some(&n(2))));
        assert!(bounds.ray(&[n(7), n(0)], &[n(-1), n(0)], Some(&n(2))));
    }

    #[test]
    fn closed_boxes_keep_touching_sub_float_gaps_and_ray_events() {
        let tiny = n(2).pow(-80);
        let edges: Vec<Segment> = (0..40)
            .map(|i| {
                let x = n(i % 8) + &tiny;
                [[x.clone(), n(i / 8)], [x + n(1), n(i / 8 + 1)]]
            })
            .collect();
        let mut budget = Budget::default();
        let index = Index::new(
            edges.iter().map(|e| Bounds::points(e)).collect(),
            &mut budget,
        )
        .unwrap();
        for (i, a) in edges.iter().enumerate() {
            let candidates = index
                .query(|b| b.overlaps(index.bounds(i)), &mut budget)
                .unwrap();
            for (j, b) in edges.iter().enumerate() {
                if !intersections(a, b).is_empty() {
                    assert!(candidates.contains(&j));
                }
            }
        }
        for origin in [[n(-1), n(2)], [n(3), n(2) + &tiny]] {
            for direction in [[n(1), n(0)], [n(0), n(1)], [n(-2), n(-1)], [n(2), n(3)]] {
                let ray = [
                    origin.clone(),
                    std::array::from_fn(|i| &origin[i] + &direction[i] * n(20)),
                ];
                let candidates = index
                    .query(|b| b.ray(&origin, &direction, None), &mut budget)
                    .unwrap();
                for (j, edge) in edges.iter().enumerate() {
                    if !intersections(&ray, edge).is_empty() {
                        assert!(candidates.contains(&j));
                    }
                }
            }
        }
        let exhausted = &mut Budget {
            used: 0,
            maximum: 0,
        };
        assert!(index.query(|_| true, exhausted).is_err());
        assert!(Index::new(vec![Bounds::points(&edges[0])], exhausted).is_err());
    }
}
