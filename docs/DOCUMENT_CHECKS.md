# Document checks and export preflight

`document.check` returns located diagnostics and repair guidance without editing documents, changing resource stores or publishing files. `document.preflight` prepares the actual output bytes through the publisher's shared preparation path, then discards the payload and returns its predicted receipt. Both use the shared Rust/JSON CLI/MCP interface, pinned document references, workspace roots and cancellation controls.

These are report-producing commands. A successfully completed diagnostic request has the ordinary `ok:true` envelope even when it finds problems. Inspect `status`/`complete` for checks and `ready` for preflight. Malformed request arguments, cancellation and deadlines remain ordinary errors; cancellation never returns a misleading partial pass.

## Check retained content

```json
{"command":"document.check","document":{"session_id":"poster","revision":3},"options":{"resources":true,"typography":true,"issue_limit":64}}
```

Saved references inherit their captured resource roots. Inline snapshots accept `resources:{"asset_root":"...","font_root":"..."}`; workspace defaults apply. Both optional checks default to true. Structural validation always runs first and shares the ordinary model validator. Invalid structure returns its first error and stops dependent checks; type/schema errors that cannot form a document reject at the request boundary.

Resource checking reads every registered image and font, including unused resources, through the existing byte/hash/size/license checks. Typography also loads registered fonts when `resources:false`; setting both flags false performs structural checks without resource reads. Missing or corrupt fonts produce located resource errors and explicitly skip dependent layouts. Font variation axes/ranges are checked even for empty text.

Typography evaluates authored text frames and stories through their ordinary layout engines. Strict text/story overflow is an error. Explicitly visible/clipped text or retained story tails produce warnings when overflow is observed; story-frame ink overflow is also a warning. Reports retain the source-index convention and overset cursor for a story tail. They do not trim or replace text, select fonts, discard tails or change overflow policies automatically.

Checks include hidden content, component definitions, replacement content in instance overrides and recursively retained object snapshots. Every authored story is checked, even if no story frame currently uses it. Linked object source files are not read or refreshed: rendering uses retained snapshots, and explicit link inspection remains `object.status`. Checks do not expand every placed instance, render every effect, judge visual quality or prove a particular export is supported. Use preflight for the intended delivery.

The report contains:

- `status`: `pass`, `warnings`, `fail` or `incomplete`. Errors take precedence in this summary; also inspect `complete`.
- `complete`: all enabled checks finished without skipped layouts or work/report limits. It can be true with reported errors; it is not a pass flag.
- `valid_structure`, `reported_errors`, `reported_warnings`, `stopped_at_limit`, requested `checks`, and actual `checked` counts for documents, images, fonts, text frames, stories and skipped layouts.
- `document_id`, `revision`, and canonical typed `document_sha256` after successful structural validation. Invalid structure leaves identity/hash null rather than assigning an identity to invalid content.
- `issues`: severity, original structured `error`, `location`, concise `context`, and `recovery` guidance with relevant command names and `automatic_fix:false`.

Each location has a JSON `pointer` within the checked document and a `retained_document_path` array. Follow each array pointer to a retained snapshot string and parse it before following the next pointer; the final issue pointer addresses that decoded document. An empty array means the top-level document. Item/font/asset identifiers stay on the original error where available. Story identifiers and overset positions appear in context. Override pointers identify their original authored replacement rather than a generated instance ID.

`issue_limit` defaults to 64 and accepts 1–256. Reports have a 128 KiB compact JSON budget, with reserved room for summary metadata. Reaching a report limit or the shared 8,192-glyph/131,072-outline-command diagnostic budget stops further work and sets `complete:false` and `stopped_at_limit:true`. Counts describe attempted checks; they are not a total inventory of unexamined issues. Fix reported problems and rerun, or inspect a specific retained document. Existing document/resource/algorithm limits still apply. Font caches are released before descending into nested snapshots.

## Prepare exact delivery

```json
{"command":"document.preflight","document":{"session_id":"poster","revision":3},"output":{"file_name":"poster-v3.png","format":"png","scale":1}}
```

The `output` object is the same as `document.publish`: destination root/name, format, scale, optional artboard/bleed selection, render quality, image options, metadata policy and PDF options. A workspace supplies the default output root; otherwise provide its existing absolute directory. Supported options and losses are determined by the real export path, not an independent checklist or estimated encoder.

On success, `ready:true` includes the canonical document hash and `prepared_output`, the normal publication receipt with `created:false`: exact byte length and SHA-256, destination, source revision, output settings, profiles, loss declarations and applicable format metadata. It returns no encoded artifact payload and creates no temporary file, destination or directory. Every codec still performs its normal preparation/encoding work and obeys its original limits; preflight is not a cheap static-only test.

On preparation failure, `ready:false` includes the same structured error as actual publication plus repair guidance. Examples include missing resources, strict overflow, unsupported semantics, size/work limits, absent alpha policy, wrong filename extension, a missing output directory or an existing destination. It reports the first failure from the shared preparation path. Ordinary publication error precedence and no-overwrite behavior remain unchanged.

A ready result is an observation, not a reservation or commit ticket. Preflight does not test writes or hard-link support. Permissions, disk capacity, resource changes, competing publishers and cancellation can affect a later attempt. Publish the same pinned revision/options, then check the actual publication receipt; its hash/bytes should match when the inputs are unchanged. Session publication also adds session identity and observed revision fields. Durable publication receipt recovery is a separate readiness requirement.

## Repair and verify

1. Read check/preflight diagnostics and inspect the affected object, resource or schema.
2. Keep the original source and propose an explicit repair with `session.dry_run`. For resources, a verified alternate store and a resource-binding action can restore pinned identities without changing or overwriting original media.
3. Request `include_document:true` and check/preflight the hypothetical document with `proposed_resources`. Review its focused preview and structural changes.
4. Apply the unchanged action through `session.apply_proposal`, then check the pinned saved revision and publish to a new destination.

`tests/test_checks_preflight.py` seeds strict text overflow, retained story tails, missing fonts, corrupt images and invalid font axes. It verifies located guidance, explicit skips/limits, nested/override checks, read-only file identities, exact predicted/actual receipts across multiple formats, destination races, cancellation, checked repairs, untouched text/artwork/source files and historical revisions. Existing publication interruption/concurrency tests also cover the shared preparation refactor. These are scripted correctness checks; actual model trials and the complete readiness audit remain separate.
