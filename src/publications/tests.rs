use super::*;
#[path = "history_tests.rs"]
mod history;
use std::{
    process::{Child, Command, Stdio},
    time::{Duration, Instant},
};

struct Owned {
    root: PathBuf,
    child: Option<Child>,
}
impl Owned {
    fn new() -> Self {
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "inkbolt-receipt-test-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        Self { root, child: None }
    }
    fn start(&mut self, point: &str, cancel: bool) {
        self.child = Some(
            Command::new(std::env::current_exe().unwrap())
                .args([
                    "--exact",
                    "publications::tests::receipt_worker",
                    "--nocapture",
                ])
                .env("INKBOLT_RECEIPT_FAULT", point)
                .env("INKBOLT_RECEIPT_TEST_ROOT", &self.root)
                .env(
                    "INKBOLT_RECEIPT_TEST_CANCEL",
                    if cancel { "yes" } else { "no" },
                )
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .unwrap(),
        );
        let started = Instant::now();
        while !self.root.join("ready").exists() {
            assert!(
                self.child.as_mut().unwrap().try_wait().unwrap().is_none(),
                "Worker exited before {point}"
            );
            assert!(
                started.elapsed() < Duration::from_secs(20),
                "Worker failed to reach {point}"
            );
            std::thread::sleep(Duration::from_millis(5));
        }
    }
    fn finish(&mut self) {
        fs::write(self.root.join("release"), b"release").unwrap();
        let started = Instant::now();
        loop {
            if let Some(status) = self.child.as_mut().unwrap().try_wait().unwrap() {
                assert!(status.success());
                break;
            }
            assert!(started.elapsed() < Duration::from_secs(20));
            std::thread::sleep(Duration::from_millis(5));
        }
    }
    fn kill(&mut self) {
        let child = self.child.as_mut().unwrap();
        child.kill().unwrap();
        child.wait().unwrap();
    }
}
impl Drop for Owned {
    fn drop(&mut self) {
        if let Some(child) = &mut self.child {
            let _ = child.kill();
            let _ = child.wait();
        }
        let base = std::env::temp_dir().canonicalize().unwrap();
        let root = self.root.canonicalize().unwrap();
        assert_eq!(root.parent(), Some(base.as_path()));
        assert!(
            root.file_name()
                .unwrap()
                .to_string_lossy()
                .starts_with("inkbolt-receipt-test-")
        );
        fs::remove_dir_all(root).unwrap();
    }
}
fn target(root: &Path) -> ReceiptTarget {
    ReceiptTarget {
        receipt_root: root.join("receipts"),
        request_id: "export".into(),
    }
}
fn request(root: &Path) -> crate::Request {
    if root.join("request.json").exists() {
        return serde_json::from_slice(&fs::read(root.join("request.json")).unwrap()).unwrap();
    }
    serde_json::from_value(json!({"command":"document.publish","document":{"schema_version":2,"id":"source","kind":"raster","width":2,"height":2,"color_space":"srgb"},
        "output":{"output_root":root,"file_name":"result.png","format":"png"},"receipt":target(root)})).unwrap()
}
fn invoke(root: &Path, control: &Control) -> Result<Value, Error> {
    crate::execute_controlled(request(root), control)
}
fn evidence(root: &Path) -> BTreeEvidence {
    fs::read_dir(root)
        .unwrap()
        .filter_map(|e| {
            let path = e.unwrap().path();
            path.file_name()
                .unwrap()
                .to_string_lossy()
                .starts_with(".inkbolt-publication-")
                .then(|| (path.clone(), fs::read(&path).unwrap()))
        })
        .collect()
}
type BTreeEvidence = std::collections::BTreeMap<PathBuf, Vec<u8>>;
#[test]
fn receipt_worker() {
    let Some(root) = std::env::var_os("INKBOLT_RECEIPT_TEST_ROOT") else {
        return;
    };
    let root = PathBuf::from(root);
    let cancel = std::env::var("INKBOLT_RECEIPT_TEST_CANCEL").unwrap() == "yes";
    let point = std::env::var("INKBOLT_RECEIPT_FAULT").unwrap();
    let control = Control::new(&crate::control::Options {
        timeout_ms: None,
        cancel_file: cancel.then(|| root.join("cancel")),
    })
    .unwrap();
    let result = invoke(&root, &control);
    if cancel && !["after_publish", "after_complete"].contains(&point.as_str()) {
        assert_eq!(result.unwrap_err().code, "CANCELLED");
    } else {
        let result = result.unwrap();
        assert_eq!(
            result["publication"]["state"],
            if point == "completion_error" {
                "completion_pending"
            } else {
                "complete"
            }
        );
    }
}
#[test]
fn process_death_at_every_receipt_and_publication_boundary_recovers_once() {
    for point in [
        "during_write",
        "before_record",
        "after_record",
        "before_publish",
        "after_publish",
        "after_complete",
    ] {
        let mut owned = Owned::new();
        owned.start(point, false);
        owned.kill();
        let published = ["after_publish", "after_complete"].contains(&point);
        assert_eq!(owned.root.join("result.png").exists(), published);
        let old = evidence(&owned.root);
        assert!(!old.is_empty());
        let saved = receipt(&target(&owned.root), &Control::default());
        if ["during_write", "before_record"].contains(&point) {
            assert_eq!(saved.unwrap_err().code, "PUBLICATION_NOT_FOUND");
        } else {
            assert_eq!(
                saved.unwrap()["state"],
                if point == "after_complete" {
                    "complete"
                } else {
                    "prepared"
                }
            );
        }
        let result = invoke(&owned.root, &Control::default()).unwrap();
        let data = fs::read(owned.root.join("result.png")).unwrap();
        assert_eq!(result["sha256"], assets::sha256(&data));
        assert_eq!(result["bytes"], data.len());
        assert_eq!(
            receipt(&target(&owned.root), &Control::default()).unwrap()["state"],
            "complete"
        );
        if ["during_write", "before_record", "after_complete"].contains(&point) {
            assert_eq!(
                evidence(&owned.root),
                old,
                "Unreferenced crash evidence is preserved"
            );
        } else {
            assert!(
                evidence(&owned.root).is_empty(),
                "Recovered completion cleans its identified staging link"
            );
        }
        assert_eq!(
            recover(&target(&owned.root), &Control::default()).unwrap()["sha256"],
            result["sha256"]
        );
        assert_eq!(fs::read(owned.root.join("result.png")).unwrap(), data);
    }
}
#[test]
fn cancellation_before_publication_is_retryable_and_late_cancellation_keeps_success() {
    for point in [
        "during_write",
        "before_record",
        "after_record",
        "before_publish",
        "after_publish",
        "after_complete",
    ] {
        let mut owned = Owned::new();
        owned.start(point, true);
        fs::write(owned.root.join("cancel"), b"stop").unwrap();
        owned.finish();
        let published = ["after_publish", "after_complete"].contains(&point);
        assert_eq!(owned.root.join("result.png").exists(), published);
        let captured = ["after_record", "before_publish"].contains(&point);
        assert_eq!(!evidence(&owned.root).is_empty(), captured);
        let result = invoke(&owned.root, &Control::default()).unwrap();
        assert_eq!(result["publication"]["state"], "complete");
        assert!(evidence(&owned.root).is_empty());
    }
}
#[test]
fn prepared_receipt_prevents_wrong_file_claim_and_serializes_competing_recovery() {
    let mut owned = Owned::new();
    owned.start("before_publish", false);
    assert_eq!(
        recover(&target(&owned.root), &Control::default())
            .unwrap_err()
            .code,
        "PUBLICATION_BUSY"
    );
    // Different bytes arrive while this writer is paused before the no-overwrite link.
    fs::write(owned.root.join("result.png"), b"unrelated").unwrap();
    owned.kill();
    assert_eq!(
        recover(&target(&owned.root), &Control::default())
            .unwrap_err()
            .code,
        "PUBLICATION_CONFLICT"
    );
    assert_eq!(
        fs::read(owned.root.join("result.png")).unwrap(),
        b"unrelated"
    );
    assert_eq!(
        receipt(&target(&owned.root), &Control::default()).unwrap()["state"],
        "prepared"
    );
}
#[test]
fn failed_completion_save_returns_published_success_with_explicit_recovery() {
    let mut owned = Owned::new();
    owned.child = Some(
        Command::new(std::env::current_exe().unwrap())
            .args([
                "--exact",
                "publications::tests::receipt_worker",
                "--nocapture",
            ])
            .env("INKBOLT_RECEIPT_TEST_ROOT", &owned.root)
            .env("INKBOLT_RECEIPT_FAULT", "completion_error")
            .env("INKBOLT_RECEIPT_TEST_CANCEL", "no")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap(),
    );
    owned.finish();
    assert!(owned.root.join("result.png").exists());
    assert_eq!(
        receipt(&target(&owned.root), &Control::default()).unwrap()["state"],
        "prepared"
    );
    let expired = Control::new(&crate::control::Options {
        timeout_ms: Some(0),
        cancel_file: None,
    })
    .unwrap();
    assert_eq!(
        recover(&target(&owned.root), &expired).unwrap()["publication"]["state"],
        "complete"
    );
}
#[test]
fn ledger_capacity_preserves_every_existing_receipt_and_replay() {
    let owned = Owned::new();
    invoke(&owned.root, &Control::default()).unwrap();
    let root = owned.root.join("receipts");
    let mut db = store::open(&root, false).unwrap().unwrap();
    let record = store::read(&db, "export").unwrap().unwrap();
    let tx = db.transaction().unwrap();
    for i in 1..MAX_RECORDS {
        let mut row = record.clone();
        row.request_id = format!("original-{i}");
        store::insert(&tx, &row).unwrap();
    }
    tx.commit().unwrap();
    drop(db);
    let before = fs::read(root.join("publications.sqlite3")).unwrap();
    let mut req = request(&owned.root);
    if let crate::Request::Publish {
        receipt: Some(target),
        output,
        ..
    } = &mut req
    {
        target.request_id = "overflow".into();
        output.file_name = "overflow.png".into();
    } else {
        panic!()
    }
    assert_eq!(crate::execute(req).unwrap_err().code, "PUBLICATION_LIMIT");
    assert!(!owned.root.join("overflow.png").exists());
    assert!(evidence(&owned.root).is_empty());
    assert_eq!(fs::read(root.join("publications.sqlite3")).unwrap(), before);
    assert_eq!(
        invoke(&owned.root, &Control::default()).unwrap()["publication"]["state"],
        "complete"
    );
}
#[test]
fn nonfinite_typed_retry_rejects_before_identity_validation() {
    let owned = Owned::new();
    let req = request(&owned.root);
    let crate::Request::Publish {
        document: doc,
        resources,
        mut output,
        receipt: Some(target),
        ..
    } = req
    else {
        panic!()
    };
    output.format = crate::ExportFormat::Jpeg;
    output.file_name = "result.jpg".into();
    output.image_options = Some(serde_json::from_value(json!({"matte":[255,255,255]})).unwrap());
    let result = document(&doc, &resources, &output, &target, &Control::default()).unwrap();
    let mut invalid = doc.clone();
    invalid.items = Vec::new();
    invalid.resolution_ppi = f64::NAN;
    assert_eq!(
        document(&invalid, &resources, &output, &target, &Control::default())
            .unwrap_err()
            .code,
        "INVALID_REQUEST"
    );
    assert_eq!(
        recover(&target, &Control::default()).unwrap()["sha256"],
        result["sha256"]
    );
}

