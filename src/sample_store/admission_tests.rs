use super::*;
use crate::sample_store::admission::{Admission, Budget, LOCK_NAME, with_test_budget};
use std::{
    process::{Child, Command, Stdio},
    time::{Duration, Instant},
};

fn one(value: u16) -> Candidate {
    let bytes: Vec<u8> = [value, 123, 456, 65535]
        .into_iter()
        .flat_map(u16::to_le_bytes)
        .collect();
    Candidate::from_bytes(spec(1, 1), &bytes, &Control::default()).unwrap()
}
fn publish(
    candidate: &Candidate,
    root: &Path,
    bytes: u64,
    entries: usize,
) -> Result<Publication, Error> {
    with_test_budget(Budget { bytes, entries }, || {
        candidate.publish(root, &Control::default())
    })
}

#[test]
fn capacity_counts_unique_blocks_and_reserves_the_last_temporary_alias() {
    let dir = Directory::new();
    let store = dir.store();
    let s = spec(129, 1);
    let candidate = Candidate::from_bytes(s, &fixture(s), &Control::default()).unwrap();
    let required = (20 + 128 * 8) + (20 + 8) + (20 + 128 * 8);
    assert_eq!(
        publish(&candidate, &store, required - 1, 4)
            .unwrap_err()
            .code,
        "RESOURCE_LIMIT"
    );
    assert_eq!(
        files(&store),
        BTreeMap::from([(LOCK_NAME.to_owned(), Vec::new())])
    );
    assert_eq!(
        publish(&candidate, &store, required, 3).unwrap_err().code,
        "RESOURCE_LIMIT"
    );
    assert_eq!(
        publish(&candidate, &store, required, 4)
            .unwrap()
            .created_tiles,
        2
    );
    let original = files(&store);
    assert_eq!(original.len(), 3);
    assert_eq!(publish(&candidate, &store, 0, 0).unwrap().created_tiles, 0);
    assert_eq!(files(&store), original);

    let repeated = Directory::new();
    let s = spec(256, 128);
    let candidate =
        Candidate::from_bytes(s, &vec![0; s.byte_len().unwrap()], &Control::default()).unwrap();
    assert_eq!(candidate.manifest.tiles[0], candidate.manifest.tiles[1]);
    let result = publish(&candidate, &repeated.store(), 2 * (20 + 128 * 128 * 8), 3).unwrap();
    assert_eq!(result.created_tiles, 1);
    assert_eq!(result.existing_tiles, 0);
}

#[test]
fn capacity_counts_orphan_stages_and_aliases_without_removing_foreign_files() {
    let dir = Directory::new();
    let store = dir.store();
    fs::create_dir(&store).unwrap();
    fs::write(store.join(".inkbolt-native-old-1.tmp"), b"orphan").unwrap();
    fs::write(store.join("notes.txt"), vec![7; 1000]).unwrap();
    assert_eq!(
        publish(&one(1), &store, 61, 5).unwrap_err().code,
        "RESOURCE_LIMIT"
    );
    assert_eq!(
        publish(&one(1), &store, 62, 4).unwrap_err().code,
        "RESOURCE_LIMIT"
    );
    assert_eq!(publish(&one(1), &store, 62, 5).unwrap().created_tiles, 1);
    let before = files(&store);
    assert_eq!(
        publish(&one(2), &store, 62, 10).unwrap_err().code,
        "RESOURCE_LIMIT"
    );
    assert_eq!(files(&store), before);

    let alias = Directory::new();
    let store = alias.store();
    let original = one(4);
    original.publish(&store, &Control::default()).unwrap();
    fs::hard_link(
        store.join(format!("{}.native-tile", original.manifest.tiles[0])),
        store.join(".inkbolt-native-left.tmp"),
    )
    .unwrap();
    let before = files(&store);
    assert_eq!(
        publish(&one(5), &store, 111, 5).unwrap_err().code,
        "RESOURCE_LIMIT"
    );
    assert_eq!(files(&store), before);
    assert_eq!(publish(&one(5), &store, 112, 5).unwrap().created_tiles, 1);
    for (name, bytes) in before {
        assert_eq!(fs::read(store.join(name)).unwrap(), bytes);
    }
}

