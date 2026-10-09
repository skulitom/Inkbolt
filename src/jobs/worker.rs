use super::*;
use crate::control::{JobHooks, PublicationPermit};
use rusqlite::TransactionBehavior;
use std::{
    os::windows::process::CommandExt,
    process::{Child, Command, Stdio},
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
    },
};

pub(super) fn launch_lease(
    root: &Path,
    control: &Control,
) -> Result<job_process::FileLease, Error> {
    let until = Instant::now() + Duration::from_secs(2);
    loop {
        control.check()?;
        if let Some(lease) = job_process::FileLease::try_acquire(&root.join("launch.lock"))? {
            return Ok(lease);
        }
        if Instant::now() >= until {
            return Err(err(
                "JOB_BUSY",
                "Another launcher owns this queue; retry the same request",
            ));
        }
        std::thread::sleep(Duration::from_millis(10));
    }
}
struct Starting(Option<Child>);
impl Drop for Starting {
    fn drop(&mut self) {
        if let Some(child) = &mut self.0 {
            child.stdin.take();
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}
pub(super) fn kick_locked(root: &Path) -> Result<(), Error> {
    let Some(probe) = job_process::FileLease::try_acquire(&root.join("worker.lock"))? else {
        return Ok(());
    };
    let mut db = store::required(root)?;
    let mut runtime = store::runtime(&db)?;
    if let Some(owner) = runtime.owner {
        match job_process::process_state(owner)? {
            job_process::ProcessState::Running => return Ok(()),
            job_process::ProcessState::Unknown => {
                return Err(err(
                    "JOB_OWNER_UNKNOWN",
                    "Cannot verify previous worker ownership; preserve the queue",
                ));
            }
            job_process::ProcessState::NotRunning => {}
        }
    }
    let _held = runtime.executable.verify(&Control::default())?;
    runtime.generation = runtime
        .generation
        .checked_add(1)
        .ok_or_else(|| err("JOB_LIMIT", "Worker generation is exhausted"))?;
    let mut command = Command::new(&runtime.executable.path);
    #[cfg(not(test))]
    command
        .arg("--job-worker")
        .arg(root)
        .arg(runtime.generation.to_string());
    #[cfg(test)]
    command
        .args(["--exact", "jobs::tests::helper", "--nocapture"])
        .env("INKBOLT_JOB_HELPER", "worker")
        .env("INKBOLT_JOB_GENERATION", runtime.generation.to_string())
        .env("INKBOLT_JOB_ROOT", root);
    command
        .creation_flags(0x0800_0000)
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    let mut starting = Starting(Some(command.spawn().map_err(|_| {
        err(
            "JOB_LAUNCH_FAILED",
            "Unable to launch the saved worker build; the queued job remains durable",
        )
    })?));
    runtime.owner = Some(job_process::child_identity(starting.0.as_ref().unwrap())?);
    let tx = db
        .transaction_with_behavior(TransactionBehavior::Immediate)
        .map_err(store::sql)?;
    store::save_runtime(&tx, &runtime)?;
    tx.commit().map_err(store::sql)?;
    #[cfg(test)]
    super::tests::checkpoint("supervisor_registered");
    drop(probe); // Registration now protects startup; the child must take this lease.
    job_process::release_start(starting.0.as_mut().unwrap().stdin.take().unwrap())?;
    // Standard Child::drop closes handles without terminating the now-registered
    // supervisor. It owns null stdout/stderr and no caller protocol pipe.
    drop(starting.0.take());
    Ok(())
}

fn owner_gone(owner: Option<job_process::ProcessIdentity>) -> Result<bool, Error> {
    match owner {
        Some(owner) => match job_process::process_state(owner)? {
            job_process::ProcessState::Running => Ok(false),
            job_process::ProcessState::NotRunning => Ok(true),
            job_process::ProcessState::Unknown => Err(err(
                "JOB_OWNER_UNKNOWN",
                "Worker identity cannot be inspected; it is not assumed dead",
            )),
        },
        None => Err(corrupt("Running job has no owner identity")),
    }
}
/// Called only after a recorded runner (or its pre-launch owner) is proved dead.
/// Lock order is publication ledger, then job store; never hold a job writer
/// transaction while opening publication recovery.
pub(super) fn reconcile(
    root: &Path,
    id: &str,
    report: Option<job_process::Report>,
) -> Result<(), Error> {
    reconcile_inner(root, id, report, false)
}
fn reconcile_inner(
    root: &Path,
    id: &str,
    report: Option<job_process::Report>,
    owned_exit: bool,
) -> Result<(), Error> {
    let db = store::required(root)?;
    let old = store::state(&db, id)?;
    if old.phase != Phase::Running {
        if let Some(report) = report {
            let mut db = store::required(root)?;
            let tx = db
                .transaction_with_behavior(TransactionBehavior::Immediate)
                .map_err(store::sql)?;
            let mut state = store::state(&tx, id)?;
            if state.reports.len() < state.attempt as usize {
                state.reports.push(report);
                store::save(&tx, &state)?;
                tx.commit().map_err(store::sql)?;
            }
        }
        return Ok(());
    }
    if !owner_gone(old.runner.or(old.worker))? {
        return Ok(());
    }
    // A live supervisor owns the exit report and its deadline/cancel outcome.
    // Observers must not replace that report with a generic interruption.
    if report.is_none() && !owned_exit && !owner_gone(old.worker)? {
        return Ok(());
    }
    let input = store::input(&db, id)?;
    drop(db);
    let completed =
        publications::recover_published_only(&receipt(root, id), &bound_control(&input)?)?;
    let mut db = store::required(root)?;
    let tx = db
        .transaction_with_behavior(TransactionBehavior::Immediate)
        .map_err(store::sql)?;
    let mut state = store::state(&tx, id)?;
    if state.phase != Phase::Running || state.attempt != old.attempt {
        return Ok(());
    }
    let timed_out = report
        .as_ref()
        .is_some_and(|r| r.stop_requested == Some(job_process::StopReason::Deadline));
    if let Some(report) = report
        && state.reports.len() < state.attempt as usize
    {
        state.reports.push(report);
    }
    if let Some(result) = completed {
        state.complete(result);
    } else if state.cancel_requested {
        state.phase = Phase::Cancelled;
        state.progress = Progress::phase("cancelled");
        state.error = None;
    } else if timed_out {
        state.phase = Phase::Failed;
        state.progress = Progress::phase("failed");
        state.error = Some(
            err(
                "JOB_TIMEOUT",
                "Worker lifetime limit was reached before publication",
            )
            .into(),
        );
    } else {
        state.phase = Phase::Interrupted;
        state.progress = Progress::phase("interrupted");
        state.error = Some(err("JOB_INTERRUPTED","Worker stopped without a completed publication; resume explicitly to retry the same pinned inputs").into());
    }
    state.updated_ms = now();
    store::save(&tx, &state)?;
    tx.commit().map_err(store::sql)
}

pub(super) fn run(root: &Path, generation: u64) -> Result<(), Error> {
    checked_root(root, &Control::default())?;
    let mut worker_lease = Some(
        job_process::FileLease::try_acquire(&root.join("worker.lock"))?
            .ok_or_else(|| err("JOB_BUSY", "Another supervisor owns this queue"))?,
    );
    let runtime = store::runtime(&store::required(root)?)?;
    let owner = runtime
        .owner
        .ok_or_else(|| corrupt("Missing supervisor identity"))?;
    if runtime.generation != generation
        || owner.pid != std::process::id()
        || job_process::process_state(owner)? != job_process::ProcessState::Running
    {
        return Err(err(
            "JOB_OWNER_CHANGED",
            "Supervisor generation or process identity changed",
        ));
    }
    for id in store::ids(&store::required(root)?)? {
        reconcile(root, &id, None)?;
        if store::state(&store::required(root)?, &id)?.phase == Phase::Running {
            return Err(err(
                "JOB_OWNER_ALIVE",
                "A previous runner is still alive; no replacement is started",
            ));
        }
    }
    loop {
        #[cfg(test)]
        super::tests::checkpoint("before_claim");
        let mut db = store::required(root)?;
        let tx = db
            .transaction_with_behavior(TransactionBehavior::Immediate)
            .map_err(store::sql)?;
        let mut selected = None;
        for id in store::ids(&tx)? {
            let mut state = store::state(&tx, &id)?;
            if state.phase == Phase::Queued {
                if state.attempt >= MAX_ATTEMPTS {
                    return Err(err("JOB_LIMIT", "Queued job exhausted its attempt bound"));
                }
                state.attempt += 1;
                state.phase = Phase::Running;
                state.worker = Some(owner);
                state.runner = None;
                state.error = None;
                state.progress = Progress::phase("starting");
                state.updated_ms = now();
                let input = store::input(&tx, &id)?;
                store::save(&tx, &state)?;
                selected = Some((input, state));
                break;
            }
        }
        tx.commit().map_err(store::sql)?;
        if let Some((input, state)) = selected {
            #[cfg(test)]
            super::tests::checkpoint("after_claim");
            if let Err(error) = execute(root, &runtime, &input, &state) {
                reconcile_inner(root, &state.id, None, true)?;
                let mut db = store::required(root)?;
                let tx = db
                    .transaction_with_behavior(TransactionBehavior::Immediate)
                    .map_err(store::sql)?;
                let mut current = store::state(&tx, &state.id)?;
                if current.phase == Phase::Running && current.attempt == state.attempt {
                    current.phase = if current.cancel_requested {
                        Phase::Cancelled
                    } else {
                        Phase::Failed
                    };
                    current.error = Some(error.into());
                    current.updated_ms = now();
                    current.progress = Progress::phase(if current.phase == Phase::Cancelled {
                        "cancelled"
                    } else {
                        "failed"
                    });
                    store::save(&tx, &current)?;
                    tx.commit().map_err(store::sql)?;
                }
            }
            continue;
        }
        // Admission holds launch.lock before inserting. Recheck under the same
        // lock and release the worker lease before the launcher may enqueue.
        let _launch = launch_lease(root, &Control::default())?;
        #[cfg(test)]
        super::tests::checkpoint("idle_exit_locked");
        let mut db = store::required(root)?;
        let tx = db
            .transaction_with_behavior(TransactionBehavior::Immediate)
            .map_err(store::sql)?;
        if store::ids(&tx)?.into_iter().any(|id| {
            store::state(&tx, &id)
                .map(|s| s.phase == Phase::Queued)
                .unwrap_or(true)
        }) {
            continue;
        }
        let mut current = store::runtime(&tx)?;
        if current.generation != generation {
            return Err(err(
                "JOB_OWNER_CHANGED",
                "Queue supervisor changed during shutdown",
            ));
        }
        current.owner = None;
        store::save_runtime(&tx, &current)?;
        tx.commit().map_err(store::sql)?;
        drop(worker_lease.take());
        return Ok(());
    }
}
fn execute(root: &Path, runtime: &Runtime, input: &Input, state: &State) -> Result<(), Error> {
    let mut command = Command::new(&runtime.executable.path);
    #[cfg(not(test))]
    command
        .arg("--job-run")
        .arg(root)
        .arg(&input.id)
        .arg(state.attempt.to_string());
    #[cfg(test)]
    command
        .args(["--exact", "jobs::tests::helper", "--nocapture"])
        .env("INKBOLT_JOB_HELPER", "attempt")
        .env("INKBOLT_JOB_ROOT", root)
        .env("INKBOLT_JOB_ID", &input.id)
        .env("INKBOLT_JOB_ATTEMPT", state.attempt.to_string());
    let pending = job_process::spawn(
        command,
        &runtime.executable,
        job_process::Limits {
            lifetime_ms: input.options.lifetime_ms,
            memory_mib: input.options.memory_mib,
        },
        &Control::default(),
    )?;
    let mut db = store::required(root)?;
    let tx = db
        .transaction_with_behavior(TransactionBehavior::Immediate)
        .map_err(store::sql)?;
    let mut current = store::state(&tx, &input.id)?;
    if current.phase != Phase::Running || current.attempt != state.attempt {
        return Err(err(
            "JOB_OWNER_CHANGED",
            "Job ownership changed before runner start",
        ));
    }
    current.runner = Some(pending.identity());
    store::save(&tx, &current)?;
    tx.commit().map_err(store::sql)?;
    #[cfg(test)]
    super::tests::checkpoint("runner_registered");
    let mut runner = pending.start()?;
    let mut cancelling = None;
    loop {
        if let Some(report) = runner.wait_slice(Duration::from_millis(100))? {
            return reconcile(root, &input.id, Some(report));
        }
        match store::required(root).and_then(|db| store::state(&db, &input.id)) {
            Ok(current) if current.phase == Phase::Running && current.cancel_requested => {
                let since = cancelling.get_or_insert_with(Instant::now);
                if since.elapsed() >= Duration::from_secs(2) {
                    runner.stop()?;
                }
            }
            Ok(_) => {}
            Err(error) if error.code == "JOB_BUSY" => {}
            Err(error) => return Err(error), // Runner::drop stops only this owned child.
        }
    }
}

struct Hook {
    root: PathBuf,
    id: String,
    attempt: u32,
    progress: Arc<Mutex<Progress>>,
}
struct Permit {
    db: rusqlite::Connection,
    state: State,
    committed: bool,
}
impl Drop for Permit {
    fn drop(&mut self) {
        if !self.committed {
            let _ = self.db.execute_batch("ROLLBACK");
        }
    }
}
impl PublicationPermit for Permit {
    fn committed(&mut self, result: &Value) -> Result<(), Error> {
        self.state.complete(result.clone());
        store::save(&self.db, &self.state)?;
        self.db.execute_batch("COMMIT").map_err(store::sql)?;
        self.committed = true;
        Ok(())
    }
}
impl JobHooks for Hook {
    fn progress(&self, phase: &'static str, completed: u64, total: Option<u64>) {
        *self.progress.lock().unwrap_or_else(|e| e.into_inner()) = Progress {
            phase: phase.into(),
            completed,
            total,
        };
    }
    fn before_publication(
        &self,
        already_published: bool,
    ) -> Result<Box<dyn PublicationPermit>, Error> {
        let db = store::required(&self.root)?;
        db.execute_batch("BEGIN IMMEDIATE").map_err(store::sql)?;
        let mut state = store::state(&db, &self.id)?;
        if state.phase != Phase::Running || state.attempt != self.attempt {
            return Err(err(
                "JOB_OWNER_CHANGED",
                "Job ownership changed before publication",
            ));
        }
        if state.cancel_requested && !already_published {
            return Err(err(
                "CANCELLED",
                "Job cancellation committed before publication",
            ));
        }
        state.progress = Progress::phase("publishing");
        state.updated_ms = now();
        store::save(&db, &state)?;
        Ok(Box::new(Permit {
            db,
            state,
            committed: false,
        }))
    }
}
pub(super) fn attempt(root: &Path, id: &str, attempt: u32) -> Result<(), Error> {
    checked_root(root, &Control::default())?;
    checked_id(id)?;
    let db = store::required(root)?;
    let input = store::input(&db, id)?;
    let state = store::state(&db, id)?;
    if state.phase != Phase::Running
        || state.attempt != attempt
        || state.runner.is_none_or(|r| r.pid != std::process::id())
    {
        return Err(err(
            "JOB_OWNER_CHANGED",
            "Runner is not the registered attempt",
        ));
    }
    let workspace = input
        .workspace
        .as_deref()
        .map(crate::workspace::Workspace::open)
        .transpose()?;
    let progress = Arc::new(Mutex::new(Progress::phase("validating_resources")));
    let control = Control::for_job(
        input.options.lifetime_ms,
        workspace.as_ref(),
        Arc::new(Hook {
            root: root.into(),
            id: id.into(),
            attempt,
            progress: progress.clone(),
        }),
    );
    control.check_path(root)?;
    control.check_path(&input.output.output_root)?;
    let done = Arc::new(AtomicBool::new(false));
    let monitored = control.clone();
    let watched_done = done.clone();
    let watched_root = root.to_owned();
    let watched_id = id.to_owned();
    let monitor = std::thread::Builder::new()
        .name("inkbolt-job-progress".into())
        .spawn(move || {
            while !watched_done.load(Ordering::Acquire) {
                let update = (|| -> Result<(), Error> {
                    let mut db = store::required(&watched_root)?;
                    let state = store::state(&db, &watched_id)?;
                    if state.cancel_requested
                        || state.phase != Phase::Running
                        || state.attempt != attempt
                    {
                        monitored.cancel();
                        return Ok(());
                    }
                    let observed = progress.lock().unwrap_or_else(|e| e.into_inner()).clone();
                    if observed != state.progress {
                        let tx = db
                            .transaction_with_behavior(TransactionBehavior::Immediate)
                            .map_err(store::sql)?;
                        let mut current = store::state(&tx, &watched_id)?;
                        if current.phase == Phase::Running && current.attempt == attempt {
                            current.progress = observed;
                            current.updated_ms = now();
                            store::save(&tx, &current)?;
                            tx.commit().map_err(store::sql)?;
                        }
                    }
                    Ok(())
                })();
                if update.is_err_and(|e| e.code != "JOB_BUSY") {
                    monitored.cancel();
                }
                std::thread::sleep(Duration::from_millis(100));
            }
        })
        .map_err(|_| {
            err(
                "JOB_PROCESS_ERROR",
                "Unable to start job cancellation monitor",
            )
        })?;
    let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        #[cfg(test)]
        super::tests::checkpoint("before_prepare");
        model::validate_controlled(&input.document, &control)?;
        // A prepared publication already owns exact encoded bytes and does not
        // need reopened resources. New encoding rechecks every pinned resource.
        match publications::receipt(&receipt(root, id), &Control::default()) {
            Ok(_) => publications::recover(&receipt(root, id), &control),
            Err(error) if error.code == "PUBLICATION_NOT_FOUND" => {
                verify_resources(&input.document, &input.resources, &control, &mut 0)?;
                publications::document(
                    &input.document,
                    &input.resources,
                    &input.output,
                    &receipt(root, id),
                    &control,
                )
            }
            Err(error) => Err(error),
        }
    }))
    .unwrap_or_else(|_| {
        Err(err(
            "JOB_ENGINE_ERROR",
            "Job engine failed unexpectedly; publication evidence is retained",
        ))
    });
    done.store(true, Ordering::Release);
    let _ = monitor.join();
    // Publication writes and guard commit precede this final bookkeeping. Never
    // substitute a late cancellation for its completed result.
    let mut db = store::required(root)?;
    let tx = db
        .transaction_with_behavior(TransactionBehavior::Immediate)
        .map_err(store::sql)?;
    let mut state = store::state(&tx, id)?;
    if state.phase == Phase::Completed {
        return Ok(());
    }
    if state.phase != Phase::Running || state.attempt != attempt {
        return Err(err(
            "JOB_OWNER_CHANGED",
            "Job attempt changed during completion",
        ));
    }
    match outcome {
        Ok(result) => state.complete(result),
        Err(error) => {
            state.phase = if error.code == "CANCELLED" && state.cancel_requested {
                Phase::Cancelled
            } else {
                Phase::Failed
            };
            state.error = Some(error.into());
            state.progress = Progress::phase(if state.phase == Phase::Cancelled {
                "cancelled"
            } else {
                "failed"
            });
        }
    }
    state.updated_ms = now();
    store::save(&tx, &state)?;
    tx.commit().map_err(store::sql)
}
