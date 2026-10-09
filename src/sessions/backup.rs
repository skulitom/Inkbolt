//! Checked whole-history copies. Publication never replaces a destination.
use super::*;
use rusqlite::backup::{Backup, StepResult};
use sha2::{Digest, Sha256};
use std::{
    io::{Read, Write},
    time::Instant,
};

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Output {
    pub output_root: PathBuf,
    /// New portable filename ending in .sqlite3 in an existing directory.
    pub file_name: String,
}

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Source {
    pub file_path: PathBuf,
    pub bytes: u64,
    /// Exact SHA-256 from the backup receipt; lowercase hexadecimal.
    pub sha256: String,
}

fn io(message: &str) -> Error {
    Error::new("IO_ERROR", message)
}

pub(super) fn checked_path(path: &Path) -> Result<(), Error> {
    assets::absolute(path)?;
    if path.as_os_str().len() > 4096 {
        return Err(limit("History path exceeds 4096 characters"));
    }
    Ok(())
}

pub(super) fn no_sidecars(path: &Path) -> Result<(), Error> {
    for suffix in ["-journal", "-wal", "-shm"] {
        let mut name = path.as_os_str().to_owned();
        name.push(suffix);
        absent(Path::new(&name))?;
    }
    Ok(())
}

pub(super) fn absent(path: &Path) -> Result<(), Error> {
    match fs::symlink_metadata(path) {
        Ok(_) => Err(Error::new(
            "OUTPUT_EXISTS",
            "History destination or sidecar already exists; preserve it and choose another destination",
        )),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(_) => Err(io("Unable to inspect history destination")),
    }
}

pub(super) fn output_path(output: &Output) -> Result<PathBuf, Error> {
    checked_path(&output.output_root)?;
    let name = &output.file_name;
    let stem = name.split('.').next().unwrap_or("").to_ascii_uppercase();
    let reserved = matches!(stem.as_str(), "CON" | "PRN" | "AUX" | "NUL")
        || (stem.len() == 4
            && (stem.starts_with("COM") || stem.starts_with("LPT"))
            && matches!(stem.as_bytes()[3], b'1'..=b'9'));
    if !model::valid_id(name)
        || !name.to_ascii_lowercase().ends_with(".sqlite3")
        || reserved
        || name.starts_with(".inkbolt-")
    {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Backup file_name must be a portable single .sqlite3 filename without reserved names",
        ));
    }
    if !output.output_root.is_dir() {
        return Err(io("Backup output_root must be an existing directory"));
    }
    let target = output.output_root.join(name);
    checked_path(&target)?;
    absent(&target)?;
    no_sidecars(&target)?;
    Ok(target)
}

pub(super) fn open_copy(path: &Path, readonly: bool) -> Result<Connection, Error> {
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
    Ok(db)
}

pub(super) fn inspect(path: &Path, session_id: &str, control: &Control) -> Result<Value, Error> {
    let mut db = open_copy(path, true)?;
    check_schema(&db)?;
    let tx = db.transaction().map_err(sql)?;
    verify_connection(&tx, session_id, control)
}

pub(super) fn identity(path: &Path, control: &Control) -> Result<Source, Error> {
    let mut file = fs::File::open(path).map_err(|_| io("Unable to read prepared history"))?;
    let mut digest = Sha256::new();
    let mut bytes = 0;
    let mut buffer = [0u8; 65536];
    loop {
        control.check()?;
        let count = file
            .read(&mut buffer)
            .map_err(|_| io("Unable to hash prepared history"))?;
        if count == 0 {
            break;
        }
        bytes += count as u64;
        if bytes > MAX_DATABASE_BYTES {
            return Err(limit("History backup exceeds 128 MiB"));
        }
        digest.update(&buffer[..count]);
    }
    Ok(Source {
        file_path: path.to_owned(),
        bytes,
        sha256: format!("{:x}", digest.finalize()),
    })
}

pub(super) fn publish(temp: &Path, target: &Path, control: &Control) -> Result<(), Error> {
    control.check()?;
    no_sidecars(target)?;
    match fs::hard_link(temp, target) {
        Ok(()) => Ok(()),
        Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => Err(Error::new(
            "OUTPUT_EXISTS",
            "History destination already exists; existing files are never overwritten",
        )),
        Err(_) => Err(io(
            "History destination must support create-only hard-link publication",
        )),
    }
}

