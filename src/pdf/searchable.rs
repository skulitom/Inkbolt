//! Keep displayed glyph placement and source Unicode together in vector PDFs.
use super::*;
use crate::text::Glyph;
use rustybuzz::ttf_parser::{Face, GlyphId, Permissions};

mod cluster;
mod instance;
mod program;

const GLYPH_COLLECTION: &str =
    "/CIDSystemInfo << /Registry (Inkbolt) /Ordering (Glyphs) /Supplement 0 >>";

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum TextDelivery {
    #[default]
    Outlines,
    Searchable,
    RequireSearchable,
}
impl TextDelivery {
    pub(super) fn is_outlines(&self) -> bool {
        *self == Self::Outlines
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Kind {
    StaticInstance,
    SubsetTrueType,
    WholeTrueType,
    SubsetCff,
    WholeNamedCff,
    WholeCidCff,
}

fn kind(data: &[u8], index: u32) -> Result<Kind, &'static str> {
    let face = Face::parse(data, index).map_err(|_| "unreadable_font")?;
    let os2 = face.tables().os2.ok_or("missing_embedding_permissions")?;
    match os2.permissions() {
        Some(Permissions::Installable | Permissions::Editable) => {}
        Some(Permissions::PreviewAndPrint) => return Err("read_only_embedding_required"),
        _ => return Err("restricted_embedding"),
    }
    if !os2.is_outline_embedding_allowed() {
        return Err("bitmap_only_embedding");
    }
    if face.is_variable() || face.tables().cff2.is_some() {
        if (face.tables().glyf.is_some() || face.tables().cff2.is_some())
            && os2.is_subsetting_allowed()
        {
            return Ok(Kind::StaticInstance);
        }
        return Err(if face.is_variable() {
            "variable_font"
        } else {
            "whole_cff2_font"
        });
    }
    let whole = !os2.is_subsetting_allowed();
    if whole && data.starts_with(b"ttcf") {
        return Err("whole_font_collection");
    }
    if face.tables().glyf.is_some() {
        return Ok(if whole {
            Kind::WholeTrueType
        } else {
            Kind::SubsetTrueType
        });
    }
    if let Some(cff) = face.tables().cff {
        if !whole {
            return Ok(Kind::SubsetCff);
        }
        if cff.glyph_cid(GlyphId(0)).is_none() {
            return Ok(Kind::WholeNamedCff);
        }
        return Ok(Kind::WholeCidCff);
    }
    Err("unsupported_font_outlines")
}

#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
struct CharacterCode {
    encoding: usize,
    index: usize,
}

struct PendingFont {
    kind: Kind,
    ids: Vec<usize>,
    codes: BTreeMap<(u16, String), CharacterCode>,
    cid_alias_count: BTreeMap<u16, usize>,
    encoding_sizes: Vec<usize>,
}

impl PendingFont {
    fn code_for(&mut self, gid: u16, source: &str) -> Result<CharacterCode, Error> {
        use std::collections::btree_map::Entry;
        let next = self.codes.len();
        let entry = match self.codes.entry((gid, source.to_owned())) {
            Entry::Occupied(entry) => return Ok(*entry.get()),
            Entry::Vacant(entry) => entry,
        };
        if next >= u16::MAX as usize && self.kind != Kind::WholeNamedCff {
            return Err(limit("PDF font character codes exhausted"));
        }
        let (encoding, index) = match self.kind {
            Kind::SubsetCff | Kind::WholeCidCff => {
                // A physical CFF glyph has one CID. Some readers resolve
                // Unicode by CID even when different text codes select it.
                // Put each additional meaning in its own encoding of the
                // same embedded program. Other glyphs can share that encoding.
                let rank = self.cid_alias_count.entry(gid).or_default();
                let part = *rank;
                *rank += 1;
                if part == self.encoding_sizes.len() {
                    self.encoding_sizes.push(0);
                }
                let code = self.encoding_sizes[part];
                self.encoding_sizes[part] += 1;
                (part, code)
            }
            Kind::WholeNamedCff => (next / 255, next % 255),
            _ => (0, next),
        };
        Ok(*entry.insert(CharacterCode { encoding, index }))
    }
}

/// The shaper applies design coordinates as f32. Store their bits in tag order
/// so different instances of the same pinned face can coexist on a page.
#[derive(Clone, PartialEq, Eq, PartialOrd, Ord)]
struct Instance {
    font_id: String,
    axes: Vec<([u8; 4], u32)>,
}
impl Instance {
    fn for_glyph(glyph: &Glyph) -> Result<Self, Error> {
        let mut axes = Vec::with_capacity(glyph.variations.len());
        for (tag, value) in &glyph.variations {
            let tag = crate::fonts::tag(tag)?.to_bytes();
            axes.push((tag, (*value as f32).to_bits()));
        }
        Ok(Self {
            font_id: glyph.font_id.clone(),
            axes,
        })
    }
}

#[derive(Default)]
pub(super) struct Registry {
    fonts: BTreeMap<Instance, PendingFont>,
    clusters: BTreeMap<(String, String), usize>,
    outlined_on_page: BTreeSet<String>,
    losses: BTreeMap<&'static str, usize>,
    embedded_fonts: usize,
    embedded_glyphs: usize,
    gradient_clusters: usize,
    independent_glyph_state: Option<usize>,
}
impl Registry {
    pub(super) fn receipt(&self, mode: TextDelivery) -> Option<(&'static str, Value)> {
        (!mode.is_outlines()).then(|| {
            let delivered = if self.embedded_glyphs == 0 {
                "vector_outlines"
            } else if self.losses.is_empty() {
                "searchable"
            } else {
                "mixed_searchable_and_outlines"
            };
            let mut receipt = json!({"requested":mode,"embedded_font_programs":self.embedded_fonts,
                "embedded_glyphs":self.embedded_glyphs,"outlined_items_by_reason":self.losses});
            if self.gradient_clusters > 0 {
                receipt["gradient_color_glyphs"] = json!(self.gradient_clusters);
            }
            (delivered, receipt)
        })
    }
}

fn fallback(
    writer: &mut Writer,
    item: &Item,
    mode: TextDelivery,
    reason: &'static str,
) -> Result<bool, Error> {
    if mode == TextDelivery::RequireSearchable {
        return Err(unsupported(&format!(
            "Searchable text cannot be embedded for this item ({reason})"
        )));
    }
    if writer.text.outlined_on_page.insert(item.id.clone()) {
        *writer.text.losses.entry(reason).or_default() += 1;
    }
    Ok(false)
}

fn source<'a>(document: &'a Document, item: &'a Item, glyph: &Glyph) -> Option<&'a str> {
    match &item.content {
        Content::Text { frame } => Some(&frame.text),
        Content::StoryFrame { story_id, .. } => Some(
            &document
                .stories
                .get(story_id)?
                .paragraphs
                .get(glyph.paragraph?)?
                .text,
        ),
        _ => None,
    }
}

struct PaintedGlyph<'a> {
    glyph: &'a Glyph,
    path: Option<&'a crate::text::PaintedPath>,
}
impl PaintedGlyph<'_> {
    fn paint(&self) -> Option<&Paint> {
        self.path.map(|path| &path.fill)
    }
    fn span(&self) -> (Option<usize>, usize, usize) {
        (self.glyph.paragraph, self.glyph.start, self.glyph.end)
    }
}

