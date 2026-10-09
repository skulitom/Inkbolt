use inkbolt::{Request, execute, mcp, schema};
use serde_json::{Value, json};

fn check_refs(value: &Value, root: &Value) {
    match value {
        Value::Object(object) => {
            if let Some(reference) = object.get("$ref").and_then(Value::as_str) {
                let name = reference.strip_prefix("#/$defs/").unwrap();
                assert!(!root["$defs"][name].is_null(), "missing {reference}");
            }
            for child in object.values() {
                check_refs(child, root);
            }
        }
        Value::Array(values) => values.iter().for_each(|v| check_refs(v, root)),
        _ => {}
    }
}

#[test]
fn compact_catalog_budget_and_every_command_reachable() {
    let full = mcp::catalog();
    let core = mcp::catalog_with_mode(mcp::CatalogMode::Core);
    let bytes = serde_json::to_vec(&core.values().map(|(_, t)| t).collect::<Vec<_>>())
        .unwrap()
        .len();
    assert!(
        bytes <= mcp::CORE_CATALOG_BYTES,
        "compact catalog is {bytes} bytes"
    );
    assert!(bytes * 10 < serde_json::to_vec(&full).unwrap().len());
    let commands = &core["inkbolt_run"].1["inputSchema"]["properties"]["command"]["enum"];
    for (name, (command, tool)) in &full {
        assert!(core.contains_key(name) || commands.as_array().unwrap().contains(&json!(command)));
        check_refs(&tool["inputSchema"], &tool["inputSchema"]);
    }
    for (_, tool) in core.values() {
        check_refs(&tool["inputSchema"], &tool["inputSchema"]);
    }
    assert_eq!(core["inkbolt_run"].1["annotations"]["readOnlyHint"], false);
    assert_eq!(
        core["inkbolt_run"].1["annotations"]["idempotentHint"],
        false
    );
}

#[test]
fn focused_schemas_are_complete_and_outlines_are_explicit() {
    let index = schema::lookup("index", None, false).unwrap();
    for name in index["types"]
        .as_array()
        .unwrap()
        .iter()
        .chain(index["commands"].as_array().unwrap())
    {
        let result = schema::lookup(name.as_str().unwrap(), None, true).unwrap();
        assert_eq!(result["detail"], "full");
        check_refs(&result["schema"], &result["schema"]);
    }
    let outline = schema::lookup("operation", None, false).unwrap();
    assert_eq!(outline["detail"], "outline");
    assert!(outline.get("schema").is_none());
    assert!(
        outline["variants"]
            .as_array()
            .unwrap()
            .iter()
            .any(|v| v["value"] == "transform")
    );
    let selected = schema::lookup("operation", Some("transform"), false).unwrap();
    assert_eq!(selected["detail"], "full");
    assert_eq!(selected["schema"]["properties"]["op"]["const"], "transform");
    assert!(serde_json::to_vec(&selected).unwrap().len() < 4096);
    let command = schema::lookup("document.edit", Some("Operation"), true).unwrap();
    assert_eq!(
        command["schema"],
        schema::lookup("operation", None, true).unwrap()["schema"]
    );
    for (name, select, full) in [
        ("unknown", None, false),
        ("operation", Some("unknown"), false),
        ("document.create", Some("Operation"), false),
        ("index", Some("document"), false),
        ("index", None, true),
    ] {
        assert!(schema::lookup(name, select, full).is_err());
    }
}

#[test]
fn legacy_schema_and_capabilities_match_typed_discovery() {
    assert_eq!(execute(Request::Schema {}).unwrap(), *schema::full());
    let capabilities = execute(Request::Capabilities {}).unwrap();
    let mut advertised: Vec<_> = capabilities["commands"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_str().unwrap())
        .collect();
    advertised.sort_unstable();
    let mut actual: Vec<_> = schema::commands().collect();
    actual.sort_unstable();
    assert_eq!(advertised, actual);
}
