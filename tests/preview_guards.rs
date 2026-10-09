use inkbolt::{Document, Request, contact_sheets, control::Control, execute, previews};
use serde_json::json;

#[test]
fn nonfinite_rust_preview_options_reject_without_panicking_or_producing_images() {
    let request: Request = serde_json::from_value(json!({"command":"document.create","id":"typed-preview","kind":"vector","width":4,"height":4})).unwrap();
    let document: Document = serde_json::from_value(execute(request).unwrap()).unwrap();
    for number in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
        let view = previews::Options {
            focus: previews::Focus::Region {
                bounds: [0.0, 0.0, number, 1.0],
            },
            ..Default::default()
        };
        assert_eq!(
            previews::preview(&document, &view, None, None, &Control::default())
                .unwrap_err()
                .code,
            "INVALID_REQUEST"
        );
        let options = contact_sheets::Options {
            views: vec![view],
            ..Default::default()
        };
        assert_eq!(
            contact_sheets::sheet(&document, &options, None, None, &Control::default())
                .unwrap_err()
                .code,
            "INVALID_REQUEST"
        );
    }
}
