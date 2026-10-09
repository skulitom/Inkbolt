//! Original editable shape/color sequences with explicit contour correspondence.
use crate::{Error, geometry as geo, model::*};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
mod geometry;

pub const MAX_COUNT: usize = 128;
pub const MAX_DOCUMENT_SPINE_LEAVES: usize = 65536;
fn one() -> f64 {
    1.0
}
fn tolerance() -> f64 {
    0.001
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Endpoint {
    pub geometry: Geometry,
    pub fill: Option<Color>,
    pub stroke: Option<Box<Stroke>>,
    #[serde(default = "one")]
    pub opacity: f64,
    pub anchor: Option<Point>,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Spine {
    pub geometry: Geometry,
    #[serde(default)]
    pub start: f64,
    #[serde(default = "one")]
    pub end: f64,
    #[serde(default)]
    pub reverse: bool,
    #[serde(default)]
    pub normal_offset: f64,
    #[serde(default = "tolerance")]
    pub tolerance: f64,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Orientation {
    #[default]
    Fixed,
    Tangent,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Pair {
    pub from: Option<usize>,
    pub to: Option<usize>,
    #[serde(default)]
    pub to_start: usize,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Spec {
    pub from: Endpoint,
    pub to: Endpoint,
    pub count: usize,
    #[serde(default)]
    pub space: crate::paint::Interpolation,
    #[serde(default)]
    pub fill_rule: FillRule,
    pub spine: Option<Spine>,
    #[serde(default)]
    pub orientation: Orientation,
    #[serde(default)]
    pub reverse_order: bool,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub contours: Vec<Pair>,
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_INTERPOLATION", message)
}
fn unsupported(message: &str) -> Error {
    Error::new("UNSUPPORTED", message)
}
fn limit(message: &str) -> Error {
    Error::new("RESOURCE_LIMIT", message)
}
fn spine_error(mut error: Error) -> Error {
    if error.code == "PATH_TEXT_TANGENT" {
        error.code = "INTERPOLATION_TANGENT";
    }
    error.message = error
        .message
        .replace("Text baseline", "Interpolation spine")
        .replace("A glyph midpoint", "An interpolation sample")
        .replace("baseline tangent", "spine tangent");
    error
}
fn mix(a: f64, b: f64, t: f64) -> f64 {
    if t == 0.0 {
        a
    } else if t == 1.0 {
        b
    } else {
        a * (1.0 - t) + b * t
    }
}
fn mix_point(a: Point, b: Point, t: f64) -> Point {
    [mix(a[0], b[0], t), mix(a[1], b[1], t)]
}
fn anchor(e: &Endpoint) -> Point {
    e.anchor.unwrap_or_else(|| {
        let b = geo::bounds(&e.geometry, identity());
        [(b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0]
    })
}
fn stroke_color(s: &Stroke) -> Result<Color, Error> {
    if let Paint::Solid(c) = s.color {
        Ok(c)
    } else {
        Err(unsupported(
            "Interpolation endpoint strokes require solid colors; expand other painted artwork before creating endpoint geometry",
        ))
    }
}
pub(crate) fn stored(spec: &Spec) -> Result<usize, Error> {
    if !(2..=MAX_COUNT).contains(&spec.count) || spec.contours.len() > 512 {
        return Err(limit(
            "Interpolation requires 2..128 objects and at most 512 contour pairs",
        ));
    }
    let mut commands = 0;
    for e in [&spec.from, &spec.to] {
        commands += geo::validate_geometry(&e.geometry)?;
        if !e.opacity.is_finite()
            || !(0.0..=1.0).contains(&e.opacity)
            || e.anchor
                .is_some_and(|p| p.iter().any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE))
        {
            return Err(invalid(
                "Endpoint opacity must be 0..1 and anchors must be finite within coordinate limits",
            ));
        }
        if let Some(s) = &e.stroke {
            stroke_color(s)?;
            if !s.width.is_finite()
                || !(0.001..=1024.0).contains(&s.width)
                || !s.miter_limit.is_finite()
                || !(1.0..=16.0).contains(&s.miter_limit)
            {
                return Err(invalid(
                    "Endpoint stroke width/miter limits must satisfy ordinary stroke limits",
                ));
            }
            crate::strokes::validate_controls(s)?;
            if let Some(d) = &s.dash {
                d.validate()?;
            }
            commands += crate::strokes::brush_segments(s)?;
        }
    }
    if let Some(s) = &spec.spine {
        if !s.start.is_finite()
            || !s.end.is_finite()
            || s.start < 0.0
            || s.end > 1.0
            || s.start >= s.end
        {
            return Err(invalid("Spine fractions require 0 <= start < end <= 1"));
        }
        commands += crate::path_text::validate(&baseline(s)).map_err(spine_error)?;
    }
    if commands > MAX_SEGMENTS {
        return Err(limit(
            "Interpolation endpoints and spine exceed 4096 stored commands",
        ));
    }
    // A missing stroke fades an otherwise identical style. Two present strokes
    // can change width and solid color; their other controls must agree.
    if let (Some(a), Some(b)) = (&spec.from.stroke, &spec.to.stroke) {
        let mut a = *a.clone();
        let mut b = *b.clone();
        a.width = 1.0;
        b.width = 1.0;
        a.color = Paint::Solid([0; 4]);
        b.color = Paint::Solid([0; 4]);
        if a != b {
            return Err(unsupported(
                "Endpoint strokes must have matching controls apart from width and solid color; expand differing strokes to filled paths first",
            ));
        }
    }
    Ok(commands)
}
fn baseline(s: &Spine) -> crate::path_text::Baseline {
    crate::path_text::Baseline {
        geometry: s.geometry.clone(),
        start_offset: 0.0,
        normal_offset: s.normal_offset,
        flip: s.reverse,
        tolerance: s.tolerance,
    }
}
fn color(a: Color, b: Color, t: f64, space: crate::paint::Interpolation) -> Color {
    if t == 0.0 {
        return a;
    }
    if t == 1.0 {
        return b;
    }
    let alpha = mix(a[3] as f64 / 255.0, b[3] as f64 / 255.0, t);
    let linear = space == crate::paint::Interpolation::LinearRgb;
    let decode = |v: u8| {
        let v = v as f64 / 255.0;
        if !linear {
            v
        } else if v <= 0.04045 {
            v / 12.92
        } else {
            ((v + 0.055) / 1.055).powf(2.4)
        }
    };
    let mut out = [0; 4];
    out[3] = (alpha * 255.0).round().clamp(0.0, 255.0) as u8;
    if alpha > 0.0 {
        for i in 0..3 {
            let v = mix(
                decode(a[i]) * a[3] as f64 / 255.0,
                decode(b[i]) * b[3] as f64 / 255.0,
                t,
            ) / alpha;
            let v = if !linear {
                v
            } else if v <= 0.0031308 {
                v * 12.92
            } else {
                1.055 * v.powf(1.0 / 2.4) - 0.055
            };
            out[i] = (v * 255.0).round().clamp(0.0, 255.0) as u8;
        }
    }
    out
}
fn optional_color(
    a: Option<Color>,
    b: Option<Color>,
    t: f64,
    space: crate::paint::Interpolation,
) -> Option<Color> {
    if t == 0.0 {
        return a;
    }
    if t == 1.0 {
        return b;
    }
    if a.is_none() && b.is_none() {
        None
    } else {
        Some(color(a.unwrap_or([0; 4]), b.unwrap_or([0; 4]), t, space))
    }
}
fn stroke(spec: &Spec, t: f64) -> Result<Option<Box<Stroke>>, Error> {
    let (a, b) = (&spec.from.stroke, &spec.to.stroke);
    if t == 0.0 {
        return Ok(a.clone());
    }
    if t == 1.0 {
        return Ok(b.clone());
    }
    let Some(base) = a.as_ref().or(b.as_ref()) else {
        return Ok(None);
    };
    let mut s = *base.clone();
    s.width = mix(
        a.as_ref().map_or(s.width, |v| v.width),
        b.as_ref().map_or(s.width, |v| v.width),
        t,
    );
    s.color = Paint::Solid(color(
        a.as_ref()
            .map(|v| stroke_color(v))
            .transpose()?
            .unwrap_or([0; 4]),
        b.as_ref()
            .map(|v| stroke_color(v))
            .transpose()?
            .unwrap_or([0; 4]),
        t,
        spec.space,
    ));
    Ok(Some(Box::new(s)))
}
pub(crate) struct Sample {
    pub index: usize,
    pub fraction: f64,
    pub blend: f64,
    pub center: Point,
    pub tangent: Point,
    pub geometry: Geometry,
    pub fill: Option<Color>,
    pub stroke: Option<Box<Stroke>>,
    pub opacity: f64,
}
pub(crate) struct Plan {
    pub samples: Vec<Sample>,
    pub spine: Option<crate::path_text::Report>,
    pub matched_commands: usize,
    pub anchors: [Point; 2],
}
impl Plan {
    pub fn new(spec: &Spec) -> Result<Self, Error> {
        stored(spec)?;
        let anchors = [anchor(&spec.from), anchor(&spec.to)];
        let matching = geometry::Correspondence::new(spec, anchors)?;
        if (spec.count - 2) * matching.commands > MAX_SEGMENTS {
            return Err(limit(
                "Interpolation intermediate geometry exceeds the document command budget",
            ));
        }
        let measured = spec
            .spine
            .as_ref()
            .map(|s| crate::path_text::Measured::new(&baseline(s)).map_err(spine_error))
            .transpose()?;
        let delta = [anchors[1][0] - anchors[0][0], anchors[1][1] - anchors[0][1]];
        let length = delta[0].hypot(delta[1]);
        let straight = if length == 0.0 {
            [1.0, 0.0]
        } else {
            delta.map(|v| v / length)
        };
        let mut samples = Vec::with_capacity(spec.count);
        for index in 0..spec.count {
            let fraction = index as f64 / (spec.count - 1) as f64;
            let t = if spec.reverse_order {
                1.0 - fraction
            } else {
                fraction
            };
            let (center, tangent) = if let (Some(m), Some(s)) = (&measured, &spec.spine) {
                let distance = m.report.length * mix(s.start, s.end, fraction);
                let placement = m.placement(0.0, distance, true).map_err(spine_error)?;
                (
                    [placement.transform[4], placement.transform[5]],
                    placement.tangent,
                )
            } else {
                (mix_point(anchors[0], anchors[1], fraction), straight)
            };
            let u = if spec.orientation == Orientation::Tangent {
                tangent
            } else {
                [1.0, 0.0]
            };
            let (mut geometry, origin) = if t == 0.0 {
                (spec.from.geometry.clone(), anchors[0])
            } else if t == 1.0 {
                (spec.to.geometry.clone(), anchors[1])
            } else {
                (matching.at(t), [0.0, 0.0])
            };
            if center != origin || u != [1.0, 0.0] {
                geometry = crate::primitives::expand(&geometry)?;
                crate::path_text::map_geometry(
                    &mut geometry,
                    [
                        u[0],
                        u[1],
                        -u[1],
                        u[0],
                        center[0] - u[0] * origin[0] + u[1] * origin[1],
                        center[1] - u[1] * origin[0] - u[0] * origin[1],
                    ],
                );
            }
            geo::validate_geometry(&geometry)?;
            samples.push(Sample {
                index,
                fraction,
                blend: t,
                center,
                tangent,
                geometry,
                fill: optional_color(spec.from.fill, spec.to.fill, t, spec.space),
                stroke: stroke(spec, t)?,
                opacity: mix(spec.from.opacity, spec.to.opacity, t),
            });
        }
        Ok(Self {
            samples,
            spine: measured.map(|m| m.report),
            matched_commands: matching.commands,
            anchors,
        })
    }
}
fn group() -> Content {
    Content::Group {
        isolated: true,
        role: GroupRole::Group,
        knockout: false,
    }
}
fn child(id: String, parent: String, s: Sample, rule: FillRule) -> Item {
    Item {
        hdr_grade: None,
        pixel_warp: None,
        metadata: None,
        id,
        name: format!("Interpolation step {}", s.index + 1),
        visible: true,
        locked: false,
        opacity: s.opacity,
        fill_opacity: 1.0,
        coverage: Default::default(),
        effects: vec![],
        blend: BlendMode::Normal,
        transform: identity(),
        parent: Some(parent),
        clip_to: None,
        clip: None,
        mask: None,
        artwork_mask: None,
        filters: vec![],
        content: Content::Vector {
            geometry: s.geometry,
            fill: s.fill.map(Paint::Solid),
            stroke: s.stroke,
            fill_rule: rule,
        },
    }
}
fn generated(item: &Item, used: &mut HashSet<String>) -> Result<(Vec<Item>, usize), Error> {
    let Content::Interpolation {
        interpolation: spec,
    } = &item.content
    else {
        unreachable!()
    };
    let plan = Plan::new(spec)?;
    let leaves = plan.spine.as_ref().map_or(0, |s| s.leaves);
    let mut out = vec![Item {
        content: group(),
        ..item.clone()
    }];
    for sample in plan.samples {
        let prefix = format!(
            "ib-interpolation-{}",
            &crate::assets::sha256(&serde_json::to_vec(&(&item.id, sample.index)).unwrap())[..24]
        );
        let mut id = prefix.clone();
        let mut suffix = 0;
        while !used.insert(id.clone()) {
            suffix += 1;
            id = format!("{prefix}-{suffix}");
        }
        out.push(child(id, item.id.clone(), sample, spec.fill_rule));
    }
    Ok((out, leaves))
}
pub(crate) fn evaluate(d: &Document) -> Result<Option<Document>, Error> {
    if !d
        .items
        .iter()
        .any(|i| matches!(i.content, Content::Interpolation { .. }))
    {
        return Ok(None);
    }
    let mut used: HashSet<_> = d.items.iter().map(|i| i.id.clone()).collect();
    let mut items = vec![];
    let mut leaves = 0;
    for item in &d.items {
        if let Content::Interpolation { interpolation } = &item.content {
            if items
                .len()
                .saturating_add(interpolation.count)
                .saturating_add(1)
                > d.resource_profile.items()
            {
                return Err(limit(
                    "Evaluated interpolation exceeds the document resource-profile item budget",
                ));
            }
            let (generated, cost) = generated(item, &mut used)?;
            leaves += cost;
            if leaves > MAX_DOCUMENT_SPINE_LEAVES {
                return Err(limit(
                    "Interpolation spines exceed 65536 document measurement leaves",
                ));
            }
            items.extend(generated);
        } else {
            items.push(item.clone());
        }
        if items.len() > d.resource_profile.items() {
            return Err(limit(
                "Evaluated interpolation exceeds the document resource-profile item budget",
            ));
        }
    }
    let mut d = d.clone();
    d.items = items;
    d.variants = None;
    Ok(Some(d))
}
pub(crate) fn validate(d: &Document, control: &crate::control::Control) -> Result<(), Error> {
    if let Some(expanded) = evaluate(d)? {
        crate::model::validate_controlled(&expanded, control)?;
    }
    Ok(())
}
pub(crate) fn bounds(spec: &Spec, m: Matrix) -> Result<geo::Bounds, Error> {
    Plan::new(spec)?
        .samples
        .iter()
        .map(|s| geo::bounds(&s.geometry, m))
        .reduce(crate::scene::union)
        .ok_or_else(|| invalid("Interpolation has no objects"))
}
pub(crate) fn expand(d: &mut Document, index: usize) -> Result<serde_json::Value, Error> {
    if !matches!(d.items[index].content, Content::Interpolation { .. }) {
        return Err(invalid("Expansion requires an interpolation item"));
    }
    let mut used = d.items.iter().map(|i| i.id.clone()).collect();
    let (items, _) = generated(&d.items[index], &mut used)?;
    let ids: Vec<_> = items[1..].iter().map(|i| i.id.clone()).collect();
    d.items.splice(index..=index, items);
    Ok(
        serde_json::json!({"created":ids,"count":ids.len(),"source_retained_in_input":true,"appearance":"isolated_group_with_editable_vector_steps"}),
    )
}
pub fn inspect(
    spec: &Spec,
    include_geometry: bool,
    control: &crate::control::Control,
) -> Result<serde_json::Value, Error> {
    control.check()?;
    let document:Document=serde_json::from_value(serde_json::json!({
        "schema_version":2,"id":"interpolation-inspection","kind":"vector","width":1,"height":1,"color_space":"srgb",
        "items":[{"id":"interpolation","content":{"type":"interpolation","interpolation":spec}}]
    })).map_err(|e|invalid(&e.to_string()))?;
    crate::model::validate(&document)?;
    let plan = Plan::new(spec)?;
    control.check()?;
    let samples:Vec<_>=plan.samples.iter().map(|s|serde_json::json!({
        "index":s.index,"fraction":s.fraction,"blend":s.blend,"center":s.center,"tangent":s.tangent,
        "bounds":geo::bounds(&s.geometry,identity()),"fill":s.fill,"stroke":s.stroke,"opacity":s.opacity,
        "geometry":if include_geometry{Some(&s.geometry)}else{None}
    })).collect();
    Ok(
        serde_json::json!({"count":samples.len(),"anchors":plan.anchors,"spine":plan.spine,"matched_commands":plan.matched_commands,
        "samples":samples,"coordinates":"interpolation_local","bounds_semantics":"unclipped_geometry_excluding_stroke"}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn nonfinite_library_controls_and_coordinate_overflow_fail_before_generation() {
        let base: Spec = serde_json::from_value(serde_json::json!({
            "from":{"geometry":{"shape":"rect","x":0,"y":0,"width":1,"height":1},"fill":[0,0,0,255]},
            "to":{"geometry":{"shape":"rect","x":2,"y":0,"width":1,"height":1},"fill":[255,255,255,255]},
            "count":3
        })).unwrap();
        for value in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            let mut spec = base.clone();
            spec.from.opacity = value;
            assert!(Plan::new(&spec).is_err());
            let mut spec = base.clone();
            spec.to.anchor = Some([value, 0.0]);
            assert!(Plan::new(&spec).is_err());
            let mut spec = base.clone();
            spec.spine = Some(Spine {
                geometry: spec.from.geometry.clone(),
                start: value,
                end: 1.0,
                reverse: false,
                normal_offset: 0.0,
                tolerance: 0.001,
            });
            assert!(Plan::new(&spec).is_err());
            spec.spine.as_mut().unwrap().start = 0.0;
            spec.spine.as_mut().unwrap().normal_offset = value;
            assert!(Plan::new(&spec).is_err());
        }
        let mut spec = base;
        spec.from.anchor = Some([-32768.0, 0.0]);
        spec.to.anchor = Some([32768.0, 0.0]);
        spec.reverse_order = true;
        assert!(Plan::new(&spec).is_err());
    }
}
