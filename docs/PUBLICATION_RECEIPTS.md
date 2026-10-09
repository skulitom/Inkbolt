# Durable publication receipts

Add `receipt:{receipt_root,request_id}` to `document.publish`, `session.publish`, `session.backup`, `session.recover` or `session.migrate` to retain a prepared output record before create-only publication. The original synchronous commands and formats stay available without this option. Durable publication currently uses the verified Windows local-filesystem backend. It is shared by the Rust library, JSON CLI and MCP executor; it does not start a background worker.

With a workspace, `receipt_root` defaults to `.inkbolt/publications`. Without one, provide an absolute root. New receipt directories are created only after output preparation succeeds. Output directories must already exist. The receipt ledger is separate from document sessions and does not add an undo revision.

```json
{"command":"session.publish","session_id":"poster","expected_revision":12,"output":{"file_name":"poster-r12.png","format":"png"},"receipt":{"request_id":"poster-png-r12"}}
```

Use the same request ID and normalized typed inputs to recover the original publication. New session exports still check the expected current head; committed retries do not recapture a newer head or reopen the source session/resources. `document.publish` fingerprints the supplied typed snapshot, resources and output options. `session.publish` fingerprints the session root/ID, expected revision and output options, then captures that exact head before encoding. A reused request ID with different input returns `REQUEST_ID_REUSED`. Control/deadline fields are outside the durable identity; invalid typed nonfinite values reject before fingerprinting.

The ordinary output receipt includes its byte length, SHA-256, format, source revision, selected artboard and actual encoder loss/colour/metadata details. The added `publication` object identifies the receipt root/request, whether this is a replay, and completion state. Preparing durable output shares the exact existing publication encoder and does not change export semantics or force a format conversion.

## Inspect or recover after a lost response

```json
{"command":"publication.receipt","request_id":"poster-png-r12"}
```

This returns either `state:"prepared"` with the proposed output identity and `next_action:"publication.recover"`, or `state:"complete"` with the historical publication result. It does not open the output or source resources; `output_rechecked:false` is explicit. A completed receipt remains historical evidence if the file is later moved, removed or changed. It is not a current availability or integrity certificate. Normal SQLite hot-journal recovery may occur when opening the ledger.

```json
{"command":"publication.recover","request_id":"poster-png-r12"}
```

Recovery of a prepared output, backup or migration record verifies the retained staging file's exact length, SHA-256 and physical file identity. It publishes those already prepared bytes if the final destination is absent. If the destination exists, it must be the same file as the retained staging link; unrelated identical bytes are a conflict. No re-render or source-file lookup is required. Completed records return the saved result even with an expired new control or missing output.

History requests retain their ordinary backup/restoration/migration result, with the same added `publication` object. Their fingerprints include the operation kind, session ID/root where applicable, source byte identity or expected revision, and output/version options. Completed retries do not reopen the original session or backup, recapture an advanced head, or recreate a deleted output. Without `receipt`, their original create-only behavior remains: repeating success returns `OUTPUT_EXISTS`.

A restoration publishes a **mutable session database**. Before creating an absent destination, recovery requires the original exact staging bytes and rejects existing journal/WAL/shared-memory sidecars. If the destination already exists, both its physical file identity and the retained staging link must match the prepared record. That pair witnesses the original creation even if later session edits have changed the bytes. Recovery then records the original historical receipt without opening, validating, repairing or rolling back the current session or its journals. Use `session.verify` for current history integrity. A different file with identical bytes, a substituted/missing witness, or an absent destination with changed staging bytes rejects and preserves the evidence. Immutable backups and migration outputs still require exact original bytes even when already published.

An initial `document.publish` request using a saved/file document reference still needs that reference resolved by the JSON adapter. If that input is no longer available, use `publication.receipt` or `publication.recover` instead. A completed `session.publish` retry uses its original fingerprint without reopening the session.

