use inkbolt::{Document, assistance::segment, control::Control};
use serde_json::json;
use sha2::{Digest, Sha256};

#[test]
fn proxy_selection_is_constructible_and_usable_through_the_public_rust_api() {
    let document: Document = serde_json::from_value(json!({
        "schema_version": 2, "id": "typed-selection", "kind": "raster",
        "width": 4, "height": 1, "color_space": "srgb", "revision": 0,
        "items": [{"id": "pixels", "content": {"type": "raster",
            "width": 4, "height": 1, "rgba_hex": "000000ff000000ffffffffffffffffff"}}]
    }))
    .unwrap();
    let before = serde_json::to_value(&document).unwrap();
    let options = segment::Options {
        region: None,
        proxy: Some(segment::ProxyOptions {
            step: 2,
            refine_radius: 1,
            include_preview: false,
        }),
        foreground: vec![[0, 0]],
        background: vec![[3, 0]],
        smoothness: 0,
        edge_scale: 4096,
        include_costs: false,
    };
    let report =
        segment::inspect(&document, "pixels", &options, None, &Control::default()).unwrap();
    assert_eq!(report["result_format"], "proxy_selection_summary_v1");
    assert_eq!(
        report["mask_summary"]["gray_sha256"],
        format!("{:x}", Sha256::digest([255, 255, 0, 0]))
    );
    assert_eq!(report["proxy_cut"]["minimum_energy"], "0");
    assert_eq!(report["refinement_cut"]["minimum_energy"], "0");
    assert_eq!(serde_json::to_value(&document).unwrap(), before);
    assert_eq!(
        serde_json::to_value(options).unwrap()["proxy"],
        json!({"step": 2, "refine_radius": 1, "include_preview": false})
    );
}
