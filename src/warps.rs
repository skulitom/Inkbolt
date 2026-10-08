//! Original retained vector deformation with exact rational expansion certificates.
use crate::{Error, geometry as geo, model::*};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
mod exact;
pub(crate) fn projective_coefficients(
    corners: &[Point; 4],
) -> Result<[num_rational::BigRational; 9], Error> {
    for p in corners {
        finite_point(*p)?;
    }
    exact::homography(corners)
}
pub const MAX_MAPS: usize = 8;
pub const MAX_DEGREE: usize = 128;
pub const MAX_WORK: usize = 2_000_000;
pub const MAX_BITS: u64 = 8192;
pub const MAX_DEPTH: usize = 24;
pub const MAX_INPUT_EDGES: usize = 256;
pub const MAX_SAMPLES: usize = 256;
fn tolerance() -> f64 {
    0.01
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Map {
    Affine {
        matrix: Matrix,
    },
    Perspective {
        domain: [f64; 4],
        corners: [Point; 4],
    },
    Envelope {
        domain: [f64; 4],
        points: [[Point; 4]; 4],
    },
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Spec {
    pub geometry: Geometry,
    pub fill: Option<Paint>,
    pub stroke: Option<Box<Stroke>>,
    #[serde(default)]
    pub fill_rule: FillRule,
    pub maps: Vec<Map>,
    #[serde(default = "tolerance")]
    pub tolerance: f64,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Grid {
    pub domain: [f64; 4],
    pub columns: usize,
    pub rows: usize,
}
#[derive(Clone, Debug, Serialize)]
pub struct Segment {
    pub contour: usize,
    pub edge: usize,
    pub parameter: [f64; 2],
    pub from: Point,
    pub to: Point,
    pub error_bound: f64,
    pub degree: usize,
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_WARP", message)
}
fn limit(message: &str) -> Error {
    Error::new("RESOURCE_LIMIT", message)
}
fn finite_point(p: Point) -> Result<(), Error> {
    if p.iter().any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE) {
        return Err(invalid("Warp coordinates must be finite within +/-32768"));
    }
    Ok(())
}
fn domain(d: [f64; 4]) -> Result<(), Error> {
    finite_point([d[0], d[1]])?;
    if d[2..]
        .iter()
        .any(|v| !v.is_finite() || !(0.001..=MAX_COORDINATE).contains(v))
    {
        return Err(invalid("Warp domain dimensions must be in 0.001..=32768"));
    }
    finite_point([d[0] + d[2], d[1] + d[3]])
}
pub(crate) fn stored(spec: &Spec) -> Result<usize, Error> {
    if spec.maps.is_empty() || spec.maps.len() > MAX_MAPS {
        return Err(limit("Warps require 1..8 ordered maps"));
    }
    if !spec.tolerance.is_finite() || !(0.000001..=1.0).contains(&spec.tolerance) {
        return Err(invalid(
            "Warp tolerance must be in 0.000001..=1 local units",
        ));
    }
    let mut commands = geo::validate_geometry(&spec.geometry)?;
    for map in &spec.maps {
        match map {
            Map::Affine { matrix } => geo::validate_matrix(*matrix)?,
            Map::Perspective { domain: d, corners } => {
                domain(*d)?;
                for p in corners {
                    finite_point(*p)?;
                }
                commands += 4;
            }
            Map::Envelope { domain: d, points } => {
                domain(*d)?;
                for row in points {
                    for p in row {
                        finite_point(*p)?;
                    }
                }
                commands += 16;
            }
        }
    }
    if let Some(s) = &spec.stroke {
        commands += crate::strokes::brush_segments(s)?;
    }
    if commands > MAX_SEGMENTS {
        return Err(limit(
            "Warp source and map controls exceed 4096 stored commands",
        ));
    }
    Ok(commands)
}
pub(crate) struct Plan {
    pub geometry: Geometry,
    pub segments: Vec<Segment>,
}
impl Plan {
    fn new(spec: &Spec, budget: &mut exact::Budget) -> Result<Self, Error> {
        stored(spec)?;
        let maps = exact::prepare(&spec.maps, budget)?;
        let Geometry::Path { commands } = crate::primitives::expand(&spec.geometry)? else {
            unreachable!()
        };
        let contours = crate::paths::parse(&commands);
        if spec.fill.is_some() && contours.iter().any(|c| !c.closed) {
            return Err(Error::new(
                "UNSUPPORTED",
                "Filled warp contours must be explicitly closed; open centerlines require fill:null",
            ));
        }
        let mut segments = vec![];
        let mut commands = vec![];
        let mut edges = 0;
        for (ci, mut contour) in contours.into_iter().enumerate() {
            let end = contour.edges.last().unwrap().to;
            if contour.closed && end != contour.start {
                contour.edges.push(crate::paths::Edge {
                    from: end,
                    to: contour.start,
                    controls: None,
                });
            }
            edges += contour.edges.len();
            if edges > MAX_INPUT_EDGES {
                return Err(limit("Warp source exceeds 256 curve/line edges"));
            }
            for (ei, edge) in contour.edges.iter().enumerate() {
                let start = segments.len();
                let mapped = exact::apply(exact::source(edge), &maps, budget)?;
                exact::flatten(mapped, spec.tolerance, ci, ei, budget, &mut segments)?;
                if ei == 0 {
                    commands.push(PathCommand::Move {
                        to: segments[start].from,
                    });
                }
                commands.extend(
                    segments[start..]
                        .iter()
                        .map(|s| PathCommand::Line { to: s.to }),
                );
            }
            if contour.closed {
                commands.push(PathCommand::Close {});
            }
            if commands.len() > MAX_SEGMENTS {
                return Err(limit("Warp expansion exceeds 4096 stored commands"));
            }
        }
        let geometry = Geometry::Path { commands };
        geo::validate_geometry(&geometry)?;
        Ok(Self { geometry, segments })
    }
}
pub(crate) fn plan(spec: &Spec) -> Result<Plan, Error> {
    Plan::new(spec, &mut exact::Budget::default())
}
fn vector(spec: &Spec, geometry: Geometry) -> Content {
    Content::Vector {
        geometry,
        fill: spec.fill.clone(),
        stroke: spec.stroke.clone(),
        fill_rule: spec.fill_rule,
    }
}
pub(crate) fn content(spec: &Spec) -> Result<Content, Error> {
    Ok(vector(spec, plan(spec)?.geometry))
}
pub(crate) fn evaluate(document: &Document) -> Result<Option<Document>, Error> {
    if !document
        .items
        .iter()
        .any(|i| matches!(i.content, Content::Warp { .. }))
    {
        return Ok(None);
    }
    let mut d = document.clone();
    let mut budget = exact::Budget::default();
    let mut commands = 0;
    for i in &mut d.items {
        if let Content::Warp { warp } = &i.content {
            let p = Plan::new(warp, &mut budget)?;
            commands += geo::validate_geometry(&p.geometry)?;
            if commands > MAX_SEGMENTS {
                return Err(limit("Warps exceed 4096 aggregate generated commands"));
            }
            i.content = vector(warp, p.geometry);
        }
    }
    d.variants = None;
    Ok(Some(d))
}
pub(crate) fn validate(document: &Document) -> Result<(), Error> {
    if let Some(d) = evaluate(document)? {
        crate::model::validate(&d)?;
    }
    Ok(())
}
fn grid(spec: &Spec, grid: &Grid, budget: &mut exact::Budget) -> Result<Plan, Error> {
    domain(grid.domain)?;
    if !(1..=16).contains(&grid.columns) || !(1..=16).contains(&grid.rows) {
        return Err(limit("Warp grid requires 1..16 intervals per axis"));
    }
    let [x, y, w, h] = grid.domain;
    let mut commands = vec![];
    for c in 0..=grid.columns {
        let u = x + w * (c as f64 / grid.columns as f64);
        commands.extend([
            PathCommand::Move { to: [u, y] },
            PathCommand::Line { to: [u, y + h] },
        ]);
    }
    for r in 0..=grid.rows {
        let v = y + h * (r as f64 / grid.rows as f64);
        commands.extend([
            PathCommand::Move { to: [x, v] },
            PathCommand::Line { to: [x + w, v] },
        ]);
    }
    Plan::new(
        &Spec {
            geometry: Geometry::Path { commands },
            fill: None,
            stroke: None,
            fill_rule: FillRule::Nonzero,
            maps: spec.maps.clone(),
            tolerance: spec.tolerance,
        },
        budget,
    )
}
pub fn inspect(
    spec: &Spec,
    samples: &[Point],
    requested_grid: Option<&Grid>,
    include_geometry: bool,
    include_segments: bool,
    control: &crate::control::Control,
) -> Result<serde_json::Value, Error> {
    control.check()?;
    if samples.len() > MAX_SAMPLES {
        return Err(limit("Warp inspection exceeds 256 sample points"));
    }
    for p in samples {
        finite_point(*p)?;
    }
    let mut budget = exact::Budget::controlled(control.clone());
    let plan = Plan::new(spec, &mut budget)?;
    // Style and ordinary generated-document checks share the real vector contract.
    let d:Document=serde_json::from_value(serde_json::json!({"schema_version":2,"id":"warp-inspection","kind":"vector","width":1,"height":1,"color_space":"srgb","items":[{"id":"warp","content":vector(spec,plan.geometry.clone())}]})).map_err(|e|invalid(&e.to_string()))?;
    crate::model::validate(&d)?;
    let maps = exact::prepare(&spec.maps, &mut budget)?;
    let mapped = samples
        .iter()
        .map(|p| {
            exact::point(*p, &maps, &mut budget).map(|q| serde_json::json!({"source":p,"mapped":q}))
        })
        .collect::<Result<Vec<_>, _>>()?;
    let grid = requested_grid
        .map(|g| grid(spec, g, &mut budget))
        .transpose()?;
    let Geometry::Path { commands } = &plan.geometry else {
        unreachable!()
    };
    control.check()?;
    Ok(
        serde_json::json!({"maps":spec.maps,"samples":mapped,"geometry":include_geometry.then_some(&plan.geometry),
        "segments":include_segments.then_some(&plan.segments),"commands":commands.len(),"segments_count":plan.segments.len(),
        "maximum_error_bound":plan.segments.iter().map(|s|s.error_bound).fold(0f64,f64::max),"tolerance":spec.tolerance,
        "grid":grid.map(|p|serde_json::json!({"geometry":p.geometry,"segments":p.segments,"maximum_error_bound":p.segments.iter().map(|s|s.error_bound).fold(0f64,f64::max)})),
        "bounds":geo::bounds(&plan.geometry,identity()),"work":budget.used,"coordinates":"warp_local",
        "certificate":"exact_rational_homogeneous_bernstein_vs_encoded_parameter_chord",
        "source_interpretation":"ordinary_line_cubic_primitive_expansion","appearance":"paint_and_stroke_after_geometry_deformation",
        "bounds_semantics":"expanded_geometry_excluding_stroke_and_clipping","source_retained":true}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn direct_library_rejects_nonfinite_source_maps_and_tolerances() {
        let base: Spec = serde_json::from_value(serde_json::json!({"geometry":{"shape":"rect","x":0,"y":0,"width":1,"height":1},"fill":[0,0,0,255],"maps":[{"type":"perspective","domain":[0,0,1,1],"corners":[[0,0],[1,0],[1,1],[0,1]]}]})).unwrap();
        for v in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            let mut s = base.clone();
            s.tolerance = v;
            assert!(plan(&s).is_err());
            let mut s = base.clone();
            if let Map::Perspective { corners, .. } = &mut s.maps[0] {
                corners[0][0] = v;
            }
            assert!(plan(&s).is_err());
            let mut s = base.clone();
            if let Map::Perspective { domain, .. } = &mut s.maps[0] {
                domain[2] = v;
            }
            assert!(plan(&s).is_err());
            let mut s = base.clone();
            s.maps = vec![Map::Affine {
                matrix: [1., 0., 0., 1., v, 0.],
            }];
            assert!(plan(&s).is_err());
            let mut s = base.clone();
            s.maps = vec![Map::Envelope {
                domain: [0., 0., 1., 1.],
                points: [[[v, 0.]; 4]; 4],
            }];
            assert!(plan(&s).is_err());
            let mut s = base.clone();
            if let Geometry::Rect { x, .. } = &mut s.geometry {
                *x = v;
            }
            assert!(plan(&s).is_err());
        }
    }
}
