use super::*;
use std::{
    fs,
    os::windows::{
        io::{AsRawHandle, FromRawHandle, OwnedHandle},
        process::CommandExt,
    },
    process::{Child, Command, Stdio},
    sync::atomic::{AtomicU64, Ordering},
};
static NEXT: AtomicU64 = AtomicU64::new(0);
pub(super) fn checkpoint(stage: &str) {
    // Publication fault points pause only the renderer, never the supervisor's
    // subsequent recovery of the same receipt after that renderer is killed.
    if ["publication_ready", "publication_locked", "published"].contains(&stage)
        && std::env::var("INKBOLT_JOB_HELPER").ok().as_deref() != Some("attempt")
    {
        return;
    }
    if std::env::var("INKBOLT_JOB_POINT").ok().as_deref() != Some(stage) {
        return;
    }
    let root = PathBuf::from(std::env::var_os("INKBOLT_JOB_TEST_ROOT").unwrap());
    fs::write(root.join("ready"), stage).unwrap();
    while !root.join("release").exists() {
        std::thread::sleep(Duration::from_millis(5));
    }
}
struct Owned {
    root: PathBuf,
    children: Vec<Child>,
}
impl Owned {
    fn new() -> Self {
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "inkbolt-jobs-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        Self {
            root,
            children: vec![],
        }
    }
    fn jobs(&self) -> PathBuf {
        self.root.join("jobs")
    }
    fn start(&mut self, point: &str, lifetime: u64) {
        let request = request(&self.root, "one", lifetime);
        fs::write(
            self.root.join("request.json"),
            serde_json::to_vec(&request).unwrap(),
        )
        .unwrap();
        self.children.push(
            Command::new(std::env::current_exe().unwrap())
                .args(["--exact", "jobs::tests::helper", "--nocapture"])
                .env("INKBOLT_JOB_HELPER", "submit")
                .env("INKBOLT_JOB_TEST_ROOT", &self.root)
                .env("INKBOLT_JOB_POINT", point)
                .creation_flags(0x0800_0000)
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .unwrap(),
        );
        self.until(|| self.root.join("ready").exists());
    }
    fn until(&self, mut condition: impl FnMut() -> bool) {
        let began = Instant::now();
        while !condition() {
            assert!(
                began.elapsed() < Duration::from_secs(30),
                "Timed out at {:?}",
                self.root
            );
            std::thread::sleep(Duration::from_millis(10));
        }
    }
    fn release(&self) {
        fs::write(self.root.join("release"), b"release").unwrap();
    }
    fn commit_contending_writer(&self, tx: rusqlite::Transaction<'_>) {
        // A supervisor reader can outlast one SQLite busy wait. Preserve this
        // fixture's deliberate writer and its cancellation update while retrying
        // COMMIT; Transaction::commit consumes and rolls it back on a busy error.
        self.until(|| match tx.execute_batch("COMMIT") {
            Ok(()) => true,
            Err(error)
                if matches!(
                    error.sqlite_error_code(),
                    Some(rusqlite::ErrorCode::DatabaseBusy | rusqlite::ErrorCode::DatabaseLocked)
                ) =>
            {
                assert!(!tx.is_autocommit());
                false
            }
            Err(error) => panic!("Unable to commit fixture writer: {error}"),
        });
        assert!(tx.is_autocommit());
    }
    fn state(&self) -> State {
        store::state(&store::required(&self.jobs()).unwrap(), "one").unwrap()
    }
    fn terminal(&self) -> Value {
        self.terminal_for("one")
    }
    fn terminal_for(&self, id: &str) -> Value {
        let mut last = json!(null);
        self.until(|| match status(&self.jobs(), id, &Control::default()) {
            Ok(r) => {
                last = r;
                !["queued", "running"].contains(&last["state"].as_str().unwrap())
            }
            Err(e) if e.code == "JOB_BUSY" => false,
            Err(e) => panic!("{e:?}"),
        });
        last
    }
    fn kill_supervisor(&self) {
        let owner = store::runtime(&store::required(&self.jobs()).unwrap())
            .unwrap()
            .owner
            .unwrap();
        terminate_owned(owner);
    }
}
#[link(name = "kernel32")]
unsafe extern "system" {
    fn OpenProcess(access: u32, inherit: i32, pid: u32) -> *mut std::ffi::c_void;
    fn TerminateProcess(handle: *mut std::ffi::c_void, code: u32) -> i32;
    fn WaitForSingleObject(handle: *mut std::ffi::c_void, milliseconds: u32) -> u32;
}
fn terminate_owned(identity: job_process::ProcessIdentity) {
    if job_process::process_state(identity).unwrap() == job_process::ProcessState::NotRunning {
        return;
    }
    let raw = unsafe { OpenProcess(0x0010_0000 | 0x1000 | 1, 0, identity.pid) };
    if raw.is_null() {
        assert_eq!(
            job_process::process_state(identity).unwrap(),
            job_process::ProcessState::NotRunning
        );
        return;
    }
    let handle = unsafe { OwnedHandle::from_raw_handle(raw) };
    assert_eq!(
        job_process::identity_creation_for_test(handle.as_raw_handle()).unwrap(),
        identity.created,
        "Never terminate a reused PID"
    );
    // Another owned kill-on-close may already be terminating it. The handle,
    // identity and bounded terminal wait remain authoritative in that race.
    let _ = unsafe { TerminateProcess(handle.as_raw_handle(), 19) };
    assert_eq!(
        unsafe { WaitForSingleObject(handle.as_raw_handle(), 10000) },
        0
    );
}
impl Drop for Owned {
    fn drop(&mut self) {
        let _ = fs::write(self.root.join("release"), b"release");
        for child in &mut self.children {
            let _ = child.kill();
            let _ = child.wait();
        }
        if let Ok(db) = store::required(&self.jobs()) {
            if let Ok(runtime) = store::runtime(&db)
                && let Some(owner) = runtime.owner
            {
                terminate_owned(owner);
            }
            if let Ok(ids) = store::ids(&db) {
                for id in ids {
                    if let Ok(state) = store::state(&db, &id)
                        && let Some(runner) = state.runner
                    {
                        terminate_owned(runner);
                    }
                }
            }
        }
        let base = std::env::temp_dir().canonicalize().unwrap();
        let root = self.root.canonicalize().unwrap();
        assert_eq!(root.parent(), Some(base.as_path()));
        assert!(
            root.file_name()
                .unwrap()
                .to_string_lossy()
                .starts_with("inkbolt-jobs-")
        );
        let began = Instant::now();
        loop {
            match fs::remove_dir_all(&root) {
                Ok(()) => break,
                Err(_) if began.elapsed() < Duration::from_secs(10) => {
                    std::thread::sleep(Duration::from_millis(20))
                }
                Err(e) => panic!("{e}"),
            }
        }
    }
}
fn request(root: &Path, id: &str, lifetime: u64) -> Value {
    json!({"command":"job.start","job_root":root.join("jobs"),"request_id":id,"document":{"schema_version":2,"id":"original","kind":"raster","width":2,"height":2,"color_space":"srgb"},"output":{"output_root":root,"file_name":format!("{id}.png"),"format":"png"},"options":{"lifetime_ms":lifetime,"worker_executable":std::env::current_exe().unwrap()}})
}
fn invoke(request: Value) -> Result<Value, Error> {
    crate::request::execute(request, None, &Control::default())
}
#[test]
fn helper() {
    let Ok(mode) = std::env::var("INKBOLT_JOB_HELPER") else {
        return;
    };
    if mode == "submit" {
        let root = PathBuf::from(std::env::var_os("INKBOLT_JOB_TEST_ROOT").unwrap());
        let result =
            invoke(serde_json::from_slice(&fs::read(root.join("request.json")).unwrap()).unwrap());
        fs::write(
            root.join("ticket.json"),
            serde_json::to_vec(
                &result
                    .as_ref()
                    .map_err(|e| json!({"code":e.code,"message":e.message})),
            )
            .unwrap(),
        )
        .unwrap();
        assert!(result.is_ok(), "{result:?}");
        return;
    }
    if job_process::await_start(std::io::stdin().lock()).is_err() {
        return;
    }
    let root = PathBuf::from(std::env::var_os("INKBOLT_JOB_ROOT").unwrap());
    let outcome = if mode == "worker" {
        run_worker(
            &root,
            std::env::var("INKBOLT_JOB_GENERATION")
                .unwrap()
                .parse()
                .unwrap(),
        )
    } else {
        run_attempt(
            &root,
            &std::env::var("INKBOLT_JOB_ID").unwrap(),
            std::env::var("INKBOLT_JOB_ATTEMPT")
                .unwrap()
                .parse()
                .unwrap(),
        )
    };
    if let Err(error) = &outcome {
        fs::write(
            root.join(format!("{mode}-error.json")),
            serde_json::to_vec(&json!({"code":error.code,"message":error.message})).unwrap(),
        )
        .unwrap();
    }
    assert!(outcome.is_ok(), "{outcome:?}");
}

