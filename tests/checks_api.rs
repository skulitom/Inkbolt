use inkbolt::{Document, Request, checks, control::Control, execute, sessions::Resources};
use serde_json::json;

#[test]
fn invalid_typed_content_is_a_failed_incomplete_report_without_a_normalized_identity() {
    let request: Request = serde_json::from_value(json!({"command":"document.create","id":"typed-check","kind":"vector","width":4,"height":4})).unwrap();
    let mut value = execute(request).unwrap();
    value["items"] = json!([{"id":"box","content":{"type":"vector","geometry":{"shape":"rect","x":0,"y":0,"width":2,"height":2},"fill":[30,80,160,255]}}]);
    let mut document: Document = serde_json::from_value(value).unwrap();
    for opacity in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
        document.items[0].opacity = opacity;
        let report = checks::check(
            &document,
            &checks::Options::default(),
            &Resources::default(),
            &Control::default(),
        )
        .unwrap();
        assert_eq!(report["status"], "fail");
        assert_eq!(report["complete"], false);
        assert_eq!(report["valid_structure"], false);
        assert!(report["document_sha256"].is_null());
        assert!(report["document_id"].is_null());
        assert!(!document.items[0].opacity.is_finite());
    }
}
