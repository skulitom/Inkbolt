//! Focused, read-only discovery derived from the same types that validate execution.
use crate::{Error, Request};
use serde_json::{Map, Value, json};
use std::{collections::BTreeSet, sync::OnceLock};

mod examples;

pub use crate::limits::schema::OUTLINE_BYTES;
const TYPES: &[(&str, &str)] = &[
    ("document", "Document"),
    ("operation", "Operation"),
    ("action", "Action"),
    ("item", "Item"),
    ("content", "Content"),
    ("geometry", "Geometry"),
    ("paint", "Paint"),
    ("resources", "Resources"),
];
const DEFERRED: &[&str] = &[
    "Document",
    "Operation",
    "Item",
    "Content",
    "Geometry",
    "Paint",
];

pub fn full() -> &'static Value {
    static SCHEMA: OnceLock<Value> = OnceLock::new();
    SCHEMA.get_or_init(|| json!(schemars::schema_for!(Request)))
}

pub fn commands() -> impl Iterator<Item = &'static str> {
    full()["oneOf"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v["properties"]["command"]["const"].as_str().unwrap())
}

fn refs(value: &Value, names: &mut BTreeSet<String>) {
    match value {
        Value::Object(object) => {
            if let Some(name) = object
                .get("$ref")
                .and_then(Value::as_str)
                .and_then(|r| r.strip_prefix("#/$defs/"))
            {
                names.insert(name.to_owned());
            }
            for child in object.values() {
                refs(child, names);
            }
        }
        Value::Array(values) => values.iter().for_each(|v| refs(v, names)),
        _ => {}
    }
}

fn abbreviate(value: &mut Value) {
    match value {
        Value::Object(object) => {
            if let Some(definition) = object
                .get("$ref")
                .and_then(Value::as_str)
                .and_then(|r| r.strip_prefix("#/$defs/"))
                .filter(|name| DEFERRED.contains(name))
            {
                let name = TYPES.iter().find(|(_, d)| *d == definition).unwrap().0;
                *value = json!({"type":"object", "description":format!(
                    "Deferred {name} schema. Call schema.lookup with name \"{name}\"; use select for one variant or definition. Runtime validates the complete type."
                ), "x-inkbolt-schema":{"name":name}});
                // Solid paints are RGBA arrays; a listing must not exclude them.
                if name == "paint" {
                    value.as_object_mut().unwrap().remove("type");
                    value["anyOf"] = json!([{"type":"array"}, {"type":"object"}]);
                }
                return;
            }
            for child in object.values_mut() {
                abbreviate(child);
            }
        }
        Value::Array(values) => values.iter_mut().for_each(abbreviate),
        _ => {}
    }
}

fn complete(mut value: Value, compact: bool) -> Value {
    value.as_object_mut().unwrap().remove("$defs");
    if compact {
        abbreviate(&mut value);
    }
    let mut pending = BTreeSet::new();
    refs(&value, &mut pending);
    let mut definitions = Map::new();
    while let Some(name) = pending.pop_first() {
        if definitions.contains_key(&name) {
            continue;
        }
        let mut definition = full()["$defs"][&name].clone();
        assert!(!definition.is_null(), "missing generated schema definition");
        if compact {
            abbreviate(&mut definition);
        }
        refs(&definition, &mut pending);
        definitions.insert(name, definition);
    }
    if !definitions.is_empty() {
        value["$defs"] = Value::Object(definitions);
    }
    value["$schema"] = full()["$schema"].clone();
    value
}

pub(crate) fn typed_arguments(command: &str, compact: bool) -> Option<Value> {
    let mut value = request_variant(command)?.clone();
    value["properties"].as_object_mut()?.remove("command");
    if let Some(required) = value.get_mut("required").and_then(Value::as_array_mut) {
        required.retain(|v| v != "command");
    }
    Some(complete(value, compact))
}

pub(crate) fn request_variant(command: &str) -> Option<&'static Value> {
    full()["oneOf"]
        .as_array()?
        .iter()
        .find(|v| v["properties"]["command"]["const"] == command)
}

pub fn arguments(command: &str, compact: bool) -> Option<Value> {
    let mut value = typed_arguments(command, false)?;
    crate::request::describe_arguments(&mut value);
    crate::responses::describe(command, &mut value);
    Some(complete(value, compact))
}

