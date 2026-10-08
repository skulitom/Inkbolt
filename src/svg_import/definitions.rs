//! Original reference resolution and SVG coordinate mapping. No resource fetching.
use super::*;
use crate::paint::{Field, Interpolation, Spread, Stop};

pub const MAX_DEFINITIONS: usize = 64;
pub const MAX_REFERENCE_DEPTH: usize = 16;

pub(super) fn reference(value: &str) -> Result<Option<&str>, Error> {
    if !value.starts_with("url(") {
        return Ok(None);
    }
    let inner = value
        .strip_prefix("url(")
        .and_then(|s| s.strip_suffix(')'))
        .ok_or_else(|| {
            unsupported("Paint/clip references require url(#id) without fallback syntax")
        })?
        .trim();
    let inner = if inner.len() >= 2
        && ((inner.starts_with('\'') && inner.ends_with('\''))
            || (inner.starts_with('"') && inner.ends_with('"')))
    {
        &inner[1..inner.len() - 1]
    } else {
        inner
    };
    let id = inner
        .strip_prefix('#')
        .filter(|s| {
            !s.is_empty()
                && !s
                    .chars()
                    .any(|c| c.is_whitespace() || matches!(c, '\'' | '"' | '(' | ')' | '%' | '#'))
        })
        .ok_or_else(|| unsupported("Only literal local fragment references are supported"))?;
    Ok(Some(id))
}
#[derive(Clone, Copy)]
pub(super) enum Coordinate {
    User(f64),
    Percent(f64),
}
impl Coordinate {
    pub(super) fn parse(s: &str) -> Result<Self, Error> {
        let s = s.trim();
        if let Some(p) = s.strip_suffix('%') {
            Ok(Self::Percent(number(p)? / 100.0))
        } else {
            Ok(Self::User(length(s)?))
        }
    }
    pub(super) fn value(self, basis: f64) -> f64 {
        match self {
            Self::User(v) => v,
            Self::Percent(v) => v * basis,
        }
    }
}
#[derive(Clone)]
struct Gradient {
    radial: bool,
    template: Option<String>,
    attributes: BTreeMap<String, String>,
    stops: Vec<StopTemplate>,
    space: Interpolation,
    style: Style,
}
#[derive(Clone)]
struct StopTemplate {
    offset: f64,
    properties: BTreeMap<String, String>,
}
#[derive(Clone)]
struct Resolved {
    radial: bool,
    bounding_box: bool,
    transform: Matrix,
    coordinates: BTreeMap<String, Coordinate>,
    stops: Vec<Stop>,
    spread: Spread,
    space: Interpolation,
}
struct ClipTemplate {
    geometry: Geometry,
    rule: FillRule,
    transform: Matrix,
    bounding_box: bool,
    empty: bool,
}
#[derive(Default)]
pub(super) struct Definitions {
    gradients: BTreeMap<String, Gradient>,
    clips: BTreeMap<String, ClipTemplate>,
    pub records: Vec<Value>,
    pub masks: BTreeMap<String, masking::Template>,
}
pub(super) struct Binding {
    pub index: usize,
    pub style: Style,
    pub clip: Option<String>,
    pub displayed: bool,
    pub text_bounds: Option<geometry::Bounds>,
    pub text_placement: Matrix,
    pub viewport: [f64; 2],
}

fn elements<'a, 'input>(node: Node<'a, 'input>) -> Result<Vec<Node<'a, 'input>>, Error> {
    let mut out = Vec::new();
    for child in node.children() {
        if child.is_text() && !child.text().unwrap_or("").trim().is_empty() {
            return Err(unsupported("Text inside an SVG definition is unsupported"));
        }
        if child.is_element() {
            if ["title", "desc"].contains(&child.tag_name().name()) {
                if child.attributes().len() != 0 || child.children().any(|c| c.is_element()) {
                    return Err(unsupported("Definition descriptions require plain text"));
                }
            } else {
                out.push(child);
            }
        }
    }
    Ok(out)
}
fn matrix(node: Node<'_, '_>, name: &str) -> Result<Matrix, Error> {
    node.attribute(name)
        .map(numbers::transform)
        .transpose()
        .map(|m| m.unwrap_or(identity()))
}
pub(super) fn bbox_unit(value: &str) -> Result<bool, Error> {
    match value {
        "objectBoundingBox" => Ok(true),
        "userSpaceOnUse" => Ok(false),
        _ => Err(invalid("Expected objectBoundingBox or userSpaceOnUse")),
    }
}
fn id(node: Node<'_, '_>) -> Result<String, Error> {
    Ok(required(node, "id")?.to_owned())
}

