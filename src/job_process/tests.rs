use super::*;
use std::{
    fs,
    os::windows::process::CommandExt,
    process::{Child, Stdio},
    sync::{
        OnceLock,
        atomic::{AtomicU64, Ordering},
    },
    time::Instant,
};

static NEXT: AtomicU64 = AtomicU64::new(0);
static EXECUTABLE: OnceLock<Executable> = OnceLock::new();
fn executable() -> &'static Executable {
    EXECUTABLE.get_or_init(|| {
        Executable::inspect(&std::env::current_exe().unwrap(), &Control::default()).unwrap()
    })
}
struct Owned {
    root: PathBuf,
    children: Vec<Child>,
}
impl Owned {
    fn new() -> Self {
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "inkbolt-job-process-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        Self {
            root,
            children: Vec::new(),
        }
    }
    fn command(&self, worker: &str, action: &str) -> Command {
        let mut command = Command::new(&executable().path);
        command
            .args(["--exact", worker, "--nocapture"])
            .env("INKBOLT_PROCESS_TEST_ROOT", &self.root)
            .env("INKBOLT_PROCESS_TEST_ACTION", action)
            .creation_flags(0x0800_0000)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        command
    }
    fn runner(&self, action: &str, limits: Limits) -> PendingRunner {
        spawn(
            self.command("job_process::tests::gated_worker", action),
            executable(),
            limits,
            &Control::default(),
        )
        .unwrap()
    }
    fn wait_file(&self, name: &str) {
        let start = Instant::now();
        while !self.root.join(name).exists() {
            assert!(
                start.elapsed() < Duration::from_secs(20),
                "No {name} marker"
            );
            std::thread::sleep(Duration::from_millis(5));
        }
    }
    fn finish(&mut self, index: usize) {
        let start = Instant::now();
        loop {
            if let Some(status) = self.children[index].try_wait().unwrap() {
                assert!(status.success());
                return;
            }
            assert!(start.elapsed() < Duration::from_secs(20));
            std::thread::sleep(Duration::from_millis(5));
        }
    }
    fn kill(&mut self, index: usize) {
        self.children[index].kill().unwrap();
        self.children[index].wait().unwrap();
    }
}
impl Drop for Owned {
    fn drop(&mut self) {
        for child in &mut self.children {
            let _ = child.kill();
            let _ = child.wait();
        }
        // Contained grandchildren exit when their supervisor's job handle closes;
        // unassigned cooperating children exit when its startup pipe closes.
        if let Ok(bytes) = fs::read(self.root.join("child.json")) {
            let identity: ProcessIdentity = serde_json::from_slice(&bytes).unwrap();
            wait_gone(identity);
        }
        let base = std::env::temp_dir().canonicalize().unwrap();
        let root = self.root.canonicalize().unwrap();
        assert_eq!(root.parent(), Some(base.as_path()));
        assert!(
            root.file_name()
                .unwrap()
                .to_string_lossy()
                .starts_with("inkbolt-job-process-")
        );
        fs::remove_dir_all(root).unwrap();
    }
}
fn report(runner: &mut Runner) -> Report {
    let start = Instant::now();
    loop {
        if let Some(report) = runner.wait_slice(Duration::from_millis(100)).unwrap() {
            return report;
        }
        assert!(start.elapsed() < Duration::from_secs(20));
    }
}
fn wait_gone(identity: ProcessIdentity) {
    let start = Instant::now();
    while process_state(identity).unwrap() != ProcessState::NotRunning {
        assert!(
            start.elapsed() < Duration::from_secs(20),
            "Owned worker did not exit"
        );
        std::thread::sleep(Duration::from_millis(5));
    }
}
fn test_root() -> Option<PathBuf> {
    std::env::var_os("INKBOLT_PROCESS_TEST_ROOT").map(PathBuf::from)
}

pub(super) fn checkpoint(stage: &str, child: &Child) {
    if std::env::var("INKBOLT_PROCESS_TEST_POINT").ok().as_deref() != Some(stage) {
        return;
    }
    use std::os::windows::io::AsRawHandle;
    let root = test_root().unwrap();
    let identity = ProcessIdentity {
        pid: child.id(),
        created: super::windows::created(child.as_raw_handle()).unwrap(),
    };
    fs::write(
        root.join("child.json"),
        serde_json::to_vec(&identity).unwrap(),
    )
    .unwrap();
    fs::write(root.join("checkpoint"), stage).unwrap();
    while !root.join("release").exists() {
        std::thread::sleep(Duration::from_millis(5));
    }
}