#[test]
fn supervisor_death_at_claim_and_runner_registration_requires_explicit_recovery() {
    for point in [
        "before_claim",
        "after_claim",
        "runner_registered",
        "before_prepare",
    ] {
        let mut owned = Owned::new();
        owned.start(point, 30000);
        owned.kill_supervisor();
        owned.until(|| {
            owned.state().runner.is_none_or(|r| {
                job_process::process_state(r).unwrap() == job_process::ProcessState::NotRunning
            })
        });
        let before = serde_json::to_value(owned.state()).unwrap();
        let found = list(&owned.jobs(), &ListOptions::default(), &Control::default()).unwrap();
        assert_eq!(found["records"][0]["request_id"], "one");
        assert_eq!(found["records"][0]["state"], before["phase"]);
        assert_eq!(found["records"][0]["next_action"], "job.status");
        assert_eq!(serde_json::to_value(owned.state()).unwrap(), before);
        let observed = status(&owned.jobs(), "one", &Control::default()).unwrap();
        assert_eq!(observed["recovery_required"], true, "{point}: {observed}");
        assert!(!owned.root.join("one.png").exists());
        owned.release();
        resume(&owned.jobs(), "one", &Control::default()).unwrap();
        assert_eq!(owned.terminal()["state"], "completed");
        assert!(owned.root.join("one.png").exists());
    }
}
#[test]
fn prepared_bytes_survive_cancel_and_interruption_without_inspection_publishing_them() {
    let mut cancelled = Owned::new();
    cancelled.start("publication_ready", 30000);
    let requested = cancel(&cancelled.jobs(), "one", &Control::default()).unwrap();
    assert_eq!(requested["cancel_requested"], true);
    // The callback ignores cooperative cancellation, exercising the forced grace.
    assert_eq!(cancelled.terminal()["state"], "cancelled");
    assert!(!cancelled.root.join("one.png").exists());
    assert_eq!(
        publications::receipt(&receipt(&cancelled.jobs(), "one"), &Control::default()).unwrap()["state"],
        "prepared"
    );
    assert_eq!(
        resume(&cancelled.jobs(), "one", &Control::default()).unwrap()["state"],
        "cancelled"
    );
    let mut interrupted = Owned::new();
    interrupted.start("publication_ready", 30000);
    interrupted.kill_supervisor();
    interrupted.until(|| {
        job_process::process_state(interrupted.state().runner.unwrap()).unwrap()
            == job_process::ProcessState::NotRunning
    });
    let discovered = list(
        &interrupted.jobs(),
        &ListOptions::default(),
        &Control::default(),
    )
    .unwrap();
    assert_eq!(discovered["records"][0]["state"], "running");
    assert!(!interrupted.root.join("one.png").exists());
    assert_eq!(
        status(&interrupted.jobs(), "one", &Control::default()).unwrap()["state"],
        "interrupted"
    );
    assert!(!interrupted.root.join("one.png").exists());
    interrupted.release();
    resume(&interrupted.jobs(), "one", &Control::default()).unwrap();
    assert_eq!(interrupted.terminal()["state"], "completed");
}
#[test]
fn publication_lock_wins_late_cancel_and_crash_after_link_recovers_success() {
    let mut owned = Owned::new();
    owned.start("publication_locked", 30000);
    assert_eq!(
        cancel(&owned.jobs(), "one", &Control::default())
            .unwrap_err()
            .code,
        "JOB_BUSY"
    );
    owned.release();
    assert_eq!(owned.terminal()["state"], "completed");
    assert_eq!(
        cancel(&owned.jobs(), "one", &Control::default()).unwrap()["state"],
        "completed"
    );
    let mut crashed = Owned::new();
    crashed.start("published", 30000);
    assert!(crashed.root.join("one.png").exists());
    let original = fs::read(crashed.root.join("one.png")).unwrap();
    crashed.kill_supervisor();
    crashed.until(|| {
        job_process::process_state(crashed.state().runner.unwrap()).unwrap()
            == job_process::ProcessState::NotRunning
    });
    assert_eq!(
        cancel(&crashed.jobs(), "one", &Control::default()).unwrap()["state"],
        "completed"
    );
    assert_eq!(fs::read(crashed.root.join("one.png")).unwrap(), original);
    fs::remove_file(crashed.root.join("one.png")).unwrap();
    assert_eq!(
        result(&crashed.jobs(), "one", &Control::default()).unwrap()["sha256"],
        assets::sha256(&original)
    );
    assert_eq!(
        resume(&crashed.jobs(), "one", &Control::default()).unwrap()["state"],
        "completed"
    );
    assert!(!crashed.root.join("one.png").exists());
}
#[test]
fn deadline_stops_a_noncooperating_attempt_without_cancelling_an_observer() {
    // The request lifetime includes cold process startup and publication. Give
    // the fixture time to reach its checkpoint on hosted runners; the blocked
    // attempt must still be stopped by that actual request deadline in both cases.
    let lifetime = 10_000;
    let mut owned = Owned::new();
    owned.start("before_prepare", lifetime);
    let observer = Control::default();
    observer.cancel();
    assert_eq!(
        wait(&owned.jobs(), "one", 1000, &observer)
            .unwrap_err()
            .code,
        "CANCELLED"
    );
    assert!(!owned.state().cancel_requested);
    let terminal = owned.terminal();
    assert_eq!(terminal["state"], "failed", "{terminal:#}");
    assert_eq!(terminal["error"]["code"], "JOB_TIMEOUT");
    assert!(!owned.root.join("one.png").exists());
    let mut published = Owned::new();
    published.start("published", lifetime);
    let terminal = published.terminal();
    assert_eq!(terminal["state"], "completed", "{terminal:#}");
    assert!(published.root.join("one.png").exists());
    assert_eq!(
        terminal["last_process_report"]["stop_requested"],
        "deadline"
    );
}
#[test]
fn queued_cancel_retry_conflict_and_active_capacity_are_durable() {
    let mut owned = Owned::new();
    owned.start("before_claim", 30000);
    for n in 1..MAX_ACTIVE {
        invoke(request(&owned.root, &format!("job{n}"), 30000)).unwrap();
    }
    assert_eq!(
        invoke(request(&owned.root, "excess", 30000))
            .unwrap_err()
            .code,
        "JOB_LIMIT"
    );
    let mut conflict = request(&owned.root, "conflict", 30000);
    conflict["output"]["file_name"] = json!("one.png");
    assert_eq!(invoke(conflict).unwrap_err().code, "JOB_OUTPUT_RESERVED");
    let replay = invoke(request(&owned.root, "one", 30000)).unwrap();
    assert_eq!(replay["replayed"], true);
    let mut changed = request(&owned.root, "one", 30000);
    changed["document"]["width"] = json!(3);
    assert_eq!(invoke(changed).unwrap_err().code, "REQUEST_ID_REUSED");
    for id in store::ids(&store::required(&owned.jobs()).unwrap()).unwrap() {
        assert_eq!(
            cancel(&owned.jobs(), &id, &Control::default()).unwrap()["state"],
            "cancelled"
        );
    }
    owned.release();
    owned.until(|| {
        match store::required(&owned.jobs()).and_then(|db| store::runtime(&db)) {
            Ok(runtime) => runtime.owner.is_none(),
            // Releasing the supervisor permits its final progress transaction.
            // Observation retries only the documented transient store conflict.
            Err(error) if error.code == "JOB_BUSY" => false,
            Err(error) => panic!("{error:?}"),
        }
    });
    assert!(!owned.root.join("one.png").exists());
}
#[test]
fn enqueue_during_idle_exit_cannot_lose_the_new_job() {
    let mut owned = Owned::new();
    owned.start("idle_exit_locked", 30000);
    let second = request(&owned.root, "second", 30000);
    // Hold the actual shutdown lease until admission exercises its bounded wait.
    // A short sleep cannot guarantee when a hosted runner schedules either side.
    assert_eq!(invoke(second.clone()).unwrap_err().code, "JOB_BUSY");
    assert_eq!(
        store::ids(&store::required(&owned.jobs()).unwrap()).unwrap(),
        ["one"]
    );
    assert!(!owned.root.join("second.png").exists());

    let retry = |request: Value| {
        let began = Instant::now();
        loop {
            match invoke(request.clone()) {
                Ok(ticket) => return ticket,
                Err(error) if error.code == "JOB_BUSY" => {
                    assert!(began.elapsed() < Duration::from_secs(30), "{error:?}");
                    std::thread::sleep(Duration::from_millis(10));
                }
                Err(error) => panic!("{error:?}"),
            }
        }
    };
    let ready = std::sync::Arc::new(std::sync::Barrier::new(2));
    let queued = second.clone();
    let submitting = ready.clone();
    let thread = std::thread::spawn(move || {
        submitting.wait();
        retry(queued)
    });
    ready.wait();
    owned.release();
    let admitted = thread.join().unwrap();
    assert_eq!(admitted["request_id"], "second");
    let terminal = owned.terminal_for("second");
    assert_eq!(terminal["state"], "completed", "{terminal:#}");
    assert_eq!(terminal["attempt"], 1);
    let original = fs::read(owned.root.join("second.png")).unwrap();
    let replay = retry(second);
    assert_eq!(replay["replayed"], true);
    assert_eq!(replay["state"], "completed");
    assert_eq!(replay["attempt"], 1);
    assert_eq!(replay["document"], admitted["document"]);
    assert_eq!(replay["submitted_ms"], admitted["submitted_ms"]);
    assert_eq!(replay["output"], terminal["output"]);
    assert_eq!(fs::read(owned.root.join("second.png")).unwrap(), original);
    owned.until(
        || match store::required(&owned.jobs()).and_then(|db| store::ids(&db)) {
            Ok(ids) => {
                assert_eq!(ids, ["one", "second"]);
                true
            }
            Err(error) if error.code == "JOB_BUSY" => false,
            Err(error) => panic!("{error:?}"),
        },
    );
}

