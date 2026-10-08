use inkbolt::{
    Document, Request, edit, execute,
    model::*,
    paint::{Paint, Sampler},
    render,
};
use serde_json::{Value, json};

fn create(kind: &str, w: u32, h: u32) -> Document {
    serde_json::from_value(execute(serde_json::from_value::<Request>(json!({"command":"document.create","id":"paint-original","kind":kind,"width":w,"height":h})).unwrap()).unwrap()).unwrap()
}
fn apply(d: &Document, ops: Value) -> Document {
    edit::apply(
        d,
        d.revision,
        &serde_json::from_value::<Vec<edit::Operation>>(ops).unwrap(),
    )
    .unwrap()
    .document
}
fn item(kind: &str, w: u32, h: u32, paint: Value) -> Value {
    if kind == "vector" {
        json!({"id":"shape","content":{"type":"vector","geometry":{"shape":"rect","x":0,"y":0,"width":w,"height":h},"fill":paint}})
    } else {
        json!({"id":"shape","content":{"type":"fill","width":w,"height":h,"paint":paint}})
    }
}
fn document(kind: &str, w: u32, h: u32, paint: Value) -> Document {
    apply(
        &create(kind, w, h),
        json!([{"op":"add","item":item(kind,w,h,paint)}]),
    )
}
fn linear() -> Value {
    json!({"type":"linear","start":[0.5,0.5],"end":[8.5,0.5],"stops":[{"offset":0,"color":[0,0,0,255]},{"offset":1,"color":[255,255,255,255]}]})
}
fn pixel(p: &render::Rasterized, x: usize, y: usize) -> [u8; 4] {
    p.rgba[(y * p.width as usize + x) * 4..(y * p.width as usize + x + 1) * 4]
        .try_into()
        .unwrap()
}
fn persist(d: &Document) -> Document {
    serde_json::from_str(&serde_json::to_string(d).unwrap()).unwrap()
}
fn sample(paint: Value, point: [f64; 2]) -> [u8; 4] {
    let p = serde_json::from_value::<Paint>(paint).unwrap();
    Sampler::new(&p, identity())
        .unwrap()
        .sample(point)
        .map(|v| (v * 255.0).round() as u8)
}

#[test]
fn editable_linear_endpoints_and_all_monotonic_pixels() {
    for kind in ["vector", "raster"] {
        let original = create(kind, 9, 3);
        let d = apply(
            &original,
            json!([{"op":"add","item":item(kind,9,3,linear())}]),
        );
        assert!(original.items.is_empty());
        let output = render::rasterize(&d, 1).unwrap();
        for y in 0..3 {
            for (x, level) in [0, 32, 64, 96, 128, 159, 191, 223, 255].iter().enumerate() {
                assert_eq!(pixel(&output, x, y), [*level, *level, *level, 255]);
            }
        }
        let mut paint = linear();
        paint["stops"][0]["color"] = json!([255, 0, 0, 255]);
        paint["stops"][1]["color"] = json!([0, 0, 255, 255]);
        let op = if kind == "vector" {
            json!({"op":"vector","id":"shape","geometry":{"shape":"rect","x":0,"y":0,"width":9,"height":3},"fill":paint})
        } else {
            json!({"op":"fill","id":"shape","paint":paint})
        };
        let changed = apply(&d, json!([op]));
        assert_eq!(changed.revision, 2);
        assert_eq!(persist(&changed), changed);
        assert_eq!(
            pixel(&render::rasterize(&changed, 1).unwrap(), 4, 1),
            [128, 0, 128, 255]
        );
        assert_eq!(
            pixel(&render::rasterize(&d, 1).unwrap(), 4, 1),
            [128, 128, 128, 255]
        );
    }
}

