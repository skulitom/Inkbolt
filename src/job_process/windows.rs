//! Original bindings to documented Windows process and job-object APIs.
use super::*;
use std::{
    ffi::c_void,
    fs::OpenOptions,
    io::Write,
    os::windows::{
        fs::OpenOptionsExt,
        io::{AsRawHandle, FromRawHandle, OwnedHandle},
        process::CommandExt,
    },
    process::{Child, Stdio},
    ptr,
    sync::{Arc, Condvar, Mutex},
    thread::JoinHandle,
    time::Instant,
};

type Handle = *mut c_void;
const EXTENDED_LIMITS: u32 = 9;
const STOP_EXIT_CODE: u32 = 0x494e4b01;
#[repr(C)]
#[derive(Default)]
struct BasicLimits {
    process_time: i64,
    job_time: i64,
    flags: u32,
    minimum_working_set: usize,
    maximum_working_set: usize,
    active_processes: u32,
    affinity: usize,
    priority: u32,
    scheduling: u32,
}
#[repr(C)]
#[derive(Default)]
struct ExtendedLimits {
    basic: BasicLimits,
    io_counters: [u64; 6],
    process_memory: usize,
    job_memory: usize,
    peak_process_memory: usize,
    peak_job_memory: usize,
}
#[repr(C)]
#[derive(Default)]
struct FileTime {
    low: u32,
    high: u32,
}

#[link(name = "kernel32")]
unsafe extern "system" {
    fn CreateJobObjectW(attributes: *const c_void, name: *const u16) -> Handle;
    fn SetInformationJobObject(
        job: Handle,
        class: u32,
        information: *const c_void,
        length: u32,
    ) -> i32;
    fn QueryInformationJobObject(
        job: Handle,
        class: u32,
        information: *mut c_void,
        length: u32,
        returned: *mut u32,
    ) -> i32;
    fn AssignProcessToJobObject(job: Handle, process: Handle) -> i32;
    fn TerminateJobObject(job: Handle, code: u32) -> i32;
    fn GetProcessTimes(
        process: Handle,
        created: *mut FileTime,
        exited: *mut FileTime,
        kernel: *mut FileTime,
        user: *mut FileTime,
    ) -> i32;
    fn OpenProcess(access: u32, inherit: i32, pid: u32) -> Handle;
    fn WaitForSingleObject(handle: Handle, milliseconds: u32) -> u32;
}

struct Job(OwnedHandle);
impl Job {
    fn new(limits: Limits) -> Result<Self, Error> {
        // Null security attributes make the unnamed handle non-inheritable.
        let raw = unsafe { CreateJobObjectW(ptr::null(), ptr::null()) };
        if raw.is_null() {
            return Err(failure(
                "JOB_PROCESS_ERROR",
                "Unable to create an owned process container",
            ));
        }
        // SAFETY: successful CreateJobObjectW transfers one owned kernel handle.
        let job = Self(unsafe { OwnedHandle::from_raw_handle(raw) });
        let info = ExtendedLimits {
            basic: BasicLimits {
                flags: 0x2000 | 0x100 | 0x8 | 0x400,
                active_processes: 1,
                ..Default::default()
            },
            process_memory: limits.memory_mib as usize * 1024 * 1024,
            ..Default::default()
        };
        // SAFETY: info has the documented C layout and remains live during the call.
        if unsafe {
            SetInformationJobObject(
                job.0.as_raw_handle(),
                EXTENDED_LIMITS,
                (&info as *const ExtendedLimits).cast(),
                size_of::<ExtendedLimits>() as u32,
            )
        } == 0
        {
            return Err(failure(
                "JOB_PROCESS_ERROR",
                "Unable to enforce worker memory and lifetime containment",
            ));
        }
        Ok(job)
    }
    fn assign(&self, child: &Child) -> Result<(), Error> {
        // SAFETY: both borrowed handles remain live for this call.
        if unsafe { AssignProcessToJobObject(self.0.as_raw_handle(), child.as_raw_handle()) } == 0 {
            return Err(failure(
                "JOB_PROCESS_ERROR",
                "Unable to contain worker; its startup gate remains closed",
            ));
        }
        Ok(())
    }
    fn terminate(&self) -> Result<(), Error> {
        // SAFETY: the private job handle contains only the assigned owned child.
        if unsafe { TerminateJobObject(self.0.as_raw_handle(), STOP_EXIT_CODE) } == 0 {
            return Err(failure("JOB_PROCESS_ERROR", "Unable to stop owned worker"));
        }
        Ok(())
    }
    fn peak(&self) -> Result<u64, Error> {
        let mut info = ExtendedLimits::default();
        // SAFETY: output points to a writable, correctly sized C-layout struct.
        if unsafe {
            QueryInformationJobObject(
                self.0.as_raw_handle(),
                EXTENDED_LIMITS,
                (&mut info as *mut ExtendedLimits).cast(),
                size_of::<ExtendedLimits>() as u32,
                ptr::null_mut(),
            )
        } == 0
        {
            return Err(failure(
                "JOB_PROCESS_ERROR",
                "Unable to measure worker committed memory",
            ));
        }
        Ok(info.peak_process_memory as u64)
    }
}
pub(super) fn created(handle: Handle) -> Result<u64, Error> {
    let (mut birth, mut exit, mut kernel, mut user) = (
        FileTime::default(),
        FileTime::default(),
        FileTime::default(),
        FileTime::default(),
    );
    // SAFETY: caller lends a live process handle; all four outputs are writable.
    if unsafe { GetProcessTimes(handle, &mut birth, &mut exit, &mut kernel, &mut user) } == 0 {
        return Err(failure(
            "JOB_PROCESS_ERROR",
            "Unable to establish worker process identity",
        ));
    }
    Ok((birth.high as u64) << 32 | birth.low as u64)
}
pub(super) fn process_state(identity: ProcessIdentity) -> Result<ProcessState, Error> {
    if identity.pid == 0 || identity.created == 0 {
        return Err(failure(
            "INVALID_REQUEST",
            "Worker process identity requires PID and creation time",
        ));
    }
    // Query and synchronization only: never open a recorded PID for termination.
    let raw = unsafe { OpenProcess(0x0010_0000 | 0x1000, 0, identity.pid) };
    if raw.is_null() {
        return Ok(
            if std::io::Error::last_os_error().raw_os_error() == Some(87) {
                ProcessState::NotRunning
            } else {
                ProcessState::Unknown
            },
        );
    }
    // SAFETY: successful OpenProcess returned one owned handle.
    let handle = unsafe { OwnedHandle::from_raw_handle(raw) };
    let Ok(birth) = created(handle.as_raw_handle()) else {
        return Ok(ProcessState::Unknown);
    };
    if birth != identity.created {
        return Ok(ProcessState::NotRunning);
    }
    // SAFETY: the queried process handle is alive and has SYNCHRONIZE rights.
    Ok(
        match unsafe { WaitForSingleObject(handle.as_raw_handle(), 0) } {
            0 => ProcessState::NotRunning,
            258 => ProcessState::Running,
            _ => ProcessState::Unknown,
        },
    )
}

