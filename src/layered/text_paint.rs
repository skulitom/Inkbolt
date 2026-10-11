//! Typed source components only, without color conversion or paint acceptance.
use super::{text_data::Node, text_style::Kind, *};
use std::collections::BTreeSet;

pub(super) const FIELDS: &[(&str, &str, &str)] = &[
    ("53", "FillColor", "fill_color"),
    ("54", "StrokeColor", "stroke_color"),
];

fn extra<'a>(
    keys: impl Iterator<Item = &'a String>,
    allowed: &[&str],
    prefix: &str,
    unknown: &mut BTreeSet<String>,
) {
    unknown.extend(
        keys.filter(|k| !allowed.contains(&k.as_str()))
            .map(|k| format!("{prefix}/{k}")),
    );
}

pub(super) fn local(
    value: &Value,
    key: &str,
    unknown: &mut BTreeSet<String>,
) -> Result<Option<Value>, Error> {
    let fields = value.as_object().ok_or_else(malformed)?;
    let mode = Kind::Integer.read(fields.get("Type").ok_or_else(malformed)?)?;
    if mode != json!(1) {
        unknown.insert(key.to_owned());
        return Ok(None);
    }
    let values = fields
        .get("Values")
        .and_then(Value::as_array)
        .ok_or_else(malformed)?;
    if values.len() != 4 {
        return Err(malformed());
    }
    let components = values
        .iter()
        .map(|v| Kind::Number.read(v))
        .collect::<Result<Vec<_>, _>>()?;
    extra(fields.keys(), &["Type", "Values"], key, unknown);
    Ok(Some(json!({"type":1,"components":components})))
}

pub(super) fn global(
    node: &Node,
    key: &str,
    unknown: &mut BTreeSet<String>,
) -> Result<Option<Value>, Error> {
    let Node::Dictionary(fields) = node else {
        return Err(malformed());
    };
    let Node::Name(class) = node.field("99")? else {
        return Err(malformed());
    };
    if class != "SimplePaint" {
        unknown.insert(key.to_owned());
        return Ok(None);
    }
    let color = node.field("0")?;
    let mode = Kind::Integer.read_node(color.field("0")?)?;
    if mode != json!(1) {
        unknown.insert(key.to_owned());
        return Ok(None);
    }
    let values = color.field("1")?.array()?;
    if values.len() != 4 {
        return Err(malformed());
    }
    let components = values
        .iter()
        .map(|v| Ok(json!(v.number()?)))
        .collect::<Result<Vec<_>, Error>>()?;
    extra(fields.keys(), &["99", "0"], key, unknown);
    let Node::Dictionary(fields) = color else {
        return Err(malformed());
    };
    extra(fields.keys(), &["0", "1"], &format!("{key}/0"), unknown);
    Ok(Some(json!({"type":1,"components":components})))
}
