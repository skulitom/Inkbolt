use super::*;
use crate::sample_store::{Candidate, Region, Spec};
use crate::samples::{Channels, Depth};
use std::{collections::BTreeMap, time::Instant};

fn original_bytes() -> Vec<u8> {
    (0..258u16)
        .flat_map(|i| {
            [i, 4321, 7654, 65535]
                .into_iter()
                .flat_map(u16::to_le_bytes)
        })
        .collect()
}

fn initial(root: &Path) -> Document {
    let spec = Spec {
        width: 129,
        height: 2,
        depth: Depth::U16,
        channels: Channels::Rgba,
        encoding: Default::default(),
    };
    let candidate = Candidate::from_bytes(spec, &original_bytes(), &Control::default()).unwrap();
    let asset_root = root.join("assets");
    let published = candidate.publish(&asset_root, &Control::default()).unwrap();
    let doc: Document = serde_json::from_value(json!({"schema_version":2,"id":"native","kind":"raster",
        "width":129,"height":2,"color_space":"srgb","items":[{"id":"pixels","content":{"type":"stored_samples",
        "grid":{"base":published.manifest}}}]})).unwrap();
    create(
        root,
        "native",
        "create",
        &doc,
        &Resources {
            asset_root: Some(asset_root),
            ..Default::default()
        },
        &Control::default(),
    )
    .unwrap();
    doc
}

fn action() -> Action {
    serde_json::from_value(json!({"type":"edit","operations":[
        {"op":"sample_storage_migrate","id":"pixels"},
        {"op":"sample_replace","id":"pixels","region":{"x":127,"y":0,"width":2,"height":2},
            "data_hex":"aabbccddeeffffff".repeat(4)}]}))
    .unwrap()
}

fn blocks(root: &Path) -> BTreeMap<PathBuf, Vec<u8>> {
    fs::read_dir(root.join("assets"))
        .unwrap()
        .map(|entry| {
            let path = entry.unwrap().path();
            let bytes = fs::read(&path).unwrap();
            (path, bytes)
        })
        .collect()
}

fn check_result(root: &Path, value: &Value) {
    let doc: Document = serde_json::from_value(value["document"].clone()).unwrap();
    let crate::model::Content::StoredSamples { grid } = &doc.items[0].content else {
        panic!("stored layer")
    };
    assert_eq!(grid.storage_version, 2);
    assert!(grid.staged.is_none());
    assert!(grid.patches.is_empty());
    let candidate = grid
        .prepare(Some(&root.join("assets")), &Control::default())
        .unwrap();
    let actual = candidate
        .read_region(
            Some(&root.join("assets")),
            Region {
                x: 0,
                y: 0,
                width: 129,
                height: 2,
            },
            &Control::default(),
        )
        .unwrap();
    let mut expected = original_bytes();
    for y in 0..2 {
        for x in 127..129 {
            expected[(y * 129 + x) * 8..(y * 129 + x + 1) * 8]
                .copy_from_slice(&[0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff, 0xff, 0xff]);
        }
    }
    assert_eq!(actual, expected);
    assert_eq!(
        verify(root, "native", &Control::default()).unwrap()["requests"],
        2
    );
}

#[test]
fn worker() {
    let Ok(point) = std::env::var("INKBOLT_SESSION_FAULT") else {
        return;
    };
    if !point.starts_with("native_") {
        return;
    }
    let root = PathBuf::from(std::env::var_os("INKBOLT_SESSION_FAULT_ROOT").unwrap());
    let control = if std::env::var_os("INKBOLT_SESSION_TEST_CANCEL").is_some() {
        Control::new(&crate::control::Options {
            cancel_file: Some(root.join("cancel")),
            ..Default::default()
        })
        .unwrap()
    } else {
        Control::default()
    };
    let result = mutate(&root, "native", "edit", 0, &action(), &control);
    let result = match result {
        Ok(value) => json!({"ok":value}),
        Err(error) => json!({"error":error}),
    };
    fs::write(
        root.join("outcome.json"),
        serde_json::to_vec(&result).unwrap(),
    )
    .unwrap();
}

#[test]
fn capacity_failure_preserves_history_and_retry_replays_without_capacity_or_blocks() {
    use crate::sample_store::admission::{Budget, with_test_budget};
    let root = tests::TestRoot::new();
    let original = initial(&root.0);
    let before = read(&root.0, "native", None).unwrap();
    let original_blocks = blocks(&root.0);
    let empty = Budget {
        bytes: 0,
        entries: 0,
    };
    let error = with_test_budget(empty, || {
        mutate(&root.0, "native", "edit", 0, &action(), &Control::default())
    })
    .unwrap_err();
    assert_eq!(error.code, "RESOURCE_LIMIT");
    assert_eq!(read(&root.0, "native", None).unwrap(), before);
    assert_eq!(capture(&root.0, "native", 0).unwrap().document, original);
    assert_eq!(blocks(&root.0), original_blocks);
    assert_eq!(
        receipt(&root.0, "native", "edit").unwrap_err().code,
        "REQUEST_NOT_FOUND"
    );
    assert_eq!(
        verify(&root.0, "native", &Control::default()).unwrap()["requests"],
        1
    );

    let committed = mutate(&root.0, "native", "edit", 0, &action(), &Control::default()).unwrap();
    check_result(&root.0, &committed);
    assert_eq!(capture(&root.0, "native", 0).unwrap().document, original);
    for (path, bytes) in original_blocks {
        assert_eq!(fs::read(path).unwrap(), bytes);
    }
    // Missing dependencies cannot cause a previously committed request to run again.
    for path in blocks(&root.0).keys() {
        if path.extension().is_some_and(|ext| ext == "native-tile") {
            fs::remove_file(path).unwrap();
        }
    }
    let remaining = blocks(&root.0);
    let replay = with_test_budget(empty, || {
        mutate(&root.0, "native", "edit", 0, &action(), &Control::default())
    })
    .unwrap();
    assert_eq!(replay["receipt"], committed["receipt"]);
    assert_eq!(replay["replayed"], true);
    assert_eq!(blocks(&root.0), remaining);
}

