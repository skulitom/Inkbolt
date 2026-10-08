//! Original grapheme-safe script itemization and explicit pinned-font selection.
use super::*;
use unicode_script::{Script, ScriptExtension, UnicodeScript};

struct Unit {
    start: usize,
    end: usize,
    script: Script,
    extensions: ScriptExtension,
    paragraph: usize,
}

pub(super) struct Analysis<'a> {
    bytes: Vec<usize>,
    units: Vec<Unit>,
    bidi: Option<bidi::Resolved<'a>>,
}

fn specific(script: Script) -> bool {
    !matches!(script, Script::Common | Script::Inherited | Script::Unknown)
}

impl<'a> Analysis<'a> {
    pub(super) fn new(frame: &'a Frame) -> Result<Self, Error> {
        Self::build(frame, false)
    }
    pub(super) fn with_generated(frame: &'a Frame) -> Result<Self, Error> {
        Self::build(frame, true)
    }
    fn build(frame: &'a Frame, generated: bool) -> Result<Self, Error> {
        let mut bytes: Vec<_> = frame.text.char_indices().map(|(b, _)| b).collect();
        bytes.push(frame.text.len());
        let mut units = Vec::new();
        let mut start = 0;
        let mut paragraph = 0;
        for g in frame.text.graphemes(true) {
            let end = start + g.chars().count();
            let script = g
                .chars()
                .map(|c| c.script())
                .find(|s| specific(*s))
                .unwrap_or(Script::Common);
            units.push(Unit {
                start,
                end,
                script,
                extensions: ScriptExtension::for_str(g),
                paragraph,
            });
            if g == "\n" {
                paragraph += 1;
            }
            start = end;
        }
        // Resolve neutral graphemes in logical paragraph order, never by font
        // coverage or visual order. Script extensions constrain inherited choices.
        let mut previous = None;
        for i in 0..units.len() {
            if i > 0 && units[i].paragraph != units[i - 1].paragraph {
                previous = None;
            }
            if !specific(units[i].script) {
                let ext = units[i].extensions;
                let next = units[i + 1..]
                    .iter()
                    .take_while(|u| u.paragraph == units[i].paragraph)
                    .map(|u| u.script)
                    .find(|s| specific(*s) && ext.contains_script(*s));
                units[i].script = previous
                    .filter(|s| ext.contains_script(*s))
                    .or(next)
                    .or_else(|| ext.iter().find(|s| specific(*s)))
                    .unwrap_or(Script::Common);
            }
            if specific(units[i].script) {
                previous = Some(units[i].script);
            }
        }
        let bidi = if frame.bidi == Bidi::Unicode {
            Some(if generated {
                bidi::Resolved::with_generated(&frame.text, frame.direction)?
            } else {
                bidi::Resolved::new(&frame.text, frame.direction)?
            })
        } else {
            None
        };
        Ok(Self { bytes, units, bidi })
    }
    pub(super) fn direction(&self, frame: &Frame, start: usize) -> Direction {
        self.bidi
            .as_ref()
            .map_or(frame.direction, |b| b.direction(start))
    }
    pub(super) fn line(&self, start: usize, end: usize) -> Result<Option<bidi::Line>, Error> {
        self.bidi.as_ref().map(|b| b.line(start, end)).transpose()
    }
    fn text<'f>(&self, frame: &'f Frame, start: usize, end: usize) -> &'f str {
        &frame.text[self.bytes[start]..self.bytes[end]]
    }
}

struct Run {
    start: usize,
    end: usize,
    style: usize,
    script: Script,
    direction: Direction,
    level: Option<u8>,
}

struct Shaper<'a> {
    frame: &'a Frame,
    analysis: &'a Analysis<'a>,
    document: &'a Document,
    cache: &'a fonts::Cache,
    start: usize,
    end: usize,
    work: &'a mut usize,
}

