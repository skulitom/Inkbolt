//! Explicit language selections observed independently in both authoring forms.
//! Missing language stays unspecified; no native default or locale inference.
use super::*;

const LANGUAGES: &[(i64, &str)] = &[(0, "en-US"), (14, "en-GB"), (2, "fr"), (26, "tr")];

pub(super) fn from_code(code: &Value) -> Result<String, Error> {
    let code = code.as_i64().ok_or_else(malformed)?;
    LANGUAGES
        .iter()
        .find_map(|(n, language)| (*n == code).then(|| (*language).to_owned()))
        .ok_or_else(|| unsupported("Native text language code has no verified editable mapping"))
}

pub(super) fn to_code(language: &str) -> Result<i64, Error> {
    LANGUAGES
        .iter()
        .find_map(|(code, tag)| (*tag == language).then_some(*code))
        .ok_or_else(|| {
            unsupported("Native text language needs an exact supported tag: en-US, en-GB, fr or tr")
        })
}
