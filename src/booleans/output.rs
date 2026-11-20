//! Retain the source of each oriented boundary atom and certify the emitted path.
use super::*;
mod deformation;
mod junctions;
mod refinement;
pub(super) use junctions::Junctions;
use num_traits::Signed;

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
#[schemars(rename = "BooleanOutput")]
pub enum Output {
    Polygon,
    #[default]
    Curves,
    /// Omit the option on an edit. New edits use curves, while historical retries
    /// and pending proposals follow the default that applied to the original request.
    #[serde(skip_deserializing, rename(serialize = "curves"))]
    #[schemars(skip)]
    Unspecified,
}
impl Output {
    pub(crate) fn unspecified() -> Self {
        Self::Unspecified
    }
    pub(crate) fn is_unspecified(&self) -> bool {
        *self == Self::Unspecified
    }
    pub fn is_polygon(&self) -> bool {
        *self == Self::Polygon
    }
    pub(super) fn sources(self) -> Sources {
        (self == Self::Curves).then(BTreeMap::new)
    }
}

#[derive(Clone, PartialEq)]
pub(super) enum Origin {
    Line,
    Cubic(Box<SourceCubic>),
    Unavailable,
}
#[derive(Clone, PartialEq)]
pub(super) struct SourceCubic {
    pub controls: Cubic,
    // Maximum component distance from the exact algebraic control. Zero for rational spans.
    pub radius: R,
}
impl Origin {
    pub(super) fn cubic(c: &Cubic) -> Self {
        Self::Cubic(Box::new(SourceCubic {
            controls: c.clone(),
            radius: R::zero(),
        }))
    }
    fn reverse(&mut self) {
        if let Self::Cubic(c) = self {
            c.controls.reverse();
        }
    }
}
type Map = BTreeMap<Segment, Origin>;
pub(super) type Sources = Option<Map>;
fn unresolved(message: &str) -> Error {
    Error::new("CURVE_TOPOLOGY_UNRESOLVED", message)
}
pub(super) fn record(map: &mut Map, mut edge: Segment, mut origin: Origin) {
    if edge[0] == edge[1] {
        return;
    }
    if edge[0] > edge[1] {
        edge.reverse();
        origin.reverse();
    }
    map.entry(edge)
        .and_modify(|old| {
            if *old != origin {
                *old = Origin::Unavailable;
            }
        })
        .or_insert(origin);
}
fn lookup(map: &Map, edge: &Segment) -> Result<Origin, Error> {
    let mut key = edge.clone();
    let reverse = key[0] > key[1];
    if reverse {
        key.reverse();
    }
    let mut origin = map
        .get(&key)
        .cloned()
        .ok_or_else(|| Error::new("INTERNAL", "Missing source for Boolean boundary edge"))?;
    if reverse {
        origin.reverse();
    }
    Ok(origin)
}
pub(super) fn split_source(
    raw: &Map,
    atoms: &mut Map,
    edge: &Segment,
    cuts: &BTreeSet<R>,
    points: &[P],
    junctions: Option<&Junctions>,
    budget: &mut Budget,
) -> Result<(), Error> {
    let origin = lookup(raw, edge)?;
    let intervals = junctions
        .map(|j| j.parameters(edge, cuts, points))
        .transpose()?;
    let polynomial = match &origin {
        Origin::Cubic(c) if cuts.len() > 2 => {
            let max_derivative = c
                .controls
                .windows(2)
                .flat_map(|w| sub(&w[0], &w[1]))
                .map(|d| d.abs() * n(3))
                .max()
                .unwrap();
            Some((curves::coefficients(&c.controls), &c.radius, max_derivative))
        }
        _ => None,
    };
    for (i, ((a, b), endpoints)) in cuts
        .iter()
        .zip(cuts.iter().skip(1))
        .zip(points.windows(2))
        .enumerate()
    {
        budget.spend(1)?;
        let origin = if let Some((poly, radius, speed)) = &polynomial {
            let (piece, uncertainty) = if let Some((junctions, intervals)) =
                junctions.zip(intervals.as_ref())
            {
                let (start, end) = (&intervals[i], &intervals[i + 1]);
                let piece = curves::restricted(poly, &start.mid(), &end.mid());
                for (source, chord) in [(&piece[0], &endpoints[0]), (&piece[3], &endpoints[1])] {
                    if source != chord && !junctions.positions.contains_key(chord) {
                        return Err(unresolved(
                            "A certified chord crossing still needs a true curve junction for exact curve output",
                        ));
                    }
                }
                // Each restricted control is a blossom at three endpoint parameters.
                // Its change per argument is bounded by the largest first difference.
                (piece, speed * start.radius().max(end.radius()))
            } else {
                (curves::restricted(poly, a, b), n(0))
            };
            Origin::Cubic(Box::new(SourceCubic {
                controls: piece,
                radius: *radius + uncertainty,
            }))
        } else {
            origin.clone()
        };
        record(atoms, [endpoints[0].clone(), endpoints[1].clone()], origin);
        if atoms.len() > MAX_ATOMS {
            return Err(limit("Boolean curve output exceeds its atomic edge limit"));
        }
    }
    Ok(())
}

