# Session dry runs and checked proposals

`session.dry_run` evaluates any session action against an explicit expected revision without committing it. It uses a read-only database connection and the same action preparation, lock checks, resource bindings, history limits and receipt limits as real application. It does not reserve a request ID, change snapshots, move undo/redo history or create a persistent proposal store.

```json
{"command":"session.dry_run","session_id":"poster","request_id":"move-title","expected_revision":3,"action":{"type":"edit","label":"Move title","operations":[{"op":"transform","id":"title","matrix":[1,0,0,1,12,0],"space":"world"}]},"options":{"preview":true,"compare_pixels":true}}
```

The example uses workspace session defaults. Without a workspace, include an absolute `session_root`. `action` accepts edit, undo, redo, snapshot, restore, remove_snapshot and resources with their usual typed fields. A new action uses a fresh request ID. If that ID was already committed with the same action/revision, dry run returns `REQUEST_ALREADY_COMMITTED` and directs the caller to `session.receipt`; different content returns `REQUEST_ID_REUSED`.

The result contains:

- `proposal`: version-one session/request identity, expected revision, normalized request fingerprint, canonical before-state hash and predicted result-state hash. State hashes include resource bindings.
- `base_ref`: an exact committed revision reference; it always identifies the reviewed source.
- `predicted_receipt`: the receipt a successful commit would return, including proposed revision, state identity and ordered changes. It is explicitly a prediction, not proof of a write.
- `difference`: the ordinary structural comparison, optionally including rendered pixel differences.
- `history`: predicted undo/redo depths and named snapshot addition/removal; `proposed_resources` retains the resulting bindings.
- `dry_run:true`, `committed:false` and `source_changed:false`.

`options.preview:true` adds a whole-canvas scale-one PNG under `preview`. Existing pixel limits and output-profile rules apply. `options.include_document:true` adds `proposed_document`; it defaults to false to avoid returning a complete snapshot. That document has the predicted revision and is hypothetical. Only `base_ref` points to saved content. Preview, document inclusion and pixel comparison are all off by default; structural comparison is always returned. These options affect review output, not the proposal's action identity.

PNG preview and pixel comparison use the captured resource bindings. Structural inspection alone does not verify every external resource byte. Resource content is checked when the operation or rendering reads it. The read transaction is released before comparison and rendering; other writers can advance the session while the review result is being produced.

## Apply exactly the reviewed content

Call `session.apply_proposal` with `session_root` (or its workspace default), the returned `proposal` object and the same `action`. Both commands are direct tools in the core MCP catalog. CLI, MCP and the Rust library use the same preparation and atomic commit path. Optional `response_mode:"compact"` returns the normal pinned session receipt summary.

The checked application validates the proposal version/hashes and action fingerprint, then checks expected revision and base content under the writer transaction. It prepares the action again and requires the resulting state hash to match the proposal before persisting anything. Changed actions or before/after content return `PROPOSAL_MISMATCH`; a later session revision returns `REVISION_CONFLICT`. Unsupported operations, invalid batches, missing history, locks and limits reject as usual. No failure reserves the new request ID.

Proposal fields are integrity conditions, not authentication or an approval token. They do not lock the session or reserve filesystem capacity. Another writer, changed required external inputs or a filesystem failure can prevent a later commit. Keep using the same session store; the proposal is not a portable history archive. Original `session.apply` remains available with its existing revision and retry contract.

A successful proposal commit uses the same durable action fingerprint and receipt ledger as ordinary application. Repeating it returns the original receipt even after the head advances or with a newly expired deadline. Replay also checks that the proposal's before/after hashes match the original receipt. `session.receipt` remains the recovery path after a lost response. Presentation may switch between full/compact or MCP JSON/preview without changing durable action identity.

Typed Rust actions receive a recursive finite-number check before calculating their fingerprint. This rejects nonfinite optional values before JSON can collapse them to null and accidentally match an earlier valid request. The check also applies to ordinary action retries and dry runs; JSON clients already cannot send nonfinite number literals.

MCP `response_format:"preview"` moves a dry-run PNG to one image payload location and retains its metadata through a content reference. See [inspection and preview transport](AGENT_INSPECTION.md). To review a focused region or contact sheet before commit, request `include_document:true` and pass the returned hypothetical document to the [focused preview commands](FOCUSED_PREVIEWS.md). Broader diagnostics, export preflight and the seeded-repair gate remain separate [readiness](AGENT_READINESS.md) work.

`tests/test_session_proposals.py` compares every action's predicted receipt, document, resources, history and pixels with the real commit. It checks unchanged database bytes/timestamps, a concurrent reserved writer, competing revisions, invalid batches, mismatched inputs, duplicate concurrent commits, compact replies and expired retries. Existing session interruption tests exercise the shared preparation/commit path. `tests/session_retries.rs` includes a regression where an optional nonfinite action previously replayed a valid receipt; it now rejects without changing saved state.