#[test]
fn duplicate_stops_spreads_spaces_and_transparent_color_are_explicit() {
    let mut p = linear();
    p["stops"] = json!([{"offset":0,"color":[255,0,0,255]},{"offset":0.5,"color":[255,0,0,255]},{"offset":0.5,"color":[0,0,255,255]},{"offset":1,"color":[0,255,0,255]}]);
    assert_eq!(sample(p.clone(), [4.5, 0.5]), [0, 0, 255, 255]);
    assert_eq!(sample(p.clone(), [2.5, 0.5]), [255, 0, 0, 255]);
    assert_eq!(sample(p.clone(), [-3.5, 0.5]), [255, 0, 0, 255]);
    p["spread"] = json!("repeat");
    assert_eq!(sample(p.clone(), [-3.5, 0.5]), [0, 0, 255, 255]);
    assert_eq!(sample(p.clone(), [8.5, 0.5]), [255, 0, 0, 255]);
    p["spread"] = json!("reflect");
    assert_eq!(sample(p.clone(), [8.5, 0.5]), [0, 255, 0, 255]);
    assert_eq!(sample(p, [16.5, 0.5]), [255, 0, 0, 255]);
    let mut p = linear();
    p["space"] = json!("linear_rgb");
    assert_eq!(sample(p.clone(), [4.5, 0.5]), [188, 188, 188, 255]);
    p["space"] = json!("srgb");
    p["stops"] = json!([{"offset":0,"color":[255,0,0,255]},{"offset":1,"color":[0,0,255,0]}]);
    assert_eq!(sample(p.clone(), [4.5, 0.5]), [128, 0, 128, 128]);
    for kind in ["vector", "raster"] {
        let d = document(kind, 9, 1, p.clone());
        assert_eq!(
            pixel(&render::rasterize(&d, 1).unwrap(), 4, 0),
            [128, 0, 128, 128]
        );
        let mut background = item(kind, 9, 1, json!([255, 255, 255, 255]));
        background["id"] = json!("backdrop");
        let d = apply(&d, json!([{"op":"add","item":background,"index":0}]));
        assert_eq!(
            pixel(&render::rasterize(&d, 1).unwrap(), 4, 0),
            [191, 128, 191, 255]
        );
    }
    p["stops"] =
        json!([{"offset":0.25,"color":[255,0,0,255]},{"offset":0.75,"color":[0,0,255,255]}]);
    assert_eq!(sample(p.clone(), [0.5, 0.5]), [255, 0, 0, 255]);
    assert_eq!(sample(p, [8.5, 0.5]), [0, 0, 255, 255]);
}

#[test]
fn radial_and_freeform_samples_transforms_and_persistence() {
    let radial = json!({"type":"radial","center":[2.5,2.5],"radius":2,"stops":linear()["stops"]});
    for kind in ["vector", "raster"] {
        let d = document(kind, 5, 5, radial.clone());
        let output = render::rasterize(&d, 1).unwrap();
        assert_eq!(pixel(&output, 2, 2), [0, 0, 0, 255]);
        assert_eq!(pixel(&output, 3, 2), [128, 128, 128, 255]);
        assert_eq!(pixel(&output, 4, 2), [255; 4]);
        assert_eq!(pixel(&output, 0, 0), [255; 4]);
    }
    let mut elliptical = radial;
    elliptical["transform"] = json!([2, 0, 0, 1, 0.5, 1]);
    assert_eq!(sample(elliptical.clone(), [5.5, 3.5]), [0, 0, 0, 255]);
    assert_eq!(sample(elliptical.clone(), [7.5, 3.5]), [128, 128, 128, 255]);
    assert_eq!(sample(elliptical, [5.5, 4.5]), [128, 128, 128, 255]);
    let free = json!({"type":"freeform","anchors":[{"point":[0.5,0.5],"color":[255,0,0,255]},{"point":[4.5,0.5],"color":[0,255,0,255]},{"point":[2.5,4.5],"color":[0,0,255,0]}]});
    let d = document("vector", 5, 5, free.clone());
    let p = render::rasterize(&d, 1).unwrap();
    assert_eq!(pixel(&p, 0, 0), [255, 0, 0, 255]);
    assert_eq!(pixel(&p, 4, 0), [0, 255, 0, 255]);
    assert_eq!(pixel(&p, 2, 4), [0; 4]);
    assert_eq!(pixel(&p, 2, 0), [113, 113, 28, 227]);
    assert_eq!(persist(&d), d);
    assert_eq!(render::svg(&d).unwrap_err().code, "UNSUPPORTED");
    let mut moved = free.clone();
    moved["transform"] = json!([2, 0, 0, 1, 4, 3]);
    assert_eq!(sample(moved, [9.0, 3.5]), [113, 113, 28, 227]);
    let mut linear = free;
    linear["space"] = json!("linear_rgb");
    assert_eq!(sample(linear, [2.5, 0.5]), [178, 178, 94, 227]);
}

