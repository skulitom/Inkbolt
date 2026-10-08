use inkbolt::{
    Document, Request,
    assets::{self, ImageAsset, Storage},
    edit, execute,
    model::*,
    render, scene,
};
use serde_json::{Value, json};

const COLORS: [[u8; 4]; 6] = [
    [250, 20, 30, 255],
    [20, 240, 40, 255],
    [30, 40, 230, 255],
    [240, 210, 20, 255],
    [200, 20, 220, 128],
    [20, 210, 230, 255],
];
fn create(kind: &str, w: u32, h: u32) -> Document {
    serde_json::from_value(execute(serde_json::from_value::<Request>(json!({"command":"document.create","id":"image-fixture","kind":kind,"width":w,"height":h})).unwrap()).unwrap()).unwrap()
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
fn embedded(width: u32, height: u32, rgba: &[u8]) -> ImageAsset {
    ImageAsset {
        width,
        height,
        sha256: assets::identity(width, height, rgba),
        storage: Storage::Embedded {
            rgba_hex: render::hex(rgba),
        },
        provenance: None,
    }
}
fn fixture(kind: &str, placed: bool) -> Document {
    let d = create(kind, 8, 8);
    if placed {
        apply(
            &d,
            json!([{"op":"asset_put","id":"original","asset":embedded(3,2,&COLORS.concat())},{"op":"add","item":{"id":"pixels","content":{"type":"image","asset_id":"original","width":3,"height":2}}}]),
        )
    } else {
        apply(
            &d,
            json!([{"op":"add","item":{"id":"pixels","content":{"type":"raster","width":3,"height":2,"rgba_hex":render::hex(&COLORS.concat())}}}]),
        )
    }
}
fn pixel(p: &render::Rasterized, x: usize, y: usize) -> [u8; 4] {
    p.rgba[(y * p.width as usize + x) * 4..(y * p.width as usize + x + 1) * 4]
        .try_into()
        .unwrap()
}
fn assert_grid(d: &Document, x: usize, y: usize, rows: &[Vec<usize>]) {
    let output = render::rasterize(d, 1).unwrap();
    for py in 0..8 {
        for px in 0..8 {
            let expected =
                if py >= y && py < y + rows.len() && px >= x && px < x + rows[py - y].len() {
                    COLORS[rows[py - y][px - x]]
                } else {
                    [0; 4]
                };
            assert_eq!(pixel(&output, px, py), expected, "at {px},{py}");
        }
    }
}

#[test]
fn placed_and_inline_pixels_translate_scale_rotate_reflect_exactly() {
    for (kind, placed) in [("vector", true), ("raster", true), ("raster", false)] {
        let d = fixture(kind, placed);
        let original = serde_json::to_string(&d).unwrap();
        assert_grid(&d, 0, 0, &[vec![0, 1, 2], vec![3, 4, 5]]);
        let translated = apply(
            &d,
            json!([{"op":"transform","id":"pixels","matrix":[1,0,0,1,2,1]}]),
        );
        assert_grid(&translated, 2, 1, &[vec![0, 1, 2], vec![3, 4, 5]]);
        let scaled = apply(
            &d,
            json!([{"op":"transform","id":"pixels","matrix":[2,0,0,2,1,1]}]),
        );
        assert_grid(
            &scaled,
            1,
            1,
            &[
                vec![0, 0, 1, 1, 2, 2],
                vec![0, 0, 1, 1, 2, 2],
                vec![3, 3, 4, 4, 5, 5],
                vec![3, 3, 4, 4, 5, 5],
            ],
        );
        let rotated = apply(
            &d,
            json!([{"op":"transform","id":"pixels","matrix":[0,1,-1,0,4,1]}]),
        );
        assert_grid(&rotated, 2, 1, &[vec![3, 0], vec![4, 1], vec![5, 2]]);
        assert_eq!(
            scene::bounds(&rotated, 0).unwrap(),
            Some([2.0, 1.0, 4.0, 4.0])
        );
        let reflected = apply(
            &d,
            json!([{"op":"transform","id":"pixels","matrix":[-1,0,0,1,4,1]}]),
        );
        assert_grid(&reflected, 1, 1, &[vec![2, 1, 0], vec![5, 4, 3]]);
        assert_eq!(serde_json::to_string(&d).unwrap(), original);
        let restored: Document =
            serde_json::from_str(&serde_json::to_string(&rotated).unwrap()).unwrap();
        assert_eq!(restored, rotated);
    }
}

#[test]
fn anchors_off_canvas_and_local_world_composition_preserve_geometry() {
    for placed in [false, true] {
        let d = fixture("raster", placed);
        let moved = apply(
            &d,
            json!([{"op":"transform","id":"pixels","matrix":[1,0,0,1,2,2]}]),
        );
        let around = apply(
            &moved,
            json!([{"op":"transform","id":"pixels","matrix":[-1,0,0,-1,0,0],"space":"world","anchor":[3.5,3]}]),
        );
        assert_grid(&around, 2, 2, &[vec![5, 4, 3], vec![2, 1, 0]]);
        let off = apply(
            &d,
            json!([{"op":"transform","id":"pixels","matrix":[1,0,0,1,-1,1]}]),
        );
        assert_grid(&off, 0, 1, &[vec![1, 2], vec![4, 5]]);
        assert_eq!(scene::bounds(&off, 0).unwrap(), Some([-1.0, 1.0, 2.0, 3.0]));
        let grouped = apply(
            &d,
            json!([{"op":"group","ids":["pixels"],"new_id":"g"},{"op":"transform","id":"g","matrix":[0,1,-1,0,4,1]}]),
        );
        let local = apply(
            &grouped,
            json!([{"op":"transform","id":"pixels","matrix":[1,0,0,1,1,0],"space":"local"}]),
        );
        let world = apply(
            &grouped,
            json!([{"op":"transform","id":"pixels","matrix":[1,0,0,1,1,0],"space":"world"}]),
        );
        assert_grid(&local, 2, 2, &[vec![3, 0], vec![4, 1], vec![5, 2]]);
        assert_grid(&world, 3, 1, &[vec![3, 0], vec![4, 1], vec![5, 2]]);
        let local_anchor = apply(
            &grouped,
            json!([{"op":"transform","id":"pixels","matrix":[-1,0,0,-1,0,0],"space":"local","anchor":[1.5,1]}]),
        );
        assert_grid(&local_anchor, 2, 1, &[vec![2, 5], vec![1, 4], vec![0, 3]]);
    }
}

#[test]
fn premultiplied_bilinear_subpixel_sampling_avoids_transparent_color_fringes() {
    for placed in [false, true] {
        let d = create("raster", 4, 1);
        let rgba = [255, 0, 0, 255, 0, 0, 255, 0];
        let mut d = if placed {
            apply(
                &d,
                json!([{"op":"asset_put","id":"a","asset":embedded(2,1,&rgba)},{"op":"add","item":{"id":"pixels","content":{"type":"image","asset_id":"a","width":2,"height":1}}}]),
            )
        } else {
            apply(
                &d,
                json!([{"op":"add","item":{"id":"pixels","content":{"type":"raster","width":2,"height":1,"rgba_hex":render::hex(&rgba)}}}]),
            )
        };
        d = apply(
            &d,
            json!([{"op":"sampling","id":"pixels","sampling":"bilinear"},{"op":"transform","id":"pixels","matrix":[2,0,0,1,0,0]}]),
        );
        let p = render::rasterize(&d, 1).unwrap();
        for (x, expected) in [
            [255, 0, 0, 255],
            [255, 0, 0, 191],
            [255, 0, 0, 64],
            [0, 0, 0, 0],
        ]
        .iter()
        .enumerate()
        {
            assert_eq!(&pixel(&p, x, 0), expected);
        }
        let nearest = apply(
            &d,
            json!([{"op":"sampling","id":"pixels","sampling":"nearest"}]),
        );
        let n = render::rasterize(&nearest, 1).unwrap();
        assert_eq!(pixel(&n, 1, 0), [255, 0, 0, 255]);
        assert_eq!(pixel(&n, 2, 0), [0; 4]);
    }
    let d = create("raster", 4, 1);
    let d = apply(
        &d,
        json!([{"op":"add","item":{"id":"p","transform":[1,0,0,1,0.5,0],"content":{"type":"raster","width":2,"height":1,"rgba_hex":"ff0000ff00ff00ff","sampling":"bilinear"}}}]),
    );
    let p = render::rasterize(&d, 1).unwrap();
    assert_eq!(pixel(&p, 1, 0), [128, 128, 0, 255]);
    for (x, rgb) in [(0, [255, 0, 0]), (2, [0, 255, 0])] {
        let c = pixel(&p, x, 0);
        assert_eq!(&c[..3], &rgb);
        assert!((127..=128).contains(&c[3]));
    }
}

#[test]
fn crop_relink_asset_locks_and_failed_batches_keep_original_pixels() {
    let d = fixture("vector", true);
    let source = d.assets["original"].clone();
    let cropped = apply(
        &d,
        json!([{"op":"image","id":"pixels","asset_id":"original","width":4,"height":2,"crop":{"x":1,"y":1,"width":2,"height":1}}]),
    );
    assert_grid(&cropped, 0, 0, &[vec![4, 4, 5, 5], vec![4, 4, 5, 5]]);
    assert_eq!(cropped.assets["original"], source);
    let new = embedded(
        3,
        2,
        &[
            COLORS[5], COLORS[4], COLORS[3], COLORS[2], COLORS[1], COLORS[0],
        ]
        .concat(),
    );
    let relinked = apply(
        &d,
        json!([{"op":"asset_put","id":"replacement","asset":new},{"op":"image","id":"pixels","asset_id":"replacement","width":3,"height":2}]),
    );
    assert_grid(&relinked, 0, 0, &[vec![5, 4, 3], vec![2, 1, 0]]);
    assert_eq!(relinked.assets["original"], source);
    let locked = apply(
        &d,
        json!([{"op":"group","ids":["pixels"],"new_id":"g"},{"op":"properties","id":"g","locked":true}]),
    );
    for ops in [
        json!([{"op":"asset_put","id":"original","asset":new}]),
        json!([{"op":"image","id":"pixels","asset_id":"original","width":2,"height":2}]),
    ] {
        let ops = serde_json::from_value::<Vec<edit::Operation>>(ops).unwrap();
        assert_eq!(
            edit::apply(&locked, locked.revision, &ops)
                .unwrap_err()
                .code,
            "LOCKED"
        );
    }
    let before = serde_json::to_string(&d).unwrap();
    for (ops, code) in [
        (
            json!([{"op":"asset_remove","id":"original"}]),
            "ASSET_IN_USE",
        ),
        (
            json!([{"op":"asset_put","id":"replacement","asset":new},{"op":"image","id":"pixels","asset_id":"original","width":3,"height":2,"crop":{"x":2,"y":0,"width":2,"height":1}}]),
            "INVALID_DOCUMENT",
        ),
        (
            json!([{"op":"image","id":"pixels","asset_id":"missing","width":3,"height":2}]),
            "INVALID_DOCUMENT",
        ),
    ] {
        let ops = serde_json::from_value::<Vec<edit::Operation>>(ops).unwrap();
        assert_eq!(edit::apply(&d, d.revision, &ops).unwrap_err().code, code);
        assert_eq!(serde_json::to_string(&d).unwrap(), before);
    }
    let removed = apply(
        &d,
        json!([{"op":"remove","id":"pixels"},{"op":"asset_remove","id":"original"}]),
    );
    assert!(removed.assets.is_empty());
}

#[test]
fn invalid_asset_identity_and_total_decoded_storage_are_bounded() {
    let mut a = embedded(3, 2, &COLORS.concat());
    a.sha256 = "../invalid".into();
    assert_eq!(assets::validate(&a).unwrap_err().code, "INVALID_DOCUMENT");
    a.sha256 = "0".repeat(64);
    assert_eq!(assets::validate(&a).unwrap_err().code, "ASSET_CORRUPT");
    let mut d = create("vector", 1, 1);
    let a = ImageAsset {
        width: 4096,
        height: 4096,
        sha256: "0".repeat(64),
        storage: Storage::Stored,
        provenance: None,
    };
    d.assets.insert("a".into(), a.clone());
    validate(&d).unwrap();
    let shared = apply(
        &d,
        json!([
            {"op":"add","item":{"id":"one","content":{"type":"image","asset_id":"a","width":1,"height":1}}},
            {"op":"add","item":{"id":"two","content":{"type":"image","asset_id":"a","width":1,"height":1}}}
        ]),
    );
    assert_eq!(render::svg(&shared).unwrap_err().code, "RESOURCE_LIMIT");
    d.assets.insert("b".into(), a);
    assert_eq!(validate(&d).unwrap_err().code, "RESOURCE_LIMIT");
    let mut d = fixture("vector", true);
    d.assets.get_mut("original").unwrap().storage = Storage::Stored;
    let e = render::rasterize(&d, 1).err().unwrap();
    assert_eq!(e.code, "ASSET_ROOT_REQUIRED");
    assert_eq!(e.asset_id.as_deref(), Some("original"));
}
