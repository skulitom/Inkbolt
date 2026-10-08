use inkbolt::{Document, Request, edit, execute, geometry, model::*, render};
use serde_json::{Value, json};

fn run(value: Value) -> Value {
    execute(serde_json::from_value::<Request>(value).unwrap()).unwrap()
}
fn create(kind: &str, w: u32, h: u32) -> Document {
    serde_json::from_value(run(
        json!({"command":"document.create","id":"original","kind":kind,"width":w,"height":h}),
    ))
    .unwrap()
}
fn apply(doc: &Document, ops: Value) -> Document {
    edit::apply(
        doc,
        doc.revision,
        &serde_json::from_value::<Vec<edit::Operation>>(ops).unwrap(),
    )
    .unwrap()
    .document
}
fn vector(id: &str, geometry: Value, fill: Value) -> Value {
    json!({"id":id,"content":{"type":"vector","geometry":geometry,"fill":fill}})
}
fn rect(id: &str, x: f64, y: f64, w: f64, h: f64, color: Value) -> Value {
    vector(
        id,
        json!({"shape":"rect","x":x,"y":y,"width":w,"height":h}),
        color,
    )
}
fn layer(id: &str, w: u32, h: u32, color: [u8; 4]) -> Value {
    json!({"id":id,"content":{"type":"raster","width":w,"height":h,"rgba_hex":render::hex(&color).repeat((w*h) as usize)}})
}
fn pixel(p: &render::Rasterized, x: usize, y: usize) -> [u8; 4] {
    p.rgba[(y * p.width as usize + x) * 4..(y * p.width as usize + x + 1) * 4]
        .try_into()
        .unwrap()
}
fn snapshot(doc: &Document) -> Document {
    let export = run(json!({"command":"document.export","document":doc,"format":"snapshot"}));
    serde_json::from_str(export["data"].as_str().unwrap()).unwrap()
}

#[test]
fn document_creation_and_empty_pixels() {
    for kind in ["vector", "raster"] {
        let d = create(kind, 128, 96);
        assert_eq!(d.resolution_ppi, 96.0);
        assert_eq!(d.color_space, ColorSpace::Srgb);
        assert!(d.items.is_empty());
        assert_eq!(d.revision, 0);
        let inspect = run(json!({"command":"document.inspect","document":d}));
        assert_eq!(inspect["canvas_bounds"], json!([0, 0, 128, 96]));
        assert_eq!(
            render::rasterize(&d, 1).unwrap().rgba,
            vec![0; 128 * 96 * 4]
        );
        assert_eq!(snapshot(&d), d);
    }
    let legacy:Document=serde_json::from_value(json!({"schema_version":1,"id":"old","kind":"vector","width":2,"height":2,"color_space":"srgb"})).unwrap();
    validate(&legacy).unwrap();
    let upgraded = apply(
        &legacy,
        json!([{"op":"add","item":rect("r",0.0,0.0,1.0,1.0,json!([1,2,3,255]))}]),
    );
    assert_eq!(upgraded.schema_version, 2);
    assert_eq!(legacy.schema_version, 1);
}

#[test]
fn rectangle_ellipse_bounds_and_interiors() {
    let d = apply(
        &create("vector", 32, 24),
        json!([
            {"op":"add","item":rect("rect",2.0,3.0,8.0,7.0,json!([220,30,10,255]))},
            {"op":"add","item":vector("oval",json!({"shape":"ellipse","cx":22.0,"cy":12.0,"rx":6.0,"ry":8.0}),json!([20,80,210,255]))}
        ]),
    );
    assert_eq!(
        geometry::item_bounds(&d.items[0]).unwrap(),
        [2.0, 3.0, 10.0, 10.0]
    );
    assert_eq!(
        geometry::item_bounds(&d.items[1]).unwrap(),
        [16.0, 4.0, 28.0, 20.0]
    );
    let p = render::rasterize(&d, 1).unwrap();
    for y in 3..10 {
        for x in 2..10 {
            assert_eq!(pixel(&p, x, y), [220, 30, 10, 255]);
        }
    }
    assert_eq!(pixel(&p, 22, 12), [20, 80, 210, 255]);
    assert_eq!(pixel(&p, 16, 4), [0, 0, 0, 0]);
    assert_eq!(snapshot(&d), d);
}

