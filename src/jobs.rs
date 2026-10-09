//! Durable, bounded local publication jobs. Sources remain immutable.
mod store;
#[cfg(all(test, windows))]
mod tests;
#[cfg(windows)]
mod worker;
use crate::{
    Document, Error, assets, control::Control, job_process, model, publications, publish,
    sessions::Resources,
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    path::{Path, PathBuf},
    sync::OnceLock,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

pub const MAX_JOBS: usize = 128;
pub const MAX_ACTIVE: usize = 32;
pub const MAX_ATTEMPTS: u32 = 8;
pub const MAX_INPUT_BYTES: usize = 16 * 1024 * 1024;
pub const MAX_STATE_BYTES: usize = publications::MAX_RECEIPT_BYTES + 65536;
pub const MAX_STORE_BYTES: usize = 256 * 1024 * 1024;
pub fn capabilities() -> Value {
    json!({"commands":["job.start","job.status","job.result","job.wait","job.cancel","job.resume"],"supported_here":cfg!(windows),"storage_version":1,"queue":"local_SQLite_FULL_rollback;checksummed_immutable_inputs_and_state","active_jobs":MAX_ACTIVE,"maximum_jobs":MAX_JOBS,"workers_per_root":1,"attempts":MAX_ATTEMPTS,"maximum_input_bytes":MAX_INPUT_BYTES,"maximum_state_bytes":MAX_STATE_BYTES,"maximum_reserved_store_bytes":MAX_STORE_BYTES,"maximum_database_bytes":512*1024*1024,"maximum_wait_ms":30000,"cancel_grace_ms":2000,"inputs":"submitted_document_revision;content_addressed_resources_and_font_licenses;exact_worker_executable_per_root","resources_copied":false,"resource_validation":"submission_and_before_new_encoding;prepared_outputs_resume_from_verified_bytes","progress":["queued","starting","validating_resources","rendering_and_encoding","staging","publishing","completed","cancelled","failed","interrupted"],"publication":"create_only_with_durable_receipt;job_transaction_serializes_cancel_with_link_and_result","inspection":"never_starts_worker_or_publishes_absent_output;may_reconcile_saved_outcome","recovery":"explicit_job.resume;no_automatic_retries;completed_and_cancelled_are_terminal","result":"job.status_compact_output_summary;job.result_full_historical_receipt","memory_measure":"OS_peak_committed_bytes_for_observed_runner_exits","platform":"Windows_trusted_local_filesystem","listener":false,"telemetry":false,"power_loss_guarantee":false})
}
static CLI_EXECUTABLE: OnceLock<PathBuf> = OnceLock::new();
#[cfg(all(test, windows))]
pub(crate) fn test_checkpoint(stage: &str) {
    tests::checkpoint(stage);
}

/// Called by the engine's own CLI. Embedders instead supply worker_executable.
pub fn configure_cli_executable(path: PathBuf) {
    let _ = CLI_EXECUTABLE.set(path);
}
fn err(code: &'static str, message: &str) -> Error {
    Error::new(code, message)
}
fn corrupt(message: &str) -> Error {
    err("JOB_CORRUPT", message)
}
fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
        .min(u64::MAX as u128) as u64
}
fn checked_root(root: &Path, control: &Control) -> Result<(), Error> {
    assets::absolute(root)?;
    if root.as_os_str().len() > 4000 {
        return Err(err("INVALID_PATH", "Job root exceeds 4000 characters"));
    }
    control.check_path(root)?;
    if !cfg!(windows) {
        return Err(err(
            "UNSUPPORTED_PLATFORM",
            "Durable job execution currently requires Windows",
        ));
    }
    Ok(())
}
fn checked_id(id: &str) -> Result<(), Error> {
    if !model::valid_id(id) {
        return Err(err(
            "INVALID_REQUEST",
            "Job request ID must use document ID syntax",
        ));
    }
    Ok(())
}
fn encode(value: &impl Serialize, limit: usize) -> Result<Vec<u8>, Error> {
    let data = serde_json::to_vec(value).map_err(|_| corrupt("Unable to encode job data"))?;
    if data.len() > limit {
        return Err(err(
            "JOB_LIMIT",
            "Job input or receipt exceeds its storage budget",
        ));
    }
    Ok(data)
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(default, deny_unknown_fields)]
pub struct Options {
    pub lifetime_ms: u64,
    pub memory_mib: u32,
    /// Optional absolute Inkbolt CLI path; required for library embedders.
    pub worker_executable: Option<PathBuf>,
}
impl Default for Options {
    fn default() -> Self {
        Self {
            lifetime_ms: 300000,
            memory_mib: 512,
            worker_executable: None,
        }
    }
}
impl Options {
    fn validate(&self) -> Result<(), Error> {
        if self.lifetime_ms == 0
            || self.lifetime_ms > job_process::MAX_LIFETIME_MS
            || !(64..=job_process::MAX_MEMORY_MIB).contains(&self.memory_mib)
        {
            return Err(err(
                "INVALID_REQUEST",
                "Job limits require 1..3600000 ms and 64..2048 MiB committed memory",
            ));
        }
        if let Some(path) = &self.worker_executable {
            assets::absolute(path)?;
            if path.as_os_str().len() > 4096 {
                return Err(err("INVALID_PATH", "Worker executable path is too long"));
            }
        }
        Ok(())
    }
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Input {
    version: u32,
    id: String,
    document: Document,
    resources: Resources,
    output: publish::Options,
    options: Options,
    workspace: Option<PathBuf>,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum Phase {
    Queued,
    Running,
    Completed,
    Cancelled,
    Failed,
    Interrupted,
}
impl Phase {
    fn active(self) -> bool {
        matches!(self, Self::Queued | Self::Running | Self::Interrupted)
    }
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Progress {
    phase: String,
    completed: u64,
    total: Option<u64>,
}
impl Progress {
    fn phase(phase: &str) -> Self {
        Self {
            phase: phase.into(),
            completed: 0,
            total: None,
        }
    }
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Failure {
    code: String,
    message: String,
}
impl From<Error> for Failure {
    fn from(error: Error) -> Self {
        Self {
            code: error.code.into(),
            message: error.message.chars().take(1024).collect(),
        }
    }
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct State {
    version: u32,
    id: String,
    phase: Phase,
    attempt: u32,
    cancel_requested: bool,
    submitted_ms: u64,
    updated_ms: u64,
    progress: Progress,
    worker: Option<job_process::ProcessIdentity>,
    runner: Option<job_process::ProcessIdentity>,
    result: Option<Value>,
    error: Option<Failure>,
    reports: Vec<job_process::Report>,
}
impl State {
    fn new(id: &str) -> Self {
        Self {
            version: 1,
            id: id.into(),
            phase: Phase::Queued,
            attempt: 0,
            cancel_requested: false,
            submitted_ms: now(),
            updated_ms: now(),
            progress: Progress::phase("queued"),
            worker: None,
            runner: None,
            result: None,
            error: None,
            reports: vec![],
        }
    }
    fn validate(&self, id: &str) -> Result<(), Error> {
        if self.version != 1
            || self.id != id
            || !model::valid_id(id)
            || self.attempt > MAX_ATTEMPTS
            || self.reports.len() > MAX_ATTEMPTS as usize
            || (self.phase == Phase::Completed) != self.result.is_some()
            || self.progress.phase.len() > 64
            || self
                .progress
                .total
                .is_some_and(|n| self.progress.completed > n)
        {
            return Err(corrupt(
                "Job state identity, limits or outcome is inconsistent",
            ));
        }
        Ok(())
    }
    fn complete(&mut self, result: Value) {
        self.phase = Phase::Completed;
        self.progress = Progress::phase("completed");
        self.result = Some(result);
        self.error = None;
        self.updated_ms = now();
    }
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Runtime {
    version: u32,
    generation: u64,
    executable: job_process::Executable,
    owner: Option<job_process::ProcessIdentity>,
}

fn receipt(root: &Path, id: &str) -> publications::ReceiptTarget {
    publications::ReceiptTarget {
        receipt_root: root.join("publications"),
        request_id: id.into(),
    }
}
fn bound_control(input: &Input) -> Result<Control, Error> {
    let workspace = input
        .workspace
        .as_deref()
        .map(crate::workspace::Workspace::open)
        .transpose()?;
    let control = Control::default().in_workspace(workspace.as_ref());
    Ok(control)
}
fn verify_resources(
    document: &Document,
    resources: &Resources,
    control: &Control,
    visited: &mut usize,
) -> Result<(), Error> {
    *visited += 1;
    if *visited > 512 {
        return Err(err(
            "JOB_LIMIT",
            "Job nested resource verification exceeds 512 documents",
        ));
    }
    control.check_resource_paths(resources)?;
    for asset in document.assets.values() {
        control.check()?;
        assets::load(asset, resources.asset_root.as_deref())?;
    }
    for font in document.fonts.values() {
        control.check()?;
        crate::fonts::load(font, resources.font_root.as_deref())?;
    }
    fn content(
        value: &model::Content,
        resources: &Resources,
        control: &Control,
        visited: &mut usize,
    ) -> Result<(), Error> {
        control.check()?;
        match value {
            model::Content::Object { object } => {
                verify_resources(&object.document()?, resources, control, visited)?
            }
            model::Content::Instance { instance } => {
                for over in instance.overrides.values() {
                    if let Some(nested) = &over.content {
                        content(nested, resources, control, visited)?;
                    }
                }
            }
            _ => {}
        }
        Ok(())
    }
    for item in &document.items {
        content(&item.content, resources, control, visited)?;
    }
    Ok(())
}
fn view(root: &Path, input: &Input, state: &State, replayed: bool) -> Value {
    let output = state.result.as_ref().map(|r| json!({"path":r["path"],"bytes":r["bytes"],"sha256":r["sha256"],"created":r["created"],"publication":r["publication"]}));
    json!({"job_root":root,"request_id":state.id,"state":state.phase,"attempt":state.attempt,"replayed":replayed,"cancel_requested":state.cancel_requested,"progress":state.progress,"submitted_ms":state.submitted_ms,"updated_ms":state.updated_ms,"document":{"id":input.document.id,"revision":input.document.revision,"sha256":assets::sha256(&serde_json::to_vec(&input.document).unwrap())},"output":output,"error":state.error,"worker":state.worker,"runner":state.runner,"last_process_report":state.reports.last(),"recovery_required":state.phase==Phase::Interrupted,"next_action":if state.phase==Phase::Completed {Some("job.result")} else if state.phase==Phase::Interrupted {Some("job.resume")} else {None}})
}

pub fn start(
    root: &Path,
    id: &str,
    document: &Document,
    resources: &Resources,
    output: &publish::Options,
    options: &Options,
    control: &Control,
) -> Result<Value, Error> {
    checked_root(root, control)?;
    checked_id(id)?;
    options.validate()?;
    crate::finite::check(&(document, output))?;
    resources.validate()?;
    publish::destination(output)?;
    let mut options = options.clone();
    if options.worker_executable.is_none() {
        options.worker_executable = CLI_EXECUTABLE.get().cloned();
    }
    let executable_path = options.worker_executable.clone().ok_or_else(|| {
        err(
            "JOB_EXECUTABLE_REQUIRED",
            "Library job submission requires an explicit Inkbolt worker executable",
        )
    })?;
    let input = Input {
        version: 1,
        id: id.into(),
        document: document.clone(),
        resources: resources.clone(),
        output: output.clone(),
        options,
        workspace: control.workspace_root(),
    };
    let data = encode(&input, MAX_INPUT_BYTES)?;
    if let Some(db) = store::open(root, None)?
        && let Some(old) = store::input_bytes(&db, id)?
    {
        if old != data {
            return Err(err(
                "REQUEST_ID_REUSED",
                "Job request ID was used with different inputs",
            ));
        }
        return Ok(view(root, &input, &store::state(&db, id)?, true));
    }
    control.check()?;
    model::validate_controlled(document, control)?;
    control.check_path(&output.output_root)?;
    verify_resources(document, resources, control, &mut 0)?;
    let executable = job_process::Executable::inspect(&executable_path, control)?;
    std::fs::create_dir_all(root).map_err(|_| err("IO_ERROR", "Unable to create job root"))?;
    #[cfg(windows)]
    {
        let _launch = worker::launch_lease(root, control)?;
        let mut db = store::open(root, Some(&executable))?.unwrap();
        let tx = db
            .transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)
            .map_err(store::sql)?;
        if let Some(old) = store::input_bytes(&tx, id)? {
            if old != data {
                return Err(err(
                    "REQUEST_ID_REUSED",
                    "Job request ID was used with different inputs",
                ));
            }
            return Ok(view(root, &input, &store::state(&tx, id)?, true));
        }
        if store::runtime(&tx)?.executable != executable {
            return Err(err(
                "JOB_EXECUTABLE_CHANGED",
                "This queue is bound to a different worker build; preserve it and choose another root",
            ));
        }
        store::admit(&tx, &input, &data)?;
        control.check()?;
        tx.commit().map_err(store::sql)?;
        #[cfg(test)]
        tests::checkpoint("admitted");
        // Once enqueued, late submission cancellation or launch failure cannot
        // erase the durable ticket. Resume uses this same identity.
        let launch_error = worker::kick_locked(root).err().map(Failure::from);
        let mut result = status_inner(root, id, false, control)?;
        result["launch_error"] = json!(launch_error);
        Ok(result)
    }
    #[cfg(not(windows))]
    Err(err("UNSUPPORTED_PLATFORM", "Durable jobs require Windows"))
}
fn status_inner(root: &Path, id: &str, reconcile: bool, control: &Control) -> Result<Value, Error> {
    checked_root(root, control)?;
    checked_id(id)?;
    #[cfg(windows)]
    if reconcile {
        worker::reconcile(root, id, None)?;
    }
    let mut db = store::required(root)?;
    let tx = db.transaction().map_err(store::sql)?;
    let input = store::input(&tx, id)?;
    let state = store::state(&tx, id)?;
    let runtime = if state.phase == Phase::Queued {
        Some(store::runtime(&tx)?)
    } else {
        None
    };
    drop(tx);
    let mut result = view(root, &input, &state, false);
    #[cfg(windows)]
    if let Some(runtime) = runtime {
        let owner = runtime.owner;
        let observed = owner
            .map(job_process::process_state)
            .transpose()?
            .unwrap_or(job_process::ProcessState::NotRunning);
        result["supervisor_state"] = json!(observed);
        if observed != job_process::ProcessState::Running {
            result["recovery_required"] = json!(true);
            result["next_action"] = json!("job.resume");
        }
    }
    Ok(result)
}
pub fn status(root: &Path, id: &str, control: &Control) -> Result<Value, Error> {
    control.check()?;
    status_inner(root, id, true, control)
}
pub fn result(root: &Path, id: &str, control: &Control) -> Result<Value, Error> {
    checked_root(root, control)?;
    checked_id(id)?;
    control.check()?;
    #[cfg(windows)]
    worker::reconcile(root, id, None)?;
    let state = store::state(&store::required(root)?, id)?;
    state.result.ok_or_else(|| {
        err(
            "JOB_NOT_COMPLETED",
            "Job has no completed publication; inspect job.status",
        )
    })
}
pub fn wait(root: &Path, id: &str, wait_ms: u64, control: &Control) -> Result<Value, Error> {
    if wait_ms > 30000 {
        return Err(err("INVALID_REQUEST", "Job wait is bounded to 30000 ms"));
    }
    let until = Instant::now() + Duration::from_millis(wait_ms);
    loop {
        let result = status(root, id, control)?;
        if result["recovery_required"] == true
            || !["queued", "running"].contains(&result["state"].as_str().unwrap_or_default())
            || Instant::now() >= until
        {
            return Ok(result);
        }
        std::thread::sleep(
            until
                .saturating_duration_since(Instant::now())
                .min(Duration::from_millis(50)),
        );
    }
}
pub fn cancel(root: &Path, id: &str, control: &Control) -> Result<Value, Error> {
    checked_root(root, control)?;
    checked_id(id)?;
    #[cfg(windows)]
    worker::reconcile(root, id, None)?;
    let mut db = store::required(root)?;
    let tx = db
        .transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)
        .map_err(store::sql)?;
    let mut state = store::state(&tx, id)?;
    if state.phase.active() {
        control.check()?;
        state.cancel_requested = true;
        if state.phase != Phase::Running {
            state.phase = Phase::Cancelled;
            state.progress = Progress::phase("cancelled");
        }
        state.updated_ms = now();
        store::save(&tx, &state)?;
        tx.commit().map_err(store::sql)?;
    }
    status_inner(root, id, false, control)
}
pub fn resume(root: &Path, id: &str, control: &Control) -> Result<Value, Error> {
    checked_root(root, control)?;
    checked_id(id)?;
    {
        let db = store::required(root)?;
        let state = store::state(&db, id)?;
        if matches!(state.phase, Phase::Completed | Phase::Cancelled) {
            return Ok(view(root, &store::input(&db, id)?, &state, true));
        }
    }
    #[cfg(windows)]
    {
        worker::reconcile(root, id, None)?;
        let _launch = worker::launch_lease(root, control)?;
        let mut db = store::required(root)?;
        let tx = db
            .transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)
            .map_err(store::sql)?;
        let mut state = store::state(&tx, id)?;
        let input = store::input(&tx, id)?;
        if matches!(
            state.phase,
            Phase::Completed | Phase::Cancelled | Phase::Running
        ) {
            return Ok(view(root, &input, &state, true));
        }
        control.check()?;
        if state.attempt >= MAX_ATTEMPTS {
            return Err(err(
                "JOB_LIMIT",
                "Job has exhausted its eight explicit attempts",
            ));
        }
        store::check_active(&tx, &input, Some(id))?;
        state.phase = Phase::Queued;
        state.error = None;
        state.progress = Progress::phase("queued");
        state.updated_ms = now();
        store::save(&tx, &state)?;
        tx.commit().map_err(store::sql)?;
        let launch_error = worker::kick_locked(root).err().map(Failure::from);
        let mut result = status_inner(root, id, false, control)?;
        result["launch_error"] = json!(launch_error);
        Ok(result)
    }
    #[cfg(not(windows))]
    Err(err("UNSUPPORTED_PLATFORM", "Durable jobs require Windows"))
}

/// Private CLI entry, always invoked behind the cooperating startup gate.
pub fn run_worker(root: &Path, generation: u64) -> Result<(), Error> {
    #[cfg(windows)]
    {
        worker::run(root, generation)
    }
    #[cfg(not(windows))]
    {
        let _ = (root, generation);
        Err(err("UNSUPPORTED_PLATFORM", "Durable jobs require Windows"))
    }
}
pub fn run_attempt(root: &Path, id: &str, attempt: u32) -> Result<(), Error> {
    #[cfg(windows)]
    {
        worker::attempt(root, id, attempt)
    }
    #[cfg(not(windows))]
    {
        let _ = (root, id, attempt);
        Err(err("UNSUPPORTED_PLATFORM", "Durable jobs require Windows"))
    }
}
