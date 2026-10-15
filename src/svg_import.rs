//! Bounded, original SVG-to-document mapping using a public XML parser.
mod arcs;
mod definitions;
mod insertion;
pub use definitions::{MAX_DEFINITIONS, MAX_REFERENCE_DEPTH};
pub use insertion::InsertFontBinding;
pub(crate) use insertion::insert;
mod labels;
mod masking;
mod styles;
pub use labels::{FaceStyle, FontBinding};
mod numbers;
use crate::{Error, geometry, model::*};
use numbers::{invalid, length, number, unsupported};
use roxmltree::Node;
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, HashSet},
    fs::File,
    io::Read,
    path::PathBuf,
};

pub use crate::limits::svg_import::MAX_BYTES;
pub use crate::limits::svg_import::MAX_LARGE_BYTES;
pub use crate::limits::svg_import::MAX_LARGE_NODES;
pub use crate::limits::svg_import::MAX_NODES;
const NS: &str = "http://www.w3.org/2000/svg";
const PROPERTIES: &[&str] = &[
    "fill",
    "fill-opacity",
    "fill-rule",
    "stroke",
    "stroke-opacity",
    "stroke-width",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-miterlimit",
    "stroke-dasharray",
    "stroke-dashoffset",
    "color",
    "opacity",
    "display",
    "visibility",
    "isolation",
    "color-interpolation",
    "clip-path",
    "clip-rule",
    "stop-color",
    "stop-opacity",
    "mask",
    "mask-type",
    "mask-mode",
];

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Source {
    Text { text: String },
    File { source_path: PathBuf },
}

