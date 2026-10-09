# Durable local export jobs

`job.start` captures a document and resource bindings into a local persistent queue, returns a compact ticket, and launches a hidden Windows supervisor. The submitting CLI or MCP process can close. The supervisor runs one bounded export process at a time and exits when the queue is empty. No listener, account, network service or telemetry is used.

This implements the background export portion of readiness gate A4. It does not complete the overall readiness plan, expand document/render limits, add engine-checkpoint credit, or cover every existing file writer. Jobs currently publish one output through the existing document publisher, including its artboard and format options.

## Commands

With an existing workspace selected, `job_root` defaults to `.inkbolt/jobs`; explicit absolute roots remain supported. `document` accepts the same inline, exact saved-revision and hash-pinned file references as ordinary publication.

```json
{"command":"job.start","request_id":"poster-preview","document":{"session_id":"poster","revision":3},"output":{"file_name":"poster-preview.png","format":"png"}}
```

| Command | Behavior |
| --- | --- |
| `job.start` | Save verified inputs and submit once per request ID. Identical retries return the saved job; changed inputs reject with `REQUEST_ID_REUSED`. |
| `job.list` | Rediscover retained request IDs, document revisions, destinations and saved progress in bounded pages. Never launches workers or reconciles outcomes. |
| `job.status` | Compact progress, cancellation, error and output summary. Reconciles stopped workers but never launches work or publishes an absent output. |
| `job.wait` | Observe for `wait_ms` in 0â€“30000, returning on completion, failure, cancellation, interruption or needed recovery. Cancelling the observation does not cancel the job. |
| `job.result` | Full historical publication receipt, including actual format losses, color and page details. Requires completed output. |
| `job.cancel` | Persist cancellation. Queued/interrupted work becomes cancelled; running work receives cooperative cancellation and a two-second forced-stop grace. |
| `job.resume` | Explicitly start a stalled queue or requeue failed/interrupted work with the original inputs. Completed/cancelled jobs stay terminal. Each new attempt is explicit, up to eight. |

Inspection and result commands can reconcile SQLite and saved publication state, so MCP marks them as potentially mutating. These are engine commands, separate from MCP protocol task support. `job.resume` can create a new attempt after a previous failure and is not advertised as an idempotent request. `job.start` supplies the durable submission identity.

`job.status` includes document ID/revision/content identity, progress, output identity, worker/runner identities, and the last available process report. It omits document contents and the full publication receipt. Ordinary tickets target 8 KiB; unusually long paths can exceed that target. States are `queued`, `running`, `completed`, `cancelled`, `failed` and `interrupted`. A queued job whose supervisor is absent or cannot be verified reports that recovery is needed. Inspection does not silently restart it.

## Rediscovering work after a lost conversation

Call `{"command":"job.list"}` in the original workspace, or supply the explicit `job_root`. No request ID is needed. Each row identifies the saved document revision, intended destination, format, attempt, progress and error code. Use `job.status` for current ownership and stopped-worker reconciliation, then choose explicit cancellation or resumption; completed rows point to `job.result`. A stored `running` value alone does not prove that a worker is still alive.

Listing defaults to eight records, accepts `options.limit` in 1â€“32 and bounds each result to 32 KiB. Long destinations can shorten a page. Pass `next_cursor` as `options.cursor` with the same limit and root until it is null. The first page fixes admission membership; later submissions appear in `current_total` but require a fresh listing to enumerate. Each page reads states from one database snapshot, so progress can change between pages without losing or duplicating members. Changed roots, recorded worker identities or original input membership invalidate the cursor. Cursors are content-bound continuations, not authentication or a frozen snapshot of outcomes.

Only page candidates are decoded and checksum-verified, including at most one row held back by the byte limit; other rows contribute their saved input identities to the membership check. Listing does not open resource files, outputs or executable bytes, and a missing queue returns an empty result without creating directories. It can perform ordinary SQLite journal recovery, but it does not reconcile job outcomes, launch processes or publish staged output. Discovery covers the selected root; it does not search other directories or discard old records.

## Pinned inputs and builds

The queue saves the normalized typed document, resource roots, output options, workspace boundary and worker limits. It verifies all image/font registry entries at submission, including retained licenses, nested object snapshots and instance override content. New encoding checks those identities again. Source resources remain in their original content-addressed stores: they are not copied into a job archive. Missing or altered data fails; restoring the exact originals permits explicit resumption. Already-prepared output can resume from its verified bytes without reopening resources or rendering again.

Saved/file reference expansion occurs before job submission. If a referenced source is later unavailable, inspect or resume using `job_root` and `request_id`; a fresh `job.start` containing that missing reference still needs to expand it. The persisted revision never follows an advancing session head. Source documents, media and history are never rewritten by jobs.

