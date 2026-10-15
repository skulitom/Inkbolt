//! Original descendant-text collection and character-addressed SVG placement.
use super::*;

pub(in crate::svg_import) struct Context<'a> {
    pub styles: &'a styles::Sheet,
    pub scopes: &'a scopes::Scopes,
    pub control: &'a crate::control::Control,
}

struct Element<'a> {
    node: Node<'a, 'a>,
    style: Style,
    parent: Option<usize>,
    coordinates: [Vec<f64>; 4],
    members: Vec<usize>,
}
#[derive(Clone, Copy)]
struct Character {
    value: char,
    owner: usize,
    leaf: usize,
}
struct Collected<'a> {
    elements: Vec<Element<'a>>,
    characters: Vec<Character>,
    pending_space: Option<Character>,
}

fn lengths(value: &str, em: f64, basis: f64) -> Result<Vec<f64>, Error> {
    let mut result = Vec::new();
    for part in value.split(',') {
        if part.trim().is_empty() {
            return Err(invalid("Empty SVG text coordinate list member"));
        }
        for token in part.split_ascii_whitespace() {
            let value = relative_length(token, em, basis)?;
            if !value.is_finite() {
                return Err(invalid("Nonfinite SVG text coordinate"));
            }
            result.push(value);
            if result.len() > text::MAX_TEXT_CHARS {
                return Err(Error::new(
                    "RESOURCE_LIMIT",
                    "SVG text coordinate list exceeds the character limit",
                ));
            }
        }
    }
    Ok(result)
}

pub(super) fn needed(node: Node<'_, '_>) -> Result<bool, Error> {
    if node.children().any(|n| n.has_tag_name("tspan")) {
        return Ok(true);
    }
    for name in ["x", "y", "dx", "dy"] {
        if let Some(value) = node.attribute(name)
            && lengths(value, 1.0, 1.0)?.len() > 1
        {
            return Ok(true);
        }
    }
    Ok(false)
}

fn anchor(style: &Style) -> text::Anchor {
    match style.text.align {
        text::Align::Left | text::Align::Start => text::Anchor::Start,
        text::Align::Center => text::Anchor::Middle,
        text::Align::Right | text::Align::End => text::Anchor::End,
    }
}

fn check_style(style: &Style) -> Result<(), Error> {
    if style.stroke != "none" && style.width != 0.0 {
        return Err(unsupported("Stroked SVG text is not yet supported"));
    }
    if style.rule != FillRule::Nonzero {
        return Err(unsupported("SVG text currently requires nonzero fill-rule"));
    }
    if style.space != crate::paint::Interpolation::Srgb {
        return Err(unsupported("Text compositing requires sRGB"));
    }
    Ok(())
}