/// Keep command fields and small scalar choices visible while moving the
/// larger action/review/delivery trees behind an executable schema selector.
/// This changes discovery only; execution still uses the complete Request.
pub(crate) fn essential_arguments(command: &str) -> Option<Value> {
    let mut value = arguments(command, true)?;
    for field in ["action", "options", "output"] {
        let Some(property) = value["properties"].get_mut(field) else {
            continue;
        };
        let Some(definition) = property
            .get("$ref")
            .and_then(Value::as_str)
            .and_then(|reference| reference.strip_prefix("#/$defs/"))
        else {
            continue;
        };
        let mut deferred = json!({"type":"object", "description":format!(
            "Fields: schema.lookup name {command:?}, select {definition:?}. Select a listed variant if outlined. Full runtime validation applies."
        ), "x-inkbolt-schema":{"name":command,"select":definition}});
        if let Some(default) = property.get("default") {
            deferred["default"] = default.clone();
        }
        *property = deferred;
    }
    Some(complete(value, true))
}

/// MCP already identifies the schema dialect; generated titles and repeated
/// dialect annotations add no validation information. Retain defaults and all
/// structural constraints, including the complete reference alternatives.
pub(crate) fn strip_catalog_metadata(value: &mut Value) {
    let Some(object) = value.as_object_mut() else {
        return;
    };
    object.remove("$schema");
    object.remove("title");
    for (key, child) in object {
        match key.as_str() {
            "properties" | "patternProperties" | "$defs" | "dependentSchemas" => {
                if let Some(schemas) = child.as_object_mut() {
                    schemas.values_mut().for_each(strip_catalog_metadata);
                }
            }
            "oneOf" | "anyOf" | "allOf" | "prefixItems" => {
                if let Some(schemas) = child.as_array_mut() {
                    schemas.iter_mut().for_each(strip_catalog_metadata);
                }
            }
            "items"
            | "additionalProperties"
            | "not"
            | "if"
            | "then"
            | "else"
            | "contains"
            | "propertyNames"
            | "unevaluatedProperties"
            | "unevaluatedItems" => strip_catalog_metadata(child),
            _ => {}
        }
    }
}

fn variants(value: &Value) -> Vec<(&str, &str, &Value)> {
    value
        .get("oneOf")
        .or_else(|| value.get("anyOf"))
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|variant| {
            variant["properties"]
                .as_object()?
                .iter()
                .find_map(|(field, property)| {
                    Some((field.as_str(), property.get("const")?.as_str()?, variant))
                })
        })
        .collect()
}

pub fn lookup(name: &str, select: Option<&str>, force_full: bool) -> Result<Value, Error> {
    lookup_in_workspace(name, select, force_full, false)
}

fn lookup_request(name: &str, select: Option<&str>) -> Value {
    let mut request = json!({"command":"schema.lookup", "name":name});
    if let Some(select) = select {
        request["select"] = json!(select);
    }
    request
}

fn variant_path(prefix: Option<&str>, tag: &str) -> String {
    match prefix {
        Some(prefix) => format!("{prefix}/{tag}"),
        None => tag.to_owned(),
    }
}

fn selector_suggestion(value: &Value, prefix: Option<&str>, selector: &str) -> Option<String> {
    let definitions = value.get("$defs").and_then(Value::as_object);
    let mut candidates = BTreeSet::new();
    for (_, tag, _) in variants(value) {
        if tag.eq_ignore_ascii_case(selector) {
            candidates.insert(variant_path(prefix, tag));
        }
    }
    if let Some(definitions) = definitions {
        for name in definitions.keys() {
            if name.eq_ignore_ascii_case(selector) {
                candidates.insert(name.clone());
            }
        }
        // Offer a nested route only when the current level has no matching name.
        // Ambiguous nested tags must still be chosen from an explicit outline.
        if candidates.is_empty() {
            for (name, definition) in definitions {
                for (_, tag, _) in variants(definition) {
                    if tag.eq_ignore_ascii_case(selector) {
                        candidates.insert(variant_path(Some(name), tag));
                    }
                }
            }
        }
    }
    if candidates.len() == 1 {
        candidates.pop_first()
    } else {
        None
    }
}

