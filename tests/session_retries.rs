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
    time::{SystemTime, UNIX_EPOCH},
};

struct OwnedRoot(PathBuf);
impl OwnedRoot {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "inkbolt-retry-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
}
impl Drop for OwnedRoot {
    fn drop(&mut self) {
        // This fixture creates only this one database; never recursively delete a computed path.
        let _ = fs::remove_file(self.0.join(format!("{}.sqlite3", assets::sha256(b"work"))));
        let _ = fs::remove_dir(&self.0);
    }
}

fn document() -> Document {
    let request: Request = serde_json::from_value(json!({"command":"document.create","id":"retry-input","kind":"vector","width":10,"height":10})).unwrap();
    let mut value = execute(request).unwrap();
    value["fonts"] = json!({"pinned":{"sha256":"a".repeat(64),"license_sha256":"b".repeat(64),"face_index":0,"bytes":100}});
    value["items"] = json!([{"id":"label","content":{"type":"text","frame":{"text":"A","width":10,"height":10,"style":{"font_id":"pinned","size":8,"fill":[0,0,0,255]}}}}]);
    serde_json::from_value(value).unwrap()
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
