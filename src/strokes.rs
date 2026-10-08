//! Editable stroke controls, original outline geometry and atomic expansion.
use crate::{Error, model::*};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
mod brush;
mod outline;
pub(crate) use brush::stored_segments as brush_segments;
pub use brush::{
    Brush, Fit as BrushFit, MAX_PLACEMENTS as MAX_BRUSH_PLACEMENTS,
    Orientation as BrushCornerOrientation,
};
pub(crate) use outline::{MAX_OUTLINE_COMMANDS, generated_item_work, generated_work};

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Scaling {
    #[default]
    Object,
    Document,
}
impl Scaling {
    pub fn is_object(&self) -> bool {
        *self == Self::Object
    }
    pub(crate) fn matrix(self, world: Matrix) -> Matrix {
        if self == Self::Document {
            identity()
        } else {
            world
        }
    }
}
fn mapped(g: &Geometry, matrix: Matrix) -> Result<Geometry, Error> {
    let Geometry::Path { mut commands } = crate::primitives::expand(g)? else {
        unreachable!()
    };
    for command in &mut commands {
        match command {
            PathCommand::Move { to } | PathCommand::Line { to } => {
                *to = crate::geometry::map(matrix, *to)
            }
            PathCommand::Cubic {
                control1,
                control2,
                to,
            } => {
                *control1 = crate::geometry::map(matrix, *control1);
                *control2 = crate::geometry::map(matrix, *control2);
                *to = crate::geometry::map(matrix, *to);
            }
            PathCommand::Close {} => {}
        }
    }
    Ok(Geometry::Path { commands })
}
fn evaluated<'a>(
    g: &'a Geometry,
    s: &Stroke,
    world: Matrix,
) -> Result<std::borrow::Cow<'a, Geometry>, Error> {
    Ok(if s.scaling == Scaling::Document {
        std::borrow::Cow::Owned(mapped(g, world)?)
    } else {
        std::borrow::Cow::Borrowed(g)
    })
}
/// Geometry in the declared evaluation space; paint remains in item coordinates.
pub(crate) fn generate_placed(
    g: &Geometry,
    s: &Stroke,
    world: Matrix,
) -> Result<Option<Geometry>, Error> {
    outline::generate(
        evaluated(g, s, world)?.as_ref(),
        s,
        placed_tolerance(s, world)?,
    )
}
/// Conservative Euclidean stretch bound from the induced one/infinity norms.
/// Translation does not affect refinement. The stored tolerance is unchanged.
pub(crate) fn placed_tolerance(s: &Stroke, world: Matrix) -> Result<f64, Error> {
    let [a, b, c, d, _, _] = s.scaling.matrix(world).map(f64::abs);
    let stretch = ((a + c).max(b + d) * (a + b).max(c + d)).sqrt() * OUTLINE_RESOLUTION as f64;
    if !stretch.is_finite() {
        return Err(invalid("Stroke refinement requires a finite placement"));
    }
    Ok(s.curve_tolerance
        .min(default_tolerance() / stretch.max(1.0)))
}
/// Freeze a placed outline back into item coordinates for editable expansion/SVG.
pub(crate) fn generate_local(
    g: &Geometry,
    s: &Stroke,
    world: Matrix,
) -> Result<Option<Geometry>, Error> {
    let result = generate_placed(g, s, world)?;
    if s.scaling == Scaling::Document {
        result
            .map(|g| mapped(&g, crate::geometry::inverse(world)?))
            .transpose()
    } else {
        Ok(result)
    }
}
pub(crate) fn work_placed(g: &Geometry, s: &Stroke, world: Matrix) -> Result<u64, Error> {
    work(evaluated(g, s, world)?.as_ref(), s)
}

