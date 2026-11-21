//! Keep displayed glyph placement and source Unicode together in vector PDFs.
use super::*;
use crate::text::Glyph;
use rustybuzz::ttf_parser::{Face, GlyphId, Permissions};

mod cluster;
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
    if face.is_variable() {
        return Err("variable_font");
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

struct PendingFont {
    kind: Kind,
    ids: Vec<usize>,
    codes: BTreeMap<(u16, String), usize>,
}

#[derive(Default)]
pub(super) struct Registry {
    fonts: BTreeMap<String, PendingFont>,
    clusters: BTreeMap<(String, String), usize>,
    outlined_on_page: BTreeSet<String>,
    losses: BTreeMap<&'static str, usize>,
    embedded_fonts: usize,
    embedded_glyphs: usize,
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
            (
                delivered,
                json!({"requested":mode,"embedded_font_programs":self.embedded_fonts,
            "embedded_glyphs":self.embedded_glyphs,"outlined_items_by_reason":self.losses}),
            )
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
    paint: Option<&'a Paint>,
}
impl PaintedGlyph<'_> {
    fn span(&self) -> (Option<usize>, usize, usize) {
        (self.glyph.paragraph, self.glyph.start, self.glyph.end)
    }
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
    if layout
        .paths
        .iter()
        .any(|p| matches!(p.fill, Paint::Field(_)))
    {
        return fallback(writer, item, resources.text, "gradient_text");
    }
    let mut paths = layout.paths.iter();
    let mut painted = Vec::new();
    for g in layout.glyphs.iter().filter(|g| drawn(g)) {
        let paint = if g.ink_bounds.is_some() {
            Some(
                &paths
                    .next()
                    .ok_or_else(|| unsupported("Missing glyph paint in layout"))?
                    .fill,
            )
        } else {
            None
        };
        painted.push(PaintedGlyph { glyph: g, paint });
    }
    let groups = || painted.chunk_by(|a, b| a.span() == b.span());
    let mut kinds = BTreeMap::new();
    let mut spans = BTreeSet::new();
    let mut boundaries = BTreeMap::new();
    for group in groups() {
        if !spans.insert(group[0].span()) {
            return fallback(writer, item, resources.text, "noncontiguous_cluster");
        }
        if group.len() > 1
            && let Err(reason) = cluster::admit(group)
        {
            return fallback(writer, item, resources.text, reason);
        }
    }
    for position in &painted {
        let g = position.glyph;
        writer.control.check()?;
        if g.generated.is_some() {
            return fallback(writer, item, resources.text, "generated_glyphs");
        }
        if g.direction == crate::text::Direction::Rtl {
            return fallback(writer, item, resources.text, "right_to_left_run");
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
        // Each CMap destination is a PDF string. Bound UTF-16 bytes before
        // reserving a character code or painting any part of this text item.
        if text[offsets[g.start]..offsets[g.end]]
            .encode_utf16()
            .count()
            > 128
        {
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
    for group in groups() {
        let g = group[0].glyph;
        let text = source(document, item, g).expect("validated source range");
        let offsets = &boundaries[&g.paragraph];
        let cluster = &text[offsets[g.start]..offsets[g.end]];
        let font_kind = kinds[g.font_id.as_str()];
        let (font, code) = if group.len() == 1 {
            register(writer, g, cluster, font_kind)?
        } else {
            (cluster::font(writer, group, cluster, &kinds)?, "01".into())
        };
        let paint = group
            .iter()
            .find_map(|p| p.paint)
            .unwrap_or(&Paint::Solid([0, 0, 0, 255]));
        let m = geometry::multiply(world, glyph_matrix(g));
        stream.content.push_str("q\n");
        flat_paint(writer, stream, paint)?;
        stream.content.push_str("BT\n");
        stream.use_resource("Font", font, "1 Tf");
        stream.content.push_str(&format!("{} Tm\n", numbers(&m)?));
        let actual = group.len() > 1
            || cluster.chars().count() > 1
            || matches!(
                font_kind,
                Kind::SubsetCff | Kind::WholeNamedCff | Kind::WholeCidCff
            );
        if actual {
            stream.content.push_str(&format!(
                "/Span << /ActualText <FEFF{}> >> BDC\n",
                utf16(cluster)
            ));
        }
        stream.content.push_str(&format!("<{code}> Tj\n"));
        if actual {
            stream.content.push_str("EMC\n");
        }
        stream.content.push_str("ET\nQ\n");
        writer.text.embedded_glyphs += group.len();
    }
    Ok(true)
}

fn register(
    writer: &mut Writer,
    g: &Glyph,
    cluster: &str,
    kind: Kind,
) -> Result<(usize, String), Error> {
    let font = writer
        .text
        .fonts
        .entry(g.font_id.clone())
        .or_insert_with(|| PendingFont {
            kind,
            ids: vec![],
            codes: BTreeMap::new(),
        });
    let next = font.codes.len();
    let n = *font
        .codes
        .entry((g.glyph_id, cluster.to_owned()))
        .or_insert(next);
    let (part, code) = if kind == Kind::WholeNamedCff {
        (n / 255, format!("{:02X}", n % 255 + 1))
    } else {
        if n >= u16::MAX as usize {
            return Err(limit("PDF font character codes exhausted"));
        }
        (0, format!("{:04X}", n + 1))
    };
    if part == font.ids.len() {
        let id = writer.add(Vec::new())?;
        writer.text.fonts.get_mut(&g.font_id).unwrap().ids.push(id);
    }
    Ok((writer.text.fonts[&g.font_id].ids[part], code))
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
    for (name, font) in std::mem::take(&mut writer.text.fonts) {
        program::embed(
            writer,
            &fonts[&name],
            document.fonts[&name].face_index,
            font,
        )
        .map_err(|e| e.at_font(&name))?;
        writer.text.embedded_fonts += 1;
    }
    writer.text.clusters.clear();
    writer.text.outlined_on_page.clear();
    Ok(())
}