#[test]
fn foreign_coordination_files_are_preserved_and_reuse_never_waits_for_growth() {
    let dir = Directory::new();
    let store = dir.store();
    fs::create_dir(&store).unwrap();
    fs::write(store.join(LOCK_NAME), b"foreign evidence").unwrap();
    let before = files(&store);
    assert_eq!(
        one(1)
            .publish(&store, &Control::default())
            .unwrap_err()
            .code,
        "SAMPLE_STORE_IO"
    );
    assert_eq!(files(&store), before);
    let ready = Directory::new();
    let store = ready.store();
    let candidate = one(2);
    candidate.publish(&store, &Control::default()).unwrap();
    let before = files(&store);
    let held = Admission::acquire(&store, &Control::default()).unwrap();
    assert_eq!(publish(&candidate, &store, 0, 0).unwrap().created_tiles, 0);
    let control = Control::new(&crate::control::Options {
        timeout_ms: Some(30),
        ..Default::default()
    })
    .unwrap();
    assert_eq!(
        one(3).publish(&store, &control).unwrap_err().code,
        "TIMEOUT"
    );
    drop(held);
    assert_eq!(files(&store), before);
}

struct Worker(Child);
impl Drop for Worker {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}
fn wait_file(path: &Path) {
    let start = Instant::now();
    while !path.exists() {
        assert!(
            start.elapsed() < Duration::from_secs(15),
            "worker did not reach {}",
            path.display()
        );
        std::thread::sleep(Duration::from_millis(5));
    }
}
fn spawn(root: &Path, label: &str, mode: &str, value: u16) -> Worker {
    let child = Command::new(std::env::current_exe().unwrap())
        .args([
            "--exact",
            "sample_store::tests::admission_checks::worker",
            "--nocapture",
        ])
        .env("INKBOLT_NATIVE_ADMISSION_TEST_ROOT", root)
        .env("INKBOLT_NATIVE_ADMISSION_LABEL", label)
        .env("INKBOLT_NATIVE_ADMISSION_MODE", mode)
        .env("INKBOLT_NATIVE_ADMISSION_VALUE", value.to_string())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    let worker = Worker(child);
    wait_file(&root.join(format!("ready-{label}")));
    worker
}
fn finish(worker: &mut Worker, root: &Path, label: &str) -> serde_json::Value {
    let start = Instant::now();
    loop {
        if let Some(status) = worker.0.try_wait().unwrap() {
            assert!(status.success());
            break;
        }
        assert!(start.elapsed() < Duration::from_secs(15));
        std::thread::sleep(Duration::from_millis(5));
    }
    serde_json::from_slice(&fs::read(root.join(format!("outcome-{label}.json"))).unwrap()).unwrap()
}

#[test]
fn worker() {
    let Some(root) = std::env::var_os("INKBOLT_NATIVE_ADMISSION_TEST_ROOT") else {
        return;
    };
    let root = PathBuf::from(root);
    let label = std::env::var("INKBOLT_NATIVE_ADMISSION_LABEL").unwrap();
    let mode = std::env::var("INKBOLT_NATIVE_ADMISSION_MODE").unwrap();
    let control = Control::new(&crate::control::Options {
        timeout_ms: Some(10000),
        cancel_file: Some(root.join("cancel")),
    })
    .unwrap();
    let held = if mode == "hold" {
        Some(Admission::acquire(&root.join("store"), &control).unwrap())
    } else {
        None
    };
    fs::write(root.join(format!("ready-{label}")), b"ready").unwrap();
    if held.is_some() {
        // The parent terminates this owned process with the OS lock still held.
        wait_file(&root.join("release-owner"));
        drop(held);
        return;
    }
    wait_file(&root.join("start"));
    let value = std::env::var("INKBOLT_NATIVE_ADMISSION_VALUE")
        .unwrap()
        .parse()
        .unwrap();
    let result = with_test_budget(
        Budget {
            bytes: 56,
            entries: 3,
        },
        || one(value).publish(&root.join("store"), &control),
    );
    let outcome = match result {
        Ok(value) => serde_json::json!({"created":value.created_tiles}),
        Err(error) => serde_json::json!({"error":error.code}),
    };
    fs::write(
        root.join(format!("outcome-{label}.json")),
        serde_json::to_vec(&outcome).unwrap(),
    )
    .unwrap();
}

