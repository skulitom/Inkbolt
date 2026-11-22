//! Small executable examples with explicit external prerequisites. No discovery I/O.
use crate::Error;
use serde_json::{Value, json};

pub(super) fn queries() -> Value {
    json!([
        {"command":"schema.lookup","name":"font.import"},
        {"command":"schema.lookup","name":"session.create"},
        {"command":"schema.lookup","name":"session.dry_run"},
        {"command":"schema.lookup","name":"document"},
        {"command":"schema.lookup","name":"content","select":"text"},
        {"command":"schema.lookup","name":"operation","select":"text"},
        {"command":"schema.lookup","name":"operation","select":"transform"},
        {"command":"schema.lookup","name":"operation","select":"boolean"}
    ])
}

fn document() -> Value {
    json!({"schema_version":2,"id":"example","kind":"vector",
        "width":64,"height":64,"color_space":"srgb","items":[]})
}

fn frame() -> Value {
    json!({"text":"A","width":32,"height":24,"wrap":false,
        "style":{"font_id":"face","size":12,"fill":[20,80,150,255]}})
}

fn text_edit() -> Value {
    json!({"op":"text","id":"label","frame":frame()})
}

fn import_font() -> Value {
    json!({"command":"font.import","source_path":"typeface.ttf","license_path":"typeface-license.txt"})
}

fn save_session(document: Value) -> Value {
    json!({"command":"session.create","session_id":"example","request_id":"create",
        "document":document,"response_mode":"compact"})
}

pub(super) fn vector_quickstart() -> Value {
    let postcard: Value = serde_json::from_str(include_str!("../../examples/first-png.json"))
        .expect("bundled postcard is valid JSON");
    json!({"name":"vector.quickstart","detail":"examples",
    "publish_png":postcard,
    "import_font":import_font(),
    "text_item":{"id":"caption","transform":[1,0,0,1,12,8],"content":{"type":"text","frame":frame()}},
    "save_session":save_session(document()),
    "publish_snapshot":publish_snapshot(),
    "usage":[
        "Run requests with one selected workspace. Adapt publish_png.document and its items to your canvas and artwork. Geometry uses canvas units and fills use RGBA bytes.",
        "For text, run import_font with your own font and license paths. Set document.fonts.face to the returned result descriptor and append text_item to document.items. Its translation places the frame's top left.",
        "To keep the edit, put that document in save_session.document and use a fresh session ID. Use the saved session ID and revision as the document in publish_snapshot and publish_png. Choose unused output filenames."
    ]})
}

fn publish_snapshot() -> Value {
    serde_json::from_str(include_str!("../../examples/publish-snapshot.json"))
        .expect("bundled snapshot request is valid JSON")
}

pub(super) fn image_quickstart() -> Value {
    let snapshot = publish_snapshot();
    let artwork = json!({
        "schema_version":2,"id":"artwork","kind":"raster","color_space":"srgb",
        "width":320,"height":240,"assets":{},
        "items":[{"id":"picture","content":{"type":"image","asset_id":"photo","width":320,"height":240}}]
    });
    json!({
        "name":"image.quickstart","detail":"examples",
        "import_image":{"command":"asset.import","source_path":"photo.png"},
        "save_session":save_session(artwork),
        "publish_png":{"command":"document.publish","document":snapshot["document"],
            "output":{"format":"png","file_name":"artwork.png"}},
        "publish_snapshot":snapshot,
        "usage":[
            "Use one selected workspace. Run import_image with your source path. Copy result.asset into save_session.document.assets.photo. Its sha256 pins the imported pixels and provenance.source_sha256 identifies the original file bytes.",
            "For native size, set the image content width and height from the asset descriptor. To fit the canvas to the image, set the document width and height to those dimensions too. The image item starts at the origin and stays editable. Set locked:true only when you want to prevent layer edits.",
            "Add other artwork to document.items and choose the document kind and resource profile for your canvas. Run save_session with a fresh session ID. Use that ID and the desired saved revision in publish_snapshot and publish_png with unused filenames."
        ]
    })
}

