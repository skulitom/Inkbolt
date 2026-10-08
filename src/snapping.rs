//! Deterministic explicit snapping against frozen points, grids and guide lines.
use crate::{
    Error,
    dimensions::{self, Anchor, Unit},
    geometry,
    model::*,
    scene,
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
fn yes() -> bool {
    true
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Mode {
    #[default]
    Together,
    Individual,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Target {
    Point {
        point: Point,
    },
    Grid {
        origin: Point,
        spacing: Point,
        #[serde(default)]
        angle: f64,
    },
    Guide {
        frame_id: String,
        id: String,
    },
    Item {
        id: String,
        #[serde(default)]
        anchor: Anchor,
        #[serde(default)]
        angle: f64,
    },
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Options {
    pub targets: Vec<Target>,
    pub max_distance: f64,
    #[serde(default)]
    pub unit: Unit,
    #[serde(default)]
    pub anchor: Anchor,
    #[serde(default)]
    pub angle: f64,
    #[serde(default)]
    pub mode: Mode,
    #[serde(default = "yes")]
    pub intersections: bool,
}
enum Prepared {
    Point(Point, Value),
    Grid(Point, Point, Matrix),
    Line(Point, Point, Value),
}
fn invalid(s: &str) -> Error {
    Error::new("INVALID_OPERATION", s)
}
fn point(p: Point, f: f64) -> Result<Point, Error> {
    let p = p.map(|v| v * f);
    if p.iter().any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE) {
        return Err(invalid("Snap coordinates exceed logical coordinate limits"));
    }
    Ok(p)
}
fn fixed(d: &Document, id: &str, selected: &[usize]) -> Result<usize, Error> {
    let i = scene::index(d, id)?;
    if std::iter::once(i)
        .chain(scene::ancestors(d, i)?)
        .any(|j| selected.contains(&j))
    {
        return Err(invalid(
            "Snap references must not move with the selected artwork",
        ));
    }
    Ok(i)
}
fn direction(a: Point, b: Point) -> Result<Point, Error> {
    let v = [b[0] - a[0], b[1] - a[1]];
    let length = v[0].hypot(v[1]);
    if !length.is_finite() || length < 1e-10 {
        return Err(invalid("Guide is too short at document precision"));
    }
    Ok(v.map(|x| x / length))
}
fn cross(a: Point, b: Point) -> f64 {
    a[0] * b[1] - a[1] * b[0]
}
fn minus(a: Point, b: Point) -> Point {
    [a[0] - b[0], a[1] - b[1]]
}
fn plus(a: Point, b: Point, t: f64) -> Point {
    [a[0] + b[0] * t, a[1] + b[1] * t]
}
fn nearest(v: f64) -> f64 {
    let lo = v.floor();
    if v - lo <= 0.5 { lo } else { lo + 1.0 }
}
pub(crate) fn apply(
    document: &mut Document,
    ids: &[String],
    options: &Options,
    control: &crate::control::Control,
) -> Result<Value, Error> {
    control.check()?;
    if options.targets.is_empty() || options.targets.len() > 64 {
        return Err(invalid("Snap requires 1..64 explicit targets"));
    }
    let f = options.unit.pixels(document.resolution_ppi);
    let limit = options.max_distance * f;
    if !limit.is_finite() || !(0.0..=MAX_COORDINATE).contains(&limit) {
        return Err(invalid(
            "Snap distance must be finite within 0..32768 logical pixels",
        ));
    }
    let axes = dimensions::basis(options.angle)?;
    let inverse = geometry::inverse(axes)?;
    let selected = scene::selection(document, ids, true)?;
    for &i in &selected {
        scene::check_unlocked(document, i, true)?;
    }
    let evaluated = dimensions::evaluated(document)?;
    let bounds: Vec<_> = ids
        .iter()
        .map(|id| {
            dimensions::projected(&evaluated, scene::index(&evaluated, id)?, axes)?
                .ok_or_else(|| invalid("Selected artwork has no snap bounds").at_item(id))
        })
        .collect::<Result<_, Error>>()?;
    let mut targets = Vec::new();
    for target in &options.targets {
        control.check()?;
        targets.push(match target {
            Target::Point { point: p } => Prepared::Point(point(*p, f)?, json!({"type":"point"})),
            Target::Grid {
                origin,
                spacing,
                angle,
            } => {
                let spacing = spacing.map(|v| v * f);
                if spacing
                    .iter()
                    .any(|v| !v.is_finite() || !(0.001..=MAX_COORDINATE).contains(v))
                {
                    return Err(invalid("Grid spacing must be 0.001..32768 logical pixels"));
                }
                Prepared::Grid(point(*origin, f)?, spacing, dimensions::basis(*angle)?)
            }
            Target::Item { id, anchor, angle } => {
                let reference = fixed(document, id, &selected)?;
                if matches!(document.items[reference].content, Content::Group { .. }) {
                    for &member in &selected {
                        if scene::ancestors(document, member)?.contains(&reference) {
                            return Err(invalid(
                                "Reference group bounds depend on selected artwork",
                            ));
                        }
                    }
                }
                let basis = dimensions::basis(*angle)?;
                let b = dimensions::projected(&evaluated, scene::index(&evaluated, id)?, basis)?
                    .ok_or_else(|| invalid("Reference item has no snap bounds"))?;
                Prepared::Point(
                    geometry::map(geometry::inverse(basis)?, anchor.point(b)),
                    json!({"type":"item","id":id}),
                )
            }
            Target::Guide { frame_id, id } => {
                let i = fixed(document, frame_id, &selected)?;
                let Content::Frame { frame } = &document.items[i].content else {
                    return Err(invalid("Guide reference requires a frame"));
                };
                let guide = frame
                    .guides
                    .iter()
                    .find(|g| g.id == *id)
                    .ok_or_else(|| Error::new("NOT_FOUND", "Guide does not exist"))?;
                let world = scene::world_transform(document, i)?;
                let [a, b] = match guide.axis {
                    crate::layout::Axis::X => {
                        [[guide.position, 0.0], [guide.position, frame.size()[1]]]
                    }
                    crate::layout::Axis::Y => {
                        [[0.0, guide.position], [frame.size()[0], guide.position]]
                    }
                }
                .map(|p| geometry::map(world, p));
                Prepared::Line(
                    a,
                    direction(a, b)?,
                    json!({"type":"guide","frame_id":frame_id,"id":id}),
                )
            }
        });
    }
    let mut intersections = Vec::new();
    let mut parallel = 0;
    if options.intersections {
        for i in 0..targets.len() {
            for j in i + 1..targets.len() {
                if let (Prepared::Line(a, u, _), Prepared::Line(b, v, _)) =
                    (&targets[i], &targets[j])
                {
                    let determinant = cross(*u, *v);
                    if determinant.abs() <= 1e-10 {
                        parallel += 1;
                        continue;
                    }
                    let p = plus(*a, *u, cross(minus(*b, *a), *v) / determinant);
                    if p.iter().all(|v| v.is_finite() && v.abs() <= MAX_COORDINATE) {
                        intersections.push((i, j, p));
                    }
                }
            }
        }
    }
    let sources: Vec<_> = match options.mode {
        Mode::Together => vec![(
            selected.clone(),
            options
                .anchor
                .point(bounds.iter().copied().reduce(scene::union).unwrap()),
        )],
        Mode::Individual => selected
            .iter()
            .zip(bounds)
            .map(|(&i, b)| (vec![i], options.anchor.point(b)))
            .collect(),
    };
    let mut changes = Vec::new();
    for (members, source) in sources {
        control.check()?;
        let source = geometry::map(inverse, source);
        let mut candidates = Vec::new();
        for (i, target) in targets.iter().enumerate() {
            let (p, priority, description) = match target {
                Prepared::Point(p, description) => (*p, 0, description.clone()),
                Prepared::Grid(origin, spacing, basis) => {
                    let local = geometry::map(*basis, minus(source, *origin));
                    let index = [
                        nearest(local[0] / spacing[0]),
                        nearest(local[1] / spacing[1]),
                    ];
                    let p = geometry::map(
                        geometry::inverse(*basis)?,
                        [index[0] * spacing[0], index[1] * spacing[1]],
                    );
                    (
                        plus(*origin, p, 1.0),
                        0,
                        json!({"type":"grid","indices":index}),
                    )
                }
                Prepared::Line(a, v, description) => {
                    let d = minus(source, *a);
                    (
                        plus(*a, *v, d[0] * v[0] + d[1] * v[1]),
                        1,
                        description.clone(),
                    )
                }
            };
            candidates.push((priority, [i, 0], p, description));
        }
        for &(i, j, p) in &intersections {
            candidates.push((
                0,
                [i, j],
                p,
                json!({"type":"guide_intersection","target_indices":[i,j]}),
            ));
        }
        let mut candidates: Vec<_> = candidates
            .into_iter()
            .filter_map(|(priority, key, p, description)| {
                let delta = minus(p, source);
                let squared = delta[0] * delta[0] + delta[1] * delta[1];
                (squared <= limit * limit
                    && p.iter().all(|v| v.is_finite() && v.abs() <= MAX_COORDINATE))
                .then_some((priority, squared, key, p, description))
            })
            .collect();
        candidates.sort_by(|a, b| {
            a.0.cmp(&b.0)
                .then_with(|| a.1.total_cmp(&b.1))
                .then(a.2.cmp(&b.2))
        });
        let member_ids: Vec<_> = members
            .iter()
            .map(|&i| document.items[i].id.clone())
            .collect();
        if let Some((_, distance, key, target, description)) = candidates.first() {
            let delta = minus(*target, source);
            for i in members {
                let inverse = geometry::inverse(scene::parent_transform(document, i)?)?;
                document.items[i].transform[4] += inverse[0] * delta[0] + inverse[2] * delta[1];
                document.items[i].transform[5] += inverse[1] * delta[0] + inverse[3] * delta[1];
            }
            changes.push(json!({"ids":member_ids,"matched":true,"source_document":source,"target_document":target,"delta_document":delta,"distance":distance.sqrt()/f,"target_index":key[0],"target":description}));
        } else {
            changes.push(json!({"ids":member_ids,"matched":false,"source_document":source}));
        }
    }
    Ok(
        json!({"mode":options.mode,"unit":options.unit,"max_distance":options.max_distance,"changes":changes,
        "priority":"points_grids_items_intersections_before_single_guide_projections;then_distance_then_target_order",
        "grid_tie":"lower_index_on_each_axis","excluded_parallel_guide_pairs":parallel,"guide_parallel_threshold":1e-10,
        "reference_state":"frozen_before_operation","bounds":"geometry_only_in_requested_axes","source_geometry_retained":true}),
    )
}
