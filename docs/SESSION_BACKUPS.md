# Checked session backup and restoration

Backup lock waiting shares the SQLite busy timeout; the retry interval is named separately. Both are reported under `capabilities.session_backups` and listed in [central limits](LIMITS.md).

`session.backup` captures a specified current revision and creates a standalone SQLite backup containing the entire session history. `session.recover` restores an exact backup into an unused session destination. They share the Rust library, JSON CLI and MCP stdio executor. Neither command replaces existing files or migrates storage implicitly.

```json
{"command":"session.backup","session_id":"poster","expected_revision":4,"output":{"file_name":"poster-r4.sqlite3"}}
```

Without a workspace, supply absolute `session_root` and `output.output_root`. A workspace defaults them to its session store and workspace root, respectively. The backup output directory must already exist. The portable single filename must end in `.sqlite3`; reserved device names, traversal and engine temporary prefixes are rejected. New publications reject all existing destinations or matching `-journal`, `-wal` or `-shm` companions with `OUTPUT_EXISTS`.

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

You can recover a Windows history on Linux, or a Linux history on Windows. `session.verify`, `session.read` and `session.receipt` retain the original bindings and history hashes. When a saved root uses the other operating system's path syntax, an operation that needs that binding returns `RESOURCE_REBIND_REQUIRED`. A native path outside the selected workspace still returns `PATH_OUTSIDE_WORKSPACE`.

Import the original image or font into a store in the destination workspace. Use a `resources` action to bind the store at a new revision. For example, a session that only uses images can use this action with `session.dry_run` and `session.apply_proposal`.

```json
{"type":"resources","resources":{"asset_root":".inkbolt/assets","font_root":null}}
```

Structural comparisons can inspect the old bindings. Pixel comparisons require accessible roots on both sides. To render a historical document reference with a relocated store, pass the appropriate local roots explicitly. Rebinding the head preserves the earlier bindings and receipts.

### Moving artwork with embedded image data

If the document contains only embedded artwork, you can create its session
without binding it to the workspace's asset and font directories. Include
both null fields in the `session.create` request.

```json
{"resources":{"asset_root":null,"font_root":null}}
```

We opened a PDF with an embedded palette image and JPEG alpha on Windows,
moved the image and backed up revision 1. A Linux MCP process recovered the
backup, retried the move with the original request ID and undid it at
revision 2. Publishing revisions 0, 1 and 2 reproduced the Windows
original, moved and original PDFs byte for byte. Only the backup was
copied to the Linux workspace.

If the session was created with the default Windows workspace bindings,
an undo that would restore those paths on Linux returns
`RESOURCE_REBIND_REQUIRED`. Rebinding the head leaves the old states'
paths intact. In a second run we rebound both stores, read the original
placement with `document.validate` on revision 0, and applied that
transform as a new edit. Supplying the local `resources` explicitly to
`document.publish` also let us publish the two earlier revisions. All
three results matched the corresponding Windows files.

### Moving a 16-bit image with stored tiles

A session backup preserves the edit history. When a raster layer uses native
tiles, copy its tile files from the original asset store separately.
Include the tiles referenced by **every revision you want to render**.
Keep each `.native-tile` filename and verify that its SHA-256 matches the
filename stem. Recover the session, then pass the destination asset root
when publishing an earlier revision. For example, this CLI request uses
a workspace-relative directory and publishes a straight-alpha RGBA16 TIFF.

```json
{"command":"document.publish","document":{"session_id":"photo","revision":1},"resources":{"asset_root":"tiles","font_root":null},"output":{"format":"tiff","file_name":"repaired.tiff","render_options":{"evaluation":"tiled"},"image_options":{"depth":"u16","channels":"rgba","compression":"none"}}}
```

A Windows agent repaired 168 pixels in a 1920 × 1080 photo, then undid and
redid the edit. We transferred its revision-3 backup and 139 distinct tile
files to Linux. The original used 135 tiles. The repair added four. Linux
recovered all four request receipts and reproduced the original, edited,
undone and redone TIFFs byte for byte. With one edited tile missing, the
original revision still exported. Publishing revision 1 returned
`SAMPLE_TILE_MISSING` and left its filename available. Supplying that
tile let the same request succeed.

## Publication, interruption and limits

The existing limits remain: at most 128 MiB of database pages, 64 MiB of stored content, 256 states, 2048 requests and 32 named snapshots, with the ordinary per-state/model/receipt bounds. Copying uses bounded steps or 64 KiB byte buffers; checksums and validation run before publication. These limits do not imply a peak-memory or latency benchmark result.

`control` supports ordinary cancellation and deadlines. Checks occur during copying/hashing, between verification records and immediately before publication. Individual filesystem/SQLite calls are not forcibly interrupted. Complete bytes are flushed before an atomic create-only hard link publishes the destination. Publication is the commit point: late cancellation returns the prepared success receipt and does not remove the completed result. Two publishers have one winner.

Normal failure/cancellation removes only the live operation's own temporary file and rollback journal. Process termination can retain `.inkbolt-session-*.tmp` files and companions; retries preserve those orphan files. The engine does not sweep unrelated work. A read-only backup, dry run or comparison cannot repair a hot journal left by an interrupted source writer. Keep the original database and journal together, recover/inspect them first through ordinary `session.verify` or `session.read`, and then retry the backup.

Add optional `receipt:{"request_id":"backup-poster-r4"}` to retain a durable historical result. Its `receipt_root` defaults to `.inkbolt/publications` in a workspace; supply an absolute root otherwise. `publication.receipt` inspects the saved result and `publication.recover` finishes interrupted publication. Repeating the same request and inputs returns that original result even after the source head advances or source/output files disappear. Different inputs under the same ID reject. Without this option, repeating success still returns `OUTPUT_EXISTS`.

Restoration receipts describe the original creation, not current integrity. A prepared receipt recognizes an already-published restored session through the retained and destination physical file identities, preserving later edits and journals. If the destination is absent, only unchanged original staging bytes can be published, with no pre-existing sidecars. Backups remain exact-byte outputs. See [durable receipts](PUBLICATION_RECEIPTS.md) for recovery, versioning, bounds and interruption semantics.

Storage versions **1 and 2** are supported, with new sessions using version 2. See [explicit migration and linked history](SESSION_LINEAGE.md) for checked version upgrades and continuation when history fills. Portable resource packaging remains open. [Durable export jobs](JOBS.md) cover document outputs; history operations remain synchronous with optional durable receipts. Local locking/hard-link filesystems are required. Process-crash behavior is tested; remote filesystems, power loss, hostile concurrent path replacement and hardware failures are not claimed.

`tests/test_session_backups.py` independently compares SQLite table rows and file bytes; exercises retained redo/named snapshots/retry receipts, competing publishers, corrupt/future inputs, sidecars, workspace relocation and explicit resource rebinding, and checks exact semantic receipt/snapshot links. Rust tests terminate actual owned processes during copying and immediately before/after publication, cancel at the same boundaries, verify writer retry behavior during a pinned backup, preserve crash evidence, and exercise hot-journal recovery. Additional history-receipt fixtures cover lost responses, exact retries, prepared recovery, concurrent writers, preservation of edits made after restoration, failed receipt saves and create-only sidecar checks. No original engine checkpoint or autonomous model benchmark is awarded for these storage contracts.