#[test]
fn simultaneous_observers_cannot_fail_a_publishing_job() {
    let mut owned = Owned::new();
    owned.start("before_prepare", 30000);
    let ready = std::sync::Arc::new(std::sync::Barrier::new(5));
    let observers: Vec<_> = (0..4)
        .map(|_| {
            let root = owned.jobs();
            let ready = ready.clone();
            std::thread::spawn(move || {
                ready.wait();
                let began = Instant::now();
                loop {
                    assert!(began.elapsed() < Duration::from_secs(30));
                    match status(&root, "one", &Control::default()) {
                        Ok(value)
                            if !["queued", "running"]
                                .contains(&value["state"].as_str().unwrap()) =>
                        {
                            return value;
                        }
                        Ok(_) => {}
                        Err(error) if error.code == "JOB_BUSY" => {}
                        Err(error) => panic!("{error:?}"),
                    }
                    std::thread::sleep(Duration::from_millis(1));
                }
            })
        })
        .collect();
    ready.wait();
    owned.release();
    let outcomes: Vec<_> = observers
        .into_iter()
        .map(|observer| observer.join())
        .collect();
    for outcome in outcomes {
        let terminal = outcome.unwrap();
        assert_eq!(terminal["state"], "completed", "{terminal:#}");
        assert_eq!(terminal["attempt"], 1);
    }
    assert!(owned.root.join("one.png").exists());
}

