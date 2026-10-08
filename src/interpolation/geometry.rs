//! Original piecewise polynomial correspondence between authored contours.
use super::*;
use crate::paths::Contour;
type Curve = [Point; 4];
#[derive(Clone)]
struct Segment {
    curve: Curve,
    line: bool,
}
#[derive(Clone)]
struct Ring {
    segments: Vec<Segment>,
    closed: bool,
    collapse: Point,
}
struct Matched {
    from: Vec<Segment>,
    to: Vec<Segment>,
    closed: bool,
}
pub(super) struct Correspondence {
    rings: Vec<Matched>,
    pub commands: usize,
}
fn split(c: Curve, t: f64) -> (Curve, Curve) {
    let a = mix_point(c[0], c[1], t);
    let b = mix_point(c[1], c[2], t);
    let d = mix_point(c[2], c[3], t);
    let e = mix_point(a, b, t);
    let f = mix_point(b, d, t);
    let p = mix_point(e, f, t);
    ([c[0], a, e, p], [p, f, d, c[3]])
}
fn trim(c: Curve, lo: f64, hi: f64) -> Curve {
    let left = if hi == 1.0 { c } else { split(c, hi).0 };
    if lo == 0.0 {
        left
    } else {
        split(left, lo / hi).1
    }
}
fn ring(c: Contour, anchor: Point) -> Ring {
    let mut segments: Vec<_> = c
        .edges
        .iter()
        .map(|e| {
            let controls = e.controls.unwrap_or([
                mix_point(e.from, e.to, 1.0 / 3.0),
                mix_point(e.from, e.to, 2.0 / 3.0),
            ]);
            Segment {
                curve: [e.from, controls[0], controls[1], e.to]
                    .map(|p| [p[0] - anchor[0], p[1] - anchor[1]]),
                line: e.controls.is_none(),
            }
        })
        .collect();
    let last = c.edges.last().map_or(c.start, |e| e.to);
    if c.closed && last != c.start {
        segments.push(Segment {
            curve: [
                last,
                mix_point(last, c.start, 1.0 / 3.0),
                mix_point(last, c.start, 2.0 / 3.0),
                c.start,
            ]
            .map(|p| [p[0] - anchor[0], p[1] - anchor[1]]),
            line: true,
        });
    }
    let mut bounds = [
        f64::INFINITY,
        f64::INFINITY,
        f64::NEG_INFINITY,
        f64::NEG_INFINITY,
    ];
    for s in &segments {
        for p in s.curve {
            bounds[0] = bounds[0].min(p[0]);
            bounds[1] = bounds[1].min(p[1]);
            bounds[2] = bounds[2].max(p[0]);
            bounds[3] = bounds[3].max(p[1]);
        }
    }
    Ring {
        segments,
        closed: c.closed,
        collapse: [(bounds[0] + bounds[2]) / 2.0, (bounds[1] + bounds[3]) / 2.0],
    }
}
fn contours(g: &Geometry, anchor: Point) -> Result<Vec<Ring>, Error> {
    let Geometry::Path { commands } = crate::primitives::expand(g)? else {
        unreachable!()
    };
    Ok(crate::paths::parse(&commands)
        .into_iter()
        .map(|c| ring(c, anchor))
        .collect())
}
fn section(r: &Ring, lo: f64, hi: f64) -> Segment {
    let n = r.segments.len() as f64;
    let index = (((lo + hi) * 0.5 * n).floor() as usize).min(r.segments.len() - 1);
    let segment = &r.segments[index];
    Segment {
        curve: trim(
            segment.curve,
            (lo * n - index as f64).clamp(0.0, 1.0),
            (hi * n - index as f64).clamp(0.0, 1.0),
        ),
        line: segment.line,
    }
}
fn collapsed(r: &Ring) -> Ring {
    Ring {
        segments: vec![Segment {
            curve: [r.collapse; 4],
            line: true,
        }],
        closed: r.closed,
        collapse: r.collapse,
    }
}
impl Correspondence {
    pub fn new(spec: &Spec, anchors: [Point; 2]) -> Result<Self, Error> {
        let from = contours(&spec.from.geometry, anchors[0])?;
        let to = contours(&spec.to.geometry, anchors[1])?;
        let pairs = if spec.contours.is_empty() {
            let mut out = vec![];
            for i in 0..from.len().max(to.len()) {
                match (from.get(i), to.get(i)) {
                    (Some(a), Some(b)) if a.closed != b.closed => {
                        out.push(Pair {
                            from: Some(i),
                            to: None,
                            to_start: 0,
                        });
                        out.push(Pair {
                            from: None,
                            to: Some(i),
                            to_start: 0,
                        });
                    }
                    _ => out.push(Pair {
                        from: (i < from.len()).then_some(i),
                        to: (i < to.len()).then_some(i),
                        to_start: 0,
                    }),
                }
            }
            out
        } else {
            spec.contours.clone()
        };
        let mut seen_from = std::collections::HashSet::new();
        let mut seen_to = std::collections::HashSet::new();
        let mut rings = vec![];
        let mut commands = 0;
        for pair in pairs {
            if pair.from.is_none() && pair.to.is_none() {
                return Err(invalid(
                    "A contour pair must reference at least one endpoint contour",
                ));
            }
            let a = pair
                .from
                .map(|i| {
                    if !seen_from.insert(i) {
                        return Err(invalid("Each source contour must appear exactly once"));
                    }
                    from.get(i)
                        .cloned()
                        .ok_or_else(|| invalid("Source contour index does not exist"))
                })
                .transpose()?;
            let mut b = pair
                .to
                .map(|i| {
                    if !seen_to.insert(i) {
                        return Err(invalid("Each destination contour must appear exactly once"));
                    }
                    to.get(i)
                        .cloned()
                        .ok_or_else(|| invalid("Destination contour index does not exist"))
                })
                .transpose()?;
            if pair.to_start != 0 {
                let b = b
                    .as_mut()
                    .ok_or_else(|| invalid("A seam offset requires a destination contour"))?;
                if !b.closed || pair.to_start >= b.segments.len() {
                    return Err(invalid(
                        "Seam offsets require a closed destination and an existing segment index",
                    ));
                }
                b.segments.rotate_left(pair.to_start);
            }
            let a = a.unwrap_or_else(|| collapsed(b.as_ref().unwrap()));
            let b = b.unwrap_or_else(|| collapsed(&a));
            if a.closed != b.closed {
                return Err(unsupported(
                    "Open and closed contours require separate collapse/grow pairs",
                ));
            }
            let mut cuts: Vec<f64> = (0..=a.segments.len())
                .map(|i| i as f64 / a.segments.len() as f64)
                .chain((0..=b.segments.len()).map(|i| i as f64 / b.segments.len() as f64))
                .collect();
            cuts.sort_by(f64::total_cmp);
            cuts.dedup();
            commands += cuts.len() + usize::from(a.closed);
            if commands > MAX_SEGMENTS {
                return Err(limit(
                    "Matched interpolation geometry exceeds 4096 commands",
                ));
            }
            rings.push(Matched {
                from: cuts.windows(2).map(|w| section(&a, w[0], w[1])).collect(),
                to: cuts.windows(2).map(|w| section(&b, w[0], w[1])).collect(),
                closed: a.closed,
            });
        }
        if seen_from.len() != from.len() || seen_to.len() != to.len() {
            return Err(invalid(
                "Contour pairs must cover every endpoint contour exactly once",
            ));
        }
        Ok(Self { rings, commands })
    }
    pub fn at(&self, t: f64) -> Geometry {
        let mut commands = Vec::with_capacity(self.commands);
        for r in &self.rings {
            commands.push(PathCommand::Move {
                to: mix_point(r.from[0].curve[0], r.to[0].curve[0], t),
            });
            for (a, b) in r.from.iter().zip(&r.to) {
                let c = std::array::from_fn::<_, 4, _>(|i| mix_point(a.curve[i], b.curve[i], t));
                if a.line && b.line {
                    commands.push(PathCommand::Line { to: c[3] });
                } else {
                    commands.push(PathCommand::Cubic {
                        control1: c[1],
                        control2: c[2],
                        to: c[3],
                    });
                }
            }
            if r.closed {
                commands.push(PathCommand::Close {});
            }
        }
        Geometry::Path { commands }
    }
}
