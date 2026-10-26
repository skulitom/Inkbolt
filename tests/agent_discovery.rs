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
fn essentials_catalog_budget_routes_and_deferred_schemas() {
    let full = mcp::catalog();
    for workspace in [false, true] {
        let tools = mcp::catalog_in_workspace(mcp::CatalogMode::Essentials, workspace);
        assert_eq!(tools.len(), 10);
        assert!(tools.len() <= mcp::ESSENTIALS_TOOLS);
        let bytes = serde_json::to_vec(&tools.values().map(|(_, t)| t).collect::<Vec<_>>())
            .unwrap()
            .len();
        assert!(
            bytes <= mcp::ESSENTIALS_CATALOG_BYTES,
            "essentials is {bytes} bytes"
        );
        let routed = tools["inkbolt_run"].1["inputSchema"]["properties"]["command"]["enum"]
            .as_array()
            .unwrap();
        for (command, _) in full.values() {
            assert!(routed.contains(&json!(command)));
        }
        for (command, tool) in tools.values() {
            let schema = &tool["inputSchema"];
            check_refs(schema, schema);
            if command == "run" {
                continue;
            }
            // Every new deferred tree has a working command-relative selector,
            // including generated definition names, and is actually an object.
            for property in schema["properties"].as_object().unwrap().values() {
                let route = &property["x-inkbolt-schema"];
                if let Some(select) = route["select"].as_str() {
                    assert_eq!(route["name"], *command);
                    let exact = schema::lookup(command, Some(select), true).unwrap();
                    assert!(
                        exact["schema"]["type"] == "object"
                            || exact["schema"]["oneOf"]
                                .as_array()
                                .is_some_and(|variants| variants
                                    .iter()
                                    .all(|variant| variant["type"] == "object"))
                    );
                    check_refs(&exact["schema"], &exact["schema"]);
                }
            }
            assert_eq!(
                tool["annotations"],
                full[tool["name"].as_str().unwrap()].1["annotations"]
            );
        }
    }
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
    assert_eq!(
        capabilities["agent_discovery"]["schema_selector_separator"],
        "/"
    );
    assert_eq!(
        capabilities["agent_discovery"]["schema_variant_selector_field"],
        "select"
    );
    assert_eq!(
        capabilities["agent_discovery"]["schema_selector_max_bytes"],
        inkbolt::limits::schema::MAX_SELECTOR_BYTES
    );
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

#[test]
fn discovery_nested_outline_routes_reach_complete_variant_schemas() {
    for (name, definition) in [
        ("session.apply", "Action"),
        ("document.edit", "Operation"),
        ("document", "Content"),
    ] {
        let outline = schema::lookup(name, Some(definition), false).unwrap();
        assert_eq!(outline["detail"], "outline");
        for variant in outline["variants"].as_array().unwrap() {
            let select = variant["select"].as_str().unwrap();
            assert!(select.len() <= inkbolt::limits::schema::MAX_SELECTOR_BYTES);
            let result = schema::lookup(name, Some(select), true).unwrap();
            check_refs(&result["schema"], &result["schema"]);
            assert_eq!(
                result["schema"]["properties"][variant["field"].as_str().unwrap()]["const"],
                variant["value"]
            );
        }
        // Definitions remain selectable by their existing names from the root.
        for definition in outline["definitions"].as_array().unwrap() {
            assert!(schema::lookup(name, definition.as_str(), false).is_ok());
        }
    }
    let nested = schema::lookup(
        "session.apply",
        Some("Action/edit/Operation/transform"),
        true,
    )
    .unwrap();
    assert_eq!(
        nested["schema"],
        schema::lookup("operation", Some("transform"), true).unwrap()["schema"]
    );
    // A deep selection yields a short executable route in its next outline.
    let repeated = schema::lookup(
        "session.apply",
        Some("Action/edit/Operation/add/Item/Content"),
        false,
    )
    .unwrap();
    for variant in repeated["variants"].as_array().unwrap() {
        let result = schema::lookup("session.apply", variant["select"].as_str(), true).unwrap();
        assert_eq!(
            result["schema"]["properties"][variant["field"].as_str().unwrap()]["const"],
            variant["value"]
        );
    }
    assert_eq!(
        schema::lookup("operation", Some("Geometry/rect"), true).unwrap()["schema"],
        schema::lookup("geometry", Some("rect"), true).unwrap()["schema"]
    );
}

#[test]
fn discovery_failures_offer_working_queries_without_echoing_unknown_text() {
    for (name, select, field) in [
        ("private-unknown-schema", None, "name"),
        ("session.apply", Some("private-unknown-selector"), "select"),
        (
            "session.apply",
            Some("Action/private-unknown-selector"),
            "select",
        ),
        ("session.apply", Some(""), "select"),
        ("session.apply", Some("/Action"), "select"),
        ("session.apply", Some("Action/"), "select"),
        ("session.apply", Some("Action//edit"), "select"),
        ("document.create", Some("Operation/transform"), "select"),
    ] {
        let error = schema::lookup(name, select, false).unwrap_err();
        assert_eq!(error.code, "SCHEMA_NOT_FOUND");
        let encoded = serde_json::to_string(&error).unwrap();
        assert!(!encoded.contains("private-unknown"));
        let details = error.details.unwrap();
        assert_eq!(details["field"], field);
        let request: Request = serde_json::from_value(details["schema_lookup"].clone()).unwrap();
        execute(request).unwrap();
    }
    for (name, select, wanted) in [
        ("session.create", "document", "Document"),
        ("session.apply", "edit", "Action/edit"),
        ("operation", "TRANSFORM", "transform"),
    ] {
        let error = schema::lookup(name, Some(select), false).unwrap_err();
        let details = error.details.unwrap();
        let suggestion = &details["suggested_lookup"];
        assert_eq!(suggestion["select"], wanted);
        let request: Request = serde_json::from_value(suggestion.clone()).unwrap();
        execute(request).unwrap();
    }
    // Both Boundary and Geometry have a rect variant; a hint must not pick one.
    let ambiguous = schema::lookup("operation", Some("rect"), false).unwrap_err();
    assert!(ambiguous.details.unwrap().get("suggested_lookup").is_none());
    let long = "Action/".repeat(20);
    assert_eq!(
        schema::lookup("session.apply", Some(&long), false)
            .unwrap_err()
            .code,
        "INVALID_REQUEST"
    );
}
