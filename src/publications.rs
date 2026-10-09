//! Durable prepared receipts and exact-file recovery for create-only publication.
mod file_identity;
mod store;
#[cfg(all(test, windows))]
mod tests;
use crate::{Document, Error, assets, control::Control, publish, sessions::Resources};
use rusqlite::TransactionBehavior;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    fs::{self, OpenOptions},
    io::{Read, Write},
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};

pub const MAX_RECEIPT_BYTES: usize = 1024 * 1024;
pub const MAX_LEDGER_BYTES: usize = 64 * 1024 * 1024;
pub const MAX_RECORDS: usize = 1024;
static NEXT: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ReceiptTarget {
    pub receipt_root: PathBuf,
    pub request_id: String,
}
fn io(message: &str) -> Error {
    Error::new("IO_ERROR", message)
}
fn corrupt(message: &str) -> Error {
    Error::new("PUBLICATION_CORRUPT", message)
}
fn checked_path(path: &Path) -> Result<(), Error> {
    assets::absolute(path)?;
    if path.as_os_str().len() > 4096 {
        return Err(crate::model::limit(
            "Publication path exceeds 4096 characters",
        ));
    }
    Ok(())
}
fn valid_hash(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
fn encode(value: &impl Serialize) -> Result<Vec<u8>, Error> {
    let bytes =
        serde_json::to_vec(value).map_err(|_| corrupt("Unable to encode publication receipt"))?;
    if bytes.len() > MAX_RECEIPT_BYTES {
        return Err(crate::model::limit(
            "Durable publication receipt exceeds 1 MiB",
        ));
    }
    Ok(bytes)
}
fn validate_target(target: &ReceiptTarget, control: &Control) -> Result<(), Error> {
    checked_path(&target.receipt_root)?;
    control.check_path(&target.receipt_root)?;
    if !crate::model::valid_id(&target.request_id) {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Publication request ID must use document ID syntax",
        ));
    }
    Ok(())
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
enum Phase {
    Prepared,
    Complete,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Record {
    version: u32,
    request_id: String,
    fingerprint: String,
    phase: Phase,
    target: PathBuf,
    staging_path: PathBuf,
    file_identity: file_identity::Identity,
    bytes: u64,
    sha256: String,
    receipt: Value,
}
impl Record {
    fn validate(&self, id: &str) -> Result<(), Error> {
        checked_path(&self.target).map_err(|_| corrupt("Invalid saved destination"))?;
        checked_path(&self.staging_path).map_err(|_| corrupt("Invalid saved staging path"))?;
        if self.version != 1
            || self.request_id != id
            || !crate::model::valid_id(id)
            || !valid_hash(&self.fingerprint)
            || !valid_hash(&self.sha256)
            || self.bytes > publish::MAX_OUTPUT_BYTES as u64
            || self.target.parent() != self.staging_path.parent()
            || self.target == self.staging_path
            || !self.staging_path.file_name().is_some_and(|s| {
                s.to_string_lossy().starts_with(".inkbolt-publication-")
                    && s.to_string_lossy().ends_with(".tmp")
            })
            || self.receipt["path"] != json!(self.target)
            || self.receipt["bytes"] != self.bytes
            || self.receipt["sha256"] != self.sha256
            || self.receipt["created"] != true
        {
            return Err(corrupt(
                "Publication receipt identity or payload is inconsistent",
            ));
        }
        Ok(())
    }
    fn result(&self, root: &Path, replayed: bool, complete: bool) -> Value {
        let mut result = self.receipt.clone();
        result["publication"] = json!({"receipt_root":root,"request_id":self.request_id,"replayed":replayed,
            "state":if complete{"complete"}else{"completion_pending"},"recovery_required":!complete});
        result
    }
}
struct Stage {
    path: PathBuf,
    retain: bool,
}
impl Stage {
    fn reserve(root: &Path, prefix: &str) -> Result<Self, Error> {
        for _ in 0..64 {
            let path = root.join(format!(
                "{prefix}{}-{}.tmp",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            checked_path(&path)?;
            match OpenOptions::new().create_new(true).write(true).open(&path) {
                Ok(_) => {
                    return Ok(Self {
                        path,
                        retain: false,
                    });
                }
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {}
                Err(_) => return Err(io("Unable to reserve publication staging file")),
            }
        }
        Err(io("Publication staging-name retry limit exceeded"))
    }
}
impl Drop for Stage {
    fn drop(&mut self) {
        if !self.retain {
            let _ = fs::remove_file(&self.path);
            let mut journal = self.path.as_os_str().to_owned();
            journal.push("-journal");
            let _ = fs::remove_file(PathBuf::from(journal));
        }
    }
}
fn regular(path: &Path) -> Result<fs::File, Error> {
    let meta = fs::symlink_metadata(path).map_err(|_| {
        Error::new(
            "PUBLICATION_EVIDENCE_MISSING",
            "Publication evidence is missing or inaccessible; existing outputs are preserved",
        )
    })?;
    if !meta.is_file() || meta.file_type().is_symlink() {
        return Err(corrupt(
            "Publication evidence must be a regular non-symlink file",
        ));
    }
    fs::File::open(path).map_err(|_| io("Unable to open publication evidence"))
}
fn verify_file(file: &mut fs::File, record: &Record, control: &Control) -> Result<(), Error> {
    if file
        .metadata()
        .map_err(|_| io("Unable to inspect prepared output"))?
        .len()
        != record.bytes
        || file_identity::identify(file)? != record.file_identity
    {
        return Err(Error::new(
            "PUBLICATION_CONFLICT",
            "File identity or length differs from the prepared publication; preserve the file and investigate",
        ));
    }
    let mut buffer = [0u8; 65536];
    let mut digest = Sha256::new();
    let mut bytes = 0;
    loop {
        control.check()?;
        let count = file
            .read(&mut buffer)
            .map_err(|_| io("Unable to verify prepared output"))?;
        if count == 0 {
            break;
        }
        bytes += count as u64;
        if bytes > record.bytes {
            return Err(Error::new(
                "PUBLICATION_CONFLICT",
                "Prepared output grew after validation",
            ));
        }
        digest.update(&buffer[..count]);
    }
    if bytes != record.bytes || format!("{:x}", digest.finalize()) != record.sha256 {
        return Err(Error::new(
            "PUBLICATION_CONFLICT",
            "Prepared output bytes differ from the durable receipt",
        ));
    }
    Ok(())
}
fn cleanup(record: &Record) {
    // Only remove this identified staging link, never a replacement or final path.
    if regular(&record.staging_path)
        .and_then(|f| file_identity::identify(&f))
        .ok()
        .as_ref()
        == Some(&record.file_identity)
    {
        let _ = fs::remove_file(&record.staging_path);
    }
}
fn resume_transaction(
    tx: rusqlite::Transaction<'_>,
    root: &Path,
    mut record: Record,
    replayed: bool,
    control: &Control,
) -> Result<Value, Error> {
    if record.phase == Phase::Complete {
        return Ok(record.result(root, true, true));
    }
    control.check_path(&record.target)?;
    control.check_path(&record.staging_path)?;
    // Retaining the staging link prevents file-ID reuse while a receipt is prepared.
    let mut stage = regular(&record.staging_path)?;
    let target_exists = match fs::symlink_metadata(&record.target) {
        Ok(_) => true,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => false,
        Err(_) => return Err(io("Unable to inspect publication destination")),
    };
    // Already-published work wins late cancellation. Verification remains bounded.
    let committed_control = Control::default();
    verify_file(
        &mut stage,
        &record,
        if target_exists {
            &committed_control
        } else {
            control
        },
    )?;
    if target_exists {
        let target = regular(&record.target)?;
        if file_identity::identify(&target)? != record.file_identity {
            return Err(Error::new(
                "PUBLICATION_CONFLICT",
                "Existing destination is not the staged file, even if its bytes match",
            ));
        }
    }
    let mut completed = record.clone();
    completed.phase = Phase::Complete;
    encode(&completed)?; // No new serialization/size decisions after publication.
    let complete_result = completed.result(root, replayed, true);
    let pending_result = completed.result(root, replayed, false);
    if !target_exists {
        #[cfg(test)]
        fault_point("before_publish");
        control.check()?;
        fs::hard_link(&record.staging_path, &record.target).map_err(|e| {
            if e.kind() == std::io::ErrorKind::AlreadyExists {
                Error::new(
                    "OUTPUT_EXISTS",
                    "Destination was created by another writer; it is preserved",
                )
            } else {
                io("Output root must support create-only hard links")
            }
        })?;
    }
    #[cfg(test)]
    fault_point("after_publish");
    // A completion-write failure cannot relabel published output as uncommitted.
    if store::complete(tx, &completed).is_err() {
        return Ok(pending_result);
    }
    record.phase = Phase::Complete;
    #[cfg(test)]
    fault_point("after_complete");
    drop(stage);
    cleanup(&record);
    Ok(complete_result)
}
fn existing(
    target: &ReceiptTarget,
    fingerprint: &str,
    control: &Control,
) -> Result<Option<Value>, Error> {
    let Some(mut db) = store::open(&target.receipt_root, false)? else {
        return Ok(None);
    };
    let tx = db
        .transaction_with_behavior(TransactionBehavior::Immediate)
        .map_err(store::sql)?;
    let Some(record) = store::read(&tx, &target.request_id)? else {
        return Ok(None);
    };
    if record.fingerprint != fingerprint {
        return Err(Error::new(
            "REQUEST_ID_REUSED",
            "Publication request ID was used with different inputs",
        ));
    }
    resume_transaction(tx, &target.receipt_root, record, true, control).map(Some)
}
fn publish_prepared(
    target: &ReceiptTarget,
    fingerprint: &str,
    control: &Control,
    prepare: impl FnOnce() -> Result<publish::PreparedOutput, Error>,
) -> Result<Value, Error> {
    validate_target(target, control)?;
    if let Some(result) = existing(target, fingerprint, control)? {
        return Ok(result);
    }
    control.check()?;
    let mut prepared = match prepare() {
        Ok(prepared) => prepared,
        Err(error) if error.code == "OUTPUT_EXISTS" => {
            return existing(target, fingerprint, control)?.ok_or(error);
        }
        Err(error) => return Err(error),
    };
    let mut stage = Stage::reserve(prepared.target.parent().unwrap(), ".inkbolt-publication-")?;
    let mut file = OpenOptions::new()
        .read(true)
        .write(true)
        .open(&stage.path)
        .map_err(|_| io("Unable to open publication staging file"))?;
    for chunk in prepared.bytes.chunks(65536) {
        control.check()?;
        file.write_all(chunk)
            .map_err(|_| io("Unable to write publication staging file"))?;
        #[cfg(test)]
        fault_point("during_write");
    }
    file.sync_all()
        .map_err(|_| io("Unable to flush publication staging file"))?;
    prepared.receipt["created"] = json!(true);
    let record = Record {
        version: 1,
        request_id: target.request_id.clone(),
        fingerprint: fingerprint.into(),
        phase: Phase::Prepared,
        target: prepared.target,
        staging_path: stage.path.clone(),
        file_identity: file_identity::identify(&file)?,
        bytes: prepared.bytes.len() as u64,
        sha256: assets::sha256(&prepared.bytes),
        receipt: prepared.receipt,
    };
    drop(file);
    record.validate(&target.request_id)?;
    encode(&record)?;
    #[cfg(test)]
    fault_point("before_record");
    control.check()?;
    let mut db = store::open(&target.receipt_root, true)?.unwrap();
    let tx = db
        .transaction_with_behavior(TransactionBehavior::Immediate)
        .map_err(store::sql)?;
    if let Some(old) = store::read(&tx, &target.request_id)? {
        if old.fingerprint != fingerprint {
            return Err(Error::new(
                "REQUEST_ID_REUSED",
                "Publication request ID was used with different inputs",
            ));
        }
        return resume_transaction(tx, &target.receipt_root, old, true, control);
    }
    store::insert(&tx, &record)?;
    control.check()?;
    // Commit failure can have an uncertain durable outcome. Preserve the evidence.
    stage.retain = true;
    tx.commit().map_err(store::sql)?;
    #[cfg(test)]
    fault_point("after_record");
    let tx = db
        .transaction_with_behavior(TransactionBehavior::Immediate)
        .map_err(store::sql)?;
    // Another caller can recover between recording and reacquiring the writer lock.
    let current = store::read(&tx, &target.request_id)?
        .ok_or_else(|| corrupt("Prepared receipt disappeared"))?;
    resume_transaction(tx, &target.receipt_root, current, false, control)
}
pub fn document(
    document: &Document,
    resources: &Resources,
    options: &publish::Options,
    target: &ReceiptTarget,
    control: &Control,
) -> Result<Value, Error> {
    crate::finite::check(&(document, resources, options))?;
    crate::model::validate(document)?;
    resources.validate()?;
    publish::destination(options)?;
    let fingerprint = assets::sha256(
        &serde_json::to_vec(
            &json!({"kind":"document","document":document,"resources":resources,"output":options}),
        )
        .map_err(|_| corrupt("Unable to encode publication inputs"))?,
    );
    publish_prepared(target, &fingerprint, control, || {
        publish::prepare_publication(document, resources, options, control)
    })
}
pub fn session(
    root: &Path,
    id: &str,
    revision: u64,
    options: &publish::Options,
    target: &ReceiptTarget,
    control: &Control,
) -> Result<Value, Error> {
    crate::finite::check(options)?;
    crate::sessions::store_path(root, id)?;
    publish::destination(options)?;
    let fingerprint=assets::sha256(&serde_json::to_vec(&json!({"kind":"session","session_root":root,"session_id":id,"expected_revision":revision,"output":options})).map_err(|_|corrupt("Unable to encode publication inputs"))?);
    publish_prepared(target, &fingerprint, control, || {
        let state = crate::sessions::capture_head(root, id, revision, control)?;
        let mut prepared =
            publish::prepare_publication(&state.document, &state.resources, options, control)?;
        prepared.receipt["session_id"] = json!(id);
        prepared.receipt["observed_current_revision"] = json!(revision);
        Ok(prepared)
    })
}
pub fn receipt(target: &ReceiptTarget, control: &Control) -> Result<Value, Error> {
    validate_target(target, control)?;
    control.check()?;
    let mut db = store::open(&target.receipt_root, false)?.ok_or_else(|| {
        Error::new(
            "PUBLICATION_NOT_FOUND",
            "Publication receipt does not exist",
        )
    })?;
    let tx = db.transaction().map_err(store::sql)?;
    let record = store::read(&tx, &target.request_id)?.ok_or_else(|| {
        Error::new(
            "PUBLICATION_NOT_FOUND",
            "Publication receipt does not exist",
        )
    })?;
    Ok(
        json!({"receipt_root":target.receipt_root,"request_id":target.request_id,"state":record.phase,"result":if record.phase==Phase::Complete{Some(record.result(&target.receipt_root,true,true))}else{None},"prepared_output":{"path":record.target,"bytes":record.bytes,"sha256":record.sha256},"output_rechecked":false,"next_action":if record.phase==Phase::Prepared{Some("publication.recover")}else{None}}),
    )
}
pub fn recover(target: &ReceiptTarget, control: &Control) -> Result<Value, Error> {
    validate_target(target, control)?;
    let mut db = store::open(&target.receipt_root, false)?.ok_or_else(|| {
        Error::new(
            "PUBLICATION_NOT_FOUND",
            "Publication receipt does not exist",
        )
    })?;
    let tx = db
        .transaction_with_behavior(TransactionBehavior::Immediate)
        .map_err(store::sql)?;
    let record = store::read(&tx, &target.request_id)?.ok_or_else(|| {
        Error::new(
            "PUBLICATION_NOT_FOUND",
            "Publication receipt does not exist",
        )
    })?;
    resume_transaction(tx, &target.receipt_root, record, true, control)
}
#[cfg(test)]
fn fault_point(stage: &str) {
    if std::env::var("INKBOLT_RECEIPT_FAULT").ok().as_deref() != Some(stage) {
        return;
    }
    let root = PathBuf::from(std::env::var_os("INKBOLT_RECEIPT_TEST_ROOT").unwrap());
    fs::write(root.join("ready"), b"ready").unwrap();
    while !root.join("release").exists() {
        std::thread::sleep(std::time::Duration::from_millis(5));
    }
}