#[test]
fn publication_lock_retry_completes_after_transient_writer() {
    let mut owned = Owned::new();
    owned.start("publication_ready", 30000);
    let prepared =
        publications::receipt(&receipt(&owned.jobs(), "one"), &Control::default()).unwrap();
    assert_eq!(prepared["state"], "prepared");
    let mut db = store::required(&owned.jobs()).unwrap();
    let tx = db
        .transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)
        .unwrap();
    store::save(&tx, &store::state(&tx, "one").unwrap()).unwrap();
    owned.release();
    // Model a delayed progress/cancel writer, beyond one SQLite busy wait but
    // within the existing job lifetime. The prepared bytes need no new attempt.
    std::thread::sleep(Duration::from_millis(
        crate::limits::sqlite::BUSY_TIMEOUT_MS + 500,
    ));
    owned.commit_contending_writer(tx);
    let terminal = owned.terminal();
    assert_eq!(terminal["state"], "completed", "{terminal:#}");
    assert_eq!(terminal["attempt"], 1);
    let bytes = fs::read(owned.root.join("one.png")).unwrap();
    assert_eq!(
        prepared["prepared_output"]["sha256"],
        assets::sha256(&bytes)
    );
    assert_eq!(prepared["prepared_output"]["bytes"], bytes.len());
}

