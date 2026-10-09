//! Explicit JSON response projection; persistent identity and retry inputs stay unchanged.
use crate::{Error, Request, control::Control};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::PathBuf;

pub const COMPACT_TARGET_BYTES: usize = 8 * 1024;
pub const COMMANDS: &[&str] = &[
    "session.create",
    "session.continue",
    "session.read",
    "session.apply",
    "session.apply_proposal",
    "session.receipt",
];

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Mode {
    #[default]
    Full,
    Compact,
}

pub(crate) fn take(value: &mut Value) -> Result<Mode, Error> {
    let Some(object) = value.as_object_mut() else {
        return Ok(Mode::Full);
    };
    let Some(mode) = object.remove("response_mode") else {
        return Ok(Mode::Full);
    };
    if !object
        .get("command")
        .and_then(Value::as_str)
        .is_some_and(|c| COMMANDS.contains(&c))
    {
        return Err(Error::new(
            "INVALID_REQUEST",
            "response_mode is supported by session.create, session.continue, session.read, session.apply, session.apply_proposal and session.receipt",
        ));
    }
    serde_json::from_value(mode)
        .map_err(|_| Error::new("INVALID_REQUEST", "response_mode must be full or compact"))
}

pub(crate) fn describe(command: &str, schema: &mut Value) {
    if COMMANDS.contains(&command) {
        schema["properties"]["response_mode"] = json!({"type":"string","enum":["full","compact"],"default":"full","description":"Compact returns pinned document/receipt references and summaries, omitting snapshot pixels, receipt changes and the snapshot list. Full preserves the original response. Presentation does not change durable retry identity."});
    }
}

fn target(request: &Request) -> Option<(PathBuf, String)> {
    match request {
        Request::SessionApplyProposal {
            session_root,
            proposal,
            ..
        } => Some((session_root.clone(), proposal.session_id.clone())),
        Request::SessionCreate {
            session_root,
            session_id,
            ..
        }
        | Request::SessionContinue {
            session_root,
            session_id,
            ..
        }
        | Request::SessionRead {
            session_root,
            session_id,
            ..
        }
        | Request::SessionApply {
            session_root,
            session_id,
            ..
        }
        | Request::SessionReceipt {
            session_root,
            session_id,
            ..
        } => Some((session_root.clone(), session_id.clone())),
        _ => None,
    }
}

fn compact(result: Value, root: PathBuf, session_id: String) -> Value {
    let document = &result["document"];
    let mut summary = json!({"response_mode":"compact",
        "document_ref":{"session_root":root,"session_id":session_id,"revision":document["revision"]},
        "document_summary":{"id":document["id"],"kind":document["kind"],"width":document["width"],"height":document["height"],
            "item_count":document["items"].as_array().map_or(0, Vec::len),
            "asset_count":document["assets"].as_object().map_or(0, serde_json::Map::len),
            "font_count":document["fonts"].as_object().map_or(0, serde_json::Map::len)},
        "omitted":["document"]});
    for key in [
        "session_id",
        "revision",
        "current_revision",
        "state_id",
        "current_state_id",
        "state_sha256",
        "resources",
        "undo_depth",
        "redo_depth",
        "replayed",
        "lineage",
    ] {
        if let Some(value) = result.get(key) {
            summary[key] = value.clone();
        }
    }
    if let Some(receipt) = result.get("receipt") {
        let mut reduced = receipt.clone();
        reduced.as_object_mut().unwrap().remove("changes");
        reduced["change_count"] = json!(receipt["changes"].as_array().map_or(0, Vec::len));
        summary["receipt_summary"] = reduced;
        summary["receipt_ref"] =
            json!({"session_root":root,"session_id":session_id,"request_id":receipt["request_id"]});
        summary["omitted"]
            .as_array_mut()
            .unwrap()
            .push(json!("receipt.changes"));
    }
    if let Some(snapshots) = result.get("snapshots").and_then(Value::as_array) {
        summary["snapshot_count"] = json!(snapshots.len());
        summary["omitted"]
            .as_array_mut()
            .unwrap()
            .push(json!("snapshots"));
    }
    summary
}

pub(crate) fn execute(request: Request, context: &Control, mode: Mode) -> Result<Value, Error> {
    let target = if mode == Mode::Compact {
        Some(target(&request).ok_or_else(|| {
            Error::new(
                "INVALID_REQUEST",
                "Compact mode requires a durable session result",
            )
        })?)
    } else {
        None
    };
    let result = crate::execute_controlled(request, context)?;
    // Projection cannot turn a committed success into a size-limit failure.
    Ok(match target {
        Some((root, session_id)) => compact(result, root, session_id),
        None => result,
    })
}
