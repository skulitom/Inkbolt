//! Focused, read-only discovery derived from the same types that validate execution.
use crate::{Error, Request};
use serde_json::{Map, Value, json};
use std::{collections::BTreeSet, sync::OnceLock};

mod examples;
mod fields;

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
    if value.is_boolean() {
        return value;
    }
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

fn argument_root(command: &str) -> Option<Value> {
    let mut value = request_variant(command)?.clone();
    value["properties"].as_object_mut()?.remove("command");
    if let Some(required) = value.get_mut("required").and_then(Value::as_array_mut) {
        required.retain(|v| v != "command");
    }
    Some(value)
}

pub(crate) fn typed_arguments(command: &str, compact: bool) -> Option<Value> {
    Some(complete(argument_root(command)?, compact))
}

pub(crate) fn request_variant(command: &str) -> Option<&'static Value> {
    full()["oneOf"]
        .as_array()?
        .iter()
        .find(|v| v["properties"]["command"]["const"] == command)
}

fn described_root(command: &str) -> Option<Value> {
    let mut value = argument_root(command)?;
    crate::request::describe_arguments(&mut value);
    crate::responses::describe(command, &mut value);
    Some(value)
}

pub fn arguments(command: &str, compact: bool) -> Option<Value> {
    Some(complete(described_root(command)?, compact))
}

fn command_fields(family: Option<&str>, workspace: bool) -> Result<Value, Error> {
    let mut rows = Map::new();
    for name in commands().filter(|name| family.is_none() || name.split('.').next() == family) {
        let mut root = described_root(name).expect("listed command has an argument schema");
        if workspace {
            crate::workspace::describe_essentials(&mut root);
        }
        let required = root["required"].as_array();
        let (required, optional): (Vec<_>, Vec<_>) = root["properties"]
            .as_object()
            .expect("command arguments are an object")
            .keys()
            .partition(|key| required.is_some_and(|list| list.iter().any(|v| v == key.as_str())));
        rows.insert(
            name.into(),
            json!({"required":required,"optional":optional}),
        );
    }
    if rows.is_empty() {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Unknown command family. Choose the part before the first dot in a command listed by schema.lookup with name index.",
        ));
    }
    Ok(
        json!({"name":"command.fields","select":family,"detail":"command_fields","workspace":workspace,
        "commands":rows,"usage":"For types, defaults and nested choices, look up the command by name. Select field:NAME for one input."}),
    )
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

fn select_component<'a>(
    value: &'a Value,
    shape: &'a Value,
    prefix: Option<&str>,
    segment: &str,
) -> Option<(&'a Value, String)> {
    if let Some(field) = segment.strip_prefix("field:") {
        return Some((
            shape.get("properties")?.get(field)?,
            variant_path(prefix, segment),
        ));
    }
    if let Some((_, _, variant)) = variants(shape)
        .into_iter()
        .find(|(_, tag, _)| *tag == segment)
    {
        return Some((variant, variant_path(prefix, segment)));
    }
    // Definitions are also reachable directly from the named root.
    Some((value.get("$defs")?.get(segment)?, segment.to_owned()))
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
    if name == "command.fields" {
        if force_full {
            return Err(Error::new(
                "INVALID_REQUEST",
                "Look up a command by name for its full validation schema",
            ));
        }
        return command_fields(select, workspace);
    }
    if matches!(
        name,
        "index" | "vector.quickstart" | "image.quickstart" | "handoff.quickstart"
    ) {
        if select.is_some() || force_full {
            return Err(Error::new(
                "INVALID_REQUEST",
                format!("The schema {name} has no select or full option"),
            ));
        }
        if name == "vector.quickstart" {
            return Ok(examples::vector_quickstart());
        }
        if name == "image.quickstart" {
            return Ok(examples::image_quickstart());
        }
        if name == "handoff.quickstart" {
            return Ok(examples::handoff_quickstart());
        }
        return Ok(
            json!({"detail":"index", "commands":commands().collect::<Vec<_>>(),
            "types":TYPES.iter().map(|(alias, _)| alias).collect::<Vec<_>>(),
            "example_queries":examples::queries(), "vector_quickstart":lookup_request("vector.quickstart", None),
            "image_quickstart":lookup_request("image.quickstart", None),
            "handoff_quickstart":lookup_request("handoff.quickstart", None),
            "command_fields":lookup_request("command.fields", Some("session")),
            "usage":"Use command.fields with select job or session for required and optional input names. Look up a command or type by name for details. Use full:true for a validation schema."}),
        );
    }
    let root_type = TYPES
        .iter()
        .find_map(|&(alias, definition)| (alias == name).then_some(definition));
    let mut value = if let Some(definition) = root_type {
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
    if workspace {
        crate::workspace::describe(&mut value);
    }
    let mut prefix: Option<String> = None;
    if let Some(selector) = select {
        let mut components = selector.split('/').peekable();
        if let Some(root) = root_type
            && value["$defs"].get(root).is_none()
        {
            // The selected type is already at the root. Recursive definitions
            // keep their existing routes and advertised child selectors.
            components.next_if_eq(&root);
        }
        for segment in components {
            let shape = fields::shape(&value, &value["$defs"]);
            let (selected, route) = select_component(&value, shape, prefix.as_deref(), segment)
                .ok_or_else(|| {
                    let mut error = Error::new(
                        "SCHEMA_NOT_FOUND",
                        "Use field:NAME, a listed variant or a reachable definition in each select component. See details.schema_lookup for choices.",
                    );
                    let mut details = json!({"field":"select", "schema_lookup":lookup_request(name, prefix.as_deref())});
                    let suggestion = selector_suggestion(&value, prefix.as_deref(), segment)
                        .or_else(|| shape.get("properties")?.get(segment)
                            .map(|_| variant_path(prefix.as_deref(), &format!("field:{segment}"))));
                    if let Some(suggestion) = suggestion.filter(|s| s.len() <= crate::limits::schema::MAX_SELECTOR_BYTES) {
                        details["suggested_lookup"] = lookup_request(name, Some(&suggestion));
                    }
                    error.details = Some(Box::new(details));
                    error
                })?;
            prefix = Some(route);
            value = complete(selected.clone(), false);
            if workspace {
                crate::workspace::describe(&mut value);
            }
        }
    }
    let example = examples::for_schema(name, prefix.as_deref(), &value);
    let bytes = serde_json::to_vec(&value).unwrap().len();
    if force_full || bytes <= OUTLINE_BYTES {
        return examples::attach(
            json!({"name":name, "select":select, "detail":"full", "schema":value, "schema_bytes":bytes}),
            example,
        );
    }
    let shape = fields::shape(&value, &value["$defs"]);
    let mut outline = json!({"name":name, "select":select, "detail":"outline", "schema_bytes":bytes,
        "fields":fields::outline(shape, &value["$defs"], prefix.as_deref()), "variants":variants(shape).iter().map(|(field, tag, _)| json!({"field":field,"value":tag,"select":variant_path(prefix.as_deref(), tag)})).collect::<Vec<_>>(),
        "definitions":value.get("$defs").and_then(Value::as_object).map(|m| m.keys().collect::<Vec<_>>()).unwrap_or_default(),
        "usage":"Keep name and use a field or variant's select value, or a listed definition. Join components with / to follow nested fields and variants. Use full:true for the complete validation schema."});
    if variants(&value).is_empty()
        && let Some(choices) = fields::alternatives(&value)
    {
        outline["anyOf"] = choices;
    }
    examples::attach(outline, example)
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