#[derive(Clone)]
struct Style {
    fill: String,
    stroke: String,
    color: Color,
    fill_opacity: f64,
    stroke_opacity: f64,
    width: f64,
    rule: FillRule,
    cap: Cap,
    join: Join,
    miter: f64,
    dash: crate::strokes::Dash,
    visible: bool,
    clip_rule: FillRule,
    space: crate::paint::Interpolation,
    stop_color: String,
    stop_opacity: f64,
    text: labels::LabelStyle,
    mask: Option<String>,
    mask_mode: Option<crate::artwork_masks::Mode>,
    mask_type: crate::artwork_masks::Mode,
}
impl Default for Style {
    fn default() -> Self {
        Self {
            fill: "black".into(),
            stroke: "none".into(),
            color: [0, 0, 0, 255],
            fill_opacity: 1.0,
            stroke_opacity: 1.0,
            width: 1.0,
            rule: FillRule::Nonzero,
            cap: Cap::Butt,
            join: Join::Miter,
            // SVG input defaults remain independent of engine authoring defaults.
            miter: 4.0,
            dash: crate::strokes::Dash {
                array: vec![],
                offset: 0.0,
            },
            visible: true,
            clip_rule: FillRule::Nonzero,
            space: crate::paint::Interpolation::Srgb,
            stop_color: "black".into(),
            stop_opacity: 1.0,
            text: Default::default(),
            mask: None,
            mask_mode: None,
            mask_type: crate::artwork_masks::Mode::Luminance,
        }
    }
}
fn unit_interval(s: &str) -> Result<f64, Error> {
    let n = number(s)?;
    if !(0.0..=1.0).contains(&n) {
        return Err(unsupported("Opacity must be a number in 0..1"));
    }
    Ok(n)
}
fn color(s: &str) -> Result<Color, Error> {
    let s = s.trim();
    if let Some(h) = s.strip_prefix('#') {
        if !h.is_ascii() || !h.bytes().all(|c| c.is_ascii_hexdigit()) {
            return Err(invalid("Invalid hexadecimal color"));
        }
        let hex = if h.len() == 3 {
            h.chars().flat_map(|c| [c, c]).collect::<String>()
        } else {
            h.to_owned()
        };
        if hex.len() != 6 {
            return Err(unsupported(
                "Hexadecimal colors require three or six digits",
            ));
        }
        return Ok([
            u8::from_str_radix(&hex[0..2], 16).unwrap(),
            u8::from_str_radix(&hex[2..4], 16).unwrap(),
            u8::from_str_radix(&hex[4..6], 16).unwrap(),
            255,
        ]);
    }
    if let Some(v) = s.strip_prefix("rgb(").and_then(|s| s.strip_suffix(')')) {
        let parts = v.split(',').map(str::trim).collect::<Vec<_>>();
        if parts.len() != 3 {
            return Err(unsupported(
                "rgb() requires three comma-separated integer or percentage components",
            ));
        }
        let percentages = parts[0].ends_with('%');
        let mut rgba = [0, 0, 0, 255];
        for (i, part) in parts.iter().enumerate() {
            if part.ends_with('%') != percentages {
                return Err(invalid("Mixed rgb() component units"));
            }
            let v = number(if percentages {
                &part[..part.len() - 1]
            } else {
                part
            })?;
            if percentages {
                if !(0.0..=100.0).contains(&v) {
                    return Err(unsupported("RGB percentages must be in 0..100"));
                }
                rgba[i] = (v * 255.0 / 100.0).round() as u8;
            } else {
                if !(0.0..=255.0).contains(&v) || v.fract() != 0.0 {
                    return Err(unsupported("RGB bytes must be integers in 0..255"));
                }
                rgba[i] = v as u8;
            }
        }
        return Ok(rgba);
    }
    let rgb = match s.to_ascii_lowercase().as_str() {
        "black" => 0x000000,
        "silver" => 0xc0c0c0,
        "gray" => 0x808080,
        "white" => 0xffffff,
        "maroon" => 0x800000,
        "red" => 0xff0000,
        "purple" => 0x800080,
        "fuchsia" => 0xff00ff,
        "green" => 0x008000,
        "lime" => 0x00ff00,
        "olive" => 0x808000,
        "yellow" => 0xffff00,
        "navy" => 0x000080,
        "blue" => 0x0000ff,
        "teal" => 0x008080,
        "aqua" => 0x00ffff,
        "transparent" => return Ok([0; 4]),
        _ => return Err(unsupported(format!("Unsupported solid color: {s}"))),
    };
    Ok([(rgb >> 16) as u8, (rgb >> 8) as u8, rgb as u8, 255])
}
fn paint(s: &str, opacity: f64, current: Color) -> Result<Option<Paint>, Error> {
    if definitions::reference(s)?.is_some() {
        // All references resolve after definitions and geometry are collected.
        return Ok(Some(Paint::Solid([0; 4])));
    }
    if s == "none" {
        return Ok(None);
    }
    let mut c = if s == "currentColor" {
        current
    } else {
        color(s)?
    };
    c[3] = (f64::from(c[3]) * opacity).round() as u8;
    Ok(Some(Paint::Solid(c)))
}
fn properties<'a>(
    node: Node<'a, 'a>,
    extra: &[&str],
    styles: &'a styles::Sheet,
) -> Result<BTreeMap<&'a str, &'a str>, Error> {
    let mut props = BTreeMap::new();
    for a in node.attributes() {
        if a.name() == "mask-mode" {
            return Err(unsupported(
                "mask-mode is supported as a CSS property, not an SVG attribute",
            ));
        }
        if a.namespace() == Some("http://www.w3.org/XML/1998/namespace") && a.name() == "space" {
            props.insert("xml:space", a.value().trim());
            continue;
        }
        if a.namespace().is_some()
            && !(extra.contains(&"href")
                && a.name() == "href"
                && a.namespace() == Some("http://www.w3.org/1999/xlink"))
        {
            return Err(unsupported(format!(
                "Namespaced attribute {} is not supported",
                a.name()
            )));
        }
        if PROPERTIES.contains(&a.name()) || labels::PROPERTIES.contains(&a.name()) {
            props.insert(a.name(), a.value().trim());
        } else if !["id", "class", "style", "transform"].contains(&a.name())
            && !extra.contains(&a.name())
        {
            return Err(unsupported(format!(
                "Attribute {} on <{}> is not supported",
                a.name(),
                node.tag_name().name()
            )));
        }
    }
    if props.get("mask") == Some(&"inherit") {
        props.insert("mask-mode", "inherit");
    }
    styles.apply(node, &mut props)?;
    Ok(props)
}
fn styled(parent: &Style, p: &BTreeMap<&str, &str>) -> Result<Style, Error> {
    let mut s = parent.clone();
    s.text = labels::styled(&parent.text, p)?;
    // These stop properties do not inherit unless explicitly requested.
    s.stop_color = "black".into();
    s.stop_opacity = 1.0;
    s.mask = None;
    s.mask_mode = None;
    s.mask_type = crate::artwork_masks::Mode::Luminance;
    for (&k, &v) in p {
        if labels::PROPERTIES.contains(&k) || k == "xml:space" {
            continue;
        }
        if v == "inherit" {
            if ["opacity", "display", "isolation", "clip-path"].contains(&k) {
                return Err(unsupported(format!(
                    "Explicit inherit is not supported for {k}"
                )));
            }
            if k == "stop-color" {
                s.stop_color = parent.stop_color.clone();
            }
            if k == "stop-opacity" {
                s.stop_opacity = parent.stop_opacity;
            }
            if k == "mask" {
                s.mask = parent.mask.clone();
            }
            if k == "mask-mode" {
                s.mask_mode = parent.mask_mode;
            }
            if k == "mask-type" {
                s.mask_type = parent.mask_type;
            }
            continue;
        }
        match k {
            "mask" => {
                s.mask = if v == "none" {
                    None
                } else {
                    Some(
                        definitions::reference(v)?
                            .ok_or_else(|| {
                                unsupported("Masks require one local url(#id) reference or none")
                            })?
                            .to_owned(),
                    )
                };
            }
            "mask-mode" => s.mask_mode = masking::mode(v, true)?,
            "mask-type" => s.mask_type = masking::mode(v, false)?.unwrap(),
            "fill" => s.fill = v.to_owned(),
            "stroke" => s.stroke = v.to_owned(),
            "color" => {
                s.color = if v == "currentColor" {
                    parent.color
                } else {
                    color(v)?
                }
            }
            "fill-opacity" => s.fill_opacity = unit_interval(v)?,
            "stroke-opacity" => s.stroke_opacity = unit_interval(v)?,
            "stop-opacity" => s.stop_opacity = unit_interval(v)?,
            "stop-color" => s.stop_color = v.to_owned(),
            "clip-path" => {
                if v != "none" && definitions::reference(v)?.is_none() {
                    return Err(unsupported(
                        "clip-path requires a local url(#id) reference or none",
                    ));
                }
            }
            "stroke-width" => s.width = length(v)?,
            "stroke-miterlimit" => s.miter = number(v)?,
            "stroke-dasharray" => {
                s.dash.array = if v == "none" {
                    vec![]
                } else {
                    numbers::length_list(v)?
                }
            }
            "stroke-dashoffset" => s.dash.offset = length(v)?,
            "fill-rule" => {
                s.rule = match v {
                    "nonzero" => FillRule::Nonzero,
                    "evenodd" => FillRule::EvenOdd,
                    _ => return Err(invalid("Invalid fill rule")),
                }
            }
            "clip-rule" => {
                s.clip_rule = match v {
                    "nonzero" => FillRule::Nonzero,
                    "evenodd" => FillRule::EvenOdd,
                    _ => return Err(invalid("Invalid clip rule")),
                }
            }
            "stroke-linecap" => {
                s.cap = match v {
                    "butt" => Cap::Butt,
                    "round" => Cap::Round,
                    "square" => Cap::Square,
                    _ => return Err(invalid("Invalid stroke cap")),
                }
            }
            "stroke-linejoin" => {
                s.join = match v {
                    "miter" => Join::Miter,
                    "round" => Join::Round,
                    "bevel" => Join::Bevel,
                    _ => return Err(invalid("Invalid stroke join")),
                }
            }
            "visibility" => {
                s.visible = match v {
                    "visible" => true,
                    "hidden" | "collapse" => false,
                    _ => return Err(invalid("Invalid visibility")),
                }
            }
            "opacity" => {
                unit_interval(v)?;
            }
            "display" => {
                if !["inline", "none"].contains(&v) {
                    return Err(unsupported(
                        "Only display:inline and display:none are supported",
                    ));
                }
            }
            "isolation" => {
                if !["auto", "isolate"].contains(&v) {
                    return Err(unsupported("Unsupported isolation"));
                }
            }
            "color-interpolation" => {
                s.space = match v {
                    "sRGB" => crate::paint::Interpolation::Srgb,
                    "linearRGB" => crate::paint::Interpolation::LinearRgb,
                    _ => {
                        return Err(unsupported(
                            "Only sRGB and linearRGB gradient interpolation are supported",
                        ));
                    }
                };
            }
            _ => unreachable!(),
        }
    }
    // Validate even unused paints so unsupported declarations never disappear.
    paint(&s.fill, s.fill_opacity, s.color)?;
    paint(&s.stroke, s.stroke_opacity, s.color)?;
    s.dash.validate()?;
    if s.stop_color != "currentColor" {
        color(&s.stop_color)?;
    }
    if s.width < 0.0
        || s.width > f64::from(crate::limits::strokes::MAX_WIDTH)
        || s.miter < f64::from(crate::limits::strokes::MIN_MITER_LIMIT)
        || s.miter > f64::from(crate::limits::strokes::MAX_MITER_LIMIT)
    {
        return Err(unsupported(
            "Stroke width or miter limit exceeds the engine range",
        ));
    }
    Ok(s)
}
fn attr(node: Node<'_, '_>, name: &str, default: f64) -> Result<f64, Error> {
    node.attribute(name).map(length).unwrap_or(Ok(default))
}
fn required<'a>(node: Node<'a, 'a>, name: &str) -> Result<&'a str, Error> {
    node.attribute(name).ok_or_else(|| {
        unsupported(format!(
            "Explicit {name} is required on <{}>",
            node.tag_name().name()
        ))
    })
}
fn shape_attributes(tag: &str) -> Result<&'static [&'static str], Error> {
    Ok(match tag {
        "rect" => &["x", "y", "width", "height", "rx", "ry"],
        "ellipse" => &["cx", "cy", "rx", "ry"],
        "circle" => &["cx", "cy", "r"],
        "line" => &["x1", "y1", "x2", "y2"],
        "polygon" | "polyline" => &["points"],
        "path" => &["d"],
        _ => return Err(unsupported(format!("Geometry <{tag}> is not supported"))),
    })
}
fn shape(node: Node<'_, '_>, approximations: &mut Vec<Value>) -> Result<Geometry, Error> {
    let mut summary = arcs::Summary::default();
    let geometry = shape_geometry(node, &mut summary)?;
    if summary.arc_commands != 0 {
        approximations.push(json!({"source_id":node.attribute("id"),"element":node.tag_name().name(),
            "byte_offset":node.range().start,"method":"tangent_cubics","coordinate_space":"source_element_local_before_transforms",
            "binary64_roundoff_included":false,"arcs":summary}));
    }
    Ok(geometry)
}
fn shape_geometry(node: Node<'_, '_>, summary: &mut arcs::Summary) -> Result<Geometry, Error> {
    Ok(match node.tag_name().name() {
        "rect" => {
            let x = attr(node, "x", 0.0)?;
            let y = attr(node, "y", 0.0)?;
            let width = length(required(node, "width")?)?;
            let height = length(required(node, "height")?)?;
            let rectangle = Geometry::Rect {
                x,
                y,
                width,
                height,
            };
            geometry::validate_geometry(&rectangle)?;
            let radius = |name| -> Result<Option<f64>, Error> {
                let Some(value) = node.attribute(name).filter(|v| v.trim() != "auto") else {
                    return Ok(None);
                };
                let value = length(value)?;
                if value < 0.0 {
                    return Err(invalid("Rectangle corner radii must not be negative"));
                }
                Ok(Some(value))
            };
            let rx = radius("rx")?;
            let ry = radius("ry")?;
            let rx_used = rx.or(ry).unwrap_or(0.0).min(width / 2.0);
            let ry_used = ry.or(rx).unwrap_or(0.0).min(height / 2.0);
            if rx_used == 0.0 || ry_used == 0.0 {
                rectangle
            } else {
                let rx = rx_used;
                let ry = ry_used;
                let mut commands = vec![PathCommand::Move { to: [x + rx, y] }];
                for (from, to) in [
                    ([x + width - rx, y], [x + width, y + ry]),
                    ([x + width, y + height - ry], [x + width - rx, y + height]),
                    ([x + rx, y + height], [x, y + height - ry]),
                    ([x, y + ry], [x + rx, y]),
                ] {
                    commands.push(PathCommand::Line { to: from });
                    arcs::append(&mut commands, from, to, &[rx, ry, 0.0, 0.0, 1.0], summary)?;
                }
                commands.push(PathCommand::Close {});
                Geometry::Path { commands }
            }
        }
        "ellipse" | "circle" => Geometry::Ellipse {
            cx: attr(node, "cx", 0.0)?,
            cy: attr(node, "cy", 0.0)?,
            rx: length(required(
                node,
                if node.tag_name().name() == "circle" {
                    "r"
                } else {
                    "rx"
                },
            )?)?,
            ry: length(required(
                node,
                if node.tag_name().name() == "circle" {
                    "r"
                } else {
                    "ry"
                },
            )?)?,
        },
        "line" => Geometry::Path {
            commands: vec![
                PathCommand::Move {
                    to: [attr(node, "x1", 0.0)?, attr(node, "y1", 0.0)?],
                },
                PathCommand::Line {
                    to: [attr(node, "x2", 0.0)?, attr(node, "y2", 0.0)?],
                },
            ],
        },
        "polygon" | "polyline" => {
            let points = numbers::list(required(node, "points")?)?;
            if points.len() < 4 || points.len() % 2 != 0 {
                return Err(invalid("Points require at least two coordinate pairs"));
            }
            let mut commands = vec![PathCommand::Move {
                to: [points[0], points[1]],
            }];
            commands.extend(
                points[2..]
                    .as_chunks::<2>()
                    .0
                    .iter()
                    .map(|p| PathCommand::Line { to: [p[0], p[1]] }),
            );
            if node.tag_name().name() == "polygon" {
                commands.push(PathCommand::Close {});
            }
            Geometry::Path { commands }
        }
        "path" => numbers::path(required(node, "d")?, summary)?,
        _ => {
            return Err(unsupported(format!(
                "Element <{}> is not supported",
                node.tag_name().name()
            )));
        }
    })
}
fn viewport(node: Node<'_, '_>) -> Result<(f64, f64, Matrix), Error> {
    let dimension = |name| -> Result<f64, Error> {
        let n = length(required(node, name)?)?;
        if !(crate::limits::vector_canvas::MIN_LOGICAL_SIZE..=MAX_DIMENSION as f64).contains(&n) {
            return Err(unsupported(format!(
                "SVG canvas dimensions must resolve to {}..{MAX_DIMENSION} logical pixels at 96 ppi",
                crate::limits::vector_canvas::MIN_LOGICAL_SIZE
            )));
        }
        Ok(n)
    };
    let (w, h) = (dimension("width")?, dimension("height")?);
    let mut matrix = identity();
    if let Some(v) = node.attribute("viewBox") {
        let v = numbers::list(v)?;
        if v.len() != 4 || v[2] <= 0.0 || v[3] <= 0.0 {
            return Err(invalid(
                "viewBox requires x y positive-width positive-height",
            ));
        }
        let mut sx = w / v[2];
        let mut sy = h / v[3];
        let p = node
            .attribute("preserveAspectRatio")
            .unwrap_or("xMidYMid meet")
            .split_whitespace()
            .collect::<Vec<_>>();
        let mut dx = 0.0;
        let mut dy = 0.0;
        if p.as_slice() != ["none"] {
            if !(1..=2).contains(&p.len())
                || ![
                    "xMinYMin", "xMidYMin", "xMaxYMin", "xMinYMid", "xMidYMid", "xMaxYMid",
                    "xMinYMax", "xMidYMax", "xMaxYMax",
                ]
                .contains(&p[0])
            {
                return Err(unsupported("Unsupported preserveAspectRatio syntax"));
            }
            let scale = match p.get(1).copied().unwrap_or("meet") {
                "meet" => sx.min(sy),
                "slice" => sx.max(sy),
                _ => return Err(invalid("Expected meet or slice")),
            };
            sx = scale;
            sy = scale;
            let factor = |s| match s {
                "Min" => 0.0,
                "Mid" => 0.5,
                _ => 1.0,
            };
            dx = (w - v[2] * scale) * factor(&p[0][1..4]);
            dy = (h - v[3] * scale) * factor(&p[0][5..8]);
        }
        matrix = [sx, 0.0, 0.0, sy, dx - v[0] * sx, dy - v[1] * sy];
    } else if node.has_attribute("preserveAspectRatio") {
        return Err(unsupported(
            "preserveAspectRatio requires viewBox in this importer",
        ));
    }
    Ok((w, h, matrix))
}
struct Importer<'css> {
    styles: &'css styles::Sheet,
    control: crate::control::Control,
    document: Document,
    mappings: Vec<Value>,
    losses: Vec<String>,
    approximations: Vec<Value>,
    definitions: definitions::Definitions,
    bindings: Vec<definitions::Binding>,
    fonts: labels::Fonts,
    viewport: [f64; 2],
    in_mask: bool,
    modern_masks: bool,
}
impl Importer<'_> {
    fn visit(
        &mut self,
        node: Node<'_, '_>,
        parent: Option<String>,
        inherited: &Style,
        root_matrix: Option<Matrix>,
    ) -> Result<(), Error> {
        self.control.check()?;
        let tag = node.tag_name().name();
        if tag == "style" {
            return Ok(());
        }
        if [
            "defs",
            "linearGradient",
            "radialGradient",
            "clipPath",
            "mask",
        ]
        .contains(&tag)
        {
            return self.definitions.collect(node, inherited, self.styles);
        }
        let is_root = root_matrix.is_some();
        let container = is_root || tag == "g";
        let is_text = tag == "text";
        if tag == "svg" && !is_root {
            return Err(unsupported("Nested SVG viewports are not yet supported"));
        }
        let extra: &[&str] = match tag {
            "svg" => &[
                "width",
                "height",
                "viewBox",
                "preserveAspectRatio",
                "version",
            ],
            "g" => &[],
            "text" => &["x", "y", "dx", "dy"],
            _ => shape_attributes(tag)?,
        };
        let props = properties(node, extra, self.styles)?;
        let style = styled(inherited, &props)?;
        if self.in_mask && style.mask.is_some() {
            return Err(unsupported(
                "Opacity masks inside mask artwork are not yet supported",
            ));
        }
        if style.space != crate::paint::Interpolation::Srgb {
            return Err(unsupported(
                "linearRGB color-interpolation is supported on gradient definitions only; ordinary compositing remains sRGB",
            ));
        }
        let mut transform = node
            .attribute("transform")
            .map(numbers::transform)
            .transpose()?
            .unwrap_or(identity());
        if let Some(view) = root_matrix {
            transform = geometry::multiply(transform, view);
        }
        let opacity = props
            .get("opacity")
            .map(|s| unit_interval(s))
            .transpose()?
            .unwrap_or(1.0);
        let mut name = node.attribute("id").unwrap_or("").to_owned();
        let mut title = false;
        for child in node.children() {
            if !is_text && child.is_text() && !child.text().unwrap_or("").trim().is_empty() {
                return Err(unsupported(format!(
                    "Text content in <{tag}> is not supported"
                )));
            }
            if child.is_element() && ["title", "desc"].contains(&child.tag_name().name()) {
                if child.attributes().len() != 0 || child.children().any(|c| c.is_element()) {
                    return Err(unsupported("Only plain title/desc text is supported"));
                }
                let value = child
                    .children()
                    .filter_map(|c| c.text())
                    .collect::<String>();
                if child.tag_name().name() == "title" {
                    if title {
                        return Err(unsupported("At most one title per element is supported"));
                    }
                    title = true;
                    name = value;
                } else {
                    self.losses
                        .push("Description text is not retained in the editable document.".into());
                }
            }
        }
        let id = format!("svg-{}", self.document.items.len());
        if self.document.items.len() >= self.document.resource_profile.items() {
            return Err(Error::new("RESOURCE_LIMIT", "SVG item limit exceeded"));
        }
        let mut text_bounds = None;
        let mut text_placement = identity();
        let content = if is_text {
            let imported = labels::content(
                node,
                &style,
                &mut self.document,
                &mut self.fonts,
                self.viewport,
            )?;
            text_bounds = imported.bounds;
            text_placement = imported.placement;
            transform = geometry::multiply(transform, text_placement);
            self.losses.push("SVG text becomes a single editable frame using explicitly bound fonts. Whitespace and baseline placement are normalized; anchor alignment persists within the initial advance-width frame. Font-family expressions and XML text structure are not retained. SVG export uses glyph outlines and reports loss of text editability.".into());
            Content::Text {
                frame: Box::new(imported.frame),
            }
        } else if container {
            Content::Group {
                isolated: true,
                role: GroupRole::Group,
                knockout: false,
            }
        } else {
            let fill = paint(&style.fill, style.fill_opacity, style.color)?;
            let stroke = paint(&style.stroke, style.stroke_opacity, style.color)?
                .filter(|_| style.width != 0.0)
                .map(|color| {
                    Box::new(Stroke {
                        scaling: Default::default(),
                        color,
                        width: style.width,
                        cap: style.cap,
                        join: style.join,
                        miter_limit: style.miter,
                        width_profile: vec![],
                        brush: None,
                        start_arrow: None,
                        end_arrow: None,
                        curve_tolerance: crate::strokes::default_tolerance(),
                        dash: (!style.dash.array.is_empty() || style.dash.offset != 0.0)
                            .then(|| style.dash.clone()),
                    })
                });
            Content::Vector {
                geometry: shape(node, &mut self.approximations)?,
                fill,
                stroke,
                fill_rule: style.rule,
            }
        };
        self.mappings.push(json!({"item_id":id,"source_id":node.attribute("id"),"element":tag,"byte_offset":node.range().start}));
        self.bindings.push(definitions::Binding {
            index: self.document.items.len(),
            style: style.clone(),
            clip: props
                .get("clip-path")
                .map(|v| definitions::reference(v))
                .transpose()?
                .flatten()
                .map(str::to_owned),
            displayed: props.get("display") != Some(&"none"),
            text_bounds,
            text_placement,
            viewport: self.viewport,
        });
        self.document.items.push(Item {
            hdr_grade: None,
            pixel_warp: None,
            metadata: None,
            id: id.clone(),
            name,
            visible: props.get("display") != Some(&"none") && (container || style.visible),
            locked: false,
            opacity,
            fill_opacity: 1.0,
            coverage: crate::coverage::Mode::Smooth {},
            effects: Vec::new(),
            blend: BlendMode::Normal,
            transform,
            parent,
            clip_to: None,
            clip: None,
            mask: None,
            artwork_mask: None,
            filters: vec![],
            content,
        });
        for child in node.children().filter(|c| c.is_element()) {
            if child.tag_name().name() == "metadata" {
                if node.parent_element().is_some() {
                    return Err(unsupported("Metadata is supported only at the SVG root"));
                }
                continue;
            }
            if ["title", "desc", "style"].contains(&child.tag_name().name()) {
                continue;
            }
            if !container {
                return Err(unsupported(format!(
                    "Child elements in <{tag}> are not supported"
                )));
            }
            self.visit(child, Some(id.clone()), &style, None)?;
        }
        Ok(())
    }
}

