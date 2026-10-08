//! Explicit font binding and original single-line SVG text placement.
use super::*;
use crate::{fonts, text};
use std::path::Path;

pub(super) const PROPERTIES: &[&str] = &[
    "font-family",
    "font-size",
    "font-style",
    "font-weight",
    "text-anchor",
    "direction",
    "writing-mode",
    "dominant-baseline",
    "letter-spacing",
    "white-space",
];

#[derive(Clone, Copy, Debug, Default, Deserialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum FaceStyle {
    #[default]
    Normal,
    Italic,
    Oblique,
}
fn normal_weight() -> u16 {
    400
}
#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct FontBinding {
    pub family: String,
    pub font_id: String,
    pub font: fonts::Font,
    #[serde(default = "normal_weight")]
    pub weight: u16,
    #[serde(default)]
    pub style: FaceStyle,
}

pub(super) struct Fonts {
    bindings: Vec<FontBinding>,
    root: Option<PathBuf>,
    cache: fonts::Cache,
}
impl Fonts {
    pub fn new(bindings: Vec<FontBinding>, root: Option<&Path>) -> Result<Self, Error> {
        if bindings.len() > fonts::MAX_FONTS {
            return Err(Error::new(
                "RESOURCE_LIMIT",
                "SVG font binding limit exceeded",
            ));
        }
        for (i, b) in bindings.iter().enumerate() {
            fonts::validate(&b.font)?;
            if !valid_id(&b.font_id)
                || b.family.trim() != b.family
                || b.family.is_empty()
                || b.family.len() > 256
                || b.family.chars().any(char::is_control)
                || b.weight < 100
                || b.weight > 900
                || b.weight % 100 != 0
            {
                return Err(invalid(
                    "Invalid SVG font binding identity, family or weight",
                ));
            }
            for earlier in &bindings[..i] {
                if (earlier.family.eq_ignore_ascii_case(&b.family)
                    && earlier.weight == b.weight
                    && earlier.style == b.style)
                    || (earlier.font_id == b.font_id && earlier.font != b.font)
                {
                    return Err(invalid("Duplicate or conflicting SVG font binding"));
                }
            }
        }
        Ok(Self {
            bindings,
            root: root.map(Path::to_owned),
            cache: Default::default(),
        })
    }
    fn select(&mut self, style: &LabelStyle, document: &mut Document) -> Result<String, Error> {
        let binding = style
            .families
            .iter()
            .find_map(|family| {
                self.bindings.iter().find(|b| {
                    b.family.eq_ignore_ascii_case(family)
                        && b.weight == style.weight
                        && b.style == style.face_style
                })
            })
            .ok_or_else(|| {
                Error::new(
                    "SVG_FONT_NOT_BOUND",
                    "No explicit font binding matches the requested family, weight and style",
                )
            })?;
        let id = binding.font_id.clone();
        if !self.cache.contains_key(&id) {
            self.cache.insert(
                id.clone(),
                fonts::load(&binding.font, self.root.as_deref()).map_err(|e| e.at_font(&id))?,
            );
        }
        document.fonts.insert(id.clone(), binding.font.clone());
        Ok(id)
    }
}

#[derive(Clone)]
pub(super) struct LabelStyle {
    families: Vec<String>,
    size: f64,
    weight: u16,
    face_style: FaceStyle,
    align: text::Align,
    preserve: bool,
    css_space: Option<bool>,
    pub modern_whitespace: bool,
}
impl Default for LabelStyle {
    fn default() -> Self {
        Self {
            families: vec!["serif".into()],
            size: 16.0,
            weight: 400,
            face_style: FaceStyle::Normal,
            align: text::Align::Left,
            preserve: false,
            css_space: None,
            modern_whitespace: false,
        }
    }
}