fn strong_rtl(c: char) -> bool {
    matches!(
        unicode_bidi::bidi_class(c),
        unicode_bidi::BidiClass::R | unicode_bidi::BidiClass::AL
    )
}

fn rtl_line_fallback(
    line: &[PaintedGlyph],
    source: &str,
    first_char: usize,
    world: Matrix,
) -> Option<&'static str> {
    if line
        .iter()
        .any(|p| p.glyph.direction != crate::text::Direction::Rtl)
    {
        return Some("right_to_left_run");
    }
    // A reader can reverse the scalars of a multi-character cluster, drop
    // controls or move edge punctuation to the opposite end of the line.
    if !source.split(' ').all(|word| {
        !word.is_empty()
            && word
                .chars()
                .all(|c| strong_rtl(c) && !crate::text::bidi::is_control(c))
    }) {
        return Some("right_to_left_source");
    }
    let baseline = line[0].glyph.origin[1];
    if world[0] <= 0.0
        || world[3] <= 0.0
        || world[1] != 0.0
        || world[2] != 0.0
        || line
            .iter()
            .any(|p| p.glyph.path.is_some() || p.glyph.tracked || p.glyph.origin[1] != baseline)
    {
        return Some("right_to_left_geometry");
    }
    if source.chars().count() != line.len()
        || line.iter().rev().enumerate().any(|(i, p)| {
            p.glyph.start != first_char + i
                || p.glyph.end != p.glyph.start + 1
                || p.glyph.advance <= 0.0
        })
    {
        return Some("right_to_left_cluster");
    }
    // Native ink can change rendering intent for subsequent text draws.
    if line
        .iter()
        .any(|p| matches!(p.paint(), Some(Paint::Named(_))))
    {
        return Some("right_to_left_ink");
    }
    None
}

fn drawn(glyph: &Glyph) -> bool {
    glyph.path.as_ref().is_none_or(|p| p.drawn)
}