#[link(name = "kernel32")]
unsafe extern "system" {
    fn VirtualAlloc(
        address: *mut std::ffi::c_void,
        size: usize,
        kind: u32,
        protect: u32,
    ) -> *mut std::ffi::c_void;
    fn VirtualFree(address: *mut std::ffi::c_void, size: usize, kind: u32) -> i32;
}
#[test]
fn gated_worker() {
    let Some(root) = test_root() else {
        return;
    };
    // Test instrumentation marks arrival, before the real gate permits work.
    fs::write(root.join("waiting"), b"waiting").unwrap();
    if await_start(std::io::stdin().lock()).is_err() {
        return;
    }
    fs::write(root.join("started"), b"started").unwrap();
    match std::env::var("INKBOLT_PROCESS_TEST_ACTION")
        .unwrap()
        .as_str()
    {
        "exit" => (),
        "hold" => {
            while !root.join("worker_release").exists() {
                std::thread::sleep(Duration::from_millis(5));
            }
        }
        "allocate" => {
            // Use a fallible native commit so limit rejection is observable without
            // an allocator abort or an ambiguous nonzero child exit.
            let buffer =
                unsafe { VirtualAlloc(std::ptr::null_mut(), 128 * 1024 * 1024, 0x3000, 4) };
            fs::write(
                root.join("allocated"),
                if buffer.is_null() {
                    b"no".as_slice()
                } else {
                    b"yes".as_slice()
                },
            )
            .unwrap();
            if !buffer.is_null() {
                assert_ne!(unsafe { VirtualFree(buffer, 0, 0x8000) }, 0);
            }
        }
        "descendant" => {
            let result = Command::new(std::env::current_exe().unwrap())
                .args(["--exact", "job_process::tests::descendant_worker"])
                .creation_flags(0x0800_0000)
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn();
            if let Ok(mut child) = result {
                let _ = child.wait();
            }
        }
        other => panic!("Unexpected worker action {other}"),
    }
}
#[test]
fn descendant_worker() {
    if let Some(root) = test_root() {
        fs::write(root.join("descendant"), b"unexpected").unwrap();
    }
}
#[test]
fn supervisor_worker() {
    let Some(root) = test_root() else {
        return;
    };
    let action = std::env::var("INKBOLT_PROCESS_TEST_ACTION").unwrap();
    if action == "lease" {
        let _lease = FileLease::try_acquire(&root.join("worker.lock"))
            .unwrap()
            .unwrap();
        fs::write(root.join("checkpoint"), b"lease").unwrap();
        while !root.join("release").exists() {
            std::thread::sleep(Duration::from_millis(5));
        }
        return;
    }
    let mut command = Command::new(&executable().path);
    command
        .args(["--exact", "job_process::tests::gated_worker", "--nocapture"])
        .env("INKBOLT_PROCESS_TEST_ACTION", "hold");
    let pending = spawn(
        command,
        executable(),
        Limits::default(),
        &Control::default(),
    )
    .unwrap();
    fs::write(
        root.join("child.json"),
        serde_json::to_vec(&pending.identity()).unwrap(),
    )
    .unwrap();
    let _runner = pending.start().unwrap();
    fs::write(root.join("checkpoint"), b"running").unwrap();
    while !root.join("release").exists() {
        std::thread::sleep(Duration::from_millis(5));
    }
}

#[test]
fn start_gate_identity_and_natural_exit_are_real_process_boundaries() {
    let owned = Owned::new();
    let pending = owned.runner("exit", Limits::default());
    owned.wait_file("waiting");
    assert!(!owned.root.join("started").exists());
    let identity = pending.identity();
    assert_eq!(process_state(identity).unwrap(), ProcessState::Running);
    assert_eq!(
        process_state(ProcessIdentity {
            created: identity.created + 1,
            ..identity
        })
        .unwrap(),
        ProcessState::NotRunning
    );
    let mut runner = pending.start().unwrap();
    let outcome = report(&mut runner);
    assert_eq!(outcome.process, identity);
    assert_eq!(outcome.exit_code, Some(0));
    assert_eq!(outcome.stop_requested, None);
    assert!(outcome.peak_committed_bytes > 0);
    assert_eq!(
        runner.poll().unwrap().unwrap().peak_committed_bytes,
        outcome.peak_committed_bytes
    );
    assert_eq!(process_state(identity).unwrap(), ProcessState::NotRunning);
    assert!(owned.root.join("started").exists());
    assert_eq!(
        runner
            .wait_slice(Duration::from_millis(1001))
            .unwrap_err()
            .code,
        "INVALID_REQUEST"
    );
}

