# Sessions, history and recovery

A session stores one vector or raster document under an explicit absolute `session_root`. The CLI remains a one-request process; reopen the same session in later calls. The root must be a writable local directory supporting file locks and create-only hard links. Network filesystems and synchronization across computers are outside this storage contract.

## Commands

Commands require `session_id`, directly or inside the reviewed proposal for `session.apply_proposal`. Without a workspace, `session_root` remains required and absolute. With `--workspace`, it defaults to `.inkbolt/sessions`; explicit roots must resolve inside that workspace. Top-level document arguments can reference exact committed session revisions. See [workspaces and saved revisions](AGENT_WORKSPACE.md). IDs use document ID syntax (1..128 ASCII letters, digits, dots, underscores or hyphens). The filename is the SHA-256 of the UTF-8 session ID followed by `.sqlite3`; IDs cannot escape the root or become reserved platform filenames.

| Command | Other inputs | Result |
| --- | --- | --- |
| session.create | request_id, document; optional resources, control | Initial document at session revision 0 and durable creation receipt |
| session.read | optional snapshot name | Document, resources, revision, current_revision, state identity, undo/redo depths and named snapshots |
| session.apply | request_id, expected_revision, action; optional control | Committed document, resources and receipt; replayed flag and current head information |
| session.dry_run | request_id, expected_revision, action; optional options, control | Read-only proposal, predicted receipt/history, structural comparison and optional PNG/pixel comparison |
| session.apply_proposal | proposal, action; optional control | Commit only if revision, reviewed action and before/after content still match |
| session.receipt | request_id | Original committed result, even after later edits |
| session.history | limit in 1..128; optional after_revision | Ordered receipt page with next_after_revision and has_more |
| session.verify | optional control | Storage integrity, content/receipt/metadata checksums, references and bounded ledger validation |

`resources` has optional absolute `asset_root` and `font_root`. They are runtime bindings saved with content. Image and font bytes remain in their external immutable stores; sessions are not self-contained resource archives. Structural persistence does not imply that stored resources are present. Rendering resolves and verifies them as usual.

To render or export a session, call `session.read` and pass its `document` plus returned resource roots to the existing document/artboard export. This exports that immutable read result even if another writer advances the session. Exports still return JSON data; they do not write output paths.

## Actions and revisions

| action.type | Fields | Effect |
| --- | --- | --- |
| edit | operations; optional label (512 UTF-8 bytes, no controls) | Apply 1..64 validated operations as one undo step |
| undo / redo | optional steps (default 1) | Move 1..256 available content-history steps |
| snapshot | name | Create a named reference to current content; existing names fail |
| restore | name | Restore named content as a new undoable action |
| remove_snapshot | name | Remove that name; immutable history and receipts remain |
| resources | resources | Replace resource-root bindings as an undoable action |

Session revisions begin at zero independently of the input snapshot's revision. Every successful action increments revision once. Undo restores content, geometry, pixels and resource bindings with a **new** revision; it never moves the revision counter backwards. Creating/removing a snapshot changes metadata and revision without adding a content undo point. Snapshot reads report the revision at which that name was created and the separate current revision.

Editing, restoring a snapshot or changing resource bindings after undo clears the redo stack. Old immutable states, named snapshots and receipts remain available. Locks still constrain editing; undo restores the entire saved state, including its locks. Invalid operations, unavailable history steps and limits discard the complete action and do not reserve its request ID.

Each receipt contains request_id, revision, from_revision, action, label, from_state, state_id, state_sha256 and ordered operation changes. These changes identify affected operations/items; Use session.diff for stable-ID structural/derived geometry comparisons and optional rendered pixel differences. State IDs are internal immutable-content identities and can have gaps.

## Retries and conflicts

Provide a new request ID for each intended action. Retrying the same ID with the same normalized typed action and expected revision returns the original receipt and original document with `replayed:true`. `current_revision` and `current_state_id` describe the newer head, if any. A replay does not move history or reapply edits. A reused ID with different input fails with `REQUEST_ID_REUSED`.

