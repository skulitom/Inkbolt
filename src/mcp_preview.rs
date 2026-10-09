//! Opt-in MCP presentation: image bytes have one location, with explicit references.
use base64::{Engine, engine::general_purpose::STANDARD};
use serde_json::{Value, json};
use std::collections::BTreeMap;

pub const MAX_IMAGES: usize = 4;
pub const MAX_IMAGE_BASE64_BYTES: usize = 8 * 1024 * 1024;

fn array_paths(result: &Value, key: &str, suffix: &str, paths: &mut Vec<String>) {
    if let Some(entries) = result[key].as_array() {
        paths.extend((0..entries.len()).map(|i| format!("/result/{key}/{i}{suffix}")));
    }
}
fn artifact_paths(command: &str, result: &Value) -> Vec<String> {
    let mut paths = vec![];
    match command {
        "document.export" | "channel.export" => paths.push("/result".into()),
        "artboard.export" => array_paths(result, "artifacts", "/artifact", &mut paths),
        "sequence.export" => array_paths(result, "frames", "/artifact", &mut paths),
        "document.separations" | "document.prepress" => {
            paths.push("/result/preview".into());
            array_paths(result, "plates", "", &mut paths);
        }
        "document.proof" => {
            paths.extend(
                [
                    "preview",
                    "difference/mask",
                    "gamut/mask",
                    "gamut/unclassified_mask",
                ]
                .iter()
                .map(|p| format!("/result/{p}")),
            );
            // These are engine-owned process identifiers, not arbitrary user keys.
            for name in ["cyan", "magenta", "yellow", "black"] {
                paths.push(format!("/result/plates/{name}"));
            }
            array_paths(result, "named_plates", "", &mut paths);
        }
        _ => {}
    }
    paths
}

pub(crate) fn present(mut envelope: Value, command: &str) -> Value {
    let mut content = vec![Value::Null];
    let mut seen: BTreeMap<String, Value> = BTreeMap::new();
    let mut image_bytes = 0;
    let mut inline_images = 0;
    let mut image_records = 0;
    // Inspect known output locations only. Documents, metadata and retained source
    // snapshots are never interpreted as transport artifacts.
    for pointer in artifact_paths(command, &envelope["result"]) {
        let Some(artifact) = envelope.pointer_mut(&pointer) else {
            continue;
        };
        if artifact["media_type"] != "image/png" || artifact["encoding"] != "base64" {
            continue;
        }
        let Some(data) = artifact["data"].as_str() else {
            continue;
        };
        image_records += 1;
        let key = crate::assets::sha256(data.as_bytes());
        let reference = if let Some(reference) = seen.get(&key) {
            Some(reference.clone())
        } else if content.len() <= MAX_IMAGES && image_bytes + data.len() <= MAX_IMAGE_BASE64_BYTES
        {
            if let Ok(bytes) = STANDARD.decode(data) {
                let reference = json!({"version":1,"kind":"content","index":content.len(),"encoding":"base64","bytes":bytes.len(),"sha256":crate::assets::sha256(&bytes)});
                image_bytes += data.len();
                content.push(json!({"type":"image","mimeType":"image/png","data":data}));
                seen.insert(key.clone(), reference.clone());
                Some(reference)
            } else {
                None
            }
        } else {
            None
        };
        if let Some(reference) = reference {
            artifact.as_object_mut().unwrap().remove("data");
            artifact["encoding"] = json!("mcp_reference");
            artifact["payload_ref"] = reference;
        } else {
            // Over-budget bytes stay recoverable once in structuredContent. Later
            // identical records reference this location instead of copying bytes.
            seen.insert(key,json!({"version":1,"kind":"structured_content","pointer":format!("{pointer}/data"),"encoding":"base64"}));
            inline_images += 1;
        }
    }
    let failed = envelope["ok"] != true;
    let message = if failed {
        format!(
            "Inkbolt could not complete the request: {}. {}",
            envelope["error"]["code"].as_str().unwrap_or("ERROR"),
            envelope["error"]["message"]
                .as_str()
                .unwrap_or("See structuredContent.")
        )
    } else {
        format!(
            "Inkbolt completed the request. Result metadata is in structuredContent. {} PNG attachments represent {image_records} image records; {inline_images} additional unique image payloads remain inline in structuredContent.",
            content.len() - 1
        )
    };
    content[0] = json!({"type":"text","text":message});
    json!({"content":content,"structuredContent":envelope,"isError":failed})
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn byte_limit_keeps_unattached_payload_once_and_accepts_later_small_image() {
        // Transport fixture only: byte admission does not reinterpret PNG pixels.
        let large = STANDARD.encode(vec![17; MAX_IMAGE_BASE64_BYTES / 4 * 3 + 1]);
        let small = STANDARD.encode([0, 1, 2, 3]);
        let artifact =
            |data: &str| json!({"media_type":"image/png","encoding":"base64","data":data});
        let envelope = json!({"ok":true,"result":{"artifacts":[{"artifact":artifact(&large)},{"artifact":artifact(&large)},{"artifact":artifact(&small)}]}});
        let result = present(envelope, "artboard.export");
        let records = &result["structuredContent"]["result"]["artifacts"];
        assert_eq!(records[0]["artifact"]["data"], large);
        assert!(records[1]["artifact"].get("data").is_none());
        assert_eq!(
            records[1]["artifact"]["payload_ref"]["pointer"],
            "/result/artifacts/0/artifact/data"
        );
        assert_eq!(records[2]["artifact"]["payload_ref"]["index"], 1);
        assert_eq!(result["content"].as_array().unwrap().len(), 2);
        assert_eq!(result["content"][1]["data"], small);
        assert_eq!(result.to_string().matches(&large).count(), 1);
    }
}
