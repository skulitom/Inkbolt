//! Restore source subcurves on smaller intervals of the same selected polygon.
use super::*;

struct Boundary {
    loops: Vec<Vec<P>>,
    sources: Map,
}

fn subdivide(
    loops: &[Vec<P>],
    sources: &Map,
    conflicts: &BTreeSet<usize>,
    budget: &mut Budget,
) -> Result<Boundary, Error> {
    let edge_count: usize = loops.iter().map(Vec::len).sum();
    if edge_count + conflicts.len() > MAX_ATOMS {
        return Err(limit(
            "Boolean curve subdivision exceeds its boundary edge limit",
        ));
    }
    let mut boundary = Boundary {
        loops: Vec::with_capacity(loops.len()),
        sources: Map::new(),
    };
    let mut index = 0;
    for contour in loops {
        let mut points = Vec::with_capacity(contour.len());
        for edge in loop_edges(contour) {
            budget.spend(1)?;
            points.push(edge[0].clone());
            let origin = lookup(sources, &edge)?;
            if conflicts.contains(&index) {
                let Origin::Cubic(source) = origin else {
                    return Err(Error::new(
                        "INTERNAL",
                        "Missing source cubic for boundary subdivision",
                    ));
                };
                // The new vertex divides the existing rational chord. Split its
                // source interval at the same parameter, before moving either handle.
                let mid = lerp(&edge[0], &edge[1], &(n(1) / n(2)));
                let (left, right) = split(&source.controls);
                points.push(mid.clone());
                for (edge, controls) in [
                    ([edge[0].clone(), mid.clone()], left),
                    ([mid, edge[1].clone()], right),
                ] {
                    record(
                        &mut boundary.sources,
                        edge,
                        Origin::Cubic(Box::new(SourceCubic {
                            controls,
                            radius: source.radius.clone(),
                        })),
                    );
                }
            } else {
                record(&mut boundary.sources, edge, origin);
            }
            index += 1;
        }
        boundary.loops.push(points);
    }
    Ok(boundary)
}

pub(super) fn recover(
    loops: &[Vec<P>],
    sources: &Map,
    mut conflicts: BTreeSet<usize>,
    tolerance: &R,
    budget: &mut Budget,
) -> Result<Path, Error> {
    let mut boundary = subdivide(loops, sources, &conflicts, budget)?;
    let mut knots = conflicts.len();
    for pass in 1..=crate::limits::booleans::MAX_TOPOLOGY_DEPTH {
        // Checking the entire rounded polygon also covers a new midpoint that
        // is representable only slightly off its reference chord in binary64.
        let (rounded, deviation) = rounding(&boundary.loops, budget)?;
        if deviation > tolerance * tolerance / n(64) {
            return Err(Error::new(
                "PRECISION_LOSS",
                "Boolean chord knot rounding exceeds its tolerance budget",
            ));
        }
        let next = candidate(
            &boundary.loops,
            &boundary.sources,
            &rounded,
            tolerance,
            Placement::LinearOffsets,
            budget,
        )?;
        conflicts = certify(&next.spans, true, budget)?;
        if conflicts.is_empty() {
            let mut path = next.path;
            path.report["chord_subdivision"] = json!({"passes":pass,"inserted_knots":knots});
            path.knot_rounding = Some(deviation);
            return Ok(path);
        }
        if pass < crate::limits::booleans::MAX_TOPOLOGY_DEPTH {
            knots += conflicts.len();
            boundary = subdivide(&boundary.loops, &boundary.sources, &conflicts, budget)?;
        }
    }
    Err(unresolved(
        "Subdivided output cubics could introduce a contact along the rounded boundary",
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reversed_interval_is_split_at_its_own_parameter() {
        let p = |x, y| [n(x), n(y)];
        let contour = vec![p(4, 0), p(0, 0), p(0, 4)];
        let mut sources = Map::new();
        let edges = loop_edges(&contour);
        let radius = n(1) / n(17);
        let controls = [p(4, 1), p(4, 3), p(0, 3), p(0, 1)];
        record(
            &mut sources,
            edges[0].clone(),
            Origin::Cubic(Box::new(SourceCubic {
                controls,
                radius: radius.clone(),
            })),
        );
        for edge in &edges[1..] {
            record(&mut sources, edge.clone(), Origin::Line);
        }
        let boundary = subdivide(
            &[contour],
            &sources,
            &BTreeSet::from([0]),
            &mut Budget::default(),
        )
        .unwrap();
        assert_eq!(boundary.loops[0], [p(4, 0), p(2, 0), p(0, 0), p(0, 4)]);
        let top = |x| [n(x), n(5) / n(2)];
        for (edge, expected) in loop_edges(&boundary.loops[0]).iter().zip([
            [p(4, 1), p(4, 2), top(3), top(2)],
            [top(2), top(1), p(0, 2), p(0, 1)],
        ]) {
            let Origin::Cubic(source) = lookup(&boundary.sources, edge).unwrap() else {
                panic!("expected a source cubic")
            };
            assert_eq!(source.controls, expected);
            assert_eq!(source.radius, radius);
        }
    }

    #[test]
    fn a_knot_that_rounds_onto_an_existing_vertex_is_refused() {
        let a = [n(1), n(0)];
        let b = [n(1) + r(f64::EPSILON), n(0)];
        let c = [n(1), n(1)];
        let contour = vec![a.clone(), b.clone(), c];
        let mut sources = Map::new();
        let edges = loop_edges(&contour);
        record(
            &mut sources,
            edges[0].clone(),
            Origin::cubic(&line_controls(&a, &b)),
        );
        for edge in &edges[1..] {
            record(&mut sources, edge.clone(), Origin::Line);
        }
        let Err(error) = recover(
            &[contour],
            &sources,
            BTreeSet::from([0]),
            &n(1),
            &mut Budget::default(),
        ) else {
            panic!("a rounded knot must stay distinct from its neighbors")
        };
        assert_eq!(error.code, "PRECISION_LOSS");
    }
}
