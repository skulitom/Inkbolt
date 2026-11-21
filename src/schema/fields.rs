use serde_json::{Value, json};

/// Look through a reference or a nullable single shape for navigation only.
/// The full lookup response always retains the selected field's constraints.
pub(super) fn shape<'a>(schema: &'a Value, definitions: &'a Value) -> &'a Value {
    let target = match schema
        .get("anyOf")
        .and_then(Value::as_array)
        .map(Vec::as_slice)
    {
        Some([left, right]) if left["type"] == "null" => right,
        Some([left, right]) if right["type"] == "null" => left,
        _ => schema,
    };
    target
        .get("$ref")
        .and_then(Value::as_str)
        .and_then(|reference| reference.strip_prefix("#/$defs/"))
        .and_then(|name| definitions.get(name))
        .unwrap_or(target)
}

fn signature(schema: &Value) -> Value {
    let mut result = json!({});
    for key in ["$ref", "type", "const", "enum", "minimum", "pattern"] {
        if let Some(value) = schema.get(key) {
            result[key] = value.clone();
        }
    }
    result
}

/// Keep alternatives shallow. In particular, a reference to the inline
/// document must never copy the document tree into an ordinary outline.
pub(super) fn alternatives(schema: &Value) -> Option<Value> {
    let choices = schema.get("anyOf")?.as_array()?;
    Some(Value::Array(
        choices
            .iter()
            .map(|choice| {
                let mut summary = signature(choice);
                if let Some(required) = choice.get("required") {
                    summary["required"] = required.clone();
                }
                if let Some(properties) = choice.get("properties").and_then(Value::as_object) {
                    summary["properties"] = Value::Object(
                        properties
                            .iter()
                            .map(|(name, field)| (name.clone(), signature(field)))
                            .collect(),
                    );
                }
                summary
            })
            .collect(),
    ))
}

/// Expose one level of object inputs. Inline scalar enums are particularly
/// useful for delivery formats, without loading the remaining option trees.
fn object_inputs(schema: &Value, definitions: &Value) -> Option<Value> {
    let properties = schema.get("properties")?.as_object()?;
    let mut inputs = json!({});
    if let Some(required) = schema.get("required") {
        inputs["required"] = required.clone();
    }
    let mut fields = serde_json::Map::new();
    for (name, property) in properties {
        let mut field = signature(property);
        if let Some(choices) = property.get("anyOf").and_then(Value::as_array) {
            field["anyOf"] = Value::Array(choices.iter().map(signature).collect());
        }
        if property.get("$ref").is_some()
            && let Some(values) = shape(property, definitions).get("enum")
        {
            field["enum"] = values.clone();
        }
        fields.insert(name.clone(), field);
    }
    inputs["properties"] = Value::Object(fields);
    Some(inputs)
}

pub(super) fn outline(object: &Value, definitions: &Value, prefix: Option<&str>) -> Vec<Value> {
    object.get("properties").and_then(Value::as_object).into_iter().flatten()
        .map(|(field, property)| {
            let mut summary = json!({"name":field,
                "required":object["required"].as_array().is_some_and(|a| a.iter().any(|v| v == field))});
            let route = super::variant_path(prefix, &format!("field:{field}"));
            if route.len() <= crate::limits::schema::MAX_SELECTOR_BYTES {
                summary["select"] = json!(route);
            }
            for key in ["type", "$ref", "description", "const", "default"] {
                if let Some(value) = property.get(key) {
                    summary[key] = value.clone();
                }
            }
            if let Some(choices) = alternatives(property) {
                summary["anyOf"] = choices;
            }
            let nested = shape(property, definitions);
            if let Some(inputs) = object_inputs(nested, definitions) {
                summary["object_inputs"] = inputs;
            }
            summary
        }).collect()
}
