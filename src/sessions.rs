//! Local transactional sessions with immutable content states, saved history and retry receipts.
pub mod backup;
pub mod lineage;
use crate::{
    Document, Error, assets,
    control::Control,
    edit,
    model::{self, limit},
};
use rusqlite::{
    Connection, OpenFlags, OptionalExtension, TransactionBehavior, limits::Limit, params,
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, HashSet},
    fs::{self, OpenOptions},
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
    time::Duration,
};
pub const STORE_VERSION: i64 = 2;
pub const SUPPORTED_STORE_VERSIONS: &[i64] = &[1, 2];
pub const APPLICATION_ID: i64 = 0x494e4b53;
pub const MAX_STATES: usize = 256;
pub const MAX_REQUESTS: usize = 2048;
pub const MAX_SNAPSHOTS: usize = 32;
pub const MAX_STATE_BYTES: usize = model::MAX_LARGE_VECTOR_BYTES + 16384;
pub const MAX_HISTORY_BYTES: i64 = 64 * 1024 * 1024;
pub const MAX_DATABASE_BYTES: u64 = 128 * 1024 * 1024;
pub const MAX_RECEIPT_BYTES: usize = 65536;
static TEMP: AtomicU64 = AtomicU64::new(0);
const SCHEMA: &[(&str, &str)] = &[
    (
        "states",
        "CREATE TABLE states(id INTEGER PRIMARY KEY, payload BLOB NOT NULL, sha256 TEXT NOT NULL) STRICT",
    ),
    (
        "meta",
        "CREATE TABLE meta(id INTEGER PRIMARY KEY CHECK(id=1), session_id TEXT NOT NULL, revision INTEGER NOT NULL, current_state INTEGER NOT NULL REFERENCES states(id), undo_json TEXT NOT NULL, redo_json TEXT NOT NULL, sha256 TEXT NOT NULL) STRICT",
    ),
    (
        "requests",
        "CREATE TABLE requests(request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, revision INTEGER UNIQUE NOT NULL, payload BLOB NOT NULL, sha256 TEXT NOT NULL) STRICT",
    ),
    (
        "snapshots",
        "CREATE TABLE snapshots(name TEXT PRIMARY KEY, state_id INTEGER NOT NULL REFERENCES states(id), revision INTEGER NOT NULL, sha256 TEXT NOT NULL) STRICT",
    ),
];
#[derive(Clone, Debug, Default, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(default, deny_unknown_fields)]
pub struct Resources {
    pub asset_root: Option<PathBuf>,
    pub font_root: Option<PathBuf>,
}
impl Resources {
    pub(crate) fn validate(&self) -> Result<(), Error> {
        for p in self.asset_root.iter().chain(self.font_root.iter()) {
            assets::absolute(p)?;
            if p.as_os_str().len() > 4096 {
                return Err(limit("Resource root path is too long"));
            }
        }
        Ok(())
    }
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct State {
    pub document: Document,
    pub resources: Resources,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Action {
    Edit {
        operations: Vec<edit::Operation>,
        #[serde(default)]
        label: String,
    },
    Undo {
        #[serde(default = "one")]
        steps: usize,
    },
    Redo {
        #[serde(default = "one")]
        steps: usize,
    },
    Snapshot {
        name: String,
    },
    Restore {
        name: String,
    },
    RemoveSnapshot {
        name: String,
    },
    Resources {
        resources: Resources,
    },
}
fn one() -> usize {
    1
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Receipt {
    pub request_id: String,
    pub revision: u32,
    pub from_revision: u32,
    pub action: String,
    pub label: String,
    pub from_state: u32,
    pub state_id: u32,
    pub state_sha256: String,
    pub changes: Vec<Value>,
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Proposal {
    pub version: u32,
    pub session_id: String,
    pub request_id: String,
    pub expected_revision: u64,
    pub request_fingerprint: String,
    pub base_state_sha256: String,
    pub result_state_sha256: String,
}
#[derive(Clone, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(default, deny_unknown_fields)]
pub struct DryRunOptions {
    pub include_document: bool,
    pub compare_pixels: bool,
    pub preview: bool,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Meta {
    session_id: String,
    revision: u32,
    current_state: u32,
    undo: Vec<u32>,
    redo: Vec<u32>,
}
#[derive(Clone, Serialize)]
struct Snapshot {
    name: String,
    state_id: u32,
    revision: u32,
}
fn corrupt(message: &str) -> Error {
    Error::new("SESSION_CORRUPT", message)
}
fn sql(e: rusqlite::Error) -> Error {
    match e.sqlite_error_code() {
        Some(rusqlite::ErrorCode::DatabaseBusy | rusqlite::ErrorCode::DatabaseLocked) => {
            Error::new(
                "SESSION_BUSY",
                "Session is busy; retry with the same request ID",
            )
        }
        Some(rusqlite::ErrorCode::DatabaseCorrupt | rusqlite::ErrorCode::NotADatabase) => {
            corrupt("Session database failed its storage integrity check")
        }
        Some(rusqlite::ErrorCode::DiskFull | rusqlite::ErrorCode::TooBig) => {
            limit("Session storage limit or available disk space exceeded")
        }
        _ => Error::new(
            "SESSION_STORE_ERROR",
            "Unable to complete the local session transaction",
        ),
    }
}
fn encode<T: Serialize>(value: &T) -> Result<Vec<u8>, Error> {
    serde_json::to_vec(value)
        .map_err(|_| Error::new("SESSION_STORE_ERROR", "Unable to encode session data"))
}
fn id(value: &str) -> Result<(), Error> {
    if !model::valid_id(value) {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Session, request and snapshot IDs use document ID syntax",
        ));
    }
    Ok(())
}
pub fn store_path(root: &Path, session_id: &str) -> Result<PathBuf, Error> {
    assets::absolute(root)?;
    id(session_id)?;
    Ok(root.join(format!("{}.sqlite3", assets::sha256(session_id.as_bytes()))))
}
fn configure(db: &Connection) -> Result<(), Error> {
    db.busy_timeout(Duration::from_millis(250)).map_err(sql)?;
    db.set_limit(Limit::SQLITE_LIMIT_LENGTH, (MAX_STATE_BYTES + 65536) as i32)
        .map_err(sql)?;
    db.set_limit(Limit::SQLITE_LIMIT_SQL_LENGTH, 32768)
        .map_err(sql)?;
    db.set_limit(Limit::SQLITE_LIMIT_COLUMN, 128).map_err(sql)?;
    db.set_limit(Limit::SQLITE_LIMIT_VARIABLE_NUMBER, 32)
        .map_err(sql)?;
    db.set_limit(Limit::SQLITE_LIMIT_ATTACHED, 0).map_err(sql)?;
    db.execute_batch("PRAGMA synchronous=FULL; PRAGMA foreign_keys=ON; PRAGMA trusted_schema=OFF; PRAGMA recursive_triggers=OFF; PRAGMA cache_size=-4096; PRAGMA temp_store=MEMORY;").map_err(sql)?;
    #[cfg(test)]
    if std::env::var_os("INKBOLT_SESSION_FAULT").is_some() {
        db.execute_batch("PRAGMA cache_size=-64;").map_err(sql)?;
    }
    Ok(())
}
fn storage_version(db: &Connection) -> Result<i64, Error> {
    db.pragma_query_value(None, "user_version", |r| r.get(0))
        .map_err(sql)
}
fn check_schema(db: &Connection) -> Result<(), Error> {
    let app: i64 = db
        .pragma_query_value(None, "application_id", |r| r.get(0))
        .map_err(sql)?;
    let version = storage_version(db)?;
    if app != APPLICATION_ID || !SUPPORTED_STORE_VERSIONS.contains(&version) {
        return Err(Error::new(
            "SESSION_FORMAT",
            "Unrecognized session format or version",
        ));
    }
    let mut stmt=db.prepare("SELECT name,type,sql FROM sqlite_schema WHERE name NOT GLOB 'sqlite_*' ORDER BY name LIMIT 16").map_err(sql)?;
    let actual: Vec<(String, String, String)> = stmt
        .query_map([], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)))
        .map_err(sql)?
        .collect::<Result<_, _>>()
        .map_err(sql)?;
    let mut schema = SCHEMA.to_vec();
    if version == 2 {
        schema.push(lineage::SCHEMA);
    }
    if actual.len() != schema.len()
        || actual.iter().any(|(name, kind, text)| {
            kind != "table" || !schema.iter().any(|(n, s)| *n == name && *s == text)
        })
    {
        return Err(Error::new(
            "SESSION_FORMAT",
            "Session schema differs from the supported storage contract",
        ));
    }
    let mode: String = db
        .pragma_query_value(None, "journal_mode", |r| r.get(0))
        .map_err(sql)?;
    if mode != "delete" {
        return Err(Error::new(
            "SESSION_FORMAT",
            "Session requires rollback-journal DELETE mode",
        ));
    }
    let pages: i64 = db
        .pragma_query_value(None, "page_count", |r| r.get(0))
        .map_err(sql)?;
    let page_size: i64 = db
        .pragma_query_value(None, "page_size", |r| r.get(0))
        .map_err(sql)?;
    if page_size != 4096 || pages < 0 || pages as u64 * 4096 > MAX_DATABASE_BYTES {
        return Err(limit("Session database exceeds its page budget"));
    }
    db.pragma_update(None, "max_page_count", (MAX_DATABASE_BYTES / 4096) as u32)
        .map_err(sql)?;
    Ok(())
}
fn open(root: &Path, session_id: &str) -> Result<Connection, Error> {
    open_mode(root, session_id, false)
}
fn open_mode(root: &Path, session_id: &str, readonly: bool) -> Result<Connection, Error> {
    let path = store_path(root, session_id)?;
    let m = fs::symlink_metadata(&path).map_err(|e| {
        if e.kind() == std::io::ErrorKind::NotFound {
            Error::new("SESSION_NOT_FOUND", "Session does not exist")
        } else {
            Error::new("IO_ERROR", "Unable to inspect session store")
        }
    })?;
    if !m.is_file() || m.file_type().is_symlink() {
        return Err(corrupt(
            "Session must be a regular non-symlink database file",
        ));
    }
    if m.len() > MAX_DATABASE_BYTES {
        return Err(limit("Session database exceeds 128 MiB"));
    }
    let db = Connection::open_with_flags(
        path,
        (if readonly {
            OpenFlags::SQLITE_OPEN_READ_ONLY
        } else {
            OpenFlags::SQLITE_OPEN_READ_WRITE
        }) | OpenFlags::SQLITE_OPEN_NO_MUTEX
            | OpenFlags::SQLITE_OPEN_NOFOLLOW,
    )
    .map_err(sql)?;
    configure(&db)?;
    check_schema(&db)?;
    Ok(db)
}
fn read_meta(db: &Connection, session_id: &str) -> Result<Meta, Error> {
    let (stored,revision,current,undo,redo,hash):(String,u32,u32,String,String,String)=db.query_row("SELECT session_id,revision,current_state,undo_json,redo_json,sha256 FROM meta WHERE id=1",[],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?,r.get(4)?,r.get(5)?))).map_err(sql)?;
    if undo.len() > 4096 || redo.len() > 4096 {
        return Err(corrupt("Session history stack exceeds limits"));
    }
    let meta = Meta {
        session_id: stored,
        revision,
        current_state: current,
        undo: serde_json::from_str(&undo).map_err(|_| corrupt("Invalid undo stack"))?,
        redo: serde_json::from_str(&redo).map_err(|_| corrupt("Invalid redo stack"))?,
    };
    if meta.session_id != session_id
        || meta.revision >= MAX_REQUESTS as u32
        || meta.undo.len() > MAX_STATES
        || meta.redo.len() > MAX_STATES
        || assets::sha256(&encode(&meta)?) != hash
    {
        return Err(corrupt("Session head or history checksum is invalid"));
    }
    let count: i64 = db
        .query_row("SELECT COUNT(*) FROM meta", [], |r| r.get(0))
        .map_err(sql)?;
    if count != 1 {
        return Err(corrupt("Session has an invalid head count"));
    }
    let mut stmt = db
        .prepare("SELECT id FROM states ORDER BY id LIMIT 257")
        .map_err(sql)?;
    let states: HashSet<u32> = stmt
        .query_map([], |r| r.get(0))
        .map_err(sql)?
        .collect::<Result<_, _>>()
        .map_err(sql)?;
    if states.is_empty()
        || states.len() > MAX_STATES
        || states.iter().any(|s| *s > meta.revision)
        || std::iter::once(&meta.current_state)
            .chain(meta.undo.iter())
            .chain(meta.redo.iter())
            .any(|s| !states.contains(s))
    {
        return Err(corrupt("Session history refers to unavailable states"));
    }
    let (requests, bytes): (i64, i64) = db
        .query_row(
            "SELECT COUNT(*),COALESCE(SUM(length(payload)),0) FROM requests",
            [],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .map_err(sql)?;
    if requests != meta.revision as i64 + 1
        || bytes > MAX_REQUESTS as i64 * MAX_RECEIPT_BYTES as i64
    {
        return Err(corrupt("Session request ledger is inconsistent"));
    }
    let latest: String = db
        .query_row(
            "SELECT request_id FROM requests WHERE revision=?1",
            [meta.revision],
            |r| r.get(0),
        )
        .map_err(sql)?;
    let (_, receipt) =
        request(db, &latest)?.ok_or_else(|| corrupt("Session head receipt is missing"))?;
    if receipt.state_id != meta.current_state || receipt.revision != meta.revision {
        return Err(corrupt("Session head disagrees with its committed receipt"));
    }
    lineage::read(db, session_id)?;
    Ok(meta)
}
fn save_meta(db: &Connection, meta: &Meta) -> Result<(), Error> {
    let hash = assets::sha256(&encode(meta)?);
    let undo = serde_json::to_string(&meta.undo).unwrap();
    let redo = serde_json::to_string(&meta.redo).unwrap();
    db.execute("INSERT INTO meta(id,session_id,revision,current_state,undo_json,redo_json,sha256) VALUES(1,?1,?2,?3,?4,?5,?6) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,current_state=excluded.current_state,undo_json=excluded.undo_json,redo_json=excluded.redo_json,sha256=excluded.sha256",params![meta.session_id,meta.revision,meta.current_state,undo,redo,hash]).map_err(sql)?;
    Ok(())
}
fn load_state(db: &Connection, state_id: u32) -> Result<(State, String), Error> {
    let (bytes, hash): (Vec<u8>, String) = db
        .query_row(
            "SELECT payload,sha256 FROM states WHERE id=?1",
            [state_id],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .optional()
        .map_err(sql)?
        .ok_or_else(|| corrupt("Saved content state is missing"))?;
    if bytes.len() > MAX_STATE_BYTES || assets::sha256(&bytes) != hash {
        return Err(corrupt("Saved content state checksum is invalid"));
    }
    let state: State = serde_json::from_slice(&bytes)
        .map_err(|_| corrupt("Saved content state cannot be decoded"))?;
    if state.document.revision != 0 || state.document.schema_version != 2 {
        return Err(corrupt(
            "Saved content state has an invalid canonical revision",
        ));
    }
    crate::validate(&state.document)
        .map_err(|_| corrupt("Saved document fails its model invariants"))?;
    state
        .resources
        .validate()
        .map_err(|_| corrupt("Saved resource bindings are invalid"))?;
    Ok((state, hash))
}
fn put_state(db: &Connection, state_id: u32, state: &State) -> Result<String, Error> {
    let (bytes, hash) = prepare_state(db, state)?;
    db.execute(
        "INSERT INTO states(id,payload,sha256) VALUES(?1,?2,?3)",
        params![state_id, bytes, hash],
    )
    .map_err(sql)?;
    Ok(hash)
}
fn prepare_state(db: &Connection, state: &State) -> Result<(Vec<u8>, String), Error> {
    let bytes = encode(state)?;
    if bytes.len() > MAX_STATE_BYTES {
        return Err(limit("Session state exceeds storage limit"));
    }
    let (count, total): (i64, i64) = db
        .query_row(
            "SELECT COUNT(*),COALESCE(SUM(length(payload)),0) FROM states",
            [],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .map_err(sql)?;
    if count >= MAX_STATES as i64 || total + bytes.len() as i64 > MAX_HISTORY_BYTES {
        return Err(Error::new(
            "HISTORY_LIMIT",
            "Session history is full; use session.backup then session.continue to start linked history without deleting the original",
        ));
    }
    let hash = assets::sha256(&bytes);
    Ok((bytes, hash))
}
fn request(db: &Connection, request_id: &str) -> Result<Option<(String, Receipt)>, Error> {
    let found: Option<(String, Vec<u8>, String, u32)> = db
        .query_row(
            "SELECT fingerprint,payload,sha256,revision FROM requests WHERE request_id=?1",
            [request_id],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)),
        )
        .optional()
        .map_err(sql)?;
    found
        .map(|(fingerprint, bytes, hash, revision)| {
            if bytes.len() > MAX_RECEIPT_BYTES
                || assets::sha256(&encode(&(&fingerprint, &bytes))?) != hash
            {
                return Err(corrupt("Saved retry receipt checksum is invalid"));
            }
            let receipt: Receipt = serde_json::from_slice(&bytes)
                .map_err(|_| corrupt("Saved retry receipt is invalid"))?;
            if receipt.request_id != request_id
                || receipt.revision != revision
                || revision >= MAX_REQUESTS as u32
                || receipt.from_revision != revision.saturating_sub(1)
                || receipt.state_id > revision
                || receipt.from_state > revision
            {
                return Err(corrupt("Retry receipt identity is inconsistent"));
            }
            Ok((fingerprint, receipt))
        })
        .transpose()
}
fn save_request(db: &Connection, fingerprint: &str, receipt: &Receipt) -> Result<(), Error> {
    let bytes = encode(receipt)?;
    if bytes.len() > MAX_RECEIPT_BYTES {
        return Err(limit("Session receipt exceeds 64 KiB"));
    }
    let hash = assets::sha256(&encode(&(fingerprint, &bytes))?);
    db.execute("INSERT INTO requests(request_id,fingerprint,revision,payload,sha256) VALUES(?1,?2,?3,?4,?5)",params![receipt.request_id,fingerprint,receipt.revision,bytes,hash]).map_err(sql)?;
    Ok(())
}
fn response(
    db: &Connection,
    meta: &Meta,
    receipt: Receipt,
    replayed: bool,
) -> Result<Value, Error> {
    let (mut state, hash) = load_state(db, receipt.state_id)?;
    if hash != receipt.state_sha256 {
        return Err(corrupt("Receipt refers to altered content"));
    }
    state.document.revision = u64::from(receipt.revision);
    Ok(
        json!({"session_id":meta.session_id,"receipt":receipt,"replayed":replayed,"current_revision":meta.revision,"current_state_id":meta.current_state,"document":state.document,"resources":state.resources,"lineage":lineage::read(db, &meta.session_id)?}),
    )
}
struct Temporary(PathBuf);
impl Drop for Temporary {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.0);
        let mut journal = self.0.as_os_str().to_owned();
        journal.push("-journal");
        let _ = fs::remove_file(PathBuf::from(journal));
    }
}
fn reserve(root: &Path) -> Result<Temporary, Error> {
    fs::create_dir_all(root)
        .map_err(|_| Error::new("IO_ERROR", "Unable to create explicit session root"))?;
    for _ in 0..64 {
        let path = root.join(format!(
            ".inkbolt-session-{}-{}.tmp",
            std::process::id(),
            TEMP.fetch_add(1, Ordering::Relaxed)
        ));
        match OpenOptions::new().create_new(true).write(true).open(&path) {
            Ok(file) => {
                drop(file);
                return Ok(Temporary(path));
            }
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(_) => return Err(Error::new("IO_ERROR", "Unable to reserve session database")),
        }
    }
    Err(Error::new(
        "SESSION_STORE_ERROR",
        "Session temporary-name retry limit exceeded",
    ))
}
pub fn create(
    root: &Path,
    session_id: &str,
    request_id: &str,
    document: &Document,
    resources: &Resources,
    control: &Control,
) -> Result<Value, Error> {
    id(request_id)?;
    let target = store_path(root, session_id)?;
    let existed = target
        .try_exists()
        .map_err(|_| Error::new("IO_ERROR", "Unable to inspect session destination"))?;
    // Validate typed input even on replay: optional NaN fields can serialize identically to null.
    // A committed retry uses bounded validation without a newly cancelled/expired context.
    if existed {
        model::validate(document)?;
    } else {
        model::validate_controlled(document, control)?;
    }
    resources.validate()?;
    let fingerprint = assets::sha256(&encode(
        &json!({"type":"create","document":document,"resources":resources}),
    )?);
    if existed {
        return replay_creation(root, session_id, request_id, &fingerprint, "create");
    }
    create_prepared(
        root,
        session_id,
        request_id,
        State {
            document: document.clone(),
            resources: resources.clone(),
        },
        &fingerprint,
        None,
        control,
    )
}

