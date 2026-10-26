//! Atomic materialization with the shared solver's selected precision and certificates.
use crate::{Error, booleans, model::*, scene};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Sources {
    #[default]
    Keep,
    Hide,
    Remove,
}

pub(super) fn apply(
    document: &mut Document,
    ids: &[String],
    new_id: &str,
    mode: booleans::Mode,
    fill: &Paint,
    options: booleans::Options,
    sources: Sources,
) -> Result<Value, Error> {
    if !(2..=booleans::MAX_INPUTS).contains(&ids.len()) {
        return Err(Error::new(
            "INVALID_REQUEST",
            format!(
                "Boolean requires 2..={} distinct vector or work-path IDs",
                booleans::MAX_INPUTS
            ),
        ));
    }
    if !valid_id(new_id) || document.items.iter().any(|item| item.id == new_id) {
        return Err(invalid("Boolean result requires a valid unused item ID"));
    }
    crate::paint::validate(fill)?;
    if sources != Sources::Keep {
        for id in ids {
            super::unlocked(document, scene::index(document, id)?)?;
        }
    }
    let mut receipt = booleans::compute_with_options(document, ids, mode, options)?;
    let geometry: Option<Geometry> = serde_json::from_value(receipt["geometry"].take())
        .map_err(|_| invalid("Boolean solver returned invalid result geometry"))?;
    receipt.as_object_mut().unwrap().remove("geometry");
    let created = geometry.is_some();
    if let Some(geometry) = geometry {
        super::add(
            document,
            Item {
                id: new_id.to_owned(),
                name: String::new(),
                visible: true,
                locked: false,
                opacity: 1.0,
                fill_opacity: 1.0,
                coverage: Default::default(),
                effects: vec![],
                blend: Default::default(),
                transform: identity(),
                parent: None,
                clip_to: None,
                clip: None,
                mask: None,
                artwork_mask: None,
                filters: vec![],
                hdr_grade: None,
                pixel_warp: None,
                metadata: None,
                content: Content::Vector {
                    geometry,
                    fill: Some(fill.clone()),
                    stroke: None,
                    fill_rule: FillRule::Nonzero,
                },
            },
            None,
        )?;
    }
    match sources {
        Sources::Keep => {}
        Sources::Hide => {
            for id in ids {
                let index = scene::index(document, id)?;
                document.items[index].visible = false;
            }
        }
        Sources::Remove => {
            // Admitted operands are vector/work-path leaves, never containers.
            // The caller's full candidate validation rejects dangling references.
            if document
                .background
                .as_ref()
                .is_some_and(|b| ids.contains(&b.item_id))
            {
                document.background = None;
            }
            document.items.retain(|item| !ids.contains(&item.id));
        }
    }
    receipt["result_id"] = if created { json!(new_id) } else { Value::Null };
    receipt["created"] = json!(created);
    receipt["sources"] = json!(sources);
    receipt["losses"][0] = json!(
        "This is a geometry-only result. Paint, strokes, masks, clips, filters, visibility and opacity do not define operands. Result paint and source handling are explicit."
    );
    Ok(receipt)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn default_precision_preserves_the_historical_operation_identity() {
        let historical = json!({"op":"boolean","ids":["a","b"],"new_id":"result",
            "mode":"difference","fill":[30,90,180,255],"curve_tolerance":0.125,"sources":"keep"});
        let operation: crate::edit::Operation = serde_json::from_value(historical.clone()).unwrap();
        assert_eq!(serde_json::to_value(operation).unwrap(), historical);
        let mut explicit = historical.clone();
        explicit["precision"] = json!("auto");
        let operation: crate::edit::Operation = serde_json::from_value(explicit.clone()).unwrap();
        assert_eq!(serde_json::to_value(operation).unwrap(), historical);
        explicit["precision"] = json!("exact");
        let operation: crate::edit::Operation = serde_json::from_value(explicit.clone()).unwrap();
        assert_eq!(serde_json::to_value(operation).unwrap(), explicit);
    }
}
