# Compact session responses

Set `response_mode:"compact"` on `session.create`, `session.read`, `session.apply`, `session.apply_proposal` or `session.receipt` to avoid receiving the entire saved document on each call. CLI and MCP use the same projection. Omission or `response_mode:"full"` retains the original full response.

```json
{"command":"session.apply","session_id":"poster","expected_revision":3,"request_id":"move-title","action":{"type":"edit","operations":[{"op":"transform","id":"title","matrix":[1,0,0,1,12,0],"space":"world"}]},"response_mode":"compact"}
```

With a workspace, the session root defaults as usual. Without one, supply `session_root`. Discover each operation's exact fields with `schema.lookup` before constructing edits.

Compact responses include:

- `document_ref`, with the exact historical document revision and session root; use it directly in a later render, inspect, edit or publish request.
- `document_summary`, with identity, kind, integer canvas dimensions and item/asset/font counts. Full logical canvas details remain in the referenced document.
- Original current-head fields, resource bindings and replay flag when provided by the command. These are distinct from the historical revision in `document_ref`.
- For receipt-bearing results, `receipt_summary` with original identity/state fields and `change_count`, plus `receipt_ref` containing the arguments for `session.receipt`.
- For reads, history depths and `snapshot_count`. `omitted` explicitly lists the full fields left out.

The original document, detailed receipt changes and named snapshot list remain stored. Request a full session read/receipt when those details are needed. Reading a named snapshot returns a reference to its saved revision even after the head advances. Compact results never point silently to the current head.

Response mode is presentation only. It is removed before typed execution and durable fingerprinting. A full request can be retried as compact, or vice versa, with the same request ID. Committed creation/edit retries return the original receipt even with a newly expired deadline; new writes still fail before publication when cancelled or expired. Invalid modes and unsupported command/mode combinations reject before any mutation.

The target is at most 8 KiB for ordinary compact result JSON. Long explicit resource paths can exceed that target; the adapter does not turn an already committed success into a size-limit error. The current implementation reduces returned bytes, while the engine still materializes its internal full result. It does not claim reduced storage or peak memory.

Compact mode is currently limited to durable session results. A snapshot edit or import that has not been saved still returns its full document. Catalog mode (`--tools core|full`) is independent of response mode. MCP `response_format` chooses JSON, Markdown or the explicit preview transport; `response_mode` belongs to the engine arguments, including the inner `arguments` of `inkbolt_run`. See [paged inspection and preview transport](AGENT_INSPECTION.md) for bounded selected records and PNG payload references.

`tests/test_compact_responses.py` checks a 65,536-pixel saved document, the 8 KiB ordinary receipt target, recovery of every original pixel, CLI/MCP parity, mixed-mode retries, historical references after later edits, named snapshots and rejection before mutation. `tests/session_retries.rs` checks expired creation retries and rejects optional nonfinite Rust values that would otherwise serialize like missing values. Default full responses continue through the existing suite. See [workspaces and input references](AGENT_WORKSPACE.md) and the [readiness plan](AGENT_READINESS.md).

`python tools/measure_responses.py` records actual CLI input/output bytes, per-call elapsed time, executable/source fingerprints and independent pixel recovery for the original fixture. It uses a temporary external session and makes five scripted engine calls. `--output <new-external-report.json>` retains a create-only report. This measures response volume; it does not measure autonomous task success, model tokens or peak memory.