fn replay_creation(
    root: &Path,
    session_id: &str,
    request_id: &str,
    fingerprint: &str,
    action: &str,
) -> Result<Value, Error> {
    let mut db = open(root, session_id)?;
    let tx = db.transaction().map_err(sql)?;
    let meta = read_meta(&tx, session_id)?;
    let Some((old, receipt)) = request(&tx, request_id)? else {
        return Err(Error::new(
            "SESSION_EXISTS",
            "Session ID already exists; existing data is preserved",
        ));
    };
    if old != fingerprint || receipt.action != action {
        return Err(Error::new(
            "REQUEST_ID_REUSED",
            "Request ID was already used for different content",
        ));
    }
    response(&tx, &meta, receipt, true)
}

fn create_prepared(
    root: &Path,
    session_id: &str,
    request_id: &str,
    mut state: State,
    fingerprint: &str,
    mut origin: Option<lineage::Origin>,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    let target = store_path(root, session_id)?;
    backup::no_sidecars(&target)?;
    let action = if origin.is_some() {
        "continue"
    } else {
        "create"
    };
    let temp = reserve(root)?;
    let mut db = Connection::open_with_flags(
        &temp.0,
        OpenFlags::SQLITE_OPEN_READ_WRITE
            | OpenFlags::SQLITE_OPEN_NO_MUTEX
            | OpenFlags::SQLITE_OPEN_NOFOLLOW,
    )
    .map_err(sql)?;
    configure(&db)?;
    db.execute_batch("PRAGMA page_size=4096; PRAGMA journal_mode=DELETE;")
        .map_err(sql)?;
    db.pragma_update(None, "application_id", APPLICATION_ID)
        .map_err(sql)?;
    db.pragma_update(None, "user_version", STORE_VERSION)
        .map_err(sql)?;
    db.pragma_update(None, "max_page_count", (MAX_DATABASE_BYTES / 4096) as u32)
        .map_err(sql)?;
    let tx = db
        .transaction_with_behavior(TransactionBehavior::Immediate)
        .map_err(sql)?;
    for (_, statement) in SCHEMA {
        tx.execute_batch(statement).map_err(sql)?;
    }
    tx.execute_batch(lineage::SCHEMA.1).map_err(sql)?;
    state.document.schema_version = 2;
    state.document.revision = 0;
    let hash = put_state(&tx, 0, &state)?;
    if let Some(origin) = &mut origin {
        origin.initial_state_sha256 = hash.clone();
        lineage::save(&tx, origin)?;
    }
    let meta = Meta {
        session_id: session_id.to_owned(),
        revision: 0,
        current_state: 0,
        undo: Vec::new(),
        redo: Vec::new(),
    };
    save_meta(&tx, &meta)?;
    let receipt = Receipt {
        request_id: request_id.to_owned(),
        revision: 0,
        from_revision: 0,
        action: action.into(),
        label: String::new(),
        from_state: 0,
        state_id: 0,
        state_sha256: hash,
        changes: Vec::new(),
    };
    save_request(&tx, fingerprint, &receipt)?;
    let result = response(&tx, &meta, receipt, false)?;
    control.check()?;
    tx.commit().map_err(sql)?;
    db.close().map_err(|(_, e)| sql(e))?;
    OpenOptions::new()
        .read(true)
        .write(true)
        .open(&temp.0)
        .and_then(|f| f.sync_all())
        .map_err(|_| Error::new("IO_ERROR", "Unable to flush new session database"))?;
    control.check()?;
    backup::no_sidecars(&target)?;
    #[cfg(test)]
    if origin.is_some() {
        fault_point("continuation_before_publish");
    }
    control.check()?;
    match fs::hard_link(&temp.0, &target) {
        Ok(()) => {}
        Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {
            return replay_creation(root, session_id, request_id, fingerprint, action);
        }
        Err(_) => {
            return Err(Error::new(
                "SESSION_STORE_ERROR",
                "Session root must support create-only hard-link publication",
            ));
        }
    }
    #[cfg(test)]
    if origin.is_some() {
        fault_point("continuation_after_publish");
    }
    Ok(result)
}
fn snapshots(db: &Connection) -> Result<Vec<Snapshot>, Error> {
    let mut stmt = db
        .prepare("SELECT name,state_id,revision,sha256 FROM snapshots ORDER BY name LIMIT 33")
        .map_err(sql)?;
    let rows = stmt
        .query_map([], |r| {
            Ok((
                r.get::<_, String>(0)?,
                r.get::<_, u32>(1)?,
                r.get::<_, u32>(2)?,
                r.get::<_, String>(3)?,
            ))
        })
        .map_err(sql)?;
    let mut result = Vec::new();
    for row in rows {
        let (name, state_id, revision, hash) = row.map_err(sql)?;
        let snapshot = Snapshot {
            name,
            state_id,
            revision,
        };
        if !model::valid_id(&snapshot.name) || assets::sha256(&encode(&snapshot)?) != hash {
            return Err(corrupt("Named snapshot checksum is invalid"));
        }
        result.push(snapshot);
    }
    if result.len() > MAX_SNAPSHOTS {
        return Err(corrupt("Too many named snapshots"));
    }
    Ok(result)
}
pub fn read(root: &Path, session_id: &str, snapshot: Option<&str>) -> Result<Value, Error> {
    let mut db = open(root, session_id)?;
    let tx = db.transaction().map_err(sql)?;
    let meta = read_meta(&tx, session_id)?;
    let names = snapshots(&tx)?;
    let (state_id, revision) = if let Some(name) = snapshot {
        let s = names
            .iter()
            .find(|s| s.name == name)
            .ok_or_else(|| Error::new("SNAPSHOT_NOT_FOUND", "Named snapshot does not exist"))?;
        (s.state_id, s.revision)
    } else {
        (meta.current_state, meta.revision)
    };
    let (mut state, hash) = load_state(&tx, state_id)?;
    state.document.revision = u64::from(revision);
    Ok(
        json!({"session_id":session_id,"revision":revision,"current_revision":meta.revision,"state_id":state_id,"state_sha256":hash,"document":state.document,"resources":state.resources,"undo_depth":meta.undo.len(),"redo_depth":meta.redo.len(),"snapshots":names,"lineage":lineage::read(&tx, session_id)?}),
    )
}
pub fn receipt(root: &Path, session_id: &str, request_id: &str) -> Result<Value, Error> {
    id(request_id)?;
    let mut db = open(root, session_id)?;
    let tx = db.transaction().map_err(sql)?;
    let meta = read_meta(&tx, session_id)?;
    let (_, receipt) = request(&tx, request_id)?.ok_or_else(|| {
        Error::new(
            "REQUEST_NOT_FOUND",
            "No committed receipt has this request ID",
        )
    })?;
    response(&tx, &meta, receipt, true)
}

