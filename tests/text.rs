use inkbolt::{Document, Request, edit, execute, fonts, model::*, scene, text};
use serde_json::{Value, json};
fn document() -> Document {
    serde_json::from_value(execute(serde_json::from_value::<Request>(json!({"command":"document.create","id":"text-contract","kind":"vector","width":100,"height":100})).unwrap()).unwrap()).unwrap()
}
fn apply(d: &Document, ops: Value) -> Result<edit::EditResult, inkbolt::Error> {
    edit::apply(
        d,
        d.revision,
        &serde_json::from_value::<Vec<edit::Operation>>(ops).unwrap(),
    )
}
fn fixture() -> Document {
    let d = document();
    let descriptor = fonts::Font {
        sha256: "a".repeat(64),
        license_sha256: "b".repeat(64),
        face_index: 0,
        bytes: 100,
    };
    apply(&d,json!([{"op":"font_put","id":"pinned","font":descriptor},{"op":"add","item":{"id":"t","content":{"type":"text","frame":{"text":"Aé😀","width":40,"height":20,"style":{"font_id":"pinned","size":12,"fill":[0,0,0,255]}}}}}])).unwrap().document
}
#[test]
fn text_frame_geometry_tracks_hierarchy_and_alignment_without_loading_fonts() {
    let d = fixture();
    let d=apply(&d,json!([{"op":"transform","id":"t","matrix":[2,0,0,3,5,7]},{"op":"group","ids":["t"],"new_id":"g"},{"op":"transform","id":"g","matrix":[1,0,0,1,4,6]}])).unwrap().document;
    assert_eq!(
        scene::bounds(&d, scene::index(&d, "t").unwrap()).unwrap(),
        Some([9., 13., 89., 73.])
    );
    let d=apply(&d,json!([{"op":"align","ids":["t"],"axis":"x","anchor":"center","reference":{"type":"canvas"}}])).unwrap().document;
    assert_eq!(
        scene::bounds(&d, scene::index(&d, "t").unwrap()).unwrap(),
        Some([10., 13., 90., 73.])
    );
}
#[test]
fn text_unicode_ranges_are_scalar_based_and_never_split_graphemes() {
    let d = fixture();
    let mut revised=apply(&d,json!([{"op":"text_range","id":"t","start":1,"end":2,"text":"AB","style":{"font_id":"pinned","size":20,"fill":[200,0,0,255]}}])).unwrap().document;
    let Content::Text { frame } = &revised.items[0].content else {
        panic!()
    };
    assert_eq!(frame.text, "AAB😀");
    assert_eq!((frame.ranges[0].start, frame.ranges[0].end), (1, 3));
    let Content::Text { frame } = &mut revised.items[0].content else {
        panic!()
    };
    frame.text = "A\u{301}B".into();
    frame.ranges.clear();
    validate(&revised).unwrap();
    let before = revised.clone();
    assert_eq!(
        apply(
            &revised,
            json!([{"op":"text_range","id":"t","start":1,"end":2,"text":"X"}])
        )
        .unwrap_err()
        .code,
        "INVALID_DOCUMENT"
    );
    assert_eq!(revised, before);
    assert_eq!(
        text::boundaries("A\u{301}😀"),
        [0, 2, 3].into_iter().collect()
    );
}
#[test]
fn font_relink_and_text_edits_honor_ancestor_locks_and_batch_rollback() {
    let d = fixture();
    let before = d.clone();
    let error=apply(&d,json!([{"op":"text_range","id":"t","start":0,"end":1,"text":"B"},{"op":"font_remove","id":"pinned"}])).unwrap_err();
    assert_eq!(error.code, "FONT_IN_USE");
    assert_eq!(error.operation_index, Some(1));
    assert_eq!(d, before);
    let locked = apply(
        &d,
        json!([{"op":"group","ids":["t"],"new_id":"g"},{"op":"properties","id":"g","locked":true}]),
    )
    .unwrap()
    .document;
    assert_eq!(
        apply(
            &locked,
            json!([{"op":"font_put","id":"pinned","font":locked.fonts["pinned"]}])
        )
        .unwrap_err()
        .code,
        "LOCKED"
    );
    assert_eq!(
        apply(
            &locked,
            json!([{"op":"text_range","id":"t","start":0,"end":1,"text":"B"}])
        )
        .unwrap_err()
        .code,
        "LOCKED"
    );
}
#[test]
fn invalid_font_descriptors_undefined_references_and_text_resources_fail_explicitly() {
    let d = fixture();
    let mut bad = d.clone();
    bad.fonts.get_mut("pinned").unwrap().sha256 = "A".repeat(64);
    assert_eq!(validate(&bad).unwrap_err().code, "INVALID_DOCUMENT");
    bad = d.clone();
    bad.fonts.clear();
    assert_eq!(validate(&bad).unwrap_err().code, "INVALID_DOCUMENT");
    bad = d.clone();
    let Content::Text { frame } = &mut bad.items[0].content else {
        panic!()
    };
    frame.text = "A".repeat(4097);
    assert_eq!(validate(&bad).unwrap_err().code, "RESOURCE_LIMIT");
    assert_eq!(
        inkbolt::render::rasterize(&d, 1).err().unwrap().code,
        "FONT_ROOT_REQUIRED"
    );
}
