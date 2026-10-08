//! Editable text, explicit shaping and original bounded paragraph placement.
use crate::{
    Document, Error, fonts,
    geometry::{self, Bounds},
    model::*,
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use unicode_segmentation::UnicodeSegmentation;
pub mod bidi;
pub mod flow;
mod shaping;
use shaping::{Analysis, shape};
pub const MAX_TEXT_CHARS: usize = 4096;
pub const MAX_TEXT_RANGES: usize = 64;
pub const MAX_GLYPHS: usize = 8192;
pub const MAX_OUTLINE_COMMANDS: usize = 131072;
const MAX_SHAPING_WORK: usize = 1_048_576;

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Direction {
    #[default]
    Ltr,
    Rtl,
    Auto,
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Bidi {
    #[default]
    SingleRun,
    Unicode,
}
impl Bidi {
    fn is_single_run(&self) -> bool {
        *self == Self::SingleRun
    }
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Align {
    #[default]
    Left,
    Center,
    Right,
    Start,
    End,
}
impl Align {
    fn offset(self, width: f64, advance: f64, direction: Direction) -> f64 {
        match self {
            Self::Center => (width - advance) / 2.0,
            Self::Right => width - advance,
            Self::Start if direction == Direction::Rtl => width - advance,
            Self::End if direction != Direction::Rtl => width - advance,
            _ => 0.0,
        }
    }
}
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Overflow {
    #[default]
    Error,
    Clip,
    Visible,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Style {
    pub font_id: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub fallback_fonts: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub language: Option<String>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub font_variations: BTreeMap<String, fonts::Coordinates>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub features: BTreeMap<String, u32>,
    pub size: f64,
    pub fill: Paint,
    #[serde(default)]
    pub tracking: f64,
}
impl Style {
    pub fn font_ids(&self) -> impl Iterator<Item = &String> {
        std::iter::once(&self.font_id).chain(&self.fallback_fonts)
    }
    fn face<'a>(
        &self,
        id: &str,
        document: &Document,
        cache: &'a fonts::Cache,
    ) -> Result<rustybuzz::Face<'a>, Error> {
        fonts::instance(
            &document.fonts[id],
            &cache[id],
            self.font_variations.get(id),
        )
        .map_err(|e| e.at_font(id))
    }
    fn shaping_features(&self) -> BTreeMap<String, u32> {
        let mut result = self.features.clone();
        if self.tracking != 0.0 {
            result.entry("liga".into()).or_insert(0);
        }
        result
    }
    fn coordinates(&self, id: &str) -> fonts::Coordinates {
        self.font_variations.get(id).cloned().unwrap_or_default()
    }
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct StyleRange {
    pub start: usize,
    pub end: usize,
    pub style: Style,
}
fn yes() -> bool {
    true
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Frame {
    pub text: String,
    pub width: f64,
    pub height: f64,
    pub style: Style,
    #[serde(default)]
    pub ranges: Vec<StyleRange>,
    #[serde(default)]
    pub align: Align,
    #[serde(default)]
    pub direction: Direction,
    #[serde(default, skip_serializing_if = "Bidi::is_single_run")]
    pub bidi: Bidi,
    #[serde(default = "yes")]
    pub wrap: bool,
    #[serde(default)]
    pub leading: Option<f64>,
    #[serde(default)]
    pub overflow: Overflow,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub path: Option<crate::path_text::Baseline>,
}
pub fn styles(frame: &Frame) -> impl Iterator<Item = &Style> {
    std::iter::once(&frame.style).chain(frame.ranges.iter().map(|r| &r.style))
}
pub fn boundaries(text: &str) -> BTreeSet<usize> {
    let mut n = 0;
    let mut b = BTreeSet::from([0]);
    for g in text.graphemes(true) {
        n += g.chars().count();
        b.insert(n);
    }
    b
}
pub fn validate(
    frame: &Frame,
    document: &Document,
    world: Matrix,
) -> Result<(usize, usize, usize), Error> {
    if let Some(path) = &frame.path {
        crate::path_text::validate(path)?;
        if frame.wrap || frame.leading.is_some() || frame.text.contains('\n') {
            return Err(Error::new(
                "UNSUPPORTED",
                "Path text requires one line, wrap:false and no paragraph leading",
            ));
        }
    }
    let count = frame.text.chars().count();
    if count > MAX_TEXT_CHARS || frame.ranges.len() > MAX_TEXT_RANGES {
        return Err(limit("Text exceeds character or style-range limits"));
    }
    if frame.direction == Direction::Auto && frame.bidi != Bidi::Unicode {
        return Err(invalid(
            "Automatic paragraph direction requires bidi:unicode",
        ));
    }
    if frame.text.chars().any(|c| {
        (c.is_control() && c != '\n')
            || matches!(c, '\u{fffe}' | '\u{ffff}' | '\u{2028}' | '\u{2029}')
            || (frame.bidi == Bidi::SingleRun && bidi::is_control(c))
    }) {
        return Err(Error::new(
            "UNSUPPORTED",
            "Text uses LF paragraph breaks; other controls/separators are unsupported, and bidi marks require bidi:unicode",
        ));
    }
    for v in [frame.width, frame.height] {
        if !v.is_finite() || !(0.001..=MAX_COORDINATE).contains(&v) {
            return Err(invalid("Text frame extent must be in 0.001..=32768"));
        }
    }
    if frame
        .leading
        .is_some_and(|v| !v.is_finite() || !(0.001..=4096.0).contains(&v))
    {
        return Err(invalid("Text leading must be in 0.001..=4096"));
    }
    let mut pixels = 0;
    let mut samples = 0;
    for style in styles(frame) {
        if style.fallback_fonts.len() >= fonts::MAX_FONTS {
            return Err(limit("Text allows at most seven fallback fonts"));
        }
        if style.font_ids().collect::<BTreeSet<_>>().len() != style.fallback_fonts.len() + 1 {
            return Err(invalid(
                "Text font preference list must not repeat font IDs",
            ));
        }
        if style.font_ids().any(|id| !document.fonts.contains_key(id)) {
            return Err(invalid("Text refers to an undefined font"));
        }
        if style.font_variations.len() > fonts::MAX_FONTS
            || style.features.len() > fonts::MAX_FEATURES
        {
            return Err(limit(
                "Text style exceeds eight font instances or 64 feature controls",
            ));
        }
        for (id, values) in &style.font_variations {
            if !style.font_ids().any(|f| f == id) {
                return Err(invalid(
                    "Font variation keys must name a font in the style preference list",
                ));
            }
            fonts::validate_coordinates(values)?;
        }
        for feature in style.features.keys() {
            fonts::tag(feature)?;
        }
        if style.language.as_ref().is_some_and(|s| {
            s.len() > 64
                || s.split('-')
                    .any(|part| part.is_empty() || !part.bytes().all(|b| b.is_ascii_alphanumeric()))
        }) {
            return Err(invalid(
                "Text language must have nonempty ASCII alphanumeric subtags separated by hyphens, at most 64 bytes",
            ));
        }
        if !style.size.is_finite()
            || !(0.01..=1024.0).contains(&style.size)
            || !style.tracking.is_finite()
            || style.tracking.abs() > 1024.0
        {
            return Err(invalid("Text size or tracking exceeds supported limits"));
        }
        let (p, s) = crate::paint::validate(&style.fill)?;
        crate::paint::validate_world(&style.fill, world)?;
        pixels += p;
        samples += s;
    }
    let boundaries = boundaries(&frame.text);
    let mut previous = 0;
    for r in &frame.ranges {
        if r.start < previous
            || r.start >= r.end
            || r.end > count
            || !boundaries.contains(&r.start)
            || !boundaries.contains(&r.end)
        {
            return Err(invalid(
                "Text style ranges must be ordered, disjoint Unicode-scalar ranges on grapheme boundaries",
            ));
        }
        previous = r.end;
    }
    Ok((count, pixels, samples))
}
fn style_index(frame: &Frame, index: usize) -> usize {
    frame
        .ranges
        .iter()
        .position(|r| r.start <= index && index < r.end)
        .map_or(0, |i| i + 1)
}
fn style(frame: &Frame, index: usize) -> &Style {
    if index == 0 {
        &frame.style
    } else {
        &frame.ranges[index - 1].style
    }
}
pub fn revise(
    frame: &mut Frame,
    start: usize,
    end: usize,
    replacement: Option<&str>,
    new_style: Option<&Style>,
) -> Result<(), Error> {
    let b = boundaries(&frame.text);
    let chars: Vec<_> = frame.text.chars().collect();
    if start > end || end > chars.len() || !b.contains(&start) || !b.contains(&end) {
        return Err(invalid(
            "Text range must use Unicode-scalar indices at grapheme boundaries",
        ));
    }
    if replacement.is_none() && new_style.is_none() {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Text range edit needs replacement text or style",
        ));
    }
    let mut values: Vec<_> = chars
        .iter()
        .enumerate()
        .map(|(i, c)| (*c, style(frame, style_index(frame, i)).clone()))
        .collect();
    if let Some(replacement) = replacement {
        let inherited = new_style
            .unwrap_or_else(|| {
                if start < chars.len() {
                    style(frame, style_index(frame, start))
                } else {
                    &frame.style
                }
            })
            .clone();
        values.splice(
            start..end,
            replacement.chars().map(|c| (c, inherited.clone())),
        );
    } else if let Some(s) = new_style {
        for v in &mut values[start..end] {
            v.1 = s.clone();
        }
    }
    frame.text = values.iter().map(|v| v.0).collect();
    frame.ranges.clear();
    let mut i = 0;
    while i < values.len() {
        let mut j = i + 1;
        while j < values.len() && values[j].1 == values[i].1 {
            j += 1;
        }
        if values[i].1 != frame.style {
            frame.ranges.push(StyleRange {
                start: i,
                end: j,
                style: values[i].1.clone(),
            });
        }
        i = j;
    }
    Ok(())
}
#[derive(Clone, Debug, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum Generated {
    ListMarker { start: usize, end: usize },
    Hyphen { offset: usize },
}
#[derive(Clone, Debug, Serialize)]
pub struct Glyph {
    pub glyph_id: u16,
    pub font_id: String,
    pub script: String,
    pub direction: Direction,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub level: Option<u8>,
    #[serde(skip_serializing_if = "BTreeMap::is_empty")]
    pub variations: fonts::Coordinates,
    #[serde(skip_serializing_if = "BTreeMap::is_empty")]
    pub features: BTreeMap<String, u32>,
    pub start: usize,
    pub end: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub generated: Option<Generated>,
    pub origin: Point,
    pub advance: f64,
    pub ink_bounds: Option<Bounds>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub path: Option<crate::path_text::Placement>,
}
#[derive(Clone, Debug, Serialize)]
pub struct Line {
    pub start: usize,
    pub end: usize,
    pub baseline: f64,
    pub x: f64,
    pub advance: f64,
    pub direction: Direction,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub bidi: Option<bidi::Line>,
}
#[derive(Clone, Debug, Serialize)]
pub struct PaintedPath {
    pub geometry: Geometry,
    pub fill: Paint,
}
#[derive(Clone, Debug, Serialize)]
pub struct Layout {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub frame_clip: Option<Geometry>,
    pub lines: Vec<Line>,
    pub glyphs: Vec<Glyph>,
    pub ink_bounds: Option<Bounds>,
    pub overflowed: bool,
    pub paths: Vec<PaintedPath>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub baseline_path: Option<crate::path_text::Report>,
}
struct Shaped {
    id: u16,
    style: usize,
    font_id: String,
    script: String,
    direction: Direction,
    level: Option<u8>,
    start: usize,
    end: usize,
    x: f64,
    y: f64,
    advance: f64,
}
struct Builder {
    commands: Vec<PathCommand>,
    at: Point,
    origin: Point,
    scale: f64,
    limit: usize,
    exceeded: bool,
}
impl Builder {
    fn p(&self, x: f32, y: f32) -> Point {
        [
            self.origin[0] + x as f64 * self.scale,
            self.origin[1] - y as f64 * self.scale,
        ]
    }
    fn push(&mut self, c: PathCommand) {
        if self.commands.len() < self.limit {
            self.commands.push(c);
        } else {
            self.exceeded = true;
        }
    }
}
impl rustybuzz::ttf_parser::OutlineBuilder for Builder {
    fn move_to(&mut self, x: f32, y: f32) {
        let p = self.p(x, y);
        self.push(PathCommand::Move { to: p });
        self.at = p;
    }
    fn line_to(&mut self, x: f32, y: f32) {
        let p = self.p(x, y);
        self.push(PathCommand::Line { to: p });
        self.at = p;
    }
    fn quad_to(&mut self, x1: f32, y1: f32, x: f32, y: f32) {
        let c = self.p(x1, y1);
        let p = self.p(x, y);
        self.push(PathCommand::Cubic {
            control1: [
                self.at[0] + (c[0] - self.at[0]) * 2.0 / 3.0,
                self.at[1] + (c[1] - self.at[1]) * 2.0 / 3.0,
            ],
            control2: [
                p[0] + (c[0] - p[0]) * 2.0 / 3.0,
                p[1] + (c[1] - p[1]) * 2.0 / 3.0,
            ],
            to: p,
        });
        self.at = p;
    }
    fn curve_to(&mut self, x1: f32, y1: f32, x2: f32, y2: f32, x: f32, y: f32) {
        let p = self.p(x, y);
        self.push(PathCommand::Cubic {
            control1: self.p(x1, y1),
            control2: self.p(x2, y2),
            to: p,
        });
        self.at = p;
    }
    fn close(&mut self) {
        self.push(PathCommand::Close {});
    }
}
pub fn layout(frame: &Frame, document: &Document, cache: &fonts::Cache) -> Result<Layout, Error> {
    let analysis = Analysis::new(frame)?;
    if let Some(path) = &frame.path {
        return path_layout(frame, &analysis, path, document, cache);
    }
    let chars: Vec<_> = frame.text.chars().collect();
    let breaks = boundaries(&frame.text);
    let mut work = 0;
    let mut line_ranges = Vec::new();
    let mut start = 0;
    loop {
        let end = chars[start..]
            .iter()
            .position(|&c| c == '\n')
            .map_or(chars.len(), |i| start + i);
        if start == end {
            line_ranges.push((start, end));
        } else {
            let mut a = start;
            while a < end {
                let mut b = end;
                if frame.wrap
                    && shape(frame, &analysis, a, end, document, cache, &mut work)?.1 > frame.width
                {
                    let candidates: Vec<_> = breaks.range(a + 1..=end).copied().collect();
                    // Contextual substitutions can make prefix advances nonmonotone.
                    // Check longest candidates directly, including the reshaped word break.
                    b = candidates[0];
                    for &candidate in candidates.iter().rev().skip(1) {
                        if shape(frame, &analysis, a, candidate, document, cache, &mut work)?.1
                            <= frame.width
                        {
                            b = candidate;
                            break;
                        }
                    }
                    if let Some(space) = (a..b).rev().find(|&i| chars[i] == ' ')
                        && space > a
                        && breaks.contains(&space)
                        && shape(frame, &analysis, a, space, document, cache, &mut work)?.1
                            <= frame.width
                    {
                        b = space;
                    }
                }
                line_ranges.push((a, b));
                a = b;
                // Break spaces are retained in source text, but do not create visible line-leading gaps.
                if a < end && frame.wrap {
                    while a < end && chars[a] == ' ' && breaks.contains(&(a + 1)) {
                        a += 1;
                    }
                }
            }
        }
        if end == chars.len() {
            break;
        }
        start = end + 1;
    }
    let mut result = Layout {
        frame_clip: None,
        lines: Vec::new(),
        glyphs: Vec::new(),
        ink_bounds: None,
        overflowed: false,
        paths: Vec::new(),
        baseline_path: None,
    };
    let mut top = 0.0;
    let mut command_count = 0usize;
    for (start, end) in line_ranges {
        let (glyphs, advance) = shape(frame, &analysis, start, end, document, cache, &mut work)?;
        let mut ascent = 0.0f64;
        let mut natural = 0.0f64;
        let ids: BTreeSet<_> = glyphs
            .iter()
            .map(|g| (g.style, g.font_id.as_str()))
            .chain(std::iter::once((0, frame.style.font_id.as_str())))
            .collect();
        for (i, font_id) in ids {
            let s = style(frame, i);
            let face = s.face(font_id, document, cache)?;
            let scale = s.size / face.units_per_em() as f64;
            ascent = ascent.max(face.ascender() as f64 * scale);
            natural = natural.max(
                (face.ascender() as f64 - face.descender() as f64 + face.line_gap() as f64) * scale,
            );
        }
        let leading = frame.leading.unwrap_or(natural.max(0.001));
        let baseline = top + ascent;
        let direction = analysis.direction(frame, start);
        let x = frame.align.offset(frame.width, advance, direction);
        result.overflowed |= advance > frame.width + 1e-9 || top + natural > frame.height + 1e-9;
        result.lines.push(Line {
            start,
            end,
            baseline,
            x,
            advance,
            direction,
            bidi: analysis.line(start, end)?,
        });
        append_glyphs(
            frame,
            document,
            cache,
            &mut result,
            glyphs,
            [x, baseline],
            &mut command_count,
        )?;
        top += leading;
    }
    if let Some(b) = result.ink_bounds {
        result.overflowed |=
            b[0] < -1e-9 || b[1] < -1e-9 || b[2] > frame.width + 1e-9 || b[3] > frame.height + 1e-9;
    }
    if result.overflowed && frame.overflow == Overflow::Error {
        return Err(Error::new(
            "TEXT_OVERFLOW",
            "Text exceeds its declared frame; enlarge it or explicitly choose clip/visible overflow",
        ));
    }
    Ok(result)
}
fn append_glyphs(
    frame: &Frame,
    document: &Document,
    cache: &fonts::Cache,
    result: &mut Layout,
    glyphs: Vec<Shaped>,
    offset: Point,
    command_count: &mut usize,
) -> Result<(), Error> {
    for g in glyphs {
        let s = style(frame, g.style);
        let face = s.face(&g.font_id, document, cache)?;
        let origin = [offset[0] + g.x, offset[1] + g.y];
        let mut builder = Builder {
            commands: Vec::new(),
            at: [0.0, 0.0],
            origin,
            scale: s.size / face.units_per_em() as f64,
            limit: MAX_OUTLINE_COMMANDS - *command_count,
            exceeded: false,
        };
        let bounds = face.outline_glyph(rustybuzz::ttf_parser::GlyphId(g.id), &mut builder);
        if builder.exceeded {
            return Err(limit("Text outlines exceed command limit"));
        }
        let ink = if bounds.is_some() && !builder.commands.is_empty() {
            let geometry = Geometry::Path {
                commands: builder.commands,
            };
            geometry::validate_geometry(&geometry)?;
            let ink = geometry::bounds(&geometry, identity());
            *command_count += match &geometry {
                Geometry::Path { commands } => commands.len(),
                _ => 0,
            };
            // Distinct glyphs paint in order, including alpha where their
            // outlines overlap. Joining contours would change coverage.
            result.paths.push(PaintedPath {
                geometry,
                fill: s.fill.clone(),
            });
            result.ink_bounds = Some(
                result
                    .ink_bounds
                    .map_or(ink, |b| crate::scene::union(b, ink)),
            );
            Some(ink)
        } else {
            None
        };
        result.glyphs.push(Glyph {
            glyph_id: g.id,
            variations: s.coordinates(&g.font_id),
            features: s.shaping_features(),
            font_id: g.font_id,
            script: g.script,
            direction: g.direction,
            level: g.level,
            start: g.start,
            end: g.end,
            generated: None,
            origin,
            advance: g.advance,
            ink_bounds: ink,
            path: None,
        });
        if result.glyphs.len() > MAX_GLYPHS {
            return Err(limit("Text exceeds glyph limit"));
        }
    }
    Ok(())
}
fn path_layout(
    frame: &Frame,
    analysis: &Analysis,
    path: &crate::path_text::Baseline,
    document: &Document,
    cache: &fonts::Cache,
) -> Result<Layout, Error> {
    let mut measured = crate::path_text::Measured::new(path)?;
    let end = frame.text.chars().count();
    let mut work = 0;
    let (glyphs, advance) = shape(frame, analysis, 0, end, document, cache, &mut work)?;
    let direction = analysis.direction(frame, 0);
    let x = path.start_offset
        + frame
            .align
            .offset(measured.report.length, advance, direction);
    measured.report.start = x;
    let overflowed = !glyphs.is_empty() && (x < 0.0 || x + advance > measured.report.length + 1e-9);
    if overflowed && frame.overflow == Overflow::Error {
        return Err(Error::new(
            "TEXT_OVERFLOW",
            "Text advance exceeds its baseline; adjust the path/offset or choose clip/visible overflow",
        ));
    }
    let mut result = Layout {
        frame_clip: None,
        lines: vec![Line {
            start: 0,
            end,
            baseline: path.normal_offset,
            x,
            advance,
            direction,
            bidi: analysis.line(0, end)?,
        }],
        glyphs: Vec::new(),
        ink_bounds: None,
        overflowed,
        paths: Vec::new(),
        baseline_path: Some(measured.report.clone()),
    };
    let mut command_count = 0;
    for g in glyphs {
        let s = style(frame, g.style);
        let center = g.x + g.advance / 2.0;
        let distance = x + center;
        let drawn =
            frame.overflow != Overflow::Clip || (0.0..=measured.report.length).contains(&distance);
        let placement = measured.placement(center, distance, drawn)?;
        let origin = geometry::map(placement.transform, [g.x, g.y]);
        let mut ink = None;
        if drawn {
            let face = s.face(&g.font_id, document, cache)?;
            let mut builder = Builder {
                commands: Vec::new(),
                at: [0.0; 2],
                origin: [g.x, g.y],
                scale: s.size / face.units_per_em() as f64,
                limit: MAX_OUTLINE_COMMANDS - command_count,
                exceeded: false,
            };
            let bounds = face.outline_glyph(rustybuzz::ttf_parser::GlyphId(g.id), &mut builder);
            if builder.exceeded {
                return Err(limit("Path text outlines exceed command limit"));
            }
            if bounds.is_some() && !builder.commands.is_empty() {
                command_count += builder.commands.len();
                let mut geometry = Geometry::Path {
                    commands: builder.commands,
                };
                crate::path_text::map_geometry(&mut geometry, placement.transform);
                geometry::validate_geometry(&geometry)?;
                let b = geometry::bounds(&geometry, identity());
                result.ink_bounds = Some(
                    result
                        .ink_bounds
                        .map_or(b, |old| crate::scene::union(old, b)),
                );
                ink = Some(b);
                result.paths.push(PaintedPath {
                    geometry,
                    fill: s.fill.clone(),
                });
            }
        }
        result.glyphs.push(Glyph {
            glyph_id: g.id,
            variations: s.coordinates(&g.font_id),
            features: s.shaping_features(),
            font_id: g.font_id,
            script: g.script,
            direction: g.direction,
            level: g.level,
            start: g.start,
            end: g.end,
            generated: None,
            origin,
            advance: g.advance,
            ink_bounds: ink,
            path: Some(placement),
        });
    }
    Ok(result)
}
pub fn prepare(
    document: &Document,
    cache: &fonts::Cache,
) -> Result<BTreeMap<String, Layout>, Error> {
    let mut layouts = BTreeMap::new();
    let mut commands = 0;
    let mut glyphs = 0;
    let mut baseline_leaves = 0;
    let mut stories = BTreeMap::new();
    let mut story_commands = 0;
    let mut story_glyphs = 0;
    for item in &document.items {
        let result = match &item.content {
            Content::Text { frame } => {
                Some(layout(frame, document, cache).map_err(|e| e.at_item(&item.id))?)
            }
            Content::StoryFrame { story_id, slot_id } => {
                if !stories.contains_key(story_id) {
                    let story = flow::story(document, story_id)?;
                    let report =
                        flow::layout(story, document, cache).map_err(|e| e.at_item(&item.id))?;
                    for layout in report.slots.values() {
                        story_glyphs += layout.glyphs.len();
                        story_commands += layout
                            .paths
                            .iter()
                            .map(|p| match &p.geometry {
                                Geometry::Path { commands } => commands.len(),
                                _ => 0,
                            })
                            .sum::<usize>();
                    }
                    if story_glyphs > MAX_GLYPHS || story_commands > MAX_OUTLINE_COMMANDS {
                        return Err(limit(
                            "Computed stories exceed shared glyph or outline budget",
                        ));
                    }
                    if report.overset.is_some() && story.overset == flow::Overset::Error {
                        return Err(Error::new("STORY_OVERFLOW","Story has unplaced text; add flow space or explicitly retain the overset tail").at_item(&item.id));
                    }
                    stories.insert(story_id.clone(), report);
                }
                Some(stories[story_id].slots[slot_id].clone())
            }
            _ => None,
        };
        if let Some(result) = result {
            baseline_leaves += result.baseline_path.as_ref().map_or(0, |p| p.leaves);
            if baseline_leaves > crate::path_text::MAX_DOCUMENT_LEAVES {
                return Err(limit(
                    "Document text baselines exceed 65536 distance-table entries",
                ));
            }
            glyphs += result.glyphs.len();
            commands += result
                .paths
                .iter()
                .map(|p| match &p.geometry {
                    Geometry::Path { commands } => commands.len(),
                    _ => 0,
                })
                .sum::<usize>();
            if commands > MAX_OUTLINE_COMMANDS || glyphs > MAX_GLYPHS {
                return Err(limit("Document text exceeds glyph or outline budget"));
            }
            layouts.insert(item.id.clone(), result);
        }
    }
    Ok(layouts)
}

pub fn frame_geometry(frame: &Frame) -> Geometry {
    Geometry::Rect {
        x: 0.0,
        y: 0.0,
        width: frame.width,
        height: frame.height,
    }
}
pub(crate) fn clip_geometry(content: &Content, layout: &Layout) -> Option<Geometry> {
    layout.frame_clip.clone().or_else(|| match content {
        Content::Text { frame } if frame.overflow == Overflow::Clip && frame.path.is_none() => {
            Some(frame_geometry(frame))
        }
        _ => None,
    })
}

// Keep the original item as an isolated group, preserving its identity and appearance.
// New path IDs are deterministic, collision-free and disclosed in the returned snapshot.
pub(crate) fn outline_item(
    document: &mut Document,
    index: usize,
    layout: &Layout,
) -> Result<(), Error> {
    let original = document.items[index].clone();
    if !matches!(
        &original.content,
        Content::Text { .. } | Content::StoryFrame { .. }
    ) {
        return Err(Error::new("INVALID_OPERATION", "Expected text item"));
    }
    let frame_clip = clip_geometry(&original.content, layout);
    let mut used: BTreeSet<_> = document.items.iter().map(|i| i.id.clone()).collect();
    let mut next = 0usize;
    let mut fresh = || {
        loop {
            let id = format!("inkbolt-glyph-{next}");
            next += 1;
            if used.insert(id.clone()) {
                return id;
            }
        }
    };
    document.items[index].content = Content::Group {
        isolated: true,
        role: GroupRole::Group,
        knockout: false,
    };
    let mut parent = original.id.clone();
    let mut additions = Vec::new();
    let template = |id: String, parent: String, content: Content| Item {
        hdr_grade: None,
        pixel_warp: None,
        metadata: None,
        id,
        name: String::new(),
        visible: true,
        locked: false,
        opacity: 1.0,
        fill_opacity: 1.0,
        coverage: crate::coverage::Mode::Smooth {},
        effects: Vec::new(),
        blend: BlendMode::Normal,
        transform: identity(),
        parent: Some(parent),
        clip_to: None,
        clip: None,
        mask: None,
        artwork_mask: None,
        filters: Vec::new(),
        content,
    };
    if let Some(geometry) = frame_clip {
        let id = fresh();
        let mut item = template(
            id.clone(),
            parent,
            Content::Group {
                isolated: true,
                role: GroupRole::Group,
                knockout: false,
            },
        );
        item.clip = Some(Clip {
            geometry,
            fill_rule: FillRule::Nonzero,
            transform: identity(),
            enabled: true,
        });
        additions.push(item);
        parent = id;
    }
    for p in &layout.paths {
        additions.push(template(
            fresh(),
            parent.clone(),
            Content::Vector {
                geometry: p.geometry.clone(),
                fill: Some(p.fill.clone()),
                stroke: None,
                fill_rule: FillRule::Nonzero,
            },
        ));
    }
    if document.items.len() + additions.len() > document.resource_profile.items() {
        return Err(limit("Text outline conversion exceeds item limit"));
    }
    document.items.splice(index + 1..index + 1, additions);
    Ok(())
}