/// Shared outline accuracy anticipates the maximum supported raster density.
pub const OUTLINE_RESOLUTION: u32 = 16;
pub fn default_tolerance() -> f64 {
    1.0 / 64.0
}
pub fn is_default_tolerance(value: &f64) -> bool {
    *value == default_tolerance()
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ArrowKind {
    Triangle,
    Chevron,
    Diamond,
    Ellipse,
    Bar,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Arrow {
    pub kind: ArrowKind,
    pub length: f64,
    pub width: f64,
}
pub(crate) fn advanced(stroke: &Stroke) -> bool {
    stroke.scaling == Scaling::Document
        || !stroke.width_profile.is_empty()
        || stroke.start_arrow.is_some()
        || stroke.end_arrow.is_some()
        || stroke.brush.is_some()
}
pub(crate) fn validate_controls(stroke: &Stroke) -> Result<(), Error> {
    brush::validate(stroke)?;
    if !stroke.curve_tolerance.is_finite() || !(1e-7..=1.0).contains(&stroke.curve_tolerance) {
        return Err(invalid(
            "Stroke curve tolerance must be finite in 0.0000001..=1 declared stroke units",
        ));
    }
    let profile = &stroke.width_profile;
    if !profile.is_empty()
        && (!(2..=64).contains(&profile.len())
            || profile[0][0] != 0.0
            || profile.last().unwrap()[0] != 1.0
            || profile.iter().any(|p| {
                !p[0].is_finite()
                    || !p[1].is_finite()
                    || !(0.0..=1.0).contains(&p[0])
                    || !(0.0..=1024.0).contains(&p[1])
                    || stroke.width * p[1] > 1024.0
            })
            || profile.windows(2).any(|w| w[0][0] >= w[1][0]))
    {
        return Err(invalid(
            "Width profiles require 2..64 increasing [position,factor] knots from position 0 to 1, nonnegative factors at most 1024, and resulting widths at most 1024",
        ));
    }
    for arrow in stroke.start_arrow.iter().chain(stroke.end_arrow.iter()) {
        if !arrow.length.is_finite()
            || !arrow.width.is_finite()
            || !(0.001..=1024.0).contains(&arrow.length)
            || !(0.001..=1024.0).contains(&arrow.width)
        {
            return Err(invalid(
                "Arrow length and width must be finite in 0.001..=1024 declared stroke units",
            ));
        }
    }
    Ok(())
}

pub const MAX_INTERVALS: usize = 64;
pub const MAX_DOCUMENT_WORK: u64 = 32_768;
pub const MAX_INSTANCE_WORK: u64 = 131_072;
pub const MAX_RANGE_WORK: u64 = 524_288;
pub const MAX_SVG_COMMANDS: u64 = 131_072;
pub const MAX_SVG_RANGE_COMMANDS: u64 = 262_144;

pub(crate) fn svg_item_work(item: &Item, world: Matrix) -> Result<u64, Error> {
    if let Content::Vector {
        stroke: Some(s), ..
    } = &item.content
        && (advanced(s) || !is_default_tolerance(&s.curve_tolerance))
    {
        generated_item_work(item, world)
    } else {
        Ok(0)
    }
}
pub(crate) fn svg_work(document: &Document) -> Result<u64, Error> {
    let mut count = 0;
    for (i, item) in document.items.iter().enumerate() {
        let world = crate::scene::world_transform(document, i)?;
        count += svg_item_work(item, world)?;
        if let Some(mask) = item.artwork_mask.as_ref().filter(|m| m.enabled) {
            let instance = crate::artwork_masks::instance(document, mask, world)?;
            crate::model::validate(&instance)?;
            for (j, node) in instance.items.iter().enumerate() {
                count += svg_item_work(node, crate::scene::world_transform(&instance, j)?)?;
            }
        }
    }
    Ok(count)
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Dash {
    pub array: Vec<f64>,
    #[serde(default)]
    pub offset: f64,
}
impl Dash {
    pub fn validate(&self) -> Result<(), Error> {
        if self.array.len() > MAX_INTERVALS
            || !self.offset.is_finite()
            || self.offset.abs() > MAX_COORDINATE
            || self
                .array
                .iter()
                .any(|v| !v.is_finite() || (*v != 0.0 && !(0.001..=MAX_COORDINATE).contains(v)))
        {
            return Err(invalid(
                "Dashes require at most 64 intervals, each zero or 0.001..=32768, and a finite offset in -32768..=32768",
            ));
        }
        Ok(())
    }
    fn normalized(&self) -> Option<(Vec<f64>, f64)> {
        if self.array.iter().all(|&v| v == 0.0) {
            return None;
        }
        let mut values = self.array.clone();
        if values.len() % 2 == 1 {
            values.extend_from_within(..);
        }
        let period = values.iter().sum::<f64>();
        Some((values, self.offset.rem_euclid(period)))
    }
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_DOCUMENT", message)
}
pub(crate) fn check_work(work: u64, maximum: u64) -> Result<(), Error> {
    if work > maximum {
        return Err(Error::new(
            "LIMIT_EXCEEDED",
            "Stroke dashing or brush patterns exceed the aggregate placement/interval work limit",
        ));
    }
    Ok(())
}
fn distance(a: Point, b: Point) -> f64 {
    (a[0] - b[0]).hypot(a[1] - b[1])
}
fn contours(g: &Geometry) -> Result<Vec<crate::paths::Contour>, Error> {
    let Geometry::Path { commands } = crate::primitives::expand(g)? else {
        unreachable!()
    };
    Ok(crate::paths::parse(&commands))
}
fn length_upper(c: &crate::paths::Contour) -> f64 {
    let mut length = 0.0;
    for edge in &c.edges {
        length += match edge.controls {
            Some([a, b]) => distance(edge.from, a) + distance(a, b) + distance(b, edge.to),
            None => distance(edge.from, edge.to),
        };
    }
    if c.closed {
        length += distance(c.edges.last().map_or(c.start, |e| e.to), c.start);
    }
    length
}
/// Conservative interval traversal cost, including all contours and hidden items.
pub(crate) fn work(g: &Geometry, s: &Stroke) -> Result<u64, Error> {
    if let Some(brush) = &s.brush {
        brush::validate(s)?;
        return brush::work(g, s, brush);
    }
    let Some(dash) = &s.dash else { return Ok(0) };
    dash.validate()?;
    let Some((array, _)) = dash.normalized() else {
        return Ok(0);
    };
    let period = array.iter().sum::<f64>();
    let mut work = 0;
    for c in contours(g)? {
        // A control-polygon bound, padded for backend coordinate/length rounding.
        // This also covers zero-length intervals and per-contour phase scans.
        let length = length_upper(&c) * 1.01 + (c.edges.len() + 1) as f64;
        let cycles = (length / period).ceil() as u64 + 2;
        work += cycles.saturating_mul(array.len() as u64) + c.edges.len() as u64;
        check_work(work, MAX_DOCUMENT_WORK)?;
    }
    Ok(work)
}
pub(crate) fn document_work(document: &Document) -> Result<u64, Error> {
    let mut total = 0;
    for (i, item) in document.items.iter().enumerate() {
        total += item_work(item, crate::scene::world_transform(document, i)?)?;
    }
    Ok(total)
}
pub(crate) fn item_work(item: &Item, world: Matrix) -> Result<u64, Error> {
    if let Content::Vector {
        geometry,
        stroke: Some(stroke),
        ..
    } = &item.content
    {
        work_placed(geometry, stroke, world)
    } else {
        Ok(0)
    }
}

/// Exact placement-aware preflight includes each independently transformed mask copy.
pub(crate) fn repeated_work(document: &Document) -> Result<(u64, u64), Error> {
    let mut dash = document_work(document)?;
    let mut generated = generated_work(document)?;
    for (i, item) in document.items.iter().enumerate() {
        if let Some(mask) = item.artwork_mask.as_ref().filter(|m| m.enabled) {
            let view = crate::artwork_masks::instance(
                document,
                mask,
                crate::scene::world_transform(document, i)?,
            )?;
            crate::model::validate(&view)?;
            dash += document_work(&view)?;
            generated += generated_work(&view)?;
        }
    }
    Ok((dash, generated))
}

pub(crate) fn expand(
    document: &mut Document,
    index: usize,
    fill_id: &str,
    stroke_id: &str,
) -> Result<serde_json::Value, Error> {
    if fill_id == stroke_id
        || [fill_id, stroke_id]
            .iter()
            .any(|id| !valid_id(id) || document.items.iter().any(|i| &i.id == id))
    {
        return Err(invalid(
            "Stroke expansion requires two distinct valid unused child IDs",
        ));
    }
    let original = document.items[index].clone();
    let Content::Vector {
        geometry,
        fill,
        stroke: Some(stroke),
        fill_rule,
    } = &original.content
    else {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Stroke expansion requires a vector item with a stroke",
        ));
    };
    if stroke.scaling == Scaling::Document
        && (crate::instances::source_owner(document, index)?.is_some()
            || crate::artwork_masks::source_owner(document, index)?.is_some())
    {
        return Err(Error::new(
            "UNSUPPORTED",
            "Document-scaled strokes in reusable source definitions cannot be frozen for all placements; expand a placed independent copy",
        ));
    }
    let outline = generate_local(
        geometry,
        stroke,
        crate::scene::world_transform(document, index)?,
    )?;
    let commands = match &outline {
        Some(Geometry::Path { commands }) => commands.len(),
        _ => 0,
    };
    let child = |id: &str, content: Content| Item {
        hdr_grade: None,
        pixel_warp: None,
        metadata: None,
        id: id.into(),
        name: String::new(),
        visible: true,
        locked: false,
        opacity: 1.0,
        fill_opacity: 1.0,
        coverage: Default::default(),
        effects: vec![],
        blend: BlendMode::Normal,
        transform: identity(),
        parent: Some(original.id.clone()),
        clip_to: None,
        clip: None,
        mask: None,
        artwork_mask: None,
        filters: vec![],
        content,
    };
    let mut children = vec![child(
        fill_id,
        Content::Vector {
            geometry: geometry.clone(),
            fill: fill.clone(),
            stroke: None,
            fill_rule: *fill_rule,
        },
    )];
    let empty = outline.is_none();
    if let Some(geometry) = outline {
        children.push(child(
            stroke_id,
            Content::Vector {
                geometry,
                fill: Some(stroke.color.clone()),
                stroke: None,
                fill_rule: FillRule::Nonzero,
            },
        ));
    }
    document.items[index].content = Content::Group {
        isolated: true,
        role: GroupRole::Group,
        knockout: false,
    };
    document.items.splice(index + 1..index + 1, children);
    Ok(
        serde_json::json!({"fill_id":fill_id,"stroke_id":if empty {None}else{Some(stroke_id)},"empty_stroke":empty,"outline_commands":commands,"curve_tolerance":stroke.curve_tolerance,"evaluated_curve_tolerance":placed_tolerance(stroke, crate::scene::world_transform(document,index)?)?,"outline_resolution":OUTLINE_RESOLUTION,"source_scaling":stroke.scaling,"future_scaling":"filled_geometry_follows_object","geometry":"filled_nonzero_compound_path","centerline_preserved":true}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn refinement_bounds_every_direction_without_changing_saved_controls() {
        let base: Stroke =
            serde_json::from_value(serde_json::json!({"color":[0,0,0,255],"width":2})).unwrap();
        for matrix in [
            [1.0, 0.0, 0.0, 1.0, 0.0, 0.0],
            [1024.0, 0.0, 0.0, 1024.0, -16384.0, 16384.0],
            [8192.0, 8192.0, -8192.0, -8191.0, 6.125, -29993.875],
            [-3.0, 2.0, 1.0, 4.0, 3.0, 5.0],
            [0.001, 0.0, 0.0, 0.001, 0.0, 0.0],
            [32768.0, 0.0, 0.0, 32768.0, 0.0, 0.0],
        ] {
            for declared in [0.0000001, 1.0 / 64.0, 1.0] {
                let mut stroke = base.clone();
                stroke.curve_tolerance = declared;
                let before = stroke.clone();
                let tolerance = placed_tolerance(&stroke, matrix).unwrap();
                assert!(tolerance > 0.0 && tolerance <= declared);
                // Independent directional sweep of the linear map, including
                // reflections and a nearly cancelling high shear.
                for i in 0..4096 {
                    let angle = std::f64::consts::TAU * i as f64 / 4096.0;
                    let (y, x) = angle.sin_cos();
                    let length =
                        (matrix[0] * x + matrix[2] * y).hypot(matrix[1] * x + matrix[3] * y);
                    assert!(
                        tolerance * length * OUTLINE_RESOLUTION as f64
                            <= default_tolerance() * (1.0 + 1e-12)
                    );
                }
                assert_eq!(stroke, before);
                stroke.scaling = Scaling::Document;
                assert_eq!(
                    placed_tolerance(&stroke, matrix).unwrap(),
                    declared.min(default_tolerance() / OUTLINE_RESOLUTION as f64)
                );
            }
        }
        assert_eq!(
            OUTLINE_RESOLUTION,
            4 * crate::render_quality::Antialias::Supersample4.factor()
        );
    }
    #[test]
    fn nonfinite_outline_controls_are_rejected_through_the_library() {
        let base: Stroke =
            serde_json::from_value(serde_json::json!({"color":[0,0,0,255],"width":2})).unwrap();
        for v in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            let mut s = base.clone();
            s.curve_tolerance = v;
            assert!(validate_controls(&s).is_err());
            s = base.clone();
            s.width_profile = vec![[0.0, 1.0], [0.5, v], [1.0, 1.0]];
            assert!(validate_controls(&s).is_err());
            s.width_profile = vec![[0.0, 1.0], [v, 1.0], [1.0, 1.0]];
            assert!(validate_controls(&s).is_err());
            s = base.clone();
            s.end_arrow = Some(Arrow {
                kind: ArrowKind::Triangle,
                length: v,
                width: 2.0,
            });
            assert!(validate_controls(&s).is_err());
            s.end_arrow = Some(Arrow {
                kind: ArrowKind::Triangle,
                length: 2.0,
                width: v,
            });
            assert!(validate_controls(&s).is_err());
        }
    }
    #[test]
    fn nonfinite_dash_controls_are_rejected_through_the_library() {
        for value in [
            f64::NAN,
            f64::INFINITY,
            f64::NEG_INFINITY,
            -1.0,
            f64::MIN_POSITIVE,
        ] {
            assert!(
                Dash {
                    array: vec![value, 2.0],
                    offset: 0.0
                }
                .validate()
                .is_err()
            );
        }
        for offset in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            assert!(
                Dash {
                    array: vec![],
                    offset
                }
                .validate()
                .is_err()
            );
        }
    }
}
