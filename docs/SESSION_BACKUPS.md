# Checked session backup and restoration

`session.backup` captures a specified current revision and creates a standalone SQLite backup containing the entire session history. `session.recover` restores an exact backup into an unused session destination. They share the Rust library, JSON CLI and MCP stdio executor. Neither command replaces existing files or migrates storage implicitly.

```json
{"command":"session.backup","session_id":"poster","expected_revision":4,"output":{"file_name":"poster-r4.sqlite3"}}
```

Without a workspace, supply absolute `session_root` and `output.output_root`. A workspace defaults them to its session store and workspace root, respectively. The backup output directory must already exist. The portable single filename must end in `.sqlite3`; reserved device names, traversal and engine temporary prefixes are rejected. All existing destinations or matching `-journal`, `-wal` or `-shm` companions fail with `OUTPUT_EXISTS`.

The `backup` object in the result is the input identity for restoration:

```json
{
  "command":"session.recover",
  "session_root":"restored-history",
  "session_id":"poster",
  "source":{
    "file_path":"poster-r4.sqlite3",
    "bytes":32768,
    "sha256":"<exact lowercase SHA-256 from the backup receipt>"
  }
}
```

Use the actual byte count and hash from the receipt; the example is illustrative. Restoration accepts absolute paths without a workspace, or checked workspace-relative paths with one. It creates a missing destination session directory as needed. The session filename retains the ordinary hash-of-session-ID convention. The supplied ID must match the backup's original session ID. An existing session or companion journal is always preserved, even if its content appears identical.

## What is retained and checked

Backups retain every immutable content state, committed request fingerprint/receipt, undo and redo stack, named snapshot and saved resource binding. Restoration preserves original revision numbers and request IDs. Reading historical revisions, replaying an old request and resuming undo/redo use the original session contract. Editing the restored copy creates independent later revisions; it does not alter the source session or backup.

Both operations verify exact schema/application version, SQLite integrity, bounded state and receipt counts, stored payload lengths, model/resource descriptors, metadata/content/receipt/snapshot checksums, contiguous request revisions, previous-state linkage and each named snapshot's historical revision. `session.verify` shares the same full-history validation. Its result now includes `head_state_sha256`, a logical `history_sha256`, undo/redo depths and snapshot count. The logical fingerprint covers ordered metadata, state identities, retry fingerprints/receipts and snapshots. It is separate from the backup's exact file-byte SHA-256 and is not an authentication signature.

Backup holds one read transaction at the requested head while copying through the pinned SQLite backup API in at most 256-page steps. This prevents source commits from restarting the copy or mixing revisions. Concurrent writers can read/prepare work but may receive the existing bounded `SESSION_BUSY` error at commit; retry the same editing request ID after the backup completes. The copy is independently verified against the captured history before publication. The session's live files are never copied piecemeal.

Recovery reads the supplied regular, non-symlink file once into an exclusively created temporary, hashing the exact bytes as they are copied. Length or hash mismatch fails with `SOURCE_MISMATCH`. The complete copied history is checked before it becomes a session. Source backup files with any journal/WAL/shared-memory companion are rejected with `BACKUP_SIDECAR`; the recovery command does not open or repair the source SQLite file. Unknown versions and changed schemas return `SESSION_FORMAT`; invalid history returns an explicit error. A failed restore may leave an empty newly created directory, but no final session file.

## Resources and portability

Image/font stores remain external. Receipts explicitly report `resources_copied:false` and `external_resources_verified:false`. A valid history backup is not a self-contained artwork archive or evidence that its fonts/images are currently available. Stored absolute paths remain exact; no automatic relinking or substituted content occurs.

When restoring in a different workspace, old resource paths can remain outside its allowed runtime boundary. Session reads can inspect those stored bindings, but rendering/editing that accesses them must satisfy the current workspace rules. Import the intended original resources into the new workspace, then use an explicit `resources` actionâ€”optionally through `session.dry_run` and `session.apply_proposal`â€”to rebind them as a new revision. Pure structural proposal comparisons do not access external roots. Old history and its original bindings remain available. This does not establish cross-platform pathname compatibility; current measured acceptance is Windows.

## Publication, interruption and limits

The existing limits remain: at most 128 MiB of database pages, 64 MiB of stored content, 256 states, 2048 requests and 32 named snapshots, with the ordinary per-state/model/receipt bounds. Copying uses bounded steps or 64 KiB byte buffers; checksums and validation run before publication. These limits do not imply a peak-memory or latency benchmark result.

`control` supports ordinary cancellation and deadlines. Checks occur during copying/hashing, between verification records and immediately before publication. Individual filesystem/SQLite calls are not forcibly interrupted. Complete bytes are flushed before an atomic create-only hard link publishes the destination. Publication is the commit point: late cancellation returns the prepared success receipt and does not remove the completed result. Two publishers have one winner.

Normal failure/cancellation removes only the live operation's own temporary file and rollback journal. Process termination can retain `.inkbolt-session-*.tmp` files and companions; retries preserve those orphan files. The engine does not sweep unrelated work. A read-only backup, dry run or comparison cannot repair a hot journal left by an interrupted source writer. Keep the original database and journal together, recover/inspect them first through ordinary `session.verify` or `session.read`, and then retry the backup.

These commands have no durable publication-receipt ledger yet. Repeating a backup or restore after success returns `OUTPUT_EXISTS`; it does not infer ownership from matching bytes or overwrite the result. Preserve the returned backup identity. A lost backup response requires explicit inspection/hash verification of the created file; restoration can be inspected through ordinary session reads and verification. This boundary remains part of the broader durable-job/publication work.

Storage versions **1 and 2** are supported, with new sessions using version 2. See [explicit migration and linked history](SESSION_LINEAGE.md) for checked version upgrades and continuation when history fills. Portable resource packaging remains open. [Durable export jobs](JOBS.md) and [publication receipts](PUBLICATION_RECEIPTS.md) cover document outputs; the backup/restore receipt gap described above remains open. Local locking/hard-link filesystems are required. Process-crash behavior is tested; remote filesystems, power loss, hostile concurrent path replacement and hardware failures are not claimed.

`tests/test_session_backups.py` independently compares SQLite table rows and file bytes; exercises retained redo/named snapshots/retry receipts, competing publishers, corrupt/future inputs, sidecars, workspace relocation and explicit resource rebinding, and checks exact semantic receipt/snapshot links. Rust tests terminate actual owned processes during copying and immediately before/after publication, cancel at the same boundaries, verify writer retry behavior during a pinned backup, preserve crash evidence, and exercise hot-journal recovery. No original engine checkpoint or autonomous model benchmark is awarded for these storage contracts.
