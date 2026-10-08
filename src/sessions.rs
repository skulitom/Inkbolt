//! Local transactional sessions with immutable content states, saved history and retry receipts.
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
pub const STORE_VERSION: i64 = 1;
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
fn check_schema(db: &Connection) -> Result<(), Error> {
    let app: i64 = db
        .pragma_query_value(None, "application_id", |r| r.get(0))
        .map_err(sql)?;
    let version: i64 = db
        .pragma_query_value(None, "user_version", |r| r.get(0))
        .map_err(sql)?;
    if app != APPLICATION_ID || version != STORE_VERSION {
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
    if actual.len() != SCHEMA.len()
        || actual.iter().any(|(name, kind, text)| {
            kind != "table" || !SCHEMA.iter().any(|(n, s)| *n == name && *s == text)
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
        OpenFlags::SQLITE_OPEN_READ_WRITE
            | OpenFlags::SQLITE_OPEN_NO_MUTEX
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
            "Session history is full; export a snapshot and start a new session without deleting this history",
        ));
    }
    let hash = assets::sha256(&bytes);
    db.execute(
        "INSERT INTO states(id,payload,sha256) VALUES(?1,?2,?3)",
        params![state_id, bytes, hash],
    )
    .map_err(sql)?;
    Ok(hash)
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
        json!({"session_id":meta.session_id,"receipt":receipt,"replayed":replayed,"current_revision":meta.revision,"current_state_id":meta.current_state,"document":state.document,"resources":state.resources}),
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
    model::validate_controlled(document, control)?;
    resources.validate()?;
    let fingerprint = assets::sha256(&encode(
        &json!({"type":"create","document":document,"resources":resources}),
    )?);
    let existing = || -> Result<Value, Error> {
        let mut db = open(root, session_id)?;
        let tx = db.transaction().map_err(sql)?;
        let meta = read_meta(&tx, session_id)?;
        let Some((old, receipt)) = request(&tx, request_id)? else {
            return Err(Error::new(
                "SESSION_EXISTS",
                "Session ID already exists; existing data is preserved",
            ));
        };
        if old != fingerprint || receipt.action != "create" {
            return Err(Error::new(
                "REQUEST_ID_REUSED",
                "Request ID was already used for different content",
            ));
        }
        response(&tx, &meta, receipt, true)
    };
    if target
        .try_exists()
        .map_err(|_| Error::new("IO_ERROR", "Unable to inspect session destination"))?
    {
        return existing();
    }
    control.check()?;
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
    let mut state = State {
        document: document.clone(),
        resources: resources.clone(),
    };
    state.document.schema_version = 2;
    state.document.revision = 0;
    let hash = put_state(&tx, 0, &state)?;
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
        action: "create".into(),
        label: String::new(),
        from_state: 0,
        state_id: 0,
        state_sha256: hash,
        changes: Vec::new(),
    };
    save_request(&tx, &fingerprint, &receipt)?;
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
    match fs::hard_link(&temp.0, &target) {
        Ok(()) => {}
        Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => return existing(),
        Err(_) => {
            return Err(Error::new(
                "SESSION_STORE_ERROR",
                "Session root must support create-only hard-link publication",
            ));
        }
    }
    let mut db = open(root, session_id)?;
    let tx = db.transaction().map_err(sql)?;
    let current = read_meta(&tx, session_id)?;
    response(&tx, &current, receipt, false)
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
        json!({"session_id":session_id,"revision":revision,"current_revision":meta.revision,"state_id":state_id,"state_sha256":hash,"document":state.document,"resources":state.resources,"undo_depth":meta.undo.len(),"redo_depth":meta.redo.len(),"snapshots":names}),
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
pub fn compare(
    root: &Path,
    session_id: &str,
    from_revision: u64,
    to_revision: u64,
    compare_pixels: bool,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    let mut db = open(root, session_id)?;
    let tx = db.transaction().map_err(sql)?;
    let meta = read_meta(&tx, session_id)?;
    let before = revision_state(&tx, from_revision, &meta)?;
    let after = revision_state(&tx, to_revision, &meta)?;
    // Release the read lock before rendering; both captured states remain immutable.
    drop(tx);
    drop(db);
    let mut result = crate::diff::compare(
        &before.document,
        &after.document,
        &before.resources,
        &after.resources,
        compare_pixels,
        control,
    )?;
    result["session_id"] = json!(session_id);
    result["observed_current_revision"] = json!(meta.revision);
    Ok(result)
}
pub fn publish(
    root: &Path,
    session_id: &str,
    expected_revision: u64,
    options: &crate::publish::Options,
    control: &Control,
) -> Result<Value, Error> {
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
    drop(tx);
    drop(db);
    let mut result = crate::publish::publish(&state.document, &state.resources, options, control)?;
    result["session_id"] = json!(session_id);
    result["observed_current_revision"] = json!(meta.revision);
    Ok(result)
}
pub fn mutate(
    root: &Path,
    session_id: &str,
    request_id: &str,
    expected_revision: u64,
    action: &Action,
    control: &Control,
) -> Result<Value, Error> {
    id(request_id)?;
    let fingerprint = assets::sha256(&encode(
        &json!({"expected_revision":expected_revision,"action":action}),
    )?);
    let mut db = open(root, session_id)?;
    let tx = db
        .transaction_with_behavior(TransactionBehavior::Immediate)
        .map_err(sql)?;
    let mut meta = read_meta(&tx, session_id)?;
    if let Some((old, receipt)) = request(&tx, request_id)? {
        if old != fingerprint {
            return Err(Error::new(
                "REQUEST_ID_REUSED",
                "Request ID was already used for different content",
            ));
        }
        return response(&tx, &meta, receipt, true);
    }
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
    let (mut state, _) = load_state(&tx, meta.current_state)?;
    let mut changes = Vec::new();
    let mut label = String::new();
    let kind = match action {
        Action::Edit {
            operations,
            label: requested,
        } => {
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
            put_state(&tx, next, &state)?;
            meta.undo.push(from_state);
            meta.redo.clear();
            meta.current_state = next;
            "edit"
        }
        Action::Resources { resources } => {
            resources.validate()?;
            state.resources = resources.clone();
            put_state(&tx, next, &state)?;
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
            let names = snapshots(&tx)?;
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
            tx.execute(
                "INSERT INTO snapshots(name,state_id,revision,sha256) VALUES(?1,?2,?3,?4)",
                params![name, meta.current_state, next, hash],
            )
            .map_err(sql)?;
            label = name.clone();
            "snapshot"
        }
        Action::Restore { name } => {
            id(name)?;
            let names = snapshots(&tx)?;
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
            if !snapshots(&tx)?.iter().any(|s| s.name == *name) {
                return Err(Error::new(
                    "SNAPSHOT_NOT_FOUND",
                    "Named snapshot does not exist",
                ));
            }
            tx.execute("DELETE FROM snapshots WHERE name=?1", [name])
                .map_err(sql)?;
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
    let (_, hash) = load_state(&tx, meta.current_state)?;
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
    save_meta(&tx, &meta)?;
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
    let result: String = tx
        .pragma_query_value(None, "quick_check", |r| r.get(0))
        .map_err(sql)?;
    if result != "ok" {
        return Err(corrupt("SQLite integrity check failed"));
    }
    let meta = read_meta(&tx, session_id)?;
    let mut stmt = tx
        .prepare("SELECT id FROM states ORDER BY id")
        .map_err(sql)?;
    let ids: Vec<u32> = stmt
        .query_map([], |r| r.get(0))
        .map_err(sql)?
        .collect::<Result<_, _>>()
        .map_err(sql)?;
    let mut hashes = BTreeMap::new();
    let mut total = 0;
    for state_id in &ids {
        control.check()?;
        let (state, hash) = load_state(&tx, *state_id)?;
        total += encode(&state)?.len();
        hashes.insert(*state_id, hash);
    }
    if total as i64 > MAX_HISTORY_BYTES {
        return Err(corrupt("History exceeds its content storage budget"));
    }
    let mut stmt = tx
        .prepare("SELECT request_id FROM requests ORDER BY revision")
        .map_err(sql)?;
    let ids: Vec<String> = stmt
        .query_map([], |r| r.get(0))
        .map_err(sql)?
        .collect::<Result<_, _>>()
        .map_err(sql)?;
    for (revision, id) in ids.iter().enumerate() {
        control.check()?;
        let (_, receipt) = request(&tx, id)?.unwrap();
        if receipt.revision != revision as u32
            || hashes.get(&receipt.state_id) != Some(&receipt.state_sha256)
            || !hashes.contains_key(&receipt.from_state)
        {
            return Err(corrupt(
                "Request history does not match saved content states",
            ));
        }
    }
    for snapshot in snapshots(&tx)? {
        if !hashes.contains_key(&snapshot.state_id) || snapshot.revision > meta.revision {
            return Err(corrupt("Named snapshot references invalid history"));
        }
    }
    Ok(
        json!({"valid":true,"session_id":session_id,"revision":meta.revision,"states":hashes.len(),"requests":ids.len(),"state_bytes":total,"storage_version":STORE_VERSION,"sqlite_version":rusqlite::version(),"journal_mode":"delete","synchronous":"full"}),
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
        cmd.args(["--exact", "sessions::tests::crash_worker", "--nocapture"])
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
