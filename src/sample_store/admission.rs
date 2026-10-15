//! Serialized, conservative capacity admission for cooperating native publishers.
use super::{Error, io_error};
use crate::{control::Control, limits::sample_store as limits};
use std::{
    fs::{self, File, OpenOptions, TryLockError},
    path::Path,
    time::{Duration, Instant},
};

pub(super) const LOCK_NAME: &str = ".inkbolt-native.lock";

#[derive(Clone, Copy)]
pub(crate) struct Budget {
    pub bytes: u64,
    pub entries: usize,
}

pub(super) fn budget() -> Budget {
    #[cfg(test)]
    if let Some(budget) = TEST_BUDGET.get() {
        return budget;
    }
    Budget {
        bytes: limits::MAX_STORE_BYTES,
        entries: limits::MAX_STORE_ENTRIES,
    }
}

/// The file stays named and empty. Dropping the handle releases the OS lock;
/// never unlink a lock file, which could split concurrent publishers' locks.
pub(super) struct Admission {
    _lock: File,
}

impl Admission {
    pub fn acquire(root: &Path, control: &Control) -> Result<Self, Error> {
        let path = root.join(LOCK_NAME);
        match fs::symlink_metadata(&path) {
            Ok(meta) if !meta.is_file() || meta.file_type().is_symlink() || meta.len() != 0 => {
                return Err(io_error());
            }
            Ok(_) => {}
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
            Err(_) => return Err(io_error()),
        }
        let mut options = OpenOptions::new();
        options.read(true).write(true).create(true).truncate(false);
        #[cfg(windows)]
        {
            use std::os::windows::fs::OpenOptionsExt;
            // Keep the named coordination file from being deleted while held.
            options.share_mode(1 | 2);
        }
        let file = options.open(&path).map_err(|_| io_error())?;
        let meta = file.metadata().map_err(|_| io_error())?;
        if !meta.is_file() || meta.len() != 0 {
            return Err(io_error());
        }
        let started = Instant::now();
        loop {
            control.check()?;
            match file.try_lock() {
                Ok(()) => return Ok(Self { _lock: file }),
                Err(TryLockError::WouldBlock) => {
                    #[cfg(test)]
                    mark_waiting(root);
                }
                Err(TryLockError::Error(_)) => return Err(io_error()),
            }
            if started.elapsed() >= Duration::from_millis(limits::MAX_ADMISSION_WAIT_MS) {
                return Err(Error::new(
                    "SAMPLE_STORE_BUSY",
                    "Another native publisher holds the store; retry after it completes",
                ));
            }
            std::thread::sleep(Duration::from_millis(limits::ADMISSION_POLL_MS));
        }
    }

    pub fn check(
        &self,
        root: &Path,
        new_bytes: &[usize],
        budget: Budget,
        control: &Control,
    ) -> Result<(), Error> {
        if new_bytes.is_empty() {
            return Ok(());
        }
        let limit =
            || crate::model::limit("Native store capacity exceeded; existing files are preserved");
        let mut bytes = 0u64;
        let mut entries = 0usize;
        for entry in fs::read_dir(root).map_err(|_| io_error())? {
            control.check()?;
            let entry = entry.map_err(|_| io_error())?;
            entries = entries.checked_add(1).ok_or_else(limit)?;
            if entries > budget.entries {
                return Err(limit());
            }
            let name = entry.file_name();
            let name = name.to_string_lossy();
            if name.ends_with(".native-tile")
                || (name.starts_with(".inkbolt-native-") && name.ends_with(".tmp"))
            {
                // Metadata does not follow a directory entry's symlink.
                let meta = fs::symlink_metadata(entry.path()).map_err(|_| io_error())?;
                if !meta.is_file() || meta.file_type().is_symlink() {
                    return Err(io_error());
                }
                bytes = bytes.checked_add(meta.len()).ok_or_else(limit)?;
                if bytes > budget.bytes {
                    return Err(limit());
                }
            }
        }
        for size in new_bytes {
            bytes = bytes.checked_add(*size as u64).ok_or_else(limit)?;
        }
        // An interruption after hard-link publication may retain both names.
        bytes = bytes
            .checked_add(*new_bytes.iter().max().expect("nonempty missing blocks") as u64)
            .ok_or_else(limit)?;
        entries = entries
            .checked_add(new_bytes.len())
            .and_then(|n| n.checked_add(1))
            .ok_or_else(limit)?;
        if bytes > budget.bytes || entries > budget.entries {
            return Err(limit());
        }
        control.check()
    }
}

#[cfg(test)]
fn mark_waiting(root: &Path) {
    let Some(parent) = std::env::var_os("INKBOLT_NATIVE_ADMISSION_TEST_ROOT") else {
        return;
    };
    let parent = std::path::PathBuf::from(parent);
    if parent.join("store") == root {
        let label = std::env::var("INKBOLT_NATIVE_ADMISSION_LABEL").unwrap();
        fs::write(parent.join(format!("waiting-{label}")), b"waiting").unwrap();
    }
}

#[cfg(test)]
thread_local! {
    static TEST_BUDGET: std::cell::Cell<Option<Budget>> = const { std::cell::Cell::new(None) };
}

/// Lower limits for exact boundary fixtures without allocating a production-sized store.
#[cfg(test)]
pub(crate) fn with_test_budget<T>(budget: Budget, work: impl FnOnce() -> T) -> T {
    assert!(budget.bytes <= limits::MAX_STORE_BYTES && budget.entries <= limits::MAX_STORE_ENTRIES);
    struct Restore(Option<Budget>);
    impl Drop for Restore {
        fn drop(&mut self) {
            TEST_BUDGET.set(self.0);
        }
    }
    let _restore = Restore(TEST_BUDGET.replace(Some(budget)));
    work()
}
