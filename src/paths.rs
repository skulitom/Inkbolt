//! Explicit path edits over revision-scoped command indices.
use crate::{Error, geometry, model::*, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::HashSet;
fn yes() -> bool {
    true
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Space {
    #[default]
    Local,
    World,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Anchor {
    pub command_index: usize,
    pub to: Point,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Join {
    #[default]
    Coincident,
    Bridge,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Action {
    Convert {},
    Simplify {
        tolerance: f64,
        #[serde(default)]
        space: Space,
        #[serde(default)]
        contours: Vec<usize>,
        #[serde(default = "crate::simplify::default_span")]
        max_span: usize,
    },
    Anchors {
        points: Vec<Anchor>,
        #[serde(default)]
        space: Space,
        #[serde(default = "yes")]
        move_handles: bool,
    },
    Handles {
        command_index: usize,
        control1: Option<Point>,
        control2: Option<Point>,
        #[serde(default)]
        space: Space,
    },
    Split {
        command_index: usize,
        t: f64,
    },
    Reverse {
        #[serde(default)]
        contours: Vec<usize>,
    },
    Join {
        first: usize,
        second: usize,
        #[serde(default)]
        mode: Join,
        #[serde(default)]
        close: bool,
    },
}
fn error(message: &str) -> Error {
    Error::new("INVALID_OPERATION", message)
}
fn endpoint(c: &PathCommand) -> Option<Point> {
    match c {
        PathCommand::Move { to } | PathCommand::Line { to } | PathCommand::Cubic { to, .. } => {
            Some(*to)
        }
        PathCommand::Close {} => None,
    }
}
fn lerp(a: Point, b: Point, t: f64) -> Point {
    std::array::from_fn(|i| a[i] + (b[i] - a[i]) * t)
}
#[derive(Clone)]
pub(crate) struct Edge {
    pub from: Point,
    pub to: Point,
    pub controls: Option<[Point; 2]>,
}
#[derive(Clone)]
pub(crate) struct Contour {
    pub start: Point,
    pub edges: Vec<Edge>,
    pub closed: bool,
}
pub(crate) fn parse(commands: &[PathCommand]) -> Vec<Contour> {
    let mut contours = Vec::new();
    let mut current: Option<Contour> = None;
    for c in commands {
        match c {
            PathCommand::Move { to } => {
                if let Some(c) = current.take() {
                    contours.push(c);
                }
                current = Some(Contour {
                    start: *to,
                    edges: vec![],
                    closed: false,
                });
            }
            PathCommand::Close {} => {
                let mut c = current.take().expect("validated contour");
                c.closed = true;
                contours.push(c);
            }
            PathCommand::Line { to } | PathCommand::Cubic { to, .. } => {
                let contour = current.as_mut().expect("validated contour");
                let from = contour.edges.last().map_or(contour.start, |e| e.to);
                let controls = if let PathCommand::Cubic {
                    control1, control2, ..
                } = c
                {
                    Some([*control1, *control2])
                } else {
                    None
                };
                contour.edges.push(Edge {
                    from,
                    to: *to,
                    controls,
                });
            }
        }
    }
    if let Some(c) = current {
        contours.push(c);
    }
    contours
}
pub(crate) fn emit(contours: &[Contour]) -> Vec<PathCommand> {
    let mut out = Vec::new();
    for c in contours {
        out.push(PathCommand::Move { to: c.start });
        for e in &c.edges {
            out.push(match e.controls {
                Some([control1, control2]) => PathCommand::Cubic {
                    control1,
                    control2,
                    to: e.to,
                },
                None => PathCommand::Line { to: e.to },
            });
        }
        if c.closed {
            out.push(PathCommand::Close {});
        }
    }
    out
}
pub(crate) fn edit(
    document: &mut Document,
    index: usize,
    action: &Action,
) -> Result<Option<Value>, Error> {
    let world = scene::world_transform(document, index)?;
    let (Content::Vector { geometry: g, .. } | Content::WorkPath { geometry: g, .. }) =
        &document.items[index].content
    else {
        return Err(error("Path editing requires vector content or a work path"));
    };
    if matches!(action, Action::Convert {}) {
        let expanded = crate::primitives::expand(g)?;
        let (Content::Vector { geometry, .. } | Content::WorkPath { geometry, .. }) =
            &mut document.items[index].content
        else {
            unreachable!()
        };
        *geometry = expanded;
        return Ok(None);
    }
    let Geometry::Path { commands } = g else {
        return Err(error(
            "Convert the primitive to a path before editing anchors or topology",
        ));
    };
    let mut commands = commands.clone();
    let mut details = None;
    let local = |point: Point, space: Space| -> Result<Point, Error> {
        if point
            .iter()
            .any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE * 2.0)
        {
            return Err(invalid(
                "Path edit coordinates must be finite and within world bounds",
            ));
        }
        Ok(match space {
            Space::Local => point,
            Space::World => geometry::map(geometry::inverse(world)?, point),
        })
    };
    match action {
        Action::Convert {} => unreachable!(),
        Action::Simplify {
            tolerance,
            space,
            contours,
            max_span,
        } => {
            let metric = if matches!(space, Space::World) {
                world
            } else {
                identity()
            };
            let filled = matches!(
                &document.items[index].content,
                Content::Vector { fill: Some(_), .. } | Content::WorkPath { .. }
            );
            let (output, report) =
                crate::simplify::run(&commands, *tolerance, metric, contours, *max_span, filled)?;
            commands = output;
            details = Some(report);
        }
        Action::Anchors {
            points,
            space,
            move_handles,
        } => {
            if points.is_empty() || points.len() > MAX_SEGMENTS {
                return Err(error(
                    "Anchor edit requires 1..=4096 unique command indices",
                ));
            }
            let mut seen = HashSet::new();
            for anchor in points {
                let i = anchor.command_index;
                if !seen.insert(i) {
                    return Err(error("Anchor command indices must be unique"));
                }
                let old = commands.get(i).and_then(endpoint).ok_or_else(|| {
                    error("Anchor index must identify a move, line or cubic endpoint")
                })?;
                let new = local(anchor.to, *space)?;
                let delta = [new[0] - old[0], new[1] - old[1]];
                let shift = |p: &mut Point| {
                    p[0] += delta[0];
                    p[1] += delta[1];
                };
                match &mut commands[i] {
                    PathCommand::Move { to } | PathCommand::Line { to } => *to = new,
                    PathCommand::Cubic { to, control2, .. } => {
                        *to = new;
                        if *move_handles {
                            shift(control2);
                        }
                    }
                    _ => unreachable!(),
                }
                if *move_handles
                    && let Some(PathCommand::Cubic { control1, .. }) = commands.get_mut(i + 1)
                {
                    shift(control1);
                }
            }
        }
        Action::Handles {
            command_index,
            control1,
            control2,
            space,
        } => {
            if control1.is_none() && control2.is_none() {
                return Err(error("Supply at least one cubic handle"));
            }
            let Some(PathCommand::Cubic {
                control1: a,
                control2: b,
                ..
            }) = commands.get_mut(*command_index)
            else {
                return Err(error("Handle index must identify a cubic command"));
            };
            if let Some(p) = control1 {
                *a = local(*p, *space)?;
            }
            if let Some(p) = control2 {
                *b = local(*p, *space)?;
            }
        }
        Action::Split { command_index, t } => {
            if !t.is_finite() || *t <= 0.0 || *t >= 1.0 {
                return Err(error(
                    "Split parameter must be finite and strictly between 0 and 1",
                ));
            }
            let i = *command_index;
            let c = commands
                .get(i)
                .ok_or_else(|| error("Split command index is out of range"))?;
            if !matches!(c, PathCommand::Line { .. } | PathCommand::Cubic { .. }) {
                return Err(error("Split requires a line or cubic segment"));
            }
            let start = commands
                .get(i.wrapping_sub(1))
                .and_then(endpoint)
                .ok_or_else(|| error("Segment lacks a preceding anchor"))?;
            let replacement = match c {
                PathCommand::Line { to } => vec![
                    PathCommand::Line {
                        to: lerp(start, *to, *t),
                    },
                    c.clone(),
                ],
                PathCommand::Cubic {
                    control1,
                    control2,
                    to,
                } => {
                    let a = lerp(start, *control1, *t);
                    let b = lerp(*control1, *control2, *t);
                    let c = lerp(*control2, *to, *t);
                    let d = lerp(a, b, *t);
                    let e = lerp(b, c, *t);
                    let middle = lerp(d, e, *t);
                    vec![
                        PathCommand::Cubic {
                            control1: a,
                            control2: d,
                            to: middle,
                        },
                        PathCommand::Cubic {
                            control1: e,
                            control2: c,
                            to: *to,
                        },
                    ]
                }
                _ => unreachable!(),
            };
            commands.splice(i..=i, replacement);
        }
        Action::Reverse { contours: selected } => {
            let mut contours = parse(&commands);
            let selected = if selected.is_empty() {
                (0..contours.len()).collect::<Vec<_>>()
            } else {
                selected.clone()
            };
            let mut seen = HashSet::new();
            for i in selected {
                if !seen.insert(i) {
                    return Err(error("Contour indices must be unique"));
                }
                let c = contours
                    .get_mut(i)
                    .ok_or_else(|| error("Contour index is out of range"))?;
                let end = c.edges.last().unwrap().to;
                if c.closed && end != c.start {
                    c.edges.push(Edge {
                        from: end,
                        to: c.start,
                        controls: None,
                    });
                }
                if !c.closed {
                    c.start = end;
                }
                c.edges = c
                    .edges
                    .iter()
                    .rev()
                    .map(|e| Edge {
                        from: e.to,
                        to: e.from,
                        controls: e.controls.map(|[a, b]| [b, a]),
                    })
                    .collect();
                if c.closed
                    && c.edges.len() > 1
                    && c.edges
                        .last()
                        .is_some_and(|e| e.controls.is_none() && e.to == c.start)
                {
                    c.edges.pop();
                }
            }
            commands = emit(&contours);
        }
        Action::Join {
            first,
            second,
            mode,
            close,
        } => {
            let contours = parse(&commands);
            if first == second {
                return Err(error("Join requires two distinct open contours"));
            }
            let a = contours
                .get(*first)
                .ok_or_else(|| error("First contour index is out of range"))?;
            let b = contours
                .get(*second)
                .ok_or_else(|| error("Second contour index is out of range"))?;
            if a.closed || b.closed {
                return Err(error("Join requires two open contours"));
            }
            let mut joined = a.clone();
            let end = a.edges.last().unwrap().to;
            if end != b.start {
                if matches!(mode, Join::Coincident) {
                    return Err(error(
                        "Coincident join requires exactly equal endpoints; use bridge for an explicit connecting line",
                    ));
                }
                joined.edges.push(Edge {
                    from: end,
                    to: b.start,
                    controls: None,
                });
            }
            joined.edges.extend(b.edges.clone());
            joined.closed = *close;
            let mut next = Vec::new();
            for (i, c) in contours.into_iter().enumerate() {
                if i == (*first).min(*second) {
                    next.push(joined.clone());
                }
                if i != *first && i != *second {
                    next.push(c);
                }
            }
            commands = emit(&next);
        }
    }
    let path = Geometry::Path { commands };
    geometry::validate_geometry(&path)?;
    let (Content::Vector { geometry, .. } | Content::WorkPath { geometry, .. }) =
        &mut document.items[index].content
    else {
        unreachable!()
    };
    *geometry = path;
    Ok(details)
}
pub(crate) fn anchors(document: &Document, index: usize) -> Result<Vec<Value>, Error> {
    if matches!(
        &document.items[index].content,
        Content::WorkPath {
            geometry: Geometry::Compound { .. },
            ..
        }
    ) {
        return crate::work_paths::component_anchors(document, index);
    }
    let (Content::Vector {
        geometry: Geometry::Path { commands },
        ..
    }
    | Content::WorkPath {
        geometry: Geometry::Path { commands },
        ..
    }) = &document.items[index].content
    else {
        return Ok(vec![]);
    };
    let world = scene::world_transform(document, index)?;
    Ok(geometry_anchors(commands, world))
}
pub(crate) fn geometry_anchors(commands: &[PathCommand], world: Matrix) -> Vec<Value> {
    let mut contour = 0usize;
    let mut count = 0;
    let mut result = Vec::new();
    for (i, c) in commands.iter().enumerate() {
        if matches!(c, PathCommand::Move { .. }) {
            if !result.is_empty() {
                contour += 1;
            }
            count = 0;
        }
        if let Some(to) = endpoint(c) {
            let controls = if let PathCommand::Cubic {
                control1, control2, ..
            } = c
            {
                Some(
                    json!({"control1":control1,"control2":control2,"world_control1":geometry::map(world,*control1),"world_control2":geometry::map(world,*control2)}),
                )
            } else {
                None
            };
            result.push(json!({"command_index":i,"contour_index":contour,"anchor_index":count,"local":to,"world":geometry::map(world,to),"incoming_segment_handles":controls}));
            count += 1;
        }
    }
    result
}