#[test]
fn process_memory_limit_rejects_actual_commit_and_records_peak() {
    for (memory_mib, expected) in [(64, "no"), (256, "yes")] {
        let owned = Owned::new();
        let mut runner = owned
            .runner(
                "allocate",
                Limits {
                    memory_mib,
                    ..Default::default()
                },
            )
            .start()
            .unwrap();
        let result = report(&mut runner);
        assert_eq!(result.exit_code, Some(0));
        assert_eq!(
            fs::read_to_string(owned.root.join("allocated")).unwrap(),
            expected
        );
        assert!(result.peak_committed_bytes <= memory_mib as u64 * 1024 * 1024);
        if expected == "yes" {
            assert!(result.peak_committed_bytes >= 128 * 1024 * 1024);
        }
    }
}
#[test]
fn deadline_is_enforced_without_polling_and_cancel_and_drop_reap_owned_children() {
    let owned = Owned::new();
    let mut runner = owned
        .runner(
            "hold",
            Limits {
                lifetime_ms: 1500,
                ..Default::default()
            },
        )
        .start()
        .unwrap();
    owned.wait_file("started");
    let identity = runner.identity();
    wait_gone(identity); // Does not call Runner.poll: the watchdog must stop it.
    assert_eq!(
        report(&mut runner).stop_requested,
        Some(StopReason::Deadline)
    );

    let owned_cancel = Owned::new();
    let mut cancelled = owned_cancel
        .runner("hold", Limits::default())
        .start()
        .unwrap();
    owned_cancel.wait_file("started");
    cancelled.stop().unwrap();
    assert_eq!(
        report(&mut cancelled).stop_requested,
        Some(StopReason::Cancelled)
    );
    cancelled.stop().unwrap();

    let owned_drop = Owned::new();
    let dropped = owned_drop
        .runner("hold", Limits::default())
        .start()
        .unwrap();
    owned_drop.wait_file("started");
    let identity = dropped.identity();
    drop(dropped);
    assert_eq!(process_state(identity).unwrap(), ProcessState::NotRunning);

    let owned_gate = Owned::new();
    let pending = owned_gate.runner("hold", Limits::default());
    owned_gate.wait_file("waiting");
    let identity = pending.identity();
    drop(pending);
    assert_eq!(process_state(identity).unwrap(), ProcessState::NotRunning);
    assert!(!owned_gate.root.join("started").exists());
}

#[test]
fn supervisor_death_before_assignment_after_assignment_and_running_leaves_no_worker() {
    for point in ["before_assignment", "after_assignment", "running"] {
        let mut owned = Owned::new();
        let mut command = owned.command("job_process::tests::supervisor_worker", "hold");
        if point != "running" {
            command.env("INKBOLT_PROCESS_TEST_POINT", point);
        }
        owned.children.push(command.spawn().unwrap());
        owned.wait_file("checkpoint");
        owned.wait_file(if point == "running" {
            "started"
        } else {
            "waiting"
        });
        let identity =
            serde_json::from_slice(&fs::read(owned.root.join("child.json")).unwrap()).unwrap();
        owned.kill(0);
        wait_gone(identity);
        assert_eq!(owned.root.join("started").exists(), point == "running");
    }
}

#[test]
fn worker_cannot_launch_an_uncontained_descendant() {
    let owned = Owned::new();
    let mut runner = owned
        .runner("descendant", Limits::default())
        .start()
        .unwrap();
    assert_eq!(report(&mut runner).exit_code, Some(0));
    assert!(!owned.root.join("descendant").exists());
}

