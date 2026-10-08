//! Original typed datasets with captured property baselines and explicit selection.
use crate::{Error, model::*, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashSet};

pub const MAX_BINDINGS: usize = 64;
pub const MAX_DATASETS: usize = 32;
pub const MAX_INHERITANCE: usize = 8;
pub const EXPORT_LOSS: &str = "Only the selected variant is exported. Retain snapshots for dataset bindings, inherited values and captured base properties.";

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq, Hash)]
#[serde(rename_all = "snake_case")]
pub enum Property {
    Name,
    Visible,
    Opacity,
    FillOpacity,
    Position,
    Transform,
    Text,
    Image,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct TextValue {
    pub text: String,
    #[serde(default)]
    pub ranges: Vec<crate::text::StyleRange>,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(
    tag = "type",
    content = "value",
    rename_all = "snake_case",
    deny_unknown_fields
)]
pub enum Value {
    Name(String),
    Visible(bool),
    Opacity(f64),
    FillOpacity(f64),
    Position(Point),
    Transform(Matrix),
    Text(TextValue),
    Image(String),
}
impl Value {
    fn property(&self) -> Property {
        match self {
            Self::Name(_) => Property::Name,
            Self::Visible(_) => Property::Visible,
            Self::Opacity(_) => Property::Opacity,
            Self::FillOpacity(_) => Property::FillOpacity,
            Self::Position(_) => Property::Position,
            Self::Transform(_) => Property::Transform,
            Self::Text(_) => Property::Text,
            Self::Image(_) => Property::Image,
        }
    }
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Binding {
    pub key: String,
    pub item_id: String,
    pub property: Property,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Dataset {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub parent: Option<String>,
    #[serde(default)]
    pub values: BTreeMap<String, Value>,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Definition {
    pub bindings: Vec<Binding>,
    pub datasets: BTreeMap<String, Dataset>,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct State {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sequence: Option<crate::sequences::Timeline>,
    pub definition: Definition,
    pub base: Vec<Value>,
    pub selected: Option<String>,
}
fn error(message: &str) -> Error {
    Error::new("INVALID_VARIANT", message)
}
fn get(item: &Item, property: Property) -> Result<Value, Error> {
    Ok(match property {
        Property::Name => Value::Name(item.name.clone()),
        Property::Visible => Value::Visible(item.visible),
        Property::Opacity => Value::Opacity(item.opacity),
        Property::FillOpacity => Value::FillOpacity(item.fill_opacity),
        Property::Position => Value::Position([item.transform[4], item.transform[5]]),
        Property::Transform => Value::Transform(item.transform),
        Property::Text => {
            let Content::Text { frame } = &item.content else {
                return Err(error("Text bindings require text content").at_item(&item.id));
            };
            Value::Text(TextValue {
                text: frame.text.clone(),
                ranges: frame.ranges.clone(),
            })
        }
        Property::Image => {
            let Content::Image { asset_id, .. } = &item.content else {
                return Err(error("Image bindings require placed image content").at_item(&item.id));
            };
            Value::Image(asset_id.clone())
        }
    })
}
fn put(item: &mut Item, value: &Value) -> Result<(), Error> {
    match value {
        Value::Name(v) => item.name = v.clone(),
        Value::Visible(v) => item.visible = *v,
        Value::Opacity(v) => item.opacity = *v,
        Value::FillOpacity(v) => item.fill_opacity = *v,
        Value::Position(v) => {
            item.transform[4] = v[0];
            item.transform[5] = v[1];
        }
        Value::Transform(v) => item.transform = *v,
        Value::Text(v) => {
            let Content::Text { frame } = &mut item.content else {
                return Err(error("Text binding target changed content type").at_item(&item.id));
            };
            frame.text = v.text.clone();
            frame.ranges = v.ranges.clone();
        }
        Value::Image(v) => {
            let Content::Image { asset_id, .. } = &mut item.content else {
                return Err(error("Image binding target changed content type").at_item(&item.id));
            };
            *asset_id = v.clone();
        }
    }
    Ok(())
}
fn resolved<'a>(
    definition: &'a Definition,
    selected: Option<&str>,
) -> Result<BTreeMap<&'a str, &'a Value>, Error> {
    let mut chain = vec![];
    let mut current = selected;
    while let Some(id) = current {
        if chain.contains(&id) {
            return Err(error("Dataset inheritance contains a cycle"));
        }
        if chain.len() == MAX_INHERITANCE {
            return Err(limit("Dataset inheritance exceeds 8 levels"));
        }
        let (id, data) = definition
            .datasets
            .get_key_value(id)
            .ok_or_else(|| error("Selected or parent dataset does not exist"))?;
        chain.push(id.as_str());
        current = data.parent.as_deref();
    }
    let mut values = BTreeMap::new();
    for id in chain.into_iter().rev() {
        for (key, value) in &definition.datasets[id].values {
            values.insert(key.as_str(), value);
        }
    }
    Ok(values)
}
fn values(state: &State, selected: Option<&str>) -> Result<Vec<Value>, Error> {
    let overrides = resolved(&state.definition, selected)?;
    Ok(state
        .definition
        .bindings
        .iter()
        .zip(&state.base)
        .map(|(b, base)| {
            overrides
                .get(b.key.as_str())
                .copied()
                .unwrap_or(base)
                .clone()
        })
        .collect())
}
fn apply_values(
    d: &mut Document,
    state: &State,
    values: &[Value],
    locks: bool,
) -> Result<Vec<String>, Error> {
    let mut changed = vec![];
    // All lock checks use the same pre-change scene, even when another binding
    // changes a shared definition or its dependent artwork in this selection.
    for (b, value) in state.definition.bindings.iter().zip(values) {
        let i = scene::index(d, &b.item_id)?;
        if get(&d.items[i], b.property)? != *value {
            if locks {
                scene::check_unlocked(d, i, true)?;
            }
            if !changed.contains(&b.item_id) {
                changed.push(b.item_id.clone());
            }
        }
    }
    for (b, value) in state.definition.bindings.iter().zip(values) {
        let i = scene::index(d, &b.item_id)?;
        put(&mut d.items[i], value)?;
    }
    Ok(changed)
}
pub(crate) fn validate(d: &Document) -> Result<(), Error> {
    let Some(state) = &d.variants else {
        return Ok(());
    };
    crate::sequences::validate(state)?;
    let def = &state.definition;
    if def.bindings.is_empty()
        || def.bindings.len() > MAX_BINDINGS
        || def.datasets.is_empty()
        || def.datasets.len() > MAX_DATASETS
    {
        return Err(limit("Variants require 1..64 bindings and 1..32 datasets"));
    }
    if state.base.len() != def.bindings.len() {
        return Err(error("Variant baseline must match every binding"));
    }
    let mut keys = BTreeMap::new();
    let mut targets = HashSet::new();
    for (b, base) in def.bindings.iter().zip(&state.base) {
        if !valid_id(&b.key) || !valid_id(&b.item_id) || base.property() != b.property {
            return Err(error("Binding key, item or baseline type is invalid"));
        }
        if keys
            .insert(&b.key, b.property)
            .is_some_and(|p| p != b.property)
        {
            return Err(error(
                "One dataset key cannot have different property types",
            ));
        }
        if !targets.insert((&b.item_id, b.property)) {
            return Err(error("Duplicate property target in variant bindings"));
        }
        let i = scene::index(d, &b.item_id)?;
        get(&d.items[i], b.property)?;
    }
    if def.bindings.iter().any(|b| {
        b.property == Property::Position && targets.contains(&(&b.item_id, Property::Transform))
    }) {
        return Err(error("Position and transform cannot bind the same item"));
    }
    for (id, dataset) in &def.datasets {
        if !valid_id(id) || dataset.parent.as_ref().is_some_and(|p| !valid_id(p)) {
            return Err(error("Dataset names and parents must use ID syntax"));
        }
        for (key, value) in &dataset.values {
            if keys.get(key).is_none_or(|p| *p != value.property()) {
                return Err(error(
                    "Dataset value has an unknown key or the wrong property type",
                ));
            }
        }
        resolved(def, Some(id))?;
    }
    let selected = values(state, state.selected.as_deref())?;
    for (b, value) in def.bindings.iter().zip(&selected) {
        let i = scene::index(d, &b.item_id)?;
        if get(&d.items[i], b.property)? != *value {
            return Err(Error::new("VARIANT_CONTROLLED","Controlled property differs from the selected dataset; revise variants or clear/bake them before ordinary edits").at_item(&b.item_id));
        }
    }
    // Validate the base and every inherited row, including inactive datasets.
    // Removing variant metadata prevents recursive validation of the same table.
    for selected in std::iter::once(None).chain(def.datasets.keys().map(|id| Some(id.as_str()))) {
        let mut candidate = d.clone();
        candidate.variants = None;
        apply_values(&mut candidate, state, &values(state, selected)?, false)?;
        crate::model::validate(&candidate).map_err(|mut e| {
            e.message = format!("Variant {}: {}", selected.unwrap_or("<base>"), e.message);
            e
        })?;
    }
    Ok(())
}
pub(crate) fn define(d: &mut Document, definition: Definition) -> Result<serde_json::Value, Error> {
    if definition.bindings.is_empty()
        || definition.bindings.len() > MAX_BINDINGS
        || definition.datasets.is_empty()
        || definition.datasets.len() > MAX_DATASETS
    {
        return Err(limit("Variants require 1..64 bindings and 1..32 datasets"));
    }
    let mut restored = vec![];
    if let Some(old) = d.variants.clone() {
        restored = apply_values(d, &old, &old.base, true)?;
    }
    let base = definition
        .bindings
        .iter()
        .map(|b| get(&d.items[scene::index(d, &b.item_id)?], b.property))
        .collect::<Result<_, _>>()?;
    let sequence = d.variants.as_ref().and_then(|s| s.sequence.clone());
    d.variants = Some(State {
        sequence,
        definition,
        base,
        selected: None,
    });
    Ok(serde_json::json!({"selected":null,"baseline_captured":true,"restored_items":restored}))
}
pub(crate) fn view(d: &Document, selected: &str) -> Result<Document, Error> {
    let state = d
        .variants
        .as_ref()
        .ok_or_else(|| error("Document has no variant definition"))?;
    let mut view = d.clone();
    apply_values(&mut view, state, &values(state, Some(selected))?, false)?;
    view.variants.as_mut().unwrap().selected = Some(selected.into());
    Ok(view)
}
pub(crate) fn select(
    d: &mut Document,
    selected: Option<String>,
) -> Result<serde_json::Value, Error> {
    let mut state = d
        .variants
        .clone()
        .ok_or_else(|| error("Document has no variant definition"))?;
    let values = values(&state, selected.as_deref())?;
    let changed = apply_values(d, &state, &values, true)?;
    state.selected = selected;
    let receipt = serde_json::json!({"selected":state.selected,"changed_items":changed,"bindings":state.definition.bindings,"resolved_values":values});
    d.variants = Some(state);
    Ok(receipt)
}
pub(crate) fn clear(d: &mut Document, bake: bool) -> Result<serde_json::Value, Error> {
    let state = d
        .variants
        .clone()
        .ok_or_else(|| error("Document has no variant definition"))?;
    if state.sequence.is_some() {
        return Err(error(
            "Clear sequence timing before clearing variant artwork",
        ));
    }
    let changed = if bake {
        vec![]
    } else {
        apply_values(d, &state, &state.base, true)?
    };
    d.variants = None;
    Ok(serde_json::json!({"baked":bake,"changed_items":changed}))
}
/// Every stored dataset keeps its pinned resources alive, even while inactive.
pub(crate) fn resource_users(d: &Document, id: &str, font: bool) -> Vec<usize> {
    let Some(state) = &d.variants else {
        return vec![];
    };
    let uses = |v: &Value| match v {
        Value::Image(asset) if !font => asset == id,
        Value::Text(text) if font => text
            .ranges
            .iter()
            .any(|r| r.style.font_ids().any(|f| f == id)),
        _ => false,
    };
    let mut users = vec![];
    for (b, base) in state.definition.bindings.iter().zip(&state.base) {
        if (uses(base)
            || state
                .definition
                .datasets
                .values()
                .any(|data| data.values.get(&b.key).is_some_and(uses)))
            && let Ok(i) = scene::index(d, &b.item_id)
            && !users.contains(&i)
        {
            users.push(i);
        }
    }
    users
}

pub(crate) fn annotate_export(
    state: Option<&State>,
    artifact: &mut serde_json::Value,
    snapshot: bool,
) {
    if let Some(state) = state {
        artifact["variant"] = serde_json::json!(state.selected);
        artifact["variant_state_sha256"] =
            serde_json::json!(crate::assets::sha256(&serde_json::to_vec(state).unwrap()));
        if !snapshot && artifact["sequence"]["all_frames"] != true {
            if artifact.get("losses").is_none() {
                artifact["losses"] = serde_json::json!([]);
            }
            let losses = artifact["losses"].as_array_mut().unwrap();
            if !losses.iter().any(|v| v.as_str() == Some(EXPORT_LOSS)) {
                losses.push(serde_json::json!(EXPORT_LOSS));
            }
            if state.sequence.is_some() {
                losses.push(serde_json::json!("This still omits sequence frame order, durations and play count; retain the original snapshot or sequence receipt."));
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn nonfinite_inactive_values_and_baselines_are_rejected() {
        let d: Document = serde_json::from_value(serde_json::json!({"schema_version":2,"id":"finite-variants","kind":"raster","width":8,"height":8,"color_space":"srgb","items":[{"id":"tile","content":{"type":"raster","width":1,"height":1,"rgba_hex":"112233ff"}}]})).unwrap();
        for number in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            for bad in [
                Value::Opacity(number),
                Value::FillOpacity(number),
                Value::Position([number, 0.0]),
                Value::Transform([1.0, 0.0, 0.0, 1.0, number, 0.0]),
            ] {
                let mut candidate = d.clone();
                let definition = Definition {
                    bindings: vec![Binding {
                        key: "v".into(),
                        item_id: "tile".into(),
                        property: bad.property(),
                    }],
                    datasets: BTreeMap::from([(
                        "inactive".into(),
                        Dataset {
                            parent: None,
                            values: BTreeMap::from([("v".into(), bad.clone())]),
                        },
                    )]),
                };
                define(&mut candidate, definition).unwrap();
                assert!(crate::validate(&candidate).is_err());
                let state = candidate.variants.as_mut().unwrap();
                state
                    .definition
                    .datasets
                    .get_mut("inactive")
                    .unwrap()
                    .values
                    .clear();
                state.base[0] = bad;
                assert!(crate::validate(&candidate).is_err());
            }
        }
    }
}
