//! Recover shown Unicode and verify it against the glyphs the PDF actually paints.
use super::*;
use crate::{
    fonts,
    geometry::multiply,
    model::{Content, Matrix, identity},
    text as layout,
};
use rustybuzz::ttf_parser::{Face, GlyphId, OutlineBuilder};
use schemars::JsonSchema;
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::path::PathBuf;
mod cmap;
mod font;

#[derive(Clone, Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields, rename = "PdfFontBinding")]
pub struct FontBinding {
    /// SHA-256 of the decoded font program in this PDF, including its subset when present.
    pub embedded_sha256: String,
    pub font_id: String,
    pub font: fonts::Font,
}
#[derive(Default)]
pub struct FontOptions {
    pub font_bindings: Vec<FontBinding>,
    pub font_root: Option<PathBuf>,
}
pub(super) struct Fonts {
    bindings: BTreeMap<String, FontBinding>,
    root: Option<PathBuf>,
    cache: fonts::Cache,
    embedded: BTreeMap<Id, font::Font>,
    checked: BTreeSet<(Id, u16, u16)>,
    pub sources: Vec<serde_json::Value>,
}
impl Fonts {
    pub fn new(options: FontOptions, control: &Control) -> Result<Self, Error> {
        if options.font_bindings.len() > fonts::MAX_FONTS {
            return Err(limit("Too many PDF font bindings"));
        }
        if let Some(path) = &options.font_root {
            control.check_path(path)?;
        }
        let mut bindings = BTreeMap::new();
        let mut ids = BTreeMap::new();
        for b in options.font_bindings {
            fonts::validate(&b.font)?;
            if !fonts::valid_hash(&b.embedded_sha256)
                || !crate::model::valid_id(&b.font_id)
                || ids
                    .insert(b.font_id.clone(), b.font.clone())
                    .is_some_and(|last| last != b.font)
                || bindings.insert(b.embedded_sha256.clone(), b).is_some()
            {
                return Err(invalid("Invalid or conflicting PDF font binding"));
            }
        }
        Ok(Self {
            bindings,
            root: options.font_root,
            cache: Default::default(),
            embedded: Default::default(),
            checked: Default::default(),
            sources: vec![],
        })
    }
}

#[derive(Default)]
struct Outline {
    hash: Sha256,
    commands: usize,
}
impl Outline {
    fn write(&mut self, op: u8, coords: &[f32]) {
        self.commands += 1;
        if self.commands > layout::MAX_OUTLINE_COMMANDS {
            return;
        }
        self.hash.update([op]);
        for v in coords {
            self.hash.update(v.to_le_bytes());
        }
    }
}
impl OutlineBuilder for Outline {
    fn move_to(&mut self, x: f32, y: f32) {
        self.write(0, &[x, y]);
    }
    fn line_to(&mut self, x: f32, y: f32) {
        self.write(1, &[x, y]);
    }
    fn quad_to(&mut self, a: f32, b: f32, x: f32, y: f32) {
        self.write(2, &[a, b, x, y]);
    }
    fn curve_to(&mut self, a: f32, b: f32, c: f32, d: f32, x: f32, y: f32) {
        self.write(3, &[a, b, c, d, x, y]);
    }
    fn close(&mut self) {
        self.write(4, &[]);
    }
}
fn outline(face: &Face, glyph: GlyphId) -> Result<([u8; 32], usize), Error> {
    let mut path = Outline::default();
    if !fonts::draw_outline(face, glyph, &mut path)? && path.commands != 0 {
        return Err(invalid("Incomplete painted glyph outline"));
    }
    if path.commands > layout::MAX_OUTLINE_COMMANDS {
        return Err(limit("PDF glyph outline exceeds path budget"));
    }
    Ok((path.hash.finalize().into(), path.commands))
}

