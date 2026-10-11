//! Observed paragraph controls after explicit source resolution; no invented defaults.
use super::{
    text_style::{Kind, Run, Styles},
    *,
};
use std::collections::{BTreeMap, BTreeSet};

const CONTROLS: &[(Option<&str>, Option<&str>, &str, Kind)] = &[
    (
        Some("0"),
        Some("Justification"),
        "justification_code",
        Kind::Integer,
    ),
    (
        Some("1"),
        Some("FirstLineIndent"),
        "first_line_indent",
        Kind::Number,
    ),
    (Some("2"), Some("StartIndent"), "start_indent", Kind::Number),
    (Some("3"), Some("EndIndent"), "end_indent", Kind::Number),
    (Some("4"), Some("SpaceBefore"), "space_before", Kind::Number),
    (Some("5"), Some("SpaceAfter"), "space_after", Kind::Number),
    (
        Some("7"),
        Some("AutoLeading"),
        "automatic_leading_factor",
        Kind::Number,
    ),
    (
        Some("9"),
        Some("AutoHyphenate"),
        "automatic_hyphenation",
        Kind::Boolean,
    ),
    (
        Some("10"),
        Some("HyphenatedWordSize"),
        "hyphenated_word_minimum",
        Kind::Integer,
    ),
    (
        Some("11"),
        Some("PreHyphen"),
        "letters_before_hyphen",
        Kind::Integer,
    ),
    (
        Some("12"),
        Some("PostHyphen"),
        "letters_after_hyphen",
        Kind::Integer,
    ),
    // The local legacy code and global limit have different observed encodings.
    // Keep them separate until the conversion has been independently verified.
    (Some("13"), None, "hyphen_limit", Kind::Integer),
    (
        None,
        Some("ConsecutiveHyphens"),
        "local_consecutive_hyphens_code",
        Kind::Integer,
    ),
    (Some("15"), None, "hyphenate_capitalized", Kind::Boolean),
    (
        Some("17"),
        Some("WordSpacing"),
        "word_spacing_factors",
        Kind::NumberTriple,
    ),
    (
        Some("18"),
        Some("LetterSpacing"),
        "letter_spacing_factors",
        Kind::NumberTriple,
    ),
    (
        Some("19"),
        Some("GlyphSpacing"),
        "glyph_scaling_factors",
        Kind::NumberTriple,
    ),
    (Some("21"), Some("Hanging"), "hanging_roman", Kind::Boolean),
    (
        Some("29"),
        Some("EveryLineComposer"),
        "every_line_composer",
        Kind::Boolean,
    ),
    (
        Some("8"),
        Some("LeadingType"),
        "leading_direction_code",
        Kind::Integer,
    ),
    (Some("24"), None, "hanging_punctuation_code", Kind::Integer),
    (
        None,
        Some("Burasagari"),
        "local_hanging_punctuation",
        Kind::Boolean,
    ),
    (Some("25"), None, "line_breaking_order_code", Kind::Integer),
    (Some("33"), None, "paragraph_direction_code", Kind::Integer),
    (Some("37"), None, "list_tier", Kind::Integer),
    (
        Some("40"),
        None,
        "joining_elongation_width_code",
        Kind::Integer,
    ),
];

pub(super) struct Paragraphs {
    pub styles: Styles,
    pub absent_properties: usize,
    pub run_ends_without_carriage_return: usize,
}
impl Paragraphs {
    fn new() -> Self {
        Self {
            styles: Styles {
                runs: Vec::new(),
                unknown: BTreeSet::new(),
            },
            absent_properties: 0,
            run_ends_without_carriage_return: 0,
        }
    }
    fn endings(&mut self, source: &str) {
        let mut end = 0;
        let boundaries = source
            .chars()
            .filter_map(|c| {
                end += c.len_utf16();
                (c == '\r').then_some(end)
            })
            .collect::<BTreeSet<_>>();
        self.run_ends_without_carriage_return = self
            .styles
            .runs
            .iter()
            .filter(|r| !boundaries.contains(&r.end_utf16))
            .count();
    }
    pub fn local(engine: &Value, source: &str, control: &Control) -> Result<Self, Error> {
        let runs = &engine["ParagraphRun"];
        let lengths = runs["RunLengthArray"].as_array().ok_or_else(malformed)?;
        let mut out = Self::new();
        let mut end = 0;
        for (run, length) in runs["RunArray"]
            .as_array()
            .ok_or_else(malformed)?
            .iter()
            .zip(lengths)
        {
            control.check()?;
            // Positive complete UTF-16 coverage is checked by the record parser.
            end += length.as_u64().ok_or_else(malformed)? as usize;
            let properties = run
                .get("ParagraphSheet")
                .map(|v| v.as_object().ok_or_else(malformed))
                .transpose()?
                .and_then(|v| v.get("Properties"))
                .map(|v| v.as_object().ok_or_else(malformed))
                .transpose()?;
            let mut controls = BTreeMap::new();
            if let Some(properties) = properties {
                for &(_, local, name, kind) in CONTROLS {
                    if let Some(value) = local.and_then(|key| properties.get(key)) {
                        controls.insert(name, kind.read(value)?);
                    }
                }
                out.styles.unknown.extend(
                    properties
                        .keys()
                        .filter(|k| {
                            !CONTROLS
                                .iter()
                                .any(|(_, local, _, _)| *local == Some(k.as_str()))
                        })
                        .cloned(),
                );
            } else {
                out.absent_properties += 1;
            }
            out.styles.runs.push(Run {
                end_utf16: end,
                controls,
            });
        }
        out.endings(source);
        Ok(out)
    }
    pub fn global(
        runs: &[super::text_inheritance::Run<'_>],
        source: &str,
        control: &Control,
    ) -> Result<Self, Error> {
        let mut out = Self::new();
        let mut end = 0;
        for run in runs {
            control.check()?;
            end += run.length;
            let properties = run.fields.as_ref();
            let mut controls = BTreeMap::new();
            if let Some(properties) = properties {
                for &(global, _, name, kind) in CONTROLS {
                    if let Some(value) = global.and_then(|key| properties.get(key)) {
                        controls.insert(name, kind.read_node(value)?);
                    }
                }
                out.styles.unknown.extend(
                    properties
                        .keys()
                        .filter(|k| {
                            !CONTROLS
                                .iter()
                                .any(|(global, _, _, _)| *global == Some(**k))
                        })
                        .map(|k| (*k).to_owned()),
                );
            } else {
                out.absent_properties += 1;
            }
            out.styles.runs.push(Run {
                end_utf16: end,
                controls,
            });
        }
        out.endings(source);
        Ok(out)
    }
    pub fn compare(
        &self,
        local: &Self,
        text_matches: bool,
        control: &Control,
    ) -> Result<Value, Error> {
        let mut result = self.styles.compare(&local.styles, text_matches, control)?;
        for (side, paragraphs) in [("global", self), ("local", local)] {
            result[side]["absent_property_runs"] = json!(paragraphs.absent_properties);
            result[side]["run_ends_without_carriage_return"] =
                json!(paragraphs.run_ends_without_carriage_return);
        }
        result["paragraph_boundaries_semantically_validated"] = json!(false);
        result["legacy_hyphen_limit_conversion_validated"] = json!(false);
        Ok(result)
    }
}
