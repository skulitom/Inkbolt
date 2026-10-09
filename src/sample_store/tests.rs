use super::*;
#[cfg(windows)]
use std::{
    thread,
    time::{Duration, Instant},
};

static NEXT_TEST: AtomicU64 = AtomicU64::new(0);
struct Directory(PathBuf);
impl Directory {
    fn new() -> Self {
        let parent = std::env::temp_dir().canonicalize().unwrap();
        for _ in 0..64 {
            let root = parent.join(format!(
                "inkbolt-native-{}-{}",
                std::process::id(),
                NEXT_TEST.fetch_add(1, Ordering::Relaxed)
            ));
            match fs::create_dir(&root) {
                Ok(()) => return Self(root.canonicalize().unwrap()),
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => (),
                Err(e) => panic!("{e}"),
            }
        }
        panic!("Unable to reserve owned native-store test directory")
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
                .starts_with(&format!("inkbolt-native-{}-", std::process::id()))
        );
        let _ = fs::remove_dir_all(&self.0);
    }
}
fn spec(w: u32, h: u32) -> Spec {
    Spec {
        width: w,
        height: h,
        depth: Depth::U16,
        channels: Channels::Rgba,
        encoding: Encoding::EncodedSrgb,
    }
}
fn fixture(s: Spec) -> Vec<u8> {
    let mut bytes = Vec::new();
    for y in 0..s.height {
        for x in 0..s.width {
            for c in 0..s.channels.count() {
                let alpha = c == s.channels.count() - 1;
                let v = (x as usize * 7 + y as usize * 31 + c * 997) % 65536;
                match s.depth {
                    Depth::U8 => bytes.push(if alpha { 255 } else { v as u8 }),
                    Depth::U16 => bytes
                        .extend_from_slice(&(if alpha { 65535 } else { v as u16 }).to_le_bytes()),
                    Depth::F32 => bytes.extend_from_slice(
                        &(if alpha {
                            1.0f32
                        } else if s.encoding == Encoding::LinearSrgb {
                            v as f32 / 16384.0 - 2.0
                        } else {
                            v as f32 / 65535.0
                        })
                        .to_le_bytes(),
                    ),
                }
            }
        }
    }
    bytes
}
fn extract(s: Spec, bytes: &[u8], r: Region) -> Vec<u8> {
    let stride = s.channels.count() * s.depth.bytes();
    let mut result = Vec::new();
    for y in r.y..r.y + r.height {
        let offset = (y as usize * s.width as usize + r.x as usize) * stride;
        result.extend_from_slice(&bytes[offset..offset + r.width as usize * stride]);
    }
    result
}
fn check_every_sample(candidate: &Candidate, root: Option<&Path>, expected: &[u8]) {
    let s = candidate.manifest().spec;
    for y in (0..s.height).step_by(128) {
        for x in (0..s.width).step_by(128) {
            let region = Region {
                x,
                y,
                width: (s.width - x).min(128),
                height: (s.height - y).min(128),
            };
            assert_eq!(
                candidate
                    .read_region(root, region, &Control::default())
                    .unwrap(),
                extract(s, expected, region)
            );
        }
    }
}
fn files(root: &Path) -> BTreeMap<String, Vec<u8>> {
    if !root.exists() {
        return BTreeMap::new();
    }
    fs::read_dir(root)
        .unwrap()
        .map(|entry| {
            let entry = entry.unwrap();
            (
                entry.file_name().to_str().unwrap().to_owned(),
                fs::read(entry.path()).unwrap(),
            )
        })
        .collect()
}
fn independent_blob(s: Spec, bytes: &[u8], region: Region) -> Vec<u8> {
    let mut blob = b"INKTILE1".to_vec();
    blob.extend_from_slice(&region.width.to_le_bytes());
    blob.extend_from_slice(&region.height.to_le_bytes());
    blob.extend_from_slice(&[
        match s.depth {
            Depth::U8 => 1,
            Depth::U16 => 2,
            Depth::F32 => 4,
        },
        if s.channels == Channels::Rgba { 4 } else { 2 },
        match s.encoding {
            Encoding::EncodedSrgb => 0,
            Encoding::LinearSrgb => 1,
            Encoding::ProfiledRgb => 2,
        },
        0,
    ]);
    blob.extend_from_slice(&extract(s, bytes, region));
    blob
}