Each queue root is bound to the exact worker executable path, length and SHA-256 recorded when the queue was created. The engine CLI selects its own executable; Rust embedders must provide `options.worker_executable` pointing to a trusted compatible Inkbolt CLI. The verified executable is held against replacement while launching/running. A changed build is rejected; retain the matching executable for unfinished jobs or use a new queue root for new builds. There is no implicit queue migration or build substitution. Executable identity does not claim to pin the operating system or every loaded library.

## Bounds and storage

| Bound | Value |
| --- | --- |
| Active jobs per root | 32, including interrupted work |
| Retained records | 128; no eviction |
| Explicit attempts per job | 8 |
| Input payload | 16 MiB |
| Reserved state/receipt capacity per job | 1 MiB + 64 KiB |
| Inputs plus reserved state capacity | 256 MiB |
| SQLite main file | 512 MiB |
| One published output | Existing 32 MiB limit |
| Worker lifetime | 1â€“3,600,000 ms; default 300,000 ms |
| Worker committed memory | 64â€“2048 MiB; default 512 MiB |

`options.lifetime_ms` and `options.memory_mib` configure each attempt. Lifetime includes runner startup and is enforced independently of client polling. Submission `control` applies to submission; it does not become a background cancellation marker. An accepted job survives a late submission timeout. Observed process duration includes startup and polling delay. Peak committed memory is an operating-system measure, not resident memory, and may be unavailable after a supervisor crash.

Strict version-1 SQLite tables separate immutable `inputs`, mutable `jobs`, and supervisor `runtime`. Each payload has a checksum. Progress updates do not rewrite the document table. The ledger uses FULL synchronization and rollback journals. An exact header/schema check rejects unrelated or unsupported databases before ordinary recovery. Logical receipt space is reserved at admission; this does not guarantee free disk space or filesystem write success. Record and byte limits can be reached before the active-job limit. Existing records are retained when full.

Published files and retained staging evidence are outside the queue's SQLite quota. Interrupted staging files may remain even when no prepared receipt was saved; jobs do not automatically delete that evidence. Changing saved inputs or worker limits requires a new request ID. Cancel interrupted work before replacing it if its active slot or destination reservation is needed.

Progress reports actual phases and available work counters. Staging counters are encoded bytes written; validation/rendering do not invent an overall percentage or ETA. Short phases may finish between observations. Publication ownership is serialized under the job transaction, so observers may see the preceding phase until its outcome commits.

## Cancellation and recovery

The supervisor and launcher share persistent OS leases. Admission takes the launch lease before enqueueing. Idle shutdown rechecks the queue under that same lease and releases the worker lease before allowing another admission. Supervisor generations, PID and process creation time protect ownership; access denial is unknown, not proof of death. A child waits behind its startup gate until durable ownership is recorded. See [contained job processes](JOB_PROCESSES.md).

Publication writes a prepared receipt before creating the final file. Immediately before its create-only link, the runner acquires the job writer transaction and checks cancellation. If cancellation committed first, the destination stays absent. If publication wins, the job saves success before releasing the transaction; a busy concurrent cancellation may require retry. Actual published output takes precedence over a later deadline, cancellation or worker crash.

When a runner stops, the live supervisor retains responsibility for its exit report. If that supervisor is gone, inspection checks physical publication evidence before assigning an interrupted/cancelled outcome. Recovery recognizes the exact staging file and bytes, never an unrelated file with identical contents. Merely inspecting or cancelling a stopped job cannot publish an absent staged output. Explicit resumption can finish that prepared output once.

Completed receipts remain historical even after the output is deleted. Neither submission retries nor resumption recreate it. If publication succeeded but receipt bookkeeping could not finish, its receipt reports pending recovery; the output remains successful. Prepared evidence and unrelated outputs are preserved. Trusted local Windows filesystem and process-interruption behavior are verified; hostile directory replacement, network filesystems and sudden-power-loss guarantees are not claimed.

## Evidence

Original Rust fixtures exercise submission loss, supervisor death around claim/runner registration, a stopped encoder, both sides of publication, timeout after publication, queued/running cancellation, the idle-exit/admission race, capacity, and preserved receipts. CLI/MCP checks independently read PNG bytes and SQLite records and cover exact saved revisions, changed image/license/build identities, explicit resume, concurrent identical submissions, historical results, workspace restrictions and MCP EOF. Discovery checks cover progress and admission changes between pages, missing resources/builds/outputs, changed cursors, byte limits and corrupt rows. Crash fixtures verify that discovery does not reconcile or publish stopped work. The full repository checks remain required before accepting a build. This evidence does not replace model-driven workflow trials or practical-scale gates.
