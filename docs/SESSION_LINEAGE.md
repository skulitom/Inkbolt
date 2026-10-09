# Explicit migration and linked history continuation

Session storage versions 1 and 2 are supported. New sessions use version 2, which adds a bounded, checksummed provenance table. Existing version-1 sessions remain readable, editable, verifiable and eligible for backups/restoration without an implicit upgrade. Document schema version 2 is a separate contract from the SQLite storage version.

## Migrate a backup

`session.migrate` takes an exact standalone backup identity, its original session ID, `target_version:2` and a new output filename. It supports the explicit 1-to-2 transition; unknown versions and downgrades reject. A version-2 input returns `MIGRATION_NOT_NEEDED`. Use `session.recover` to restore the returned identity into an unused session root. All commands share Rust library, JSON CLI and MCP stdio behavior.

```json
{"command":"session.migrate","session_id":"poster","source":{"file_path":"backups/poster-v1.sqlite3","bytes":32768,"sha256":"<exact hash from the saved backup identity>"},"target_version":2,"output":{"file_name":"poster-v2.sqlite3"}}
```

The example uses workspace-relative paths; substitute the actual byte count and lowercase SHA-256. With no workspace, runtime paths must be absolute. Migration never changes the source backup or active session. It streams and hashes the input once into an owned temporary, validates the complete old history, adds an empty provenance table and changes the storage version in one transaction, then independently validates the result before create-only publication. Existing state/metadata/receipt/snapshot rows are untouched. The logical `history_sha256` stays identical across this migration; physical bytes and their hash change. No synthetic revision or request is added to the old ledger.

All backup bounds, standalone-file and sidecar checks apply. An optional `receipt:{"request_id":"migrate-poster-v2"}` retains the original result for durable retries and `publication.receipt`/`publication.recover`; the workspace default root is `.inkbolt/publications`. Prepared migration recovery requires exact unchanged output bytes. Completed retries work without reopening the original backup. Without this option, repeating a successfully published migration returns `OUTPUT_EXISTS`. Preserve the returned backup identity. See [durable receipts](PUBLICATION_RECEIPTS.md). No in-place migration or downgrade is offered.

## Continue under a new session ID

Create a complete `session.backup` of the parent, then pass its identity and the desired exact historical revision to `session.continue`. The new session ID must differ from the parent's, and the destination must be unused. Both supported parent storage versions are accepted. The selected revision need not be the backup's head.

```json
{"command":"session.continue","session_id":"poster-next","request_id":"continue-poster-r12","parent":{"source":{"file_path":"backups/poster-r14.sqlite3","bytes":32768,"sha256":"<exact hash from the saved backup identity>"},"session_id":"poster","revision":12},"response_mode":"compact"}
```

The result starts at revision 0 with the selected document content, original document ID and saved resource bindings. The old undo/redo stacks, named snapshots and retry ledger stay in the parent backup. The new session starts fresh bounded history, with a durable `continue` receipt. No original state is deleted or evicted. This provides a checked path forward at `HISTORY_LIMIT`; it does not raise document, raster, state, receipt or storage limits.

`lineage` in session reads, receipts (including compact results) and verification records:

- The exact parent backup path, byte count and SHA-256, parent session ID and selected revision.
- The captured parent storage version, head revision, selected stored-state hash and full logical history hash.
- The new session ID and canonical initial-state hash. Semantically equivalent parent JSON can have different stored bytes, so the two state hashes are recorded separately.

The provenance row has its own checksum and is validated against the new session's initial receipt, retry fingerprint and initial state. Removing the row from a continued session or changing its local identity links rejects. The whole-history fingerprint includes nonempty provenance. Ordinary fresh and migrated sessions report `lineage:null`, preserving version-1 logical fingerprints. Checksums detect corruption; they are not authentication of an externally supplied history.

Only one parent link is stored. Reads do not open the parent path or recursively traverse ancestry. Each referenced backup and its external resource stores must be retained if earlier history is needed. The parent backup can itself contain a prior link; inspect it explicitly through checked restoration. Continuing again does not embed an ever-growing ancestry tree.

## Retry, resources and interruption

Retry continuation with the same session ID, request ID and normalized parent identity. Once published, the original result can be recovered even after the parent backup disappears or a new deadline expires. Later edits affect the separately reported current head, not the original result. Different parent input reusing that request ID rejects. Workspace path admission still applies to every incoming request; missing parents inside the workspace do not require opening the file on replay. `response_mode` may change on retry.

Resource roots remain data in saved content. Continuation and migration do not read/copy resource stores or silently replace bindings with new workspace defaults. Rendering checks those bindings as usual. Restore/import the required immutable resources and apply an explicit resource-binding action when moving between workspaces. Compact results retain the parent link; the ordinary 8 KiB target remains a target, with long explicit paths able to exceed it.

Preparation and verification happen before publication. Both operations flush their prepared database and publish a create-only hard link. A pre-publication cancellation or failure leaves no final output; an interruption after publication leaves a complete result. The shared executor preserves committed success under late cancellation. Normal cleanup removes only the live operation's temporary files; process termination can leave owned temporary files/journals, which later retries preserve. No orphan sweep is implied.

Independent Python tests construct the frozen version-1 schema, compare every old table row, test old receipt/undo/redo behavior, select historical revisions, check provenance corruption, run competing publishers and exercise CLI/MCP/workspace/compact retries. Rust tests continue after the full 256-state limit and terminate owned processes or cancel during copying, after schema/capture preparation and immediately before/after publication through the public executor. These are Windows process-crash checks, not power-loss, hostile path replacement, remote-filesystem or performance guarantees. [Durable export jobs](JOBS.md) cover document outputs; optional [publication receipts](PUBLICATION_RECEIPTS.md) also cover backup, restoration and migration retries with checked historical results.