/// Map one font em (y up) into document-local coordinates (y down).
fn glyph_matrix(g: &Glyph) -> Matrix {
    let [x, y] = g.path.as_ref().map_or([1.0, 0.0], |p| p.tangent);
    let [w, h] = g.em_size;
    [x * w, y * w, y * h, -x * h, g.origin[0], g.origin[1]]
}

pub(super) fn paint_text(
    writer: &mut Writer,
    stream: &mut Stream,
    document: &Document,
    item: &Item,
    world: Matrix,
    resources: &PageResources,
) -> Result<bool, Error> {
    let layout = &resources.layouts[&item.id];
    if layout.glyphs.is_empty() {
        return Ok(true);
    }
    if writer.form_depths.is_some() {
        return fallback(writer, item, resources.text, "knockout_page");
    }
    let mut paths = layout.paths.iter();
    let mut painted = Vec::new();
    for g in layout.glyphs.iter().filter(|g| drawn(g)) {
        let path = if g.ink_bounds.is_some() {
            Some(
                paths
                    .next()
                    .ok_or_else(|| unsupported("Missing glyph paint in layout"))?,
            )
        } else {
            None
        };
        painted.push(PaintedGlyph { glyph: g, path });
    }
    let groups = || painted.chunk_by(|a, b| a.span() == b.span());
    let lines = || painted.chunk_by(|a, b| a.glyph.line == b.glyph.line);
    let mut kinds = BTreeMap::new();
    let mut spans = BTreeSet::new();
    let mut boundaries = BTreeMap::new();
    for group in groups() {
        if !spans.insert(group[0].span()) {
            return fallback(writer, item, resources.text, "noncontiguous_cluster");
        }
        if group.len() > 1
            && group
                .iter()
                .filter_map(PaintedGlyph::paint)
                .any(|p| matches!(p, Paint::Named(_)))
        {
            return fallback(writer, item, resources.text, "cluster_paint");
        }
    }
    for position in &painted {
        let g = position.glyph;
        writer.control.check()?;
        if g.generated.is_some() {
            return fallback(writer, item, resources.text, "generated_glyphs");
        }
        let Some(text) = source(document, item, g) else {
            return fallback(writer, item, resources.text, "missing_source_range");
        };
        let offsets = boundaries.entry(g.paragraph).or_insert_with(|| {
            text.char_indices()
                .map(|(i, _)| i)
                .chain([text.len()])
                .collect::<Vec<_>>()
        });
        if g.start >= g.end || g.end >= offsets.len() {
            return fallback(writer, item, resources.text, "missing_source_range");
        }
        let cluster = &text[offsets[g.start]..offsets[g.end]];
        // Single-run layout can paint strong RTL characters left to right.
        // Readers may then reverse their Unicode even though the glyphs match.
        if g.direction != crate::text::Direction::Rtl && cluster.chars().any(strong_rtl) {
            return fallback(writer, item, resources.text, "right_to_left_source");
        }
        // Each CMap destination is a PDF string. Bound UTF-16 bytes before
        // reserving a character code or painting any part of this text item.
        if cluster.encode_utf16().count() > 128 {
            return fallback(writer, item, resources.text, "long_unicode_cluster");
        }
        if let std::collections::btree_map::Entry::Vacant(entry) = kinds.entry(g.font_id.as_str()) {
            let font_kind = match kind(
                &resources.fonts[&g.font_id],
                document.fonts[&g.font_id].face_index,
            ) {
                Ok(kind) => kind,
                Err(reason) => return fallback(writer, item, resources.text, reason),
            };
            entry.insert(font_kind);
        }
    }
    for line in lines().filter(|l| {
        l.iter()
            .any(|p| p.glyph.direction == crate::text::Direction::Rtl)
    }) {
        let g = line[0].glyph;
        let range = &layout.lines[g.line];
        let offsets = &boundaries[&g.paragraph];
        let text = source(document, item, g).expect("validated source range");
        let Some(end) = offsets.get(range.end) else {
            return fallback(writer, item, resources.text, "missing_source_range");
        };
        let text = &text[offsets[range.start]..*end];
        if let Some(reason) = rtl_line_fallback(line, text, range.start, world) {
            return fallback(writer, item, resources.text, reason);
        }
    }
    for line in lines() {
        let g = line[0].glyph;
        let text = source(document, item, g).expect("validated source range");
        paint_line(
            writer,
            stream,
            line,
            world,
            &kinds,
            text,
            &boundaries[&g.paragraph],
        )?;
    }
    Ok(true)
}