fn revision_state(db: &Connection, revision: u64, meta: &Meta) -> Result<State, Error> {
    if revision > u64::from(meta.revision) {
        return Err(Error::new(
            "REVISION_NOT_FOUND",
            "Requested revision has not been committed",
        ));
    }
    let request_id: String = db
        .query_row(
            "SELECT request_id FROM requests WHERE revision=?1",
            [revision as u32],
            |r| r.get(0),
        )
        .map_err(sql)?;
    let (_, receipt) =
        request(db, &request_id)?.ok_or_else(|| corrupt("Revision receipt is missing"))?;
    let (mut state, hash) = load_state(db, receipt.state_id)?;
    if hash != receipt.state_sha256 {
        return Err(corrupt("Revision content differs from its receipt"));
    }
    state.document.revision = revision;
    Ok(state)
}
/// Capture an immutable saved revision and its resource bindings under one read transaction.
pub fn capture(root: &Path, session_id: &str, revision: u64) -> Result<State, Error> {
    let mut db = open(root, session_id)?;
    let tx = db.transaction().map_err(sql)?;
    let meta = read_meta(&tx, session_id)?;
    revision_state(&tx, revision, &meta)
}
pub fn compare(
    root: &Path,
    session_id: &str,
    from_revision: u64,
    to_revision: u64,
    compare_pixels: bool,
    control: &Control,
) -> Result<Value, Error> {
    let (before, after, current_revision) =
        capture_pair(root, session_id, from_revision, to_revision, control)?;
    let mut result = crate::diff::compare(
        &before.document,
        &after.document,
        &before.resources,
        &after.resources,
        compare_pixels,
        control,
    )?;
    result["session_id"] = json!(session_id);
    result["observed_current_revision"] = json!(current_revision);
    Ok(result)
}

