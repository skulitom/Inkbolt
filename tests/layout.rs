use inkbolt::{Document, Request, edit, execute, render, scene};
use serde_json::{Value, json};

fn run(v: Value) -> Value {
    execute(serde_json::from_value::<Request>(v).unwrap()).unwrap()
}
fn create(kind: &str, width: u32, height: u32) -> Document {
    serde_json::from_value(run(
        json!({"command":"document.create","id":"scene","kind":kind,"width":width,"height":height}),
    ))
    .unwrap()
}
fn ops(value: Value) -> Vec<edit::Operation> {
    serde_json::from_value(value).unwrap()
}
fn apply(d: &Document, value: Value) -> Document {
    edit::apply(d, d.revision, &ops(value)).unwrap().document
}
fn rect(id: &str, x: f64, y: f64, w: f64, h: f64, color: [u8; 4]) -> Value {
    json!({"id":id,"content":{"type":"vector","geometry":{"shape":"rect","x":x,"y":y,"width":w,"height":h},"fill":color}})
}
fn bounds(d: &Document, id: &str) -> [f64; 4] {
    scene::bounds(d, scene::index(d, id).unwrap())
        .unwrap()
        .unwrap()
}
fn pixels(d: &Document) -> Vec<u8> {
    render::rasterize(d, 1).unwrap().rgba
}
fn snapshot(d: &Document) -> Document {
    let r = run(json!({"command":"document.export","document":d,"format":"snapshot"}));
    serde_json::from_str(r["data"].as_str().unwrap()).unwrap()
}
fn children(d: &Document, id: Option<&str>) -> Vec<String> {
    scene::children(d, id)
        .iter()
        .map(|&i| d.items[i].id.clone())
        .collect()
}

#[test]
fn nested_groups_transform_ungroup_regroup_and_identity() {
    let original = apply(
        &create("vector", 64, 48),
        json!([
            {"op":"add","item":rect("a",2.0,3.0,8.0,6.0,[220,30,10,255])},
            {"op":"add","item":rect("b",12.0,5.0,4.0,8.0,[20,80,210,255])}
        ]),
    );
    let grouped = apply(
        &original,
        json!([
            {"op":"group","ids":["a","b"],"new_id":"inner","name":"Objects"},
            {"op":"transform","id":"inner","matrix":[1,0,0,1,3,4]},
            {"op":"group","ids":["inner"],"new_id":"outer"},
            {"op":"transform","id":"outer","matrix":[2,0,0,2,0,0]}
        ]),
    );
    assert_eq!(children(&grouped, None), vec!["outer"]);
    assert_eq!(children(&grouped, Some("inner")), vec!["a", "b"]);
    assert_eq!(bounds(&grouped, "a"), [10.0, 14.0, 26.0, 26.0]);
    assert_eq!(bounds(&grouped, "b"), [30.0, 18.0, 38.0, 34.0]);
    assert_eq!(bounds(&grouped, "outer"), [10.0, 14.0, 38.0, 34.0]);
    assert_eq!(snapshot(&grouped), grouped);
    let picture = pixels(&grouped);
    let released = apply(
        &grouped,
        json!([{"op":"ungroup","id":"outer"},{"op":"ungroup","id":"inner"}]),
    );
    assert_eq!(children(&released, None), vec!["a", "b"]);
    assert_eq!(pixels(&released), picture);
    for id in ["a", "b"] {
        assert_eq!(
            released.items[scene::index(&released, id).unwrap()].content,
            original.items[scene::index(&original, id).unwrap()].content
        );
    }
    let regrouped = apply(
        &released,
        json!([{"op":"group","ids":["b","a"],"new_id":"again"}]),
    );
    assert_eq!(children(&regrouped, Some("again")), vec!["a", "b"]);
    assert_eq!(pixels(&regrouped), picture);
}

