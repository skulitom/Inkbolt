//! Character-addressed placement retained independently of font glyph selection.
use super::*;

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Anchor {
    #[default]
    Start,
    Middle,
    End,
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct CharacterPosition {
    pub index: usize,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub x: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub y: Option<f64>,
    #[serde(default, skip_serializing_if = "is_zero")]
    pub dx: f64,
    #[serde(default, skip_serializing_if = "is_zero")]
    pub dy: f64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub anchor: Option<Anchor>,
}
impl CharacterPosition {
    fn absolute(&self) -> bool {
        self.x.is_some() || self.y.is_some()
    }
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Positioning {
    #[serde(default)]
    pub origin: Point,
    #[serde(default)]
    pub anchor: Anchor,
    #[serde(default)]
    pub positions: Vec<CharacterPosition>,
}

fn checked(value: f64) -> Result<f64, Error> {
    if !value.is_finite() || value.abs() > MAX_COORDINATE {
        return Err(invalid(
            "Text positions must remain finite and within the coordinate limit",
        ));
    }
    Ok(value)
}

impl Positioning {
    pub(super) fn validate(&self, frame: &Frame) -> Result<(), Error> {
        if frame.wrap
            || frame.path.is_some()
            || frame.leading.is_some()
            || frame.first_baseline.is_some()
            || frame.text.contains('\n')
            || frame.direction != Direction::Ltr
            || frame.bidi != Bidi::SingleRun
            || frame.align != Align::Left
        {
            return Err(Error::new(
                "UNSUPPORTED",
                "Character positioning requires unwrapped horizontal LTR text, align:left, and no path, paragraph leading or first-baseline setting",
            ));
        }
        let count = frame.text.chars().count();
        if self.positions.len() > MAX_TEXT_CHARS {
            return Err(limit("Text positions exceed the character limit"));
        }
        for value in self.origin {
            checked(value)?;
        }
        let boundaries = boundaries(&frame.text);
        let mut previous = None;
        for p in &self.positions {
            if p.index >= count || previous.is_some_and(|i| i >= p.index) {
                return Err(invalid(
                    "Text positions require unique increasing Unicode-scalar indices inside the text",
                ));
            }
            if p.absolute() && !boundaries.contains(&p.index) {
                return Err(invalid(
                    "Absolute text positions must be at grapheme boundaries",
                ));
            }
            if p.anchor.is_some() && p.index != 0 && !p.absolute() {
                return Err(invalid(
                    "Text anchors require the first character or an absolute position",
                ));
            }
            for value in [p.x, p.y, Some(p.dx), Some(p.dy)].into_iter().flatten() {
                checked(value)?;
            }
            previous = Some(p.index);
        }
        Ok(())
    }

    // An entry at the start follows the first replacement character; entries
    // removed with other characters disappear, and later entries keep their
    // character association. Insertion keeps the start entry on the new text.
    pub(super) fn revise(&mut self, start: usize, end: usize, inserted: usize) {
        self.positions.retain_mut(|p| {
            if p.index < start {
                return true;
            }
            if p.index == start && inserted != 0 {
                return true;
            }
            if p.index < end {
                return false;
            }
            p.index = p.index - (end - start) + inserted;
            true
        });
    }

    pub(super) fn layout(
        &self,
        frame: &Frame,
        analysis: &Analysis,
        document: &Document,
        cache: &fonts::Cache,
    ) -> Result<Layout, Error> {
        self.validate(frame)?;
        let count = frame.text.chars().count();
        let mut starts = vec![0];
        starts.extend(
            self.positions
                .iter()
                .filter(|p| p.index != 0 && p.absolute())
                .map(|p| p.index),
        );
        starts.push(count);
        let mut result = Layout {
            frame_clip: None,
            lines: vec![],
            glyphs: vec![],
            ink_bounds: None,
            overflowed: false,
            paths: vec![],
            baseline_path: None,
        };
        let mut pen = self.origin;
        let mut work = 0;
        let mut commands = 0;
        let mut next = 0;
        for chunk in starts.windows(2) {
            let (start, end) = (chunk[0], chunk[1]);
            let mut anchor = self.anchor;
            if let Some(p) = self.positions.get(next).filter(|p| p.index == start) {
                if let Some(x) = p.x {
                    pen[0] = x;
                }
                if let Some(y) = p.y {
                    pen[1] = y;
                }
                anchor = p.anchor.unwrap_or(anchor);
            }
            let base = pen;
            let mut shifts = Vec::with_capacity(end - start + 1);
            let mut shift = [0.0, 0.0];
            for index in start..end {
                if let Some(p) = self.positions.get(next).filter(|p| p.index == index) {
                    shift[0] = checked(shift[0] + p.dx)?;
                    shift[1] = checked(shift[1] + p.dy)?;
                    next += 1;
                }
                shifts.push(shift);
            }
            shifts.push(shift);
            let (mut glyphs, advance) =
                shape(frame, analysis, start, end, document, cache, &mut work)?;
            let initial = shifts[0];
            let mut extent: Option<[f64; 2]> = None;
            for g in &mut glyphs {
                let delta = shifts[g.start - start];
                g.x = checked(g.x + base[0] + delta[0])?;
                g.y = checked(g.y + base[1] + delta[1])?;
                let edge = checked(g.x + g.advance)?;
                extent = Some(extent.map_or([g.x, edge], |b| {
                    [b[0].min(g.x).min(edge), b[1].max(g.x).max(edge)]
                }));
            }
            // Continuation uses the unanchored advance. Anchoring is a visual
            // translation of this chunk, not a displacement of the next chunk.
            pen = [
                checked(base[0] + advance + shift[0])?,
                checked(base[1] + shift[1])?,
            ];
            let offset = extent.map_or(0.0, |[a, b]| {
                base[0] + initial[0]
                    - match anchor {
                        Anchor::Start => a,
                        Anchor::Middle => (a + b) / 2.0,
                        Anchor::End => b,
                    }
            });
            for g in &mut glyphs {
                g.x = checked(g.x + offset)?;
                let style = style(frame, g.style);
                let face = style.face(&g.font_id, document, cache)?;
                let scale = style.glyph_scale(&face)[1];
                let cell = [
                    g.x,
                    g.y - face.ascender() as f64 * scale,
                    g.x + g.advance,
                    g.y - face.descender() as f64 * scale,
                ];
                for value in cell {
                    checked(value)?;
                }
                result.overflowed |= outside(cell, frame);
            }
            result.lines.push(Line {
                start,
                end,
                baseline: base[1] + initial[1],
                x: base[0] + initial[0] + offset,
                advance: advance + shift[0] - initial[0],
                direction: Direction::Ltr,
                bidi: None,
            });
            append_glyphs(
                frame,
                document,
                cache,
                &mut result,
                glyphs,
                [0.0, 0.0],
                &mut commands,
            )?;
        }
        if let Some(bounds) = result.ink_bounds {
            result.overflowed |= outside(bounds, frame);
        }
        if result.overflowed && frame.overflow == Overflow::Error {
            return Err(Error::new(
                "TEXT_OVERFLOW",
                "Positioned text exceeds its declared frame; enlarge it or choose clip/visible overflow",
            ));
        }
        Ok(result)
    }
}

fn outside(b: Bounds, frame: &Frame) -> bool {
    b[0] < -limits::LAYOUT_OVERFLOW_TOLERANCE
        || b[1] < -limits::LAYOUT_OVERFLOW_TOLERANCE
        || b[2] > frame.width + limits::LAYOUT_OVERFLOW_TOLERANCE
        || b[3] > frame.height + limits::LAYOUT_OVERFLOW_TOLERANCE
}
