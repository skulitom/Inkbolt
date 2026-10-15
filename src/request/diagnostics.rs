//! Advisory schema hints after typed rejection; never an alternate validator.
use crate::limits::request::MAX_DIAGNOSTIC_BYTES as MAX_BYTES;
use crate::{Error, limits, schema};
use serde_json::{Value, json};
use std::{collections::BTreeSet, fmt::Write};

pub(super) fn command(value: &Value) -> Option<String> {
    value
        .get("command")?
        .as_str()
        .filter(|name| name.len() <= limits::schema::MAX_SELECTOR_BYTES)
        .map(str::to_owned)
}

struct Message(String);
impl Write for Message {
    fn write_str(&mut self, text: &str) -> std::fmt::Result {
        if self.0.len().saturating_add(text.len()) > MAX_BYTES {
            return Err(std::fmt::Error);
        }
        self.0.push_str(text);
        Ok(())
    }
}

fn required_properties<'a>(node: &'a Value, field: &str, found: &mut Vec<&'a Value>) {
    if node["required"]
        .as_array()
        .is_some_and(|required| required.iter().any(|name| name == field))
        && let Some(property) = node.get("properties").and_then(|p| p.get(field))
    {
        found.push(property);
    }
    // Walk only compiled schema structure. Definitions are visited separately,
    // once each; references never recurse and caller values never enter here.
    for keyword in ["oneOf", "anyOf", "allOf"] {
        for branch in node[keyword].as_array().into_iter().flatten() {
            required_properties(branch, field, found);
        }
    }
    if let Some(properties) = node.get("properties").and_then(Value::as_object) {
        for property in properties.values() {
            required_properties(property, field, found);
        }
    }
}

fn missing_field(command: &str, field: &str) -> Option<Value> {
    let arguments = schema::typed_arguments(command, false)?;
    let mut owners = BTreeSet::new();
    let mut properties = Vec::new();
    required_properties(&arguments, field, &mut properties);
    if !properties.is_empty() {
        owners.insert(None);
    }
    if let Some(definitions) = arguments.get("$defs").and_then(Value::as_object) {
        for (name, definition) in definitions {
            let before = properties.len();
            required_properties(definition, field, &mut properties);
            if properties.len() != before {
                owners.insert(Some(name.as_str()));
            }
        }
    }
    let first = *properties.first()?;
    let mut query = json!({"command":"schema.lookup","name":command});
    if owners.len() == 1
        && let Some(Some(name)) = owners.first()
        && name.len() <= limits::schema::MAX_SELECTOR_BYTES
    {
        query["select"] = json!(name);
    }
    let mut details = json!({"reason":"missing_field","field":field,"schema_lookup":query});
    if properties.iter().all(|property| *property == first) {
        let mut expected = serde_json::Map::new();
        for name in ["type", "enum", "const", "$ref", "format"] {
            if let Some(value) = first.get(name) {
                expected.insert(name.to_owned(), value.clone());
            }
        }
        if !expected.is_empty() {
            details["expected"] = Value::Object(expected);
        }
    }
    Some(details)
}

pub(super) fn invalid_arguments(command: Option<&str>, cause: serde_json::Error) -> Error {
    let command = command.filter(|name| schema::request_variant(name).is_some());
    let mut fallback = Error::new(
        "INVALID_REQUEST",
        "Arguments must match the command schema; use details.schema_lookup",
    );
    fallback.details = Some(Box::new(json!({"reason":"invalid_arguments",
        "schema_lookup":{"command":"schema.lookup","name":command.unwrap_or("index")}})));
    let Some(command) = command else {
        return fallback;
    };
    let mut message = Message(String::new());
    // Serde's pinned missing-field wording is only a hint. Accept its field name
    // only when the generated schema confirms it is required; any other wording
    // or ambiguity falls back to a working lookup, never guessed execution.
    if write!(&mut message, "{cause}").is_err() {
        return fallback;
    }
    let Some(field) = message
        .0
        .strip_prefix("missing field `")
        .and_then(|s| s.strip_suffix('`'))
        .filter(|s| s.len() <= limits::schema::MAX_SELECTOR_BYTES)
    else {
        return fallback;
    };
    let Some(details) = missing_field(command, field) else {
        return fallback;
    };
    let mut error = Error::new(
        "INVALID_REQUEST",
        format!(
            "Required field `{field}` is missing; use details.schema_lookup for its definition"
        ),
    );
    error.details = Some(Box::new(details));
    if serde_json::to_vec(&error).unwrap().len() > MAX_BYTES {
        error
            .details
            .as_mut()
            .unwrap()
            .as_object_mut()
            .unwrap()
            .remove("expected");
    }
    if serde_json::to_vec(&error).unwrap().len() > MAX_BYTES {
        return fallback;
    }
    error
}
