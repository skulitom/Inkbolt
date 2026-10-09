//! Durable history creation receipts use streamed, already verified SQLite copies.
use super::*;
use crate::sessions::{backup, lineage};

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub(super) enum Kind {
    Backup,
    Restore,
    Migration,
}
impl Kind {
    pub(super) fn matches(self, record: &Record) -> bool {
        let receipt = &record.receipt;
        let identity = match self {
            Self::Backup | Self::Migration => &receipt["backup"],
            Self::Restore => &receipt["source"],
        };
        let path = match self {
            Self::Restore => &receipt["database"],
            _ => &identity["file_path"],
        };
        record.bytes > 0
            && path == &json!(record.target)
            && identity["bytes"] == record.bytes
            && identity["sha256"] == record.sha256
            && receipt["history_preserved"] == true
            && receipt["source_changed"] == false
            && receipt["migration_performed"] == (self == Self::Migration)
    }
}

fn publish(
    kind: Kind,
    inputs: Value,
    target: &ReceiptTarget,
    control: &Control,
    prepare: impl FnOnce() -> Result<backup::PreparedHistory, Error>,
) -> Result<Value, Error> {
    validate_target(target, control)?;
    let fingerprint = assets::sha256(
        &serde_json::to_vec(&json!({"kind":kind,"history":inputs}))
            .map_err(|_| corrupt("Unable to encode history publication inputs"))?,
    );
    if let Some(result) = existing(target, &fingerprint, control)? {
        return Ok(result);
    }
    control.check()?;
    let prepared = match prepare() {
        Ok(prepared) => prepared,
        Err(error) if error.code == "OUTPUT_EXISTS" => {
            return existing(target, &fingerprint, control)?.ok_or(error);
        }
        Err(error) => return Err(error),
    };
    // Link the owned verified temporary into the receipt's namespace. This adds
    // no second database copy or whole-file allocation; dropping preparation
    // releases its original name while this independently owned link survives.
    let mut stage = None;
    for _ in 0..64 {
        let path = prepared.target.parent().unwrap().join(format!(
            ".inkbolt-publication-{}-{}.tmp",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        checked_path(&path)?;
        match fs::hard_link(prepared.staging_path(), &path) {
            Ok(()) => {
                stage = Some(Stage {
                    path,
                    retain: false,
                });
                break;
            }
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {}
            Err(_) => return Err(io("History receipt requires create-only local hard links")),
        }
    }
    let stage = stage.ok_or_else(|| io("History receipt staging-name retry limit exceeded"))?;
    let file = regular(&stage.path)?;
    let record = Record {
        version: 2,
        history: Some(kind),
        request_id: target.request_id.clone(),
        fingerprint: fingerprint.clone(),
        phase: Phase::Prepared,
        target: prepared.target.clone(),
        staging_path: stage.path.clone(),
        file_identity: file_identity::identify(&file)?,
        bytes: prepared.identity.bytes,
        sha256: prepared.identity.sha256.clone(),
        receipt: prepared.receipt.clone(),
    };
    drop(file);
    drop(prepared);
    commit_prepared(target, &fingerprint, record, stage, control)
}

pub fn backup(
    root: &Path,
    id: &str,
    revision: u64,
    output: &backup::Output,
    target: &ReceiptTarget,
    control: &Control,
) -> Result<Value, Error> {
    publish(
        Kind::Backup,
        json!({"session_root":root,"session_id":id,"expected_revision":revision,"output":output}),
        target,
        control,
        || backup::prepare_backup(root, id, revision, output, control),
    )
}

pub fn restore(
    root: &Path,
    id: &str,
    source: &backup::Source,
    target: &ReceiptTarget,
    control: &Control,
) -> Result<Value, Error> {
    publish(
        Kind::Restore,
        json!({"session_root":root,"session_id":id,"source":source}),
        target,
        control,
        || backup::prepare_recovery(root, id, source, control),
    )
}

pub fn migrate(
    id: &str,
    source: &backup::Source,
    version: i64,
    output: &backup::Output,
    target: &ReceiptTarget,
    control: &Control,
) -> Result<Value, Error> {
    publish(
        Kind::Migration,
        json!({"session_id":id,"source":source,"target_version":version,"output":output}),
        target,
        control,
        || lineage::prepare_migration(id, source, version, output, control),
    )
}