#[test]
fn native_types_edges_and_hdr_preserve_all_original_bits() {
    for depth in [Depth::U8, Depth::U16, Depth::F32] {
        for channels in [Channels::Rgba, Channels::GrayAlpha] {
            let encodings = if depth == Depth::F32 {
                vec![
                    Encoding::EncodedSrgb,
                    Encoding::LinearSrgb,
                    Encoding::ProfiledRgb,
                ]
            } else {
                vec![Encoding::EncodedSrgb, Encoding::ProfiledRgb]
            };
            for encoding in encodings {
                let s = Spec {
                    depth,
                    channels,
                    encoding,
                    ..spec(261, 259)
                };
                let bytes = fixture(s);
                let original = bytes.clone();
                let dir = Directory::new();
                let candidate = Candidate::from_bytes(s, &bytes, &Control::default()).unwrap();
                assert!(!dir.store().exists());
                check_every_sample(&candidate, None, &bytes);
                let published = candidate
                    .publish(&dir.store(), &Control::default())
                    .unwrap();
                assert_eq!(published.manifest.tiles.len(), 9);
                // The byte-depth pattern repeats across two diagonal full
                // tiles; the higher-depth fixtures keep all nine distinct.
                assert_eq!(
                    published.created_tiles,
                    if depth == Depth::U8 { 7 } else { 9 }
                );
                assert_eq!(published.existing_tiles, 0);
                let restored = Candidate::from_manifest(
                    serde_json::from_slice(&serde_json::to_vec(&published.manifest).unwrap())
                        .unwrap(),
                )
                .unwrap();
                assert_eq!(restored.pending_bytes(), 0);
                restored
                    .verify(Some(&dir.store()), &Control::default())
                    .unwrap();
                check_every_sample(&restored, Some(&dir.store()), &bytes);
                assert_eq!(
                    candidate
                        .publish(&dir.store(), &Control::default())
                        .unwrap()
                        .created_tiles,
                    0
                );
                assert_eq!(bytes, original);
            }
        }
    }
}

#[test]
fn canonical_files_and_ordered_manifest_have_independent_byte_identities() {
    let s = spec(129, 129);
    let bytes = fixture(s);
    let dir = Directory::new();
    let candidate = Candidate::from_bytes(s, &bytes, &Control::default()).unwrap();
    candidate
        .publish(&dir.store(), &Control::default())
        .unwrap();
    let regions = [
        Region {
            x: 0,
            y: 0,
            width: 128,
            height: 128,
        },
        Region {
            x: 128,
            y: 0,
            width: 1,
            height: 128,
        },
        Region {
            x: 0,
            y: 128,
            width: 128,
            height: 1,
        },
        Region {
            x: 128,
            y: 128,
            width: 1,
            height: 1,
        },
    ];
    let expected: Vec<_> = regions
        .into_iter()
        .map(|r| independent_blob(s, &bytes, r))
        .collect();
    let ids: Vec<_> = expected.iter().map(|b| assets::sha256(b)).collect();
    assert_eq!(candidate.manifest().tiles, ids);
    for (id, raw) in ids.iter().zip(&expected) {
        assert_eq!(
            fs::read(dir.store().join(format!("{id}.native-tile"))).unwrap(),
            *raw
        );
    }
    let mut identity = b"INKGRID1INKTILE1".to_vec();
    identity.extend_from_slice(&129u32.to_le_bytes());
    identity.extend_from_slice(&129u32.to_le_bytes());
    identity.extend_from_slice(&[2, 4, 0, 0]);
    identity.extend_from_slice(&128u32.to_le_bytes());
    for blob in &expected {
        identity.extend_from_slice(&Sha256::digest(blob));
    }
    assert_eq!(candidate.manifest().sha256, assets::sha256(&identity));
    let before = candidate.manifest().clone();
    for altered in 0..6 {
        let mut bad = before.clone();
        match altered {
            0 => bad.version = 2,
            1 => bad.spec.width -= 1,
            2 => bad.tiles.swap(0, 1),
            3 => bad.tiles[0] = "../other".to_owned(),
            4 => {
                bad.tiles.pop();
            }
            _ => bad.sha256 = "0".repeat(64),
        }
        assert!(Candidate::from_manifest(bad).is_err());
    }
}

