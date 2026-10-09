# Paged inspection and preview transport

`document.inspect.page` reads a bounded selection without returning a complete document or inventory. It is available through Rust, JSON CLI, the core MCP catalog and the dispatcher. Legacy `document.inspect`, `document.query` and `document.select` retain their existing behavior.

```json
{"command":"document.inspect.page","document":{"session_id":"poster","revision":3},"options":{"limit":32,"view":{"collection":"items","fields":["name","content_type","bounds"]}}}
```

Use the workspace session default, or include an explicit session root in the reference. Inline documents and hashed snapshot file references work as well. The command supports ordinary cancellation/deadline controls and never edits the document.

## Collections and fields

`options.view` defaults to the items collection. Item and resource `ids` are optional; an empty list means the whole collection. Unknown or duplicate IDs reject explicitly. Selected IDs retain collection order, independent of the order supplied by the caller.

| Collection | Selection | Records and order |
| --- | --- | --- |
| `items` | Optional `ids`, `types`, `fields` | Item IDs and original indices, in document storage order; includes hidden and locked items |
| `assets` | Optional `ids` | Dimensions, hash, storage kind and provenance, in ID order; no pixel bodies |
| `fonts` | Optional `ids` | Font and license hashes, face index and byte count, in ID order; no font bodies |
| `anchors` | Required item `id` | Path endpoints and incoming cubic handles, in component/command order |

Every item record includes `id` and `index`. Fields default to `name`, `content_type`, `hierarchy`, `visibility`, `locks` and `bounds`. An explicit empty field list returns IDs and indices only.

| Field | Added values |
| --- | --- |
| `name`, `content_type` | Item label or content kind |
| `hierarchy` | `parent`, `clip_to`, `sibling_index` |
| `visibility` | Own and effective visibility |
| `locks` | Own/effective locks and whether an edit is blocked by affected locks |
| `transform` | World transform |
| `bounds` | Unclipped world geometry bounds; excludes stroke/effect expansion; text uses its frame |
| `geometry` | Retained vector/work-path geometry, or null |
| `style` | Opacity, fill opacity, coverage, blend, effects, filters, vector stroke and vector/fill paint; null where inapplicable |
| `metadata` | Original descriptive record, including explicitly requested private fields |

Compound work-path bounds disclose their conservative operand-union semantics. Anchors cover explicit path geometry and path leaves of compound work paths; other geometry/content yields no path anchors. They retain command/contour/anchor indices, local/world coordinates and cubic handles. Compound records also include the original operand address. They do not approximate primitive shapes into paths. Topology edits can renumber addresses; use the same expected revision when editing.

Resource pages are inventories of saved descriptors. They do not open external stores or certify that referenced bytes still exist; use `asset.verify` or `font.verify` for that. Resource users, text layout, retained-source details and other specialist diagnostics remain in their existing inspection commands.

## Page and cursor contract

The limit defaults to 32 and accepts 1 through 128. Each result is at most 32 KiB of compact JSON. The record allowance is 28 KiB, with the remainder reserved for metadata. A page may contain fewer than the requested number of records to fit that allowance. A single oversized record returns `INSPECTION_RECORD_TOO_LARGE`; remove large selected fields or read path controls through the anchors collection. No values or geometry coordinates are silently truncated.

Results include `records`, `offset`, `returned`, `total`, `order`, document identity/revision, `document_sha256` and `next_cursor`. Repeat the same document and options with `cursor` set to the returned token; stop when `next_cursor` is null. The digest covers the complete canonical typed document, not the input file's whitespace or byte representation. The cursor binds that digest, the view and the page limit. Changed content rejects with `STALE_CURSOR` even if its ID/revision was reused. Invalid offsets reject with `INVALID_CURSOR`. Cursors are continuation tokens, not authorization credentials.

The engine still reads, validates and hashes the full bounded snapshot on each request. It collects matching IDs/indices or borrowed path slices, then evaluates selected page fields, with at most one extra record for byte admission. It does not construct the legacy complete inspection result and trim it afterward. This reduces returned data and inspection projection work; it does not claim incremental document loading or constant-memory validation.

## One location for image payloads

MCP calls accept `response_format:"preview"` alongside existing `json` (default) and `markdown`. For `inkbolt_run`, put it on the outer arguments:

```json
{"name":"inkbolt_run","arguments":{"command":"document.export","arguments":{"document":{"session_id":"poster","revision":3},"format":"png"},"response_format":"preview"}}
```

Preview format returns a short text summary, structured metadata and at most four PNG image blocks totalling at most 8 MiB of base64 data. Image data is removed from its structured artifact when delivered in an image block. The artifact uses `encoding:"mcp_reference"` and a version-one `payload_ref` containing `kind:"content"`, the zero-based content-block `index`, original encoding, byte length and SHA-256. Identical encoded PNGs share that location.

When attachment count/bytes would exceed the limit, the payload remains once in its original structured artifact with `encoding:"base64"`. Later duplicates use `kind:"structured_content"` and a JSON pointer rooted at `structuredContent` to that original `data` string. The summary states how many unique payloads remain inline. Nothing is silently dropped, and smaller subsequent images can still fit the attachment budget.

To reconstruct an artifact, resolve its payload reference, remove `payload_ref`, and restore `encoding:"base64"` and `data`. Widths, profiles, loss statements, frame timing, hashes and all other engine metadata remain unchanged. Existing JSON/Markdown responses preserve their original full-envelope behavior. Preview format does not change engine execution, output bytes, session fingerprints or the shared CLI result.

Supported PNG locations cover document export, focused previews, contact sheets, artboard export, sequence frame export, channel export, proof previews/diagnostic masks/plates, native prepress plates, named-ink separations and session dry-run previews. Other formats/results remain complete in structured content with summary text. The adapter examines only known command output locations; it never interprets snapshot contents or metadata strings as image artifacts. This transport is separate from `response_mode:"compact"`, which projects saved session results in both CLI and MCP.

Independent process checks in `tests/test_paged_inspection.py` cover large inventories, fields, bounds, cursor invalidation, historical references, byte limits, path indices and compound placement. `tests/test_mcp_preview.py` reconstructs exact engine artifacts, independently checks pixels, and covers duplicate/overflow images, sequences, plates, diagnostics, errors and literal metadata. A Rust transport check covers the aggregate image-byte limit. These contract checks do not substitute for the model-driven tasks in [agent readiness](AGENT_READINESS.md).

`python tools/measure_inspection.py --output <new-external-report.json>` records full-versus-selected inventory traffic and legacy-versus-preview PNG wire bytes on original fixtures. It checks every ID/bound and reconstructs the exact original PNG artifact. Reports identify source/executable hashes and list actual call sizes and elapsed times. They do not measure model success, tokens, peak memory or controlled performance budgets.
