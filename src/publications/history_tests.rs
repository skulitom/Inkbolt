use super::*;

fn execute(value: Value) -> Value {
    crate::execute(serde_json::from_value(value).unwrap()).unwrap()
}
fn fixture(root: &Path, kind: &str) -> PathBuf {
    execute(
        json!({"command":"session.create","session_root":root.join("source"),"session_id":"history","request_id":"create",
        "document":{"schema_version":2,"id":"original","kind":"vector","width":2,"height":2,"color_space":"srgb"}}),
    );
    let original = execute(
        json!({"command":"session.backup","session_root":root.join("source"),"session_id":"history","expected_revision":0,
        "output":{"output_root":root,"file_name":"source.sqlite3"}}),
    );
    let mut source = original["backup"].clone();
    if kind == "migrate" {
        let db = rusqlite::Connection::open(root.join("source.sqlite3")).unwrap();
        db.execute_batch("DROP TABLE lineage; PRAGMA user_version=1;")
            .unwrap();
        db.close().unwrap();
        source["sha256"] = json!(assets::sha256(
            &fs::read(root.join("source.sqlite3")).unwrap()
        ));
    }
    let mut request =
        json!({"command":format!("session.{kind}"),"session_id":"history","receipt":target(root)});
    let destination = if kind == "recover" {
        request["session_root"] = json!(root.join("restored"));
        request["source"] = source;
        crate::sessions::store_path(&root.join("restored"), "history").unwrap()
    } else {
        request["output"] = json!({"output_root":root,"file_name":"result.sqlite3"});
        if kind == "backup" {
            request["session_root"] = json!(root.join("source"));
            request["expected_revision"] = json!(0);
        } else {
            request["source"] = source;
            request["target_version"] = json!(2);
        }
        root.join("result.sqlite3")
    };
    fs::write(
        root.join("request.json"),
        serde_json::to_vec(&request).unwrap(),
    )
    .unwrap();
    destination
}

#[test]
fn history_creation_crashes_recover_without_recapturing_or_reopening_sources() {
    for kind in ["backup", "recover", "migrate"] {
        for point in [
            "before_record",
            "after_record",
            "before_publish",
            "after_publish",
            "after_complete",
        ] {
            let mut owned = Owned::new();
            let output = fixture(&owned.root, kind);
            owned.start(point, false);
            owned.kill();
            let published = ["after_publish", "after_complete"].contains(&point);
            assert_eq!(output.exists(), published, "{kind} {point}");
            if point != "before_record" {
                fs::remove_file(owned.root.join("source.sqlite3")).unwrap();
                fs::remove_file(
                    crate::sessions::store_path(&owned.root.join("source"), "history").unwrap(),
                )
                .unwrap();
            }
            let result = invoke(&owned.root, &Control::default()).unwrap();
            assert_eq!(result["publication"]["state"], "complete");
            assert_eq!(result["session"]["revision"], 0);
            assert_eq!(result["session"]["storage_version"], 2);
            let before = fs::read(&output).unwrap();
            let replay = recover(&target(&owned.root), &Control::default()).unwrap();
            assert_eq!(replay["session"], result["session"]);
            assert_eq!(fs::read(output).unwrap(), before);
        }
    }
}

#[test]
fn history_cancellation_uses_the_same_publication_boundary() {
    for kind in ["backup", "recover", "migrate"] {
        for point in [
            "before_record",
            "after_record",
            "before_publish",
            "after_publish",
            "after_complete",
        ] {
            let mut owned = Owned::new();
            let output = fixture(&owned.root, kind);
            owned.start(point, true);
            fs::write(owned.root.join("cancel"), b"stop").unwrap();
            owned.finish();
            assert_eq!(
                output.exists(),
                ["after_publish", "after_complete"].contains(&point)
            );
            assert_eq!(
                invoke(&owned.root, &Control::default()).unwrap()["publication"]["state"],
                "complete"
            );
        }
    }
}

#[test]
fn restoration_edited_before_completion_survives_worker_death_and_late_cancellation() {
    let mut owned = Owned::new();
    let output = fixture(&owned.root, "recover");
    owned.start("after_publish", false);
    // A genuine writer commits after restoration but before the receipt completes.
    execute(
        json!({"command":"session.apply","session_root":owned.root.join("restored"),"session_id":"history",
        "request_id":"newer","expected_revision":0,"action":{"type":"snapshot","name":"newer"}}),
    );
    let bytes = fs::read(&output).unwrap();
    owned.kill();
    let expired = Control::new(&crate::control::Options {
        timeout_ms: Some(0),
        cancel_file: None,
    })
    .unwrap();
    let result = invoke(&owned.root, &expired).unwrap();
    assert_eq!(
        result["session"]["revision"], 0,
        "Receipt describes original restoration"
    );
    assert_eq!(result["publication"]["state"], "complete");
    assert_eq!(
        fs::read(&output).unwrap(),
        bytes,
        "Newer history is never rolled back"
    );
    let current = execute(
        json!({"command":"session.verify","session_root":owned.root.join("restored"),"session_id":"history"}),
    );
    assert_eq!(current["revision"], 1);
    assert_eq!(current["snapshots"], 1);
}

#[test]
fn history_completion_write_failure_keeps_success_and_original_receipt() {
    for kind in ["backup", "recover", "migrate"] {
        let mut owned = Owned::new();
        let output = fixture(&owned.root, kind);
        // completion_error injects a real SQLite write failure, without pausing.
        owned.child = Some(
            Command::new(std::env::current_exe().unwrap())
                .args([
                    "--exact",
                    "publications::tests::receipt_worker",
                    "--nocapture",
                ])
                .env("INKBOLT_RECEIPT_FAULT", "completion_error")
                .env("INKBOLT_RECEIPT_TEST_ROOT", &owned.root)
                .env("INKBOLT_RECEIPT_TEST_CANCEL", "no")
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .unwrap(),
        );
        owned.finish();
        assert!(output.exists());
        assert_eq!(
            receipt(&target(&owned.root), &Control::default()).unwrap()["state"],
            "prepared"
        );
        assert_eq!(
            recover(&target(&owned.root), &Control::default()).unwrap()["publication"]["state"],
            "complete"
        );
    }
}