pub(super) struct Path {
    pub commands: Vec<PathCommand>,
    pub report: Value,
    pub knot_rounding: Option<R>,
}
fn distance_squared(a: &P, b: &P) -> R {
    let delta = sub(a, b);
    dot(&delta, &delta)
}
fn to_point(p: &P) -> Result<Point, Error> {
    let coordinate = |v: &R| {
        v.to_f64()
            .filter(|x| x.is_finite() && x.abs() <= MAX_COORDINATE)
            .ok_or_else(|| invalid("Boolean curve control exceeds root geometry limits"))
    };
    Ok([coordinate(&p[0])?, coordinate(&p[1])?])
}
fn line_controls(a: &P, b: &P) -> Cubic {
    [
        a.clone(),
        lerp(a, b, &(n(1) / n(3))),
        lerp(a, b, &(n(2) / n(3))),
        b.clone(),
    ]
}
pub(super) fn materialize(
    arrangement: &Arrangement,
    rounded: &[Vec<Point>],
    tolerance: &R,
    strict: bool,
    budget: &mut Budget,
) -> Result<Path, Error> {
    let sources = arrangement
        .sources
        .as_ref()
        .ok_or_else(|| unresolved("Curve provenance is unavailable after output snap repair"))?;
    let placement = if strict {
        Placement::Source
    } else {
        Placement::EndpointTangents
    };
    let first = candidate(
        &arrangement.loops,
        sources,
        rounded,
        tolerance,
        placement,
        budget,
    )?;
    match certify(&first.spans, false, budget) {
        Ok(_) => return Ok(first.path),
        Err(e) if !strict && e.code == "CURVE_TOPOLOGY_UNRESOLVED" => {}
        Err(e) => return Err(e),
    }
    let retry = candidate(
        &arrangement.loops,
        sources,
        rounded,
        tolerance,
        Placement::LinearOffsets,
        budget,
    )?;
    let conflicts = certify(&retry.spans, true, budget)?;
    let mut path = if conflicts.is_empty() {
        retry.path
    } else {
        refinement::recover(&arrangement.loops, sources, conflicts, tolerance, budget)?
    };
    path.report["handle_adjustment"] = json!("linear_interpolation_of_snapped_endpoint_offsets");
    Ok(path)
}

#[derive(Clone, Copy)]
enum Placement {
    Source,
    EndpointTangents,
    LinearOffsets,
}