fn capture_pair(
    root: &Path,
    session_id: &str,
    from_revision: u64,
    to_revision: u64,
    control: &Control,
) -> Result<(State, State, u32), Error> {
    control.check()?;
    let mut db = open_mode(root, session_id, true)?;
    let tx = db.transaction().map_err(sql)?;
    let meta = read_meta(&tx, session_id)?;
    let before = revision_state(&tx, from_revision, &meta)?;
    let after = revision_state(&tx, to_revision, &meta)?;
    control.check_resource_paths(&before.resources)?;
    control.check_resource_paths(&after.resources)?;
    // Release the read lock before rendering; both captured states remain immutable.
    drop(tx);
    drop(db);
    Ok((before, after, meta.revision))
}

pub fn compare_preview(
    root: &Path,
    session_id: &str,
    from_revision: u64,
    to_revision: u64,
    options: &crate::visual_diff::Options,
    control: &Control,
) -> Result<Value, Error> {
    let (before, after, current_revision) =
        capture_pair(root, session_id, from_revision, to_revision, control)?;
    let mut result = crate::visual_diff::compare(
        &before.document,
        &after.document,
        &before.resources,
        &after.resources,
        options,
        control,
    )?;
    result["session_id"] = json!(session_id);
    result["observed_current_revision"] = json!(current_revision);
    Ok(result)
}
pub fn publish(
    root: &Path,
    session_id: &str,
    expected_revision: u64,
    options: &crate::publish::Options,
    control: &Control,
) -> Result<Value, Error> {
    let state = capture_head(root, session_id, expected_revision, control)?;
    let mut result = crate::publish::publish(&state.document, &state.resources, options, control)?;
    result["session_id"] = json!(session_id);
    result["observed_current_revision"] = json!(expected_revision);
    Ok(result)
}
pub(crate) fn capture_head(
    root: &Path,
    session_id: &str,
    expected_revision: u64,
    control: &Control,
) -> Result<State, Error> {
    control.check()?;
    let mut db = open(root, session_id)?;
    let tx = db.transaction().map_err(sql)?;
    let meta = read_meta(&tx, session_id)?;
    if expected_revision != u64::from(meta.revision) {
        return Err(Error::new(
            "REVISION_CONFLICT",
            "Expected revision does not match the committed session head",
        ));
    }
    let state = revision_state(&tx, expected_revision, &meta)?;
    control.check_resource_paths(&state.resources)?;
    drop(tx);
    drop(db);
    Ok(state)
}
struct PreparedAction {
    meta: Meta,
    state: State,
    receipt: Receipt,
    new_state: Option<(Vec<u8>, String)>,
    snapshot_put: Option<(Snapshot, String)>,
    snapshot_remove: Option<String>,
}
fn prepare_action(
    db: &Connection,
    mut meta: Meta,
    request_id: &str,
    expected_revision: u64,
    action: &Action,
    control: &Control,
) -> Result<PreparedAction, Error> {
    control.check()?;
    if expected_revision != u64::from(meta.revision) {
        return Err(Error::new(
            "REVISION_CONFLICT",
            "Expected revision does not match the committed session head",
        ));
    }
    if meta.revision + 1 >= MAX_REQUESTS as u32 {
        return Err(Error::new(
            "HISTORY_LIMIT",
            "Session request history is full; preserve it and start a new session",
        ));
    }
    let previous = meta.revision;
    let from_state = meta.current_state;
    let next = previous + 1;
    let (mut state, _) = load_state(db, meta.current_state)?;
    let mut new_state = None;
    let mut snapshot_put = None;
    let mut snapshot_remove = None;
    let mut changes = Vec::new();
    let mut label = String::new();
    let kind = match action {
        Action::Edit {
            operations,
            label: requested,
        } => {
            control.check_resource_paths(&state.resources)?;
            if requested.len() > 512 || requested.chars().any(char::is_control) {
                return Err(Error::new(
                    "INVALID_REQUEST",
                    "History label must be at most 512 bytes with no control characters",
                ));
            }
            label = requested.clone();
            state.document.revision = u64::from(previous);
            let result = edit::apply_with_resources(
                &state.document,
                u64::from(previous),
                operations,
                state.resources.asset_root.as_deref(),
                state.resources.font_root.as_deref(),
                control,
            )?;
            changes = result.changes.into_iter().map(|v| json!(v)).collect();
            state.document = result.document;
            state.document.revision = 0;
            new_state = Some(prepare_state(db, &state)?);
            meta.undo.push(from_state);
            meta.redo.clear();
            meta.current_state = next;
            "edit"
        }
        Action::Resources { resources } => {
            resources.validate()?;
            state.resources = resources.clone();
            new_state = Some(prepare_state(db, &state)?);
            meta.undo.push(from_state);
            meta.redo.clear();
            meta.current_state = next;
            "resources"
        }
        Action::Undo { steps } | Action::Redo { steps } => {
            if *steps == 0 || *steps > MAX_STATES {
                return Err(Error::new(
                    "INVALID_REQUEST",
                    "History movement requires 1 through 256 steps",
                ));
            }
            let undo = matches!(action, Action::Undo { .. });
            let (source, destination) = if undo {
                (&mut meta.undo, &mut meta.redo)
            } else {
                (&mut meta.redo, &mut meta.undo)
            };
            if *steps > source.len() {
                return Err(Error::new(
                    "HISTORY_BOUNDARY",
                    "Requested history movement exceeds available steps",
                ));
            }
            for _ in 0..*steps {
                destination.push(meta.current_state);
                meta.current_state = source.pop().unwrap();
            }
            if undo { "undo" } else { "redo" }
        }
        Action::Snapshot { name } => {
            id(name)?;
            let names = snapshots(db)?;
            if names.iter().any(|s| s.name == *name) {
                return Err(Error::new(
                    "SNAPSHOT_EXISTS",
                    "Named snapshot already exists; it is never overwritten",
                ));
            }
            if names.len() >= MAX_SNAPSHOTS {
                return Err(limit("Session exceeds 32 named snapshots"));
            }
            let snapshot = Snapshot {
                name: name.clone(),
                state_id: meta.current_state,
                revision: next,
            };
            let hash = assets::sha256(&encode(&snapshot)?);
            snapshot_put = Some((snapshot, hash));
            label = name.clone();
            "snapshot"
        }
        Action::Restore { name } => {
            id(name)?;
            let names = snapshots(db)?;
            let snapshot = names
                .iter()
                .find(|s| s.name == *name)
                .ok_or_else(|| Error::new("SNAPSHOT_NOT_FOUND", "Named snapshot does not exist"))?;
            meta.undo.push(from_state);
            meta.redo.clear();
            meta.current_state = snapshot.state_id;
            label = name.clone();
            "restore"
        }
        Action::RemoveSnapshot { name } => {
            id(name)?;
            if !snapshots(db)?.iter().any(|s| s.name == *name) {
                return Err(Error::new(
                    "SNAPSHOT_NOT_FOUND",
                    "Named snapshot does not exist",
                ));
            }
            snapshot_remove = Some(name.clone());
            label = name.clone();
            "remove_snapshot"
        }
    };
    if meta.undo.len() > MAX_STATES || meta.redo.len() > MAX_STATES {
        return Err(Error::new(
            "HISTORY_LIMIT",
            "Undo or redo depth exceeds 256 steps",
        ));
    }
    meta.revision = next;
    let (committed, hash) = if let Some((_, hash)) = &new_state {
        (state, hash.clone())
    } else {
        load_state(db, meta.current_state)?
    };
    control.check_resource_paths(&committed.resources)?;
    let receipt = Receipt {
        request_id: request_id.to_owned(),
        revision: next,
        from_revision: previous,
        action: kind.into(),
        label,
        from_state,
        state_id: meta.current_state,
        state_sha256: hash,
        changes,
    };
    if encode(&receipt)?.len() > MAX_RECEIPT_BYTES {
        return Err(limit("Session receipt exceeds 64 KiB"));
    }
    Ok(PreparedAction {
        meta,
        state: committed,
        receipt,
        new_state,
        snapshot_put,
        snapshot_remove,
    })
}
fn persist_action(db: &Connection, prepared: &PreparedAction) -> Result<(), Error> {
    if let Some((bytes, hash)) = &prepared.new_state {
        db.execute(
            "INSERT INTO states(id,payload,sha256) VALUES(?1,?2,?3)",
            params![prepared.receipt.state_id, bytes, hash],
        )
        .map_err(sql)?;
    }
    if let Some((snapshot, hash)) = &prepared.snapshot_put {
        db.execute(
            "INSERT INTO snapshots(name,state_id,revision,sha256) VALUES(?1,?2,?3,?4)",
            params![snapshot.name, snapshot.state_id, snapshot.revision, hash],
        )
        .map_err(sql)?;
    }
    if let Some(name) = &prepared.snapshot_remove {
        db.execute("DELETE FROM snapshots WHERE name=?1", [name])
            .map_err(sql)?;
    }
    save_meta(db, &prepared.meta)
}
fn action_fingerprint(expected_revision: u64, action: &Action) -> Result<String, Error> {
    crate::finite::check(action)?;
    Ok(assets::sha256(&encode(
        &json!({"expected_revision":expected_revision,"action":action}),
    )?))
}
pub fn mutate(
    root: &Path,
    session_id: &str,
    request_id: &str,
    expected_revision: u64,
    action: &Action,
    control: &Control,
) -> Result<Value, Error> {
    mutate_checked(
        root,
        session_id,
        request_id,
        expected_revision,
        action,
        None,
        control,
    )
}
fn mutate_checked(
    root: &Path,
    session_id: &str,
    request_id: &str,
    expected_revision: u64,
    action: &Action,
    proposal: Option<&Proposal>,
    control: &Control,
) -> Result<Value, Error> {
    id(request_id)?;
    let fingerprint = action_fingerprint(expected_revision, action)?;
    let mut db = open(root, session_id)?;
    let tx = db
        .transaction_with_behavior(TransactionBehavior::Immediate)
        .map_err(sql)?;
    let meta = read_meta(&tx, session_id)?;
    if let Some((old, receipt)) = request(&tx, request_id)? {
        if old != fingerprint {
            return Err(Error::new(
                "REQUEST_ID_REUSED",
                "Request ID was already used for different content",
            ));
        }
        if let Some(proposal) = proposal {
            let (_, base_hash) = load_state(&tx, receipt.from_state)?;
            if base_hash != proposal.base_state_sha256
                || receipt.state_sha256 != proposal.result_state_sha256
            {
                return Err(Error::new(
                    "PROPOSAL_MISMATCH",
                    "The committed receipt differs from the supplied proposal; recover the original session receipt",
                ));
            }
        }
        return response(&tx, &meta, receipt, true);
    }
    control.check()?;
    if let Some(proposal) = proposal {
        if expected_revision != u64::from(meta.revision) {
            return Err(Error::new(
                "REVISION_CONFLICT",
                "Expected revision does not match the committed session head",
            ));
        }
        let (_, base_hash) = load_state(&tx, meta.current_state)?;
        if base_hash != proposal.base_state_sha256 {
            return Err(Error::new(
                "PROPOSAL_MISMATCH",
                "The current content differs from the reviewed proposal base; create a new dry run",
            ));
        }
    }
    let prepared = prepare_action(&tx, meta, request_id, expected_revision, action, control)?;
    if proposal.is_some_and(|p| p.result_state_sha256 != prepared.receipt.state_sha256) {
        return Err(Error::new(
            "PROPOSAL_MISMATCH",
            "Re-evaluating the action changed the proposed content; create a new dry run",
        ));
    }
    persist_action(&tx, &prepared)?;
    let receipt = prepared.receipt;
    save_request(&tx, &fingerprint, &receipt)?;
    #[cfg(test)]
    fault_point("before_commit");
    control.check()?;
    tx.commit().map_err(sql)?;
    #[cfg(test)]
    fault_point("after_commit");
    // Do not reinterpret a cancellation arriving after commit as an uncommitted failure.
    let tx = db.transaction().map_err(sql)?;
    let current = read_meta(&tx, session_id)?;
    response(&tx, &current, receipt, false)
}
pub fn apply_proposal(
    root: &Path,
    proposal: &Proposal,
    action: &Action,
    control: &Control,
) -> Result<Value, Error> {
    id(&proposal.session_id)?;
    id(&proposal.request_id)?;
    if proposal.version != 1
        || [
            &proposal.request_fingerprint,
            &proposal.base_state_sha256,
            &proposal.result_state_sha256,
        ]
        .iter()
        .any(|s| !crate::fonts::valid_hash(s))
    {
        return Err(Error::new(
            "INVALID_PROPOSAL",
            "Proposal version and content hashes must match the version-one dry-run contract",
        ));
    }
    if action_fingerprint(proposal.expected_revision, action)? != proposal.request_fingerprint {
        return Err(Error::new(
            "PROPOSAL_MISMATCH",
            "Action or expected revision differs from the reviewed proposal",
        ));
    }
    mutate_checked(
        root,
        &proposal.session_id,
        &proposal.request_id,
        proposal.expected_revision,
        action,
        Some(proposal),
        control,
    )
}
pub fn dry_run(
    root: &Path,
    session_id: &str,
    request_id: &str,
    expected_revision: u64,
    action: &Action,
    options: &DryRunOptions,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    id(request_id)?;
    let fingerprint = action_fingerprint(expected_revision, action)?;
    let mut db = open_mode(root, session_id, true)?;
    let tx = db.transaction().map_err(sql)?;
    let meta = read_meta(&tx, session_id)?;
    if let Some((old, _)) = request(&tx, request_id)? {
        return Err(if old == fingerprint {
            Error::new(
                "REQUEST_ALREADY_COMMITTED",
                "This request was already committed; recover it with session.receipt",
            )
        } else {
            Error::new(
                "REQUEST_ID_REUSED",
                "Request ID was already used for different content",
            )
        });
    }
    let (mut before, base_hash) = load_state(&tx, meta.current_state)?;
    before.document.revision = u64::from(meta.revision);
    let mut prepared = prepare_action(&tx, meta, request_id, expected_revision, action, control)?;
    let proposal = Proposal {
        version: 1,
        session_id: session_id.to_owned(),
        request_id: request_id.to_owned(),
        expected_revision,
        request_fingerprint: fingerprint,
        base_state_sha256: base_hash,
        result_state_sha256: prepared.receipt.state_sha256.clone(),
    };
    // Rendering/comparison has no reason to retain the database read lock.
    drop(tx);
    drop(db);
    prepared.state.document.revision = u64::from(prepared.receipt.revision);
    if options.compare_pixels {
        control.check_resource_paths(&before.resources)?;
    }
    let difference = crate::diff::compare(
        &before.document,
        &prepared.state.document,
        &before.resources,
        &prepared.state.resources,
        options.compare_pixels,
        control,
    )?;
    let mut result = json!({"dry_run":true,"committed":false,"proposal":proposal,"base_ref":{"session_root":root,"session_id":session_id,"revision":expected_revision},"predicted_receipt":prepared.receipt,"proposed_resources":prepared.state.resources,"difference":difference,"history":{"undo_depth":prepared.meta.undo.len(),"redo_depth":prepared.meta.redo.len(),"snapshot_put":prepared.snapshot_put.as_ref().map(|(s,_)|&s.name),"snapshot_remove":prepared.snapshot_remove},"apply_command":"session.apply_proposal","source_changed":false});
    if options.preview {
        result["preview"] = crate::render::png_controlled(
            &prepared.state.document,
            1,
            prepared.state.resources.asset_root.as_deref(),
            prepared.state.resources.font_root.as_deref(),
            None,
            control,
        )?;
    }
    if options.include_document {
        result["proposed_document"] = json!(prepared.state.document);
    }
    control.check()?;
    Ok(result)
}
pub fn history(
    root: &Path,
    session_id: &str,
    after: Option<u64>,
    count: usize,
) -> Result<Value, Error> {
    if !(1..=128).contains(&count) {
        return Err(Error::new(
            "INVALID_REQUEST",
            "History page size must be in 1..=128",
        ));
    }
    let mut db = open(root, session_id)?;
    let tx = db.transaction().map_err(sql)?;
    let meta = read_meta(&tx, session_id)?;
    let after = after
        .map(|v| {
            i64::try_from(v)
                .map_err(|_| Error::new("INVALID_REQUEST", "History cursor is too large"))
        })
        .transpose()?
        .unwrap_or(-1);
    let mut stmt = tx
        .prepare("SELECT request_id FROM requests WHERE revision>?1 ORDER BY revision LIMIT ?2")
        .map_err(sql)?;
    let ids: Vec<String> = stmt
        .query_map(params![after, count as u32], |r| r.get(0))
        .map_err(sql)?
        .collect::<Result<_, _>>()
        .map_err(sql)?;
    let entries: Vec<Receipt> = ids
        .iter()
        .map(|id| {
            request(&tx, id)?
                .map(|(_, r)| r)
                .ok_or_else(|| corrupt("History entry disappeared"))
        })
        .collect::<Result<_, _>>()?;
    let next = entries.last().map(|r| r.revision);
    Ok(
        json!({"session_id":session_id,"current_revision":meta.revision,"current_state_id":meta.current_state,"undo_depth":meta.undo.len(),"redo_depth":meta.redo.len(),"entries":entries,"next_after_revision":next,"has_more":next.is_some_and(|v|v<meta.revision)}),
    )
}
pub fn verify(root: &Path, session_id: &str, control: &Control) -> Result<Value, Error> {
    control.check()?;
    let mut db = open(root, session_id)?;
    let tx = db.transaction().map_err(sql)?;
    verify_connection(&tx, session_id, control)
}

