use inkbolt::{Document, Request, boards, edit, execute, model::*, render, scene};
use serde_json::{Value, json};
fn create() -> Document {
    serde_json::from_value(execute(serde_json::from_value::<Request>(json!({"command":"document.create","id":"board-contract","kind":"raster","width":64,"height":48})).unwrap()).unwrap()).unwrap()
}
fn apply(d: &Document, ops: Value) -> Result<edit::EditResult, inkbolt::Error> {
    edit::apply(
        d,
        d.revision,
        &serde_json::from_value::<Vec<edit::Operation>>(ops).unwrap(),
    )
}
fn frame(id: &str, parent: Option<&str>, role: &str, w: u32, h: u32, x: f64, y: f64) -> Value {
    json!({"op":"add","item":{"id":id,"parent":parent,"transform":[1,0,0,1,x,y],"content":{"type":"frame","frame":{"role":role,"width":w,"height":h}}}})
}
fn fixture() -> Document {
    let d = create();
    let mut ops = vec![frame("board", None, "artboard", 20, 10, 10., 15.)];
    for (n, x) in [1., 5., 9.].into_iter().enumerate() {
        ops.push(frame(&format!("f{n}"), Some("board"), "frame", 2, 2, x, 1.));
    }
    ops.push(json!({"op":"guide_put","id":"board","guide":{"id":"top","axis":"y","position":3}}));
    apply(&d, json!(ops)).unwrap().document
}
#[test]
fn nested_frames_align_to_transformed_guides_and_distribute_inside_artboard() {
    let d = fixture();
    let d=apply(&d,json!([
        {"op":"align","ids":["f0","f1","f2"],"axis":"y","anchor":"min","reference":{"type":"guide","frame_id":"board","id":"top"}},
        {"op":"distribute","ids":["f0","f1","f2"],"axis":"x","mode":"gaps","reference":{"type":"item","id":"board"}}
    ])).unwrap().document;
    for (id, x) in [("f0", 10.), ("f1", 19.), ("f2", 28.)] {
        let i = scene::index(&d, id).unwrap();
        assert_eq!(scene::bounds(&d, i).unwrap(), Some([x, 18., x + 2., 20.]));
    }
    let saved = serde_json::to_vec(&d).unwrap();
    let reopened: Document = serde_json::from_slice(&saved).unwrap();
    validate(&reopened).unwrap();
    assert_eq!(reopened, d);
    let d=apply(&d,json!([{"op":"guide_put","id":"board","guide":{"id":"top","axis":"y","position":4}},{"op":"align","ids":["f0"],"axis":"y","anchor":"min","reference":{"type":"guide","frame_id":"board","id":"top"}}])).unwrap().document;
    assert_eq!(
        scene::bounds(&d, scene::index(&d, "f0").unwrap()).unwrap(),
        Some([10., 19., 12., 21.])
    );
}
#[test]
fn rotated_guides_use_world_axes_and_oblique_guides_fail_without_mutation() {
    let d = fixture();
    let d=apply(&d,json!([{"op":"transform","id":"board","matrix":[0,1,-1,0,30,0]},{"op":"align","ids":["f0"],"axis":"x","anchor":"min","reference":{"type":"guide","frame_id":"board","id":"top"}}])).unwrap().document;
    assert_eq!(
        scene::bounds(&d, scene::index(&d, "f0").unwrap())
            .unwrap()
            .unwrap()[0],
        27.
    );
    let skewed = apply(
        &d,
        json!([{"op":"transform","id":"board","matrix":[1,0.5,0,1,0,0]}]),
    )
    .unwrap()
    .document;
    let before = skewed.clone();
    let e=apply(&skewed,json!([{"op":"align","ids":["f0"],"axis":"y","anchor":"min","reference":{"type":"guide","frame_id":"board","id":"top"}}])).unwrap_err();
    assert_eq!(e.code, "UNSUPPORTED");
    assert_eq!(skewed, before);
}
#[test]
fn frame_bounds_exclude_overflow_and_resize_changes_only_the_viewport() {
    let d = create();
    let d=apply(&d,json!([frame("board",None,"artboard",8,6,3.,4.),{"op":"add","item":{"id":"oversized","parent":"board","transform":[1,0,0,1,-3,-2],"content":{"type":"fill","width":20,"height":20,"paint":[20,40,80,255]}}}])).unwrap().document;
    assert_eq!(
        scene::bounds(&d, scene::index(&d, "board").unwrap()).unwrap(),
        Some([3., 4., 11., 10.])
    );
    let revised = apply(
        &d,
        json!([{"op":"frame","id":"board","frame":{"role":"artboard","width":5,"height":3}}]),
    )
    .unwrap()
    .document;
    assert_eq!(
        revised.items[scene::index(&revised, "oversized").unwrap()],
        d.items[scene::index(&d, "oversized").unwrap()]
    );
    let standalone = boards::standalone(&revised, "board", false).unwrap();
    let png = render::rasterize(&standalone, 1).unwrap();
    assert_eq!((png.width, png.height), (5, 3));
    assert_eq!(png.rgba, [20, 40, 80, 255].repeat(15));
}
#[test]
fn existing_clip_and_own_opacity_survive_bleed_and_ancestor_effects_stay_outside_export() {
    let d = create();
    let d=apply(&d,json!([
        {"op":"add","item":{"id":"parent","opacity":0.25,"content":{"type":"group"}}},
        {"op":"add","item":{"id":"board","parent":"parent","opacity":0.5,"clip":{"geometry":{"shape":"rect","x":0,"y":0,"width":2,"height":3}},"content":{"type":"frame","frame":{"role":"artboard","width":4,"height":3,"bleed":{"left":1,"top":1},"background":[100,150,200,255]}}}}
    ])).unwrap().document;
    let standalone = boards::standalone(&d, "board", true).unwrap();
    let rendered = render::rasterize(&standalone, 1).unwrap();
    assert_eq!((rendered.width, rendered.height), (5, 4));
    for y in 0..4 {
        for x in 0..5 {
            let expected = if (1..3).contains(&x) && (1..4).contains(&y) {
                vec![100, 150, 200, 128]
            } else {
                vec![0; 4]
            };
            assert_eq!(
                rendered.rgba[(y * 5 + x) * 4..(y * 5 + x + 1) * 4],
                expected
            );
        }
    }
}
#[test]
fn artboard_and_guide_locks_and_cycles_preserve_the_whole_snapshot() {
    let d = fixture();
    let locked = apply(&d, json!([{"op":"properties","id":"f1","locked":true}]))
        .unwrap()
        .document;
    let before = locked.clone();
    for op in [
        json!({"op":"guide_remove","id":"board","guide_id":"top"}),
        json!({"op":"remove","id":"board"}),
        json!({"op":"frame","id":"board","frame":{"role":"artboard","width":10,"height":5}}),
    ] {
        assert_eq!(apply(&locked, json!([op])).unwrap_err().code, "LOCKED");
        assert_eq!(locked, before);
    }
    assert_eq!(
        apply(&d, json!([{"op":"reparent","id":"board","parent":"f0"}]))
            .unwrap_err()
            .code,
        "INVALID_OPERATION"
    );
    assert_eq!(boards::order(&d).len(), 1);
    assert_eq!(apply(&d,json!([{"op":"align","ids":["board"],"axis":"y","anchor":"min","reference":{"type":"guide","frame_id":"board","id":"top"}}])).unwrap_err().code,"INVALID_OPERATION");
    let removed = apply(
        &d,
        json!([{"op":"guide_remove","id":"board","guide_id":"top"}]),
    )
    .unwrap()
    .document;
    assert_eq!(
        boards::guide_bounds(&removed, "board", "top", inkbolt::layout::Axis::Y)
            .unwrap_err()
            .code,
        "NOT_FOUND"
    );
}
#[test]
fn guide_frame_and_artboard_limits_fail_before_edit_publication() {
    let d = create();
    let ops: Vec<_> = (0..33)
        .map(|i| frame(&format!("b{i}"), None, "artboard", 2, 2, 0., 0.))
        .collect();
    let e = apply(&d, json!(ops)).unwrap_err();
    assert_eq!(e.code, "RESOURCE_LIMIT");
    assert_eq!(e.operation_index, Some(32));
    assert!(d.items.is_empty());
    let d = fixture();
    for value in [
        json!({"role":"frame","width":3,"height":3,"bleed":{"top":1}}),
        json!({"role":"artboard","width":3,"height":3,"guides":[{"id":"g","axis":"x","position":0},{"id":"g","axis":"y","position":1}]}),
    ] {
        assert_eq!(
            apply(&d, json!([{"op":"frame","id":"board","frame":value}]))
                .unwrap_err()
                .code,
            "INVALID_DOCUMENT"
        );
    }
    let guides: Vec<_> = (0..65)
        .map(|i| json!({"id":format!("g{i}"),"axis":"x","position":i}))
        .collect();
    assert_eq!(apply(&d,json!([{"op":"frame","id":"board","frame":{"role":"artboard","width":100,"height":100,"guides":guides}}])).unwrap_err().code,"RESOURCE_LIMIT");
}
