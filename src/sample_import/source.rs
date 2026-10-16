//! Private seekable input snapshots; no payload survives the final owned handle.
use crate::{Error, assets, control::Control, limits::sample_import as limits, model::limit};
use sha2::{Digest, Sha256};
use std::{
    fs::{File, OpenOptions},
    io::{self, Cursor, Read, Seek, SeekFrom, Write},
    path::Path,
    sync::{
        Arc, Mutex,
        atomic::{AtomicU64, Ordering},
    },
};

static NEXT: AtomicU64 = AtomicU64::new(0);

fn scratch_error() -> Error {
    Error::new(
        "IO_ERROR",
        "Unable to access private image-import scratch storage",
    )
}

#[cfg(test)]
mod tests;

#[derive(Clone)]
pub(super) struct Budget {
    maximum: u64,
    used: Arc<Mutex<u64>>,
}
impl Budget {
    pub(super) fn new(maximum: u64) -> Self {
        assert!(maximum <= limits::MAX_PRIVATE_STAGING_BYTES);
        Self {
            maximum,
            used: Arc::new(Mutex::new(0)),
        }
    }
    fn reserve(&self, bytes: u64) -> Result<(), Error> {
        let mut used = self.used.lock().map_err(|_| scratch_error())?;
        *used = used
            .checked_add(bytes)
            .filter(|n| *n <= self.maximum)
            .ok_or_else(|| limit("Private image-import staging capacity exceeded"))?;
        Ok(())
    }
}

