//! Bounded checksummed receipt ledger. Rendering never holds a writer transaction.
use super::*;
use rusqlite::{Connection, OpenFlags, OptionalExtension, limits::Limit, params};
use std::time::Duration;

pub(super) const SCHEMA: &str = "CREATE TABLE publications(request_id TEXT PRIMARY KEY, payload BLOB NOT NULL, sha256 TEXT NOT NULL) STRICT";
const APPLICATION: i64 = 0x494e4b50;
const DATABASE_BYTES: u64 = 128 * 1024 * 1024;

pub(super) fn sql(e: rusqlite::Error) -> Error {
    match e.sqlite_error_code() {
        Some(rusqlite::ErrorCode::DatabaseBusy | rusqlite::ErrorCode::DatabaseLocked) => {
            Error::new(
                "PUBLICATION_BUSY",
                "Receipt store is busy; retry the same publication request",
            )
        }
        Some(rusqlite::ErrorCode::DatabaseCorrupt | rusqlite::ErrorCode::NotADatabase) => {
            corrupt("Receipt database is corrupt")
        }
        Some(rusqlite::ErrorCode::DiskFull | rusqlite::ErrorCode::TooBig) => {
            crate::model::limit("Receipt storage or available disk space exhausted")
        }
        _ => Error::new(
            "PUBLICATION_STORE_ERROR",
            "Unable to complete receipt storage; inspect or recover the original request before retrying",
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
        (MAX_RECEIPT_BYTES + 16384) as i32,
    )
    .map_err(sql)?;
    db.set_limit(Limit::SQLITE_LIMIT_SQL_LENGTH, 16384)
        .map_err(sql)?;
    db.set_limit(Limit::SQLITE_LIMIT_COLUMN, 32).map_err(sql)?;
    db.set_limit(Limit::SQLITE_LIMIT_ATTACHED, 0).map_err(sql)?;
    db.execute_batch("PRAGMA synchronous=FULL; PRAGMA trusted_schema=OFF; PRAGMA recursive_triggers=OFF; PRAGMA cache_size=-4096; PRAGMA temp_store=MEMORY;").map_err(sql)?;
    Ok(db)
}
pub(super) fn open(root: &Path, create: bool) -> Result<Option<Connection>, Error> {
    checked_path(root)?;
    let path = root.join("publications.sqlite3");
    match fs::symlink_metadata(&path) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            if !create {
                return Ok(None);
            }
            for suffix in ["-journal", "-wal", "-shm"] {
                crate::publish::exists(&root.join(format!("publications.sqlite3{suffix}")))?;
            }
            fs::create_dir_all(root).map_err(|_| io("Unable to create receipt root"))?;
            let temp = Stage::reserve(root, ".inkbolt-receipts-")?;
            let mut db = connection(&temp.path)?;
            db.execute_batch("PRAGMA page_size=4096; PRAGMA journal_mode=DELETE;")
                .map_err(sql)?;
            db.pragma_update(None, "application_id", APPLICATION)
                .map_err(sql)?;
            db.pragma_update(None, "user_version", 1).map_err(sql)?;
            let tx = db.transaction().map_err(sql)?;
            tx.execute_batch(SCHEMA).map_err(sql)?;
            tx.commit().map_err(sql)?;
            db.close().map_err(|(_, e)| sql(e))?;
            OpenOptions::new()
                .read(true)
                .write(true)
                .open(&temp.path)
                .and_then(|f| f.sync_all())
                .map_err(|_| io("Unable to flush new receipt store"))?;
            match fs::hard_link(&temp.path, &path) {
                Ok(()) => {}
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {}
                Err(_) => return Err(io("Receipt root must support create-only hard links")),
            }
        }
        Err(_) => return Err(io("Unable to inspect receipt store")),
        Ok(meta)
            if !meta.is_file() || meta.file_type().is_symlink() || meta.len() > DATABASE_BYTES =>
        {
            return Err(corrupt("Invalid receipt database file"));
        }
        Ok(_) => {}
    }
    // Check the fixed format header before opening SQLite, so an unrelated database
    // (including its rollback journal) is never recovered as our receipt store.
    let meta = fs::symlink_metadata(&path).map_err(|_| io("Unable to inspect receipt database"))?;
    if !meta.is_file() || meta.file_type().is_symlink() || meta.len() > DATABASE_BYTES {
        return Err(corrupt("Invalid receipt database file"));
    }
    let mut header = [0u8; 100];
    fs::File::open(&path)
        .and_then(|mut file| file.read_exact(&mut header))
        .map_err(|_| {
            Error::new(
                "PUBLICATION_FORMAT",
                "Receipt database header is missing or incomplete",
            )
        })?;
    if &header[..16] != b"SQLite format 3\0"
        || u32::from_be_bytes(header[68..72].try_into().unwrap()) != APPLICATION as u32
        || u32::from_be_bytes(header[60..64].try_into().unwrap()) != 1
    {
        return Err(Error::new(
            "PUBLICATION_FORMAT",
            "Unrecognized receipt database; existing files and journals are preserved",
        ));
    }
    let db = connection(&path)?;
    let app: i64 = db
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
    let mut stmt=db.prepare("SELECT name,type,sql FROM sqlite_schema WHERE name NOT GLOB 'sqlite_*' ORDER BY name LIMIT 3").map_err(sql)?;
    let schemas: Vec<(String, String, String)> = stmt
        .query_map([], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)))
        .map_err(sql)?
        .collect::<Result<_, _>>()
        .map_err(sql)?;
    if app != APPLICATION
        || version != 1
        || mode != "delete"
        || page_size != 4096
        || pages < 0
        || pages as u64 * 4096 > DATABASE_BYTES
        || schemas != vec![("publications".into(), "table".into(), SCHEMA.into())]
    {
        return Err(Error::new(
            "PUBLICATION_FORMAT",
            "Receipt storage differs from the supported version-1 contract",
        ));
    }
    drop(stmt);
    db.pragma_update(None, "max_page_count", (DATABASE_BYTES / 4096) as u32)
        .map_err(sql)?;
    Ok(Some(db))
}
pub(super) fn read(db: &Connection, id: &str) -> Result<Option<Record>, Error> {
    let row: Option<(Vec<u8>, String)> = db
        .query_row(
            "SELECT payload,sha256 FROM publications WHERE request_id=?1",
            [id],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .optional()
        .map_err(sql)?;
    row.map(|(payload, hash)| {
        if payload.len() > MAX_RECEIPT_BYTES || assets::sha256(&payload) != hash {
            return Err(corrupt("Publication receipt checksum or bound is invalid"));
        }
        let record: Record =
            serde_json::from_slice(&payload).map_err(|_| corrupt("Invalid publication receipt"))?;
        record.validate(id)?;
        Ok(record)
    })
    .transpose()
}
pub(super) fn insert(db: &Connection, record: &Record) -> Result<(), Error> {
    let payload = encode(record)?;
    let (count, bytes): (i64, i64) = db
        .query_row(
            "SELECT COUNT(*),COALESCE(SUM(length(payload)),0) FROM publications",
            [],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .map_err(sql)?;
    if count >= MAX_RECORDS as i64 || bytes + payload.len() as i64 > MAX_LEDGER_BYTES as i64 {
        return Err(Error::new(
            "PUBLICATION_LIMIT",
            "Receipt ledger is full; preserve it and choose another receipt root",
        ));
    }
    db.execute(
        "INSERT INTO publications(request_id,payload,sha256) VALUES(?1,?2,?3)",
        params![record.request_id, payload, assets::sha256(&payload)],
    )
    .map_err(sql)?;
    Ok(())
}
pub(super) fn complete(tx: rusqlite::Transaction<'_>, record: &Record) -> Result<(), Error> {
    let payload = encode(record)?;
    // Force a real SQLite write rejection after publication in the owned test child.
    #[cfg(test)]
    if std::env::var("INKBOLT_RECEIPT_FAULT").ok().as_deref() == Some("completion_error") {
        tx.pragma_update(None, "query_only", true).map_err(sql)?;
    }
    if tx
        .execute(
            "UPDATE publications SET payload=?1,sha256=?2 WHERE request_id=?3",
            params![payload, assets::sha256(&payload), record.request_id],
        )
        .map_err(sql)?
        != 1
    {
        return Err(corrupt("Publication receipt disappeared"));
    }
    tx.commit().map_err(sql)
}