#[test]
fn multi_megapixel_local_changes_share_blocks_and_keep_old_revisions_exact() {
    let s = spec(1920, 1080);
    let bytes = fixture(s);
    let dir = Directory::new();
    let original = Candidate::from_bytes(s, &bytes, &Control::default()).unwrap();
    let published = original.publish(&dir.store(), &Control::default()).unwrap();
    drop(original);
    let base = Candidate::from_manifest(published.manifest).unwrap();
    let before = files(&dir.store());
    let region = Region {
        x: 127,
        y: 127,
        width: 2,
        height: 2,
    };
    let replacement = [1u16, 2, 3, 65535]
        .into_iter()
        .flat_map(u16::to_le_bytes)
        .collect::<Vec<_>>()
        .repeat(4);
    let next = base
        .replace(
            Some(&dir.store()),
            region,
            &replacement,
            &Control::default(),
        )
        .unwrap();
    assert_eq!(
        files(&dir.store()),
        before,
        "Candidate preparation must not publish"
    );
    assert_eq!(base.pending_tiles(), 0);
    assert_eq!(next.pending_tiles(), 4);
    assert!(next.pending_bytes() <= 4 * (128 * 128 * 8 + 20));
    assert_eq!(
        next.read_region(None, region, &Control::default()).unwrap(),
        replacement
    );
    let changed: Vec<_> = base
        .manifest()
        .tiles
        .iter()
        .zip(&next.manifest().tiles)
        .enumerate()
        .filter(|(_, (a, b))| a != b)
        .map(|(i, _)| i)
        .collect();
    assert_eq!(changed, [0, 1, 15, 16]);
    let mut expected = bytes.clone();
    for row in 0..2 {
        let offset = ((127 + row) * 1920 + 127) * 8;
        expected[offset..offset + 16].copy_from_slice(&replacement[row * 16..row * 16 + 16]);
    }
    check_every_sample(&next, Some(&dir.store()), &expected);
    let saved = next.publish(&dir.store(), &Control::default()).unwrap();
    assert_eq!(saved.created_tiles, 4);
    for (name, data) in before {
        assert_eq!(fs::read(dir.store().join(name)).unwrap(), data);
    }
    check_every_sample(&base, Some(&dir.store()), &bytes);
    let loaded = Candidate::from_manifest(saved.manifest).unwrap();
    check_every_sample(&loaded, Some(&dir.store()), &expected);
    let no_op = loaded
        .replace(
            Some(&dir.store()),
            region,
            &replacement,
            &Control::default(),
        )
        .unwrap();
    assert_eq!(no_op.manifest(), loaded.manifest());
    assert_eq!(no_op.pending_tiles(), 0);
}

#[test]
fn repeated_blocks_deduplicate_and_pending_forks_remain_read_only() {
    let s = spec(256, 128);
    let bytes = [17u16, 18, 19, 65535]
        .into_iter()
        .flat_map(u16::to_le_bytes)
        .collect::<Vec<_>>()
        .repeat(256 * 128);
    let original = Candidate::from_bytes(s, &bytes, &Control::default()).unwrap();
    assert_eq!(original.pending_tiles(), 1);
    assert_eq!(original.manifest().tiles[0], original.manifest().tiles[1]);
    let r = Region {
        x: 129,
        y: 1,
        width: 1,
        height: 1,
    };
    let replacement = [4u16, 5, 6, 65535]
        .into_iter()
        .flat_map(u16::to_le_bytes)
        .collect::<Vec<_>>();
    let next = original
        .replace(None, r, &replacement, &Control::default())
        .unwrap();
    assert_eq!(next.pending_tiles(), 2);
    assert_eq!(
        original.read_region(None, r, &Control::default()).unwrap(),
        bytes[..8]
    );
    assert_eq!(
        next.read_region(None, r, &Control::default()).unwrap(),
        replacement
    );
    let dir = Directory::new();
    let first = original.publish(&dir.store(), &Control::default()).unwrap();
    assert_eq!(first.created_tiles, 1);
    assert_eq!(
        next.publish(&dir.store(), &Control::default())
            .unwrap()
            .created_tiles,
        1
    );
}