fn example(kind: &str, value: Value, requires: &[&str], usage: &str) -> Value {
    json!({"kind":kind,"value":value,"requires":requires,"usage":usage})
}

pub(super) fn for_schema(name: &str, selected: Option<&str>, schema: &Value) -> Option<Value> {
    let text_usage = "Bind document.fonts.face to the descriptor returned as the font.import result. Supply that font store through --workspace or font_root. A text operation replaces the complete frame: copy the existing frame and change only intended fields when repairing it.";
    match schema["properties"]["op"]["const"].as_str() {
        Some("text") => {
            return Some(example(
                "operation",
                text_edit(),
                &[
                    "An editable text item named label",
                    "A document font named face",
                ],
                text_usage,
            ));
        }
        Some("boolean") => {
            return Some(example(
                "operation",
                json!({"op":"boolean","ids":["outer","opening"],"new_id":"frame",
                    "mode":"difference","fill":[35,100,180,255],"sources":"hide"}),
                &[
                    "Two unlocked vector items named outer and opening",
                    "Unused item ID frame",
                ],
                "Combine filled geometry and add the explicitly painted result at the document root in one edit. Hide the sources atomically. Empty results create no item. Existing curve/topology limits still apply; this does not flatten source appearance.",
            ));
        }
        Some("transform") => {
            return Some(example(
                "operation",
                json!({"op":"transform","id":"label","matrix":[1,0,0,1,4,4],"space":"world"}),
                &["An editable item named label"],
                "Translate the existing item four document units right and down. Other geometry and items are retained.",
            ));
        }
        _ => {}
    }
    if schema["properties"]["type"]["const"] == "text" {
        return Some(example(
            "content",
            json!({"type":"text","frame":frame()}),
            &["A document font named face"],
            text_usage,
        ));
    }
    if (name == "document" && selected.is_none()) || selected == Some("Document") {
        return Some(example(
            "document",
            document(),
            &[],
            "An empty editable document; use as a document argument. Add imported font descriptors to fonts by ID before adding text.",
        ));
    }
    if selected.is_some() {
        return None;
    }
    let workspace = "Run the JSON request with --workspace EXISTING_ABSOLUTE_DIRECTORY, or through an MCP server launched with that workspace. Without a workspace, supply absolute source paths and required roots explicitly.";
    match name {
        "font.import" => Some(example(
            "request",
            import_font(),
            &[
                "An existing selected workspace",
                "Original typeface.ttf and typeface-license.txt files in that workspace",
            ],
            &format!(
                "{workspace} The default font store is .inkbolt/fonts. Bind the returned result descriptor as document.fonts[font_id], and use the same ID in text style.font_id. Source files are preserved."
            ),
        )),
        "session.create" => Some(example(
            "request",
            save_session(document()),
            &[
                "An existing selected workspace",
                "An unused session ID example",
            ],
            &format!(
                "{workspace} Saves revision zero in .inkbolt/sessions. For existing artwork, replace document with its snapshot or a pinned file/reference."
            ),
        )),
        "session.dry_run" => Some(example(
            "request",
            json!({"command":"session.dry_run",
            "session_id":"example","request_id":"edit","expected_revision":0,
            "action":{"type":"edit","operations":[text_edit()]},"options":{"preview":true}}),
            &[
                "An existing selected workspace",
                "Session example at revision zero with editable text item label and font face",
            ],
            &format!(
                "{workspace} Review the changes and preview. Submit the returned proposal and the identical action to session.apply_proposal. Copy existing text/frame controls when changing only one field."
            ),
        )),
        _ => None,
    }
}

pub(super) fn attach(mut result: Value, example: Option<Value>) -> Result<Value, Error> {
    if let Some(example) = example {
        if serde_json::to_vec(&example).unwrap().len() > crate::limits::schema::EXAMPLE_BYTES {
            return Err(Error::new(
                "RESOURCE_LIMIT",
                "Discovery example exceeds its byte budget",
            ));
        }
        result["example"] = example;
    }
    Ok(result)
}