pub(super) struct Scratch {
    file: Option<File>,
    budget: Budget,
    reserved: u64,
}
impl Scratch {
    pub(super) fn create(parent: &Path, budget: Budget, control: &Control) -> Result<Self, Error> {
        control.check()?;
        let mut options = OpenOptions::new();
        options.read(true).write(true).create_new(true);
        #[cfg(windows)]
        {
            use std::os::windows::fs::OpenOptionsExt;
            const FILE_FLAG_DELETE_ON_CLOSE: u32 = 0x04000000;
            options
                .share_mode(0)
                .custom_flags(FILE_FLAG_DELETE_ON_CLOSE);
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        #[cfg(not(any(windows, unix)))]
        return Err(Error::new(
            "UNSUPPORTED_PLATFORM",
            "Private native import staging requires Windows or Unix",
        ));

        for _ in 0..limits::MAX_SCRATCH_ATTEMPTS {
            control.check()?;
            let path = parent.join(format!(
                "inkbolt-import-{}-{}.tmp",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            let file = match options.open(&path) {
                Ok(file) => file,
                Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
                Err(_) => return Err(scratch_error()),
            };
            #[cfg(unix)]
            std::fs::remove_file(&path).map_err(|_| scratch_error())?;
            return Ok(Self {
                file: Some(file),
                budget,
                reserved: 0,
            });
        }
        Err(scratch_error())
    }

    fn append(&mut self, bytes: &[u8], control: &Control) -> Result<(), Error> {
        control.check()?;
        self.budget.reserve(bytes.len() as u64)?;
        // Keep the complete reservation after a partial failed write. Drop closes
        // the payload handle before releasing these bytes to the shared budget.
        self.reserved += bytes.len() as u64;
        self.file
            .as_mut()
            .unwrap()
            .write_all(bytes)
            .map_err(|_| scratch_error())
    }

    pub(super) fn allocate(&mut self, bytes: u64, control: &Control) -> Result<(), Error> {
        control.check()?;
        if self.reserved != 0 {
            return Err(scratch_error());
        }
        self.budget.reserve(bytes)?;
        self.reserved = bytes;
        // Reservation survives a partial/failed allocation until the handle closes.
        self.file
            .as_ref()
            .unwrap()
            .set_len(bytes)
            .map_err(|_| scratch_error())
    }

    pub(super) fn write_at(
        &mut self,
        offset: u64,
        bytes: &[u8],
        control: &Control,
    ) -> Result<(), Error> {
        control.check()?;
        if offset
            .checked_add(bytes.len() as u64)
            .is_none_or(|end| end > self.reserved)
        {
            return Err(limit("Private pixel write exceeds reserved staging extent"));
        }
        let file = self.file.as_mut().unwrap();
        file.seek(SeekFrom::Start(offset))
            .and_then(|_| file.write_all(bytes))
            .map_err(|_| scratch_error())
    }

    pub(super) fn read_at(
        &mut self,
        offset: u64,
        bytes: &mut [u8],
        control: &Control,
    ) -> Result<(), Error> {
        control.check()?;
        if offset
            .checked_add(bytes.len() as u64)
            .is_none_or(|end| end > self.reserved)
        {
            return Err(scratch_error());
        }
        let file = self.file.as_mut().unwrap();
        file.seek(SeekFrom::Start(offset))
            .and_then(|_| file.read_exact(bytes))
            .map_err(|_| scratch_error())
    }
}
impl Drop for Scratch {
    fn drop(&mut self) {
        drop(self.file.take());
        let mut used = self.budget.used.lock().unwrap_or_else(|e| e.into_inner());
        *used -= self.reserved;
    }
}
impl Read for Scratch {
    fn read(&mut self, output: &mut [u8]) -> io::Result<usize> {
        self.file.as_mut().unwrap().read(output)
    }
}
impl Seek for Scratch {
    fn seek(&mut self, position: SeekFrom) -> io::Result<u64> {
        self.file.as_mut().unwrap().seek(position)
    }
}

pub(super) trait ReadSeek: Read + Seek {}
impl<T: Read + Seek> ReadSeek for T {}

pub(super) struct Source {
    pub reader: Box<dyn ReadSeek>,
    pub sha256: String,
    pub bytes: usize,
    pub staging: Option<Budget>,
}
impl Source {
    pub fn open(path: &Path, private_file: bool, control: &Control) -> Result<Self, Error> {
        control.check()?;
        if !private_file {
            let bytes = assets::read_bounded(path, assets::MAX_IMPORT_BYTES)?;
            control.check()?;
            return Ok(Self {
                sha256: assets::sha256(&bytes),
                bytes: bytes.len(),
                reader: Box::new(Cursor::new(bytes)),
                staging: None,
            });
        }
        let mut input = File::open(path).map_err(|_| assets::io_error())?;
        let meta = input.metadata().map_err(|_| assets::io_error())?;
        if !meta.is_file() {
            return Err(assets::io_error());
        }
        if meta.len() > limits::MAX_NATIVE_SOURCE_BYTES {
            return Err(limit("Asset input exceeds byte limit"));
        }
        let budget = Budget::new(limits::MAX_PRIVATE_STAGING_BYTES);
        let scratch = Scratch::create(&std::env::temp_dir(), budget, control)?;
        Self::capture(
            &mut input,
            scratch,
            limits::MAX_NATIVE_SOURCE_BYTES,
            control,
        )
    }

    fn capture(
        input: &mut impl Read,
        mut scratch: Scratch,
        maximum: u64,
        control: &Control,
    ) -> Result<Self, Error> {
        let mut buffer = vec![0; limits::INPUT_BUFFER_BYTES];
        let mut hash = Sha256::new();
        let mut bytes = 0usize;
        loop {
            control.check()?;
            let read = input.read(&mut buffer).map_err(|_| assets::io_error())?;
            if read == 0 {
                break;
            }
            bytes += read;
            if bytes as u64 > maximum {
                return Err(limit("Asset input exceeds byte limit"));
            }
            scratch.append(&buffer[..read], control)?;
            hash.update(&buffer[..read]);
        }
        control.check()?;
        scratch.rewind().map_err(|_| scratch_error())?;
        Ok(Self {
            staging: Some(scratch.budget.clone()),
            reader: Box::new(scratch),
            sha256: format!("{:x}", hash.finalize()),
            bytes,
        })
    }
}
