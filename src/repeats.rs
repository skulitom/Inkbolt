//! Original editable closed-motif layouts with combined, seam-safe coverage.
use crate::{Error, geometry as geo, model::*};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

pub const MAX_COPIES: usize = 128;
fn half() -> f64 {
    0.5
}
fn turn() -> f64 {
    360.0
}
fn yes() -> bool {
    true
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Mirror {
    #[default]
    None,
    Columns,
    Rows,
    Both,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Axis {
    #[default]
    Rows,
    Columns,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum HexOrientation {
    #[default]
    Pointy,
    Flat,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Orientation {
    #[default]
    Fixed,
    Radial,
    Tangent,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Layout {
    Grid {
        columns: usize,
        rows: usize,
        step: Point,
        #[serde(default)]
        mirror: Mirror,
    },
    Brick {
        columns: usize,
        rows: usize,
        step: Point,
        #[serde(default)]
        axis: Axis,
        #[serde(default = "half")]
        offset: f64,
        #[serde(default)]
        mirror: Mirror,
    },
    Hex {
        columns: usize,
        rows: usize,
        radius: f64,
        #[serde(default)]
        orientation: HexOrientation,
        #[serde(default)]
        mirror: Mirror,
    },
    Radial {
        count: usize,
        radius: f64,
        #[serde(default)]
        start_angle: f64,
        #[serde(default = "turn")]
        sweep: f64,
        #[serde(default = "yes")]
        closed: bool,
        #[serde(default)]
        orientation: Orientation,
    },
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Spec {
    pub geometry: Geometry,
    pub fill: Paint,
    #[serde(default)]
    pub fill_rule: FillRule,
    pub layout: Layout,
    #[serde(default)]
    pub origin: Point,
    pub anchor: Option<Point>,
    #[serde(default = "identity")]
    pub motif_transform: Matrix,
    #[serde(default = "identity")]
    pub transform: Matrix,
}
#[derive(Clone, Debug, Serialize)]
pub struct Placement {
    pub index: usize,
    pub column: Option<usize>,
    pub row: Option<usize>,
    pub center: Point,
    pub matrix: Matrix,
    pub reflected: bool,
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_REPEAT", message)
}
fn limit(message: &str) -> Error {
    Error::new("RESOURCE_LIMIT", message)
}
fn point(p: Point) -> Result<(), Error> {
    if p.iter().any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE) {
        return Err(invalid("Repeat coordinates must be finite within +/-32768"));
    }
    Ok(())
}
fn radius(r: f64) -> Result<(), Error> {
    if !r.is_finite() || !(0.001..=MAX_COORDINATE).contains(&r) {
        return Err(invalid("Repeat radius must be in 0.001..=32768"));
    }
    Ok(())
}
fn step(s: Point) -> Result<(), Error> {
    point(s)?;
    if s.iter().any(|v| v.abs() < 0.001) {
        return Err(invalid("Repeat steps must have magnitude at least 0.001"));
    }
    Ok(())
}
fn size(columns: usize, rows: usize) -> Result<usize, Error> {
    if columns == 0 || rows == 0 || columns.saturating_mul(rows) > MAX_COPIES {
        return Err(limit("Repeat layout requires 1..128 total copies"));
    }
    Ok(columns * rows)
}
pub fn count(layout: &Layout) -> Result<usize, Error> {
    match *layout {
        Layout::Grid {
            columns,
            rows,
            step: s,
            ..
        } => {
            step(s)?;
            size(columns, rows)
        }
        Layout::Brick {
            columns,
            rows,
            step: s,
            offset,
            ..
        } => {
            step(s)?;
            if !offset.is_finite() || !(0.0..=1.0).contains(&offset) {
                return Err(invalid("Brick offset must be in 0..=1"));
            }
            size(columns, rows)
        }
        Layout::Hex {
            columns,
            rows,
            radius: r,
            ..
        } => {
            radius(r)?;
            size(columns, rows)
        }
        Layout::Radial {
            count,
            radius: r,
            start_angle,
            sweep,
            closed,
            ..
        } => {
            radius(r)?;
            if !start_angle.is_finite()
                || start_angle.abs() > 360.0
                || !sweep.is_finite()
                || sweep == 0.0
                || sweep.abs() > 360.0
            {
                return Err(invalid(
                    "Radial angles must be finite within +/-360 and sweep must be nonzero",
                ));
            }
            if (closed && sweep.abs() != 360.0) || (!closed && (sweep.abs() >= 360.0 || count < 2))
            {
                return Err(invalid(
                    "Closed radial layouts require a full turn; open arcs require at least two copies and less than a full turn",
                ));
            }
            size(count, 1)
        }
    }
}
fn direction(degrees: f64) -> Point {
    match degrees.rem_euclid(360.0) {
        0.0 => [1., 0.],
        90.0 => [0., 1.],
        180.0 => [-1., 0.],
        270.0 => [0., -1.],
        a => {
            let (s, c) = a.to_radians().sin_cos();
            [c, s]
        }
    }
}
fn translation(p: Point) -> Matrix {
    [1., 0., 0., 1., p[0], p[1]]
}
fn determinant(m: Matrix) -> f64 {
    m[0] * m[3] - m[1] * m[2]
}
pub fn placements(spec: &Spec) -> Result<Vec<Placement>, Error> {
    let n = count(&spec.layout)?;
    geo::validate_geometry(&spec.geometry)?;
    point(spec.origin)?;
    geo::validate_matrix(spec.motif_transform)?;
    geo::validate_matrix(spec.transform)?;
    let b = geo::bounds(&spec.geometry, identity());
    let anchor = spec
        .anchor
        .unwrap_or([(b[0] + b[2]) / 2., (b[1] + b[3]) / 2.]);
    point(anchor)?;
    let source = geo::multiply(spec.motif_transform, translation(anchor.map(|v| -v)));
    let mut out = Vec::with_capacity(n);
    for index in 0..n {
        let (position, rotation, column, row, mirror) = match spec.layout {
            Layout::Radial {
                count,
                radius,
                start_angle,
                sweep,
                closed,
                orientation,
            } => {
                let denominator = if closed { count } else { count - 1 };
                let angle = start_angle + sweep * (index as f64 / denominator as f64);
                let u = direction(angle);
                let rotation = match orientation {
                    Orientation::Fixed => [1., 0.],
                    Orientation::Radial => u,
                    Orientation::Tangent => direction(angle + if sweep > 0. { 90. } else { -90. }),
                };
                (u.map(|v| v * radius), rotation, None, None, Mirror::None)
            }
            ref grid => {
                let (columns, s, axis, offset, mirror) = match *grid {
                    Layout::Grid {
                        columns,
                        step,
                        mirror,
                        ..
                    } => (columns, step, Axis::Rows, 0., mirror),
                    Layout::Brick {
                        columns,
                        step,
                        axis,
                        offset,
                        mirror,
                        ..
                    } => (columns, step, axis, offset, mirror),
                    Layout::Hex {
                        columns,
                        radius,
                        orientation,
                        mirror,
                        ..
                    } => {
                        let long = 3f64.sqrt() * radius;
                        let short = 1.5 * radius;
                        match orientation {
                            HexOrientation::Pointy => {
                                (columns, [long, short], Axis::Rows, 0.5, mirror)
                            }
                            HexOrientation::Flat => {
                                (columns, [short, long], Axis::Columns, 0.5, mirror)
                            }
                        }
                    }
                    _ => unreachable!(),
                };
                let c = index % columns;
                let r = index / columns;
                let position = match axis {
                    Axis::Rows => [(c as f64 + (r % 2) as f64 * offset) * s[0], r as f64 * s[1]],
                    Axis::Columns => [c as f64 * s[0], (r as f64 + (c % 2) as f64 * offset) * s[1]],
                };
                (position, [1., 0.], Some(c), Some(r), mirror)
            }
        };
        let sx = if matches!(mirror, Mirror::Columns | Mirror::Both) && column.unwrap() % 2 == 1 {
            -1.
        } else {
            1.
        };
        let sy = if matches!(mirror, Mirror::Rows | Mirror::Both) && row.unwrap() % 2 == 1 {
            -1.
        } else {
            1.
        };
        let center = [spec.origin[0] + position[0], spec.origin[1] + position[1]];
        let pose = [
            rotation[0] * sx,
            rotation[1] * sx,
            -rotation[1] * sy,
            rotation[0] * sy,
            center[0],
            center[1],
        ];
        let matrix = geo::multiply(spec.transform, geo::multiply(pose, source));
        geo::validate_matrix(matrix)?;
        out.push(Placement {
            index,
            column,
            row,
            center: geo::map(spec.transform, center),
            reflected: determinant(matrix) < 0.,
            matrix,
        });
    }
    Ok(out)
}
fn original(spec: &Spec) -> Result<Vec<crate::paths::Contour>, Error> {
    geo::validate_geometry(&spec.geometry)?;
    let Geometry::Path { commands } = crate::primitives::expand(&spec.geometry)? else {
        unreachable!()
    };
    let contours = crate::paths::parse(&commands);
    if contours.iter().any(|c| !c.closed) {
        return Err(Error::new(
            "UNSUPPORTED",
            "Repeated fill motifs require closed contours; expand strokes to closed filled geometry first",
        ));
    }
    Ok(contours)
}
pub(crate) fn stored(spec: &Spec) -> Result<usize, Error> {
    count(&spec.layout)?;
    original(spec)?;
    geo::validate_geometry(&spec.geometry)
}
fn mapped(contours: &[crate::paths::Contour], m: Matrix) -> Vec<PathCommand> {
    let mut cs = contours.to_vec();
    for c in &mut cs {
        c.start = geo::map(m, c.start);
        for e in &mut c.edges {
            e.from = geo::map(m, e.from);
            e.to = geo::map(m, e.to);
            e.controls = e.controls.map(|v| v.map(|p| geo::map(m, p)));
        }
        if determinant(m) < 0. {
            // Start at the former terminal anchor, preserving the implicit
            // closing edge without adding a segment or changing curve loci.
            c.start = c.edges.last().unwrap().to;
            c.edges.reverse();
            for e in &mut c.edges {
                std::mem::swap(&mut e.from, &mut e.to);
                e.controls = e.controls.map(|[a, b]| [b, a]);
            }
        }
    }
    crate::paths::emit(&cs)
}
pub(crate) fn geometry(spec: &Spec) -> Result<Geometry, Error> {
    let contours = original(spec)?;
    let commands_per_copy = crate::paths::emit(&contours).len();
    let n = count(&spec.layout)?;
    if commands_per_copy.saturating_mul(n) > MAX_SEGMENTS {
        return Err(limit("Repeated geometry exceeds 4096 generated commands"));
    }
    let mut commands = Vec::with_capacity(commands_per_copy * n);
    for p in placements(spec)? {
        commands.extend(mapped(&contours, p.matrix));
    }
    let g = Geometry::Path { commands };
    geo::validate_geometry(&g)?;
    Ok(g)
}
pub(crate) fn content(spec: &Spec) -> Result<Content, Error> {
    Ok(Content::Vector {
        geometry: geometry(spec)?,
        fill: Some(spec.fill.clone()),
        stroke: None,
        fill_rule: spec.fill_rule,
    })
}
pub(crate) fn evaluate(document: &Document) -> Result<Option<Document>, Error> {
    if !document
        .items
        .iter()
        .any(|i| matches!(i.content, Content::Repeat { .. }))
    {
        return Ok(None);
    }
    let mut d = document.clone();
    let mut commands = 0;
    for i in &mut d.items {
        if let Content::Repeat { repeat } = &i.content {
            let content = content(repeat)?;
            if let Content::Vector { geometry, .. } = &content {
                commands += geo::validate_geometry(geometry)?;
            }
            if commands > MAX_SEGMENTS {
                return Err(limit(
                    "Repeat layouts exceed 4096 aggregate generated commands",
                ));
            }
            i.content = content;
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
pub fn inspect(
    spec: &Spec,
    include_geometry: bool,
    control: &crate::control::Control,
) -> Result<serde_json::Value, Error> {
    control.check()?;
    let d:Document=serde_json::from_value(serde_json::json!({"schema_version":2,"id":"repeat-inspection","kind":"vector","width":1,"height":1,"color_space":"srgb","items":[{"id":"repeat","content":{"type":"repeat","repeat":spec}}]})).map_err(|e|invalid(&e.to_string()))?;
    crate::model::validate(&d)?;
    let placements = placements(spec)?;
    let geometry = geometry(spec)?;
    let Geometry::Path { commands } = &geometry else {
        unreachable!()
    };
    let result = serde_json::json!({"count":placements.len(),"placements":placements,"bounds":geo::bounds(&geometry,identity()),"commands":commands.len(),"geometry":include_geometry.then_some(&geometry),"coordinates":"repeat_local","coverage":"combined_fill_once","winding":"reflections_preserve_authored_winding","source_retained":true});
    control.check()?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn nonfinite_controls_are_rejected_by_direct_library_calls() {
        let base:Spec=serde_json::from_value(serde_json::json!({"geometry":{"shape":"rect","x":0,"y":0,"width":1,"height":1},"fill":[0,0,0,255],"layout":{"type":"brick","rows":2,"columns":2,"step":[4,4]}})).unwrap();
        for value in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            let mut s = base.clone();
            s.origin[0] = value;
            assert!(geometry(&s).is_err());
            let mut s = base.clone();
            s.anchor = Some([value, 0.]);
            assert!(geometry(&s).is_err());
            let mut s = base.clone();
            s.motif_transform[0] = value;
            assert!(geometry(&s).is_err());
            let mut s = base.clone();
            if let Layout::Brick { offset, .. } = &mut s.layout {
                *offset = value;
            }
            assert!(geometry(&s).is_err());
            let mut s = base.clone();
            s.layout = Layout::Radial {
                count: 3,
                radius: 4.,
                start_angle: value,
                sweep: 360.,
                closed: true,
                orientation: Orientation::Fixed,
            };
            assert!(geometry(&s).is_err());
        }
    }
}