fn paint_line(
    writer: &mut Writer,
    stream: &mut Stream,
    line: &[PaintedGlyph],
    world: Matrix,
    kinds: &BTreeMap<&str, Kind>,
    text: &str,
    offsets: &[usize],
) -> Result<(), Error> {
    let rtl = line[0].glyph.direction == crate::text::Direction::Rtl;
    // One text object preserves RTL word order. With text knockout disabled,
    // overlapping glyphs composite independently just as their outlines do.
    if rtl {
        stream.content.push_str("q\n");
        let state = match writer.text.independent_glyph_state {
            Some(id) => id,
            None => {
                let id = writer.add("<< /Type /ExtGState /TK false >>")?;
                writer.text.independent_glyph_state = Some(id);
                id
            }
        };
        stream.use_resource("ExtGState", state, "gs");
        stream.content.push_str("BT\n");
    }
    for group in line.chunk_by(|a, b| a.span() == b.span()) {
        let g = group[0].glyph;
        let cluster = &text[offsets[g.start]..offsets[g.end]];
        let font_kind = kinds[g.font_id.as_str()];
        let gradient = group
            .iter()
            .any(|g| matches!(g.paint(), Some(Paint::Field(_))));
        let colored = gradient || (group.len() > 1 && cluster::intrinsic_color(group));
        let (font, code) = if group.len() == 1 && !gradient {
            register(writer, g, cluster, font_kind)?
        } else {
            (
                cluster::font(
                    writer,
                    group,
                    cluster,
                    kinds,
                    stream,
                    colored,
                    gradient.then_some(world),
                )?,
                "01".into(),
            )
        };
        let paint = group
            .iter()
            .find_map(PaintedGlyph::paint)
            .unwrap_or(&Paint::Solid([0, 0, 0, 255]));
        let mut cell = glyph_matrix(g);
        if rtl && gradient {
            // The color font uses a 1000-unit cell. Place its exact advance in
            // the matrix so readers that truncate Type 3 widths select the
            // same horizontal interval as the shaped glyph.
            cell[0] = g.advance;
        }
        let m = geometry::multiply(world, cell);
        if !rtl {
            stream.content.push_str("q\n");
        }
        if colored {
            // The charproc paints each component at its own opacity. Applying
            // the first component's opacity to the whole cluster would double it.
            graphics_state(writer, stream, 1.0, BlendMode::Normal)?;
        } else {
            flat_paint(writer, stream, paint)?;
        }
        if !rtl {
            stream.content.push_str("BT\n");
        }
        stream.use_resource("Font", font, "1 Tf");
        stream.content.push_str(&format!("{} Tm\n", numbers(&m)?));
        // ToUnicode maps this visible character, including a ligature, to its
        // exact source. A replacement around Tj can displace the selection.
        stream.content.push_str(&format!("<{code}> Tj\n"));
        if !rtl {
            stream.content.push_str("ET\nQ\n");
        }
        writer.text.embedded_glyphs += group.len();
    }
    if rtl {
        stream.content.push_str("ET\nQ\n");
    }
    Ok(())
}

fn register(
    writer: &mut Writer,
    g: &Glyph,
    cluster: &str,
    kind: Kind,
) -> Result<(usize, String), Error> {
    let instance = Instance::for_glyph(g)?;
    let font = writer
        .text
        .fonts
        .entry(instance.clone())
        .or_insert_with(|| PendingFont {
            kind,
            ids: vec![],
            codes: BTreeMap::new(),
            cid_alias_count: BTreeMap::new(),
            encoding_sizes: Vec::new(),
        });
    let CharacterCode { encoding, index } = font.code_for(g.glyph_id, cluster)?;
    let code = if kind == Kind::WholeNamedCff {
        format!("{:02X}", index + 1)
    } else {
        format!("{:04X}", index + 1)
    };
    if let Some(&id) = font.ids.get(encoding) {
        return Ok((id, code));
    }
    let id = writer.add(Vec::new())?;
    writer.text.fonts.get_mut(&instance).unwrap().ids.push(id);
    Ok((id, code))
}
fn utf16(s: &str) -> String {
    use std::fmt::Write;
    let mut result = String::new();
    for unit in s.encode_utf16() {
        write!(result, "{unit:04X}").unwrap();
    }
    result
}

pub(super) fn finish_page(
    writer: &mut Writer,
    document: &Document,
    fonts: &crate::fonts::Cache,
) -> Result<(), Error> {
    for (instance, font) in std::mem::take(&mut writer.text.fonts) {
        let name = instance.font_id;
        program::embed(
            writer,
            &fonts[&name],
            document.fonts[&name].face_index,
            font,
            &instance.axes,
        )
        .map_err(|e| e.at_font(&name))?;
        writer.text.embedded_fonts += 1;
    }
    writer.text.clusters.clear();
    writer.text.outlined_on_page.clear();
    Ok(())
}