#[test]
fn named_layers_stacking_visibility_and_explicit_selection_persist() {
    let d = apply(
        &create("vector", 8, 8),
        json!([
            {"op":"add","item":rect("red",0.0,0.0,8.0,8.0,[255,0,0,255])},
            {"op":"group","ids":["red"],"new_id":"under","name":"Duplicate name","role":"layer"},
            {"op":"add","item":rect("blue",0.0,0.0,8.0,8.0,[0,0,255,255])},
            {"op":"group","ids":["blue"],"new_id":"over","name":"Duplicate name","role":"layer"}
        ]),
    );
    assert_eq!(children(&d, None), vec!["under", "over"]);
    assert_eq!(pixels(&d), [0, 0, 255, 255].repeat(64));
    let selected = run(json!({"command":"document.select","document":d,"ids":["blue","red"]}));
    assert_eq!(selected["ids"], json!(["blue", "red"]));
    assert_eq!(selected["items"][0]["parent"], "over");
    let hidden = apply(
        &d,
        json!([{"op":"properties","id":"over","visible":false,"locked":true}]),
    );
    let reopened = snapshot(&hidden);
    assert_eq!(reopened, hidden);
    assert_eq!(pixels(&reopened), [255, 0, 0, 255].repeat(64));
    let selected = run(json!({"command":"document.select","document":reopened,"ids":["blue"]}));
    assert_eq!(selected["items"][0]["effective_visible"], false);
    assert_eq!(selected["items"][0]["effective_locked"], true);
    let err = edit::apply(
        &reopened,
        reopened.revision,
        &ops(json!([{"op":"properties","id":"blue","name":"forbidden"}])),
    )
    .unwrap_err();
    assert_eq!(err.code, "LOCKED");
    let reordered = apply(&d, json!([{"op":"reorder","id":"under","index":1}]));
    assert_eq!(children(&reordered, None), vec!["over", "under"]);
    assert_eq!(pixels(&snapshot(&reordered)), [255, 0, 0, 255].repeat(64));
}

#[test]
fn group_isolation_opacity_and_appearance_loss_rejection() {
    for kind in ["vector", "raster"] {
        let make = |id: &str, color: [u8; 4]| {
            if kind == "vector" {
                rect(id, 0.0, 0.0, 4.0, 4.0, color)
            } else {
                json!({"id":id,"content":{"type":"raster","width":4,"height":4,"rgba_hex":render::hex(&color).repeat(16)}})
            }
        };
        let d = apply(
            &create(kind, 4, 4),
            json!([
                {"op":"add","item":make("back",[100,150,200,255])},
                {"op":"add","item":make("front",[200,100,50,255])},
                {"op":"properties","id":"front","blend":"multiply"},
                {"op":"group","ids":["front"],"new_id":"group","isolated":false}
            ]),
        );
        assert_eq!(pixels(&d), [78, 59, 39, 255].repeat(16));
        let isolated = apply(
            &d,
            json!([{"op":"group_options","id":"group","isolated":true}]),
        );
        assert_eq!(pixels(&isolated), [200, 100, 50, 255].repeat(16));
        let faded = apply(
            &isolated,
            json!([{"op":"properties","id":"group","opacity":0.5}]),
        );
        assert_eq!(pixels(&faded), [150, 125, 125, 255].repeat(16));
        assert_eq!(
            edit::apply(
                &isolated,
                isolated.revision,
                &ops(json!([{"op":"ungroup","id":"group"}]))
            )
            .unwrap_err()
            .code,
            "UNSUPPORTED"
        );
        assert_eq!(
            pixels(&apply(
                &d,
                json!([{"op":"properties","id":"group","opacity":0.5}])
            )),
            [89, 104, 120, 255].repeat(16)
        );
        assert_eq!(
            pixels(&apply(&d, json!([{"op":"ungroup","id":"group"}]))),
            pixels(&d)
        );
    }
}