#[test]
fn corrupt_missing_and_wrong_type_dependencies_never_publish_or_replace_them() {
    let dir = Directory::new();
    let s = spec(129, 1);
    let source = Candidate::from_bytes(s, &fixture(s), &Control::default()).unwrap();
    source.publish(&dir.store(), &Control::default()).unwrap();
    let stored = Candidate::from_manifest(source.manifest().clone()).unwrap();
    let damaged = dir
        .store()
        .join(format!("{}.native-tile", stored.manifest().tiles[1]));
    let bad = b"corrupt original cache evidence";
    fs::write(&damaged, bad).unwrap();
    let r = Region {
        x: 0,
        y: 0,
        width: 1,
        height: 1,
    };
    assert!(
        stored
            .read_region(Some(&dir.store()), r, &Control::default())
            .is_ok()
    );
    assert_eq!(
        stored
            .verify(Some(&dir.store()), &Control::default())
            .unwrap_err()
            .code,
        "SAMPLE_TILE_CORRUPT"
    );
    assert_eq!(
        source
            .publish(&dir.store(), &Control::default())
            .unwrap_err()
            .code,
        "SAMPLE_TILE_CORRUPT"
    );
    let before = files(&dir.store());
    let changed = stored
        .replace(Some(&dir.store()), r, &[0; 8], &Control::default())
        .unwrap();
    assert_eq!(
        changed
            .publish(&dir.store(), &Control::default())
            .unwrap_err()
            .code,
        "SAMPLE_TILE_CORRUPT"
    );
    assert_eq!(files(&dir.store()), before);
    assert_eq!(fs::read(&damaged).unwrap(), bad);
    fs::remove_file(&damaged).unwrap();
    assert_eq!(
        stored
            .verify(Some(&dir.store()), &Control::default())
            .unwrap_err()
            .code,
        "SAMPLE_TILE_MISSING"
    );
    fs::create_dir(&damaged).unwrap();
    assert_eq!(
        stored
            .verify(Some(&dir.store()), &Control::default())
            .unwrap_err()
            .code,
        "SAMPLE_TILE_CORRUPT"
    );
    assert!(damaged.is_dir());
    assert_eq!(
        stored
            .read_region(None, r, &Control::default())
            .unwrap_err()
            .code,
        "SAMPLE_ROOT_REQUIRED"
    );
}

