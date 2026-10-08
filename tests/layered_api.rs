use base64::{Engine, engine::general_purpose::STANDARD};
use inkbolt::{Document, assets::ColorPolicy, control::Control, layered};
use serde_json::json;

#[test]
fn authored_and_constant_mask_planes_retain_controls_independently_of_color() {
    for constant in [false, true] {
        let document: Document = serde_json::from_value(json!({
            "schema_version":2,"id":"masks","kind":"raster","width":4,"height":2,"color_space":"srgb",
            "items":[{"id":"original","content":{"type":"raster","width":2,"height":1,"rgba_hex":"11dd6700be1f4f80"},
                "mask":{"constant":constant,"width":if constant{0}else{2},"height":if constant{0}else{1},
                    "gray_hex":if constant{""}else{"40ff"},"linked":false,"enabled":false,"clip":false,"density":128.0/255.0}}]
        })).unwrap();
        let before = document.clone();
        for version in [layered::Version::Standard, layered::Version::Large] {
            for compression in [layered::Compression::Raw, layered::Compression::Rle] {
                let artifact =
                    layered::export_versioned(&document, compression, version, &Control::default())
                        .unwrap();
                let bytes = STANDARD.decode(artifact["data"].as_str().unwrap()).unwrap();
                let reopened = layered::decode(
                    &bytes,
                    "reopened".into(),
                    ColorPolicy::RequireSrgb,
                    &Control::default(),
                )
                .unwrap();
                assert_eq!(
                    reopened["document"]["items"][0]["mask"],
                    serde_json::to_value(&document.items[0].mask).unwrap()
                );
                assert_eq!(
                    reopened["document"]["items"][0]["content"],
                    serde_json::to_value(&document.items[0].content).unwrap()
                );
                assert_eq!(
                    artifact["layered"]["layers"][0]["mask"]["constant"],
                    constant
                );
            }
        }
        assert_eq!(document, before);
    }
}

#[test]
fn nested_library_folders_use_raw_and_rle_without_changing_original_samples() {
    let document: Document = serde_json::from_value(json!({
        "schema_version":2,"id":"folders","kind":"raster","width":8,"height":4,
        "color_space":"srgb","items":[
            {"id":"pixel","parent":"folder","content":{"type":"raster","width":2,"height":1,"rgba_hex":"11dd6700be1f4f80"}},
            {"id":"folder","name":"retained","transform":[1,0,0,1,3,1],"content":{"type":"group","isolated":false}}
        ]
    })).unwrap();
    let before = document.clone();
    for version in [layered::Version::Standard, layered::Version::Large] {
        for compression in [layered::Compression::Raw, layered::Compression::Rle] {
            let encoded =
                layered::export_versioned(&document, compression, version, &Control::default())
                    .unwrap();
            let raw = STANDARD.decode(encoded["data"].as_str().unwrap()).unwrap();
            let decoded = layered::decode(
                &raw,
                "reopened".into(),
                ColorPolicy::RequireSrgb,
                &Control::default(),
            )
            .unwrap();
            assert_eq!(decoded["groups"], 1);
            assert_eq!(decoded["serialized_records"], 3);
            let items = decoded["document"]["items"].as_array().unwrap();
            assert_eq!(items[0]["content"]["rgba_hex"], "11dd6700be1f4f80");
            assert_eq!(items[0]["parent"], items[1]["id"]);
            assert_eq!(items[0]["transform"], json!([1.0, 0.0, 0.0, 1.0, 3.0, 1.0]));
            assert_eq!(items[1]["content"]["isolated"], false);
        }
    }
    assert_eq!(document, before);
}

#[test]
fn raw_and_row_compressed_library_delivery_keep_original_channels() {
    let document: Document = serde_json::from_value(json!({
        "schema_version":2,"id":"original","kind":"raster","width":3,"height":1,
        "color_space":"srgb","items":[{"id":"pixels","name":"original",
        "content":{"type":"raster","width":3,"height":1,
        "rgba_hex":"ff007f0011ee9980224466ff"}}]
    }))
    .unwrap();
    let before = document.clone();
    for compression in [layered::Compression::Raw, layered::Compression::Rle] {
        let artifact = layered::export(&document, compression, &Control::default()).unwrap();
        let bytes = STANDARD.decode(artifact["data"].as_str().unwrap()).unwrap();
        let reopened = layered::decode(
            &bytes,
            "reopened".into(),
            ColorPolicy::RequireSrgb,
            &Control::default(),
        )
        .unwrap();
        assert_eq!(
            reopened["document"]["items"][0]["content"],
            serde_json::to_value(&document.items[0].content).unwrap()
        );
    }
    assert_eq!(document, before);
}

#[test]
fn library_decode_enforces_its_own_file_bound_and_cancellation() {
    let oversized = vec![0; layered::MAX_FILE_BYTES + 1];
    let decode = |bytes: &[u8], control: &Control| {
        layered::decode(bytes, "bounded".into(), ColorPolicy::AssumeSrgb, control)
    };
    assert_eq!(
        decode(&oversized, &Control::default()).unwrap_err().code,
        "RESOURCE_LIMIT"
    );
    let control = Control::default();
    control.cancel();
    assert_eq!(decode(&[], &control).unwrap_err().code, "CANCELLED");
}

#[test]
fn large_library_framing_keeps_original_planes_and_cancellation() {
    let document: Document = serde_json::from_value(json!({
        "schema_version":2,"id":"large","kind":"raster","width":30001,"height":1,
        "color_space":"srgb","items":[{"id":"pixel","content":{"type":"raster",
        "width":1,"height":1,"rgba_hex":"28a03c01"}}]
    }))
    .unwrap();
    for compression in [layered::Compression::Raw, layered::Compression::Rle] {
        let value = layered::export_versioned(
            &document,
            compression,
            layered::Version::Large,
            &Control::default(),
        )
        .unwrap();
        let bytes = STANDARD.decode(value["data"].as_str().unwrap()).unwrap();
        assert_eq!(&bytes[4..6], &[0, 2]);
        let decoded = layered::decode(
            &bytes,
            "reopen".into(),
            ColorPolicy::RequireSrgb,
            &Control::default(),
        )
        .unwrap();
        assert_eq!(decoded["document"]["width"], 30001);
        assert_eq!(
            decoded["document"]["items"][0]["content"]["rgba_hex"],
            "28a03c01"
        );
    }
    let control = Control::default();
    control.cancel();
    assert_eq!(
        layered::export_versioned(
            &document,
            layered::Compression::Rle,
            layered::Version::Large,
            &control
        )
        .unwrap_err()
        .code,
        "CANCELLED"
    );
}