#[test]
fn nested_transformed_clips_match_every_pixel_and_release_preserves_source() {
    let d = apply(
        &create("vector", 32, 32),
        json!([
            {"op":"add","item":rect("art",0.0,0.0,32.0,32.0,[20,160,90,255])},
            {"op":"clip","id":"art","clip":{"geometry":{"shape":"rect","x":4,"y":4,"width":10,"height":10},"transform":[1,0,0,1,3,2]}},
            {"op":"group","ids":["art"],"new_id":"group"},
            {"op":"clip","id":"group","clip":{"geometry":{"shape":"rect","x":8,"y":0,"width":6,"height":32}}},
            {"op":"transform","id":"group","matrix":[1,0,0,1,2,3]}
        ]),
    );
    let actual = pixels(&snapshot(&d));
    for y in 0..32 {
        for x in 0..32 {
            assert_eq!(
                &actual[(y * 32 + x) * 4..(y * 32 + x + 1) * 4],
                if (10..16).contains(&x) && (9..19).contains(&y) {
                    &[20, 160, 90, 255]
                } else {
                    &[0, 0, 0, 0]
                }
            );
        }
    }
    assert_eq!(bounds(&d, "art"), [2.0, 3.0, 34.0, 35.0]);
    let released = apply(
        &d,
        json!([{"op":"clip","id":"art","clip":null},{"op":"clip","id":"group","clip":null}]),
    );
    assert_eq!(
        released.items[scene::index(&released, "art").unwrap()].content,
        d.items[scene::index(&d, "art").unwrap()].content
    );
    assert_eq!(
        &pixels(&released)[(4 * 32 + 3) * 4..(4 * 32 + 4) * 4],
        &[20, 160, 90, 255]
    );
}

#[test]
fn compound_clip_hole_and_disabled_clip_settings_survive_snapshot() {
    let mut clip = json!({"geometry":{"shape":"path","commands":[
        {"verb":"move","to":[2,2]},{"verb":"line","to":[14,2]},{"verb":"line","to":[14,14]},{"verb":"line","to":[2,14]},{"verb":"close"},
        {"verb":"move","to":[6,6]},{"verb":"line","to":[10,6]},{"verb":"line","to":[10,10]},{"verb":"line","to":[6,10]},{"verb":"close"}
    ]},"fill_rule":"even_odd"});
    let d = apply(
        &create("vector", 16, 16),
        json!([{"op":"add","item":rect("a",0.0,0.0,16.0,16.0,[80,20,190,255])},{"op":"clip","id":"a","clip":clip}]),
    );
    let actual = pixels(&d);
    for y in 0..16 {
        for x in 0..16 {
            let solid = (2..14).contains(&x)
                && (2..14).contains(&y)
                && !((6..10).contains(&x) && (6..10).contains(&y));
            assert_eq!(actual[(y * 16 + x) * 4 + 3], if solid { 255 } else { 0 });
        }
    }
    clip["enabled"] = json!(false);
    let disabled = snapshot(&apply(&d, json!([{"op":"clip","id":"a","clip":clip}])));
    assert!(!disabled.items[0].clip.as_ref().unwrap().enabled);
    assert_eq!(pixels(&disabled), [80, 20, 190, 255].repeat(256));
}