#[test]
fn invalid_ranges_nonfinite_samples_and_cancellation_leave_candidates_and_stores_untouched() {
    let s = Spec {
        depth: Depth::F32,
        ..spec(2, 2)
    };
    let bytes = fixture(s);
    let candidate = Candidate::from_bytes(s, &bytes, &Control::default()).unwrap();
    for value in [f32::NAN, f32::INFINITY, -0.1, 1.1] {
        let mut bad = bytes.clone();
        bad[..4].copy_from_slice(&value.to_le_bytes());
        assert!(Candidate::from_bytes(s, &bad, &Control::default()).is_err());
    }
    let linear = Spec {
        encoding: Encoding::LinearSrgb,
        ..s
    };
    let mut hdr = fixture(linear);
    hdr[..4].copy_from_slice(&(-f32::MAX).to_le_bytes());
    assert!(Candidate::from_bytes(linear, &hdr, &Control::default()).is_ok());
    hdr[12..16].copy_from_slice(&1.1f32.to_le_bytes());
    assert!(Candidate::from_bytes(linear, &hdr, &Control::default()).is_err());
    for region in [
        Region {
            x: 0,
            y: 0,
            width: 0,
            height: 1,
        },
        Region {
            x: u32::MAX,
            y: 0,
            width: 2,
            height: 1,
        },
    ] {
        assert!(
            candidate
                .replace(None, region, &[], &Control::default())
                .is_err()
        );
        assert!(
            candidate
                .read_region(None, region, &Control::default())
                .is_err()
        );
    }
    assert!(
        Spec {
            width: u32::MAX,
            ..s
        }
        .validate()
        .is_err()
    );
    assert!(spec(32768, 32768).validate().is_err());
    assert!(
        Spec {
            encoding: Encoding::LinearSrgb,
            ..spec(2, 2)
        }
        .validate()
        .is_err()
    );
    let dir = Directory::new();
    let cancelled = Control::default();
    cancelled.cancel();
    assert_eq!(
        candidate
            .publish(&dir.store(), &cancelled)
            .unwrap_err()
            .code,
        "CANCELLED"
    );
    assert!(!dir.store().exists());
    assert!(
        candidate
            .replace(
                None,
                Region {
                    x: 0,
                    y: 0,
                    width: 1,
                    height: 1
                },
                &bytes[..16],
                &cancelled
            )
            .is_err()
    );
    check_every_sample(&candidate, None, &bytes);
}

#[test]
fn binary32_subnormals_signed_zero_and_extreme_finite_radiance_keep_their_bits() {
    let s = Spec {
        depth: Depth::F32,
        encoding: Encoding::LinearSrgb,
        ..spec(2, 1)
    };
    let words = [
        1u32,
        0x8000_0000,
        0x7f7f_ffff,
        0x3f80_0000,
        0xff7f_ffff,
        0x8000_0001,
        0,
        1,
    ];
    let bytes: Vec<_> = words.into_iter().flat_map(u32::to_le_bytes).collect();
    let candidate = Candidate::from_bytes(s, &bytes, &Control::default()).unwrap();
    let dir = Directory::new();
    let published = candidate
        .publish(&dir.store(), &Control::default())
        .unwrap();
    check_every_sample(
        &Candidate::from_manifest(published.manifest).unwrap(),
        Some(&dir.store()),
        &bytes,
    );
}

#[test]
fn region_limits_and_workspace_roots_apply_before_any_publication() {
    let dir = Directory::new();
    let outside = Directory::new();
    let s = spec(512, 256);
    let source = Candidate::from_bytes(s, &fixture(s), &Control::default()).unwrap();
    let region = Region {
        x: 0,
        y: 0,
        width: 512,
        height: 256,
    };
    assert_eq!(
        source
            .read_region(None, region, &Control::default())
            .unwrap_err()
            .code,
        "RESOURCE_LIMIT"
    );
    assert!(
        source
            .replace(None, region, &[], &Control::default())
            .is_err()
    );
    let workspace = crate::workspace::Workspace::open(&dir.0).unwrap();
    let control = Control::default().in_workspace(Some(&workspace));
    assert_eq!(
        source.publish(&outside.store(), &control).unwrap_err().code,
        "PATH_OUTSIDE_WORKSPACE"
    );
    assert!(!outside.store().exists());
    assert_eq!(
        source
            .publish(Path::new("relative"), &control)
            .unwrap_err()
            .code,
        "INVALID_REQUEST"
    );
    source.publish(&dir.store(), &control).unwrap();
}

#[cfg(windows)]
pub(super) fn checkpoint(root: &Path, point: &str) {
    static HITS: AtomicU64 = AtomicU64::new(0);
    let Ok(expected) = std::env::var("INKBOLT_NATIVE_FAULT") else {
        return;
    };
    if expected != point {
        return;
    }
    let base = PathBuf::from(std::env::var_os("INKBOLT_NATIVE_TEST_ROOT").unwrap());
    if root != base.join("store") {
        return;
    }
    let occurrence: u64 = std::env::var("INKBOLT_NATIVE_OCCURRENCE")
        .unwrap()
        .parse()
        .unwrap();
    if HITS.fetch_add(1, Ordering::Relaxed) + 1 != occurrence {
        return;
    }
    let label = std::env::var("INKBOLT_NATIVE_WORKER").unwrap();
    fs::write(base.join(format!("ready-{label}")), point).unwrap();
    while !base.join(format!("release-{label}")).exists() {
        thread::sleep(Duration::from_millis(5));
    }
}