impl<'a> Collected<'a> {
    fn emit(&mut self, character: Character) -> Result<(), Error> {
        if self.characters.len() == text::MAX_TEXT_CHARS {
            return Err(Error::new(
                "RESOURCE_LIMIT",
                "SVG text exceeds character limit",
            ));
        }
        self.characters.push(character);
        Ok(())
    }
    fn text(&mut self, value: &str, owner: usize, leaf: usize) -> Result<(), Error> {
        let style = self.elements[owner].style.text.clone();
        let preserve = style.css_space.unwrap_or(style.preserve);
        for value in value.chars() {
            let value = match (value, style.css_space, style.preserve) {
                ('\n' | '\r' | '\t', Some(true), _) => {
                    return Err(unsupported(
                        "Preserved SVG line breaks and tab stops are not yet supported",
                    ));
                }
                ('\n' | '\r', None, false) if !style.modern_whitespace => continue,
                ('\n' | '\r' | '\t', _, _) => ' ',
                _ => value,
            };
            let character = Character { value, owner, leaf };
            if value == ' ' && !preserve {
                if self.pending_space.is_none()
                    && self.characters.last().is_some_and(|c| c.value != ' ')
                {
                    self.pending_space = Some(character);
                }
            } else {
                if let Some(space) = self.pending_space.take() {
                    self.emit(space)?;
                }
                self.emit(character)?;
            }
        }
        Ok(())
    }
    fn visit(
        &mut self,
        node: Node<'a, 'a>,
        style: Style,
        parent: Option<usize>,
        displayed: bool,
        interpretation: ([f64; 2], bool),
        context: &Context<'a>,
    ) -> Result<(), Error> {
        let (viewport, template) = interpretation;
        context.control.check()?;
        check_style(&style).map_err(|e| reuse::located(e, node))?;
        let mut coordinates: [Vec<f64>; 4] = Default::default();
        for (axis, name) in ["x", "y", "dx", "dy"].iter().enumerate() {
            if let Some(value) = node.attribute(*name) {
                coordinates[axis] = lengths(
                    value,
                    if template { 1.0 } else { style.text.size },
                    if template { 1.0 } else { viewport[axis % 2] },
                )
                .map_err(|e| reuse::located(e, node))?;
            }
        }
        let owner = self.elements.len();
        self.elements.push(Element {
            node,
            style: style.clone(),
            parent,
            coordinates,
            members: vec![],
        });
        let mut title = false;
        for child in node.children() {
            context.control.check()?;
            if child.is_text() {
                if displayed {
                    self.text(child.text().unwrap_or(""), owner, child.range().start)
                        .map_err(|e| reuse::located(e, node))?;
                }
            } else if child.is_element() {
                match child.tag_name().name() {
                    "title" | "desc" => {
                        if child.attributes().len() != 0 || child.children().any(|n| n.is_element())
                        {
                            return Err(reuse::located(
                                unsupported("Text descriptions require plain text"),
                                child,
                            ));
                        }
                        if child.has_tag_name("title") {
                            if title {
                                return Err(reuse::located(
                                    unsupported("At most one title per text element is supported"),
                                    child,
                                ));
                            }
                            title = true;
                        }
                    }
                    "tspan" => {
                        let props = properties(child, &["x", "y", "dx", "dy"], context.styles)
                            .map_err(|e| reuse::located(e, child))?;
                        // These need separate compositing/geometry owners, not
                        // multiplication into per-glyph color or ignored fields.
                        if child.has_attribute("transform")
                            || props
                                .get("opacity")
                                .map(|v| unit_interval(v))
                                .transpose()
                                .map_err(|e| reuse::located(e, child))?
                                .is_some_and(|v| v != 1.0)
                            || props.get("clip-path").is_some_and(|v| *v != "none")
                            || props.get("mask").is_some_and(|v| *v != "none")
                            || props.get("isolation").is_some_and(|v| *v != "auto")
                        {
                            return Err(reuse::located(
                                unsupported(
                                    "Span transforms, opacity, clipping, masks and isolation require separate compositing owners",
                                ),
                                child,
                            ));
                        }
                        let next = context
                            .scopes
                            .styled(&style, &props, template)
                            .map_err(|e| reuse::located(e, child))?;
                        self.visit(
                            child,
                            next,
                            Some(owner),
                            displayed && props.get("display") != Some(&"none"),
                            interpretation,
                            context,
                        )?;
                    }
                    _ => {
                        return Err(reuse::located(
                            unsupported(
                                "SVG text children require tspan or plain descriptions; textPath is not yet supported",
                            ),
                            child,
                        ));
                    }
                }
            }
        }
        Ok(())
    }
    fn collect(
        node: Node<'a, 'a>,
        style: &Style,
        viewport: [f64; 2],
        context: &Context<'a>,
        template: bool,
    ) -> Result<Self, Error> {
        let mut result = Self {
            elements: vec![],
            characters: vec![],
            pending_space: None,
        };
        result.visit(
            node,
            style.clone(),
            None,
            true,
            (viewport, template),
            context,
        )?;
        for (index, c) in result.characters.iter().enumerate() {
            let mut owner = Some(c.owner);
            while let Some(i) = owner {
                result.elements[i].members.push(index);
                owner = result.elements[i].parent;
            }
        }
        Ok(result)
    }
}

