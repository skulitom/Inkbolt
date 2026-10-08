//! Retained paragraph stories and ordered frame/column placement.
use super::*;
pub mod hyphens;
pub mod lists;

pub const MAX_STORIES: usize = 32;
pub const MAX_PARAGRAPHS: usize = 256;
pub const MAX_SLOTS: usize = 64;
pub const MAX_COLUMNS: usize = 16;
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Overset {
    #[default]
    Error,
    Retain,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Paragraph {
    pub text: String,
    pub style: Style,
    #[serde(default)]
    pub ranges: Vec<StyleRange>,
    #[serde(default)]
    pub align: Align,
    #[serde(default)]
    pub direction: Direction,
    #[serde(default)]
    pub bidi: Bidi,
    #[serde(default)]
    pub leading: Option<f64>,
    #[serde(default)]
    pub before: f64,
    #[serde(default)]
    pub after: f64,
    #[serde(default)]
    pub indent_start: f64,
    #[serde(default)]
    pub indent_end: f64,
    #[serde(default)]
    pub first_indent: f64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub list: Option<lists::List>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub hyphenation: Option<hyphens::Config>,
}
impl Paragraph {
    pub fn styles(&self) -> impl Iterator<Item = &Style> {
        std::iter::once(&self.style)
            .chain(self.ranges.iter().map(|r| &r.style))
            .chain(self.list.iter().filter_map(|l| l.style.as_ref()))
    }
    pub fn styles_mut(&mut self) -> impl Iterator<Item = &mut Style> {
        std::iter::once(&mut self.style)
            .chain(self.ranges.iter_mut().map(|r| &mut r.style))
            .chain(self.list.iter_mut().filter_map(|l| l.style.as_mut()))
    }
    fn frame(&self) -> Frame {
        Frame {
            text: self.text.clone(),
            width: 32768.0,
            height: 32768.0,
            style: self.style.clone(),
            ranges: self.ranges.clone(),
            align: self.align,
            direction: self.direction,
            bidi: self.bidi,
            wrap: true,
            leading: self.leading,
            overflow: Overflow::Visible,
            path: None,
        }
    }
}
fn one() -> usize {
    1
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Slot {
    pub id: String,
    pub width: f64,
    pub height: f64,
    #[serde(default = "one")]
    pub columns: usize,
    #[serde(default)]
    pub gutter: f64,
    #[serde(default)]
    pub reverse_columns: bool,
}
impl Slot {
    pub fn geometry(&self) -> Geometry {
        Geometry::Rect {
            x: 0.0,
            y: 0.0,
            width: self.width,
            height: self.height,
        }
    }
    fn column_width(&self) -> f64 {
        (self.width - (self.columns - 1) as f64 * self.gutter) / self.columns as f64
    }
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Story {
    pub paragraphs: Vec<Paragraph>,
    pub slots: Vec<Slot>,
    #[serde(default)]
    pub overset: Overset,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub hyphenation_rules: BTreeMap<String, crate::hyphenation::Rules>,
}
impl Story {
    pub fn styles(&self) -> impl Iterator<Item = &Style> {
        self.paragraphs.iter().flat_map(Paragraph::styles)
    }
    pub fn styles_mut(&mut self) -> impl Iterator<Item = &mut Style> {
        self.paragraphs.iter_mut().flat_map(Paragraph::styles_mut)
    }
    pub fn slot(&self, id: &str) -> Result<&Slot, Error> {
        self.slots
            .iter()
            .find(|s| s.id == id)
            .ok_or_else(|| invalid("Story slot does not exist"))
    }
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_STORY", message)
}
pub fn story<'a>(d: &'a Document, id: &str) -> Result<&'a Story, Error> {
    d.stories
        .get(id)
        .ok_or_else(|| invalid("Story does not exist"))
}
pub fn geometry(d: &Document, content: &Content) -> Result<Option<Geometry>, Error> {
    if let Content::StoryFrame { story_id, slot_id } = content {
        Ok(Some(story(d, story_id)?.slot(slot_id)?.geometry()))
    } else {
        Ok(None)
    }
}
pub(crate) fn uses(content: &Content, id: &str) -> bool {
    crate::instances::any_content(
        content,
        &|c| matches!(c,Content::StoryFrame {story_id,..} if story_id==id),
    )
}
pub(crate) fn dependency_hash(d: &Document, i: usize) -> Result<Option<String>, Error> {
    let mut visited = BTreeSet::new();
    let mut pending = vec![i];
    let mut ids = BTreeSet::new();
    while let Some(i) = pending.pop() {
        if !visited.insert(i) {
            continue;
        }
        let item = &d.items[i];
        ids.extend(
            d.stories
                .keys()
                .filter(|id| uses(&item.content, id))
                .cloned(),
        );
        pending.extend(crate::scene::children(d, Some(&item.id)));
        if let Content::Instance { instance } = &item.content {
            pending.push(crate::scene::index(d, &instance.source)?);
        }
        if let Some(mask) = &item.artwork_mask {
            pending.push(crate::scene::index(d, &mask.source)?);
        }
    }
    let values: BTreeMap<_, _> = ids.iter().map(|id| (id, &d.stories[id])).collect();
    Ok((!values.is_empty()).then(|| crate::assets::sha256(&crate::metadata::canonical(&values))))
}
pub(crate) fn check_unlocked(d: &Document, id: &str) -> Result<(), Error> {
    for (i, item) in d.items.iter().enumerate() {
        if uses(&item.content, id) {
            crate::scene::check_unlocked(d, i, false)?;
        }
    }
    Ok(())
}
pub(crate) fn set(d: &mut Document, id: &str, value: Option<&Story>) -> Result<(), Error> {
    if !valid_id(id) {
        return Err(invalid("Story ID must use document ID syntax"));
    }
    check_unlocked(d, id)?;
    if let Some(value) = value {
        d.stories.insert(id.into(), value.clone());
    } else {
        if d.items.iter().any(|i| uses(&i.content, id)) {
            return Err(Error::new(
                "STORY_IN_USE",
                "Remove or relink story frames before removing their source",
            ));
        }
        if d.stories.remove(id).is_none() {
            return Err(invalid("Story does not exist"));
        }
    }
    Ok(())
}
pub(crate) fn revise(
    d: &mut Document,
    id: &str,
    paragraph: usize,
    range: [usize; 2],
    text: Option<&str>,
    style: Option<&Style>,
) -> Result<(), Error> {
    check_unlocked(d, id)?;
    let s = d
        .stories
        .get_mut(id)
        .ok_or_else(|| invalid("Story does not exist"))?;
    let p = s
        .paragraphs
        .get_mut(paragraph)
        .ok_or_else(|| invalid("Paragraph index does not exist"))?;
    let mut f = p.frame();
    super::revise(&mut f, range[0], range[1], text, style)?;
    p.text = f.text;
    p.ranges = f.ranges;
    Ok(())
}
pub fn validate(story: &Story, d: &Document) -> Result<(usize, usize, usize), Error> {
    if story.paragraphs.is_empty() || story.slots.is_empty() {
        return Err(invalid("Stories require paragraphs and flow slots"));
    }
    if story.paragraphs.len() > MAX_PARAGRAPHS || story.slots.len() > MAX_SLOTS {
        return Err(limit("Story exceeds paragraph or slot count limit"));
    }
    hyphens::validate(story)?;
    let mut ids = BTreeSet::new();
    for slot in &story.slots {
        if !valid_id(&slot.id) || !ids.insert(&slot.id) {
            return Err(invalid("Story slot IDs must be valid and unique"));
        }
        if !(1..=MAX_COLUMNS).contains(&slot.columns) {
            return Err(invalid("Story columns must be in 1..=16"));
        }
        if [slot.width, slot.height]
            .iter()
            .any(|v| !v.is_finite() || !(0.001..=32768.0).contains(v))
            || !slot.gutter.is_finite()
            || !(0.0..=32768.0).contains(&slot.gutter)
            || slot.column_width() < 0.001
        {
            return Err(invalid(
                "Story slots require finite positive extents and columns after gutters",
            ));
        }
    }
    let labels = lists::resolve(story)?;
    let mut totals = (0, 0, 0);
    for (p, label) in story.paragraphs.iter().zip(labels.iter()) {
        if p.text.contains('\n') {
            return Err(invalid(
                "Story paragraphs are separate records; text must not contain LF",
            ));
        }
        if [p.before, p.after, p.indent_start, p.indent_end]
            .iter()
            .any(|v| !v.is_finite() || !(0.0..=32768.0).contains(v))
            || !p.first_indent.is_finite()
            || p.first_indent.abs() > 32768.0
        {
            return Err(invalid(
                "Paragraph spacing and indents exceed their finite bounds",
            ));
        }
        if p.indent_start + p.first_indent < 0.0 {
            return Err(invalid("First-line indent cannot extend before the column"));
        }
        let (a, b, c) = super::validate(&p.frame(), d, identity())?;
        totals.0 += a;
        totals.1 += b;
        totals.2 += c;
        if let Some(label) = label {
            let marker = lists::frame(p, label, Direction::Ltr);
            let (a, b, c) = super::validate(&marker, d, identity())?;
            totals.0 += a;
            totals.1 += b;
            totals.2 += c;
        }
        if totals.0 > MAX_TEXT_CHARS
            || totals.1 > MAX_STORED_PIXELS
            || totals.2 > crate::paint::MAX_PAINT_SAMPLES
        {
            return Err(limit("Story exceeds aggregate text or paint limits"));
        }
    }
    Ok(totals)
}
#[derive(Clone, Debug, Serialize)]
pub struct Cursor {
    pub paragraph: usize,
    pub offset: usize,
}
#[derive(Debug, Serialize)]
pub struct SourceLine {
    pub slot_id: String,
    pub column: usize,
    pub line: usize,
    pub paragraph: usize,
    pub start: usize,
    pub end: usize,
    pub consumed_end: usize,
    pub glyph_start: usize,
    pub glyph_end: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub marker: Option<lists::Placement>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hyphen: Option<hyphens::Placement>,
}
#[derive(Debug, Serialize)]
pub struct Report {
    pub slots: BTreeMap<String, Layout>,
    pub lines: Vec<SourceLine>,
    pub overset: Option<Cursor>,
    pub indices: &'static str,
}
fn empty() -> Layout {
    Layout {
        frame_clip: None,
        lines: Vec::new(),
        glyphs: Vec::new(),
        ink_bounds: None,
        overflowed: false,
        paths: Vec::new(),
        baseline_path: None,
    }
}
pub(crate) fn placed(
    d: &Document,
    story_id: &str,
    slot_id: &str,
    cache: &fonts::Cache,
) -> Result<Layout, Error> {
    let source = story(d, story_id)?;
    let mut report = layout(source, d, cache)?;
    if report.overset.is_some() && source.overset == Overset::Error {
        return Err(Error::new(
            "STORY_OVERFLOW",
            "Story has unplaced text; add flow space or explicitly retain the overset tail",
        ));
    }
    report
        .slots
        .remove(slot_id)
        .ok_or_else(|| invalid("Story slot does not exist"))
}
pub fn layout(story: &Story, d: &Document, cache: &fonts::Cache) -> Result<Report, Error> {
    validate(story, d)?;
    let mut result = Report {
        slots: story
            .slots
            .iter()
            .map(|s| {
                let mut layout = empty();
                layout.frame_clip = Some(s.geometry());
                (s.id.clone(), layout)
            })
            .collect(),
        lines: Vec::new(),
        overset: None,
        indices: "paragraph_local_unicode_scalars",
    };
    let mut slot_index = 0;
    let mut column = 0;
    let mut top = 0.0;
    let mut work = 0;
    let mut commands = 0;
    let mut glyph_count = 0;
    let labels = lists::resolve(story)?;
    let rules = hyphens::compile(story)?;
    let mut hyphenation_work = 0;
    for (paragraph, p) in story.paragraphs.iter().enumerate() {
        let frame = p.frame();
        let analysis = Analysis::new(&frame)?;
        let mut marker = labels[paragraph]
            .as_ref()
            .map(|label| {
                lists::prepare(p, label, analysis.direction(&frame, 0), d, cache, &mut work)
            })
            .transpose()?;
        let chars: Vec<_> = p.text.chars().collect();
        let boundaries = super::boundaries(&p.text);
        let opportunities = hyphens::opportunities(p, &rules, &mut hyphenation_work)?;
        let mut a = 0;
        let mut first = true;
        loop {
            let Some(slot) = story.slots.get(slot_index) else {
                result.overset = Some(Cursor {
                    paragraph,
                    offset: a,
                });
                return Ok(result);
            };
            let width = slot.column_width();
            let start_indent = p.indent_start + if first { p.first_indent } else { 0.0 };
            let available = width - start_indent - p.indent_end;
            if available < 0.001 {
                column += 1;
                top = 0.0;
                if column == slot.columns {
                    slot_index += 1;
                    column = 0;
                }
                continue;
            }
            let end = chars.len();
            let mut b = end;
            let mut selected = None;
            let full_advance = shape(&frame, &analysis, a, end, d, cache, &mut work)?.1;
            if a < end && full_advance > available && p.hyphenation.is_some() {
                selected = hyphens::choose(
                    p,
                    &frame,
                    &analysis,
                    &opportunities,
                    a,
                    available,
                    d,
                    cache,
                    &mut work,
                )?;
            }
            if let Some(value) = &selected {
                b = value.end;
            } else if a < end
                && full_advance > available
                && p.hyphenation.as_ref().is_none_or(|h| h.emergency_break)
            {
                let candidates: Vec<_> = boundaries.range(a + 1..=end).copied().collect();
                b = candidates[0];
                for &candidate in candidates.iter().rev().skip(1) {
                    if shape(&frame, &analysis, a, candidate, d, cache, &mut work)?.1 <= available {
                        b = candidate;
                        break;
                    }
                }
                if let Some(space) = (a..b).rev().find(|&i| chars[i] == ' ')
                    && space > a
                    && boundaries.contains(&space)
                    && shape(&frame, &analysis, a, space, d, cache, &mut work)?.1 <= available
                {
                    b = space;
                }
            }
            let (glyphs, advance) = if let Some(value) = &mut selected {
                (std::mem::take(&mut value.glyphs), value.advance)
            } else {
                shape(&frame, &analysis, a, b, d, cache, &mut work)?
            };
            let shaped_frame = selected
                .as_ref()
                .and_then(|v| v.frame.as_ref())
                .unwrap_or(&frame);
            let mut ascent = 0.0f64;
            let mut descent = 0.0f64;
            let mut gap = 0.0f64;
            for (f, gs) in std::iter::once((shaped_frame, glyphs.as_slice()))
                .chain(marker.iter().map(|m| (&m.frame, m.glyphs.as_slice())))
            {
                let ids: BTreeSet<_> = gs
                    .iter()
                    .map(|g| (g.style, g.font_id.as_str()))
                    .chain(std::iter::once((0, f.style.font_id.as_str())))
                    .collect();
                for (i, font_id) in ids {
                    let s = style(f, i);
                    let face = s.face(font_id, d, cache)?;
                    let scale = s.size / face.units_per_em() as f64;
                    ascent = ascent.max(face.ascender() as f64 * scale);
                    descent = descent.max(-(face.descender() as f64) * scale);
                    gap = gap.max(face.line_gap() as f64 * scale);
                }
            }
            let natural = (ascent + descent + gap).max(0.001);
            let line_top = top + if first { p.before } else { 0.0 };
            let marker_fits = marker
                .as_ref()
                .is_none_or(|m| m.advance + p.list.as_ref().unwrap().gap <= start_indent + 1e-9);
            if line_top + natural > slot.height + 1e-9 || advance > available + 1e-9 || !marker_fits
            {
                column += 1;
                top = 0.0;
                if column == slot.columns {
                    slot_index += 1;
                    column = 0;
                }
                continue;
            }
            let visual_column = if slot.reverse_columns {
                slot.columns - 1 - column
            } else {
                column
            };
            let direction = analysis.direction(&frame, a);
            let left = if direction == Direction::Rtl {
                p.indent_end
            } else {
                start_indent
            };
            let x = visual_column as f64 * (width + slot.gutter)
                + left
                + p.align.offset(available, advance, direction);
            let baseline = line_top + ascent;
            let target = result.slots.get_mut(&slot.id).unwrap();
            let glyph_start = target.glyphs.len();
            let line = target.lines.len();
            target.lines.push(Line {
                start: a,
                end: b,
                baseline,
                x,
                advance,
                direction,
                bidi: analysis.line(a, b)?,
            });
            append_glyphs(
                shaped_frame,
                d,
                cache,
                target,
                glyphs,
                [x, baseline],
                &mut commands,
            )?;
            let glyph_end = target.glyphs.len();
            let hyphen = selected.and_then(|v| v.hyphen);
            if hyphen.is_some() {
                for glyph in &mut target.glyphs[glyph_start..glyph_end] {
                    if glyph.end > b {
                        glyph.generated = Some(Generated::Hyphen { offset: b });
                    }
                    glyph.start = glyph.start.min(b);
                    glyph.end = glyph.end.min(b);
                }
            }
            let marker = marker
                .take()
                .map(|m| {
                    let column_left = visual_column as f64 * (width + slot.gutter);
                    let marker_x = if direction == Direction::Rtl {
                        column_left + width - start_indent + p.list.as_ref().unwrap().gap
                    } else {
                        column_left + start_indent - p.list.as_ref().unwrap().gap - m.advance
                    };
                    lists::append(m, target, marker_x, baseline, d, cache, &mut commands)
                })
                .transpose()?;
            glyph_count += target.glyphs.len() - glyph_start;
            if glyph_count > MAX_GLYPHS {
                return Err(limit("Story exceeds glyph limit"));
            }
            let mut consumed_end = b;
            if b < end {
                while consumed_end < end
                    && chars[consumed_end] == ' '
                    && boundaries.contains(&(consumed_end + 1))
                {
                    consumed_end += 1;
                }
            }
            result.lines.push(SourceLine {
                slot_id: slot.id.clone(),
                column: visual_column,
                line,
                paragraph,
                start: a,
                end: b,
                consumed_end,
                glyph_start,
                glyph_end,
                marker,
                hyphen,
            });
            if let Some(bounds) = target.ink_bounds {
                target.overflowed |= bounds[0] < -1e-9
                    || bounds[1] < -1e-9
                    || bounds[2] > slot.width + 1e-9
                    || bounds[3] > slot.height + 1e-9;
            }
            top = line_top + p.leading.unwrap_or(natural);
            first = false;
            a = consumed_end;
            if a == end {
                top += p.after;
                break;
            }
        }
    }
    Ok(result)
}