#[test]
fn align_and_distribute_use_world_bounds_and_declared_references() {
    let d = apply(
        &create("vector", 80, 60),
        json!([
            {"op":"add","item":rect("a",2.0,2.0,8.0,6.0,[10,20,30,255])},
            {"op":"add","item":rect("b",14.0,14.0,12.0,8.0,[10,20,30,255])},
            {"op":"add","item":rect("c",40.0,28.0,4.0,10.0,[10,20,30,255])},
            {"op":"group","ids":["a","b"],"new_id":"g"},
            {"op":"transform","id":"g","matrix":[2,0,0,2,0,0]}
        ]),
    );
    let aligned = apply(
        &d,
        json!([{"op":"align","ids":["a","b","c"],"axis":"y","anchor":"center","reference":{"type":"canvas"}}]),
    );
    for id in ["a", "b", "c"] {
        let b = bounds(&aligned, id);
        assert_eq!((b[1] + b[3]) * 0.5, 30.0);
    }
    let distributed = apply(
        &aligned,
        json!([{"op":"distribute","ids":["c","a","b"],"axis":"x","mode":"gaps","reference":{"type":"bounds","bounds":[0,0,80,60]}}]),
    );
    assert_eq!(bounds(&distributed, "a"), [0.0, 24.0, 16.0, 36.0]);
    assert_eq!(bounds(&distributed, "b"), [34.0, 22.0, 58.0, 38.0]);
    assert_eq!(bounds(&distributed, "c"), [76.0, 25.0, 80.0, 35.0]);
    assert_eq!(
        bounds(&distributed, "b")[0] - bounds(&distributed, "a")[2],
        18.0
    );
    assert_eq!(
        bounds(&distributed, "c")[0] - bounds(&distributed, "b")[2],
        18.0
    );
    let key = apply(
        &d,
        json!([{"op":"align","ids":["a","c"],"axis":"x","anchor":"max","reference":{"type":"item","id":"b"}}]),
    );
    for id in ["a", "c"] {
        assert_eq!(bounds(&key, id)[2], bounds(&d, "b")[2]);
    }
    assert_eq!(snapshot(&distributed), distributed);
}

#[test]
fn reparent_and_duplicate_subtrees_keep_world_geometry_and_independent_ids() {
    let d = apply(
        &create("vector", 64, 48),
        json!([
            {"op":"add","item":rect("a",2.0,3.0,8.0,6.0,[220,30,10,255])},
            {"op":"group","ids":["a"],"new_id":"left"},
            {"op":"transform","id":"left","matrix":[2,0,0,2,4,6]},
            {"op":"add","item":{"id":"right","transform":[1,0,0,1,20,10],"content":{"type":"group"}}}
        ]),
    );
    let moved = apply(&d, json!([{"op":"reparent","id":"a","parent":"right"}]));
    assert_eq!(bounds(&moved, "a"), bounds(&d, "a"));
    assert_eq!(pixels(&moved), pixels(&d));
    let copied = apply(
        &moved,
        json!([{"op":"duplicate","id":"right","new_id":"copy","descendant_ids":{"a":"a-copy"}},{"op":"transform","id":"copy","matrix":[1,0,0,1,16,0],"space":"world"}]),
    );
    assert_eq!(children(&copied, Some("copy")), vec!["a-copy"]);
    assert_eq!(bounds(&copied, "a-copy"), [24.0, 12.0, 40.0, 24.0]);
    assert_eq!(bounds(&copied, "a"), [8.0, 12.0, 24.0, 24.0]);
    let removed = apply(&copied, json!([{"op":"remove","id":"copy"}]));
    assert!(scene::index(&removed, "a-copy").is_err());
    assert_eq!(pixels(&removed), pixels(&moved));
}