impl Definitions {
    pub fn collect(&mut self, node: Node<'_, '_>, inherited: &Style) -> Result<(), Error> {
        if node.tag_name().name() == "defs" {
            let props = properties(node, &[])?;
            if node.has_attribute("transform")
                || props.contains_key("clip-path")
                || props.get("mask").is_some_and(|v| *v != "none")
            {
                return Err(unsupported(
                    "Transforms/effects on defs containers are not supported",
                ));
            }
            let style = styled(inherited, &props)?;
            for child in elements(node)? {
                self.collect(child, &style)?;
            }
            return Ok(());
        }
        if self.gradients.len() + self.clips.len() + self.masks.len() >= MAX_DEFINITIONS {
            return Err(Error::new(
                "RESOURCE_LIMIT",
                "SVG exceeds 64 gradient/clip/mask definitions",
            ));
        }
        let name = id(node)?;
        match node.tag_name().name() {
            "linearGradient" | "radialGradient" => self.gradient(node, inherited, name.clone())?,
            "clipPath" => self.clip(node, inherited, name.clone())?,
            "mask" => {
                self.masks
                    .insert(name.clone(), masking::Template::parse(node, inherited)?);
            }
            tag => return Err(unsupported(format!("Definition <{tag}> is not supported"))),
        }
        self.records.push(json!({"source_id":name,"element":node.tag_name().name(),"byte_offset":node.range().start}));
        Ok(())
    }
    fn gradient(&mut self, node: Node<'_, '_>, inherited: &Style, id: String) -> Result<(), Error> {
        let radial = node.tag_name().name() == "radialGradient";
        let extras: &[&str] = if radial {
            &[
                "gradientUnits",
                "gradientTransform",
                "spreadMethod",
                "cx",
                "cy",
                "r",
                "fx",
                "fy",
                "href",
            ]
        } else {
            &[
                "gradientUnits",
                "gradientTransform",
                "spreadMethod",
                "x1",
                "y1",
                "x2",
                "y2",
                "href",
            ]
        };
        let props = properties(node, extras)?;
        if node.has_attribute("transform")
            || props.contains_key("clip-path")
            || props.get("mask").is_some_and(|v| *v != "none")
        {
            return Err(unsupported(
                "Use gradientTransform; clipping a paint server is unsupported",
            ));
        }
        let style = styled(inherited, &props)?;
        let href = node.attribute("href");
        let xlink = node.attribute(("http://www.w3.org/1999/xlink", "href"));
        if href.is_some() && xlink.is_some() && href != xlink {
            return Err(unsupported("Conflicting href and xlink:href references"));
        }
        let template = href
            .or(xlink)
            .map(|v| {
                v.strip_prefix('#')
                    .filter(|v| {
                        !v.is_empty()
                            && !v.chars().any(|c| {
                                c.is_whitespace() || matches!(c, '\'' | '"' | '(' | ')' | '%' | '#')
                            })
                    })
                    .map(str::to_owned)
                    .ok_or_else(|| unsupported("Gradient templates require local #id references"))
            })
            .transpose()?;
        let mut attributes = BTreeMap::new();
        for key in extras.iter().filter(|k| **k != "href") {
            if let Some(value) = node.attribute(*key) {
                // Syntax is validated even when a child template replaces it later.
                match *key {
                    "gradientUnits" => {
                        bbox_unit(value)?;
                    }
                    "gradientTransform" => {
                        numbers::transform(value)?;
                    }
                    "spreadMethod" => {
                        spread(value)?;
                    }
                    _ => {
                        Coordinate::parse(value)?;
                    }
                }
                attributes.insert((*key).to_owned(), value.to_owned());
            }
        }
        let mut stops = Vec::new();
        let mut previous = 0.0f64;
        for child in elements(node)? {
            if child.tag_name().name() != "stop" {
                return Err(unsupported("Gradients accept stop elements only"));
            }
            let props = properties(child, &["offset"])?;
            if child.has_attribute("transform")
                || props.contains_key("clip-path")
                || props.get("mask").is_some_and(|v| *v != "none")
                || !elements(child)?.is_empty()
            {
                return Err(unsupported(
                    "Transformed, clipped or nested gradient stops are unsupported",
                ));
            }
            styled(&style, &props)?;
            let raw_offset = required(child, "offset")?.trim();
            let offset = if let Some(value) = raw_offset.strip_suffix('%') {
                number(value)? / 100.0
            } else {
                number(raw_offset)?
            };
            let offset = offset.clamp(0.0, 1.0).max(previous);
            previous = offset;
            stops.push(StopTemplate {
                offset,
                properties: props
                    .into_iter()
                    .map(|(k, v)| (k.to_owned(), v.to_owned()))
                    .collect(),
            });
            if stops.len() > crate::paint::MAX_STOPS {
                return Err(Error::new(
                    "RESOURCE_LIMIT",
                    "SVG gradient exceeds 64 stops",
                ));
            }
        }
        self.gradients.insert(
            id,
            Gradient {
                radial,
                template,
                attributes,
                stops,
                space: style.space,
                style,
            },
        );
        Ok(())
    }
    fn clip(&mut self, node: Node<'_, '_>, inherited: &Style, id: String) -> Result<(), Error> {
        let props = properties(node, &["clipPathUnits"])?;
        if props.get("clip-path").is_some_and(|v| *v != "none")
            || props.get("mask").is_some_and(|v| *v != "none")
        {
            return Err(unsupported(
                "References on clip definitions are not yet supported",
            ));
        }
        let style = styled(inherited, &props)?;
        let children = elements(node)?;
        if children.len() > 1 {
            return Err(unsupported(
                "Multiple clip children require geometric union support; use one compound path",
            ));
        }
        let bounding_box = bbox_unit(node.attribute("clipPathUnits").unwrap_or("userSpaceOnUse"))?;
        let transform = matrix(node, "transform")?;
        let empty_geometry = || Geometry::Path {
            commands: vec![
                PathCommand::Move { to: [0.0, 0.0] },
                PathCommand::Line { to: [0.0, 0.0] },
            ],
        };
        let (geometry, rule, transform, empty) = if let Some(child) = children.first() {
            let tag = child.tag_name().name();
            let props = properties(*child, super::shape_attributes(tag)?)?;
            if props.get("clip-path").is_some_and(|v| *v != "none")
                || props.get("mask").is_some_and(|v| *v != "none")
                || !elements(*child)?.is_empty()
            {
                return Err(unsupported(
                    "Nested content/effects in clipping geometry are unsupported",
                ));
            }
            let cs = styled(&style, &props)?;
            let g = shape(*child)?;
            crate::geometry::validate_geometry(&g)?;
            let hidden = props.get("display") == Some(&"none") || !cs.visible;
            (
                if hidden { empty_geometry() } else { g },
                cs.clip_rule,
                geometry::multiply(transform, matrix(*child, "transform")?),
                hidden,
            )
        } else {
            (empty_geometry(), style.clip_rule, transform, true)
        };
        crate::geometry::validate_matrix(transform)?;
        self.clips.insert(
            id,
            ClipTemplate {
                geometry,
                rule,
                transform,
                bounding_box,
                empty,
            },
        );
        Ok(())
    }
    fn inherited_gradient(&self, id: &str, stack: &mut Vec<String>) -> Result<Gradient, Error> {
        if stack.iter().any(|s| s == id) {
            return Err(invalid("Cyclic SVG gradient reference"));
        }
        if stack.len() >= MAX_REFERENCE_DEPTH {
            return Err(Error::new(
                "RESOURCE_LIMIT",
                "SVG gradient reference chain exceeds 16 definitions",
            ));
        }
        let mut g = self
            .gradients
            .get(id)
            .ok_or_else(|| invalid(format!("Missing or wrong-type gradient reference: {id}")))?
            .clone();
        if let Some(parent) = g.template.clone() {
            stack.push(id.to_owned());
            let base = self.inherited_gradient(&parent, stack)?;
            stack.pop();
            let mut attributes = base.attributes;
            attributes.extend(g.attributes);
            g.attributes = attributes;
            if g.stops.is_empty() {
                g.stops = base.stops;
            }
        }
        Ok(g)
    }
    fn resolved(&self) -> Result<BTreeMap<String, Resolved>, Error> {
        let mut out = BTreeMap::new();
        for id in self.gradients.keys() {
            let g = self.inherited_gradient(id, &mut vec![])?;
            let get = |key: &str, default: &str| {
                g.attributes
                    .get(key)
                    .map(String::as_str)
                    .unwrap_or(default)
                    .to_owned()
            };
            let mut coordinates = BTreeMap::new();
            for (k, d) in if g.radial {
                vec![("cx", "50%"), ("cy", "50%"), ("r", "50%")]
            } else {
                vec![("x1", "0%"), ("y1", "0%"), ("x2", "100%"), ("y2", "0%")]
            } {
                coordinates.insert(k.to_owned(), Coordinate::parse(&get(k, d))?);
            }
            // Focal points are checked against the resolved center at use time.
            if g.radial {
                for k in ["fx", "fy"] {
                    if let Some(v) = g.attributes.get(k) {
                        coordinates.insert(k.to_owned(), Coordinate::parse(v)?);
                    }
                }
            }
            // SVG template children behave like a cloned subtree. Recompute
            // inherited presentation in the final gradient's XML context.
            let stops = g
                .stops
                .iter()
                .map(|stop| -> Result<Stop, Error> {
                    let props = stop
                        .properties
                        .iter()
                        .map(|(k, v)| (k.as_str(), v.as_str()))
                        .collect();
                    let style = styled(&g.style, &props)?;
                    let mut rgba = if style.stop_color == "currentColor" {
                        style.color
                    } else {
                        color(&style.stop_color)?
                    };
                    rgba[3] = (rgba[3] as f64 * style.stop_opacity).round() as u8;
                    Ok(Stop {
                        offset: stop.offset,
                        color: rgba,
                    })
                })
                .collect::<Result<Vec<_>, _>>()?;
            out.insert(
                id.clone(),
                Resolved {
                    radial: g.radial,
                    bounding_box: bbox_unit(&get("gradientUnits", "objectBoundingBox"))?,
                    transform: numbers::transform(&get("gradientTransform", ""))?,
                    coordinates,
                    stops,
                    spread: spread(&get("spreadMethod", "pad"))?,
                    space: g.space,
                },
            );
        }
        Ok(out)
    }
    pub fn apply(
        &self,
        document: &mut Document,
        bindings: &[Binding],
        viewport: [f64; 2],
    ) -> Result<(), Error> {
        let resolved = self.resolved()?;
        // Diagnose unsupported or out-of-range definitions even when unused.
        for id in resolved.keys() {
            resolve_paint(
                &format!("url(#{id})"),
                1.0,
                [0, 0, 0, 255],
                &resolved,
                Some([0.0, 0.0, 1.0, 1.0]),
                viewport,
            )?;
        }
        for b in bindings {
            let viewport = b.viewport;
            for value in [&b.style.fill, &b.style.stroke] {
                if let Some(id) = reference(value)?
                    && !resolved.contains_key(id)
                {
                    return Err(invalid(format!(
                        "Missing or wrong-type gradient reference: {id}"
                    )));
                }
            }
            let bounds = local_bounds(document, b.index, identity(), bindings);
            if let Content::Text { frame } = &mut document.items[b.index].content {
                let paint_bounds = bounds.map(|v| {
                    [
                        v[0] + b.text_placement[4],
                        v[1] + b.text_placement[5],
                        v[2] + b.text_placement[4],
                        v[3] + b.text_placement[5],
                    ]
                });
                frame.style.fill = resolve_paint(
                    &b.style.fill,
                    b.style.fill_opacity,
                    b.style.color,
                    &resolved,
                    paint_bounds,
                    viewport,
                )?
                .unwrap_or(Paint::Solid([0; 4]));
                if let Paint::Field(
                    Field::Linear { transform, .. } | Field::Radial { transform, .. },
                ) = &mut frame.style.fill
                {
                    *transform =
                        geometry::multiply(geometry::inverse(b.text_placement)?, *transform);
                }
            }
            if let Content::Vector { fill, stroke, .. } = &mut document.items[b.index].content {
                *fill = resolve_paint(
                    &b.style.fill,
                    b.style.fill_opacity,
                    b.style.color,
                    &resolved,
                    bounds,
                    viewport,
                )?;
                if stroke.is_some() {
                    let paint = resolve_paint(
                        &b.style.stroke,
                        b.style.stroke_opacity,
                        b.style.color,
                        &resolved,
                        bounds,
                        viewport,
                    )?;
                    if let Some(paint) = paint {
                        stroke.as_mut().unwrap().color = paint;
                    } else {
                        *stroke = None;
                    }
                }
            }
            if let Some(id) = &b.clip {
                let clip = self.clips.get(id).ok_or_else(|| {
                    invalid(format!("Missing or wrong-type clip reference: {id}"))
                })?;
                let unit = if clip.bounding_box && !clip.empty {
                    bbox_matrix(bounds)?
                } else {
                    geometry::inverse(b.text_placement)?
                };
                document.items[b.index].clip = Some(Clip {
                    geometry: clip.geometry.clone(),
                    fill_rule: clip.rule,
                    transform: geometry::multiply(unit, clip.transform),
                    enabled: true,
                });
            }
        }
        Ok(())
    }
}
fn spread(s: &str) -> Result<Spread, Error> {
    match s {
        "pad" => Ok(Spread::Pad),
        "repeat" => Ok(Spread::Repeat),
        "reflect" => Ok(Spread::Reflect),
        _ => Err(invalid("Unknown gradient spread method")),
    }
}
pub(super) fn bbox_matrix(bounds: Option<geometry::Bounds>) -> Result<Matrix, Error> {
    let b = bounds
        .ok_or_else(|| unsupported("Object-bounding-box effects require nonempty geometry"))?;
    if b[2] <= b[0] || b[3] <= b[1] {
        return Err(unsupported(
            "Object-bounding-box effects require nonzero geometry width and height; stroke thickness is excluded",
        ));
    }
    Ok([b[2] - b[0], 0.0, 0.0, b[3] - b[1], b[0], b[1]])
}
pub(super) fn local_bounds(
    d: &Document,
    index: usize,
    transform: Matrix,
    bindings: &[Binding],
) -> Option<geometry::Bounds> {
    match &d.items[index].content {
        Content::Vector { geometry, .. } => Some(geometry::bounds(geometry, transform)),
        Content::Text { .. } => bindings[index].text_bounds.map(|b| {
            let points = [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]];
            points
                .into_iter()
                .map(|p| {
                    let p = geometry::map(transform, p);
                    [p[0], p[1], p[0], p[1]]
                })
                .reduce(crate::scene::union)
                .unwrap()
        }),
        Content::Group { .. } | Content::MaskSource {} => {
            crate::scene::children(d, Some(&d.items[index].id))
                .into_iter()
                .filter(|&c| bindings[c].displayed)
                .filter_map(|c| {
                    local_bounds(
                        d,
                        c,
                        geometry::multiply(transform, d.items[c].transform),
                        bindings,
                    )
                })
                .reduce(crate::scene::union)
        }
        _ => None,
    }
}
fn resolve_paint(
    s: &str,
    opacity: f64,
    current: Color,
    definitions: &BTreeMap<String, Resolved>,
    bounds: Option<geometry::Bounds>,
    viewport: [f64; 2],
) -> Result<Option<Paint>, Error> {
    let Some(id) = reference(s)? else {
        return paint(s, opacity, current);
    };
    let g = definitions
        .get(id)
        .ok_or_else(|| invalid(format!("Missing gradient: {id}")))?;
    if g.stops.is_empty() {
        return Ok(None);
    }
    let stops: Vec<_> = g
        .stops
        .iter()
        .map(|s| {
            let mut s = s.clone();
            s.color[3] = (s.color[3] as f64 * opacity).round() as u8;
            s
        })
        .collect();
    if stops.len() == 1 {
        return Ok(Some(Paint::Solid(stops[0].color)));
    }
    let basis = if g.bounding_box { [1.0, 1.0] } else { viewport };
    let coord = |name: &str, axis: usize| g.coordinates[name].value(basis[axis]);
    let transform = geometry::multiply(
        if g.bounding_box {
            bbox_matrix(bounds)?
        } else {
            identity()
        },
        g.transform,
    );
    let field = if g.radial {
        let center = [coord("cx", 0), coord("cy", 1)];
        for (key, axis) in [("fx", 0), ("fy", 1)] {
            if let Some(f) = g.coordinates.get(key)
                && f.value(basis[axis]) != center[axis]
            {
                return Err(unsupported(
                    "Off-center radial gradient focus is not yet supported",
                ));
            }
        }
        let radius = g.coordinates["r"].value(basis[0].hypot(basis[1]) / 2.0f64.sqrt());
        if radius < 0.0 {
            return Err(invalid("Radial gradient radius must not be negative"));
        }
        if radius == 0.0 {
            return Ok(Some(Paint::Solid(stops.last().unwrap().color)));
        }
        Field::Radial {
            center,
            radius,
            stops,
            spread: g.spread,
            space: g.space,
            transform,
        }
    } else {
        let start = [coord("x1", 0), coord("y1", 1)];
        let end = [coord("x2", 0), coord("y2", 1)];
        if start == end {
            return Ok(Some(Paint::Solid(stops.last().unwrap().color)));
        }
        Field::Linear {
            start,
            end,
            stops,
            spread: g.spread,
            space: g.space,
            transform,
        }
    };
    let paint = Paint::Field(field);
    crate::paint::validate(&paint)?;
    Ok(Some(paint))
}