#[test]
fn interrupted_native_publication_and_commit_preserve_exact_history_and_retry() {
    for point in [
        "native_block_published",
        "native_before_commit",
        "native_after_commit",
    ] {
        let root = tests::TestRoot::new();
        let original = initial(&root.0);
        let before = read(&root.0, "native", None).unwrap();
        let original_blocks = blocks(&root.0);
        let mut child = tests::spawn(&root.0, point, false);
        child.0.kill().unwrap();
        child.0.wait().unwrap();
        let head = read(&root.0, "native", None).unwrap();
        if point == "native_after_commit" {
            assert_eq!(head["current_revision"], 1);
        } else {
            assert_eq!(head, before);
            assert_eq!(
                receipt(&root.0, "native", "edit").unwrap_err().code,
                "REQUEST_NOT_FOUND"
            );
        }
        for (path, bytes) in &original_blocks {
            assert_eq!(fs::read(path).unwrap(), *bytes);
        }
        let orphan_evidence = blocks(&root.0);
        let committed =
            mutate(&root.0, "native", "edit", 0, &action(), &Control::default()).unwrap();
        assert_eq!(committed["replayed"], point == "native_after_commit");
        check_result(&root.0, &committed);
        for (path, bytes) in orphan_evidence {
            assert_eq!(fs::read(path).unwrap(), bytes);
        }
        let old = capture(&root.0, "native", 0).unwrap().document;
        assert_eq!(old, original);
        let replay = mutate(&root.0, "native", "edit", 0, &action(), &Control::default()).unwrap();
        assert_eq!(replay["receipt"], committed["receipt"]);
        assert_eq!(replay["replayed"], true);
    }
}

#[test]
fn cancellation_before_and_after_native_commit_preserves_the_boundary() {
    for point in ["native_before_commit", "native_after_commit"] {
        let root = tests::TestRoot::new();
        initial(&root.0);
        let before = read(&root.0, "native", None).unwrap();
        let mut child = tests::spawn(&root.0, point, true);
        fs::write(root.0.join("cancel"), b"cancel").unwrap();
        fs::write(root.0.join("release"), b"release").unwrap();
        let start = Instant::now();
        loop {
            if let Some(status) = child.0.try_wait().unwrap() {
                assert!(status.success());
                break;
            }
            assert!(start.elapsed() < Duration::from_secs(20));
            std::thread::sleep(Duration::from_millis(5));
        }
        let result: Value =
            serde_json::from_slice(&fs::read(root.0.join("outcome.json")).unwrap()).unwrap();
        if point == "native_before_commit" {
            assert_eq!(result["error"]["code"], "CANCELLED");
            assert_eq!(read(&root.0, "native", None).unwrap(), before);
        } else {
            assert!(result.get("ok").is_some(), "{result}");
            check_result(&root.0, &result["ok"]);
        }
    }
}

#[test]
fn concurrent_native_writers_commit_one_revision_without_changing_original_blocks() {
    let root = tests::TestRoot::new();
    initial(&root.0);
    let originals = blocks(&root.0);
    let barrier = std::sync::Arc::new(std::sync::Barrier::new(2));
    let threads: Vec<_> = (0..2)
        .map(|index| {
            let root = root.0.clone();
            let barrier = barrier.clone();
            std::thread::spawn(move || {
                barrier.wait();
                mutate(
                    &root,
                    "native",
                    &format!("edit-{index}"),
                    0,
                    &action(),
                    &Control::default(),
                )
            })
        })
        .collect();
    let results: Vec<_> = threads.into_iter().map(|t| t.join().unwrap()).collect();
    assert_eq!(results.iter().filter(|r| r.is_ok()).count(), 1);
    let (loser, error) = results
        .iter()
        .enumerate()
        .find_map(|(index, result)| result.as_ref().err().map(|error| (index, error)))
        .unwrap();
    assert!(
        matches!(error.code, "SESSION_BUSY" | "REVISION_CONFLICT"),
        "{}",
        error.code
    );
    let committed = read(&root.0, "native", None).unwrap();
    let committed_blocks = blocks(&root.0);
    // The bounded lock wait may expire before the competing revision is visible.
    // Once both writers finish, the same request must observe that revision.
    assert_eq!(
        mutate(
            &root.0,
            "native",
            &format!("edit-{loser}"),
            0,
            &action(),
            &Control::default(),
        )
        .unwrap_err()
        .code,
        "REVISION_CONFLICT"
    );
    assert_eq!(read(&root.0, "native", None).unwrap(), committed);
    assert_eq!(blocks(&root.0), committed_blocks);
    assert_eq!(
        receipt(&root.0, "native", &format!("edit-{loser}"))
            .unwrap_err()
            .code,
        "REQUEST_NOT_FOUND"
    );
    check_result(
        &root.0,
        results.iter().find_map(|r| r.as_ref().ok()).unwrap(),
    );
    for (path, bytes) in originals {
        assert_eq!(fs::read(path).unwrap(), bytes);
    }
}