impl Shaper<'_> {
    fn attempt(&mut self, run: &Run, id: &str) -> Result<Option<Vec<Shaped>>, Error> {
        *self.work += run.end - run.start;
        if *self.work > MAX_SHAPING_WORK {
            return Err(limit("Text shaping and font selection exceed work limit"));
        }
        let style = style(self.frame, run.style);
        let face = style.face(id, self.document, self.cache)?;
        let text = self.analysis.text(self.frame, run.start, run.end);
        let mut buffer = rustybuzz::UnicodeBuffer::new();
        buffer.push_str(text);
        // Joining context crosses style/font boundaries, but not line breaks.
        buffer.set_pre_context(self.analysis.text(self.frame, self.start, run.start));
        buffer.set_post_context(self.analysis.text(self.frame, run.end, self.end));
        buffer.set_direction(if run.direction == Direction::Rtl {
            rustybuzz::Direction::RightToLeft
        } else {
            rustybuzz::Direction::LeftToRight
        });
        buffer.set_script(
            rustybuzz::Script::from_iso15924_tag(rustybuzz::ttf_parser::Tag(
                run.script.as_iso15924_tag(),
            ))
            .ok_or_else(|| Error::new("TEXT_LAYOUT_ERROR", "Invalid script tag"))?,
        );
        if let Some(language) = &style.language {
            buffer.set_language(
                language
                    .parse()
                    .map_err(|_| invalid("Invalid text language"))?,
            );
        }
        buffer.set_flags(rustybuzz::BufferFlags::REMOVE_DEFAULT_IGNORABLES);
        buffer.guess_segment_properties();
        let controls = style.shaping_features();
        let features: Vec<_> = controls
            .iter()
            .map(|(key, value)| Ok(rustybuzz::Feature::new(fonts::tag(key)?, *value, ..)))
            .collect::<Result<_, Error>>()?;
        let shaped = rustybuzz::shape(&face, &features, buffer);
        // Coverage is a shaping result, allowing canonical composition and
        // default-ignorable controls even without individual cmap entries.
        if shaped.glyph_infos().iter().any(|g| g.glyph_id == 0) {
            return Ok(None);
        }
        if !shaped.is_empty() {
            for (key, value) in &style.features {
                if *value != 0 && !fonts::has_feature(&face, key)? {
                    return Err(Error::new(
                        "FONT_FEATURE_UNAVAILABLE",
                        format!("Selected font has no {key} feature"),
                    )
                    .at_font(id));
                }
            }
        }
        if shaped.len() > MAX_GLYPHS {
            return Err(limit("Text exceeds glyph limit"));
        }
        let scale = style.size / face.units_per_em() as f64;
        let mut boundaries: Vec<_> = shaped
            .glyph_infos()
            .iter()
            .map(|g| g.cluster as usize)
            .collect();
        boundaries.push(text.len());
        boundaries.sort_unstable();
        boundaries.dedup();
        let mut result = Vec::new();
        for (info, pos) in shaped.glyph_infos().iter().zip(shaped.glyph_positions()) {
            let cluster = info.cluster as usize;
            let next = *boundaries
                .get(boundaries.partition_point(|&v| v <= cluster))
                .ok_or_else(|| {
                    Error::new("TEXT_LAYOUT_ERROR", "Shaper returned an invalid cluster")
                })?;
            if !text.is_char_boundary(cluster) || !text.is_char_boundary(next) {
                return Err(Error::new(
                    "TEXT_LAYOUT_ERROR",
                    "Shaper returned invalid cluster boundaries",
                ));
            }
            result.push(Shaped {
                id: info.glyph_id as u16,
                style: run.style,
                font_id: id.to_owned(),
                script: run.script.short_name().into(),
                direction: run.direction,
                level: run.level,
                start: run.start + text[..cluster].chars().count(),
                end: run.start + text[..next].chars().count(),
                x: pos.x_offset as f64 * scale,
                y: -(pos.y_offset as f64) * scale,
                advance: pos.x_advance as f64 * scale,
            });
        }
        Ok(Some(result))
    }

    fn missing(&self, run: &Run) -> Error {
        let s = style(self.frame, run.style);
        Error::new("MISSING_GLYPH", format!(
            "No declared font shapes the complete grapheme at scalar range {}..{} ({}); tried {}",
            run.start, run.end,
            self.analysis.text(self.frame, run.start, run.end).chars()
                .map(|c| format!("U+{:04X}", c as u32)).collect::<Vec<_>>().join(" "),
            s.font_ids().cloned().collect::<Vec<_>>().join(", ")))
            .at_font(&s.font_id)
    }

    fn select(&mut self, run: &Run) -> Result<Vec<Shaped>, Error> {
        let ids: Vec<_> = style(self.frame, run.style).font_ids().cloned().collect();
        // Prefer one face covering the complete script/style run so a fallback
        // does not fragment a joining word or a multi-character substitution.
        for id in &ids {
            if let Some(glyphs) = self.attempt(run, id)? {
                return Ok(glyphs);
            }
        }
        // Directional boundaries are resolved before shaping. Segment inside
        // this run so invisible prepends crossing a level boundary cannot drop
        // the following grapheme during fallback.
        let mut at = run.start;
        let ranges: Vec<_> = self
            .analysis
            .text(self.frame, run.start, run.end)
            .graphemes(true)
            .map(|g| {
                let a = at;
                at += g.chars().count();
                (a, at)
            })
            .collect();
        let mut selected: Vec<(Run, String)> = Vec::new();
        for (start, end) in ranges {
            let unit = Run {
                start,
                end,
                style: run.style,
                script: run.script,
                direction: run.direction,
                level: run.level,
            };
            let mut chosen = None;
            for id in &ids {
                if self.attempt(&unit, id)?.is_some() {
                    chosen = Some(id.clone());
                    break;
                }
            }
            let id = chosen.ok_or_else(|| self.missing(&unit))?;
            if let Some((last, last_id)) = selected.last_mut()
                && *last_id == id
                && last.end == start
            {
                last.end = end;
            } else {
                selected.push((unit, id));
            }
        }
        if run.direction == Direction::Rtl {
            selected.reverse();
        }
        let mut result = Vec::new();
        for (part, id) in selected {
            result.extend(self.attempt(&part, &id)?.ok_or_else(|| {
                Error::new(
                    "MISSING_GLYPH",
                    "Selected fallback does not cover the coalesced shaping run",
                )
                .at_font(&id)
            })?);
            if result.len() > MAX_GLYPHS {
                return Err(limit("Text exceeds glyph limit"));
            }
        }
        Ok(result)
    }
}

