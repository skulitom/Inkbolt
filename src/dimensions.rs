//! Original dimension inspection and explicit physical-unit geometry edits.
use crate::{Error, control::Control, geometry, model::*, scene};
use num_rational::BigRational as R;
use num_traits::{ToPrimitive, Zero};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
mod measure;
pub const MAX_WORK: usize = 65_536;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Unit {
    #[default]
    Px,
    Pt,
    Pc,
    Mm,
    Cm,
    In,
}
impl Unit {
    pub(crate) fn exact(self, ppi: f64) -> R {
        let n = |a: i64, b: i64| R::new(a.into(), b.into());
        match self {
            Self::Px => n(1, 1),
            Self::Pt => measure::r(ppi) / n(72, 1),
            Self::Pc => measure::r(ppi) / n(6, 1),
            Self::Mm => measure::r(ppi) / n(254, 10),
            Self::Cm => measure::r(ppi) / n(254, 100),
            Self::In => measure::r(ppi),
        }
    }
    pub(crate) fn pixels(self, ppi: f64) -> f64 {
        self.exact(ppi).to_f64().unwrap()
    }
}
fn tolerance() -> f64 {
    0.0001
}
fn area_tolerance() -> f64 {
    0.000001
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Options {
    pub ids: Vec<String>,
    #[serde(default)]
    pub unit: Unit,
    #[serde(default)]
    pub angle: f64,
    #[serde(default = "tolerance")]
    pub tolerance: f64,
    #[serde(default = "area_tolerance")]
    pub area_tolerance: f64,
    #[serde(default)]
    pub bounds_only: bool,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(default, deny_unknown_fields)]
pub struct Anchor {
    pub x: crate::layout::Anchor,
    pub y: crate::layout::Anchor,
}
impl Default for Anchor {
    fn default() -> Self {
        Self {
            x: crate::layout::Anchor::Center,
            y: crate::layout::Anchor::Center,
        }
    }
}
impl Anchor {
    pub(crate) fn point(self, b: geometry::Bounds) -> Point {
        let at = |a: crate::layout::Anchor, i: usize| match a {
            crate::layout::Anchor::Min => b[i],
            crate::layout::Anchor::Center => (b[i] + b[i + 2]) * 0.5,
            crate::layout::Anchor::Max => b[i + 2],
        };
        [at(self.x, 0), at(self.y, 1)]
    }
}
pub(crate) fn basis(angle: f64) -> Result<Matrix, Error> {
    if !angle.is_finite() || angle.abs() > 360_000.0 {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Measurement angle must be finite within +/-360000 degrees",
        ));
    }
    let reduced = angle.rem_euclid(360.0);
    let (s, c) = match reduced {
        0.0 => (0.0, 1.0),
        90.0 => (1.0, 0.0),
        180.0 => (0.0, -1.0),
        270.0 => (-1.0, 0.0),
        _ => (angle.to_radians()).sin_cos(),
    };
    Ok([c, -s, s, c, 0.0, 0.0])
}
pub(crate) fn evaluated(d: &Document) -> Result<Document, Error> {
    let mut out = d.clone();
    if let Some(v) = crate::instances::evaluate(&out)? {
        out = v;
    }
    if let Some(v) = crate::warps::evaluate(&out)? {
        out = v;
    }
    if let Some(v) = crate::repeats::evaluate(&out)? {
        out = v;
    }
    if let Some(v) = crate::interpolation::evaluate(&out)? {
        out = v;
    }
    Ok(out)
}
pub(crate) fn projected(
    d: &Document,
    i: usize,
    basis: Matrix,
) -> Result<Option<geometry::Bounds>, Error> {
    if matches!(d.items[i].content, Content::Group { .. }) {
        let mut out = None;
        for c in scene::children(d, Some(&d.items[i].id)) {
            if let Some(b) = projected(d, c, basis)? {
                out = Some(out.map_or(b, |a| scene::union(a, b)));
            }
        }
        return Ok(out);
    }
    if matches!(
        d.items[i].content,
        Content::ComponentSource {} | Content::MaskSource {} | Content::Adjustment { .. }
    ) {
        return Ok(None);
    }
    let mut item = d.items[i].clone();
    item.transform = geometry::multiply(basis, scene::world_transform(d, i)?);
    if let Some(g) = crate::text::flow::geometry(d, &item.content)? {
        return Ok(Some(geometry::bounds(&g, item.transform)));
    }
    geometry::item_bounds(&item).map(Some)
}
fn geometry_of(d: &Document, item: &Item) -> Result<Option<(Geometry, &'static str)>, Error> {
    if let Some(p) = crate::pixel_warps::plan(item)? {
        return Ok(Some((p.geometry(), "deformed_image_boundary")));
    }
    if let Some(g) = crate::text::flow::geometry(d, &item.content)? {
        return Ok(Some((g, "story_frame_not_glyph_ink")));
    }
    let value = match &item.content {
        Content::Vector { geometry, .. } | Content::WorkPath { geometry, .. } => {
            (geometry.clone(), "authored_geometry")
        }
        Content::Frame { frame } => (frame.geometry(), "container_frame"),
        Content::Text { frame } => (
            crate::text::frame_geometry(frame),
            "text_frame_not_glyph_ink",
        ),
        Content::Image { width, height, .. } => (
            Geometry::Rect {
                x: 0.0,
                y: 0.0,
                width: *width,
                height: *height,
            },
            "image_frame",
        ),
        Content::Samples { grid } => (grid.geometry(), "sample_grid_frame"),
        Content::StoredSamples { grid } => (grid.geometry(), "stored_sample_grid_frame"),
        Content::Raw { raw } => (raw.geometry(), "raw_sensor_frame"),
        Content::Raster { width, height, .. } | Content::Fill { width, height, .. } => (
            Geometry::Rect {
                x: 0.0,
                y: 0.0,
                width: *width as f64,
                height: *height as f64,
            },
            "pixel_or_fill_frame",
        ),
        _ => return Ok(None),
    };
    Ok(Some(value))
}
fn leaves(d: &Document, i: usize, out: &mut Vec<usize>) {
    if matches!(d.items[i].content, Content::Group { .. }) {
        for c in scene::children(d, Some(&d.items[i].id)) {
            leaves(d, c, out);
        }
    } else if !matches!(
        d.items[i].content,
        Content::ComponentSource {} | Content::MaskSource {} | Content::Adjustment { .. }
    ) {
        out.push(i);
    }
}
pub fn inspect(document: &Document, options: &Options, control: &Control) -> Result<Value, Error> {
    control.check()?;
    crate::validate(document)?;
    let axes = basis(options.angle)?;
    if !options.tolerance.is_finite()
        || !(0.000001..=100.0).contains(&options.tolerance)
        || !options.area_tolerance.is_finite()
        || !(0.000000001..=10000.0).contains(&options.area_tolerance)
    {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Length tolerance must be 1e-6..100 units; area tolerance must be 1e-9..10000 square units",
        ));
    }
    scene::selection(document, &options.ids, true)?;
    let d = evaluated(document)?;
    let selected = scene::selection(&d, &options.ids, true)?;
    let factor = options.unit.exact(document.resolution_ppi);
    let factor2 = &factor * &factor;
    let tolerance = measure::r(options.tolerance);
    let area_tolerance = measure::r(options.area_tolerance);
    let mut budget = measure::Budget { used: 0, control };
    let mut items = Vec::new();
    let inverse = geometry::inverse(axes)?;
    for i in selected {
        control.check()?;
        let b = projected(&d, i, axes)?.ok_or_else(|| {
            Error::new(
                "INVALID_OPERATION",
                "Item has no measurable geometry bounds",
            )
            .at_item(&d.items[i].id)
        })?;
        let f = factor.to_f64().unwrap();
        let mut record = json!({"id":d.items[i].id,"bounds":b.map(|v|v/f),"width":(b[2]-b[0])/f,"height":(b[3]-b[1])/f,
            "corners_document":([[b[0],b[1]],[b[2],b[1]],[b[2],b[3]],[b[0],b[3]]].map(|p|geometry::map(inverse,p)))});
        if !options.bounds_only {
            let mut chosen = Vec::new();
            leaves(&d, i, &mut chosen);
            let each = &tolerance * &factor / R::from_integer((2 * chosen.len().max(1)).into());
            let mut lower = R::zero();
            let mut upper = R::zero();
            let mut signed = Some((R::zero(), R::zero()));
            let mut components = Vec::new();
            for j in chosen {
                let (g, kind) = geometry_of(&d, &d.items[j])?.ok_or_else(|| {
                    Error::new("UNSUPPORTED", "No boundary metric for selected content")
                        .at_item(&d.items[j].id)
                })?;
                let m = measure::measure(&g, scene::world_transform(&d, j)?, &each, &mut budget)
                    .map_err(|e| e.at_item(&d.items[j].id))?;
                lower += &m.lower;
                upper += &m.upper;
                signed = match (signed, m.area) {
                    (Some((a, b)), Some((c, d))) => Some((a + c, b + d)),
                    _ => None,
                };
                components.push(json!({"id":d.items[j].id,"boundary":kind,"contours":m.contours,"closed_contours":m.closed}));
            }
            record["boundary_length"] =
                measure::interval(lower / &factor, upper / &factor, Some(&tolerance))?;
            record["signed_area"] = match signed {
                Some((a, b)) => {
                    measure::interval(a / &factor2, b / &factor2, Some(&area_tolerance))?
                }
                None => Value::Null,
            };
            record["components"] = json!(components);
        }
        items.push(record);
    }
    control.check()?;
    Ok(
        json!({"document_id":document.id,"revision":document.revision,"unit":options.unit,"resolution_ppi":document.resolution_ppi,
        "pixels_per_unit_exact":factor.to_string(),"angle":options.angle,"basis":axes,"items":items,"work_units":budget.used,
        "length_tolerance":options.tolerance,"area_tolerance":options.area_tolerance,
        "bounds_semantics":"unclipped_geometry_in_declared_rotated_axes;excludes_strokes_effects_and_glyph_ink",
        "length_semantics":"sum_of_authored_open_or_closed_boundaries;closed_contours_include_closing_segment",
        "area_semantics":"signed_algebraic_integral_of_closed_contours;null_if_any_contour_open;not_filled_union_area",
        "metric_certificate":"exact_binary64_rationals;Bezier_chord_control_polygon_and_ellipse_chord_tangent_enclosures;outward_rounded_output",
        "generated_geometry":"component_warp_repeat_and_interpolation_evaluation_uses_their_declared_contracts","source_changed":false}),
    )
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Resize {
    pub width: Option<f64>,
    pub height: Option<f64>,
    #[serde(default)]
    pub unit: Unit,
    #[serde(default)]
    pub angle: f64,
    #[serde(default)]
    pub anchor: Anchor,
    #[serde(default)]
    pub preserve_aspect: bool,
}
pub(crate) fn resize(d: &mut Document, id: &str, options: &Resize) -> Result<Value, Error> {
    let i = scene::index(d, id)?;
    scene::check_unlocked(d, i, true)?;
    let axes = basis(options.angle)?;
    let f = options.unit.pixels(d.resolution_ppi);
    if (options.width.is_none() && options.height.is_none())
        || (options.preserve_aspect && options.width.is_some() && options.height.is_some())
    {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Specify at least one dimension, or exactly one when preserving aspect",
        ));
    }
    if options
        .width
        .into_iter()
        .chain(options.height)
        .any(|v| !v.is_finite() || v * f < 0.001 || v * f > MAX_COORDINATE * 2.0)
    {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Requested dimensions must be finite within 0.001..65536 logical pixels",
        ));
    }
    let evaluated = evaluated(d)?;
    let j = scene::index(&evaluated, id)?;
    let b = projected(&evaluated, j, axes)?
        .ok_or_else(|| Error::new("INVALID_OPERATION", "Item has no dimension bounds"))?;
    let size = [b[2] - b[0], b[3] - b[1]];
    if size.iter().any(|v| *v <= 0.0) {
        return Err(Error::new(
            "UNSUPPORTED",
            "Resizing requires two nonzero geometry dimensions",
        ));
    }
    let mut scales = [
        options.width.map_or(1.0, |v| v * f / size[0]),
        options.height.map_or(1.0, |v| v * f / size[1]),
    ];
    if options.preserve_aspect {
        scales = [if options.width.is_some() {
            scales[0]
        } else {
            scales[1]
        }; 2];
    }
    let p = options.anchor.point(b);
    let local = [
        scales[0],
        0.0,
        0.0,
        scales[1],
        p[0] * (1.0 - scales[0]),
        p[1] * (1.0 - scales[1]),
    ];
    let world = geometry::multiply(geometry::inverse(axes)?, geometry::multiply(local, axes));
    geometry::validate_matrix(world)?;
    let parent = scene::parent_transform(d, i)?;
    d.items[i].transform = geometry::multiply(
        geometry::inverse(parent)?,
        geometry::multiply(world, scene::world_transform(d, i)?),
    );
    Ok(
        json!({"unit":options.unit,"angle":options.angle,"before_dimensions":size.map(|v|v/f),"requested_width":options.width,"requested_height":options.height,
        "scale":scales,"anchor_document":geometry::map(geometry::inverse(axes)?,p),"world_transform":world,"source_geometry_retained":true}),
    )
}