#[test]
fn gradient_strokes_nested_transforms_and_object_opacity() {
    let stroke = linear();
    let d = apply(
        &create("vector", 12, 6),
        json!([
            {"op":"add","item":{"id":"g","transform":[1,0,0,1,1,1],"content":{"type":"group"}}},
            {"op":"add","item":{"id":"line","parent":"g","content":{"type":"vector","geometry":{"shape":"path","commands":[{"verb":"move","to":[0.5,1.5]},{"verb":"line","to":[8.5,1.5]}]},"stroke":{"color":stroke,"width":2,"cap":"square"}}}}
        ]),
    );
    let p = render::rasterize(&d, 1).unwrap();
    assert_eq!(pixel(&p, 1, 2), [0, 0, 0, 255]);
    assert_eq!(pixel(&p, 5, 2), [128, 128, 128, 255]);
    assert_eq!(pixel(&p, 9, 2), [255; 4]);
    let mut shape = item("vector", 8, 8, json!([255, 0, 0, 255]));
    shape["content"]["geometry"] = json!({"shape":"rect","x":1,"y":1,"width":6,"height":6});
    let blue = json!({"type":"linear","start":[0,0],"end":[1,0],"stops":[{"offset":0,"color":[0,0,255,128]},{"offset":1,"color":[0,0,255,128]}]});
    shape["content"]["stroke"] = json!({"color":blue,"width":2});
    shape["opacity"] = json!(0.5);
    let d = apply(&create("vector", 8, 8), json!([{"op":"add","item":shape}]));
    let p = render::rasterize(&d, 1).unwrap();
    assert_eq!(pixel(&p, 1, 3), [127, 0, 128, 128]);
    assert_eq!(pixel(&p, 3, 3), [255, 0, 0, 128]);
}

#[test]
fn original_pattern_all_pixels_repeat_seams_negative_offsets_and_scale() {
    let tile = [
        [255, 0, 0, 255],
        [0, 255, 0, 128],
        [0, 0, 255, 255],
        [255, 255, 0, 255],
        [0, 0, 0, 0],
        [0, 255, 255, 255],
    ];
    let paint = json!({"type":"pattern","width":3,"height":2,"rgba_hex":render::hex(&tile.concat()),"transform":[2,0,0,2,1,1]});
    for kind in ["vector", "raster"] {
        let d = document(kind, 13, 9, paint.clone());
        let p = render::rasterize(&d, 1).unwrap();
        for y in 0..9 {
            for x in 0..13 {
                let tx = ((x as i32 - 1).div_euclid(2)).rem_euclid(3) as usize;
                let ty = ((y as i32 - 1).div_euclid(2)).rem_euclid(2) as usize;
                assert_eq!(pixel(&p, x, y), tile[ty * 3 + tx]);
            }
        }
        assert_eq!(persist(&d), d);
        let copy = apply(
            &d,
            json!([{"op":"duplicate","id":"shape","new_id":"copy"},{"op":"remove","id":"shape"}]),
        );
        assert_eq!(render::rasterize(&copy, 1).unwrap().rgba, p.rgba);
    }
}

#[test]
fn raster_fill_dither_is_repeatable_unbiased_and_editable() {
    let mut paint = linear();
    paint["start"] = json!([0, 0]);
    paint["end"] = json!([256, 0]);
    let original = document("raster", 8, 6, paint.clone());
    let plain = render::rasterize(&original, 1).unwrap();
    let d = apply(
        &original,
        json!([{"op":"fill","id":"shape","paint":paint,"dither":"ordered4x4"}]),
    );
    let p = render::rasterize(&d, 1).unwrap();
    assert_eq!(render::rasterize(&persist(&d), 1).unwrap().rgba, p.rgba);
    let expected = [[0, 2, 2, 4], [1, 1, 3, 3], [0, 2, 2, 4], [1, 1, 3, 3]];
    let mut sum = 0;
    for (y, row) in expected.iter().enumerate() {
        for (x, v) in row.iter().enumerate() {
            assert_eq!(pixel(&p, x, y), [*v, *v, *v, 255]);
            sum += *v as i32;
            assert_eq!(pixel(&plain, x, y), [x as u8, x as u8, x as u8, 255]);
        }
    }
    assert_eq!(sum, 32);
    let moved = apply(
        &d,
        json!([{"op":"transform","id":"shape","matrix":[1,0,0,1,2,1]}]),
    );
    let m = render::rasterize(&moved, 1).unwrap();
    for y in 0..4 {
        for x in 0..4 {
            assert_eq!(pixel(&m, x + 2, y + 1), pixel(&p, x, y));
        }
    }
    let locked = apply(&d, json!([{"op":"properties","id":"shape","locked":true}]));
    let ops = serde_json::from_value::<Vec<edit::Operation>>(
        json!([{"op":"fill","id":"shape","paint":[12,34,56,128]}]),
    )
    .unwrap();
    assert_eq!(
        edit::apply(&locked, locked.revision, &ops)
            .unwrap_err()
            .code,
        "LOCKED"
    );
    let solid = apply(
        &original,
        json!([{"op":"fill","id":"shape","paint":[12,34,56,128]}]),
    );
    assert_eq!(
        pixel(&render::rasterize(&solid, 1).unwrap(), 0, 0),
        [12, 34, 56, 128]
    );
    for kind in ["vector", "raster"] {
        let low_alpha = document(kind, 1, 1, json!([123, 231, 34, 1]));
        assert_eq!(
            pixel(&render::rasterize(&low_alpha, 1).unwrap(), 0, 0),
            [123, 231, 34, 1]
        );
    }
}