fn verify_connection(tx: &Connection, session_id: &str, control: &Control) -> Result<Value, Error> {
    use sha2::{Digest, Sha256};
    control.check()?;
    let result: String = tx
        .pragma_query_value(None, "quick_check", |r| r.get(0))
        .map_err(sql)?;
    if result != "ok" {
        return Err(corrupt("SQLite integrity check failed"));
    }
    let meta = read_meta(tx, session_id)?;
    let mut digest = Sha256::new();
    digest.update(encode(&meta)?);
    let mut stmt = tx
        .prepare("SELECT id FROM states ORDER BY id")
        .map_err(sql)?;
    let ids: Vec<u32> = stmt
        .query_map([], |r| r.get(0))
        .map_err(sql)?
        .collect::<Result<_, _>>()
        .map_err(sql)?;
    let mut hashes = BTreeMap::new();
    let total: i64 = tx
        .query_row(
            "SELECT COALESCE(SUM(length(payload)),0) FROM states",
            [],
            |r| r.get(0),
        )
        .map_err(sql)?;
    if total > MAX_HISTORY_BYTES {
        return Err(corrupt("History exceeds its content storage budget"));
    }
    for state_id in &ids {
        control.check()?;
        let (_, hash) = load_state(tx, *state_id)?;
        digest.update(encode(&(state_id, &hash))?);
        hashes.insert(*state_id, hash);
    }
    let mut stmt = tx
        .prepare("SELECT request_id FROM requests ORDER BY revision")
        .map_err(sql)?;
    let ids: Vec<String> = stmt
        .query_map([], |r| r.get(0))
        .map_err(sql)?
        .collect::<Result<_, _>>()
        .map_err(sql)?;
    let mut previous_state = 0;
    let mut revision_states = Vec::new();
    for (revision, id) in ids.iter().enumerate() {
        control.check()?;
        let (fingerprint, receipt) = request(tx, id)?.unwrap();
        if receipt.revision != revision as u32
            || hashes.get(&receipt.state_id) != Some(&receipt.state_sha256)
            || receipt.from_state != previous_state
        {
            return Err(corrupt(
                "Request history does not match saved content states",
            ));
        }
        previous_state = receipt.state_id;
        revision_states.push(receipt.state_id);
        digest.update(encode(&(&fingerprint, &receipt))?);
    }
    let snapshots = snapshots(tx)?;
    for snapshot in &snapshots {
        control.check()?;
        if revision_states.get(snapshot.revision as usize) != Some(&snapshot.state_id) {
            return Err(corrupt("Named snapshot references invalid history"));
        }
        digest.update(encode(snapshot)?);
    }
    control.check()?;
    let origin = lineage::read(tx, session_id)?;
    // Empty provenance keeps v1 logical fingerprints stable across migration.
    if let Some(origin) = &origin {
        digest.update(encode(origin)?);
    }
    Ok(
        json!({"valid":true,"session_id":session_id,"revision":meta.revision,"states":hashes.len(),"requests":ids.len(),"state_bytes":total,"storage_version":storage_version(tx)?,"sqlite_version":rusqlite::version(),"journal_mode":"delete","synchronous":"full","head_state_sha256":hashes.get(&meta.current_state),"history_sha256":format!("{:x}",digest.finalize()),"undo_depth":meta.undo.len(),"redo_depth":meta.redo.len(),"snapshots":snapshots.len(),"lineage":origin}),
    )
}
#[cfg(test)]
fn fault_point(point: &str) {
    if std::env::var("INKBOLT_SESSION_FAULT").ok().as_deref() != Some(point) {
        return;
    }
    let root = PathBuf::from(std::env::var_os("INKBOLT_SESSION_FAULT_ROOT").unwrap());
    fs::write(root.join("ready"), point).unwrap();
    while !root.join("release").exists() {
        std::thread::sleep(Duration::from_millis(5));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        process::{Child, Command, Stdio},
        time::Instant,
    };

    struct TestRoot(PathBuf);
    impl TestRoot {
        fn new() -> Self {
            let base = std::env::temp_dir().canonicalize().unwrap();
            let path = base.join(format!(
                "inkbolt-session-test-{}-{}",
                std::process::id(),
                TEMP.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&path).unwrap();
            Self(path)
        }
    }
    impl Drop for TestRoot {
        fn drop(&mut self) {
            let base = std::env::temp_dir().canonicalize().unwrap();
            let target = self.0.canonicalize().unwrap();
            assert_eq!(target.parent(), Some(base.as_path()));
            assert!(
                target
                    .file_name()
                    .unwrap()
                    .to_string_lossy()
                    .starts_with("inkbolt-session-test-")
            );
            fs::remove_dir_all(target).unwrap();
        }
    }
    struct Worker(Child);
    impl Drop for Worker {
        fn drop(&mut self) {
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
    }
    fn initial(root: &Path) {
        let doc:Document=serde_json::from_value(json!({"schema_version":2,"id":"fixture","kind":"raster","width":256,"height":256,"color_space":"srgb"})).unwrap();
        create(
            root,
            "recovery",
            "create",
            &doc,
            &Resources::default(),
            &Control::default(),
        )
        .unwrap();
    }
    fn large_action() -> Action {
        // 512 KiB of original data forces dirty-page spill beyond the test cache.
        serde_json::from_value(json!({"type":"edit","operations":[{"op":"add","item":{"id":"pixels","content":{"type":"raster","width":256,"height":256,"rgba_hex":"134faaff".repeat(65536)}}}]})).unwrap()
    }
    fn spawn(root: &Path, point: &str, cancel: bool) -> Worker {
        let mut cmd = Command::new(std::env::current_exe().unwrap());
        let worker = if point.starts_with("backup_") || point.starts_with("recovery_") {
            "sessions::tests::history_worker"
        } else if point.starts_with("migration_") || point.starts_with("continuation_") {
            "sessions::tests::lineage_worker"
        } else {
            "sessions::tests::crash_worker"
        };
        cmd.args(["--exact", worker, "--nocapture"])
            .env("INKBOLT_SESSION_FAULT", point)
            .env("INKBOLT_SESSION_FAULT_ROOT", root)
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        if cancel {
            cmd.env("INKBOLT_SESSION_TEST_CANCEL", "1");
        }
        let mut worker = Worker(cmd.spawn().unwrap());
        let start = Instant::now();
        while !root.join("ready").exists() {
            assert!(
                worker.0.try_wait().unwrap().is_none(),
                "Worker exited before fault point"
            );
            assert!(
                start.elapsed() < Duration::from_secs(20),
                "Worker did not reach fault point"
            );
            std::thread::sleep(Duration::from_millis(5));
        }
        worker
    }
    fn history_fixture(root: &Path) -> Value {
        initial(root);
        mutate(
            root,
            "recovery",
            "large",
            0,
            &large_action(),
            &Control::default(),
        )
        .unwrap();
        for (revision, opacity) in [(1, 0.75), (2, 0.5)] {
            let action = serde_json::from_value(json!({"type":"edit","operations":[{"op":"properties","id":"pixels","opacity":opacity}]})).unwrap();
            mutate(
                root,
                "recovery",
                &format!("change-{revision}"),
                revision,
                &action,
                &Control::default(),
            )
            .unwrap();
        }
        let result = backup::create(
            root,
            "recovery",
            3,
            &backup::Output {
                output_root: root.to_owned(),
                file_name: "snapshot.sqlite3".into(),
            },
            &Control::default(),
        )
        .unwrap();
        fs::write(
            root.join("identity.json"),
            serde_json::to_vec(&result["backup"]).unwrap(),
        )
        .unwrap();
        result["session"].clone()
    }
    fn history_source(root: &Path) -> backup::Source {
        serde_json::from_slice(&fs::read(root.join("identity.json")).unwrap()).unwrap()
    }
    fn history_target(root: &Path, point: &str) -> PathBuf {
        if point.starts_with("backup_") {
            root.join("result.sqlite3")
        } else {
            store_path(&root.join("restored"), "recovery").unwrap()
        }
    }
    fn finish(worker: &mut Worker) {
        let start = Instant::now();
        loop {
            if let Some(status) = worker.0.try_wait().unwrap() {
                assert!(status.success());
                break;
            }
            assert!(start.elapsed() < Duration::from_secs(20));
            std::thread::sleep(Duration::from_millis(5));
        }
    }
    fn orphans(root: &Path) -> BTreeMap<PathBuf, Vec<u8>> {
        let mut result = BTreeMap::new();
        for parent in [root.to_owned(), root.join("restored")] {
            if !parent.exists() {
                continue;
            }
            for entry in fs::read_dir(parent).unwrap() {
                let path = entry.unwrap().path();
                if path
                    .file_name()
                    .unwrap()
                    .to_string_lossy()
                    .starts_with(".inkbolt-session-")
                {
                    result.insert(path.clone(), fs::read(path).unwrap());
                }
            }
        }
        result
    }
    #[test]
    fn history_worker() {
        let Some(root) = std::env::var_os("INKBOLT_SESSION_FAULT_ROOT") else {
            return;
        };
        let root = PathBuf::from(root);
        let point = std::env::var("INKBOLT_SESSION_FAULT").unwrap();
        let cancelled = std::env::var_os("INKBOLT_SESSION_TEST_CANCEL").is_some();
        let control = Control::new(&crate::control::Options {
            timeout_ms: None,
            cancel_file: cancelled.then(|| root.join("cancel")),
        })
        .unwrap();
        let request = if point.starts_with("backup_") {
            crate::Request::SessionBackup {
                session_root: root.clone(),
                session_id: "recovery".into(),
                expected_revision: 3,
                output: backup::Output {
                    output_root: root.clone(),
                    file_name: "result.sqlite3".into(),
                },
                receipt: None,
                control: Default::default(),
            }
        } else {
            crate::Request::SessionRecover {
                session_root: root.join("restored"),
                session_id: "recovery".into(),
                source: history_source(&root),
                receipt: None,
                control: Default::default(),
            }
        };
        let result = crate::execute_controlled(request, &control);
        if cancelled && !point.ends_with("after_publish") {
            assert_eq!(result.unwrap_err().code, "CANCELLED");
        } else {
            assert_eq!(result.unwrap()["created"], true);
        }
    }
    #[test]
    fn history_copies_survive_actual_process_termination_at_each_boundary() {
        for point in [
            "backup_during_copy",
            "backup_before_publish",
            "backup_after_publish",
            "recovery_during_copy",
            "recovery_before_publish",
            "recovery_after_publish",
        ] {
            let root = TestRoot::new();
            let expected = history_fixture(&root.0);
            let source = store_path(&root.0, "recovery").unwrap();
            let original = fs::read(&source).unwrap();
            let original_backup = fs::read(root.0.join("snapshot.sqlite3")).unwrap();
            let mut worker = spawn(&root.0, point, false);
            worker.0.kill().unwrap();
            worker.0.wait().unwrap();
            assert_eq!(fs::read(&source).unwrap(), original);
            assert_eq!(
                fs::read(root.0.join("snapshot.sqlite3")).unwrap(),
                original_backup
            );
            let target = history_target(&root.0, point);
            assert_eq!(target.exists(), point.ends_with("after_publish"));
            let retained = orphans(&root.0);
            assert!(!retained.is_empty());
            if point.ends_with("after_publish") {
                let db =
                    Connection::open_with_flags(&target, OpenFlags::SQLITE_OPEN_READ_ONLY).unwrap();
                configure(&db).unwrap();
                check_schema(&db).unwrap();
                assert_eq!(
                    verify_connection(&db, "recovery", &Control::default()).unwrap(),
                    expected
                );
                if point.starts_with("recovery_") {
                    assert_eq!(fs::read(&target).unwrap(), original_backup);
                }
            } else if point.starts_with("backup_") {
                backup::create(
                    &root.0,
                    "recovery",
                    3,
                    &backup::Output {
                        output_root: root.0.clone(),
                        file_name: "result.sqlite3".into(),
                    },
                    &Control::default(),
                )
                .unwrap();
            } else {
                backup::recover(
                    &root.0.join("restored"),
                    "recovery",
                    &history_source(&root.0),
                    &Control::default(),
                )
                .unwrap();
            }
            assert_eq!(
                orphans(&root.0),
                retained,
                "Retries must preserve orphan evidence owned by the killed process"
            );
        }
    }
    fn lineage_request(root: &Path, point: &str) -> crate::Request {
        if point.starts_with("migration_") {
            crate::Request::SessionMigrate {
                session_id: "recovery".into(),
                source: history_source(root),
                target_version: 2,
                output: backup::Output {
                    output_root: root.to_owned(),
                    file_name: "migrated.sqlite3".into(),
                },
                receipt: None,
                control: Default::default(),
            }
        } else {
            crate::Request::SessionContinue {
                session_root: root.join("restored"),
                session_id: "continued".into(),
                request_id: "continue".into(),
                parent: lineage::Parent {
                    source: history_source(root),
                    session_id: "recovery".into(),
                    revision: 1,
                },
                control: Default::default(),
            }
        }
    }
    #[test]
    fn lineage_worker() {
        let Some(root) = std::env::var_os("INKBOLT_SESSION_FAULT_ROOT") else {
            return;
        };
        let root = PathBuf::from(root);
        let point = std::env::var("INKBOLT_SESSION_FAULT").unwrap();
        let cancelled = std::env::var_os("INKBOLT_SESSION_TEST_CANCEL").is_some();
        let control = Control::new(&crate::control::Options {
            timeout_ms: None,
            cancel_file: cancelled.then(|| root.join("cancel")),
        })
        .unwrap();
        let result = crate::execute_controlled(lineage_request(&root, &point), &control);
        if cancelled && !point.ends_with("after_publish") {
            assert_eq!(result.unwrap_err().code, "CANCELLED");
        } else {
            assert!(result.is_ok(), "{result:?}");
        }
    }
    #[test]
    fn migration_and_continuation_survive_crash_and_cancellation_through_executor() {
        for cancel in [false, true] {
            for point in [
                "migration_during_copy",
                "migration_after_schema",
                "migration_before_publish",
                "migration_after_publish",
                "continuation_during_copy",
                "continuation_after_capture",
                "continuation_before_publish",
                "continuation_after_publish",
            ] {
                let root = TestRoot::new();
                let mut expected = history_fixture(&root.0);
                let backup_path = root.0.join("snapshot.sqlite3");
                // Original synthetic source with the exact former table schema.
                let db = backup::open_copy(&backup_path, false).unwrap();
                db.execute_batch("DROP TABLE lineage; PRAGMA user_version=1;")
                    .unwrap();
                db.close().unwrap();
                let source = backup::identity(&backup_path, &Control::default()).unwrap();
                fs::write(root.0.join("identity.json"), encode(&source).unwrap()).unwrap();
                let source_bytes = fs::read(&backup_path).unwrap();
                let live_path = store_path(&root.0, "recovery").unwrap();
                let live_bytes = fs::read(&live_path).unwrap();
                let mut worker = spawn(&root.0, point, cancel);
                if cancel {
                    fs::write(root.0.join("cancel"), b"stop").unwrap();
                    fs::write(root.0.join("release"), b"release").unwrap();
                    finish(&mut worker);
                } else {
                    worker.0.kill().unwrap();
                    worker.0.wait().unwrap();
                }
                assert_eq!(fs::read(&backup_path).unwrap(), source_bytes);
                assert_eq!(fs::read(&live_path).unwrap(), live_bytes);
                let target = if point.starts_with("migration_") {
                    root.0.join("migrated.sqlite3")
                } else {
                    store_path(&root.0.join("restored"), "continued").unwrap()
                };
                let committed = point.ends_with("after_publish");
                assert_eq!(target.exists(), committed, "{point}");
                let retained = orphans(&root.0);
                assert_eq!(retained.is_empty(), cancel);
                let retry = crate::execute(lineage_request(&root.0, point));
                if point.starts_with("migration_") {
                    if committed {
                        assert_eq!(retry.unwrap_err().code, "OUTPUT_EXISTS");
                    } else {
                        retry.unwrap();
                    }
                    expected["storage_version"] = json!(2);
                    assert_eq!(
                        backup::inspect(&target, "recovery", &Control::default()).unwrap(),
                        expected
                    );
                } else {
                    let result = retry.unwrap();
                    assert_eq!(result["replayed"], committed);
                    assert_eq!(result["lineage"]["parent"]["revision"], 1);
                    assert_eq!(result["lineage"]["source_storage_version"], 1);
                    assert_eq!(result["document"]["items"][0]["opacity"], 1.0);
                    assert_eq!(
                        verify(&root.0.join("restored"), "continued", &Control::default()).unwrap()
                            ["states"],
                        1
                    );
                }
                assert_eq!(
                    orphans(&root.0),
                    retained,
                    "Retry must preserve old owned evidence"
                );
            }
        }
    }
    #[test]
    fn full_history_can_continue_without_evicting_a_single_state() {
        let root = TestRoot::new();
        let doc:Document=serde_json::from_value(json!({"schema_version":2,"id":"fixture","kind":"vector","width":2,"height":2,"color_space":"srgb","items":[{"id":"box","content":{"type":"vector","geometry":{"shape":"rect","x":0,"y":0,"width":1,"height":1},"fill":[1,2,3,255]}}]})).unwrap();
        create(
            &root.0,
            "full",
            "create",
            &doc,
            &Resources::default(),
            &Control::default(),
        )
        .unwrap();
        let action = |n: usize| {
            serde_json::from_value(json!({"type":"edit","operations":[{"op":"properties","id":"box","name":format!("name-{n}")}]})).unwrap()
        };
        for n in 1..MAX_STATES {
            mutate(
                &root.0,
                "full",
                &format!("r-{n}"),
                (n - 1) as u64,
                &action(n),
                &Control::default(),
            )
            .unwrap();
        }
        assert_eq!(
            mutate(
                &root.0,
                "full",
                "over",
                255,
                &action(256),
                &Control::default()
            )
            .unwrap_err()
            .code,
            "HISTORY_LIMIT"
        );
        let path = store_path(&root.0, "full").unwrap();
        let original = fs::read(&path).unwrap();
        let result = backup::create(
            &root.0,
            "full",
            255,
            &backup::Output {
                output_root: root.0.clone(),
                file_name: "full.sqlite3".into(),
            },
            &Control::default(),
        )
        .unwrap();
        let parent = lineage::Parent {
            source: serde_json::from_value(result["backup"].clone()).unwrap(),
            session_id: "full".into(),
            revision: 255,
        };
        lineage::continue_from(&root.0, "next", "continue", &parent, &Control::default()).unwrap();
        mutate(
            &root.0,
            "next",
            "next-edit",
            0,
            &action(256),
            &Control::default(),
        )
        .unwrap();
        assert_eq!(
            verify(&root.0, "next", &Control::default()).unwrap()["states"],
            2
        );
        assert_eq!(fs::read(&path).unwrap(), original);
    }
    #[test]
    fn history_cancellation_discards_unpublished_copies_but_keeps_committed_success() {
        for point in [
            "backup_during_copy",
            "backup_before_publish",
            "backup_after_publish",
            "recovery_during_copy",
            "recovery_before_publish",
            "recovery_after_publish",
        ] {
            let root = TestRoot::new();
            history_fixture(&root.0);
            let path = store_path(&root.0, "recovery").unwrap();
            let original = fs::read(&path).unwrap();
            let original_backup = fs::read(root.0.join("snapshot.sqlite3")).unwrap();
            let mut worker = spawn(&root.0, point, true);
            fs::write(root.0.join("cancel"), b"stop").unwrap();
            fs::write(root.0.join("release"), b"release").unwrap();
            finish(&mut worker);
            assert_eq!(
                history_target(&root.0, point).exists(),
                point.ends_with("after_publish")
            );
            assert_eq!(fs::read(path).unwrap(), original);
            assert_eq!(
                fs::read(root.0.join("snapshot.sqlite3")).unwrap(),
                original_backup
            );
            assert!(orphans(&root.0).is_empty());
        }
    }
    #[test]
    fn pinned_backup_blocks_commit_then_writer_retries_without_changing_the_copy() {
        let root = TestRoot::new();
        let expected = history_fixture(&root.0);
        let mut worker = spawn(&root.0, "backup_during_copy", false);
        let action = serde_json::from_value(
            json!({"type":"edit","operations":[{"op":"properties","id":"pixels","name":"new"}]}),
        )
        .unwrap();
        assert_eq!(
            mutate(
                &root.0,
                "recovery",
                "writer",
                3,
                &action,
                &Control::default()
            )
            .unwrap_err()
            .code,
            "SESSION_BUSY"
        );
        fs::write(root.0.join("release"), b"release").unwrap();
        finish(&mut worker);
        mutate(
            &root.0,
            "recovery",
            "writer",
            3,
            &action,
            &Control::default(),
        )
        .unwrap();
        let target = root.0.join("result.sqlite3");
        let db = Connection::open_with_flags(target, OpenFlags::SQLITE_OPEN_READ_ONLY).unwrap();
        configure(&db).unwrap();
        assert_eq!(
            verify_connection(&db, "recovery", &Control::default()).unwrap(),
            expected
        );
        assert_eq!(
            verify(&root.0, "recovery", &Control::default()).unwrap()["revision"],
            4
        );
    }
    #[test]
    fn read_only_backup_and_comparisons_preserve_hot_journal_until_explicit_recovery() {
        let root = TestRoot::new();
        initial(&root.0);
        let mut worker = spawn(&root.0, "before_commit", false);
        worker.0.kill().unwrap();
        worker.0.wait().unwrap();
        let path = store_path(&root.0, "recovery").unwrap();
        let journal = PathBuf::from(format!("{}-journal", path.display()));
        let bytes = fs::read(&path).unwrap();
        let undo = fs::read(&journal).unwrap();
        assert_ne!(&undo[..8], &[0; 8]);
        assert!(
            backup::create(
                &root.0,
                "recovery",
                0,
                &backup::Output {
                    output_root: root.0.clone(),
                    file_name: "result.sqlite3".into()
                },
                &Control::default()
            )
            .is_err()
        );
        assert!(compare(&root.0, "recovery", 0, 0, false, &Control::default()).is_err());
        assert!(
            compare_preview(
                &root.0,
                "recovery",
                0,
                0,
                &Default::default(),
                &Control::default()
            )
            .is_err()
        );
        assert_eq!(fs::read(&path).unwrap(), bytes);
        assert_eq!(fs::read(&journal).unwrap(), undo);
        assert_eq!(
            verify(&root.0, "recovery", &Control::default()).unwrap()["revision"],
            0
        );
        backup::create(
            &root.0,
            "recovery",
            0,
            &backup::Output {
                output_root: root.0.clone(),
                file_name: "result.sqlite3".into(),
            },
            &Control::default(),
        )
        .unwrap();
    }
    #[test]
    fn crash_worker() {
        let Some(root) = std::env::var_os("INKBOLT_SESSION_FAULT_ROOT") else {
            return;
        };
        let root = PathBuf::from(root);
        let cancelled = std::env::var_os("INKBOLT_SESSION_TEST_CANCEL").is_some();
        let control = Control::new(&crate::control::Options {
            timeout_ms: None,
            cancel_file: cancelled.then(|| root.join("cancel")),
        })
        .unwrap();
        let result = mutate(
            &root,
            "recovery",
            "large-edit",
            0,
            &large_action(),
            &control,
        );
        if cancelled {
            assert_eq!(result.unwrap_err().code, "CANCELLED");
        } else {
            result.unwrap();
        }
    }
    #[test]
    fn killed_uncommitted_writer_recovers_last_state_and_retry_applies_once() {
        let root = TestRoot::new();
        initial(&root.0);
        let before = read(&root.0, "recovery", None).unwrap();
        let mut worker = spawn(&root.0, "before_commit", false);
        let dbpath = store_path(&root.0, "recovery").unwrap();
        let journal = PathBuf::from(format!("{}-journal", dbpath.display()));
        let bytes = fs::read(&journal).unwrap();
        assert!(bytes.len() > 4096);
        assert_ne!(
            &bytes[..8],
            &[0; 8],
            "Journal must be hot before simulated crash"
        );
        worker.0.kill().unwrap();
        worker.0.wait().unwrap();
        assert_eq!(read(&root.0, "recovery", None).unwrap(), before);
        assert_eq!(
            receipt(&root.0, "recovery", "large-edit").unwrap_err().code,
            "REQUEST_NOT_FOUND"
        );
        let committed = mutate(
            &root.0,
            "recovery",
            "large-edit",
            0,
            &large_action(),
            &Control::default(),
        )
        .unwrap();
        assert_eq!(committed["document"]["items"].as_array().unwrap().len(), 1);
        let replay = mutate(
            &root.0,
            "recovery",
            "large-edit",
            0,
            &large_action(),
            &Control::default(),
        )
        .unwrap();
        assert_eq!(replay["receipt"], committed["receipt"]);
        assert_eq!(replay["replayed"], true);
        assert_eq!(
            verify(&root.0, "recovery", &Control::default()).unwrap()["requests"],
            2
        );
    }
    #[test]
    fn killed_committed_writer_reopens_and_returns_original_receipt() {
        let root = TestRoot::new();
        initial(&root.0);
        let mut worker = spawn(&root.0, "after_commit", false);
        worker.0.kill().unwrap();
        worker.0.wait().unwrap();
        let stored = read(&root.0, "recovery", None).unwrap();
        assert_eq!(stored["current_revision"], 1);
        let replay = mutate(
            &root.0,
            "recovery",
            "large-edit",
            0,
            &large_action(),
            &Control::default(),
        )
        .unwrap();
        assert_eq!(replay["replayed"], true);
        assert_eq!(replay["document"], stored["document"]);
        assert_eq!(
            verify(&root.0, "recovery", &Control::default()).unwrap()["requests"],
            2
        );
    }
    #[test]
    fn cancellation_after_dirty_page_spill_rolls_back_entire_batch() {
        let root = TestRoot::new();
        initial(&root.0);
        let before = read(&root.0, "recovery", None).unwrap();
        let mut worker = spawn(&root.0, "before_commit", true);
        fs::write(root.0.join("cancel"), b"cancel").unwrap();
        fs::write(root.0.join("release"), b"release").unwrap();
        let start = Instant::now();
        let status = loop {
            if let Some(status) = worker.0.try_wait().unwrap() {
                break status;
            }
            assert!(start.elapsed() < Duration::from_secs(20));
            std::thread::sleep(Duration::from_millis(5));
        };
        assert!(status.success());
        assert_eq!(read(&root.0, "recovery", None).unwrap(), before);
        assert_eq!(
            verify(&root.0, "recovery", &Control::default()).unwrap()["requests"],
            1
        );
    }
    #[test]
    fn shared_cancellation_token_and_state_budget_fail_without_mutation() {
        let root = TestRoot::new();
        initial(&root.0);
        let control = Control::default();
        control.clone().cancel();
        assert_eq!(
            mutate(
                &root.0,
                "recovery",
                "cancelled",
                0,
                &large_action(),
                &control
            )
            .unwrap_err()
            .code,
            "CANCELLED"
        );
        let mut db = open(&root.0, "recovery").unwrap();
        let tx = db.transaction().unwrap();
        let (state, _) = load_state(&tx, 0).unwrap();
        for n in 1..MAX_STATES {
            put_state(&tx, n as u32, &state).unwrap();
        }
        assert_eq!(
            put_state(&tx, MAX_STATES as u32, &state).unwrap_err().code,
            "HISTORY_LIMIT"
        );
        drop(tx);
        drop(db);
        assert_eq!(
            verify(&root.0, "recovery", &Control::default()).unwrap()["states"],
            1
        );
    }

    #[test]
    fn aggregate_history_budget_rejects_growth_without_evicting_saved_states() {
        let root = TestRoot::new();
        initial(&root.0);
        let mut db = open(&root.0, "recovery").unwrap();
        let tx = db.transaction().unwrap();
        let (mut state, _) = load_state(&tx, 0).unwrap();
        let Action::Edit { operations, .. } = large_action() else {
            unreachable!()
        };
        state.document = edit::apply(&state.document, 0, &operations)
            .unwrap()
            .document;
        state.document.revision = 0;
        let size = encode(&state).unwrap().len() as i64;
        let initial_bytes: i64 = tx
            .query_row("SELECT length(payload) FROM states WHERE id=0", [], |r| {
                r.get(0)
            })
            .unwrap();
        let capacity = ((MAX_HISTORY_BYTES - initial_bytes) / size) as u32;
        assert!(capacity < MAX_STATES as u32 - 1);
        for n in 1..=capacity {
            put_state(&tx, n, &state).unwrap();
        }
        assert_eq!(
            put_state(&tx, capacity + 1, &state).unwrap_err().code,
            "HISTORY_LIMIT"
        );
        let count: u32 = tx
            .query_row("SELECT COUNT(*) FROM states", [], |r| r.get(0))
            .unwrap();
        assert_eq!(count, capacity + 1);
        assert!(load_state(&tx, 0).unwrap().0.document.items.is_empty());
        assert_eq!(
            load_state(&tx, capacity).unwrap().0.document,
            state.document
        );
        drop(tx);
        drop(db);
        assert_eq!(
            verify(&root.0, "recovery", &Control::default()).unwrap()["states"],
            1
        );
    }
}
