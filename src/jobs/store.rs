//! Strict, checksummed queue storage. Immutable inputs are separate from progress.
use super::*;
use rusqlite::{Connection, OpenFlags, OptionalExtension, limits::Limit, params};
use std::{
    fs::{self, OpenOptions},
    io::Read,
    sync::atomic::{AtomicU64, Ordering},
};

const APP: u32 = 0x494e4b4a;
const DATABASE_BYTES: u64 = 512 * 1024 * 1024;
const INPUTS: &str =
    "CREATE TABLE inputs(id TEXT PRIMARY KEY, payload BLOB NOT NULL, sha256 TEXT NOT NULL) STRICT";
const JOBS: &str = "CREATE TABLE jobs(id TEXT PRIMARY KEY REFERENCES inputs(id), state BLOB NOT NULL, state_sha256 TEXT NOT NULL) STRICT";
const RUNTIME: &str = "CREATE TABLE runtime(id INTEGER PRIMARY KEY CHECK(id=1), payload BLOB NOT NULL, sha256 TEXT NOT NULL) STRICT";
static NEXT: AtomicU64 = AtomicU64::new(0);
pub(super) fn sql(error: rusqlite::Error) -> Error {
    match error.sqlite_error_code() {
        Some(rusqlite::ErrorCode::DatabaseBusy | rusqlite::ErrorCode::DatabaseLocked) => {
            err("JOB_BUSY", "Job store is busy; retry the same request")
        }
        Some(rusqlite::ErrorCode::DatabaseCorrupt | rusqlite::ErrorCode::NotADatabase) => {
            corrupt("Job database is corrupt")
        }
        Some(rusqlite::ErrorCode::DiskFull | rusqlite::ErrorCode::TooBig) => {
            err("JOB_LIMIT", "Job storage or available disk space exhausted")
        }
        _ => err(
            "JOB_STORE_ERROR",
            "Unable to complete job storage; inspect the original job before retrying",
        ),
    }
}
fn connection(path: &Path) -> Result<Connection, Error> {
    let db = Connection::open_with_flags(
        path,
        OpenFlags::SQLITE_OPEN_READ_WRITE
            | OpenFlags::SQLITE_OPEN_NO_MUTEX
            | OpenFlags::SQLITE_OPEN_NOFOLLOW,
    )
    .map_err(sql)?;
    db.busy_timeout(Duration::from_millis(250)).map_err(sql)?;
    db.set_limit(
        Limit::SQLITE_LIMIT_LENGTH,
        (MAX_INPUT_BYTES + MAX_STATE_BYTES + 16384) as i32,
    )
    .map_err(sql)?;
    db.set_limit(Limit::SQLITE_LIMIT_SQL_LENGTH, 16384)
        .map_err(sql)?;
    db.set_limit(Limit::SQLITE_LIMIT_COLUMN, 32).map_err(sql)?;
    db.set_limit(Limit::SQLITE_LIMIT_ATTACHED, 0).map_err(sql)?;
    db.execute_batch("PRAGMA synchronous=FULL; PRAGMA trusted_schema=OFF; PRAGMA recursive_triggers=OFF; PRAGMA foreign_keys=ON; PRAGMA cache_size=-4096; PRAGMA temp_store=MEMORY;").map_err(sql)?;
    Ok(db)
}
struct Temp(PathBuf);
impl Temp {
    fn new(root: &Path) -> Result<Self, Error> {
        for _ in 0..64 {
            let path = root.join(format!(
                ".inkbolt-jobs-{}-{}.tmp",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            match OpenOptions::new().create_new(true).write(true).open(&path) {
                Ok(_) => return Ok(Self(path)),
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {}
                Err(_) => return Err(err("IO_ERROR", "Unable to reserve new job database")),
            }
        }
        Err(err("IO_ERROR", "Job database staging-name limit exceeded"))
    }
}
impl Drop for Temp {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.0);
        let mut journal = self.0.as_os_str().to_owned();
        journal.push("-journal");
        let _ = fs::remove_file(PathBuf::from(journal));
    }
}
pub(super) fn open(
    root: &Path,
    create: Option<&job_process::Executable>,
) -> Result<Option<Connection>, Error> {
    assets::absolute(root)?;
    let path = root.join("jobs.sqlite3");
    match fs::symlink_metadata(&path) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            let Some(executable) = create else {
                return Ok(None);
            };
            for suffix in ["-journal", "-wal", "-shm"] {
                publish::exists(&root.join(format!("jobs.sqlite3{suffix}")))?;
            }
            fs::create_dir_all(root).map_err(|_| err("IO_ERROR", "Unable to create job root"))?;
            let temp = Temp::new(root)?;
            let mut db = connection(&temp.0)?;
            db.execute_batch("PRAGMA page_size=4096; PRAGMA journal_mode=DELETE;")
                .map_err(sql)?;
            db.pragma_update(None, "application_id", APP).map_err(sql)?;
            db.pragma_update(None, "user_version", 1).map_err(sql)?;
            let tx = db.transaction().map_err(sql)?;
            tx.execute_batch(INPUTS).map_err(sql)?;
            tx.execute_batch(JOBS).map_err(sql)?;
            tx.execute_batch(RUNTIME).map_err(sql)?;
            let runtime = Runtime {
                version: 1,
                generation: 0,
                executable: executable.clone(),
                owner: None,
            };
            let payload = encode(&runtime, 16384)?;
            tx.execute(
                "INSERT INTO runtime VALUES(1,?1,?2)",
                params![payload, assets::sha256(&payload)],
            )
            .map_err(sql)?;
            tx.commit().map_err(sql)?;
            db.close().map_err(|(_, e)| sql(e))?;
            OpenOptions::new()
                .read(true)
                .write(true)
                .open(&temp.0)
                .and_then(|f| f.sync_all())
                .map_err(|_| err("IO_ERROR", "Unable to flush new job database"))?;
            match fs::hard_link(&temp.0, &path) {
                Ok(()) => {}
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {}
                Err(_) => {
                    return Err(err(
                        "IO_ERROR",
                        "Job root must support create-only hard links",
                    ));
                }
            }
        }
        Err(_) => return Err(err("IO_ERROR", "Unable to inspect job database")),
        Ok(_) => {}
    }
    let metadata = fs::symlink_metadata(&path)
        .map_err(|_| err("IO_ERROR", "Unable to inspect job database"))?;
    if !metadata.is_file() || metadata.file_type().is_symlink() || metadata.len() > DATABASE_BYTES {
        return Err(corrupt("Invalid job database file"));
    }
    // Do not let SQLite recover an unrelated file or its journal.
    let mut header = [0u8; 100];
    fs::File::open(&path)
        .and_then(|mut f| f.read_exact(&mut header))
        .map_err(|_| err("JOB_FORMAT", "Job database header is incomplete"))?;
    if &header[..16] != b"SQLite format 3\0"
        || u32::from_be_bytes(header[68..72].try_into().unwrap()) != APP
        || u32::from_be_bytes(header[60..64].try_into().unwrap()) != 1
    {
        return Err(err(
            "JOB_FORMAT",
            "Unknown job database; existing files and journals are preserved",
        ));
    }
    let db = connection(&path)?;
    let application: i64 = db
        .pragma_query_value(None, "application_id", |r| r.get(0))
        .map_err(sql)?;
    let version: i64 = db
        .pragma_query_value(None, "user_version", |r| r.get(0))
        .map_err(sql)?;
    let mode: String = db
        .pragma_query_value(None, "journal_mode", |r| r.get(0))
        .map_err(sql)?;
    let page_size: i64 = db
        .pragma_query_value(None, "page_size", |r| r.get(0))
        .map_err(sql)?;
    let pages: i64 = db
        .pragma_query_value(None, "page_count", |r| r.get(0))
        .map_err(sql)?;
    let mut statement = db.prepare("SELECT name,type,sql FROM sqlite_schema WHERE name NOT GLOB 'sqlite_*' ORDER BY name LIMIT 4").map_err(sql)?;
    let schema: Vec<(String, String, String)> = statement
        .query_map([], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)))
        .map_err(sql)?
        .collect::<Result<_, _>>()
        .map_err(sql)?;
    if application != APP as i64
        || version != 1
        || mode != "delete"
        || page_size != 4096
        || pages < 0
        || pages.saturating_mul(page_size) > DATABASE_BYTES as i64
        || schema
            != vec![
                ("inputs".into(), "table".into(), INPUTS.into()),
                ("jobs".into(), "table".into(), JOBS.into()),
                ("runtime".into(), "table".into(), RUNTIME.into()),
            ]
    {
        return Err(err(
            "JOB_FORMAT",
            "Job storage differs from the supported version-1 contract",
        ));
    }
    drop(statement);
    db.pragma_update(None, "max_page_count", (DATABASE_BYTES / 4096) as u32)
        .map_err(sql)?;
    Ok(Some(db))
}
pub(super) fn required(root: &Path) -> Result<Connection, Error> {
    open(root, None)?.ok_or_else(|| err("JOB_NOT_FOUND", "Job queue does not exist"))
}
fn decode<T: serde::de::DeserializeOwned>(
    data: Vec<u8>,
    hash: String,
    limit: usize,
) -> Result<T, Error> {
    if data.len() > limit || assets::sha256(&data) != hash {
        return Err(corrupt("Job payload checksum or bound is invalid"));
    }
    serde_json::from_slice(&data).map_err(|_| corrupt("Job payload does not match its schema"))
}
pub(super) fn input_bytes(db: &Connection, id: &str) -> Result<Option<Vec<u8>>, Error> {
    let row: Option<(Vec<u8>, String)> = db
        .query_row("SELECT payload,sha256 FROM inputs WHERE id=?1", [id], |r| {
            Ok((r.get(0)?, r.get(1)?))
        })
        .optional()
        .map_err(sql)?;
    row.map(|(data, hash)| {
        if data.len() > MAX_INPUT_BYTES || assets::sha256(&data) != hash {
            return Err(corrupt("Job input checksum or bound is invalid"));
        }
        Ok(data)
    })
    .transpose()
}
pub(super) fn input(db: &Connection, id: &str) -> Result<Input, Error> {
    let data =
        input_bytes(db, id)?.ok_or_else(|| err("JOB_NOT_FOUND", "Job request does not exist"))?;
    let input: Input =
        serde_json::from_slice(&data).map_err(|_| corrupt("Job input schema is invalid"))?;
    if input.version != 1 || input.id != id || !model::valid_id(id) {
        return Err(corrupt("Job input identity is inconsistent"));
    }
    input
        .options
        .validate()
        .map_err(|_| corrupt("Saved job limits are invalid"))?;
    input
        .resources
        .validate()
        .map_err(|_| corrupt("Saved resource bindings are invalid"))?;
    publish::destination(&input.output)
        .map_err(|_| corrupt("Saved output destination is invalid"))?;
    Ok(input)
}
pub(super) fn state(db: &Connection, id: &str) -> Result<State, Error> {
    let row: Option<(Vec<u8>, String)> = db
        .query_row(
            "SELECT state,state_sha256 FROM jobs WHERE id=?1",
            [id],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .optional()
        .map_err(sql)?;
    let (data, hash) = row.ok_or_else(|| err("JOB_NOT_FOUND", "Job request does not exist"))?;
    let state: State = decode(data, hash, MAX_STATE_BYTES)?;
    state.validate(id)?;
    Ok(state)
}
pub(super) fn save(db: &Connection, state: &State) -> Result<(), Error> {
    state.validate(&state.id)?;
    let data = encode(state, MAX_STATE_BYTES)?;
    if db
        .execute(
            "UPDATE jobs SET state=?1,state_sha256=?2 WHERE id=?3",
            params![data, assets::sha256(&data), state.id],
        )
        .map_err(sql)?
        != 1
    {
        return Err(corrupt("Job disappeared during update"));
    }
    Ok(())
}
pub(super) fn runtime(db: &Connection) -> Result<Runtime, Error> {
    let row: (Vec<u8>, String) = db
        .query_row("SELECT payload,sha256 FROM runtime WHERE id=1", [], |r| {
            Ok((r.get(0)?, r.get(1)?))
        })
        .map_err(sql)?;
    let runtime: Runtime = decode(row.0, row.1, 16384)?;
    if runtime.version != 1
        || runtime.executable.bytes == 0
        || runtime.executable.bytes > job_process::MAX_EXECUTABLE_BYTES
        || runtime.executable.sha256.len() != 64
        || !runtime.executable.path.is_absolute()
    {
        return Err(corrupt("Invalid queue runtime identity"));
    }
    Ok(runtime)
}
pub(super) fn save_runtime(db: &Connection, runtime: &Runtime) -> Result<(), Error> {
    let data = encode(runtime, 16384)?;
    if db
        .execute(
            "UPDATE runtime SET payload=?1,sha256=?2 WHERE id=1",
            params![data, assets::sha256(&data)],
        )
        .map_err(sql)?
        != 1
    {
        return Err(corrupt("Queue runtime disappeared"));
    }
    Ok(())
}
pub(super) fn ids(db: &Connection) -> Result<Vec<String>, Error> {
    let mut query = db
        .prepare("SELECT id FROM jobs ORDER BY rowid LIMIT ?1")
        .map_err(sql)?;
    let ids = query
        .query_map([(MAX_JOBS + 1) as i64], |r| r.get(0))
        .map_err(sql)?
        .collect::<Result<Vec<String>, _>>()
        .map_err(sql)?;
    if ids.len() > MAX_JOBS {
        return Err(corrupt("Job count exceeds the storage bound"));
    }
    Ok(ids)
}
/// Compact immutable membership for paging. Mutable progress does not invalidate
/// a cursor, and bounded discovery does not deserialize every saved document.
pub(super) fn inventory(db: &Connection) -> Result<Vec<(String, String)>, Error> {
    let mut query = db.prepare("SELECT j.rowid,j.id,i.sha256 FROM jobs j LEFT JOIN inputs i ON i.id=j.id ORDER BY j.rowid LIMIT ?1").map_err(sql)?;
    let rows: Vec<(i64, String, Option<String>)> = query
        .query_map([(MAX_JOBS + 1) as i64], |r| {
            Ok((r.get(0)?, r.get(1)?, r.get(2)?))
        })
        .map_err(sql)?
        .collect::<Result<_, _>>()
        .map_err(sql)?;
    let input_count: i64 = db
        .query_row(
            "SELECT COUNT(*) FROM (SELECT 1 FROM inputs LIMIT ?1)",
            [(MAX_JOBS + 1) as i64],
            |r| r.get(0),
        )
        .map_err(sql)?;
    if rows.len() > MAX_JOBS || input_count != rows.len() as i64 {
        return Err(corrupt("Job membership count or input linkage is invalid"));
    }
    rows.into_iter()
        .enumerate()
        .map(|(index, (ordinal, id, sha))| {
            let sha = sha.ok_or_else(|| corrupt("Job input is missing"))?;
            if ordinal != index as i64 + 1
                || !model::valid_id(&id)
                || !crate::fonts::valid_hash(&sha)
            {
                return Err(corrupt("Job admission order or input identity is invalid"));
            }
            Ok((id, sha))
        })
        .collect()
}
pub(super) fn check_active(
    db: &Connection,
    input: &Input,
    except: Option<&str>,
) -> Result<(), Error> {
    let destination = publish::destination(&input.output)?;
    let mut active = 0;
    for id in ids(db)? {
        if except == Some(id.as_str()) {
            continue;
        }
        if state(db, &id)?.phase.active() {
            active += 1;
            if publish::destination(&self::input(db, &id)?.output)? == destination {
                return Err(err(
                    "JOB_OUTPUT_RESERVED",
                    "Another active job reserves this output destination",
                ));
            }
        }
    }
    if active >= MAX_ACTIVE {
        return Err(err(
            "JOB_LIMIT",
            "Queue already has 32 active or interrupted jobs",
        ));
    }
    Ok(())
}
pub(super) fn admit(db: &Connection, input: &Input, data: &[u8]) -> Result<(), Error> {
    check_active(db, input, None)?;
    let (count, bytes): (i64, i64) = db
        .query_row(
            "SELECT COUNT(*),COALESCE(SUM(length(payload)),0) FROM inputs",
            [],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .map_err(sql)?;
    if count < 0
        || bytes < 0
        || count >= MAX_JOBS as i64
        || bytes + data.len() as i64 + (count + 1) * MAX_STATE_BYTES as i64 > MAX_STORE_BYTES as i64
    {
        return Err(err(
            "JOB_LIMIT",
            "Job ledger is full, including reserved receipt capacity; preserve it and choose another root",
        ));
    }
    let state = encode(&State::new(&input.id), MAX_STATE_BYTES)?;
    db.execute(
        "INSERT INTO inputs VALUES(?1,?2,?3)",
        params![input.id, data, assets::sha256(data),],
    )
    .map_err(sql)?;
    db.execute(
        "INSERT INTO jobs VALUES(?1,?2,?3)",
        params![input.id, state, assets::sha256(&state)],
    )
    .map_err(sql)?;
    Ok(())
}
