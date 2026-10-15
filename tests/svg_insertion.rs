use inkbolt::{edit, model::Document};
use serde_json::json;

#[test]
fn svg_insertion_request_ceiling_covers_fragments_and_documents_in_typed_api() {
    let document: Document = serde_json::from_value(json!({"schema_version":2,
        "id":"typed-svg","kind":"vector","width":16,"height":16,
        "color_space":"srgb","revision":0,"items":[]}))
    .unwrap();
    let original = serde_json::to_value(&document).unwrap();
    for full_document in [false, true] {
        let opening = if full_document {
            "<svg width=\"16\" height=\"16\"><!--"
        } else {
            "<!--"
        };
        let closing = if full_document {
            "--><rect width=\"1\" height=\"1\"/></svg>"
        } else {
            "--><rect width=\"1\" height=\"1\"/>"
        };
        let padding = inkbolt::MAX_REQUEST_BYTES as usize - opening.len() - closing.len();
        let mut svg = format!("{opening}{}{closing}", "x".repeat(padding));
        let operation = |svg| edit::Operation::AddSvg {
            svg,
            images: Default::default(),
            unsupported: Default::default(),
            parent: None,
            prefix: None,
            font_bindings: vec![],
        };
        let accepted = edit::apply(&document, 0, &[operation(svg.clone())]).unwrap();
        assert_eq!(accepted.document.revision, 1);
        assert_eq!(
            accepted.document.items.len(),
            if full_document { 3 } else { 2 }
        );
        svg.push(' ');
        match edit::apply(&document, 0, &[operation(svg)]) {
            Err(error) => {
                assert_eq!(error.code, "RESOURCE_LIMIT");
                assert_eq!(error.operation_index, Some(0));
            }
            Ok(_) => panic!("SVG beyond the advertised request ceiling was admitted"),
        }
        assert_eq!(serde_json::to_value(&document).unwrap(), original);
    }
}