#[test]
fn cubic_edit_and_analytic_extrema() {
    // y(t)=30t(1-t), whose maximum is7.5 at t=0.5; handles lie at y=10.
    let g = json!({"shape":"path","commands":[{"verb":"move","to":[0,0]},{"verb":"cubic","control1":[0,10],"control2":[10,10],"to":[10,0]}]});
    let d = apply(
        &create("vector", 32, 24),
        json!([{"op":"add","item":vector("curve",g.clone(),json!([10,20,30,255]))}]),
    );
    assert_eq!(
        geometry::item_bounds(&d.items[0]).unwrap(),
        [0.0, 0.0, 10.0, 7.5]
    );
    let mut revised = g;
    revised["commands"][1]["to"] = json!([12, 0]);
    let changed = apply(
        &d,
        json!([{"op":"vector","id":"curve","geometry":revised,"fill":[10,20,30,255]}]),
    );
    assert_eq!(
        geometry::item_bounds(&changed.items[0]).unwrap(),
        [0.0, 0.0, 12.0, 7.5]
    );
    let svg = run(json!({"command":"document.export","document":changed,"format":"svg"}));
    assert!(svg["data"].as_str().unwrap().contains("C 0 10 10 10 12 0"));
    assert_eq!(geometry::item_bounds(&d.items[0]).unwrap()[2], 10.0);
}

#[test]
fn compound_fill_rules_and_centered_stroke() {
    let commands = json!([
        {"verb":"move","to":[2,2]},{"verb":"line","to":[22,2]},{"verb":"line","to":[22,22]},{"verb":"line","to":[2,22]},{"verb":"close"},
        {"verb":"move","to":[8,8]},{"verb":"line","to":[16,8]},{"verb":"line","to":[16,16]},{"verb":"line","to":[8,16]},{"verb":"close"}
    ]);
    let mut item = vector(
        "ring",
        json!({"shape":"path","commands":commands}),
        json!([10, 80, 190, 255]),
    );
    item["content"]["fill_rule"] = json!("even_odd");
    let d = apply(&create("vector", 24, 24), json!([{"op":"add","item":item}]));
    let p = render::rasterize(&snapshot(&d), 1).unwrap();
    for y in 0..24 {
        for x in 0..24 {
            let in_outer = (2..22).contains(&x) && (2..22).contains(&y);
            let in_hole = (8..16).contains(&x) && (8..16).contains(&y);
            assert_eq!(
                pixel(&p, x, y),
                if in_outer && !in_hole {
                    [10, 80, 190, 255]
                } else {
                    [0, 0, 0, 0]
                }
            );
        }
    }
    let mut winding = d.clone();
    if let Content::Vector { fill_rule, .. } = &mut winding.items[0].content {
        *fill_rule = FillRule::Nonzero;
    }
    assert_eq!(
        pixel(&render::rasterize(&winding, 1).unwrap(), 12, 12),
        [10, 80, 190, 255]
    );
    let mut border = rect("border", 4.0, 4.0, 16.0, 16.0, Value::Null);
    border["content"]["stroke"] = json!({"color":[0,0,0,255],"width":4});
    let d = apply(
        &create("vector", 24, 24),
        json!([{"op":"add","item":border}]),
    );
    let p = render::rasterize(&d, 1).unwrap();
    assert_eq!(
        geometry::item_bounds(&d.items[0]).unwrap(),
        [4.0, 4.0, 20.0, 20.0]
    );
    for y in 0..24 {
        for x in 0..24 {
            let outer = (2..22).contains(&x) && (2..22).contains(&y);
            let inner = (6..18).contains(&x) && (6..18).contains(&y);
            assert_eq!(pixel(&p, x, y)[3], if outer && !inner { 255 } else { 0 });
        }
    }
}

#[test]
fn affine_bounds_composition_and_native_precision() {
    let d = apply(
        &create("vector", 64, 64),
        json!([{"op":"add","item":rect("r",1.25,-2.5,8.0,6.0,json!([3,4,5,255]))}]),
    );
    let d = apply(
        &d,
        json!([
            {"op":"transform","id":"r","matrix":[2,0,0,3,0,0]},
            {"op":"transform","id":"r","matrix":[0,1,-1,0,30,20],"space":"world"}
        ]),
    );
    assert_eq!(
        geometry::item_bounds(&d.items[0]).unwrap(),
        [19.5, 22.5, 37.5, 38.5]
    );
    assert_eq!(snapshot(&d), d);
    let local = apply(
        &d,
        json!([{"op":"transform","id":"r","matrix":[1,0,0,1,1,0],"space":"local"}]),
    );
    assert_eq!(
        geometry::item_bounds(&local.items[0]).unwrap(),
        [19.5, 24.5, 37.5, 40.5]
    );
    // Rotated ellipse bounds are analytic, not a transformed bounding rectangle.
    let e = Geometry::Ellipse {
        cx: 0.0,
        cy: 0.0,
        rx: 4.0,
        ry: 2.0,
    };
    let q = 0.5f64.sqrt();
    let b = geometry::bounds(&e, [q, q, -q, q, 10.0, 20.0]);
    assert!((b[0] - (10.0 - 10.0f64.sqrt())).abs() < 1e-12);
}

