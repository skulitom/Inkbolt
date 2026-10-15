use super::*;
use crate::{hdr::Encoding, sample_store::Candidate, samples::Channels};
use std::{
    fs,
    path::PathBuf,
    sync::atomic::{AtomicU64, Ordering},
};

struct Directory(PathBuf);
impl Directory {
    fn new() -> Self {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let path = std::env::temp_dir().join(format!(
            "inkbolt-pixel-test-{}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
}
impl Drop for Directory {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}

fn spec(depth: Depth, channels: Channels) -> Spec {
    Spec {
        width: 131,
        height: 133,
        depth,
        channels,
        encoding: if depth == Depth::F32 {
            Encoding::LinearSrgb
        } else {
            Encoding::EncodedSrgb
        },
    }
}

fn samples(spec: Spec) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(spec.byte_len().unwrap());
    for pixel in 0..spec.width as usize * spec.height as usize {
        for component in 0..spec.channels.count() {
            let n = pixel * spec.channels.count() + component;
            match spec.depth {
                Depth::U8 => bytes.push((n * 73 + 19) as u8),
                Depth::U16 => bytes.extend_from_slice(&((n * 7919 + 3571) as u16).to_le_bytes()),
                Depth::F32 => {
                    let words = [0x80000000_u32, 1, 0xc0000000, 0x40500000, 0x3f000001];
                    let word = if component == spec.channels.count() - 1 {
                        0x3f800000
                    } else {
                        words[n % words.len()]
                    };
                    bytes.extend_from_slice(&word.to_le_bytes());
                }
            }
        }
    }
    bytes
}

fn prepare(spec: Spec, bytes: &[u8], budget: &Budget, control: &Control) -> Prepared {
    let stride = spec.width as usize * spec.stride();
    Builder::from_rows(spec, budget, control, |y, row| {
        row.copy_from_slice(&bytes[y as usize * stride..(y as usize + 1) * stride]);
        Ok(())
    })
    .unwrap()
}

#[test]
fn private_rows_preserve_typed_edge_blocks_and_pure_candidate_identity() {
    let control = Control::default();
    for depth in [Depth::U8, Depth::U16, Depth::F32] {
        for channels in [Channels::GrayAlpha, Channels::Rgba] {
            let spec = spec(depth, channels);
            let bytes = samples(spec);
            let budget = Budget::new(bytes.len() as u64);
            let prepared = prepare(spec, &bytes, &budget, &control);
            let pure = Candidate::from_bytes(spec, &bytes, &control).unwrap();
            assert_eq!(prepared.manifest(), pure.manifest());
            let dir = Directory::new();
            let root = dir.0.join("blocks");
            let published = prepared.publish(&root, &control).unwrap();
            assert_eq!(published.created_tiles, 4);
            // Construct every final header and block independently of the importer.
            let mut index = 0;
            for y in (0..spec.height).step_by(128) {
                for x in (0..spec.width).step_by(128) {
                    let w = (spec.width - x).min(128);
                    let h = (spec.height - y).min(128);
                    let mut expected = b"INKTILE1".to_vec();
                    expected.extend_from_slice(&w.to_le_bytes());
                    expected.extend_from_slice(&h.to_le_bytes());
                    expected.extend_from_slice(&[
                        depth.bytes() as u8,
                        channels.count() as u8,
                        u8::from(depth == Depth::F32),
                        0,
                    ]);
                    for row in y..y + h {
                        let start =
                            (row as usize * spec.width as usize + x as usize) * spec.stride();
                        expected
                            .extend_from_slice(&bytes[start..start + w as usize * spec.stride()]);
                    }
                    let id = &published.manifest.tiles[index];
                    assert_eq!(assets::sha256(&expected), *id);
                    assert_eq!(
                        fs::read(root.join(format!("{id}.native-tile"))).unwrap(),
                        expected
                    );
                    index += 1;
                }
            }
            let paths: Vec<_> = published
                .manifest
                .tiles
                .iter()
                .map(|id| root.join(format!("{id}.native-tile")))
                .collect();
            let times: Vec<_> = paths
                .iter()
                .map(|p| fs::metadata(p).unwrap().modified().unwrap())
                .collect();
            let repeated = prepare(spec, &bytes, &budget, &control)
                .publish(&root, &control)
                .unwrap();
            assert_eq!(repeated.created_tiles, 0);
            assert_eq!(repeated.existing_tiles, 4);
            assert_eq!(
                times,
                paths
                    .iter()
                    .map(|p| fs::metadata(p).unwrap().modified().unwrap())
                    .collect::<Vec<_>>()
            );
            assert_eq!(pure.publish(&root, &control).unwrap().created_tiles, 0);
        }
    }
}

#[test]
fn scattered_rows_reject_overlap_holes_and_bounds_without_mutating_prior_samples() {
    let control = Control::default();
    let spec = Spec {
        width: 5,
        height: 2,
        ..spec(Depth::U8, Channels::GrayAlpha)
    };
    let budget = Budget::new(20);
    let mut target = Builder::new(spec, &budget, true, &control).unwrap();
    target.row(0, 0, 2, &[1, 2, 5, 6, 9, 10], &control).unwrap();
    assert!(target.row(1, 0, 1, &[21, 22, 23, 24], &control).is_err());
    assert!(target.row(4, 0, 1, &[21, 22, 23, 24], &control).is_err());
    target.row(1, 0, 2, &[3, 4, 7, 8], &control).unwrap();
    target
        .row(0, 1, 1, &[11, 12, 13, 14, 15, 16, 17, 18, 19, 20], &control)
        .unwrap();
    let prepared = target.finish(&control).unwrap();
    let pure = Candidate::from_bytes(spec, &(1..=20).collect::<Vec<_>>(), &control).unwrap();
    assert_eq!(prepared.manifest(), pure.manifest());
    drop(prepared);
    let mut hole = Builder::new(spec, &budget, true, &control).unwrap();
    hole.row(0, 0, 1, &[1, 2], &control).unwrap();
    assert!(hole.finish(&control).is_err());
    assert!(Builder::new(spec, &budget, true, &control).is_ok());
}

#[test]
fn planar_components_preserve_float_bits_and_validate_final_alpha() {
    let control = Control::default();
    let spec = Spec {
        width: 2,
        height: 1,
        ..spec(Depth::F32, Channels::Rgba)
    };
    let region = Region {
        x: 0,
        y: 0,
        width: 2,
        height: 1,
    };
    let budget = Budget::new(32);
    let mut target = Builder::new(spec, &budget, false, &control).unwrap();
    let planes = [
        [0x80000000_u32, 1],
        [0xc0000000, 0x40400000],
        [0x3f000001, 0x40800000],
    ];
    for (component, words) in planes.iter().enumerate().rev() {
        let row: Vec<_> = words.iter().flat_map(|v| v.to_le_bytes()).collect();
        target
            .components(region, component, 1, &row, true, &control)
            .unwrap();
    }
    let expected: Vec<_> = (0..2)
        .flat_map(|p| {
            [planes[0][p], planes[1][p], planes[2][p], 0x3f800000]
                .into_iter()
                .flat_map(u32::to_le_bytes)
        })
        .collect();
    let prepared = target.finish(&control).unwrap();
    assert_eq!(
        prepared.manifest(),
        Candidate::from_bytes(spec, &expected, &control)
            .unwrap()
            .manifest()
    );
    drop(prepared);
    let mut invalid = Builder::new(spec, &budget, false, &control).unwrap();
    invalid
        .components(
            region,
            3,
            1,
            &[2_f32.to_le_bytes(), 1_f32.to_le_bytes()].concat(),
            false,
            &control,
        )
        .unwrap();
    assert_eq!(
        invalid.finish(&control).err().unwrap().code,
        "UNSUPPORTED_SAMPLE_RANGE"
    );
}

#[test]
fn private_pixel_capacity_is_shared_and_released_after_failure_or_drop() {
    let control = Control::default();
    let dir = Directory::new();
    let budget = Budget::new(16);
    let mut encoded = Scratch::create(&dir.0, budget.clone(), &control).unwrap();
    encoded.allocate(8, &control).unwrap();
    let spec = Spec {
        width: 2,
        height: 1,
        ..spec(Depth::U8, Channels::Rgba)
    };
    let first = Builder::in_directory(spec, &budget, false, &dir.0, &control).unwrap();
    assert_eq!(
        Builder::in_directory(spec, &budget, false, &dir.0, &control)
            .err()
            .unwrap()
            .code,
        "RESOURCE_LIMIT"
    );
    drop(first);
    let second = Builder::in_directory(spec, &budget, false, &dir.0, &control).unwrap();
    drop(second);
    drop(encoded);
    assert_eq!(fs::read_dir(&dir.0).unwrap().count(), 0);
}

#[test]
fn late_row_failure_cancellation_and_staged_corruption_cannot_publish() {
    let control = Control::default();
    let spec = Spec {
        width: 2,
        height: 3,
        ..spec(Depth::U8, Channels::Rgba)
    };
    let bytes = samples(spec);
    let budget = Budget::new(bytes.len() as u64);
    for cancel in [false, true] {
        let current = Control::default();
        let result = Builder::from_rows(spec, &budget, &current, |y, row| {
            row.fill(3);
            if y == 2 {
                if cancel {
                    current.cancel();
                } else {
                    return Err(Error::new("SYNTHETIC", "late producer failure"));
                }
            }
            Ok(())
        });
        assert_eq!(
            result.err().unwrap().code,
            if cancel { "CANCELLED" } else { "SYNTHETIC" }
        );
    }
    let mut prepared = prepare(spec, &bytes, &budget, &control);
    prepared.data.scratch.write_at(0, &[255], &control).unwrap();
    let dir = Directory::new();
    let root = dir.0.join("untouched");
    assert_eq!(
        prepared.publish(&root, &control).unwrap_err().code,
        "SAMPLE_TILE_CORRUPT"
    );
    assert!(!root.exists());
    assert!(Builder::new(spec, &budget, false, &control).is_ok());
}