fn families(value: &str) -> Result<Vec<String>, Error> {
    let mut names = Vec::new();
    let mut part = String::new();
    let mut quote = None;
    for c in value.chars() {
        if c == '\\' || c.is_control() {
            return Err(unsupported(
                "Escaped/control font-family syntax is unsupported",
            ));
        }
        if let Some(q) = quote {
            part.push(c);
            if c == q {
                quote = None;
            }
        } else if c == '\'' || c == '"' {
            quote = Some(c);
            part.push(c);
        } else if c == ',' {
            names.push(std::mem::take(&mut part));
        } else {
            part.push(c);
        }
    }
    if quote.is_some() {
        return Err(invalid("Unclosed font-family quote"));
    }
    names.push(part);
    if names.len() > fonts::MAX_FONTS {
        return Err(unsupported("Font-family list exceeds eight families"));
    }
    names
        .into_iter()
        .map(|name| {
            let name = name.trim();
            let result = if name.starts_with(['\'', '"']) {
                if name.len() < 2
                    || name.as_bytes().first() != name.as_bytes().last()
                    || name[1..name.len() - 1].contains(['\'', '"'])
                {
                    return Err(invalid("Malformed quoted font family"));
                }
                name[1..name.len() - 1].to_owned()
            } else {
                if name
                    .chars()
                    .any(|c| !(c.is_alphanumeric() || matches!(c, ' ' | '-' | '_')))
                {
                    return Err(unsupported("Unsupported font-family syntax"));
                }
                name.split_whitespace().collect::<Vec<_>>().join(" ")
            };
            if result.is_empty() || result.len() > 256 {
                return Err(invalid("Empty or excessive font family"));
            }
            Ok(result)
        })
        .collect()
}
fn relative_length(value: &str, em: f64, percent: f64) -> Result<f64, Error> {
    if let Some(n) = value.strip_suffix("em") {
        Ok(number(n)? * em)
    } else if let Some(n) = value.strip_suffix('%') {
        Ok(number(n)? * percent / 100.0)
    } else {
        length(value)
    }
}
pub(super) fn styled(parent: &LabelStyle, p: &BTreeMap<&str, &str>) -> Result<LabelStyle, Error> {
    let mut s = parent.clone();
    for (&k, &v) in p {
        if v == "inherit" && k != "xml:space" {
            continue;
        }
        match k {
            "font-family" => s.families = families(v)?,
            "font-size" => {
                s.size = relative_length(v, parent.size, parent.size)?;
                if !(0.01..=1024.0).contains(&s.size) {
                    return Err(unsupported(
                        "Font size must resolve to 0.01..1024 user units",
                    ));
                }
            }
            "font-style" => {
                s.face_style = match v {
                    "normal" => FaceStyle::Normal,
                    "italic" => FaceStyle::Italic,
                    "oblique" => FaceStyle::Oblique,
                    _ => return Err(unsupported("Unsupported font-style")),
                }
            }
            "font-weight" => {
                s.weight = match v {
                    "normal" | "400" => 400,
                    "bold" | "700" => 700,
                    "100" | "200" | "300" | "500" | "600" | "800" | "900" => v.parse().unwrap(),
                    _ => {
                        return Err(unsupported(
                            "Font weight requires normal, bold or 100..900 in steps of 100",
                        ));
                    }
                }
            }
            "text-anchor" => {
                s.align = match v {
                    "start" => text::Align::Left,
                    "middle" => text::Align::Center,
                    "end" => text::Align::Right,
                    _ => return Err(unsupported("Unsupported text-anchor")),
                }
            }
            "xml:space" => {
                s.preserve = match v {
                    "default" => false,
                    "preserve" => true,
                    _ => return Err(invalid("xml:space requires default or preserve")),
                }
            }
            "white-space" => {
                s.css_space = Some(match v {
                    "normal" => false,
                    "pre" => true,
                    _ => return Err(unsupported("white-space currently requires normal or pre")),
                })
            }
            "direction" if v != "ltr" => {
                return Err(unsupported(
                    "SVG text currently requires left-to-right layout",
                ));
            }
            "writing-mode" if !["lr", "lr-tb", "horizontal-tb"].contains(&v) => {
                return Err(unsupported("Only horizontal SVG text is supported"));
            }
            "dominant-baseline" if !["auto", "alphabetic"].contains(&v) => {
                return Err(unsupported(
                    "Only alphabetic SVG text baselines are supported",
                ));
            }
            "letter-spacing" if v != "normal" && length(v)? != 0.0 => {
                return Err(unsupported(
                    "Nonzero SVG letter spacing is not yet supported",
                ));
            }
            _ => (),
        }
    }
    Ok(s)
}

