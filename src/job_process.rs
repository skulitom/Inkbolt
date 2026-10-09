//! Local process containment for cooperating background-job runners.
//!
//! This is a library building block, not a durable queue or a security sandbox.
//! A child must call [`await_start`] before doing any work and exit on failure.
//! Its stdin is exclusively the startup gate; outcomes belong in durable storage.
//! Only the Windows backend currently has a verified implementation.
use crate::{Error, assets, control::Control};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
#[cfg(windows)]
use std::time::Duration;
use std::{
    fs::File,
    io::Read,
    path::{Path, PathBuf},
    process::Command,
};

#[cfg(all(test, windows))]
mod tests;
#[cfg(windows)]
mod windows;
#[cfg(windows)]
pub use windows::{FileLease, PendingRunner, Runner};

pub const MAX_EXECUTABLE_BYTES: u64 = 512 * 1024 * 1024;
pub const MAX_LIFETIME_MS: u64 = 3_600_000;
pub const MAX_MEMORY_MIB: u32 = 2048;
const START_BYTE: u8 = 0xa7;

fn failure(code: &'static str, message: &str) -> Error {
    Error::new(code, message)
}
fn path(path: &Path) -> Result<(), Error> {
    assets::absolute(path)?;
    if path.as_os_str().len() > 4096 {
        return Err(failure(
            "INVALID_PATH",
            "Worker path exceeds 4096 characters",
        ));
    }
    Ok(())
}

/// Content identity captured at submission; the runner checks it with a write-
/// and delete-denying handle before spawning and retains that handle until exit.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Executable {
    pub path: PathBuf,
    pub bytes: u64,
    pub sha256: String,
}
impl Executable {
    pub fn inspect(path: &Path, control: &Control) -> Result<Self, Error> {
        self::path(path)?;
        let mut file = open_executable(path)?;
        let (bytes, sha256) = digest(&mut file, control)?;
        Ok(Self {
            path: path.into(),
            bytes,
            sha256,
        })
    }
    fn verify(&self, control: &Control) -> Result<File, Error> {
        path(&self.path)?;
        if self.bytes == 0
            || self.bytes > MAX_EXECUTABLE_BYTES
            || self.sha256.len() != 64
            || !self
                .sha256
                .bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
        {
            return Err(failure(
                "JOB_EXECUTABLE_IDENTITY",
                "Invalid worker executable identity",
            ));
        }
        let mut file = open_executable(&self.path)?;
        let (bytes, hash) = digest(&mut file, control)?;
        if bytes != self.bytes || hash != self.sha256 {
            return Err(failure(
                "JOB_EXECUTABLE_CHANGED",
                "Worker executable differs from the submitted content identity",
            ));
        }
        Ok(file)
    }
}
fn open_executable(path: &Path) -> Result<File, Error> {
    let mut options = std::fs::OpenOptions::new();
    options.read(true);
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        // Deny replacement/writes for the whole process lifetime. Open a final
        // reparse point itself so metadata can reject it, rather than following it.
        options.share_mode(1).custom_flags(0x0020_0000);
    }
    let file = options.open(path).map_err(|_| {
        failure(
            "JOB_EXECUTABLE_UNAVAILABLE",
            "Unable to hold the worker executable against replacement or writes",
        )
    })?;
    let metadata = file
        .metadata()
        .map_err(|_| failure("IO_ERROR", "Unable to inspect worker executable"))?;
    if !metadata.is_file()
        || metadata.file_type().is_symlink()
        || metadata.len() == 0
        || metadata.len() > MAX_EXECUTABLE_BYTES
    {
        return Err(failure(
            "JOB_EXECUTABLE_IDENTITY",
            "Worker executable must be a nonempty regular file within 512 MiB",
        ));
    }
    Ok(file)
}
fn digest(file: &mut File, control: &Control) -> Result<(u64, String), Error> {
    let mut hash = Sha256::new();
    let mut count = 0;
    let mut buffer = [0u8; 65536];
    loop {
        control.check()?;
        let size = file
            .read(&mut buffer)
            .map_err(|_| failure("IO_ERROR", "Unable to read worker executable"))?;
        if size == 0 {
            break;
        }
        count += size as u64;
        if count > MAX_EXECUTABLE_BYTES {
            return Err(failure(
                "RESOURCE_LIMIT",
                "Worker executable exceeds 512 MiB",
            ));
        }
        hash.update(&buffer[..size]);
    }
    Ok((count, format!("{:x}", hash.finalize())))
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Limits {
    /// Wall time from process launch, including time awaiting the start gate.
    pub lifetime_ms: u64,
    /// Maximum committed process memory, not resident set size or an estimate.
    pub memory_mib: u32,
}
impl Default for Limits {
    fn default() -> Self {
        Self {
            lifetime_ms: 300_000,
            memory_mib: 512,
        }
    }
}
impl Limits {
    fn validate(self) -> Result<(), Error> {
        if self.lifetime_ms == 0
            || self.lifetime_ms > MAX_LIFETIME_MS
            || !(64..=MAX_MEMORY_MIB).contains(&self.memory_mib)
        {
            return Err(failure(
                "INVALID_REQUEST",
                "Worker limits require 1..3600000 ms and 64..2048 MiB committed memory",
            ));
        }
        Ok(())
    }
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ProcessIdentity {
    pub pid: u32,
    /// Windows creation FILETIME in 100 ns units, used together with the PID.
    pub created: u64,
}
#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ProcessState {
    Running,
    NotRunning,
    Unknown,
}
#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum StopReason {
    Cancelled,
    Deadline,
}
#[derive(Clone, Debug, Serialize)]
pub struct Report {
    pub process: ProcessIdentity,
    pub exit_code: Option<i32>,
    /// A termination request, not proof that it caused the exit. A publication
    /// receipt must still be reconciled before assigning a job's terminal state.
    pub stop_requested: Option<StopReason>,
    /// Monotonic time from launch until the owner first observes exit. This can
    /// include time awaiting startup and time after actual process exit.
    pub observed_elapsed_ms: u64,
    pub peak_committed_bytes: u64,
}