#[cfg(windows)]
#[test]
fn worker() {
    let Some(root) = std::env::var_os("INKBOLT_NATIVE_TEST_ROOT") else {
        return;
    };
    let root = PathBuf::from(root);
    let label = std::env::var("INKBOLT_NATIVE_WORKER").unwrap();
    let control = Control::new(&crate::control::Options {
        timeout_ms: None,
        cancel_file: Some(root.join("cancel")),
    })
    .unwrap();
    let bytes = fs::read(root.join("source.bin")).unwrap();
    let candidate = Candidate::from_bytes(spec(129, 1), &bytes, &control).unwrap();
    let result = match candidate.publish(&root.join("store"), &control) {
        Ok(value) => serde_json::json!({"ok":true,"result":value}),
        Err(error) => serde_json::json!({"ok":false,"code":error.code}),
    };
    fs::write(
        root.join(format!("result-{label}.json")),
        serde_json::to_vec(&result).unwrap(),
    )
    .unwrap();
}

#[cfg(windows)]
struct Workers {
    dir: Directory,
    children: Vec<std::process::Child>,
}
#[cfg(windows)]
impl Workers {
    fn new() -> Self {
        let dir = Directory::new();
        fs::write(dir.0.join("source.bin"), fixture(spec(129, 1))).unwrap();
        Self {
            dir,
            children: Vec::new(),
        }
    }
    fn spawn(&mut self, point: &str, occurrence: usize) -> usize {
        use std::os::windows::process::CommandExt;
        let label = self.children.len();
        let child = std::process::Command::new(std::env::current_exe().unwrap())
            .args(["--exact", "sample_store::tests::worker", "--nocapture"])
            .env("INKBOLT_NATIVE_TEST_ROOT", &self.dir.0)
            .env("INKBOLT_NATIVE_WORKER", label.to_string())
            .env("INKBOLT_NATIVE_FAULT", point)
            .env("INKBOLT_NATIVE_OCCURRENCE", occurrence.to_string())
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .creation_flags(0x08000000)
            .spawn()
            .unwrap();
        self.children.push(child);
        label
    }
    fn ready(&mut self, label: usize) {
        let deadline = Instant::now() + Duration::from_secs(20);
        while !self.dir.0.join(format!("ready-{label}")).exists() {
            assert!(
                self.children[label].try_wait().unwrap().is_none(),
                "Owned worker stopped before checkpoint"
            );
            assert!(
                Instant::now() < deadline,
                "Owned worker missed checkpoint deadline"
            );
            thread::sleep(Duration::from_millis(5));
        }
    }
    fn release(&self, label: usize) {
        fs::write(self.dir.0.join(format!("release-{label}")), b"release").unwrap();
    }
    fn finish(&mut self, label: usize) -> serde_json::Value {
        let deadline = Instant::now() + Duration::from_secs(20);
        loop {
            if let Some(status) = self.children[label].try_wait().unwrap() {
                assert!(status.success());
                break;
            }
            assert!(Instant::now() < deadline, "Owned worker did not finish");
            thread::sleep(Duration::from_millis(5));
        }
        serde_json::from_slice(&fs::read(self.dir.0.join(format!("result-{label}.json"))).unwrap())
            .unwrap()
    }
}
#[cfg(windows)]
impl Drop for Workers {
    fn drop(&mut self) {
        for child in &mut self.children {
            if child.try_wait().ok().flatten().is_none() {
                let _ = child.kill();
            }
            let _ = child.wait();
        }
    }
}