#[test]
fn persistent_lease_survives_contention_and_is_released_on_process_death() {
    let mut owned = Owned::new();
    let path = owned.root.join("worker.lock");
    let held = FileLease::try_acquire(&path).unwrap().unwrap();
    assert!(FileLease::try_acquire(&path).unwrap().is_none());
    assert!(
        fs::remove_file(&path).is_err(),
        "An open lease must not be replaceable"
    );
    drop(held);
    let child = owned
        .command("job_process::tests::supervisor_worker", "lease")
        .spawn()
        .unwrap();
    owned.children.push(child);
    owned.wait_file("checkpoint");
    assert!(FileLease::try_acquire(&path).unwrap().is_none());
    owned.kill(0);
    let recovered = FileLease::try_acquire(&path).unwrap().unwrap();
    drop(recovered);
    assert_eq!(fs::read(&path).unwrap(), b"");
    fs::write(&path, b"unrelated data").unwrap();
    assert!(FileLease::try_acquire(&path).is_err());
    assert_eq!(fs::read(&path).unwrap(), b"unrelated data");
}

#[test]
fn executable_identity_limits_and_gate_errors_preserve_inputs_without_launching() {
    let owned = Owned::new();
    let path = owned.root.join("original.bin");
    fs::write(&path, b"original synthetic executable identity fixture").unwrap();
    let identity = Executable::inspect(&path, &Control::default()).unwrap();
    let held = identity.verify(&Control::default()).unwrap();
    assert!(std::fs::OpenOptions::new().write(true).open(&path).is_err());
    assert!(fs::remove_file(&path).is_err());
    drop(held);
    fs::write(&path, b"changed synthetic executable identity fixture!").unwrap();
    let error = match spawn(
        Command::new(&path),
        &identity,
        Limits::default(),
        &Control::default(),
    ) {
        Ok(_) => panic!("Changed executable was admitted"),
        Err(e) => e,
    };
    assert_eq!(error.code, "JOB_EXECUTABLE_CHANGED");
    assert_eq!(
        fs::read(&path).unwrap(),
        b"changed synthetic executable identity fixture!"
    );
    for limits in [
        Limits {
            lifetime_ms: 0,
            ..Default::default()
        },
        Limits {
            lifetime_ms: MAX_LIFETIME_MS + 1,
            ..Default::default()
        },
        Limits {
            memory_mib: 63,
            ..Default::default()
        },
        Limits {
            memory_mib: MAX_MEMORY_MIB + 1,
            ..Default::default()
        },
    ] {
        assert_eq!(limits.validate().unwrap_err().code, "INVALID_REQUEST");
    }
    assert!(await_start([].as_slice()).is_err());
    assert!(await_start([1].as_slice()).is_err());
    assert!(await_start([START_BYTE].as_slice()).is_ok());
    assert!(process_state(ProcessIdentity { pid: 0, created: 1 }).is_err());
    let cancelled = Control::default();
    cancelled.cancel();
    let error = match spawn(
        Command::new(&executable().path),
        executable(),
        Limits::default(),
        &cancelled,
    ) {
        Ok(_) => panic!("Cancelled spawn"),
        Err(e) => e,
    };
    assert_eq!(error.code, "CANCELLED");
    assert!(!owned.root.join("started").exists());
}

#[test]
fn cooperative_lease_exit_also_releases_the_same_persistent_file() {
    let mut owned = Owned::new();
    let child = owned
        .command("job_process::tests::supervisor_worker", "lease")
        .spawn()
        .unwrap();
    owned.children.push(child);
    owned.wait_file("checkpoint");
    fs::write(owned.root.join("release"), b"release").unwrap();
    owned.finish(0);
    assert!(
        FileLease::try_acquire(&owned.root.join("worker.lock"))
            .unwrap()
            .is_some()
    );
}

#[test]
fn an_unreleased_start_gate_also_has_a_deadline() {
    let owned = Owned::new();
    let pending = owned.runner(
        "hold",
        Limits {
            lifetime_ms: 1500,
            ..Default::default()
        },
    );
    owned.wait_file("waiting");
    wait_gone(pending.identity());
    assert!(!owned.root.join("started").exists());
    drop(pending);
}

#[test]
fn capability_reporting_distinguishes_containment_from_a_durable_queue() {
    let capabilities = crate::execute(crate::Request::Capabilities {}).unwrap();
    let details = &capabilities["job_process"];
    assert_eq!(details["supported_here"], true);
    assert_eq!(details["durable_queue"], false);
    assert_eq!(details["publication_reconciliation"], false);
    assert_eq!(details["maximum_lifetime_ms"], MAX_LIFETIME_MS);
    assert_eq!(details["maximum_committed_memory_mib"], MAX_MEMORY_MIB);
    assert_eq!(details["active_processes"], 1);
}