pub(crate) fn lookup_in_workspace(
    name: &str,
    select: Option<&str>,
    force_full: bool,
    workspace: bool,
) -> Result<Value, Error> {
    if name.len() > crate::limits::schema::MAX_SELECTOR_BYTES
        || select.is_some_and(|s| s.len() > crate::limits::schema::MAX_SELECTOR_BYTES)
    {
        return Err(Error::new(
            "INVALID_REQUEST",
            format!(
                "Schema names and selectors are limited to {} bytes",
                crate::limits::schema::MAX_SELECTOR_BYTES
            ),
        ));
    }
    if name == "index" {
        if select.is_some() || force_full {
            return Err(Error::new(
                "INVALID_REQUEST",
                "The schema index has no select or full option",
            ));
        }
        return Ok(
            json!({"detail":"index", "commands":commands().collect::<Vec<_>>(),
            "types":TYPES.iter().map(|(alias, _)| alias).collect::<Vec<_>>(),
            "example_queries":examples::queries(),
            "usage":"Choose a command or type as name. Large schemas return an outline; select a listed variant/definition, or request full:true."}),
        );
    }
    let mut value = if let Some((_, definition)) = TYPES.iter().find(|(alias, _)| *alias == name) {
        complete(full()["$defs"][definition].clone(), false)
    } else {
        arguments(name, false).ok_or_else(|| {
            let mut error = Error::new(
                "SCHEMA_NOT_FOUND",
                "Unknown schema name; choose a command or type from schema.lookup with name index",
            );
            error.details = Some(Box::new(
                json!({"field":"name", "schema_lookup":lookup_request("index", None)}),
            ));
            error
        })?
    };
    let mut prefix: Option<String> = None;
    if let Some(selector) = select {
        for segment in selector.split('/') {
            let selected = variants(&value)
                .into_iter()
                .find(|(_, tag, _)| *tag == segment)
                .map(|(_, tag, v)| (v.clone(), variant_path(prefix.as_deref(), tag)))
                .or_else(|| {
                    value.get("$defs").and_then(|d| d.get(segment))
                        .map(|v| (v.clone(), segment.to_owned()))
                })
                .ok_or_else(|| {
                    let mut error = Error::new(
                        "SCHEMA_NOT_FOUND",
                        "Each select component must name a listed variant or reachable definition; use details.schema_lookup for valid choices",
                    );
                    let mut details = json!({"field":"select", "schema_lookup":lookup_request(name, prefix.as_deref())});
                    if let Some(suggestion) = selector_suggestion(&value, prefix.as_deref(), segment) {
                        details["suggested_lookup"] = lookup_request(name, Some(&suggestion));
                    }
                    error.details = Some(Box::new(details));
                    error
                })?;
            // Every reachable definition is also reachable from the named root.
            // Resetting its route avoids growing paths when definitions recur.
            prefix = Some(selected.1);
            value = complete(selected.0, false);
        }
    }
    if workspace {
        crate::workspace::describe(&mut value);
    }
    let example = examples::for_schema(name, prefix.as_deref(), &value);
    let bytes = serde_json::to_vec(&value).unwrap().len();
    if force_full || bytes <= OUTLINE_BYTES {
        return examples::attach(
            json!({"name":name, "select":select, "detail":"full", "schema":value, "schema_bytes":bytes}),
            example,
        );
    }
    let fields: Vec<Value> = value.get("properties").and_then(Value::as_object).into_iter().flat_map(|m| m.iter()).map(|(field, property)| {
        let mut summary = json!({"name":field, "required":value["required"].as_array().is_some_and(|a| a.iter().any(|v| v == field))});
        for key in ["type", "$ref", "description", "const", "default"] {
            if let Some(v) = property.get(key) {
                summary[key] = v.clone();
            }
        }
        summary
    }).collect();
    examples::attach(
        json!({"name":name, "select":select, "detail":"outline", "schema_bytes":bytes,
        "fields":fields, "variants":variants(&value).iter().map(|(field, tag, _)| json!({"field":field,"value":tag,"select":variant_path(prefix.as_deref(), tag)})).collect::<Vec<_>>(),
        "definitions":value.get("$defs").and_then(Value::as_object).map(|m| m.keys().collect::<Vec<_>>()).unwrap_or_default(),
        "usage":"This is an outline, not a validation schema. Keep name and use a variant's select value or a listed definition name. Select components separated by / follow nested variants/definitions. Repeat this lookup with full:true for the complete schema."}),
        example,
    )
}

#[cfg(test)]
mod essentials_tests {
    use super::*;

    #[test]
    fn essentials_metadata_keeps_named_fields_and_literal_values() {
        let mut schema = json!({"title":"schema title","$schema":"dialect","type":"object",
            "properties":{"title":{"type":"string","title":"property title"},
                "$schema":{"type":"string"}},"required":["title","$schema"],
            "default":{"title":"authored","$schema":"retained"},
            "const":{"title":"literal"},"enum":[{"title":"choice"}]});
        let before = schema.clone();
        strip_catalog_metadata(&mut schema);
        assert_eq!(schema["properties"]["title"], json!({"type":"string"}));
        assert_eq!(schema["properties"]["$schema"], json!({"type":"string"}));
        for key in ["default", "const", "enum", "required"] {
            assert_eq!(schema[key], before[key]);
        }
    }
}