#[test]
fn competing_processes_share_capacity_and_identical_blocks_cost_only_once() {
    for same in [false, true] {
        let dir = Directory::new();
        fs::create_dir(dir.store()).unwrap();
        let mut first = spawn(&dir.0, "first", "publish", 1);
        let mut second = spawn(&dir.0, "second", "publish", if same { 1 } else { 2 });
        fs::write(dir.0.join("start"), b"start").unwrap();
        let results = [
            finish(&mut first, &dir.0, "first"),
            finish(&mut second, &dir.0, "second"),
        ];
        assert_eq!(
            results
                .iter()
                .filter_map(|r| r["created"].as_u64())
                .sum::<u64>(),
            1
        );
        assert_eq!(
            results.iter().filter(|r| r.get("error").is_some()).count(),
            usize::from(!same)
        );
        if !same {
            assert!(results.iter().any(|r| r["error"] == "RESOURCE_LIMIT"));
        }
        let actual = files(&dir.store());
        assert_eq!(actual.len(), 2);
        assert!(actual[LOCK_NAME].is_empty());
    }
}

#[test]
fn waiting_process_cancels_and_owner_termination_releases_the_os_lock() {
    for cancelled in [true, false] {
        let dir = Directory::new();
        fs::create_dir(dir.store()).unwrap();
        let mut owner = spawn(&dir.0, "owner", "hold", 1);
        let mut publisher = spawn(&dir.0, "publisher", "publish", 2);
        fs::write(dir.0.join("start"), b"start").unwrap();
        wait_file(&dir.0.join("waiting-publisher"));
        if cancelled {
            fs::write(dir.0.join("cancel"), b"cancel").unwrap();
            assert_eq!(
                finish(&mut publisher, &dir.0, "publisher")["error"],
                "CANCELLED"
            );
            // Windows also enforces the lock against reading the empty file.
            owner.0.kill().unwrap();
            owner.0.wait().unwrap();
            assert_eq!(
                files(&dir.store()),
                BTreeMap::from([(LOCK_NAME.to_owned(), Vec::new())])
            );
        } else {
            owner.0.kill().unwrap();
            owner.0.wait().unwrap();
            assert_eq!(finish(&mut publisher, &dir.0, "publisher")["created"], 1);
            Candidate::from_manifest(one(2).manifest)
                .unwrap()
                .verify(Some(&dir.store()), &Control::default())
                .unwrap();
        }
    }
}

#[test]
fn directory_entries_in_native_namespaces_are_not_followed_or_replaced() {
    for name in [
        LOCK_NAME,
        "foreign.native-tile",
        ".inkbolt-native-foreign.tmp",
    ] {
        let dir = Directory::new();
        let path = dir.store().join(name);
        fs::create_dir_all(&path).unwrap();
        fs::write(path.join("evidence"), b"preserved").unwrap();
        assert_eq!(
            one(1)
                .publish(&dir.store(), &Control::default())
                .unwrap_err()
                .code,
            "SAMPLE_STORE_IO"
        );
        assert_eq!(fs::read(path.join("evidence")).unwrap(), b"preserved");
        assert!(!fs::read_dir(dir.store()).unwrap().any(|e| {
            let path = e.unwrap().path();
            path.is_file() && path.extension().is_some_and(|ext| ext == "native-tile")
        }));
    }
}

#[cfg(unix)]
#[test]
fn symlink_entries_in_native_namespaces_preserve_the_external_target() {
    for name in [
        LOCK_NAME,
        "foreign.native-tile",
        ".inkbolt-native-foreign.tmp",
    ] {
        let dir = Directory::new();
        fs::create_dir(dir.store()).unwrap();
        let target = dir.0.join("external");
        fs::write(&target, b"").unwrap();
        let link = dir.store().join(name);
        std::os::unix::fs::symlink(&target, &link).unwrap();
        assert_eq!(
            one(1)
                .publish(&dir.store(), &Control::default())
                .unwrap_err()
                .code,
            "SAMPLE_STORE_IO"
        );
        assert_eq!(fs::read(&target).unwrap(), b"");
        assert_eq!(fs::read_link(&link).unwrap(), target);
    }
}