pub fn create(
    root: &Path,
    session_id: &str,
    expected_revision: u64,
    output: &Output,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    let target = output_path(output)?;
    // Pin a read snapshot so concurrent commits cannot restart the stepped copy.
    // A pending hot journal must first be recovered through an ordinary session open.
    let mut source = open_mode(root, session_id, true)?;
    let tx = source.transaction().map_err(sql)?;
    let meta = read_meta(&tx, session_id)?;
    if expected_revision != meta.revision as u64 {
        return Err(Error::new(
            "REVISION_CONFLICT",
            "Backup expected_revision differs from the captured session head",
        ));
    }
    let original = verify_connection(&tx, session_id, control)?;
    let temp = reserve(&output.output_root)?;
    let mut destination = open_copy(&temp.0, false)?;
    destination
        .pragma_update(None, "max_page_count", (MAX_DATABASE_BYTES / 4096) as u32)
        .map_err(sql)?;
    {
        let copy = Backup::new(&tx, &mut destination).map_err(sql)?;
        let started = Instant::now();
        loop {
            control.check()?;
            match copy.step(256).map_err(sql)? {
                StepResult::Done => break,
                StepResult::More => {}
                StepResult::Busy | StepResult::Locked
                    if started.elapsed() < Duration::from_millis(250) =>
                {
                    std::thread::sleep(Duration::from_millis(5))
                }
                _ => {
                    return Err(Error::new(
                        "SESSION_BUSY",
                        "History copy could not obtain its bounded locks; retry the backup",
                    ));
                }
            }
            #[cfg(test)]
            super::fault_point("backup_during_copy");
        }
    }
    drop(tx);
    drop(source);
    destination.close().map_err(|(_, e)| sql(e))?;
    let verified = inspect(&temp.0, session_id, control)?;
    if verified != original {
        return Err(corrupt("Prepared backup differs from its captured history"));
    }
    OpenOptions::new()
        .write(true)
        .open(&temp.0)
        .and_then(|f| f.sync_all())
        .map_err(|_| io("Unable to flush prepared backup"))?;
    let mut source = identity(&temp.0, control)?;
    source.file_path = target.clone();
    let result = json!({"created":true,"backup":source,"session":verified,"history_preserved":true,"resources_copied":false,"external_resources_verified":false,"source_changed":false,"migration_performed":false});
    #[cfg(test)]
    super::fault_point("backup_before_publish");
    publish(&temp.0, &target, control)?;
    #[cfg(test)]
    super::fault_point("backup_after_publish");
    // Publication is the commit point: no fallible work or cancellation afterwards.
    Ok(result)
}

pub fn recover(
    root: &Path,
    session_id: &str,
    source: &Source,
    control: &Control,
) -> Result<Value, Error> {
    control.check()?;
    checked_path(root)?;
    validate_source(source)?;
    let target = store_path(root, session_id)?;
    checked_path(&target)?;
    absent(&target)?;
    no_sidecars(&target)?;
    let temp = copy_source(root, source, control)?;
    let verified = inspect(&temp.0, session_id, control)?;
    let result = json!({"created":true,"session_id":session_id,"session_root":root,"database":target,"source":source,"session":verified,"history_preserved":true,"resources_copied":false,"external_resources_verified":false,"source_changed":false,"migration_performed":false});
    #[cfg(test)]
    super::fault_point("recovery_before_publish");
    publish(&temp.0, &target, control)?;
    #[cfg(test)]
    super::fault_point("recovery_after_publish");
    Ok(result)
}

pub(super) fn validate_source(source: &Source) -> Result<(), Error> {
    checked_path(&source.file_path)?;
    if source.bytes == 0
        || source.bytes > MAX_DATABASE_BYTES
        || source.sha256.len() != 64
        || !source
            .sha256
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Backup identity requires 1..128 MiB bytes and a lowercase SHA-256",
        ));
    }
    Ok(())
}

/// Read pinned bytes once; never open the supplied source as SQLite.
pub(super) fn copy_source(
    root: &Path,
    source: &Source,
    control: &Control,
) -> Result<Temporary, Error> {
    control.check()?;
    validate_source(source)?;
    let metadata = fs::symlink_metadata(&source.file_path)
        .map_err(|_| io("Unable to inspect backup source"))?;
    if !metadata.is_file() || metadata.file_type().is_symlink() {
        return Err(Error::new(
            "INVALID_REQUEST",
            "Backup source must be a regular non-symlink file",
        ));
    }
    // A backup must be standalone. Never reopen/recover the caller's input database.
    no_sidecars(&source.file_path).map_err(|_| Error::new("BACKUP_SIDECAR", "Backup source has a journal/WAL sidecar or cannot be checked; supply a complete standalone backup"))?;
    if metadata.len() != source.bytes {
        return Err(Error::new(
            "SOURCE_MISMATCH",
            "Backup length differs from its pinned identity",
        ));
    }
    let mut input =
        fs::File::open(&source.file_path).map_err(|_| io("Unable to open backup source"))?;
    let temp = reserve(root)?;
    let mut file = OpenOptions::new()
        .write(true)
        .open(&temp.0)
        .map_err(|_| io("Unable to open recovery temporary"))?;
    let mut digest = Sha256::new();
    let mut bytes = 0;
    let mut buffer = [0u8; 65536];
    loop {
        control.check()?;
        let count = input
            .read(&mut buffer)
            .map_err(|_| io("Unable to read backup source"))?;
        if count == 0 {
            break;
        }
        bytes += count as u64;
        if bytes > source.bytes {
            return Err(Error::new(
                "SOURCE_MISMATCH",
                "Backup grew beyond its pinned identity",
            ));
        }
        digest.update(&buffer[..count]);
        file.write_all(&buffer[..count])
            .map_err(|_| io("Unable to write recovery temporary"))?;
        #[cfg(test)]
        {
            super::fault_point("recovery_during_copy");
            super::fault_point("migration_during_copy");
            super::fault_point("continuation_during_copy");
        }
    }
    if bytes != source.bytes || format!("{:x}", digest.finalize()) != source.sha256 {
        return Err(Error::new(
            "SOURCE_MISMATCH",
            "Copied backup differs from its pinned identity",
        ));
    }
    file.flush()
        .and_then(|()| file.sync_all())
        .map_err(|_| io("Unable to flush recovered history"))?;
    drop(file);
    drop(input);
    Ok(temp)
}
