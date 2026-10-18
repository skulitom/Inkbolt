use super::*;
use crate::{
    control::Control,
    scalar_store::{Candidate, Spec},
    stored_scalars::Grid,
};
use serde_json::json;

fn fixture(w: u32, h: u32) -> Mask {
    let bytes: Vec<_> = (0..w * h)
        .map(|i| ((i * 71 + (i / w) * 13) % 256) as u8)
        .collect();
    serde_json::from_value(json!({"width":w,"height":h,"gray_hex":crate::render::hex(&bytes)}))
        .unwrap()
}
fn native(mask: &Mask) -> Mask {
    let mut result = mask.clone();
    result.native = Some(Grid::from_candidate(
        Candidate::from_bytes(
            Spec {
                width: mask.width,
                height: mask.height,
            },
            &crate::render::unhex(&mask.gray_hex),
            &Control::default(),
        )
        .unwrap(),
    ));
    result.gray_hex.clear();
    result
}
fn independent(mask: &Mask, local: Point) -> f64 {
    let bytes = crate::render::unhex(&mask.gray_hex);
    let r = mask.feather as i64;
    let at = |x: i64, y: i64| {
        let mut sum = 0.0;
        for dy in -r..=r {
            for dx in -r..=r {
                let (sx, sy) = (x + dx, y + dy);
                let v = if sx < 0 || sy < 0 || sx >= mask.width as i64 || sy >= mask.height as i64 {
                    f64::from(!mask.clip)
                } else {
                    let v = bytes[(sy * mask.width as i64 + sx) as usize] as f64 / 255.0;
                    if mask.invert { 1.0 - v } else { v }
                };
                sum += v * ((r + 1 - dx.abs()) * (r + 1 - dy.abs())) as f64;
            }
        }
        (1.0 - mask.density * (1.0 - sum / ((r + 1).pow(4) as f64))).clamp(0.0, 1.0)
    };
    if mask.sampling == Sampling::Nearest {
        return at(local[0].floor() as i64, local[1].floor() as i64);
    }
    let (x, y) = (local[0] - 0.5, local[1] - 0.5);
    let (ix, iy) = (x.floor() as i64, y.floor() as i64);
    let (fx, fy) = (x - ix as f64, y - iy as f64);
    at(ix, iy) * (1.0 - fx) * (1.0 - fy)
        + at(ix + 1, iy) * fx * (1.0 - fy)
        + at(ix, iy + 1) * (1.0 - fx) * fy
        + at(ix + 1, iy + 1) * fx * fy
}

#[test]
fn native_mask_controls_match_independent_infinite_field_and_historical_inline() {
    let control = Control::default();
    for feather in [0, 1, 4, 32] {
        for clip in [false, true] {
            for invert in [false, true] {
                for density in [0.0, 0.37, 1.0] {
                    for sampling in [Sampling::Nearest, Sampling::Bilinear] {
                        let mut mask = fixture(9, 7);
                        mask.feather = feather;
                        mask.clip = clip;
                        mask.invert = invert;
                        mask.density = density;
                        mask.sampling = sampling;
                        mask.linked = clip;
                        mask.transform = [0.8, 0.2, -0.1, 1.1, 2.0, 3.0];
                        let world = [1.2, -0.1, 0.3, 0.9, 4.0, 7.0];
                        let inline = prepare(&mask, world).unwrap();
                        let blocks = prepare_with_resources(
                            &native(&mask),
                            world,
                            None,
                            &control,
                            Default::default(),
                        )
                        .unwrap();
                        let [a, b, c, d, e, f] = mask.world_transform(world);
                        for p in [
                            [-40.5, -40.5],
                            [-1.75, 0.25],
                            [0.5, 0.5],
                            [4.25, 3.75],
                            [8.5, 6.5],
                            [9.5, 7.5],
                            [10.25, -0.75],
                        ] {
                            let mapped = [a * p[0] + c * p[1] + e, b * p[0] + d * p[1] + f];
                            let actual = blocks.sample(mapped).unwrap();
                            let old = inline.sample(mapped).unwrap();
                            assert_eq!(
                                actual.to_bits(),
                                old.to_bits(),
                                "{feather}/{clip}/{invert}/{density}/{sampling:?}/{p:?}"
                            );
                            assert!((actual - independent(&mask, p)).abs() < 2e-12);
                        }
                    }
                }
            }
        }
    }
}

#[test]
fn native_mask_short_tiles_and_two_pass_row_traversal_preserve_every_sample() {
    let control = Control::default();
    for feather in [0, 2] {
        let mut mask = fixture(257, 129);
        mask.feather = feather;
        mask.sampling = Sampling::Bilinear;
        mask.invert = true;
        mask.clip = false;
        mask.density = 0.73;
        let inline = prepare(&mask, identity()).unwrap();
        let blocks = prepare_with_resources(
            &native(&mask),
            identity(),
            None,
            &control,
            Default::default(),
        )
        .unwrap();
        for _ in 0..2 {
            for y in -4..134 {
                for x in -4..262 {
                    let point = [x as f64 + 0.25, y as f64 + 0.75];
                    assert_eq!(
                        blocks.sample(point).unwrap().to_bits(),
                        inline.sample(point).unwrap().to_bits()
                    );
                }
            }
        }
    }
}

#[test]
fn native_descriptor_is_exclusive_and_old_serialization_has_no_new_field() {
    let mask = fixture(3, 2);
    let old = serde_json::to_value(&mask).unwrap();
    assert!(old.get("native").is_none());
    let decoded: Mask = serde_json::from_value(old.clone()).unwrap();
    assert_eq!(serde_json::to_value(decoded).unwrap(), old);
    let blocks = native(&mask);
    assert_eq!(blocks.validate(identity()).unwrap(), 0);
    let roundtrip: Mask = serde_json::from_value(serde_json::to_value(&blocks).unwrap()).unwrap();
    assert_eq!(roundtrip, blocks);
    for variant in 0..3 {
        let mut invalid = blocks.clone();
        match variant {
            0 => invalid.gray_hex = "00".into(),
            1 => invalid.width += 1,
            _ => invalid.constant = true,
        }
        assert!(invalid.validate(identity()).is_err());
    }
    assert_eq!(
        prepare(&blocks, identity()).err().unwrap().code,
        "UNSUPPORTED_NATIVE_MASK"
    );
    let schema = serde_json::to_value(schemars::schema_for!(Mask)).unwrap();
    assert!(schema["$defs"].get("StoredScalarGrid").is_some());
    assert!(schema["$defs"].get("ScalarManifest").is_some());
}

#[test]
fn native_cached_sampling_observes_cancellation_with_bounded_latency() {
    let control = Control::default();
    let mask = native(&fixture(9, 7));
    let blocks =
        prepare_with_resources(&mask, identity(), None, &control, Default::default()).unwrap();
    blocks.sample([0.5, 0.5]).unwrap();
    control.cancel();
    let mut stopped = false;
    for _ in 0..crate::limits::control::PIXEL_CHECK_INTERVAL {
        match blocks.sample([0.5, 0.5]) {
            Ok(_) => (),
            Err(e) => {
                assert_eq!(e.code, "CANCELLED");
                stopped = true;
                break;
            }
        }
    }
    assert!(stopped);
    assert_eq!(
        prepare_with_resources(&mask, identity(), None, &control, Default::default())
            .err()
            .unwrap()
            .code,
        "CANCELLED"
    );
}