pub(in crate::svg_import) fn validate_template<'a>(
    node: Node<'a, 'a>,
    style: &Style,
    context: &Context<'a>,
    refs: &mut definitions::TemplateReferences,
) -> Result<(), Error> {
    let collected = Collected::collect(node, style, [1.0, 1.0], context, true)?;
    for element in &collected.elements {
        refs.record(&element.style, None)?;
    }
    Ok(())
}

fn native_style(
    style: &Style,
    document: &mut Document,
    fonts: &mut Fonts,
) -> Result<text::Style, Error> {
    Ok(text::Style {
        font_id: fonts.select(&style.text, document)?,
        fallback_fonts: vec![],
        font_variations: Default::default(),
        features: Default::default(),
        language: None,
        size: style.text.size,
        fill: paint(&style.fill, style.fill_opacity, style.color)?.unwrap_or(Paint::Solid([0; 4])),
        tracking: 0.0,
        horizontal_scale: 1.0,
        vertical_scale: 1.0,
        baseline_shift: 0.0,
    })
}

pub(super) fn content<'a>(
    node: Node<'a, 'a>,
    style: &Style,
    document: &mut Document,
    fonts: &mut Fonts,
    viewport: [f64; 2],
    context: &Context<'a>,
) -> Result<Imported, Error> {
    let collected = Collected::collect(node, style, viewport, context, false)?;
    let characters = &collected.characters;
    let source: String = characters.iter().map(|c| c.value).collect();
    let mut positions: Vec<_> = (0..characters.len())
        .map(|index| text::CharacterPosition {
            index,
            x: None,
            y: None,
            dx: 0.0,
            dy: 0.0,
            anchor: None,
        })
        .collect();
    for element in &collected.elements {
        for (axis, values) in element.coordinates.iter().enumerate() {
            for (&index, &value) in element.members.iter().zip(values) {
                let p = &mut positions[index];
                match axis {
                    0 => p.x = Some(value),
                    1 => p.y = Some(value),
                    2 => p.dx = value,
                    _ => p.dy = value,
                };
            }
        }
    }
    for p in &mut positions {
        if p.index == 0 || p.x.is_some() || p.y.is_some() {
            p.anchor = Some(anchor(&collected.elements[characters[p.index].owner].style));
        }
    }
    positions.retain(|p| {
        p.x.is_some() || p.y.is_some() || p.dx != 0.0 || p.dy != 0.0 || p.anchor.is_some()
    });
    let base = characters
        .first()
        .map_or(style, |c| &collected.elements[c.owner].style);
    let base_node = characters
        .first()
        .map_or(node, |c| collected.elements[c.owner].node);
    let mut frame = text::Frame {
        text: source,
        width: MAX_COORDINATE,
        height: MAX_COORDINATE,
        style: native_style(base, document, fonts).map_err(|e| reuse::located(e, base_node))?,
        ranges: vec![],
        align: text::Align::Left,
        direction: text::Direction::Ltr,
        bidi: text::Bidi::SingleRun,
        wrap: false,
        leading: None,
        first_baseline: None,
        overflow: text::Overflow::Visible,
        path: None,
        positioning: Some(text::Positioning {
            origin: [0.0, 0.0],
            anchor: anchor(style),
            positions,
        }),
    };
    let boundaries = text::boundaries(&frame.text);
    for p in &frame.positioning.as_ref().unwrap().positions {
        if (p.x.is_some() || p.y.is_some()) && !boundaries.contains(&p.index) {
            return Err(reuse::located(
                unsupported("Absolute SVG text positions inside a grapheme are not yet supported"),
                collected.elements[characters[p.index].owner].node,
            ));
        }
    }
    let mut range_styles: Vec<Style> = Vec::new();
    let mut start = 0;
    while start < characters.len() {
        context.control.check()?;
        let c = characters[start];
        let mut end = start + 1;
        while end < characters.len()
            && characters[end].owner == c.owner
            && characters[end].leaf == c.leaf
        {
            end += 1;
        }
        let style = &collected.elements[c.owner].style;
        let native = native_style(style, document, fonts)
            .map_err(|e| reuse::located(e, collected.elements[c.owner].node))?;
        if !boundaries.contains(&start) {
            let previous = range_styles.last().unwrap();
            if frame.ranges.last().unwrap().style != native
                || previous.fill != style.fill
                || previous.fill_opacity != style.fill_opacity
                || previous.color != style.color
                || previous.visible != style.visible
            {
                return Err(reuse::located(
                    unsupported("Different SVG styles inside one grapheme are not yet supported"),
                    collected.elements[c.owner].node,
                ));
            }
            frame.ranges.last_mut().unwrap().end = end;
            start = end;
            continue;
        }
        if frame.ranges.len() == text::MAX_TEXT_RANGES {
            return Err(Error::new(
                "RESOURCE_LIMIT",
                "SVG text exceeds the native style-range limit",
            ));
        }
        frame.ranges.push(text::StyleRange {
            start,
            end,
            style: native,
        });
        range_styles.push(style.clone());
        start = end;
    }
    text::validate(&frame, document, identity())?;
    let layout = text::layout(&frame, document, &fonts.cache)?;
    let chars: Vec<_> = frame.text.chars().collect();
    let mut bounds = None;
    for glyph in &layout.glyphs {
        if chars[glyph.start..glyph.end].iter().all(|&c| c == ' ') && glyph.ink_bounds.is_some() {
            return Err(unsupported(
                "Visible whitespace glyph outlines cannot be imported",
            ));
        }
        let s = frame
            .ranges
            .iter()
            .find(|r| r.start <= glyph.start && glyph.start < r.end)
            .map_or(&frame.style, |r| &r.style);
        let face = fonts::parsed(
            &document.fonts[&glyph.font_id],
            &fonts.cache[&glyph.font_id],
        )?;
        let scale = s.size / face.units_per_em() as f64;
        let b = [
            glyph.origin[0],
            glyph.origin[1] - face.ascender() as f64 * scale,
            glyph.origin[0] + glyph.advance,
            glyph.origin[1] - face.descender() as f64 * scale,
        ];
        bounds = Some(bounds.map_or(b, |old| crate::scene::union(old, b)));
    }
    let mut placement = identity();
    if let Some(b) = bounds {
        placement[4] = b[0];
        placement[5] = b[1];
        frame.width = (b[2] - b[0]).max(0.001);
        frame.height = (b[3] - b[1]).max(0.001);
        let positions = frame.positioning.as_mut().unwrap();
        positions.origin = [-b[0], -b[1]];
        for p in &mut positions.positions {
            if let Some(x) = p.x.as_mut() {
                *x -= b[0];
            }
            if let Some(y) = p.y.as_mut() {
                *y -= b[1];
            }
        }
        bounds = Some([0.0, 0.0, b[2] - b[0], b[3] - b[1]]);
    } else {
        frame.width = 0.001;
        frame.height = 0.001;
    }
    text::validate(&frame, document, identity())?;
    let mappings=collected.elements.iter().skip(1).map(|element| {
        let empty=characters.partition_point(|c|c.leaf<element.node.range().end);
        let start=element.members.first().copied().unwrap_or(empty);let end=element.members.last().map_or(start,|i|i+1);
        json!({"source_id":element.node.attribute("id"),"element":"tspan","byte_offset":element.node.range().start,"text_range":[start,end],"range_units":"Unicode_scalars"})
    }).collect();
    Ok(Imported {
        frame,
        placement,
        bounds,
        range_styles,
        mappings,
        template_styles: collected.elements.into_iter().map(|e| e.style).collect(),
    })
}
