//! Explicit story-local hyphenation rules and source-preserving display candidates.
use super::*;
use crate::{
    control::Control,
    hyphenation::{self, Compiled},
};

pub const MAX_RULE_SETS: usize = 16;
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Mark {
    #[default]
    HyphenMinus,
    Hyphen,
}
impl Mark {
    fn character(self) -> char {
        match self {
            Self::HyphenMinus => '-',
            Self::Hyphen => '\u{2010}',
        }
    }
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub rules_id: String,
    #[serde(default)]
    pub mark: Mark,
    #[serde(default)]
    pub emergency_break: bool,
}
#[derive(Clone, Debug, Serialize)]
pub struct Placement {
    pub offset: usize,
    pub character: char,
    pub word_start: usize,
    pub word_end: usize,
    pub rules_id: String,
    pub rules_sha256: String,
    /// This diagnostic uses the virtual paragraph containing one inserted scalar.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub display_bidi: Option<bidi::Line>,
}
pub(super) struct Opportunity {
    word_start: usize,
    word_end: usize,
    hash: String,
}
pub(super) struct Selected {
    pub end: usize,
    pub glyphs: Vec<Shaped>,
    pub advance: f64,
    pub frame: Option<Frame>,
    pub hyphen: Option<Placement>,
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_HYPHENATION", message)
}
pub(crate) fn validate_resources<'a>(
    stories: impl Iterator<Item = &'a Story>,
) -> Result<(), Error> {
    let mut patterns = 0;
    let mut chars = 0;
    let mut exceptions = 0;
    let mut exception_chars = 0;
    for story in stories {
        if story.hyphenation_rules.len() > MAX_RULE_SETS {
            return Err(limit("Story exceeds 16 hyphenation rule sets"));
        }
        for rules in story.hyphenation_rules.values() {
            patterns += rules.patterns.len();
            exceptions += rules.exceptions.len();
            if patterns > hyphenation::MAX_PATTERNS || exceptions > hyphenation::MAX_EXCEPTIONS {
                return Err(limit(
                    "Document exceeds aggregate hyphenation pattern or exception count",
                ));
            }
            for p in &rules.patterns {
                if p.text.len() > hyphenation::MAX_PATTERN_CHARS * 4
                    || p.weights.len() > hyphenation::MAX_PATTERN_CHARS + 1
                {
                    return Err(limit("Hyphenation pattern exceeds storage limit"));
                }
                chars += p.text.chars().count();
            }
            for (text, positions) in &rules.exceptions {
                if text.len() > hyphenation::MAX_WORD_CHARS * 4
                    || positions.len() > hyphenation::MAX_WORD_CHARS
                {
                    return Err(limit("Hyphenation exception exceeds storage limit"));
                }
                exception_chars += text.chars().count();
            }
            if chars > hyphenation::MAX_TOTAL_PATTERN_CHARS
                || exception_chars > hyphenation::MAX_EXCEPTION_CHARS
            {
                return Err(limit(
                    "Document exceeds aggregate hyphenation rule characters",
                ));
            }
        }
    }
    Ok(())
}
pub(super) fn validate(story: &Story) -> Result<(), Error> {
    validate_resources(std::iter::once(story))?;
    for (id, rules) in &story.hyphenation_rules {
        if !valid_id(id) {
            return Err(invalid("Hyphenation rule ID must use document ID syntax"));
        }
        Compiled::new(rules, &Control::default())?;
    }
    for p in &story.paragraphs {
        if let Some(config) = &p.hyphenation {
            if !story.hyphenation_rules.contains_key(&config.rules_id) {
                return Err(invalid("Paragraph refers to missing hyphenation rules"));
            }
            if p.text.contains('\u{ad}') {
                return Err(Error::new(
                    "UNSUPPORTED",
                    "Retained soft-hyphen controls require an explicit source conversion; use rule exceptions for discretionary breaks",
                ));
            }
        }
    }
    Ok(())
}
pub(super) fn compile(story: &Story) -> Result<BTreeMap<String, Compiled>, Error> {
    story
        .hyphenation_rules
        .iter()
        .map(|(id, r)| Ok((id.clone(), Compiled::new(r, &Control::default())?)))
        .collect()
}
pub(super) fn opportunities(
    p: &Paragraph,
    rules: &BTreeMap<String, Compiled>,
    work: &mut usize,
) -> Result<BTreeMap<usize, Opportunity>, Error> {
    let mut result = BTreeMap::new();
    let Some(config) = &p.hyphenation else {
        return Ok(result);
    };
    let compiled = &rules[&config.rules_id];
    let bytes: Vec<_> = p
        .text
        .char_indices()
        .map(|(b, _)| b)
        .chain([p.text.len()])
        .collect();
    let words: Vec<_> = p.text.unicode_word_indices().collect();
    for batch in words.chunks(hyphenation::MAX_WORDS) {
        let tokens: Vec<_> = batch.iter().map(|(_, w)| (*w).to_owned()).collect();
        let report = compiled.inspect_budgeted(&tokens, &Control::default(), work)?;
        for ((byte, _), word) in batch.iter().zip(report.words) {
            let start = bytes.binary_search(byte).unwrap();
            let end = start + word.word.chars().count();
            for offset in word.breaks {
                result.insert(
                    start + offset,
                    Opportunity {
                        word_start: start,
                        word_end: end,
                        hash: report.rules_sha256.clone(),
                    },
                );
            }
        }
    }
    Ok(result)
}
fn display(frame: &Frame, end: usize, mark: char) -> Frame {
    let mut output = frame.clone();
    let byte = frame
        .text
        .char_indices()
        .nth(end)
        .map_or(frame.text.len(), |(b, _)| b);
    output.text.insert(byte, mark);
    // The generated character inherits the preceding source character's complete
    // style; all following source ranges move by one only in this temporary view.
    for range in &mut output.ranges {
        if range.start >= end {
            range.start += 1;
            range.end += 1;
        } else if range.end >= end {
            range.end += 1;
        }
    }
    output
}
#[allow(clippy::too_many_arguments)]
pub(super) fn choose(
    p: &Paragraph,
    frame: &Frame,
    analysis: &Analysis,
    opportunities: &BTreeMap<usize, Opportunity>,
    start: usize,
    available: f64,
    d: &Document,
    cache: &fonts::Cache,
    work: &mut usize,
) -> Result<Option<Selected>, Error> {
    let config = p.hyphenation.as_ref().unwrap();
    let boundaries = super::super::boundaries(&p.text);
    let mut candidates: BTreeSet<usize> = p
        .text
        .chars()
        .enumerate()
        .filter_map(|(i, c)| (i > start && c == ' ' && boundaries.contains(&i)).then_some(i))
        .collect();
    candidates.extend(opportunities.range(start + 1..).map(|(b, _)| *b));
    for end in candidates.into_iter().rev() {
        if let Some(opportunity) = opportunities.get(&end) {
            let frame = display(frame, end, config.mark.character());
            *work += frame.text.chars().count();
            if *work > MAX_SHAPING_WORK {
                return Err(limit(
                    "Hyphen display analysis exceeds shared shaping work limit",
                ));
            }
            let analysis = Analysis::with_generated(&frame)?;
            let (glyphs, advance) = shape(&frame, &analysis, start, end + 1, d, cache, work)?;
            if advance <= available {
                let hyphen = Placement {
                    offset: end,
                    character: config.mark.character(),
                    word_start: opportunity.word_start,
                    word_end: opportunity.word_end,
                    rules_id: config.rules_id.clone(),
                    rules_sha256: opportunity.hash.clone(),
                    display_bidi: analysis.line(start, end + 1)?,
                };
                return Ok(Some(Selected {
                    end,
                    glyphs,
                    advance,
                    frame: Some(frame),
                    hyphen: Some(hyphen),
                }));
            }
        } else {
            let (glyphs, advance) = shape(frame, analysis, start, end, d, cache, work)?;
            if advance <= available {
                return Ok(Some(Selected {
                    end,
                    glyphs,
                    advance,
                    frame: None,
                    hyphen: None,
                }));
            }
        }
    }
    Ok(None)
}
