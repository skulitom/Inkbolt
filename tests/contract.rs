use inkbolt::{Document, Request, execute};
use serde_json::json;

#[test]
fn both_document_kinds_round_trip_without_state() {
    for kind in ["vector", "raster"] {
        let request = serde_json::from_value::<Request>(json!({
            "command": "document.create", "id": "test-01", "kind": kind,
            "width": 1, "height": 32768
        }))
        .unwrap();
        let document = execute(request).unwrap();
        assert_eq!(
            document,
            json!({"schema_version": 2, "id": "test-01", "kind": kind,
            "width": 1, "height": 32768, "color_space": "srgb", "revision":0,
            "resolution_ppi":96.0, "items":[]})
        );
        let validated = execute(
            serde_json::from_value(json!({
                "command": "document.validate", "document": document
            }))
            .unwrap(),
        )
        .unwrap();
        assert_eq!(document, validated);
    }
}

#[test]
fn document_invariants_are_enforced() {
    let original = json!({"schema_version": 1, "id": "valid", "kind": "raster",
        "width": 20, "height": 30, "color_space": "srgb"});
    for (field, value) in [
        ("schema_version", json!(3)),
        ("width", json!(0)),
        ("height", json!(32769)),
        ("id", json!("")),
        ("id", json!("x".repeat(129))),
        ("id", json!("a/b")),
        ("id", json!("a\nb")),
    ] {
        let mut invalid = original.clone();
        invalid[field] = value;
        let document: Document = serde_json::from_value(invalid).unwrap();
        assert_eq!(
            execute(Request::Validate { document }).unwrap_err().code,
            "INVALID_DOCUMENT"
        );
    }
}

#[test]
fn unsupported_semantics_and_unknown_fields_fail() {
    for request in [
        json!({"command": "render"}),
        json!({"command": "capabilities", "surprise": true}),
        json!({"command": "document.create", "id": "x", "kind": "hybrid", "width": 1, "height": 1}),
        json!({"command": "document.create", "id": "x", "kind": "vector", "width": 1.5, "height": 1}),
        json!({"command": "document.create", "id": "x", "kind": "vector", "width": 1, "height": 1, "layers": []}),
        json!({"command": "document.validate", "document": {"schema_version": 1, "id": "x",
            "kind": "raster", "width": 1, "height": 1, "color_space": "srgb", "layers": []}}),
    ] {
        assert!(serde_json::from_value::<Request>(request).is_err());
    }
}