struct Candidate {
    path: Path,
    spans: Vec<(Cubic, bool)>,
}
fn candidate(
    loops: &[Vec<P>],
    sources: &Map,
    rounded: &[Vec<Point>],
    tolerance: &R,
    placement: Placement,
    budget: &mut Budget,
) -> Result<Candidate, Error> {
    let mut spans = Vec::new();
    let mut commands = Vec::new();
    let mut signed_area = R::zero();
    let mut maximum = R::zero();
    let mut source_shift = R::zero();
    let mut count = 0;
    for (contour, vertices) in loops.iter().zip(rounded) {
        commands.push(PathCommand::Move { to: vertices[0] });
        for (i, edge) in loop_edges(contour).into_iter().enumerate() {
            budget.spend(1)?;
            let next = (i + 1) % vertices.len();
            let start = vertices[i].map(r);
            let end = vertices[next].map(r);
            let (emitted, curved) = match lookup(sources, &edge)? {
                Origin::Unavailable => {
                    return Err(unresolved(
                        "The selected Boolean boundary needs a unique representable source curve",
                    ));
                }
                Origin::Line => {
                    if next != 0 {
                        commands.push(PathCommand::Line { to: vertices[next] });
                    }
                    signed_area += cross(&start, &end) / n(2);
                    (line_controls(&start, &end), false)
                }
                Origin::Cubic(source) => {
                    let SourceCubic {
                        controls: source,
                        radius,
                    } = *source;
                    let handle =
                        |index: usize, anchor: usize, target: &P| -> Result<Point, Error> {
                            let shift = match placement {
                                Placement::Source => return to_point(&source[index]),
                                Placement::EndpointTangents => sub(target, &source[anchor]),
                                // Adding a linear offset to the source polynomial keeps its
                                // displacement from its own chord at every parameter.
                                Placement::LinearOffsets => lerp(
                                    &sub(&start, &source[0]),
                                    &sub(&end, &source[3]),
                                    &(n(index as i32) / n(3)),
                                ),
                            };
                            to_point(&std::array::from_fn(|j| &source[index][j] + &shift[j]))
                        };
                    let control1 = handle(1, 0, &start)?;
                    let control2 = handle(2, 3, &end)?;
                    let emitted = [start, control1.map(r), control2.map(r), end];
                    for (a, b) in emitted.iter().zip(source.iter()) {
                        let shift = sub(a, b).map(|d| d.abs() + &radius);
                        source_shift = source_shift.max(dot(&shift, &shift));
                    }
                    signed_area += crate::dimensions::cubic_signed_area(&emitted);
                    commands.push(PathCommand::Cubic {
                        control1,
                        control2,
                        to: vertices[next],
                    });
                    count += 1;
                    (emitted, true)
                }
            };
            // The same-parameter difference is a cubic Bezier curve. Its control
            // hull bounds every point, including every recursively flattened span.
            for (a, b) in emitted.iter().zip(line_controls(&edge[0], &edge[1])) {
                maximum = maximum.max(distance_squared(a, &b));
            }
            spans.push((emitted, curved));
        }
        commands.push(PathCommand::Close {});
    }
    if count > 0 && (maximum > tolerance * tolerance || source_shift > tolerance * tolerance) {
        return Err(Error::new(
            "PRECISION_LOSS",
            "Emitted Boolean curves exceed the requested tolerance",
        ));
    }
    Ok(Candidate {
        spans,
        path: Path {
            commands,
            knot_rounding: None,
            report: json!({
                "cubic_segments":count,"signed_area_exact":signed_area.to_string(),
                "polygon_deviation_squared":maximum.to_string(),"source_curve_deviation_squared":source_shift.to_string(),
                "topology":"rounded_boundary_certified_through_curve_to_chord_deformation"
            }),
        },
    })
}

fn certify(
    spans: &[(Cubic, bool)],
    refine: bool,
    budget: &mut Budget,
) -> Result<BTreeSet<usize>, Error> {
    let mut conflicts = BTreeSet::new();
    if !spans.iter().any(|(_, curved)| *curved) {
        return Ok(conflicts);
    }
    let index = spatial::Index::new(
        spans
            .iter()
            .map(|(c, _)| spatial::Bounds::points(c))
            .collect(),
        budget,
    )?;
    for (i, (a, curved)) in spans.iter().enumerate() {
        if !curved {
            continue;
        }
        if !topology::monotone(a, &sub(&a[3], &a[0])) {
            return Err(unresolved(
                "A rounded output cubic could reverse along its chord",
            ));
        }
        for j in index.query(|b| b.overlaps(index.bounds(i)), budget)? {
            let (b, other_curved) = &spans[j];
            if *other_curved && j <= i {
                continue;
            }
            if !topology::separated(a, b, budget)?
                && !topology::paired_coordinate(a, b, budget)?
                && topology::transverse(a, b, budget)? != Some(false)
                && (!refine || !deformation::separated(a, b, budget)?)
            {
                if !refine {
                    return Err(unresolved(
                        "Curve output could introduce a contact along its rounded boundary",
                    ));
                }
                conflicts.insert(i);
                if *other_curved {
                    conflicts.insert(j);
                }
            }
        }
    }
    Ok(conflicts)
}