#[test]
fn invalid_hierarchy_and_locked_ancestors_fail_atomically() {
    let d = apply(
        &create("vector", 16, 16),
        json!([
            {"op":"add","item":rect("a",0.0,0.0,4.0,4.0,[255,0,0,255])},
            {"op":"group","ids":["a"],"new_id":"g"},
            {"op":"properties","id":"g","locked":true}
        ]),
    );
    let source = serde_json::to_vec(&d).unwrap();
    for operation in [
        json!({"op":"properties","id":"a","locked":false}),
        json!({"op":"remove","id":"g"}),
        json!({"op":"clip","id":"a","clip":null}),
        json!({"op":"align","ids":["a"],"axis":"x","anchor":"min","reference":{"type":"canvas"}}),
    ] {
        assert_eq!(
            edit::apply(&d, d.revision, &ops(json!([operation])))
                .unwrap_err()
                .code,
            "LOCKED"
        );
        assert_eq!(serde_json::to_vec(&d).unwrap(), source);
    }
    let unlocked = apply(&d, json!([{"op":"properties","id":"g","locked":false}]));
    assert_eq!(
        edit::apply(
            &unlocked,
            unlocked.revision,
            &ops(json!([{"op":"reparent","id":"g","parent":"g"}]))
        )
        .unwrap_err()
        .code,
        "INVALID_OPERATION"
    );
    assert_eq!(
        edit::apply(
            &unlocked,
            unlocked.revision,
            &ops(json!([{"op":"duplicate","id":"g","new_id":"copy"}]))
        )
        .unwrap_err()
        .code,
        "INVALID_OPERATION"
    );
    let mut cycle = unlocked.clone();
    let i = scene::index(&cycle, "g").unwrap();
    cycle.items[i].parent = Some("g".into());
    assert!(inkbolt::validate(&cycle).is_err());
    let mut dangling = unlocked.clone();
    dangling.items[0].parent = Some("missing".into());
    assert!(inkbolt::validate(&dangling).is_err());
    let mut child_parent = unlocked.clone();
    let i = scene::index(&child_parent, "g").unwrap();
    child_parent.items[i].parent = Some("a".into());
    assert!(inkbolt::validate(&child_parent).is_err());
}

#[test]
fn world_transforms_center_spacing_group_opacity_and_resource_limits() {
    let d = apply(
        &create("vector", 32, 32),
        json!([
            {"op":"add","item":rect("a",0.0,0.0,8.0,8.0,[255,0,0,255])},
            {"op":"add","item":rect("b",4.0,0.0,8.0,8.0,[0,0,255,255])},
            {"op":"group","ids":["a","b"],"new_id":"g"},
            {"op":"properties","id":"g","opacity":0.5}
        ]),
    );
    let p = pixels(&d);
    assert_eq!(&p[4 * 4..5 * 4], &[0, 0, 255, 128]); // Group opacity applies once even in overlap.
    let d = apply(
        &d,
        json!([
            {"op":"transform","id":"g","matrix":[0,1,-1,0,20,0]},
            {"op":"transform","id":"a","matrix":[1,0,0,1,3,4],"space":"world"}
        ]),
    );
    assert_eq!(bounds(&d, "a"), [15.0, 4.0, 23.0, 12.0]);
    let d = apply(
        &create("vector", 32, 32),
        json!([
            {"op":"add","item":rect("a",0.0,1.0,4.0,4.0,[0,0,0,255])},
            {"op":"add","item":rect("b",0.0,12.0,4.0,6.0,[0,0,0,255])},
            {"op":"add","item":rect("c",0.0,24.0,4.0,8.0,[0,0,0,255])},
            {"op":"distribute","ids":["b","c","a"],"axis":"y","mode":"centers","reference":{"type":"canvas"}}
        ]),
    );
    let centers: Vec<_> = ["a", "b", "c"]
        .iter()
        .map(|id| {
            let b = bounds(&d, id);
            (b[1] + b[3]) * 0.5
        })
        .collect();
    assert_eq!(centers, vec![2.0, 15.0, 28.0]);
    let mut d = create("vector", 1024, 1024);
    for i in 0..17 {
        let item=serde_json::from_value(json!({"id":format!("g{i}"),"parent":if i==0 {None}else{Some(format!("g{}",i-1))},"content":{"type":"group"}})).unwrap();
        d.items.push(item);
    }
    inkbolt::validate(&d).unwrap();
    assert_eq!(
        render::rasterize(&d, 1).err().unwrap().code,
        "RESOURCE_LIMIT"
    );
    let item =
        serde_json::from_value(json!({"id":"too-deep","parent":"g16","content":{"type":"group"}}))
            .unwrap();
    d.items.push(item);
    assert_eq!(inkbolt::validate(&d).unwrap_err().code, "RESOURCE_LIMIT");
}
