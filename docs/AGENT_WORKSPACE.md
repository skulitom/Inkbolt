# Workspaces and saved revisions

The optional durable output receipt store defaults `receipt_root` to `.inkbolt/publications`. Prepared recovery checks saved output and staging paths against the selected workspace before file access. Receipt inspection returns saved path data without following it. See [publication receipts](PUBLICATION_RECEIPTS.md).

CLI and MCP accept an optional explicit workspace. Put the flag before the request file or `mcp`:

```powershell
inkbolt --workspace C:\Work\Graphics request.json
inkbolt --workspace C:\Work\Graphics mcp --tools core
```

The directory must already exist and be absolute. Starting a process, inspecting capabilities and looking up schemas do not create folders. The working directory and environment do not silently select a workspace. Existing commands without the flag retain their explicit-root behavior. `capabilities.workspace` reports the selected canonical root and defaults; `capabilities.agent_inputs` describes the shared JSON interface.

| Omitted runtime root | Default relative to workspace |
| --- | --- |
| `session_root` | `.inkbolt/sessions` |
| `asset_root`, image/sequence `store_root` | `.inkbolt/assets` |
| `font_root`, font-import `store_root` | `.inkbolt/fonts` |
| `output_root` | `.` |

Explicit runtime paths can be relative to that workspace or absolute inside it. This includes request files, source images, fonts, licenses, profile sources, sequence-frame sources, linked-object roots, recipes and cancellation markers. Output names retain their existing validation and create-only publication rules. Output directories must still exist when required by the publication command; store commands create their own directories. Explicit `null` retains optional-root semantics, rather than selecting a default. Required non-null roots still reject `null`.

Path checks reject parent traversal, alternate streams, drive-relative paths and outside absolute paths. On Windows only local disk paths are accepted. Existing links and junctions resolve before the containment check; missing leaves are checked through their nearest existing ancestor. Metadata, document contents and arbitrary descriptive strings are not interpreted as paths. This is a checked argument convention, not an OS sandbox or protection against hostile concurrent filesystem replacement. The process retains the launching user's permissions.

## Saved document input

A top-level `document`, `before` or `after` argument that normally takes a full snapshot can instead take an exact committed session revision:

```json
{"command":"document.render","document":{"session_id":"poster","revision":3}}
```

Outside a workspace, include `session_root` in the reference. Inside a workspace it is optional and uses the session default; explicit roots follow the same path rules. The reference accepts only `session_id`, `revision` and `session_root`. Revision is required, cannot be a moving head, and must have been committed. A supplied `session_root` must be a string, not `null`.

The engine captures and checks the revision's immutable state and receipt in one read transaction, then releases the database before rendering or further work. Future revisions fail with `REVISION_NOT_FOUND`; damaged saved content fails explicitly. Neither lookup nor a snapshot edit changes the source session. To commit edits use `session.apply` with its existing expected revision and durable request ID. A `document.edit` against a reference returns a proposed snapshot exactly as it does for inline input.

Saved asset/font bindings, including `null`, are inherited by commands with resource arguments. Explicit request fields take precedence, then saved bindings, then workspace defaults for still-omitted fields. Comparisons inherit each side separately. Resource-consuming session operations also check stored bindings; a workspace cannot publish through an old outside root or restore outside bindings with undo. A resource-rebinding action can explicitly repair them. Read-only history and receipt recovery remain available, and committed retries are recovered before cancellation checks as before.

References are supported in top-level snapshot arguments only. Nested `transfer.source` remains an inline document. Sessions still depend on their external resource stores; a reference is not a backup. A retried request containing a reference must still resolve its source revision; durable receipt lookup is available if that source is no longer present.

## Snapshot file input

Publish a create-only JSON snapshot with `document.publish` or `session.publish`, `format:"snapshot"` and a new `.json` filename. Its receipt supplies the exact path and SHA-256. A later top-level snapshot argument can use those values:

```json
{"command":"document.inspect","document":{"file_path":"poster.json","sha256":"<64 lowercase hexadecimal characters from the publication receipt>"}}
```

Both fields are required, with no extras. `file_path` follows workspace path rules; without a workspace it must be absolute. The file is read once with a 16 MiB bound. Its exact bytes must match the supplied hash before parsing. Changed bytes return `SOURCE_MISMATCH`; malformed JSON, duplicate keys, response envelopes and files containing another reference fail with `INVALID_DOCUMENT_FILE`. References never recursively open other files. The expanded request retains its separate 16 MiB limit, including both sides of a comparison.

The file contains an ordinary editable snapshot and does not inherit a session's resource bindings. Supply resource roots explicitly or use workspace defaults. Read, inspect, edit and compare calls preserve the input file; edits return a new snapshot. Publish that result to a new filename. A file reference does not authorize replacement of an existing output. To recover a committed session creation after the source file changes or disappears, use `session.receipt` rather than changing the pin on the original request ID.

## Interface and verification

Both CLI and MCP use `request::execute` for JSON preparation, followed by the shared typed executor. Rust callers can use that JSON API with `Workspace` and `Control`, or continue using the unchanged inline-snapshot `Request` API. Request bytes and the expanded request are each bounded to 16 MiB. Cancellation/deadline context covers preparation and execution; database lock waits remain bounded. MCP preparation runs on the engine worker so the protocol reader can process ping and cancellation while a reference is being read.

Command schemas from `schema.lookup` and both MCP catalogs describe the reference alternatives. Workspace lookups remove defaultable roots from required fields and report sizes after adjustment. Shared `document` type lookup and the legacy `schema` command still describe the inline Rust snapshot contract. Compact catalogs remain within their 96 KiB budget. Results default to their previous full shapes; [compact session responses](AGENT_RESPONSES.md) are explicit.

`tests/test_agent_workspace.py` checks real CLI/MCP behavior: canonical defaults, no writes during discovery, historical pixels, independent comparison, create-only output, actual image/font stores, explicit root compatibility, strict reference failures, metadata preservation, link escapes, damaged revisions, resource-history rollback/repair and cancellation. `tests/test_document_files.py` checks independent byte hashes, file round trips, original pixels, source preservation, malformed/changed/recursive inputs, explicit resource roots, combined expansion limits and durable creation retries. This is scripted contract evidence, not a model-driven task benchmark. See [agent readiness](AGENT_READINESS.md) for remaining gates.