/// An OS-owned exclusive lease on a persistent empty file. Never remove or
/// replace lease files; the handle also denies deletion while this lease lives.
pub struct FileLease {
    _file: File,
}
impl FileLease {
    pub fn try_acquire(path: &Path) -> Result<Option<Self>, Error> {
        super::path(path)?;
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .share_mode(1 | 2)
            .custom_flags(0x0020_0000)
            .open(path)
            .map_err(|_| failure("JOB_LEASE_ERROR", "Unable to open worker lease"))?;
        let metadata = file
            .metadata()
            .map_err(|_| failure("JOB_LEASE_ERROR", "Unable to inspect worker lease"))?;
        if !metadata.is_file() || metadata.file_type().is_symlink() || metadata.len() != 0 {
            return Err(failure(
                "JOB_LEASE_ERROR",
                "Worker lease must be an empty regular file; existing content is preserved",
            ));
        }
        match file.try_lock() {
            Ok(()) => Ok(Some(Self { _file: file })),
            Err(std::fs::TryLockError::WouldBlock) => Ok(None),
            Err(std::fs::TryLockError::Error(_)) => Err(failure(
                "JOB_LEASE_ERROR",
                "Unable to acquire OS worker lease",
            )),
        }
    }
}

#[derive(Default)]
struct Watch {
    finished: bool,
    stop: Option<StopReason>,
}
type Signal = Arc<(Mutex<Watch>, Condvar)>;

/// Assigned and bounded, but not yet permitted to run job work.
pub struct PendingRunner {
    runner: Runner,
}
impl PendingRunner {
    pub fn identity(&self) -> ProcessIdentity {
        self.runner.identity
    }
    /// Release the one-byte start gate only after durable ownership is recorded.
    pub fn start(mut self) -> Result<Runner, Error> {
        let mut gate =
            self.runner.child.stdin.take().ok_or_else(|| {
                failure("JOB_START_ABORTED", "Worker startup gate is unavailable")
            })?;
        gate.write_all(&[START_BYTE]).map_err(|_| {
            failure(
                "JOB_START_ABORTED",
                "Worker exited before startup was permitted",
            )
        })?;
        drop(gate);
        Ok(self.runner)
    }
}

