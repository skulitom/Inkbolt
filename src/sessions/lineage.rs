//! Explicit versioned copies and checked links between bounded histories.
use super::*;

pub(super) const SCHEMA: (&str, &str) = (
    "lineage",
    "CREATE TABLE lineage(id INTEGER PRIMARY KEY CHECK(id=1), payload BLOB NOT NULL, sha256 TEXT NOT NULL) STRICT",
);

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Parent {
    pub source: backup::Source,
    pub session_id: String,
    /// Exact revision from the complete parent backup, including non-head revisions.
    pub revision: u64,
}
impl Parent {
    fn validate(&self) -> Result<(), Error> {
        backup::validate_source(&self.source)?;
        id(&self.session_id)?;
        if self.revision >= MAX_REQUESTS as u64 {
            return Err(Error::new(
                "INVALID_REQUEST",
                "Parent revision exceeds bounded history",
            ));
        }
        Ok(())
    }
    fn fingerprint(&self, session_id: &str) -> Result<String, Error> {
        Ok(assets::sha256(&encode(
            &json!({"type":"continue","session_id":session_id,"parent":self}),
        )?))
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Origin {
    pub version: u32,
    pub session_id: String,
    pub parent: Parent,
    pub source_storage_version: i64,
    pub source_head_revision: u64,
    pub source_state_sha256: String,
    pub source_history_sha256: String,
    /// New canonical encoding may differ from semantically equivalent parent bytes.
    pub initial_state_sha256: String,
}
fn hash_valid(hash: &str) -> bool {
    hash.len() == 64
        && hash
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
pub(super) fn save(db: &Connection, origin: &Origin) -> Result<(), Error> {
    let payload = encode(origin)?;
    if payload.len() > 32768 {
        return Err(limit("Session provenance exceeds 32 KiB"));
    }
    db.execute(
        "INSERT INTO lineage(id,payload,sha256) VALUES(1,?1,?2)",
        params![payload, assets::sha256(&payload)],
    )
    .map_err(sql)?;
    Ok(())
}
pub(super) fn read(db: &Connection, session_id: &str) -> Result<Option<Origin>, Error> {
    let first: String = db
        .query_row(
            "SELECT request_id FROM requests WHERE revision=0",
            [],
            |r| r.get(0),
        )
        .map_err(sql)?;
    let (fingerprint, receipt) =
        request(db, &first)?.ok_or_else(|| corrupt("Initial receipt is missing"))?;
    let row: Option<(Vec<u8>, String)> = if storage_version(db)? == 2 {
        // Bound the allocation before loading untrusted provenance bytes.
        let (count, length): (i64, i64) = db
            .query_row(
                "SELECT COUNT(*),COALESCE(SUM(length(payload)),0) FROM lineage",
                [],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .map_err(sql)?;
        if count > 1 || length > 32768 {
            return Err(corrupt("Session provenance exceeds its bound"));
        }
        let row = db
            .query_row("SELECT payload,sha256 FROM lineage WHERE id=1", [], |r| {
                Ok((r.get(0)?, r.get(1)?))
            })
            .optional()
            .map_err(sql)?;
        if row.is_none() && count != 0 {
            return Err(corrupt("Invalid session provenance row identity"));
        }
        row
    } else {
        None
    };
    let Some((payload, hash)) = row else {
        if receipt.action != "create" {
            return Err(corrupt("Initial receipt requires session provenance"));
        }
        return Ok(None);
    };
    if assets::sha256(&payload) != hash {
        return Err(corrupt("Session provenance checksum is invalid"));
    }
    let origin: Origin =
        serde_json::from_slice(&payload).map_err(|_| corrupt("Invalid session provenance"))?;
    origin
        .parent
        .validate()
        .map_err(|_| corrupt("Invalid parent history identity"))?;
    let initial_hash: String = db
        .query_row("SELECT sha256 FROM states WHERE id=0", [], |r| r.get(0))
        .map_err(sql)?;
    if origin.version != 1
        || origin.session_id != session_id
        || origin.parent.session_id == session_id
        || !SUPPORTED_STORE_VERSIONS.contains(&origin.source_storage_version)
        || origin.source_head_revision >= MAX_REQUESTS as u64
        || origin.parent.revision > origin.source_head_revision
        || !hash_valid(&origin.source_state_sha256)
        || !hash_valid(&origin.source_history_sha256)
        || !hash_valid(&origin.initial_state_sha256)
        || origin.initial_state_sha256 != initial_hash
        || receipt.state_id != 0
        || receipt.state_sha256 != initial_hash
        || receipt.action != "continue"
        || fingerprint != origin.parent.fingerprint(session_id)?
    {
        return Err(corrupt(
            "Session provenance disagrees with its initial receipt or identity",
        ));
    }
    Ok(Some(origin))
}

/// Start independent bounded history; the original remains in the pinned backup.
pub fn continue_from(
    root: &Path,
    session_id: &str,
    request_id: &str,
    parent: &Parent,
    control: &Control,
) -> Result<Value, Error> {
    backup::checked_path(root)?;
    id(request_id)?;
    parent.validate()?;
    if parent.session_id == session_id {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Continuation requires a new session ID",
        ));
    }
    let target = store_path(root, session_id)?;
    backup::checked_path(&target)?;
    let fingerprint = parent.fingerprint(session_id)?;
    // A durable retry depends on the committed receipt, not continued availability of its parent.
    if target
        .try_exists()
        .map_err(|_| Error::new("IO_ERROR", "Unable to inspect continuation destination"))?
    {
        return replay_creation(root, session_id, request_id, &fingerprint, "continue");
    }
    control.check()?;
    backup::no_sidecars(&target)?;
    let temp = backup::copy_source(root, &parent.source, control)?;
    let mut db = backup::open_copy(&temp.0, true)?;
    check_schema(&db)?;
    let tx = db.transaction().map_err(sql)?;
    let verified = verify_connection(&tx, &parent.session_id, control)?;
    let meta = read_meta(&tx, &parent.session_id)?;
    let state = revision_state(&tx, parent.revision, &meta)?;
    let source_request: String = tx
        .query_row(
            "SELECT request_id FROM requests WHERE revision=?1",
            [parent.revision as u32],
            |r| r.get(0),
        )
        .map_err(sql)?;
    let source_state_sha256 = request(&tx, &source_request)?
        .ok_or_else(|| corrupt("Parent revision receipt is missing"))?
        .1
        .state_sha256;
    let origin = Origin {
        version: 1,
        session_id: session_id.to_owned(),
        parent: parent.clone(),
        source_storage_version: storage_version(&tx)?,
        source_head_revision: meta.revision.into(),
        source_state_sha256,
        source_history_sha256: verified["history_sha256"].as_str().unwrap().to_owned(),
        initial_state_sha256: String::new(),
    };
    drop(tx);
    db.close().map_err(|(_, e)| sql(e))?;
    #[cfg(test)]
    fault_point("continuation_after_capture");
    create_prepared(
        root,
        session_id,
        request_id,
        state,
        &fingerprint,
        Some(origin),
        control,
    )
}

/// Migrate a checked v1 standalone backup to a new v2 backup without changing old rows.
pub fn migrate(
    session_id: &str,
    source: &backup::Source,
    target_version: i64,
    output: &backup::Output,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    id(session_id)?;
    if target_version != STORE_VERSION {
        return Err(Error::new(
            "SESSION_FORMAT",
            "Only explicit migration from version 1 to version 2 is supported",
        ));
    }
    let target = backup::output_path(output)?;
    let temp = backup::copy_source(&output.output_root, source, control)?;
    let original = backup::inspect(&temp.0, session_id, control)?;
    if original["storage_version"] != 1 {
        return Err(Error::new(
            "MIGRATION_NOT_NEEDED",
            "Source is already version 2; use recovery to restore it unchanged",
        ));
    }
    let mut db = backup::open_copy(&temp.0, false)?;
    let tx = db
        .transaction_with_behavior(TransactionBehavior::Immediate)
        .map_err(sql)?;
    tx.execute_batch(SCHEMA.1).map_err(sql)?;
    tx.pragma_update(None, "user_version", STORE_VERSION)
        .map_err(sql)?;
    #[cfg(test)]
    fault_point("migration_after_schema");
    control.check()?;
    tx.commit().map_err(sql)?;
    db.close().map_err(|(_, e)| sql(e))?;
    let verified = backup::inspect(&temp.0, session_id, control)?;
    let mut expected = original.clone();
    expected["storage_version"] = json!(STORE_VERSION);
    if verified != expected {
        return Err(corrupt("Migration changed original session history"));
    }
    OpenOptions::new()
        .write(true)
        .open(&temp.0)
        .and_then(|f| f.sync_all())
        .map_err(|_| Error::new("IO_ERROR", "Unable to flush migrated history"))?;
    let mut identity = backup::identity(&temp.0, control)?;
    identity.file_path = target.clone();
    let result = json!({"created":true,"source":source,"backup":identity,"from_storage_version":1,"session":verified,"history_preserved":true,"resources_copied":false,"external_resources_verified":false,"source_changed":false,"migration_performed":true});
    #[cfg(test)]
    fault_point("migration_before_publish");
    backup::publish(&temp.0, &target, control)?;
    #[cfg(test)]
    fault_point("migration_after_publish");
    Ok(result)
}