pub(super) struct Imported {
    pub frame: text::Frame,
    pub placement: Matrix,
    pub bounds: Option<geometry::Bounds>,
}
pub(super) fn content(
    node: Node<'_, '_>,
    style: &Style,
    document: &mut Document,
    fonts: &mut Fonts,
    viewport: [f64; 2],
) -> Result<Imported, Error> {
    if style.stroke != "none" && style.width != 0.0 {
        return Err(unsupported("Stroked SVG text is not yet supported"));
    }
    if style.rule != FillRule::Nonzero {
        return Err(unsupported("SVG text currently requires nonzero fill-rule"));
    }
    for child in node.children().filter(|c| c.is_element()) {
        if !["title", "desc"].contains(&child.tag_name().name()) {
            return Err(unsupported(
                "SVG text children, including tspan and textPath, are not yet supported",
            ));
        }
    }
    let raw = node
        .children()
        .filter(|n| n.is_text())
        .filter_map(|n| n.text())
        .collect::<String>();
    let s = &style.text;
    let mut normalized = String::new();
    for c in raw.chars() {
        match (c, s.css_space, s.preserve) {
            ('\n' | '\r' | '\t', Some(true), _) => {
                return Err(unsupported(
                    "Preserved SVG line breaks and tab stops are not yet supported",
                ));
            }
            ('\n' | '\r', None, false) if !s.modern_whitespace => (),
            ('\n' | '\r' | '\t', _, _) => normalized.push(' '),
            _ => normalized.push(c),
        }
    }
    if !s.css_space.unwrap_or(s.preserve) {
        normalized = normalized
            .split(' ')
            .filter(|s| !s.is_empty())
            .collect::<Vec<_>>()
            .join(" ");
    }
    let font_id = fonts.select(s, document)?;
    let mut frame = text::Frame {
        text: normalized,
        width: MAX_COORDINATE,
        height: MAX_COORDINATE,
        style: text::Style {
            fallback_fonts: Vec::new(),
            font_variations: Default::default(),
            features: Default::default(),
            language: None,
            font_id: font_id.clone(),
            size: s.size,
            fill: paint(&style.fill, style.fill_opacity, style.color)?
                .unwrap_or(Paint::Solid([0; 4])),
            tracking: 0.0,
        },
        ranges: vec![],
        align: text::Align::Left,
        direction: text::Direction::Ltr,
        bidi: text::Bidi::SingleRun,
        wrap: false,
        leading: None,
        overflow: text::Overflow::Visible,
        path: None,
    };
    text::validate(&frame, document, identity())?;
    let layout = text::layout(&frame, document, &fonts.cache)?;
    let face = fonts::parsed(&document.fonts[&font_id], &fonts.cache[&font_id])?;
    let ascent = face.ascender() as f64 * s.size / face.units_per_em() as f64;
    let descent = face.descender() as f64 * s.size / face.units_per_em() as f64;
    frame.width = layout.lines[0].advance.max(0.001);
    frame.height = (ascent - descent).max(0.001);
    frame.align = s.align;
    text::validate(&frame, document, identity())?;
    let layout = text::layout(&frame, document, &fonts.cache)?;
    let coordinate = |name, axis| {
        node.attribute(name)
            .map(|v| relative_length(v.trim(), s.size, viewport[axis]))
            .unwrap_or(Ok(0.0))
    };
    let factor = match s.align {
        text::Align::Left | text::Align::Start => 0.0,
        text::Align::Center => 0.5,
        text::Align::Right | text::Align::End => 1.0,
    };
    let placement = [
        1.0,
        0.0,
        0.0,
        1.0,
        coordinate("x", 0)? + coordinate("dx", 0)? - frame.width * factor,
        coordinate("y", 1)? + coordinate("dy", 1)? - layout.lines[0].baseline,
    ];
    let chars = frame.text.chars().collect::<Vec<_>>();
    let mut bounds = None;
    for glyph in &layout.glyphs {
        if chars[glyph.start..glyph.end].iter().all(|&c| c == ' ') && glyph.ink_bounds.is_some() {
            return Err(unsupported(
                "Visible whitespace glyph outlines cannot be imported",
            ));
        }
        let b = [
            glyph.origin[0],
            glyph.origin[1] - ascent,
            glyph.origin[0] + glyph.advance,
            glyph.origin[1] - descent,
        ];
        bounds = Some(bounds.map_or(b, |old| crate::scene::union(old, b)));
    }
    Ok(Imported {
        frame,
        placement,
        bounds,
    })
}