/// Owns exactly one cooperating process and a deadline watchdog. Dropping this
/// value terminates and reaps that child; no PID-based termination is performed.
pub struct Runner {
    child: Child,
    job: Arc<Job>,
    identity: ProcessIdentity,
    launched: Instant,
    signal: Signal,
    watchdog: Option<JoinHandle<()>>,
    report: Option<Report>,
    _executable: File,
}
impl Runner {
    pub fn identity(&self) -> ProcessIdentity {
        self.identity
    }
    pub fn stop(&mut self) -> Result<(), Error> {
        if self.poll()?.is_some() {
            return Ok(());
        }
        let mut watch = self.signal.0.lock().unwrap_or_else(|e| e.into_inner());
        self.job.terminate()?;
        watch.stop.get_or_insert(StopReason::Cancelled);
        Ok(())
    }
    pub fn poll(&mut self) -> Result<Option<Report>, Error> {
        if let Some(report) = &self.report {
            return Ok(Some(report.clone()));
        }
        let Some(status) = self
            .child
            .try_wait()
            .map_err(|_| failure("JOB_PROCESS_ERROR", "Unable to inspect owned worker exit"))?
        else {
            return Ok(None);
        };
        self.finish_watchdog();
        let stop = self.signal.0.lock().unwrap_or_else(|e| e.into_inner()).stop;
        let report = Report {
            process: self.identity,
            exit_code: status.code(),
            stop_requested: stop,
            observed_elapsed_ms: self.launched.elapsed().as_millis().min(u64::MAX as u128) as u64,
            peak_committed_bytes: self.job.peak()?,
        };
        self.report = Some(report.clone());
        Ok(Some(report))
    }
    /// Bounded polling convenience; the watchdog enforces the deadline even when
    /// this method is never called. The result remains available on later calls.
    pub fn wait_slice(&mut self, duration: Duration) -> Result<Option<Report>, Error> {
        slice_duration(duration)?;
        let until = Instant::now() + duration;
        loop {
            if let Some(report) = self.poll()? {
                return Ok(Some(report));
            }
            let remaining = until.saturating_duration_since(Instant::now());
            if remaining.is_zero() {
                return Ok(None);
            }
            std::thread::sleep(remaining.min(Duration::from_millis(5)));
        }
    }
    fn finish_watchdog(&mut self) {
        {
            let mut watch = self.signal.0.lock().unwrap_or_else(|e| e.into_inner());
            watch.finished = true;
            self.signal.1.notify_all();
        }
        if let Some(thread) = self.watchdog.take() {
            let _ = thread.join();
        }
    }
}
impl Drop for Runner {
    fn drop(&mut self) {
        let _ = self.job.terminate();
        // Closing stdin also releases an unstarted child's read on every error.
        self.child.stdin.take();
        let _ = self.child.kill();
        let _ = self.child.wait();
        self.finish_watchdog();
    }
}

struct StartingChild(Option<Child>);
impl Drop for StartingChild {
    fn drop(&mut self) {
        if let Some(child) = &mut self.0 {
            child.stdin.take();
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}
pub(super) fn spawn(
    mut command: Command,
    executable: &Executable,
    limits: Limits,
    control: &Control,
) -> Result<PendingRunner, Error> {
    limits.validate()?;
    if Path::new(command.get_program()) != executable.path {
        return Err(failure(
            "JOB_EXECUTABLE_IDENTITY",
            "Worker command must name exactly the pinned absolute executable",
        ));
    }
    let held = executable.verify(control)?;
    let job = Arc::new(Job::new(limits)?);
    control.check()?;
    let launched = Instant::now();
    command
        .creation_flags(0x0800_0000)
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    let mut starting =
        StartingChild(Some(command.spawn().map_err(|_| {
            failure("JOB_PROCESS_ERROR", "Unable to start worker process")
        })?));
    let child = starting.0.as_ref().unwrap();
    #[cfg(test)]
    super::tests::checkpoint("before_assignment", child);
    job.assign(child)?;
    #[cfg(test)]
    super::tests::checkpoint("after_assignment", child);
    let identity = ProcessIdentity {
        pid: child.id(),
        created: created(child.as_raw_handle())?,
    };
    // The watchdog owns a second process handle only for waiting, not reopening a PID.
    let watched_process = child.as_handle().try_clone_to_owned().map_err(|_| {
        failure(
            "JOB_PROCESS_ERROR",
            "Unable to retain owned worker wait handle",
        )
    })?;
    let signal: Signal = Arc::default();
    let watched_signal = signal.clone();
    let watched_job = job.clone();
    let deadline = launched + Duration::from_millis(limits.lifetime_ms);
    let watchdog = std::thread::Builder::new()
        .name("inkbolt-job-deadline".into())
        .spawn(move || {
            let (mutex, condition) = &*watched_signal;
            let mut watch = mutex.lock().unwrap_or_else(|e| e.into_inner());
            while !watch.finished {
                let remaining = deadline.saturating_duration_since(Instant::now());
                if remaining.is_zero() {
                    // SAFETY: a cloned owned process handle remains live in this thread.
                    if unsafe { WaitForSingleObject(watched_process.as_raw_handle(), 0) } == 258
                        && watched_job.terminate().is_ok()
                    {
                        watch.stop.get_or_insert(StopReason::Deadline);
                    }
                    break;
                }
                watch = condition
                    .wait_timeout(watch, remaining)
                    .unwrap_or_else(|e| e.into_inner())
                    .0;
            }
        })
        .map_err(|_| {
            failure(
                "JOB_PROCESS_ERROR",
                "Unable to start worker deadline watchdog",
            )
        })?;
    let runner = Runner {
        child: starting.0.take().unwrap(),
        job,
        identity,
        launched,
        signal,
        watchdog: Some(watchdog),
        report: None,
        _executable: held,
    };
    // Cancellation after launch drops and reaps the still-gated runner.
    control.check()?;
    Ok(PendingRunner { runner })
}

use std::os::windows::io::AsHandle;