#[test]
fn paint_validation_resource_limits_and_failed_batches_preserve_sources() {
    let original = document("raster", 8, 8, linear());
    let saved = serde_json::to_string(&original).unwrap();
    let bad = [
        json!({"type":"linear","start":[0,0],"end":[0,0],"stops":linear()["stops"]}),
        json!({"type":"linear","start":[0,0],"end":[1,0],"stops":[{"offset":1,"color":[0,0,0,0]},{"offset":0,"color":[255,255,255,255]}]}),
        json!({"type":"radial","center":[0,0],"radius":0,"stops":linear()["stops"]}),
        json!({"type":"freeform","anchors":[{"point":[0,0],"color":[0,0,0,0]},{"point":[0,0],"color":[255,255,255,255]}]}),
        json!({"type":"pattern","width":0,"height":1,"rgba_hex":""}),
        json!({"type":"pattern","width":1,"height":1,"rgba_hex":"gg112233"}),
    ];
    for paint in bad {
        let ops=serde_json::from_value::<Vec<edit::Operation>>(json!([{"op":"properties","id":"shape","name":"candidate"},{"op":"fill","id":"shape","paint":paint}])).unwrap();
        assert_eq!(
            edit::apply(&original, 1, &ops).unwrap_err().operation_index,
            Some(1)
        );
        assert_eq!(serde_json::to_string(&original).unwrap(), saved);
    }
    let mut singular = linear();
    singular["transform"] = json!([0, 0, 0, 1, 0, 0]);
    assert!(Sampler::new(&serde_json::from_value(singular).unwrap(), identity()).is_err());
    let mut unknown = linear();
    unknown["focal"] = json!([1, 1]);
    assert!(serde_json::from_value::<Paint>(unknown).is_err());
    let mut d = create("vector", 1, 1);
    let mut p = linear();
    p["stops"] = json!(
        (0..64)
            .map(|i| json!({"offset":i as f64/63.0,"color":[0,0,0,255]}))
            .collect::<Vec<_>>()
    );
    for i in 0..65 {
        let mut v = item("vector", 1, 1, p.clone());
        v["id"] = json!(format!("i{i}"));
        d.items.push(serde_json::from_value(v).unwrap());
    }
    assert_eq!(validate(&d).unwrap_err().code, "RESOURCE_LIMIT");
    let free = json!({"type":"freeform","anchors":(0..64).map(|i|json!({"point":[i,0],"color":[0,0,0,255]})).collect::<Vec<_>>()});
    let mut d = document("vector", 1024, 1024, free);
    for i in 1..3 {
        let mut duplicate = d.items[0].clone();
        duplicate.id = format!("i{i}");
        d.items.push(duplicate);
    }
    assert_eq!(
        render::rasterize(&d, 1).err().unwrap().code,
        "RESOURCE_LIMIT"
    );
}

#[test]
fn field_and_layer_affine_transforms_compose_before_sampling() {
    for kind in ["vector", "raster"] {
        let mut paint = linear();
        paint["start"] = json!([0.25, 0.25]);
        paint["end"] = json!([2.25, 0.25]);
        paint["transform"] = json!([2, 0, 0, 2, 0, 0]);
        let mut shape = item(kind, 6, 2, paint);
        shape["parent"] = json!("g");
        let d = apply(
            &create(kind, 8, 8),
            json!([
                {"op":"add","item":{"id":"g","transform":[0,1,-1,0,5,1],"content":{"type":"group"}}},
                {"op":"add","item":shape}
            ]),
        );
        let p = render::rasterize(&d, 1).unwrap();
        for y in 0..8 {
            for x in 0..8 {
                let expected = if (3..5).contains(&x) && (1..7).contains(&y) {
                    let level = [0, 64, 128, 191, 255, 255][y - 1];
                    [level, level, level, 255]
                } else {
                    [0; 4]
                };
                assert_eq!(pixel(&p, x, y), expected);
            }
        }
        assert_eq!(
            inkbolt::scene::bounds(&d, 1).unwrap(),
            Some([3.0, 1.0, 5.0, 7.0])
        );
    }
}