#[test]
fn publication_lock_retry_preserves_cancellation_and_deadline() {
    for cancelling in [true, false] {
        let mut owned = Owned::new();
        owned.start("publication_ready", if cancelling { 30000 } else { 10000 });
        let mut db = store::required(&owned.jobs()).unwrap();
        let tx = db
            .transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)
            .unwrap();
        let mut state = store::state(&tx, "one").unwrap();
        state.cancel_requested = cancelling;
        store::save(&tx, &state).unwrap();
        owned.release();
        if cancelling {
            std::thread::sleep(Duration::from_millis(
                crate::limits::sqlite::BUSY_TIMEOUT_MS + 500,
            ));
        } else {
            // The runner must stop at its original lifetime even when it cannot
            // obtain a publication permit or write final bookkeeping.
            owned.until(|| {
                job_process::process_state(state.runner.unwrap()).unwrap()
                    == job_process::ProcessState::NotRunning
            });
        }
        owned.commit_contending_writer(tx);
        let terminal = owned.terminal();
        assert_eq!(
            terminal["state"],
            if cancelling { "cancelled" } else { "failed" },
            "{terminal:#}"
        );
        assert_eq!(terminal["attempt"], 1);
        if !cancelling {
            assert_eq!(terminal["error"]["code"], "JOB_TIMEOUT", "{terminal:#}");
            assert_eq!(
                terminal["last_process_report"]["stop_requested"],
                "deadline"
            );
        }
        assert!(!owned.root.join("one.png").exists());
        assert_eq!(
            publications::receipt(&receipt(&owned.jobs(), "one"), &Control::default()).unwrap()["state"],
            "prepared"
        );
    }
}