Workspace checks apply both to incoming runtime paths and to stored output/staging paths when recovery accesses them. A copied ledger can be inspected as data in another workspace, but does not authorize writing outside it. Missing, altered or substituted evidence fails explicitly and all existing final files are preserved.

## Commit and cancellation boundaries

Encoding completes before the ledger writer lock is acquired. A new `.inkbolt-publication-*.tmp` file in the output directory receives the complete bytes and is flushed. History operations instead hard-link their independently verified, flushed SQLite temporary into that namespace, avoiding a second whole-file allocation or copy. Its prepared receipt is committed before the final hard link. A writer transaction serializes same-ledger recovery/publication. The final cancellation check precedes the no-overwrite link; late cancellation preserves published success.

After the link, completion is recorded in a second ledger transaction state. If that write fails, the command still reports `created:true`, with `publication.state:"completion_pending"` and `recovery_required:true`. The already durable prepared record and staging link allow `publication.recover` to finish. The engine does not relabel an existing committed output as unpublished or render it again. This covers an uncertain completion-write outcome; it does not guarantee storage hardware durability.

Before a prepared record is durable, normal failure/cancellation removes the live call's own staging file. After preparation is committed, failure or cancellation retains its evidence so recovery can finish. Recovery is an explicit request to finish the original publication; it does not automatically resume cancelled work. Uncertain preparation commits also retain staging evidence. Process death can leave unreferenced staging/database temporaries, which retries preserve. Successful completion cleans only its identified staging link. There is no directory sweep or automatic history pruning.

Prepared records retain a hard link so the original file remains alive during recovery. Windows identity uses the volume serial number and 128-bit file ID from the documented [file-information interface](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getfileinformationbyhandleex) and [FILE_ID_INFO contract](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info). The small original binding adds no package or SDK source. Unsupported file-identity operations fail explicitly; no fallback infers ownership from equal hashes.

## Bounds and verification

Each receipt root holds at most 1,024 records and 64 MiB of receipt payloads. Each record is at most 1 MiB; database pages are capped at 128 MiB. Exports retain the existing 32 MiB publication limit and all document/render limits. History copies retain their separate 128 MiB database limit and bounded copy/hash buffers. Output payloads retain version 1; history payloads use version 2 with an explicit backup/restore/migration kind. Existing output rows need no migration. Older readers reject unknown history payloads before acting on them. The checksummed, exact-schema SQLite ledger itself remains version 1, 4,096-byte pages, rollback DELETE journaling and synchronous FULL. Unknown application/version headers reject before opening SQLite so unrelated journals are preserved. A full ledger rejects new requests while old receipts remain recoverable; preserve it and choose another root for new work. Checksums are corruption checks, not authentication.

Original Python fixtures verify actual encoded bytes across six formats, exact retries, source-session/resource disappearance, prepared recovery, identical-but-unrelated destination rejection, corrupted/missing evidence, unknown formats, workspace relocation, concurrent publishers and MCP parity. Rust child-process tests terminate writers during staging, before/after receipt creation, and before/after publication/completion; cancellation exercises the same boundaries through the shared executor. Tests also inject a failed completion save, serialize competing recovery, and fill the record/payload budgets without eviction.

These are local Windows process-crash and cooperative cancellation checks. Power loss, hostile concurrent file/path replacement, network filesystems, cross-machine ledger portability and other platforms are not certified. [Durable background exports](JOBS.md) use these receipts for their publication boundary. History fixtures also verify all three optional receipt paths, advanced/missing sources, identical-but-unrelated restored files, a real edit between restoration and completion, sidecars, records above the export byte limit, independent table preservation, concurrency, MCP parity, process termination and failed completion writes. Resource import stores and other writers retain their separately documented receipt contracts; the complete [A4 recovery audit](RECOVERY_CONTRACTS.md) records those writer boundaries and their interruption evidence. No original engine checkpoint or model-driven benchmark is awarded for this infrastructure.
