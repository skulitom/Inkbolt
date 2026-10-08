//! Paragraph resolution and line-local directional inspection, in logical scalar indices.
use super::{Direction, MAX_TEXT_CHARS};
use crate::Error;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use unicode_bidi::{BidiClass, BidiInfo, Level};

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Range {
    pub start: usize,
    pub end: usize,
}
#[derive(Clone, Debug, Serialize)]
pub struct Run {
    pub start: usize,
    pub end: usize,
    pub level: u8,
    pub direction: Direction,
}
#[derive(Clone, Debug, Serialize)]
pub struct Line {
    pub start: usize,
    pub end: usize,
    pub base_level: u8,
    pub levels: Vec<Option<u8>>,
    pub visual_order: Vec<usize>,
    pub runs: Vec<Run>,
}
#[derive(Clone, Debug, Serialize)]
pub struct Report {
    pub unicode_version: [u64; 3],
    pub indices: &'static str,
    pub visual_order_semantics: &'static str,
    pub paragraphs: Vec<Run>,
    pub lines: Vec<Line>,
}

pub fn is_control(c: char) -> bool {
    matches!(c, '\u{061c}' | '\u{200e}' | '\u{200f}' | '\u{202a}'..='\u{202e}' | '\u{2066}'..='\u{2069}')
}
fn removed(class: BidiClass) -> bool {
    matches!(
        class,
        BidiClass::LRE
            | BidiClass::RLE
            | BidiClass::LRO
            | BidiClass::RLO
            | BidiClass::PDF
            | BidiClass::BN
    )
}
fn direction(level: Level) -> Direction {
    if level.is_rtl() {
        Direction::Rtl
    } else {
        Direction::Ltr
    }
}

pub struct Resolved<'a> {
    info: BidiInfo<'a>,
    bytes: Vec<usize>,
    default: Level,
}
impl<'a> Resolved<'a> {
    pub fn new(text: &'a str, base: Direction) -> Result<Self, Error> {
        Self::bounded(text, base, MAX_TEXT_CHARS)
    }
    pub(super) fn with_generated(text: &'a str, base: Direction) -> Result<Self, Error> {
        Self::bounded(text, base, MAX_TEXT_CHARS + 1)
    }
    fn bounded(text: &'a str, base: Direction, maximum: usize) -> Result<Self, Error> {
        let mut bytes: Vec<_> = text.char_indices().map(|(i, _)| i).collect();
        if bytes.len() > maximum {
            return Err(Error::new(
                "RESOURCE_LIMIT",
                "Directional analysis exceeds 4096 scalars",
            ));
        }
        bytes.push(text.len());
        let level = match base {
            Direction::Ltr => Some(Level::ltr()),
            Direction::Rtl => Some(Level::rtl()),
            Direction::Auto => None,
        };
        Ok(Self {
            info: BidiInfo::new(text, level),
            bytes,
            default: level.unwrap_or(Level::ltr()),
        })
    }
    fn scalar(&self, byte: usize) -> usize {
        // Every boundary originates from scalar-aligned library runs/paragraphs.
        self.bytes
            .binary_search(&byte)
            .expect("scalar-aligned bidi boundary")
    }
    fn paragraph(&self, start: usize) -> Option<&unicode_bidi::ParagraphInfo> {
        let byte = *self.bytes.get(start)?;
        self.info
            .paragraphs
            .iter()
            .find(|p| p.range.start <= byte && byte < p.range.end)
            .or_else(|| {
                self.info.paragraphs.last().filter(|_| {
                    byte == self.info.text.len()
                        && self.info.original_classes.last() != Some(&BidiClass::B)
                })
            })
    }
    pub fn direction(&self, start: usize) -> Direction {
        direction(self.paragraph(start).map_or(self.default, |p| p.level))
    }
    pub fn line(&self, start: usize, end: usize) -> Result<Line, Error> {
        if start > end || end >= self.bytes.len() {
            return Err(Error::new(
                "INVALID_OPERATION",
                "Directional line range is outside the source",
            ));
        }
        let para = self.paragraph(start);
        let base = para.map_or(self.default, |p| p.level);
        let mut line = Line {
            start,
            end,
            base_level: base.number(),
            levels: Vec::new(),
            visual_order: Vec::new(),
            runs: Vec::new(),
        };
        if start == end {
            return Ok(line);
        }
        let para = para
            .ok_or_else(|| Error::new("INVALID_OPERATION", "Directional line has no paragraph"))?;
        if self.bytes[end] > para.range.end {
            return Err(Error::new(
                "INVALID_OPERATION",
                "Directional line cannot cross a paragraph boundary",
            ));
        }
        let (levels, runs) = self
            .info
            .visual_runs(para, self.bytes[start]..self.bytes[end]);
        for &byte in &self.bytes[start..end] {
            line.levels.push(
                (!removed(self.info.original_classes[byte])).then_some(levels[byte].number()),
            );
        }
        for run in runs {
            let a = self.scalar(run.start);
            let b = self.scalar(run.end);
            let level = levels[run.start];
            line.runs.push(Run {
                start: a,
                end: b,
                level: level.number(),
                direction: direction(level),
            });
            let mut indices: Vec<_> = (a..b)
                .filter(|&i| !removed(self.info.original_classes[self.bytes[i]]))
                .collect();
            if level.is_rtl() {
                indices.reverse();
            }
            line.visual_order.extend(indices);
        }
        Ok(line)
    }
    pub fn report(&self, lines: &[Range]) -> Result<Report, Error> {
        if lines.len() > MAX_TEXT_CHARS + 1 {
            return Err(Error::new("RESOURCE_LIMIT", "Too many directional lines"));
        }
        let paragraphs: Vec<_> = self
            .info
            .paragraphs
            .iter()
            .map(|p| Run {
                start: self.scalar(p.range.start),
                end: self.scalar(p.range.end),
                level: p.level.number(),
                direction: direction(p.level),
            })
            .collect();
        let requested: Vec<_> = if lines.is_empty() {
            if paragraphs.is_empty() {
                vec![Range { start: 0, end: 0 }]
            } else {
                paragraphs
                    .iter()
                    .map(|p| Range {
                        start: p.start,
                        end: p.end,
                    })
                    .collect()
            }
        } else {
            lines.to_vec()
        };
        let mut previous_end = 0;
        let mut output = Vec::new();
        for r in requested {
            if r.start < previous_end {
                return Err(Error::new(
                    "INVALID_OPERATION",
                    "Directional lines must be ordered and nonoverlapping",
                ));
            }
            output.push(self.line(r.start, r.end)?);
            previous_end = r.end;
        }
        let (a, b, c) = unicode_bidi::UNICODE_VERSION;
        Ok(Report {
            unicode_version: [a, b, c],
            indices: "unicode_scalars",
            visual_order_semantics: "UAX9_L1_L2_excluding_X9_controls_before_shaping_L3_L4",
            paragraphs,
            lines: output,
        })
    }
}
pub fn inspect(text: &str, direction: Direction, lines: &[Range]) -> Result<Report, Error> {
    Resolved::new(text, direction)?.report(lines)
}