#[test]
fn raster_layers_snapshot_and_independent_duplicate() {
    let original = create("raster", 4, 3);
    let d = apply(
        &original,
        json!([
            {"op":"add","item":layer("base",4,3,[100,120,140,255])},
            {"op":"duplicate","id":"base","new_id":"copy"},
            {"op":"properties","id":"copy","name":"duplicate name"},
            {"op":"pixel_fill","id":"copy","rect":{"x":1,"y":1,"width":2,"height":1},"color":[240,10,50,128]}
        ]),
    );
    assert!(original.items.is_empty());
    assert_eq!(snapshot(&d), d);
    let Content::Raster { rgba_hex, .. } = &d.items[0].content else {
        panic!()
    };
    assert_eq!(rgba_hex, &"64788cff".repeat(12));
    let d = apply(&d, json!([{"op":"properties","id":"base","visible":false}]));
    assert_eq!(
        pixel(&render::rasterize(&d, 1).unwrap(), 1, 1),
        [240, 10, 50, 128]
    );
    let d = apply(
        &d,
        json!([{"op":"properties","id":"base","visible":true},{"op":"reorder","id":"base","index":1}]),
    );
    assert_eq!(
        pixel(&render::rasterize(&d, 1).unwrap(), 1, 1),
        [100, 120, 140, 255]
    );
    assert_eq!(d.items[1].id, "base");
}

#[test]
fn opacity_and_blending_match_known_swatches() {
    for kind in ["vector", "raster"] {
        let make = |id: &str, c: [u8; 4]| {
            if kind == "vector" {
                rect(id, 0.0, 0.0, 4.0, 4.0, json!(c))
            } else {
                layer(id, 4, 4, c)
            }
        };
        let d = apply(
            &create(kind, 4, 4),
            json!([{"op":"add","item":make("back",[100,150,200,255])},{"op":"add","item":make("front",[200,100,50,255])}]),
        );
        for (mode, expected) in [
            ("normal", [150, 125, 125, 255]),
            ("multiply", [89, 104, 120, 255]),
            ("screen", [161, 171, 205, 255]),
        ] {
            let changed = apply(
                &d,
                json!([{"op":"properties","id":"front","opacity":0.5,"blend":mode}]),
            );
            assert_eq!(
                pixel(&render::rasterize(&changed, 1).unwrap(), 2, 2),
                expected
            );
        }
        let mut transparent = d.clone();
        transparent.items[0].visible = false;
        transparent.items[1].opacity = 0.5;
        transparent.items[1].blend = BlendMode::Multiply;
        assert_eq!(
            pixel(&render::rasterize(&transparent, 1).unwrap(), 2, 2),
            [200, 100, 50, 128]
        );
    }
}