pub fn import(
    id: String,
    source: Source,
    font_bindings: Vec<FontBinding>,
    font_root: Option<PathBuf>,
) -> Result<Value, Error> {
    import_controlled(
        id,
        source,
        font_bindings,
        font_root,
        ResourceProfile::Standard,
        &crate::control::Control::default(),
    )
}
pub fn import_controlled(
    id: String,
    source: Source,
    font_bindings: Vec<FontBinding>,
    font_root: Option<PathBuf>,
    resource_profile: ResourceProfile,
    control: &crate::control::Control,
) -> Result<Value, Error> {
    import_with_budget(
        id,
        source,
        font_bindings,
        font_root,
        resource_profile,
        control,
        None,
    )
}
fn import_with_budget(
    id: String,
    source: Source,
    font_bindings: Vec<FontBinding>,
    font_root: Option<PathBuf>,
    resource_profile: ResourceProfile,
    control: &crate::control::Control,
    byte_budget: Option<usize>,
) -> Result<Value, Error> {
    control.check()?;
    if resource_profile == ResourceProfile::LargeRaster {
        return Err(crate::model::invalid(
            "SVG import requires a vector resource profile",
        ));
    }
    let (max_bytes, max_nodes) = if resource_profile.is_standard() {
        (MAX_BYTES, MAX_NODES)
    } else {
        (MAX_LARGE_BYTES, MAX_LARGE_NODES)
    };
    let max_bytes = byte_budget.unwrap_or(max_bytes);
    let bytes = match source {
        Source::Text { text } => text.into_bytes(),
        Source::File { source_path } => {
            let file = File::open(&source_path)
                .map_err(|e| Error::new("SVG_IO", format!("Cannot open source: {e}")))?;
            if !file
                .metadata()
                .map_err(|e| Error::new("SVG_IO", e.to_string()))?
                .is_file()
            {
                return Err(Error::new("SVG_IO", "Source must be a regular file"));
            }
            let mut bytes = Vec::new();
            file.take(max_bytes as u64 + 1)
                .read_to_end(&mut bytes)
                .map_err(|e| Error::new("SVG_IO", e.to_string()))?;
            bytes
        }
    };
    if bytes.len() > max_bytes {
        return Err(Error::new(
            "RESOURCE_LIMIT",
            "SVG source exceeds its resource-profile byte budget",
        ));
    }
    let hash = format!("{:x}", Sha256::digest(&bytes));
    let text = std::str::from_utf8(&bytes).map_err(|_| invalid("SVG source must be UTF-8"))?;
    if text.contains("<!DOCTYPE") {
        return Err(unsupported("DTD declarations are not supported"));
    }
    let xml = roxmltree::Document::parse_with_options(
        text,
        roxmltree::ParsingOptions {
            allow_dtd: false,
            nodes_limit: max_nodes,
            entity_resolver: None,
        },
    )
    .map_err(|e| invalid(format!("XML parse failed: {e}")))?;
    let root = xml.root_element();
    if root.tag_name().name() != "svg" || !matches!(root.tag_name().namespace(), None | Some(NS)) {
        return Err(unsupported("Expected an SVG root element"));
    }
    if let Some(v) = root.attribute("version")
        && !["1.0", "1.1", "2.0"].contains(&v)
    {
        return Err(unsupported("Unsupported SVG version"));
    }
    let mut source_ids = HashSet::new();
    for n in xml.descendants() {
        control.check()?;
        if n.is_pi() {
            return Err(unsupported(
                "Processing instructions and external stylesheets are not supported",
            ));
        }
        if !n.is_element() {
            continue;
        }
        if n.tag_name().namespace() != root.tag_name().namespace()
            && !(n.tag_name().name() == "inkbolt"
                && n.tag_name().namespace() == Some(crate::metadata::SVG_NS)
                && n.parent()
                    .is_some_and(|p| p.tag_name().name() == "metadata" && p.parent() == Some(root)))
        {
            return Err(unsupported(
                "Mixed or foreign element namespaces are not supported",
            ));
        }
        if n.ancestors().take(crate::scene::MAX_DEPTH + 4).count() > crate::scene::MAX_DEPTH + 2 {
            return Err(Error::new(
                "RESOURCE_LIMIT",
                "SVG nesting exceeds the document limit",
            ));
        }
        if let Some(id) = n.attribute("id")
            && (id.is_empty() || !source_ids.insert(id))
        {
            return Err(invalid("Empty or duplicate SVG source ID"));
        }
    }
    let styles = styles::Sheet::parse(root, control)?;
    let (width, height, matrix) = viewport(root)?;
    let document = Document {
        resource_profile,
        vector_canvas: (width.fract() != 0.0 || height.fract() != 0.0).then_some(
            crate::vector_canvas::Canvas {
                origin_px: [0.0; 2],
                size_px: [width, height],
                unit: crate::dimensions::Unit::Px,
                process_space: Default::default(),
            },
        ),
        stories: BTreeMap::new(),
        swatches: Default::default(),
        background: None,
        metadata: None,
        output_profile: None,
        variants: None,
        global_light: crate::effects::Lighting::default(),
        schema_version: 2,
        id,
        kind: DocumentKind::Vector,
        width: width.ceil() as u32,
        height: height.ceil() as u32,
        color_space: ColorSpace::Srgb,
        revision: 0,
        resolution_ppi: 96.0,
        items: vec![],
        assets: Default::default(),
        fonts: Default::default(),
        selection: None,
        channels: Default::default(),
        ink_recipe: None,
    };
    let user_viewport = if let Some(v) = root.attribute("viewBox") {
        let v = numbers::list(v)?;
        [v[2], v[3]]
    } else {
        [width, height]
    };
    let mut importer=Importer{styles:&styles,control:control.clone(),document,mappings:vec![],approximations:vec![],definitions:Default::default(),bindings:vec![],
        fonts: labels::Fonts::new(font_bindings, font_root.as_deref())?, viewport: user_viewport, in_mask:false, modern_masks: root.attribute("version") == Some("2.0"), losses:vec![
        "Source IDs are mapped to deterministic item IDs; the root is an editable group. Retain the source for XML formatting, comments and original IDs.".into(),
        "Presentation inheritance, embedded stylesheets and inline style are resolved into editable properties. Classes, selectors and stylesheet syntax are not retained. Quadratic curves and shorthand become explicit cubic/line commands; units/viewBox become affine transforms. Original syntax is not retained.".into(),
        "Paint colors and fill/stroke opacity are quantized to RGBA8; object and group opacity retain f64 precision. Geometry is f64; display coverage uses the existing f32 renderer.".into(),
    ]};
    let mut initial_style = Style::default();
    initial_style.text.modern_whitespace = root.attribute("version") == Some("2.0");
    importer.visit(root, None, &initial_style, Some(matrix))?;
    let metadata_nodes: Vec<_> = root
        .children()
        .filter(|n| n.is_element() && n.tag_name().name() == "metadata")
        .collect();
    if metadata_nodes.len() > 1 {
        return Err(invalid("Duplicate root metadata"));
    }
    if let Some(node) = metadata_nodes.first() {
        let children: Vec<_> = node.children().filter(|n| n.is_element()).collect();
        if node
            .children()
            .any(|n| n.is_text() && !n.text().unwrap_or("").trim().is_empty())
            || node.attributes().len() != 0
            || children.len() != 1
            || children[0].tag_name().name() != "inkbolt"
            || children[0].tag_name().namespace() != Some(crate::metadata::SVG_NS)
            || children[0].attributes().len() != 0
            || children[0].children().any(|n| n.is_element())
        {
            return Err(unsupported(
                "Only the Inkbolt root metadata envelope is supported",
            ));
        }
        let text = children[0]
            .children()
            .filter_map(|n| n.text())
            .collect::<String>();
        let recovered = crate::metadata::read_packet(text.as_bytes())?;
        let envelope = &recovered["envelope"];
        importer.document.metadata = serde_json::from_value(envelope["document"].clone())
            .map_err(|_| invalid("Invalid document metadata"))?;
        for (source, record) in envelope["items"].as_object().unwrap() {
            if let Some(mapping) = importer
                .mappings
                .iter()
                .find(|m| m["source_id"] == source.as_str())
            {
                let id = mapping["item_id"].as_str().unwrap();
                let i = crate::scene::index(&importer.document, id)?;
                importer.document.items[i].metadata = Some(
                    serde_json::from_value(record.clone())
                        .map_err(|_| invalid("Invalid item metadata"))?,
                );
            } else {
                importer.losses.push(format!(
                    "Metadata for source item {source} has no exported editable counterpart."
                ));
            }
        }
        importer.losses.push("Public document/item metadata is retained. Embedded manifests and provenance are untrusted source descriptions, not resource bindings or authentication, and are not promoted into the editable document.".into());
    }

    importer.prepare_masks(root)?;
    // Validate geometry/hierarchy before deriving local bounding boxes or paints.
    validate_controlled(&importer.document, control)?;
    importer
        .approximations
        .append(&mut importer.definitions.approximations);
    importer
        .approximations
        .sort_by_key(|v| v["byte_offset"].as_u64());
    if !importer.approximations.is_empty() {
        importer.losses.push("Elliptical arcs and rounded rectangle corners become editable tangent cubics (degenerate arcs become lines or no segment). The approximations receipt bounds radial error in source-element local units, before transforms and excluding binary64 roundoff. Original arc/corner parameters are not retained.".into());
    }
    importer
        .definitions
        .apply(&mut importer.document, &importer.bindings, user_viewport)?;
    masking::apply(
        &mut importer.document,
        &importer.bindings,
        &importer.definitions.masks,
        importer.modern_masks,
    )?;
    if !importer.definitions.masks.is_empty() {
        importer.losses.push("SVG mask definitions become shared editable nonprinting artwork sources. Region/content units and text baseline coordinates resolve into reference transforms at import; later geometry edits do not automatically resize object-box masks. Definition display/opacity do not affect mask content. Snapshots preserve shared references; SVG export copies each reference and outlines text.".into());
    }
    if !importer.definitions.records.is_empty() {
        importer.losses.push("SVG gradient and clip definitions are copied into each referencing item. Shared references, templates and definition metadata are not retained; object-bounding-box coordinates are resolved at import.".into());
    }
    validate_controlled(&importer.document, control)?;
    importer.losses.sort();
    importer.losses.dedup();
    Ok(
        json!({"document":importer.document,"source":{"sha256":hash,"bytes":bytes.len(),"media_type":"image/svg+xml"},"mapping":importer.mappings,"definitions":importer.definitions.records,"losses":importer.losses,"approximations":importer.approximations}),
    )
}