pub(super) fn shape(
    frame: &Frame,
    analysis: &Analysis,
    start: usize,
    end: usize,
    document: &Document,
    cache: &fonts::Cache,
    work: &mut usize,
) -> Result<(Vec<Shaped>, f64), Error> {
    let mut runs: Vec<Run> = Vec::new();
    let line = analysis.line(start, end)?;
    let parts = line.as_ref().map_or_else(
        || {
            vec![bidi::Run {
                start,
                end,
                level: if frame.direction == Direction::Rtl {
                    1
                } else {
                    0
                },
                direction: frame.direction,
            }]
        },
        |l| l.runs.clone(),
    );
    // The paragraph resolver orders directional runs. Shaping orders glyphs
    // inside each run; reversing those glyphs again would corrupt joining/marks.
    for part in parts {
        let mut logical: Vec<Run> = Vec::new();
        for u in analysis
            .units
            .iter()
            .filter(|u| u.end > part.start && u.start < part.end)
        {
            let a = u.start.max(part.start);
            let b = u.end.min(part.end);
            let s = style_index(frame, a);
            if let Some(last) = logical.last_mut()
                && last.end == a
                && last.style == s
                && last.script == u.script
            {
                last.end = b;
            } else {
                logical.push(Run {
                    start: a,
                    end: b,
                    style: s,
                    script: u.script,
                    direction: part.direction,
                    level: line.as_ref().map(|_| part.level),
                });
            }
        }
        if part.direction == Direction::Rtl {
            logical.reverse();
        }
        runs.extend(logical);
    }
    let mut shaper = Shaper {
        frame,
        analysis,
        document,
        cache,
        start,
        end,
        work,
    };
    let mut glyphs = Vec::new();
    for run in runs {
        glyphs.extend(shaper.select(&run)?);
        if glyphs.len() > MAX_GLYPHS {
            return Err(limit("Text exceeds glyph limit"));
        }
    }
    let mut advance = 0.0;
    for i in 0..glyphs.len() {
        let tracking = if i + 1 < glyphs.len()
            && (glyphs[i].start != glyphs[i + 1].start || glyphs[i].style != glyphs[i + 1].style)
        {
            style(frame, glyphs[i].style).tracking
        } else {
            0.0
        };
        glyphs[i].x += advance;
        glyphs[i].advance += tracking;
        if glyphs[i].advance < 0.0 {
            return Err(Error::new(
                "UNSUPPORTED",
                "Tracking cannot reverse glyph advance",
            ));
        }
        advance += glyphs[i].advance;
    }
    Ok((glyphs, advance))
}