#[test]
fn failures_are_atomic_conflicts_locks_ids_and_limits_are_explicit() {
    let original = apply(
        &create("vector", 16, 16),
        json!([{"op":"add","item":rect("r",2.0,2.0,4.0,4.0,json!([1,2,3,255]))}]),
    );
    let before = serde_json::to_vec(&original).unwrap();
    let operations: Vec<edit::Operation> = serde_json::from_value(
        json!([{"op":"properties","id":"r","name":"changed"},{"op":"remove","id":"missing"}]),
    )
    .unwrap();
    let err = edit::apply(&original, original.revision, &operations).unwrap_err();
    assert_eq!(err.code, "NOT_FOUND");
    assert_eq!(err.operation_index, Some(1));
    assert_eq!(serde_json::to_vec(&original).unwrap(), before);
    assert_eq!(
        edit::apply(&original, 0, &operations).unwrap_err().code,
        "REVISION_CONFLICT"
    );
    let locked = apply(
        &original,
        json!([{"op":"properties","id":"r","locked":true}]),
    );
    for op in [
        json!({"op":"remove","id":"r"}),
        json!({"op":"properties","id":"r","locked":false,"name":"bypass"}),
    ] {
        assert_eq!(
            edit::apply(
                &locked,
                locked.revision,
                &serde_json::from_value::<Vec<edit::Operation>>(json!([op])).unwrap()
            )
            .unwrap_err()
            .code,
            "LOCKED"
        );
    }
    let unlocked = apply(
        &locked,
        json!([{"op":"properties","id":"r","locked":false},{"op":"remove","id":"r"}]),
    );
    assert!(unlocked.items.is_empty());
    let mut invalid = original.clone();
    invalid.items.push(invalid.items[0].clone());
    assert_eq!(validate(&invalid).unwrap_err().code, "INVALID_DOCUMENT");
    invalid = original.clone();
    invalid.items[0].opacity = f64::NAN;
    assert!(validate(&invalid).is_err());
    invalid = original.clone();
    invalid.items[0].transform = [0.0; 6];
    assert_eq!(validate(&invalid).unwrap_err().code, "UNSUPPORTED");
    let large = create("vector", 32768, 32768);
    assert_eq!(
        render::rasterize(&large, 1).err().unwrap().code,
        "RESOURCE_LIMIT"
    );
    let mut exhausted = original.clone();
    exhausted.revision = u64::MAX;
    assert_eq!(
        edit::apply(&exhausted, u64::MAX, &operations)
            .unwrap_err()
            .code,
        "RESOURCE_LIMIT"
    );
}

#[test]
fn unsupported_semantics_do_not_silently_render() {
    let d = apply(
        &create("raster", 2, 2),
        json!([{"op":"add","item":layer("p",2,2,[0,0,0,0])}]),
    );
    let ops = serde_json::from_value::<Vec<edit::Operation>>(
        json!([{"op":"transform","id":"p","matrix":[0,0,0,2,0,0]}]),
    )
    .unwrap();
    assert_eq!(
        edit::apply(&d, d.revision, &ops).unwrap_err().code,
        "UNSUPPORTED"
    );
    for bad in [
        json!({"op":"gradient","id":"x"}),
        json!({"op":"remove","id":"x","surprise":true}),
    ] {
        assert!(serde_json::from_value::<edit::Operation>(bad).is_err());
    }
    let mut d = create("vector", 2, 2);
    let mut item: Item =
        serde_json::from_value(rect("r", 0.0, 0.0, 1.0, 1.0, json!([10, 20, 30, 255]))).unwrap();
    item.blend = BlendMode::Screen;
    d.items.push(item);
    assert_eq!(render::svg(&d).unwrap_err().code, "UNSUPPORTED");
}
#[test]
fn boundary_conditions_preserve_transparency_and_reject_invalid_geometry() {
    let mut d = apply(
        &create("raster", 1, 1),
        json!([{"op":"add","item":layer("p",1,1,[220,40,50,1])}]),
    );
    d.items[0].opacity = 0.1;
    assert_eq!(render::rasterize(&d, 1).unwrap().rgba, vec![0, 0, 0, 0]);
    let mut d = create("vector", 16, 16);
    let item: Item =
        serde_json::from_value(rect("r", 0.0, 0.0, 2.0, 2.0, json!([0, 0, 0, 255]))).unwrap();
    d.items.push(item);
    d.items[0].name = "bad\u{ffff}".to_owned();
    assert!(render::svg(&d).is_err());
    for commands in [
        json!([]),
        json!([{"verb":"move","to":[0,0]}]),
        json!([{"verb":"line","to":[1,1]}]),
        json!([{"verb":"move","to":[0,0]},{"verb":"close"}]),
    ] {
        let malformed: Item = serde_json::from_value(vector(
            "bad",
            json!({"shape":"path","commands":commands}),
            json!([0, 0, 0, 255]),
        ))
        .unwrap();
        d.items = vec![malformed];
        assert!(validate(&d).is_err());
    }
    let g = Geometry::Path {
        commands: vec![
            PathCommand::Move { to: [0.0, 0.0] },
            PathCommand::Cubic {
                control1: [3.0, 4.0],
                control2: [-3.0, 4.0],
                to: [0.0, 0.0],
            },
        ],
    };
    let b = geometry::bounds(&g, identity());
    assert!((b[0] + 3.0f64.sqrt() / 2.0).abs() < 1e-12);
    assert!((b[2] - 3.0f64.sqrt() / 2.0).abs() < 1e-12);
    assert_eq!([b[1], b[3]], [0.0, 3.0]);
}
