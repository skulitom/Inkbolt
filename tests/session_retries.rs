use inkbolt::{
    Document, Request, assets,
    control::{Control, Options},
    execute,
    model::Content,
    sessions::{self, Resources},
};
use serde_json::json;
use std::{
    fs,
    path::PathBuf,
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

static NEXT_ROOT: AtomicU64 = AtomicU64::new(0);

struct OwnedRoot(PathBuf);
impl OwnedRoot {
    fn new() -> Self {
        Self::at(
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
        )
    }

    fn at(timestamp: u128) -> Self {
        // Clock resolution does not guarantee uniqueness across parallel tests.
        // Keep exclusive creation, including when an earlier process left a root.
        for _ in 0..1024 {
            let path = std::env::temp_dir().join(format!(
                "inkbolt-retry-{}-{}-{}",
                std::process::id(),
                timestamp,
                NEXT_ROOT.fetch_add(1, Ordering::Relaxed)
            ));
            match fs::create_dir(&path) {
                Ok(()) => return Self(path),
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(error) => panic!("Cannot create owned retry fixture: {error}"),
            }
        }
        panic!("Cannot allocate an unused retry fixture root")
    }
}
impl Drop for OwnedRoot {
    fn drop(&mut self) {
        // This fixture creates only this one database; never recursively delete a computed path.
        let _ = fs::remove_file(self.0.join(format!("{}.sqlite3", assets::sha256(b"work"))));
        let _ = fs::remove_dir(&self.0);
    }
}

#[test]
fn retry_roots_remain_distinct_with_repeated_clock_values() {
    let roots = std::thread::scope(|scope| {
        let handles: Vec<_> = (0..16).map(|_| scope.spawn(|| OwnedRoot::at(0))).collect();
        handles
            .into_iter()
            .map(|handle| handle.join().unwrap())
            .collect::<Vec<_>>()
    });
    let paths: std::collections::HashSet<_> = roots.iter().map(|root| &root.0).collect();
    assert_eq!(paths.len(), roots.len());
    assert!(roots.iter().all(|root| root.0.is_dir()));
}

fn document() -> Document {
    let request: Request = serde_json::from_value(json!({"command":"document.create","id":"retry-input","kind":"vector","width":10,"height":10})).unwrap();
    let mut value = execute(request).unwrap();
    value["fonts"] = json!({"pinned":{"sha256":"a".repeat(64),"license_sha256":"b".repeat(64),"face_index":0,"bytes":100}});
    value["items"] = json!([{"id":"label","content":{"type":"text","frame":{"text":"A","width":10,"height":10,"style":{"font_id":"pinned","size":8,"fill":[0,0,0,255]}}}}]);
    serde_json::from_value(value).unwrap()
}

#[cfg(unix)]
#[test]
fn session_parent_aliases_preserve_library_retries_and_refuse_database_links() {
    use std::os::unix::fs::symlink;
    let root = OwnedRoot::new();
    let alias = root.0.join("directory-alias");
    symlink(&root.0, &alias).unwrap();
    let original = document();
    let resources = Resources::default();
    let first = sessions::create(
        &alias,
        "work",
        "create",
        &original,
        &resources,
        &Control::default(),
    )
    .unwrap();
    let replay = sessions::create(
        &root.0,
        "work",
        "create",
        &original,
        &resources,
        &Control::default(),
    )
    .unwrap();
    assert_eq!(first["receipt"], replay["receipt"]);
    assert_eq!(replay["replayed"], true);
    assert_eq!(
        sessions::read(&alias, "work", None).unwrap(),
        sessions::read(&root.0, "work", None).unwrap()
    );
    let database = sessions::store_path(&root.0, "work").unwrap();
    let bytes = fs::read(&database).unwrap();
    let preserved = root.0.join("original.sqlite3");
    fs::rename(&database, &preserved).unwrap();
    symlink(&preserved, &database).unwrap();
    assert_eq!(
        sessions::read(&alias, "work", None).unwrap_err().code,
        "SESSION_CORRUPT"
    );
    assert_eq!(fs::read(&preserved).unwrap(), bytes);
    fs::remove_file(&database).unwrap();
    fs::rename(&preserved, &database).unwrap();
    fs::remove_file(alias).unwrap();
}

#[test]
fn committed_creation_recovers_with_expired_control_but_rejects_nonfinite_typed_input() {
    let root = OwnedRoot::new();
    let original = document();
    let resources = Resources::default();
    let first = sessions::create(
        &root.0,
        "work",
        "create",
        &original,
        &resources,
        &Control::default(),
    )
    .unwrap();
    let expired = Control::new(&Options {
        timeout_ms: Some(0),
        cancel_file: None,
    })
    .unwrap();
    let repeated =
        sessions::create(&root.0, "work", "create", &original, &resources, &expired).unwrap();
    assert_eq!(repeated["receipt"], first["receipt"]);
    assert_eq!(repeated["replayed"], true);
    let mut invalid = original.clone();
    let Content::Text { frame } = &mut invalid.items[0].content else {
        panic!()
    };
    frame.leading = Some(f64::NAN);
    // JSON serializes optional nonfinite values like None: fingerprint equality alone is insufficient.
    assert_eq!(json!(invalid), json!(original));
    assert_eq!(
        sessions::create(
            &root.0,
            "work",
            "create",
            &invalid,
            &resources,
            &Control::default()
        )
        .unwrap_err()
        .code,
        "INVALID_DOCUMENT"
    );
    assert_eq!(
        sessions::read(&root.0, "work", None).unwrap()["current_revision"],
        0
    );
}

#[test]
fn ordinary_and_reviewed_action_retries_reject_optional_nonfinite_values() {
    let root = OwnedRoot::new();
    sessions::create(
        &root.0,
        "work",
        "create",
        &document(),
        &Resources::default(),
        &Control::default(),
    )
    .unwrap();
    let original:sessions::Action=serde_json::from_value(json!({"type":"edit","operations":[{"op":"properties","id":"label","name":"Reviewed name"}]})).unwrap();
    let mut invalid = original.clone();
    let sessions::Action::Edit { operations, .. } = &mut invalid else {
        panic!()
    };
    let inkbolt::edit::Operation::Properties { opacity, .. } = &mut operations[0] else {
        panic!()
    };
    *opacity = Some(f64::NAN);
    assert_eq!(json!(original), json!(invalid));
    let first = sessions::mutate(
        &root.0,
        "work",
        "ordinary",
        0,
        &original,
        &Control::default(),
    )
    .unwrap();
    assert_eq!(
        sessions::mutate(
            &root.0,
            "work",
            "ordinary",
            0,
            &invalid,
            &Control::default()
        )
        .unwrap_err()
        .code,
        "INVALID_REQUEST"
    );
    assert_eq!(
        sessions::receipt(&root.0, "work", "ordinary").unwrap()["receipt"],
        first["receipt"]
    );
    let result = sessions::dry_run(
        &root.0,
        "work",
        "reviewed",
        1,
        &original,
        &sessions::DryRunOptions::default(),
        &Control::default(),
    )
    .unwrap();
    let proposal: sessions::Proposal = serde_json::from_value(result["proposal"].clone()).unwrap();
    let committed =
        sessions::apply_proposal(&root.0, &proposal, &original, &Control::default()).unwrap();
    assert_eq!(
        sessions::apply_proposal(&root.0, &proposal, &invalid, &Control::default())
            .unwrap_err()
            .code,
        "INVALID_REQUEST"
    );
    assert_eq!(
        sessions::receipt(&root.0, "work", "reviewed").unwrap()["receipt"],
        committed["receipt"]
    );
    assert_eq!(
        sessions::read(&root.0, "work", None).unwrap()["current_revision"],
        2
    );
}
