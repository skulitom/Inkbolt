//! Discover retained jobs without resuming work or reconciling their outcomes.
use super::*;
use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};

pub const MAX_PAGE_RECORDS: usize = 32;
pub const MAX_PAGE_BYTES: usize = 32 * 1024;
const MAX_CURSOR_BYTES: usize = 1024;

#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(default, deny_unknown_fields)]
pub struct ListOptions {
    /// Maximum returned records, 1..=32. The 32 KiB byte limit can shorten a page.
    pub limit: usize,
    /// Opaque continuation from job.list; reuse with the same root and limit.
    pub cursor: Option<String>,
}
impl Default for ListOptions {
    fn default() -> Self {
        Self {
            limit: 8,
            cursor: None,
        }
    }
}
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Cursor {
    version: u32,
    scope: String,
    members: String,
    through: usize,
    after: usize,
    limit: usize,
}
fn invalid_cursor() -> Error {
    err(
        "INVALID_CURSOR",
        "Invalid job cursor; restart job.list without a cursor",
    )
}
fn changed_cursor() -> Error {
    err(
        "JOB_CURSOR_CHANGED",
        "Job root, build or retained inputs changed; restart job.list without a cursor",
    )
}
fn parse_cursor(value: &str) -> Result<Cursor, Error> {
    if value.len() > MAX_CURSOR_BYTES {
        return Err(invalid_cursor());
    }
    let bytes = URL_SAFE_NO_PAD
        .decode(value)
        .map_err(|_| invalid_cursor())?;
    let cursor: Cursor = serde_json::from_slice(&bytes).map_err(|_| invalid_cursor())?;
    if cursor.version != 1
        || cursor.after == 0
        || cursor.after >= cursor.through
        || cursor.through > MAX_JOBS
        || !(1..=MAX_PAGE_RECORDS).contains(&cursor.limit)
        || !crate::fonts::valid_hash(&cursor.scope)
        || !crate::fonts::valid_hash(&cursor.members)
    {
        return Err(invalid_cursor());
    }
    Ok(cursor)
}
fn token(scope: &str, members: &str, through: usize, after: usize, limit: usize) -> String {
    URL_SAFE_NO_PAD.encode(
        serde_json::to_vec(&Cursor {
            version: 1,
            scope: scope.into(),
            members: members.into(),
            through,
            after,
            limit,
        })
        .unwrap(),
    )
}
fn page(root: &Path, options: &ListOptions, exists: bool) -> Value {
    json!({"job_root":root,"exists":exists,"order":"admission","offset":0,"snapshot_total":0,"current_total":0,"limit":options.limit,"returned":0,"records":[],"next_cursor":null,"supervisor":null,"semantics":"Membership is fixed by the first page; later submissions require a fresh listing. States are saved values at each page read. Use job.status to reconcile stopped work; listing never starts workers or publishes outputs."})
}

pub fn list(root: &Path, options: &ListOptions, control: &Control) -> Result<Value, Error> {
    checked_root(root, control)?;
    control.check()?;
    if !(1..=MAX_PAGE_RECORDS).contains(&options.limit) {
        return Err(err("INVALID_REQUEST", "Job list limit must be in 1..=32"));
    }
    let cursor = options.cursor.as_deref().map(parse_cursor).transpose()?;
    if cursor.as_ref().is_some_and(|c| c.limit != options.limit) {
        return Err(invalid_cursor());
    }
    let Some(mut db) = store::open(root, None)? else {
        control.check()?;
        return if cursor.is_some() {
            Err(changed_cursor())
        } else {
            Ok(page(root, options, false))
        };
    };
    let tx = db.transaction().map_err(store::sql)?;
    let runtime = store::runtime(&tx)?;
    let canonical_root = std::fs::canonicalize(root)
        .map_err(|_| err("IO_ERROR", "Unable to identify job listing root"))?;
    let scope = assets::sha256(&encode(&(canonical_root, &runtime.executable), 32768)?);
    let inventory = store::inventory(&tx)?;
    let through = cursor.as_ref().map_or(inventory.len(), |c| c.through);
    let after = cursor.as_ref().map_or(0, |c| c.after);
    if through > inventory.len() {
        return Err(changed_cursor());
    }
    let members = assets::sha256(&encode(&&inventory[..through], 32768)?);
    if let Some(cursor) = &cursor
        && (cursor.scope != scope || cursor.members != members)
    {
        return Err(changed_cursor());
    }
    let mut result = page(root, options, true);
    result["offset"] = json!(after);
    result["snapshot_total"] = json!(through);
    result["current_total"] = json!(inventory.len());
    result["supervisor"] = json!({"recorded_process":runtime.owner});
    // Reserve the largest cursor and fixed metadata before admitting rows.
    result["next_cursor"] = json!(token(&scope, &members, through, through, options.limit));
    let mut bytes = serde_json::to_vec(&result).unwrap().len();
    let mut records = vec![];
    for (id, input_sha256) in inventory
        .iter()
        .take(through)
        .skip(after)
        .take(options.limit)
    {
        control.check()?;
        // Only page candidates (including byte-budget lookahead) are opened.
        // Listing never reopens source files,
        // font licenses, completed outputs or the pinned worker executable.
        let input = store::input(&tx, id)?;
        let state = store::state(&tx, id)?;
        let row = json!({"request_id":id,"input_sha256":input_sha256,"document":{"id":input.document.id,"revision":input.document.revision},"destination":publish::destination(&input.output)?,"format":input.output.format,"state":state.phase,"attempt":state.attempt,"cancel_requested":state.cancel_requested,"progress":state.progress,"submitted_ms":state.submitted_ms,"updated_ms":state.updated_ms,"error_code":state.error.as_ref().map(|e|&e.code),"next_action":if state.phase==Phase::Completed {Some("job.result")} else if state.phase==Phase::Cancelled {None} else {Some("job.status")}});
        let size = serde_json::to_vec(&row).unwrap().len() + 1;
        if bytes + size + 32 > MAX_PAGE_BYTES {
            if records.is_empty() {
                return Err(err(
                    "JOB_LIMIT",
                    "Job listing metadata and one record exceed 32 KiB",
                ));
            }
            break;
        }
        bytes += size;
        records.push(row);
    }
    drop(tx);
    control.check()?;
    let next = after + records.len();
    result["returned"] = json!(records.len());
    result["records"] = json!(records);
    result["next_cursor"] =
        json!((next < through).then(|| token(&scope, &members, through, next, options.limit)));
    if serde_json::to_vec(&result).unwrap().len() > MAX_PAGE_BYTES {
        return Err(err(
            "JOB_LIMIT",
            "Job listing exceeds its 32 KiB result bound",
        ));
    }
    Ok(result)
}
