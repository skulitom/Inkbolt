use super::*;
use std::{
    fs,
    path::PathBuf,
    process::{Child, Command, Stdio},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

struct Directory(PathBuf);
impl Directory {
    fn new() -> Self {
        static NEXT_DIR: AtomicU64 = AtomicU64::new(0);
        let path = std::env::temp_dir().join(format!(
            "inkbolt-source-test-{}-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
            NEXT_DIR.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
}
impl Drop for Directory {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}

#[test]
fn shared_capacity_is_reserved_before_writes_and_released_after_close() {
    let dir = Directory::new();
    let control = Control::default();
    let budget = Budget::new(7);
    let mut a = Scratch::create(&dir.0, budget.clone(), &control).unwrap();
    let mut b = Scratch::create(&dir.0, budget.clone(), &control).unwrap();
    a.append(b"abcd", &control).unwrap();
    b.append(b"123", &control).unwrap();
    assert_eq!(b.append(b"4", &control).unwrap_err().code, "RESOURCE_LIMIT");
    assert_eq!(*budget.used.lock().unwrap(), 7);
    a.rewind().unwrap();
    let mut bytes = Vec::new();
    a.read_to_end(&mut bytes).unwrap();
    assert_eq!(bytes, b"abcd");
    drop(a);
    assert_eq!(*budget.used.lock().unwrap(), 3);
    b.append(b"4567", &control).unwrap();
    b.rewind().unwrap();
    bytes.clear();
    b.read_to_end(&mut bytes).unwrap();
    assert_eq!(bytes, b"1234567");
    drop(b);
    assert_eq!(*budget.used.lock().unwrap(), 0);
    assert_eq!(fs::read_dir(&dir.0).unwrap().count(), 0);
}

#[test]
fn reserved_extent_bounds_random_io_and_preserves_zero_filled_gaps() {
    let dir = Directory::new();
    let control = Control::default();
    let budget = Budget::new(16);
    let mut file = Scratch::create(&dir.0, budget.clone(), &control).unwrap();
    file.allocate(16, &control).unwrap();
    file.write_at(12, b"tail", &control).unwrap();
    file.write_at(2, b"head", &control).unwrap();
    assert_eq!(
        file.write_at(15, b"no", &control).unwrap_err().code,
        "RESOURCE_LIMIT"
    );
    assert!(file.read_at(16, &mut [0], &control).is_err());
    assert!(file.write_at(u64::MAX, b"no", &control).is_err());
    let mut bytes = [0; 16];
    file.read_at(0, &mut bytes, &control).unwrap();
    assert_eq!(&bytes, b"\0\0head\0\0\0\0\0\0tail");
    assert_eq!(*budget.used.lock().unwrap(), 16);
    assert_eq!(file.file.as_ref().unwrap().metadata().unwrap().len(), 16);
    drop(file);
    assert_eq!(*budget.used.lock().unwrap(), 0);
    assert_eq!(fs::read_dir(&dir.0).unwrap().count(), 0);
}

#[test]
fn captured_identity_and_seekable_bytes_survive_source_replacement() {
    let dir = Directory::new();
    let path = dir.0.join("input");
    let original: Vec<u8> = (0..limits::INPUT_BUFFER_BYTES * 2 + 17)
        .map(|n| (n % 251) as u8)
        .collect();
    fs::write(&path, &original).unwrap();
    let mut source = Source::open(&path, true, &Control::default()).unwrap();
    assert_eq!(fs::read(&path).unwrap(), original);
    assert_eq!(source.sha256, assets::sha256(&original));
    assert_eq!(source.bytes, original.len());
    fs::write(&path, b"replacement").unwrap();
    let mut captured = Vec::new();
    source.reader.read_to_end(&mut captured).unwrap();
    assert_eq!(captured, original);
    source.reader.seek(SeekFrom::Start(13)).unwrap();
    let mut fragment = [0; 31];
    source.reader.read_exact(&mut fragment).unwrap();
    assert_eq!(fragment, original[13..44]);
    assert_eq!(fs::read_dir(&dir.0).unwrap().count(), 1);
}

struct Generated {
    remaining: usize,
    maximum_read: usize,
    calls: usize,
    cancel: Option<Control>,
    fail_on_second: bool,
}
impl Read for Generated {
    fn read(&mut self, output: &mut [u8]) -> io::Result<usize> {
        self.maximum_read = self.maximum_read.max(output.len());
        self.calls += 1;
        if self.calls == 2 && self.fail_on_second {
            return Err(io::Error::other("synthetic read failure"));
        }
        let count = output.len().min(self.remaining);
        output[..count].fill(42);
        self.remaining -= count;
        if let Some(control) = self.cancel.take() {
            control.cancel();
        }
        Ok(count)
    }
}

#[test]
fn bounded_copy_cancellation_io_failure_and_growth_release_private_payloads() {
    for mode in ["cancel", "io", "growth", "success"] {
        let dir = Directory::new();
        let budget = Budget::new(limits::MAX_PRIVATE_STAGING_BYTES);
        let control = Control::default();
        let mut input = Generated {
            remaining: if mode == "growth" {
                limits::INPUT_BUFFER_BYTES * 2 + 1
            } else {
                limits::INPUT_BUFFER_BYTES + 7
            },
            maximum_read: 0,
            calls: 0,
            cancel: (mode == "cancel").then(|| control.clone()),
            fail_on_second: mode == "io",
        };
        let scratch = Scratch::create(&dir.0, budget.clone(), &control).unwrap();
        let result = Source::capture(
            &mut input,
            scratch,
            (limits::INPUT_BUFFER_BYTES * 2) as u64,
            &control,
        );
        match mode {
            "success" => {
                let mut source = result.unwrap();
                assert_eq!(source.bytes, limits::INPUT_BUFFER_BYTES + 7);
                let mut bytes = Vec::new();
                source.reader.read_to_end(&mut bytes).unwrap();
                assert_eq!(bytes, vec![42; limits::INPUT_BUFFER_BYTES + 7]);
                assert_eq!(source.sha256, assets::sha256(&bytes));
            }
            _ => assert_eq!(
                result.err().unwrap().code,
                match mode {
                    "cancel" => "CANCELLED",
                    "io" => "IO_ERROR",
                    _ => "RESOURCE_LIMIT",
                }
            ),
        }
        assert_eq!(input.maximum_read, limits::INPUT_BUFFER_BYTES);
        assert_eq!(*budget.used.lock().unwrap(), 0);
        assert_eq!(fs::read_dir(&dir.0).unwrap().count(), 0);
    }
}

struct Worker(Child);
impl Drop for Worker {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

#[test]
fn private_payload_disappears_after_process_death_without_touching_collisions() {
    let dir = Directory::new();
    let mut worker = Worker(
        Command::new(std::env::current_exe().unwrap())
            .args([
                "--exact",
                "sample_import::source::tests::scratch_worker",
                "--nocapture",
            ])
            .env("INKBOLT_TEST_SOURCE_SCRATCH", &dir.0)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .spawn()
            .unwrap(),
    );
    let until = Instant::now() + Duration::from_secs(10);
    while !dir.0.join("ready").exists() {
        assert!(
            worker.0.try_wait().unwrap().is_none(),
            "scratch worker exited before readiness"
        );
        assert!(Instant::now() < until, "scratch worker readiness timed out");
        std::thread::sleep(Duration::from_millis(5));
    }
    let foreign = dir
        .0
        .join(format!("inkbolt-import-{}-0.tmp", worker.0.id()));
    assert_eq!(fs::read(&foreign).unwrap(), b"foreign data");
    #[cfg(windows)]
    {
        let scratch = dir
            .0
            .join(format!("inkbolt-import-{}-1.tmp", worker.0.id()));
        assert!(
            File::open(scratch).is_err(),
            "live scratch must be exclusively owned"
        );
    }
    worker.0.kill().unwrap();
    worker.0.wait().unwrap();
    assert_eq!(fs::read(&foreign).unwrap(), b"foreign data");
    assert_eq!(
        fs::read_dir(&dir.0).unwrap().count(),
        2,
        "only ready marker and foreign collision may remain"
    );
}

#[test]
fn scratch_worker() {
    let Some(root) = std::env::var_os("INKBOLT_TEST_SOURCE_SCRATCH") else {
        return;
    };
    let root = PathBuf::from(root);
    let foreign = root.join(format!("inkbolt-import-{}-0.tmp", std::process::id()));
    fs::write(&foreign, b"foreign data").unwrap();
    let budget = Budget::new(64);
    let mut scratch = Scratch::create(&root, budget.clone(), &Control::default()).unwrap();
    scratch
        .append(b"private payload", &Control::default())
        .unwrap();
    let mut pixels = Scratch::create(&root, budget, &Control::default()).unwrap();
    pixels.allocate(32, &Control::default()).unwrap();
    pixels.write_at(28, b"tail", &Control::default()).unwrap();
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(
            scratch
                .file
                .as_ref()
                .unwrap()
                .metadata()
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o600
        );
        assert_eq!(
            fs::read_dir(&root).unwrap().count(),
            1,
            "Unix scratch payload must already be unlinked"
        );
    }
    fs::write(root.join("ready"), b"ready").unwrap();
    loop {
        std::thread::park();
    }
}

struct Counted {
    input: Cursor<Vec<u8>>,
    maximum: usize,
    total: usize,
}
impl Read for Counted {
    fn read(&mut self, output: &mut [u8]) -> io::Result<usize> {
        self.maximum = self.maximum.max(output.len());
        let read = self.input.read(output)?;
        self.total += read;
        Ok(read)
    }
}
impl Seek for Counted {
    fn seek(&mut self, position: SeekFrom) -> io::Result<u64> {
        self.input.seek(position)
    }
}

fn chunk(target: &mut Vec<u8>, kind: &[u8; 4], body: &[u8]) {
    target.extend_from_slice(&(body.len() as u32).to_be_bytes());
    target.extend_from_slice(kind);
    target.extend_from_slice(body);
    let mut hash = crc32fast::Hasher::new();
    hash.update(kind);
    hash.update(body);
    target.extend_from_slice(&hash.finalize().to_be_bytes());
}

#[test]
fn png_crc_scans_bounded_chunks_while_metadata_skips_unrelated_payload() {
    let packet = br#"{"schema":"inkbolt.metadata.v1","document":{"title":"original"},"items":{}}"#;
    let mut encoded = b"\x89PNG\r\n\x1a\n".to_vec();
    chunk(
        &mut encoded,
        b"IHDR",
        &[0, 0, 0, 1, 0, 0, 0, 1, 8, 6, 0, 0, 0],
    );
    let large = vec![b'x'; limits::INPUT_BUFFER_BYTES * 4 + 13];
    chunk(&mut encoded, b"iTXt", &large);
    let mut text = crate::metadata::PNG_KEY.to_vec();
    text.extend_from_slice(&[0; 5]);
    text.extend_from_slice(packet);
    chunk(&mut encoded, b"iTXt", &text);
    chunk(&mut encoded, b"IEND", &[]);
    let length = encoded.len() as u64;
    let mut input = Counted {
        input: Cursor::new(encoded),
        maximum: 0,
        total: 0,
    };
    assets::preflight_samples_reader(
        &mut input,
        length,
        assets::ColorPolicy::AssumeSrgb,
        1,
        &Control::default(),
    )
    .unwrap();
    assert_eq!(input.total as u64, length);
    assert!(input.maximum <= limits::INPUT_BUFFER_BYTES);
    input.total = 0;
    let metadata = crate::metadata::recover_reader(&mut input, length, "png", &Control::default())
        .unwrap()
        .unwrap();
    assert_eq!(metadata["envelope_sha256"], assets::sha256(packet));
    assert!(
        input.total < 512,
        "unrelated large metadata must be skipped without reading its body"
    );
    let last_body_byte = input.input.get_ref().len() - 17;
    input.input.get_mut()[last_body_byte] ^= 1;
    assert_eq!(
        assets::preflight_samples_reader(
            &mut input,
            length,
            assets::ColorPolicy::AssumeSrgb,
            1,
            &Control::default()
        )
        .unwrap_err()
        .code,
        "INVALID_IMAGE"
    );
}

#[test]
fn source_admission_checks_file_kind_size_and_initial_cancellation() {
    let dir = Directory::new();
    let path = dir.0.join("input");
    let file = File::create(&path).unwrap();
    file.set_len(limits::MAX_NATIVE_SOURCE_BYTES + 1).unwrap();
    drop(file);
    assert_eq!(
        Source::open(&path, true, &Control::default())
            .err()
            .unwrap()
            .code,
        "RESOURCE_LIMIT"
    );
    assert_eq!(
        Source::open(&dir.0, true, &Control::default())
            .err()
            .unwrap()
            .code,
        "IO_ERROR"
    );
    let control = Control::default();
    control.cancel();
    assert_eq!(
        Source::open(&path, true, &control).err().unwrap().code,
        "CANCELLED"
    );
    assert_eq!(fs::read_dir(&dir.0).unwrap().count(), 1);
}

#[test]
fn native_capture_exceeds_inline_input_without_changing_the_source() {
    let dir = Directory::new();
    let path = dir.0.join("original");
    let bytes = assets::MAX_IMPORT_BYTES + 1;
    let file = File::create(&path).unwrap();
    file.set_len(bytes).unwrap();
    drop(file);
    assert_eq!(
        Source::open(&path, false, &Control::default())
            .err()
            .unwrap()
            .code,
        "RESOURCE_LIMIT"
    );
    let mut captured = Source::open(&path, true, &Control::default()).unwrap();
    assert_eq!(captured.bytes as u64, bytes);
    captured.reader.seek(SeekFrom::Start(bytes - 1)).unwrap();
    let mut last = [1];
    captured.reader.read_exact(&mut last).unwrap();
    assert_eq!(last, [0]);
    assert_eq!(path.metadata().unwrap().len(), bytes);
    let expected = {
        let mut file = File::open(&path).unwrap();
        let mut hash = Sha256::new();
        let mut buffer = [0; 4096];
        loop {
            let read = file.read(&mut buffer).unwrap();
            if read == 0 {
                break;
            }
            hash.update(&buffer[..read]);
        }
        format!("{:x}", hash.finalize())
    };
    assert_eq!(captured.sha256, expected);
}