#[test]
fn aggregate_receipt_budget_rejects_growth_without_evicting_existing_records() {
    let owned = Owned::new();
    invoke(&owned.root, &Control::default()).unwrap();
    let root = owned.root.join("receipts");
    let mut db = store::open(&root, false).unwrap().unwrap();
    let mut row = store::read(&db, "export").unwrap().unwrap();
    row.receipt["original_fixture_padding"] = json!("x".repeat(MAX_RECEIPT_BYTES - 4096));
    let payload_size = encode(&row).unwrap().len();
    assert!(payload_size < MAX_RECEIPT_BYTES);
    let tx = db.transaction().unwrap();
    let mut inserted = 0;
    loop {
        row.request_id = format!("bounded-{inserted}");
        match store::insert(&tx, &row) {
            Ok(()) => inserted += 1,
            Err(error) => {
                assert_eq!(error.code, "PUBLICATION_LIMIT");
                break;
            }
        }
    }
    assert!((63..MAX_RECORDS).contains(&inserted));
    tx.commit().unwrap();
    let total: i64 = db
        .query_row("SELECT SUM(length(payload)) FROM publications", [], |r| {
            r.get(0)
        })
        .unwrap();
    assert!(total <= MAX_LEDGER_BYTES as i64);
    assert!(total + payload_size as i64 > MAX_LEDGER_BYTES as i64);
    assert_eq!(
        store::read(&db, "export").unwrap().unwrap().phase,
        Phase::Complete
    );
    row.receipt["too_large"] = json!("y".repeat(8192));
    assert_eq!(encode(&row).unwrap_err().code, "RESOURCE_LIMIT");
}
