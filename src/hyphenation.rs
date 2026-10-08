//! Original bounded weighted-pattern matching for discretionary text breaks.
//! This module computes opportunities only; it never rewrites or lays out text.
use crate::{Error, control::Control};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

pub const MAX_PATTERNS: usize = 32_768;
pub const MAX_PATTERN_CHARS: usize = 64;
pub const MAX_TOTAL_PATTERN_CHARS: usize = 262_144;
pub const MAX_EXCEPTIONS: usize = 4_096;
pub const MAX_EXCEPTION_CHARS: usize = 65_536;
pub const MAX_WORD_CHARS: usize = 256;
pub const MAX_WORDS: usize = 256;
pub const MAX_TOTAL_WORD_CHARS: usize = 4_096;
pub const MAX_WORK: usize = 4_194_304;

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Case {
    #[default]
    Exact,
    AsciiLower,
}
impl Case {
    fn apply(self, text: &str) -> String {
        match self {
            Self::Exact => text.to_owned(),
            Self::AsciiLower => text.to_ascii_lowercase(),
        }
    }
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Pattern {
    pub text: String,
    /// One priority for every scalar gap, including both outside gaps.
    pub weights: Vec<u8>,
    #[serde(default)]
    pub at_start: bool,
    #[serde(default)]
    pub at_end: bool,
}
fn minimum() -> usize {
    2
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Rules {
    #[serde(default)]
    pub case: Case,
    #[serde(default = "minimum")]
    pub min_left: usize,
    #[serde(default = "minimum")]
    pub min_right: usize,
    #[serde(default)]
    pub patterns: Vec<Pattern>,
    /// Exact canonical tokens mapped to replacement candidate scalar offsets.
    /// An empty list explicitly disables pattern breaks for that token.
    #[serde(default)]
    pub exceptions: BTreeMap<String, Vec<usize>>,
}
#[derive(Default)]
struct Node {
    children: BTreeMap<char, usize>,
    terminals: BTreeMap<(bool, bool), Vec<u8>>,
}
pub struct Compiled {
    nodes: Vec<Node>,
    exceptions: BTreeMap<String, Vec<usize>>,
    case: Case,
    min_left: usize,
    min_right: usize,
    sha256: String,
}
#[derive(Debug, Serialize)]
pub struct Word {
    pub word: String,
    pub matching_word: String,
    pub source: &'static str,
    /// None for an exception, which replaces the pattern result entirely.
    pub weights: Option<Vec<u8>>,
    pub candidates: Vec<usize>,
    pub grapheme_boundaries: Vec<usize>,
    pub breaks: Vec<usize>,
    pub parts: Vec<String>,
}
#[derive(Debug, Serialize)]
pub struct Report {
    pub rules_sha256: String,
    pub indices: &'static str,
    pub minima_units: &'static str,
    pub words: Vec<Word>,
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_HYPHENATION", message)
}
fn limit(message: &str) -> Error {
    Error::new("RESOURCE_LIMIT", message)
}
fn token(text: &str, max: usize) -> Result<usize, Error> {
    // Bound allocations and Unicode scanning even for direct library callers.
    if text.len() > max * 4 {
        return Err(limit("Hyphenation token exceeds its scalar limit"));
    }
    let count = text.chars().count();
    if count > max {
        return Err(limit("Hyphenation token exceeds its scalar limit"));
    }
    if count == 0
        || text.chars().any(|c| {
            c.is_whitespace()
                || c.is_control()
                || matches!(c, '\u{ad}' | '\u{fffe}' | '\u{ffff}')
                || crate::text::bidi::is_control(c)
        })
    {
        return Err(invalid(
            "Hyphenation requires nonempty tokens without whitespace, controls or soft hyphens",
        ));
    }
    Ok(count)
}
impl Compiled {
    pub fn new(rules: &Rules, control: &Control) -> Result<Self, Error> {
        control.check()?;
        if !(1..=128).contains(&rules.min_left) || !(1..=128).contains(&rules.min_right) {
            return Err(invalid("Hyphenation minima must be in 1..=128 graphemes"));
        }
        if rules.patterns.len() > MAX_PATTERNS || rules.exceptions.len() > MAX_EXCEPTIONS {
            return Err(limit("Too many hyphenation patterns or exceptions"));
        }
        let mut result = Self {
            nodes: vec![Node::default()],
            exceptions: BTreeMap::new(),
            case: rules.case,
            min_left: rules.min_left,
            min_right: rules.min_right,
            sha256: String::new(),
        };
        let mut total = 0;
        for pattern in &rules.patterns {
            control.check()?;
            total += token(&pattern.text, MAX_PATTERN_CHARS)?;
            if total > MAX_TOTAL_PATTERN_CHARS {
                return Err(limit("Hyphenation patterns exceed aggregate scalar limit"));
            }
            if pattern.text != rules.case.apply(&pattern.text) {
                return Err(invalid("Pattern text must use the declared canonical case"));
            }
            if pattern.weights.len() != pattern.text.chars().count() + 1
                || pattern.weights.iter().any(|v| *v > 9)
            {
                return Err(invalid(
                    "Patterns require one integer weight in 0..=9 per scalar gap",
                ));
            }
            let mut node = 0;
            for c in pattern.text.chars() {
                node = if let Some(next) = result.nodes[node].children.get(&c) {
                    *next
                } else {
                    let next = result.nodes.len();
                    result.nodes.push(Node::default());
                    result.nodes[node].children.insert(c, next);
                    next
                };
            }
            let weights = result.nodes[node]
                .terminals
                .entry((pattern.at_start, pattern.at_end))
                .or_insert_with(|| vec![0; pattern.weights.len()]);
            for (value, incoming) in weights.iter_mut().zip(&pattern.weights) {
                *value = (*value).max(*incoming);
            }
        }
        let mut total = 0;
        for (word, positions) in &rules.exceptions {
            control.check()?;
            let n = token(word, MAX_WORD_CHARS)?;
            total += n;
            if total > MAX_EXCEPTION_CHARS {
                return Err(limit(
                    "Hyphenation exceptions exceed aggregate scalar limit",
                ));
            }
            let boundaries = crate::text::boundaries(word);
            if *word != rules.case.apply(word)
                || positions.len() >= n
                || positions.windows(2).any(|w| w[0] >= w[1])
                || positions
                    .iter()
                    .any(|p| *p == 0 || *p >= n || !boundaries.contains(p))
            {
                return Err(invalid(
                    "Exceptions require canonical case and strictly increasing internal grapheme boundaries",
                ));
            }
            result.exceptions.insert(word.clone(), positions.clone());
        }
        let bytes = serde_json::to_vec(rules)
            .map_err(|_| invalid("Unable to serialize hyphenation rules"))?;
        result.sha256 = format!("{:x}", Sha256::digest(bytes));
        Ok(result)
    }

    pub fn inspect(&self, words: &[String], control: &Control) -> Result<Report, Error> {
        self.inspect_budgeted(words, control, &mut 0)
    }
    pub(crate) fn inspect_budgeted(
        &self,
        words: &[String],
        control: &Control,
        work: &mut usize,
    ) -> Result<Report, Error> {
        control.check()?;
        if words.len() > MAX_WORDS {
            return Err(limit("Too many hyphenation words"));
        }
        let mut total = 0;
        // Validate the complete batch before computing any result.
        for word in words {
            total += token(word, MAX_WORD_CHARS)?;
            if total > MAX_TOTAL_WORD_CHARS {
                return Err(limit("Hyphenation words exceed aggregate scalar limit"));
            }
        }
        let mut result = Vec::with_capacity(words.len());
        for word in words {
            control.check()?;
            let matching_word = self.case.apply(word);
            let chars: Vec<_> = matching_word.chars().collect();
            let n = chars.len();
            let (source, weights, candidates) = if let Some(p) = self.exceptions.get(&matching_word)
            {
                ("exception", None, p.clone())
            } else {
                let mut weights = vec![0u8; n + 1];
                for start in 0..n {
                    control.check()?;
                    let mut node = 0;
                    for (end, c) in chars.iter().enumerate().skip(start).take(MAX_PATTERN_CHARS) {
                        charge(work, 1)?;
                        let Some(next) = self.nodes[node].children.get(c) else {
                            break;
                        };
                        node = *next;
                        for ((at_start, at_end), incoming) in &self.nodes[node].terminals {
                            if (*at_start && start != 0) || (*at_end && end + 1 != n) {
                                continue;
                            }
                            charge(work, incoming.len())?;
                            for (i, weight) in incoming.iter().enumerate() {
                                weights[start + i] = weights[start + i].max(*weight);
                            }
                        }
                    }
                }
                let candidates = (1..n).filter(|p| weights[*p] % 2 == 1).collect();
                ("patterns", Some(weights), candidates)
            };
            let grapheme_boundaries: Vec<_> = crate::text::boundaries(word).into_iter().collect();
            let count = grapheme_boundaries.len() - 1;
            let breaks: Vec<_> = candidates
                .iter()
                .copied()
                .filter(|p| {
                    grapheme_boundaries
                        .binary_search(p)
                        .is_ok_and(|i| i >= self.min_left && count - i >= self.min_right)
                })
                .collect();
            let bytes: Vec<_> = word
                .char_indices()
                .map(|(i, _)| i)
                .chain([word.len()])
                .collect();
            let offsets: Vec<_> = std::iter::once(0)
                .chain(breaks.iter().copied())
                .chain([n])
                .collect();
            let parts = offsets
                .windows(2)
                .map(|p| word[bytes[p[0]]..bytes[p[1]]].to_owned())
                .collect();
            result.push(Word {
                word: word.clone(),
                matching_word,
                source,
                weights,
                candidates,
                grapheme_boundaries,
                breaks,
                parts,
            });
        }
        control.check()?;
        Ok(Report {
            rules_sha256: self.sha256.clone(),
            indices: "unicode_scalars",
            minima_units: "extended_graphemes",
            words: result,
        })
    }
}
fn charge(work: &mut usize, amount: usize) -> Result<(), Error> {
    *work += amount;
    if *work > MAX_WORK {
        Err(limit("Hyphenation matching exceeds aggregate work limit"))
    } else {
        Ok(())
    }
}