#[cfg(windows)]
#[test]
fn actual_process_death_retains_only_complete_tiles_and_retry_preserves_orphans() {
    for point in ["before_write", "before_publish", "after_publish"] {
        for occurrence in [1, 2] {
            let mut workers = Workers::new();
            let label = workers.spawn(point, occurrence);
            workers.ready(label);
            workers.children[label].kill().unwrap();
            workers.children[label].wait().unwrap();
            let before = files(&workers.dir.store());
            let complete = before
                .keys()
                .filter(|p| p.ends_with(".native-tile"))
                .count();
            assert_eq!(complete, occurrence - usize::from(point != "after_publish"));
            assert_eq!(before.keys().filter(|p| p.ends_with(".tmp")).count(), 1);
            assert!(!workers.dir.0.join(format!("result-{label}.json")).exists());
            let source = fs::read(workers.dir.0.join("source.bin")).unwrap();
            let candidate =
                Candidate::from_bytes(spec(129, 1), &source, &Control::default()).unwrap();
            let result = candidate
                .publish(&workers.dir.store(), &Control::default())
                .unwrap();
            assert_eq!(result.created_tiles, 2 - complete);
            for (name, bytes) in before {
                assert_eq!(fs::read(workers.dir.store().join(name)).unwrap(), bytes);
            }
            Candidate::from_manifest(result.manifest)
                .unwrap()
                .verify(Some(&workers.dir.store()), &Control::default())
                .unwrap();
            assert_eq!(fs::read(workers.dir.0.join("source.bin")).unwrap(), source);
        }
    }
}

#[cfg(windows)]
#[test]
fn cancellation_on_each_side_of_publication_and_competing_writers_preserve_outcomes() {
    for (point, occurrence, ok, complete) in [
        ("before_publish", 1, false, 0),
        ("after_publish", 1, false, 1),
        ("after_publish", 2, true, 2),
    ] {
        let mut workers = Workers::new();
        let label = workers.spawn(point, occurrence);
        workers.ready(label);
        fs::write(workers.dir.0.join("cancel"), b"cancel").unwrap();
        workers.release(label);
        let result = workers.finish(label);
        assert_eq!(result["ok"], ok);
        if !ok {
            assert_eq!(result["code"], "CANCELLED");
        }
        assert_eq!(
            files(&workers.dir.store())
                .keys()
                .filter(|p| p.ends_with(".native-tile"))
                .count(),
            complete
        );
        assert!(
            !files(&workers.dir.store())
                .keys()
                .any(|p| p.ends_with(".tmp"))
        );
    }
    let mut workers = Workers::new();
    let first = workers.spawn("before_publish", 1);
    workers.ready(first);
    let second = workers.spawn("before_publish", 1);
    workers.ready(second);
    workers.release(first);
    workers.release(second);
    let a = workers.finish(first);
    let b = workers.finish(second);
    assert_eq!(a["ok"], true);
    assert_eq!(b["ok"], true);
    assert_eq!(a["result"]["manifest"], b["result"]["manifest"]);
    assert_eq!(
        a["result"]["created_tiles"].as_u64().unwrap()
            + b["result"]["created_tiles"].as_u64().unwrap(),
        2
    );
    assert_eq!(files(&workers.dir.store()).len(), 2);

    let mut conflict = Workers::new();
    let label = conflict.spawn("before_publish", 1);
    conflict.ready(label);
    let source = fixture(spec(129, 1));
    let candidate = Candidate::from_bytes(spec(129, 1), &source, &Control::default()).unwrap();
    let target = conflict
        .dir
        .store()
        .join(format!("{}.native-tile", candidate.manifest().tiles[0]));
    fs::write(&target, b"foreign evidence created after preflight").unwrap();
    conflict.release(label);
    let result = conflict.finish(label);
    assert_eq!(result["ok"], false);
    assert_eq!(result["code"], "SAMPLE_TILE_CORRUPT");
    assert_eq!(
        fs::read(target).unwrap(),
        b"foreign evidence created after preflight"
    );
    assert_eq!(fs::read(conflict.dir.0.join("source.bin")).unwrap(), source);
}
