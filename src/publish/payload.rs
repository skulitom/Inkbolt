//! Bounded encoded streams; private file payloads never enter response JSON.
use crate::{Error, assets, control::Control, limits::publish as limits, model::limit};
use sha2::{Digest, Sha256};
use std::{
    fs::{File, OpenOptions},
    io::{self, Cursor, Read, Seek, Write},
    sync::atomic::{AtomicU64, Ordering},
};

static NEXT: AtomicU64 = AtomicU64::new(0);

mod seekable;
pub(crate) use seekable::SeekSink;
mod projection;
pub(crate) use projection::Projection;

enum Storage {
    Memory(Vec<u8>),
    Private(File),
    Discard,
}

fn io_error() -> Error {
    Error::new(
        "IO_ERROR",
        "Unable to access private encoded output storage",
    )
}

fn private_file(control: &Control) -> Result<File, Error> {
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
        "Private output staging requires Windows or Unix",
    ));
    for _ in 0..limits::MAX_STAGE_ATTEMPTS {
        control.check()?;
        let path = std::env::temp_dir().join(format!(
            "inkbolt-export-{}-{}.tmp",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        match options.open(&path) {
            Ok(file) => {
                #[cfg(unix)]
                std::fs::remove_file(&path).map_err(|_| io_error())?;
                return Ok(file);
            }
            Err(e) if e.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(_) => return Err(io_error()),
        }
    }
    Err(io_error())
}

pub(crate) struct Payload {
    storage: Storage,
    len: usize,
    sha256: String,
}
impl Payload {
    pub fn from_bytes(bytes: Vec<u8>) -> Self {
        Self {
            len: bytes.len(),
            sha256: assets::sha256(&bytes),
            storage: Storage::Memory(bytes),
        }
    }
    pub fn len(&self) -> usize {
        self.len
    }
    pub fn sha256(&self) -> &str {
        &self.sha256
    }
    pub fn into_memory(self) -> Vec<u8> {
        match self.storage {
            Storage::Memory(bytes) => bytes,
            _ => unreachable!("Memory encoder payload"),
        }
    }
    pub fn copy_to(
        &mut self,
        output: &mut impl Write,
        control: &Control,
        mut progress: impl FnMut(usize),
    ) -> Result<(), Error> {
        let mut memory;
        let input: &mut dyn Read = match &mut self.storage {
            Storage::Memory(bytes) => {
                memory = Cursor::new(bytes.as_slice());
                &mut memory
            }
            Storage::Private(file) => {
                file.rewind().map_err(|_| io_error())?;
                file
            }
            Storage::Discard => {
                return Err(Error::new(
                    "EXPORT_ERROR",
                    "Preflight has no retained output",
                ));
            }
        };
        let mut buffer = vec![0; limits::IO_CHUNK_BYTES];
        let mut copied = 0;
        let mut hash = Sha256::new();
        loop {
            control.check()?;
            let count = input.read(&mut buffer).map_err(|_| io_error())?;
            if count == 0 {
                break;
            }
            copied += count;
            if copied > self.len {
                return Err(io_error());
            }
            output.write_all(&buffer[..count]).map_err(|_| io_error())?;
            hash.update(&buffer[..count]);
            progress(copied);
        }
        if copied != self.len || format!("{:x}", hash.finalize()) != self.sha256 {
            return Err(io_error());
        }
        control.check()
    }
}

pub(crate) struct Sink<'a> {
    storage: Storage,
    len: usize,
    maximum: usize,
    hash: Sha256,
    control: &'a Control,
    error: Option<Error>,
}
impl<'a> Sink<'a> {
    fn new(storage: Storage, control: &'a Control) -> Self {
        Self {
            storage,
            len: 0,
            maximum: limits::MAX_OUTPUT_BYTES,
            hash: Sha256::new(),
            control,
            error: None,
        }
    }
    pub fn memory(control: &'a Control) -> Self {
        Self::new(Storage::Memory(Vec::new()), control)
    }
    pub fn publication(retain: bool, control: &'a Control) -> Result<Self, Error> {
        let mut sink = Self::new(
            if retain {
                Storage::Private(private_file(control)?)
            } else {
                Storage::Discard
            },
            control,
        );
        sink.maximum = limits::MAX_FILE_IMAGE_BYTES;
        Ok(sink)
    }
    fn fail(&mut self, error: Error) -> io::Error {
        if self.error.is_none() {
            self.error = Some(error);
        }
        io::Error::other("Encoded output rejected")
    }
    pub fn finish(self) -> Result<Payload, Error> {
        if let Some(error) = self.error {
            return Err(error);
        }
        self.control.check()?;
        Ok(Payload {
            storage: self.storage,
            len: self.len,
            sha256: format!("{:x}", self.hash.finalize()),
        })
    }
}
impl Write for Sink<'_> {
    fn write(&mut self, data: &[u8]) -> io::Result<usize> {
        if self.error.is_some() {
            return Err(io::Error::other("Encoded output already failed"));
        }
        if let Err(error) = self.control.check() {
            return Err(self.fail(error));
        }
        if data.len() > self.maximum.saturating_sub(self.len) {
            return Err(self.fail(limit("Encoded output exceeds publication byte limit")));
        }
        let count = match &mut self.storage {
            Storage::Memory(bytes) => {
                bytes.extend_from_slice(data);
                data.len()
            }
            Storage::Private(file) => match file.write(data) {
                Ok(n) => n,
                Err(_) => return Err(self.fail(io_error())),
            },
            Storage::Discard => data.len(),
        };
        self.len += count;
        self.hash.update(&data[..count]);
        Ok(count)
    }
    fn flush(&mut self) -> io::Result<()> {
        if self.error.is_some() {
            return Err(io::Error::other("Encoded output already failed"));
        }
        if let Err(error) = self.control.check() {
            return Err(self.fail(error));
        }
        if let Storage::Private(file) = &mut self.storage
            && file.flush().is_err()
        {
            return Err(self.fail(io_error()));
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        fs,
        path::PathBuf,
        process::{Child, Command, Stdio},
        time::{Duration, Instant},
    };

    struct OwnedWorker {
        root: PathBuf,
        child: Option<Child>,
    }
    impl Drop for OwnedWorker {
        fn drop(&mut self) {
            if let Some(child) = &mut self.child {
                let _ = child.kill();
                let _ = child.wait();
            }
            let _ = fs::remove_file(self.root.join("ready"));
            let _ = fs::remove_dir(&self.root);
        }
    }

    #[test]
    fn private_payload_worker() {
        let Some(root) = std::env::var_os("INKBOLT_PNG_PAYLOAD_TEST_ROOT") else {
            return;
        };
        let root = PathBuf::from(root);
        let control = Control::default();
        let expected = vec![79; limits::IO_CHUNK_BYTES + 11];
        let mut sink = Sink::publication(true, &control).unwrap();
        sink.write_all(&expected).unwrap();
        let mut payload = sink.finish().unwrap();
        let mut read = Vec::new();
        payload.copy_to(&mut read, &control, |_| {}).unwrap();
        assert_eq!(read, expected);
        // This marker follows a real read of the complete private payload. The
        // process retains its handle until the parent kills this exact child.
        fs::write(root.join("ready.pending"), payload.sha256()).unwrap();
        fs::rename(root.join("ready.pending"), root.join("ready")).unwrap();
        loop {
            std::thread::park();
        }
    }

    #[test]
    fn process_death_closes_the_verified_private_payload_on_windows_and_unix() {
        let parent = std::env::temp_dir().canonicalize().unwrap();
        let root = parent.join(format!(
            "inkbolt-output-lifetime-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        assert!(root.canonicalize().unwrap().starts_with(&parent));
        let mut owned = OwnedWorker { root, child: None };
        let mut command = Command::new(std::env::current_exe().unwrap());
        command
            .args([
                "--exact",
                "publish::payload::tests::private_payload_worker",
                "--nocapture",
            ])
            .env("INKBOLT_PNG_PAYLOAD_TEST_ROOT", &owned.root)
            .env("TMP", &owned.root)
            .env("TEMP", &owned.root)
            .env("TMPDIR", &owned.root)
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        owned.child = Some(command.spawn().unwrap());
        let deadline = Instant::now() + Duration::from_secs(10);
        while !owned.root.join("ready").exists() {
            assert!(owned.child.as_mut().unwrap().try_wait().unwrap().is_none());
            assert!(
                Instant::now() < deadline,
                "Private payload worker did not become ready"
            );
            std::thread::sleep(Duration::from_millis(5));
        }
        assert_eq!(
            fs::read_to_string(owned.root.join("ready")).unwrap(),
            assets::sha256(&vec![79; limits::IO_CHUNK_BYTES + 11])
        );
        #[cfg(windows)]
        assert_eq!(fs::read_dir(&owned.root).unwrap().count(), 2);
        #[cfg(unix)]
        assert_eq!(fs::read_dir(&owned.root).unwrap().count(), 1);
        let child = owned.child.as_mut().unwrap();
        child.kill().unwrap();
        child.wait().unwrap();
        assert_eq!(fs::read_dir(&owned.root).unwrap().count(), 1);
    }

    #[test]
    fn output_bound_and_cancellation_poison_the_whole_stream() {
        let control = Control::default();
        let mut sink = Sink::memory(&control);
        sink.maximum = 8;
        sink.write_all(b"12345678").unwrap();
        assert!(sink.write_all(b"9").is_err());
        assert_eq!(sink.len, 8);
        assert!(sink.flush().is_err());
        assert_eq!(sink.finish().err().unwrap().code, "RESOURCE_LIMIT");
        let mut sink = Sink::memory(&control);
        sink.write_all(b"header").unwrap();
        control.cancel();
        assert!(sink.write_all(b"payload").is_err());
        assert_eq!(sink.finish().err().unwrap().code, "CANCELLED");
    }
    #[test]
    fn file_streams_cross_the_inline_boundary_without_a_larger_response() {
        let control = Control::default();
        let chunk = vec![37; limits::IO_CHUNK_BYTES];
        let mut inline = Sink::memory(&control);
        let mut file = Sink::publication(true, &control).unwrap();
        let mut preflight = Sink::publication(false, &control).unwrap();
        for _ in 0..limits::MAX_OUTPUT_BYTES / chunk.len() {
            for sink in [&mut inline, &mut file, &mut preflight] {
                sink.write_all(&chunk).unwrap();
            }
        }
        assert!(inline.write_all(b"!").is_err());
        assert_eq!(inline.finish().err().unwrap().code, "RESOURCE_LIMIT");
        file.write_all(b"!").unwrap();
        preflight.write_all(b"!").unwrap();
        let mut file = file.finish().unwrap();
        let preflight = preflight.finish().unwrap();
        assert_eq!(file.len(), limits::MAX_OUTPUT_BYTES + 1);
        assert_eq!(file.len(), preflight.len());
        assert_eq!(file.sha256(), preflight.sha256());
        file.copy_to(&mut io::sink(), &control, |_| {}).unwrap();
    }
    #[test]
    fn memory_private_and_discard_streams_agree_without_reopening_paths() {
        let control = Control::default();
        let data: Vec<u8> = (0..limits::IO_CHUNK_BYTES * 2 + 19)
            .map(|n| (n * 31) as u8)
            .collect();
        for mut sink in [
            Sink::memory(&control),
            Sink::publication(true, &control).unwrap(),
            Sink::publication(false, &control).unwrap(),
        ] {
            #[cfg(unix)]
            if let Storage::Private(file) = &sink.storage {
                use std::os::unix::fs::MetadataExt;
                let metadata = file.metadata().unwrap();
                assert_eq!(metadata.nlink(), 0);
                assert_eq!(metadata.mode() & 0o777, 0o600);
            }
            for piece in data.chunks(37) {
                sink.write_all(piece).unwrap();
            }
            let mut payload = sink.finish().unwrap();
            assert_eq!(payload.len(), data.len());
            assert_eq!(payload.sha256(), assets::sha256(&data));
            let mut output = Vec::new();
            if matches!(payload.storage, Storage::Discard) {
                assert!(payload.copy_to(&mut output, &control, |_| {}).is_err());
                assert!(output.is_empty());
            } else {
                let mut chunks = 0;
                payload
                    .copy_to(&mut output, &control, |_| chunks += 1)
                    .unwrap();
                assert_eq!(chunks, 3);
                assert_eq!(output, data);
            }
        }
    }
    #[test]
    fn cancellation_between_copy_chunks_prevents_further_staging_writes() {
        let control = Control::default();
        let mut payload = Payload::from_bytes(vec![91; limits::IO_CHUNK_BYTES * 2]);
        let mut written = Vec::new();
        let error = payload
            .copy_to(&mut written, &control, |_| control.cancel())
            .unwrap_err();
        assert_eq!(error.code, "CANCELLED");
        assert_eq!(written.len(), limits::IO_CHUNK_BYTES);
    }
}