impl drawing::Drawing<'_> {
    /// A native frame retains each shown string's source text, paint and baseline.
    /// The PDF text matrix advances by its declared widths, in text space.
    pub fn show_text(
        &mut self,
        state: &drawing::State,
        matrix: Matrix,
        bytes: &[u8],
        loc: (Id, usize),
    ) -> Result<f64, Error> {
        let id = state
            .font
            .ok_or_else(|| unsupported("Painted PDF text requires an indirect font resource"))?;
        if bytes.is_empty() {
            return Ok(0.);
        }
        if !self.fonts.embedded.contains_key(&id) {
            if self.fonts.embedded.len() >= fonts::MAX_FONTS {
                return Err(limit("Too many PDF font resources"));
            }
            let encoded = font::Font::read(self.pdf, id, &mut self.remaining_bytes, self.control)?;
            let Some(binding) = self.fonts.bindings.get(&encoded.digest) else {
                let mut err = Error::new(
                    "PDF_FONT_NOT_BOUND",
                    "Bind this embedded program to a licensed editable font from font.import",
                );
                err.details = Some(Box::new(
                    json!({"page_index":self.page_index,"object":loc.0.0,"generation":loc.0.1,
                    "decoded_byte_offset":loc.1,"font_object":id.0,"font_generation":id.1,"embedded_sha256":encoded.digest}),
                ));
                return Err(err);
            };
            if !self.fonts.cache.contains_key(&binding.font_id) {
                let length = usize::try_from(binding.font.bytes)
                    .map_err(|_| limit("PDF bound font too large"))?;
                if length > self.remaining_bytes {
                    return Err(limit("Bound PDF fonts exceed decoded resource budget"));
                }
                self.remaining_bytes -= length;
                let bytes = fonts::load(&binding.font, self.fonts.root.as_deref())
                    .map_err(|e| e.at_font(&binding.font_id))?;
                self.fonts.cache.insert(binding.font_id.clone(), bytes);
                self.document
                    .fonts
                    .insert(binding.font_id.clone(), binding.font.clone());
            }
            self.fonts.sources.push(json!({"object":id.0,"generation":id.1,"program_object":encoded.stream.0,
                "program_generation":encoded.stream.1,"embedded_sha256":encoded.digest,"font_id":binding.font_id}));
            self.fonts.embedded.insert(id, encoded);
        }
        let encoded = &self.fonts.embedded[&id];
        let binding = &self.fonts.bindings[&encoded.digest];
        let local = Face::parse(&self.fonts.cache[&binding.font_id], binding.font.face_index)
            .map_err(|_| invalid("Unreadable bound font"))?;
        let embedded =
            Face::parse(&encoded.bytes, 0).map_err(|_| invalid("Unreadable embedded font"))?;
        if local.units_per_em() != embedded.units_per_em()
            || local.is_variable()
            || local.tables().glyf.is_some() != embedded.tables().glyf.is_some()
            || local.tables().cff.is_some() != embedded.tables().cff.is_some()
        {
            return Err(unsupported(
                "Bound font has different outline units or technology",
            ));
        }
        if !bytes.len().is_multiple_of(encoded.unicode.width) {
            return Err(invalid("Incomplete PDF text character code"));
        }
        let mut expected = Vec::new();
        let mut text = String::new();
        let mut scalar_count = 0;
        let mut advance = 0.;
        for raw in bytes.chunks_exact(encoded.unicode.width) {
            let code = match raw {
                [a] => u16::from(*a),
                [a, b] => u16::from_be_bytes([*a, *b]),
                _ => unreachable!(),
            };
            let chars = encoded
                .unicode
                .values
                .get(&code)
                .ok_or_else(|| unsupported("Painted PDF code lacks a ToUnicode mapping"))?;
            if chars.chars().any(char::is_control) {
                return Err(unsupported("Control text in painted PDF label"));
            }
            let start = scalar_count;
            scalar_count += chars.chars().count();
            if scalar_count > layout::MAX_TEXT_CHARS || expected.len() >= layout::MAX_GLYPHS {
                return Err(limit("PDF label exceeds native text limits"));
            }
            text.push_str(chars);
            expected.push((
                start,
                scalar_count,
                encoded.glyph(&embedded, code)?,
                advance,
            ));
            advance += encoded.width(code)? * state.font_size / 1000.;
        }
        if state.alpha != 1. || state.blend != crate::model::BlendMode::Normal {
            return Err(unsupported(
                "Editable PDF text requires an opaque normal fill",
            ));
        }
        if matches!(
            state.space,
            color::FillSpace::Cmyk | color::FillSpace::Spot(_)
        ) {
            return Err(unsupported(
                "Native print text is unsupported in editable PDF import",
            ));
        }
        let paint = state
            .space
            .paint(state.values, state.alpha, &mut self.swatches)?;
        let mut frame = layout::Frame {
            text,
            width: crate::model::MAX_COORDINATE,
            height: crate::model::MAX_COORDINATE,
            style: layout::Style {
                font_id: binding.font_id.clone(),
                fallback_fonts: vec![],
                language: None,
                font_variations: Default::default(),
                features: Default::default(),
                size: state.font_size,
                fill: paint,
                tracking: 0.,
                horizontal_scale: 1.,
                vertical_scale: 1.,
                baseline_shift: 0.,
            },
            ranges: vec![],
            align: layout::Align::Left,
            direction: layout::Direction::Ltr,
            bidi: Default::default(),
            wrap: false,
            leading: None,
            first_baseline: None,
            overflow: layout::Overflow::Visible,
            path: None,
            positioning: None,
        };
        layout::validate(&frame, &self.document, identity())?;
        let shaped = layout::layout(&frame, &self.document, &self.fonts.cache)?;
        let [line] = shaped.lines.as_slice() else {
            return Err(unsupported("Unsupported multiline PDF text"));
        };
        let tolerance = state.font_size * 1e-9;
        if expected.len() != shaped.glyphs.len() || (line.advance - advance).abs() > tolerance {
            return Err(unsupported(
                "Bound face does not reproduce PDF glyph count or advances",
            ));
        }
        for ((start, end, gid, x), g) in expected.into_iter().zip(&shaped.glyphs) {
            self.control.check()?;
            if (g.start, g.end) != (start, end)
                || (g.origin[0] - x).abs() > tolerance
                || (g.origin[1] - line.baseline).abs() > tolerance
            {
                return Err(unsupported(
                    "Bound face does not reproduce painted PDF glyph placement",
                ));
            }
            if self.fonts.checked.insert((id, gid.0, g.glyph_id))
                && outline(&embedded, gid)? != outline(&local, GlyphId(g.glyph_id))?
            {
                return Err(unsupported(
                    "Bound font outline differs from the painted PDF glyph",
                ));
            }
        }
        frame.width = advance.max(0.001);
        frame.height = ((f64::from(local.ascender()) - f64::from(local.descender()))
            * state.font_size
            / f64::from(local.units_per_em()))
        .max(0.001);
        let transform = multiply(
            multiply(state.matrix, matrix),
            [1., 0., 0., -1., 0., line.baseline],
        );
        self.add(
            state.parent.clone(),
            Content::Text {
                frame: Box::new(frame),
            },
            None,
            (1., state.blend),
            transform,
            loc,
        )?;
        Ok(advance)
    }
}