/// Block before any job work. Parent death/closed stdin, malformed gate bytes,
/// and read failures reject startup. This function does not read job requests.
pub fn await_start(mut input: impl Read) -> Result<(), Error> {
    let mut byte = [0];
    input
        .read_exact(&mut byte)
        .map_err(|_| failure("JOB_START_ABORTED", "Worker owner closed the startup gate"))?;
    if byte[0] != START_BYTE {
        return Err(failure("JOB_START_ABORTED", "Invalid worker startup gate"));
    }
    Ok(())
}

/// Spawn a hidden cooperating process, assign its limits, and leave its start
/// gate closed. The command must name exactly the pinned absolute executable.
/// Command stdin/stdout/stderr are replaced with the gate and null outputs.
#[cfg(windows)]
pub fn spawn(
    command: Command,
    executable: &Executable,
    limits: Limits,
    control: &Control,
) -> Result<PendingRunner, Error> {
    windows::spawn(command, executable, limits, control)
}

/// Inspect identity without terminating or signalling any process. Access
/// denial returns Unknown; a reused PID does not identify the recorded owner.
#[cfg(windows)]
pub fn process_state(identity: ProcessIdentity) -> Result<ProcessState, Error> {
    windows::process_state(identity)
}

// Keep platform availability explicit rather than silently weakening the same API.
#[cfg(not(windows))]
pub struct PendingRunner;
#[cfg(not(windows))]
pub fn spawn(
    _command: Command,
    executable: &Executable,
    limits: Limits,
    control: &Control,
) -> Result<PendingRunner, Error> {
    limits.validate()?;
    let _ = executable.verify(control)?;
    Err(failure(
        "UNSUPPORTED_PLATFORM",
        "Contained job processes currently require Windows",
    ))
}
#[cfg(not(windows))]
pub fn process_state(_identity: ProcessIdentity) -> Result<ProcessState, Error> {
    Err(failure(
        "UNSUPPORTED_PLATFORM",
        "Worker identity inspection currently requires Windows",
    ))
}

#[cfg(windows)]
fn slice_duration(duration: Duration) -> Result<(), Error> {
    if duration > Duration::from_secs(1) {
        return Err(failure(
            "INVALID_REQUEST",
            "A process wait slice cannot exceed one second",
        ));
    }
    Ok(())
}