The retry lookup occurs before revision/cancellation checks: a committed creation or edit remains committed even if the retry has an expired deadline. Existing creation inputs still receive bounded validation without the newly expired control; invalid typed numbers cannot masquerade as missing JSON values in the fingerprint. New creation uses full controlled validation before reserving storage. Otherwise, a stale expected revision fails with `REVISION_CONFLICT`; inspect the current document before issuing a new action. Transactions serialize writers. `SESSION_BUSY` means the bounded 250 ms lock wait expired; retry the same request ID. A lost response or I/O error can leave commit outcome uncertain: inspect `session.receipt` or retry the original request rather than generating a new ID.

`response_mode:"compact"` is optional on creation, read, apply, apply_proposal and receipt commands. It returns pinned document/receipt references and summaries; full responses remain the default. This presentation field is excluded from durable identity, so it may change on retry. See [compact responses](AGENT_RESPONSES.md). [Dry runs and checked proposals](SESSION_PROPOSALS.md) add read-only review before applying the same validated action; typed actions reject nonfinite numbers before retry fingerprinting.

Creation is also idempotent for identical typed document/resources and request ID. A different creation request never overwrites an existing session. The existing session remains untouched when input validation or creation publication fails.

## Cancellation

`control` is optional on session.create, session.apply, session.dry_run, session.apply_proposal, session.verify and document.edit:

```json
{"timeout_ms":10000,"cancel_file":"C:/work/controls/cancel-request-17"}
```

Timeout is 0..60000 ms; zero expires immediately, omission means no deadline. `cancel_file` must be absolute; its existence requests cancellation. The caller creates/removes the marker. Inkbolt does not modify it. Rust callers may instead clone `Control` and call `cancel()` on the shared token.

Checks are cooperative, between operations/verification records and immediately before commit/publication. They do not forcibly interrupt an individual operation, filesystem call or SQLite lock wait. Precommit `CANCELLED`/`TIMEOUT` discards all candidate changes. A cancellation arriving after commit does not turn success into an uncommitted failure. Document rendering and exports also accept the shared control object; supported commands report their controls in the request schema. Blocking filesystem and individual codec calls are not forcibly interrupted.

## Storage limits and persistence boundary

| Bound | Limit |
| --- | ---: |
| Immutable content states, including initial | 256 |
| Committed requests, including creation | 2048 |
| Undo or redo depth | 256 |
| Named snapshots | 32 |
| One serialized state, including resource roots | 8 MiB + 16 KiB |
| Combined serialized content states | 64 MiB |
| Database pages | 128 MiB |
| One receipt | 64 KiB |

Profile-specific document and whole-request limits also apply; see [LARGE_VECTOR.md](LARGE_VECTOR.md). History is never silently evicted. `HISTORY_LIMIT` means preserve the current session, read/export its desired document and create a new session ID for more work. Limits protect storage; they do not extend the engine's rendering or document-size capacity.

The store uses schema version 1, SQLite rollback journal DELETE mode, 4096-byte pages and synchronous FULL. Content, head, undo/redo stacks and receipt commit together. Ordinary writable openings perform SQLite hot-journal recovery. Read-only dry runs and comparison captures do not repair a pending hot journal; first use `session.verify` or an ordinary session read to recover and inspect the store. Keep the database and its journal together. Tests terminate an owned process after actual dirty-page spill before commit and immediately after commit; the former restores the old state and the latter retains the new receipt. Cancellation after spill also rolls back.

Creation flushes and closes its temporary database before create-only hard-link publication. An interrupted creation can leave an unpublished `.inkbolt-session-*.tmp` file and journal. No automatic sweep deletes these, because another process may own them. The final database and its `-journal` must stay together during recovery. Copy/backup only when all users of that session are closed; retain external image/font stores separately. There is no live backup or migration command yet.

Durability relies on local filesystem locking and the operating system honoring flushes. Process interruption is tested; sudden power loss, failing hardware and malicious modification are not guaranteed by checksums. Stored paths are explicit local paths, not a filesystem sandbox or access-control boundary. Unsupported versions, changed schema, corrupt states/receipts or missing references fail explicitly and do not trigger destructive repair.

`session.diff` compares two committed revisions without modifying history; `session.diff.preview` adds aligned images, a change mask and coordinate maps. Both capture their pair through a read-only database connection before releasing the transaction. `session.publish` captures the expected current revision, releases its read lock, then exports it to a create-only destination. These commands reuse saved resource bindings; see [agent execution](AGENT_EXECUTION.md) and [visual comparisons](VISUAL_COMPARISONS.md). MCP cancellation notifications share the same precommit controls. Ordinary in-memory exports remain available.
