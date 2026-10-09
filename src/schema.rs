//! Focused, read-only discovery derived from the same types that validate execution.
use crate::{Error, Request};
use serde_json::{Map, Value, json};
use std::{collections::BTreeSet, sync::OnceLock};

pub const OUTLINE_BYTES: usize = 12 * 1024;
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

pub(crate) fn lookup_in_workspace(
    name: &str,
    select: Option<&str>,
    force_full: bool,
    workspace: bool,
) -> Result<Value, Error> {
    if name.len() > 128 || select.is_some_and(|s| s.len() > 128) {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Schema names and selectors are limited to 128 bytes",
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
            "usage":"Choose a command or type as name. Large schemas return an outline; select a listed variant/definition, or request full:true."}),
        );
    }
    let mut value = if let Some((_, definition)) = TYPES.iter().find(|(alias, _)| *alias == name) {
        complete(full()["$defs"][definition].clone(), false)
    } else {
        arguments(name, false).ok_or_else(|| {
            Error::new(
                "SCHEMA_NOT_FOUND",
                "Unknown schema name; use schema.lookup with name index",
            )
        })?
    };
    if let Some(selector) = select {
        let selected = variants(&value)
            .into_iter()
            .find(|(_, tag, _)| *tag == selector)
            .map(|(_, _, v)| v.clone())
            .or_else(|| value.get("$defs").and_then(|d| d.get(selector)).cloned())
            .ok_or_else(|| {
                Error::new(
                    "SCHEMA_NOT_FOUND",
                    "Selector must name a listed variant or reachable definition",
                )
            })?;
        value = complete(selected, false);
    }
    if workspace {
        crate::workspace::describe(&mut value);
    }
    let bytes = serde_json::to_vec(&value).unwrap().len();
    if force_full || bytes <= OUTLINE_BYTES {
        return Ok(
            json!({"name":name, "select":select, "detail":"full", "schema":value, "schema_bytes":bytes}),
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
    Ok(
        json!({"name":name, "select":select, "detail":"outline", "schema_bytes":bytes,
        "fields":fields, "variants":variants(&value).iter().map(|(field, tag, _)| json!({"field":field,"value":tag})).collect::<Vec<_>>(),
        "definitions":value.get("$defs").and_then(Value::as_object).map(|m| m.keys().collect::<Vec<_>>()).unwrap_or_default(),
        "usage":"This is an outline, not a validation schema. Select a listed variant/definition from name, or repeat this lookup with full:true for the complete schema."}),
    )
}
