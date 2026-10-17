use super::*;
use crate::control::Control;
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};

static NEXT: AtomicU64 = AtomicU64::new(0);
struct Directory(PathBuf);
impl Directory {
    fn new() -> Self {
        let parent = std::env::temp_dir().canonicalize().unwrap();
        for _ in 0..64 {
            let path = parent.join(format!(
                "inkbolt-scalar-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            match fs::create_dir(&path) {
                Ok(()) => return Self(path.canonicalize().unwrap()),
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => (),
                Err(e) => panic!("{e}"),
            }
        }
        panic!("Could not reserve scalar test directory")
    }
    fn store(&self) -> PathBuf {
        self.0.join("store")
    }
}
impl Drop for Directory {
    fn drop(&mut self) {
        assert_eq!(
            self.0.parent(),
            Some(std::env::temp_dir().canonicalize().unwrap().as_path())
        );
        assert!(
            self.0
                .file_name()
                .unwrap()
                .to_str()
                .unwrap()
                .starts_with(&format!("inkbolt-scalar-{}-", std::process::id()))
        );
        let _ = fs::remove_dir_all(&self.0);
    }
}
fn files(root: &Path) -> BTreeMap<String, Vec<u8>> {
    if !root.exists() {
        return BTreeMap::new();
    }
    fs::read_dir(root)
        .unwrap()
        .map(|e| {
            let e = e.unwrap();
            (
                e.file_name().to_str().unwrap().to_owned(),
                fs::read(e.path()).unwrap(),
            )
        })
        .collect()
}
fn value(x: u32, y: u32) -> u8 {
    let mut n = (y as u64 * 32768 + x as u64).wrapping_add(0x9e3779b97f4a7c15);
    n = (n ^ (n >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
    n = (n ^ (n >> 27)).wrapping_mul(0x94d049bb133111eb);
    (n ^ (n >> 31)) as u8
}
fn fixture(s: Spec) -> Vec<u8> {
    (0..s.height)
        .flat_map(|y| (0..s.width).map(move |x| value(x, y)))
        .collect()
}
fn header(w: u32, h: u32) -> Vec<u8> {
    [
        b"INKSCAL1".as_slice(),
        &w.to_le_bytes(),
        &h.to_le_bytes(),
        &[1, 1, 0, 0],
    ]
    .concat()
}
fn regions(s: Spec) -> impl Iterator<Item = Region> {
    (0..s.height).step_by(128).flat_map(move |y| {
        (0..s.width).step_by(128).map(move |x| Region {
            x,
            y,
            width: (s.width - x).min(128),
            height: (s.height - y).min(128),
        })
    })
}
fn extract(s: Spec, bytes: &[u8], r: Region) -> Vec<u8> {
    (r.y..r.y + r.height)
        .flat_map(|y| {
            let start = (y * s.width + r.x) as usize;
            bytes[start..start + r.width as usize].iter().copied()
        })
        .collect()
}
fn every_sample(c: &Candidate, root: Option<&Path>, expected: &[u8]) {
    let s = c.manifest().spec;
    for r in regions(s) {
        assert_eq!(
            c.read_region(root, r, &Control::default()).unwrap(),
            extract(s, expected, r)
        );
    }
}

#[test]
fn exact_coverage_files_and_manifest_match_independent_framing() {
    let control = Control::default();
    let s = Spec {
        width: 257,
        height: 131,
    };
    let bytes = fixture(s);
    let c = Candidate::from_bytes(s, &bytes, &control).unwrap();
    let rows = Candidate::from_rows(s, &control, |y, row| {
        row.copy_from_slice(&bytes[y as usize * 257..(y as usize + 1) * 257]);
        Ok(())
    })
    .unwrap();
    assert_eq!(c, rows);
    let transfer = c.transfer(c.pending_bytes(), &control).unwrap();
    let mut expected_files = BTreeMap::new();
    let mut hashes = Vec::new();
    let mut identity = Sha256::new();
    identity.update(b"INKSCGR1");
    identity.update(header(257, 131));
    identity.update(128u32.to_le_bytes());
    for r in regions(s) {
        let mut blob = header(r.width, r.height);
        blob.extend(extract(s, &bytes, r));
        let digest = Sha256::digest(&blob);
        identity.update(digest);
        let hash = format!("{digest:x}");
        expected_files.insert(format!("{hash}.native-tile"), blob);
        hashes.push(hash);
    }
    assert_eq!(c.manifest().tiles, hashes);
    assert_eq!(c.manifest().sha256, format!("{:x}", identity.finalize()));
    for block in &transfer.pending {
        assert_eq!(
            crate::render::unhex(&block.data_hex),
            expected_files[&format!("{}.native-tile", block.sha256)]
        );
    }
    let dir = Directory::new();
    let store = dir.store();
    c.verify(None, &control).unwrap();
    every_sample(&c, None, &bytes);
    assert!(!store.exists());
    let publication = c.publish(&store, &control).unwrap();
    assert_eq!(publication.created_tiles, 6);
    expected_files.insert(".inkbolt-native.lock".into(), vec![]);
    assert_eq!(files(&store), expected_files);
    let durable = Candidate::from_manifest(publication.manifest).unwrap();
    durable.verify(Some(&store), &control).unwrap();
    every_sample(&durable, Some(&store), &bytes);
    assert_eq!(durable.publish(&store, &control).unwrap().created_tiles, 0);
    assert_eq!(files(&store), expected_files);
}

#[test]
fn copy_on_write_transfer_preserves_old_states_and_disconnected_edits() {
    let control = Control::default();
    let s = Spec {
        width: 513,
        height: 259,
    };
    let original = fixture(s);
    let base = Candidate::from_bytes(s, &original, &control).unwrap();
    let dir = Directory::new();
    let store = dir.store();
    let base = Candidate::from_manifest(base.publish(&store, &control).unwrap().manifest).unwrap();
    let before = files(&store);
    let r = Region {
        x: 127,
        y: 127,
        width: 2,
        height: 2,
    };
    let next = base
        .replace(Some(&store), r, &[0, 1, 254, 255], &control)
        .unwrap();
    assert_eq!(next.pending_tiles(), 4);
    assert_eq!(
        next.replace(Some(&store), r, &[0, 1, 254, 255], &control)
            .unwrap(),
        next
    );
    let far = Region {
        x: 512,
        y: 258,
        width: 1,
        height: 1,
    };
    let next = next.replace(Some(&store), far, &[51], &control).unwrap();
    let encoded =
        serde_json::to_vec(&next.transfer(next.pending_bytes(), &control).unwrap()).unwrap();
    let transfer: Transfer = serde_json::from_slice(&encoded).unwrap();
    let restored = transfer.prepare(next.pending_bytes(), &control).unwrap();
    assert_eq!(restored, next);
    let mut expected = original.clone();
    for (x, y, v) in [
        (127, 127, 0),
        (128, 127, 1),
        (127, 128, 254),
        (128, 128, 255),
        (512, 258, 51),
    ] {
        expected[y * s.width as usize + x] = v;
    }
    every_sample(&restored, Some(&store), &expected);
    every_sample(&base, Some(&store), &original);
    assert_eq!(files(&store), before);
    restored.publish(&store, &control).unwrap();
    every_sample(&base, Some(&store), &original);
    for (name, bytes) in before {
        assert_eq!(fs::read(store.join(name)).unwrap(), bytes);
    }
    // Repeated immutable revisions do not accumulate a legacy patch limit.
    let mut revision = restored;
    for n in 0..300 {
        revision = revision
            .replace(Some(&store), far, &[(n % 256) as u8], &control)
            .unwrap();
    }
    assert_eq!(
        revision.read_region(Some(&store), far, &control).unwrap(),
        [43]
    );
    assert_eq!(revision.pending_tiles(), 5);
}

#[test]
fn malformed_transfers_and_cross_layout_substitution_are_rejected() {
    let control = Control::default();
    let s = Spec {
        width: 129,
        height: 1,
    };
    let c = Candidate::from_bytes(s, &fixture(s), &control).unwrap();
    let transfer = c.transfer(c.pending_bytes(), &control).unwrap();
    assert_eq!(
        transfer
            .prepare(c.pending_bytes() - 1, &control)
            .unwrap_err()
            .code,
        "RESOURCE_LIMIT"
    );
    for action in 0..8 {
        let mut t = transfer.clone();
        match action {
            0 => t.version += 1,
            1 => t.manifest.version += 1,
            2 => t.manifest.spec.width += 1,
            3 => t.pending.reverse(),
            4 => t.pending.push(t.pending[0].clone()),
            5 => t.pending[0].data_hex.make_ascii_uppercase(),
            6 => {
                t.pending[0].data_hex.pop();
            }
            _ => t.pending[0].data_hex.replace_range(0..2, "00"),
        }
        assert!(
            t.prepare(usize::MAX, &control).is_err(),
            "mutation {action}"
        );
    }
    let native_spec = sample_store::Spec {
        width: 129,
        height: 1,
        depth: crate::samples::Depth::U8,
        channels: crate::samples::Channels::GrayAlpha,
        encoding: Default::default(),
    };
    let native = sample_store::Candidate::from_bytes(native_spec, &vec![0; 258], &control).unwrap();
    let mut forged = transfer.clone();
    forged.manifest.tiles = native.manifest().tiles.clone();
    forged.manifest.sha256 = forged.manifest.identity();
    forged.pending = native
        .transfer(native.pending_bytes(), &control)
        .unwrap()
        .pending;
    assert!(forged.prepare(usize::MAX, &control).is_err());
    // Scalar manifest identity cannot be reused as an image manifest identity.
    let image = sample_store::Manifest {
        version: 1,
        spec: native_spec,
        tiles: transfer.manifest.tiles.clone(),
        sha256: transfer.manifest.sha256.clone(),
    };
    assert!(image.validate().is_err());
    let mut unrelated = transfer.clone();
    unrelated.pending[0].sha256 = "00".repeat(32);
    assert!(unrelated.prepare(usize::MAX, &control).is_err());
}

#[test]
fn missing_or_corrupt_unselected_dependencies_and_bad_roots_are_preserved() {
    let control = Control::default();
    let s = Spec {
        width: 257,
        height: 1,
    };
    let c = Candidate::from_bytes(s, &fixture(s), &control).unwrap();
    let dir = Directory::new();
    let store = dir.store();
    let durable = Candidate::from_manifest(c.publish(&store, &control).unwrap().manifest).unwrap();
    let r = Region {
        x: 0,
        y: 0,
        width: 1,
        height: 1,
    };
    assert_eq!(
        durable.read_region(None, r, &control).unwrap_err().code,
        "SAMPLE_ROOT_REQUIRED"
    );
    assert!(
        durable
            .read_region(Some(Path::new("relative")), r, &control)
            .is_err()
    );
    let last = store.join(format!("{}.native-tile", durable.manifest().tiles[2]));
    fs::remove_file(&last).unwrap();
    assert!(durable.read_region(Some(&store), r, &control).is_ok());
    assert_eq!(
        durable.verify(Some(&store), &control).unwrap_err().code,
        "SAMPLE_TILE_MISSING"
    );
    c.publish(&store, &control).unwrap();
    fs::write(&last, b"foreign bytes").unwrap();
    let before = files(&store);
    assert_eq!(
        durable.verify(Some(&store), &control).unwrap_err().code,
        "SAMPLE_TILE_CORRUPT"
    );
    assert_eq!(
        c.publish(&store, &control).unwrap_err().code,
        "SAMPLE_TILE_CORRUPT"
    );
    assert_eq!(files(&store), before);
}

#[test]
fn admission_cancellation_and_concurrent_publication_share_native_guards() {
    use crate::sample_store::admission::{Budget, with_test_budget};
    let control = Control::default();
    let s = Spec {
        width: 129,
        height: 1,
    };
    let c = Candidate::from_bytes(s, &fixture(s), &control).unwrap();
    let dir = Directory::new();
    let store = dir.store();
    // Two scalar blocks + one largest temporary alias + the persistent lock.
    let required = 148 + 21 + 148;
    assert_eq!(
        with_test_budget(
            Budget {
                bytes: required - 1,
                entries: 4
            },
            || c.publish(&store, &control)
        )
        .unwrap_err()
        .code,
        "RESOURCE_LIMIT"
    );
    assert_eq!(
        files(&store),
        BTreeMap::from([(".inkbolt-native.lock".into(), vec![])])
    );
    let results = std::thread::scope(|scope| {
        let first = scope.spawn(|| c.publish(&store, &control).unwrap());
        let second = scope.spawn(|| c.publish(&store, &control).unwrap());
        [first.join().unwrap(), second.join().unwrap()]
    });
    assert_eq!(results.iter().map(|r| r.created_tiles).sum::<usize>(), 2);
    assert_eq!(
        with_test_budget(
            Budget {
                bytes: 0,
                entries: 0
            },
            || c.publish(&store, &control)
        )
        .unwrap()
        .created_tiles,
        0
    );
    // Image and scalar publishers share one capacity ledger.
    let image = sample_store::Candidate::from_bytes(
        sample_store::Spec {
            width: 1,
            height: 1,
            depth: crate::samples::Depth::U8,
            channels: crate::samples::Channels::Rgba,
            encoding: Default::default(),
        },
        &[1, 2, 3, 255],
        &control,
    )
    .unwrap();
    assert_eq!(
        with_test_budget(
            Budget {
                bytes: 216,
                entries: 5
            },
            || image.publish(&store, &control)
        )
        .unwrap_err()
        .code,
        "RESOURCE_LIMIT"
    );
    assert_eq!(
        with_test_budget(
            Budget {
                bytes: 217,
                entries: 5
            },
            || image.publish(&store, &control)
        )
        .unwrap()
        .created_tiles,
        1
    );
    let before = files(&store);
    control.cancel();
    assert_eq!(c.publish(&store, &control).unwrap_err().code, "CANCELLED");
    assert_eq!(files(&store), before);
    let fresh = Control::default();
    let cancelled = Candidate::from_rows(s, &fresh, |_, _| {
        fresh.cancel();
        Ok(())
    });
    assert_eq!(cancelled.unwrap_err().code, "CANCELLED");
    assert_eq!(files(&store), before);
    assert!(
        Candidate::from_rows(s, &Control::default(), |_, _| Err(Error::new(
            "ORACLE",
            "producer error"
        )))
        .is_err()
    );
}

#[test]
fn scalar_bounds_and_schema_names_do_not_expand_image_interpretations() {
    for s in [
        Spec {
            width: 0,
            height: 1,
        },
        Spec {
            width: 1,
            height: u32::MAX,
        },
        Spec {
            width: 8193,
            height: 8192,
        },
        Spec {
            width: 1,
            height: 32769,
        },
    ] {
        assert!(s.validate().is_err());
    }
    let s = Spec {
        width: 8192,
        height: 8192,
    };
    assert_eq!(s.byte_len().unwrap(), 67_108_864);
    assert!(
        s.validate_region_bytes(
            Region {
                x: u32::MAX,
                y: 0,
                width: 2,
                height: 1
            },
            &[0; 2]
        )
        .is_err()
    );
    assert!(
        s.validate_region_bytes(
            Region {
                x: 0,
                y: 0,
                width: 257,
                height: 256
            },
            &[]
        )
        .is_err()
    );
    assert!(
        s.validate_region_bytes(
            Region {
                x: 0,
                y: 0,
                width: 0,
                height: 1
            },
            &[]
        )
        .is_err()
    );
    assert_eq!(Manifest::schema_name(), "ScalarManifest");
    assert_eq!(Transfer::schema_name(), "ScalarTransfer");
    assert_eq!(sample_store::Manifest::schema_name(), "Manifest");
    assert_eq!(sample_store::Transfer::schema_name(), "Transfer");
    let image_schema = serde_json::to_value(schemars::schema_for!(sample_store::Manifest)).unwrap();
    let scalar_schema = serde_json::to_value(schemars::schema_for!(Manifest)).unwrap();
    assert!(image_schema.to_string().contains("gray_alpha"));
    assert!(!scalar_schema.to_string().contains("gray_alpha"));
    assert_eq!(scalar_schema["additionalProperties"], false);
    assert!(
        serde_json::from_value::<Spec>(serde_json::json!({"width":1,"height":1,"depth":"u8"}))
            .is_err()
    );
    let caps = crate::execute(crate::Request::Capabilities {}).unwrap();
    let scalar = &caps["native_scalar_store_library"];
    assert_eq!(scalar["max_pixels"], 67_108_864);
    for key in [
        "document_integration",
        "mask_application",
        "selection_to_mask",
    ] {
        assert_eq!(scalar[key], false);
    }
    let native = &caps["native_sample_store_library"];
    for key in ["retained_edits", "block_edits"] {
        assert!(
            native[key]["operations"]
                .as_array()
                .unwrap()
                .contains(&serde_json::json!("repair"))
        );
    }
    assert!(
        native["unsupported"]
            .as_array()
            .unwrap()
            .contains(&serde_json::json!("native_mask_bake"))
    );
    assert!(
        !native["unsupported"]
            .as_array()
            .unwrap()
            .contains(&serde_json::json!("native_automatic_repair_and_mask_bake"))
    );
}

#[test]
fn fifty_megapixel_scalar_plane_retains_every_sample_through_private_edits() {
    let s = Spec {
        width: 8192,
        height: 6144,
    };
    let control = Control::default();
    let original = Candidate::from_rows(s, &control, |y, row| {
        for (x, v) in row.iter_mut().enumerate() {
            *v = value(x as u32, y);
        }
        Ok(())
    })
    .unwrap();
    assert_eq!(original.manifest().tiles.len(), 3072);
    assert_eq!(original.pending_bytes(), 50_331_648 + 3072 * 20);
    let region = Region {
        x: 4095,
        y: 3071,
        width: 2,
        height: 2,
    };
    let changed = original
        .replace(None, region, &[0, 85, 170, 255], &control)
        .unwrap();
    assert_eq!(
        changed
            .manifest()
            .tiles
            .iter()
            .zip(&original.manifest().tiles)
            .filter(|(a, b)| a != b)
            .count(),
        4
    );
    for r in regions(s) {
        let before = original.read_region(None, r, &control).unwrap();
        let after = changed.read_region(None, r, &control).unwrap();
        for y in 0..r.height {
            for x in 0..r.width {
                let (gx, gy) = (r.x + x, r.y + y);
                let i = (y * r.width + x) as usize;
                let expected = value(gx, gy);
                assert_eq!(before[i], expected);
                let edited = match (gx, gy) {
                    (4095, 3071) => 0,
                    (4096, 3071) => 85,
                    (4095, 3072) => 170,
                    (4096, 3072) => 255,
                    _ => expected,
                };
                assert_eq!(after[i], edited);
            }
        }
    }
}