#[test]
fn submitter_death_after_admission_or_supervisor_registration_keeps_the_ticket() {
    for point in ["admitted", "supervisor_registered"] {
        let mut owned = Owned::new();
        owned.start(point, 30000);
        owned.children[0].kill().unwrap();
        owned.children[0].wait().unwrap();
        owned.until(|| {
            store::runtime(&store::required(&owned.jobs()).unwrap())
                .unwrap()
                .owner
                .is_none_or(|o| {
                    job_process::process_state(o).unwrap() == job_process::ProcessState::NotRunning
                })
        });
        assert_eq!(owned.state().phase, Phase::Queued);
        assert_eq!(
            status(&owned.jobs(), "one", &Control::default()).unwrap()["recovery_required"],
            true
        );
        owned.release();
        resume(&owned.jobs(), "one", &Control::default()).unwrap();
        assert_eq!(owned.terminal()["state"], "completed");
    }
}

#[test]
fn completed_record_capacity_reserves_receipts_and_never_evicts_original_inputs() {
    let mut owned = Owned::new();
    owned.start("before_claim", 30000);
    let mut db = store::required(&owned.jobs()).unwrap();
    let tx = db
        .transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)
        .unwrap();
    let original = store::input_bytes(&tx, "one").unwrap().unwrap();
    let source = store::input(&tx, "one").unwrap();
    for n in 1..MAX_JOBS {
        let mut input = source.clone();
        input.id = format!("saved{n}");
        input.output.file_name = format!("saved{n}.png");
        store::admit(&tx, &input, &encode(&input, MAX_INPUT_BYTES).unwrap()).unwrap();
        let mut state = store::state(&tx, &input.id).unwrap();
        state.phase = Phase::Cancelled;
        state.progress = Progress::phase("cancelled");
        store::save(&tx, &state).unwrap();
    }
    let mut extra = source.clone();
    extra.id = "extra".into();
    extra.output.file_name = "extra.png".into();
    assert_eq!(
        store::admit(&tx, &extra, &encode(&extra, MAX_INPUT_BYTES).unwrap())
            .unwrap_err()
            .code,
        "JOB_LIMIT"
    );
    assert_eq!(store::input_bytes(&tx, "one").unwrap().unwrap(), original);
    tx.commit().unwrap();
    // The admitted job's reserved mutable record can still grow to the receipt bound.
    let tx = db
        .transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)
        .unwrap();
    let mut state = store::state(&tx, "one").unwrap();
    state.complete(json!({"original_fixture":"x".repeat(publications::MAX_RECEIPT_BYTES-2048)}));
    store::save(&tx, &state).unwrap();
    tx.commit().unwrap();
    assert_eq!(store::ids(&db).unwrap().len(), MAX_JOBS);
    assert_eq!(store::state(&db, "one").unwrap().phase, Phase::Completed);
    drop(db);
    owned.release();
}
