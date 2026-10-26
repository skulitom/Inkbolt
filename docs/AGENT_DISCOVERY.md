# Agent discovery

See the generated [limit reference](LIMITS.md) for centralized resource ceilings.

Current source builds offer `inkbolt mcp --tools essentials` for new agent
connections: ten tools within a 24 KiB tool-array budget, including focused
lookup and the complete dispatcher. The v0.82.0 release uses `--tools core`,
which lists twenty-one everyday tools plus `inkbolt_run` within 96 KiB.
`inkbolt mcp` and `--tools full` retain the full per-command catalog. All modes
use the same typed executor, editing semantics, output envelopes, images,
cancellation and session receipts. Catalog mode changes discovery only. Use the
separate [response mode](AGENT_RESPONSES.md) to shorten durable session replies
and [paged inspection/preview format](AGENT_INSPECTION.md) for focused reads.

Essentials directly lists `session.create`, `session.apply`,
`document.inspect.page`, `document.preview`, `document.check`, `session.publish`,
`asset.import`, `font.import`, `schema.lookup` and `inkbolt_run`. Create a blank
document, choose a preset or import artwork through the dispatcher before saving
it as a session. Other operations, including dry runs, receipts and history,
remain reachable through that same dispatcher.

Essentials defers larger `action`, `options` and `output` trees. Their
`x-inkbolt-schema` supplies a command name and working `select`; use those exact
values with `schema.lookup`. Required top-level fields, scalar choices, defaults
and full pinned-document/file alternatives remain visible. Generated titles and
repeated dialect annotations are omitted; the [MCP tool specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools#tool)
defaults these schemas to JSON Schema 2020-12. Workspace path rules
appear once per tool. Smaller discovery is not yet a measured model-efficiency
claim; see the [evaluation gate](DEVELOPMENT_STATUS.md#w52-essentials-catalog-implementation-and-evaluation-gate).

The core catalog covers document creation, inspection, object queries, edits and previews; session creation, reads, edits, dry runs, checked proposals, receipts, history, comparisons and publication; image/font import; and focused schema lookup. Specialist commands remain available through `inkbolt_run`:

```json
{"name":"inkbolt_run","arguments":{"command":"document.export","arguments":{"document":"<snapshot object>","format":"svg"}}}
```

The inner arguments are ordinary engine fields without `command`. Optional `response_format` belongs to the outer arguments. The dispatcher is conservatively annotated as potentially mutating; individual commands retain their actual effects. Unknown commands, recursive dispatch, unexpected fields and malformed nested arguments fail before execution. It cannot bypass revision checks, resource validation, locks, retries or create-only publication.

All catalogs retain deterministic eight-tool pagination. The smaller catalogs
start with `inkbolt_schema_lookup` and `inkbolt_run`, so their first page provides
access to every command and its arguments. Remaining compact tools and the full
catalog use alphabetical name order. Capabilities report the compact entry
points in `agent_discovery.mcp_compact_first_tools`.

Cursors belong to their catalog mode and order version. Compact cursors now use
`inkbolt-tools-core-v2:`; essentials uses `inkbolt-tools-essentials-v1:`.
Cross-mode and old compact cursors fail explicitly rather than resuming
at a different tool. Full-catalog cursors are unchanged. Treat cursors as opaque
and begin discovery without one on a new connection. Discovery mode and order
are fixed for the lifetime of the process; no environment variable silently
changes an existing client.

## Focused schemas

For CLI discovery, `inkbolt --help` (or `-h`) returns one successful JSON envelope
with compact usage, request examples and the focused lookup path. It does not
read stdin or execute those examples. `--workspace ABSOLUTE_DIRECTORY` may precede
the help flag, with the usual existing-directory validation. Capabilities report
the supported flags in `agent_discovery.cli_help_arguments`.

Current source builds also include `workspace_defaults` in help. These paths are
relative to a workspace explicitly selected with `--workspace`; help never
selects or creates one. Image and font `store_root` defaults appear separately
as `image_store_root` and `font_store_root` in this description.

The schema index's `example_queries` lists focused examples for font import,
session creation/review, an empty document, text content and text/transform/boolean
operations. Those lookups include `example` beside the schema or outline, with
`kind`, `value`, `requires` and `usage`. Each complete example is bounded to 2 KiB.
`schema_bytes` continues to measure only the validation schema. Nested routes
to the same selected type return the same example. Discovery never executes it.

Request examples need the declared workspace, original input files and unused
or existing session IDs. Content and operation examples are fragments with
explicit font/item prerequisites. Bind the imported font descriptor in
`document.fonts` and use that ID in the text style. A text operation replaces
the complete frame: copy the existing frame and change only intended fields
when repairing artwork. These examples cover a focused subset; they do not
imply every operation has a recipe or establish model-efficiency gains.

`schema.lookup` is a read-only CLI/library/MCP command. The original argument-free `schema` command still returns the complete engine schema unchanged in shape.

```json
{"command":"schema.lookup","name":"index"}
{"command":"schema.lookup","name":"document.create"}
{"command":"schema.lookup","name":"operation"}
{"command":"schema.lookup","name":"operation","select":"transform"}
{"command":"schema.lookup","name":"operation","select":"reorder"}
{"command":"schema.lookup","name":"document.edit","select":"Operation","full":true}
{"command":"schema.lookup","name":"session.apply","select":"Action/edit"}
{"command":"schema.lookup","name":"session.apply","select":"Action/edit/Operation/transform"}
```

`name` accepts any engine command or a shared type alias: `document`, `operation`, `action`, `item`, `content`, `geometry`, `paint`, `resources`. Command schemas describe the shared JSON interface without the command tag; they do not include MCP-specific text presentation fields. Top-level snapshot arguments include pinned saved-revision and hashed-file alternatives, and supported session commands include `response_mode`. A configured workspace adjusts defaultable roots before outlines and sizes are calculated; see [workspaces and references](AGENT_WORKSPACE.md). Shared type aliases and the legacy full schema retain the typed inline-snapshot contract.

Results report `detail`, `name`, `select` and the serialized `schema_bytes`. Schemas through 12 KiB return `detail:"full"` and `schema`, including every referenced definition. Larger schemas return `detail:"outline"`, fields, tagged variants and reachable definition names. An outline is not a validation schema. `full:true` always requests the complete selected schema. The index is already complete and rejects `select` and `full:true`.

`select` chooses a variant of the named root (for example `transform`) or a
reachable definition. Separate components with `/` to follow nested selections.
Each outline variant supplies its complete next `select` value; keep the same
`name`. For example, the `Action` outline under `session.apply` advertises
`Action/edit`. Its operation can then be selected with
`Action/edit/Operation/transform`. Definition names remain directly selectable
from the named root. Shared aliases such as `action` and `operation` remain
available; generated definition names come from the current schema.

Unknown names/selectors still return `SCHEMA_NOT_FOUND` without echoing unknown
text. Error `details.field` identifies `name` or `select`, and
`details.schema_lookup` is a complete working request for the available choices.
An unambiguous case correction or nested variant can also produce
`details.suggested_lookup`; the caller decides whether to use it. Ambiguous
variants are never chosen automatically. Empty components and definitions not
reachable from the current selection fail. Names and entire selector paths are
limited to 128 UTF-8 bytes. Selection and error recovery never execute edits.

`reorder.index` is the final zero-based position among items with the same parent,
including the moved item; root items are siblings. For two children, valid indexes
are 0 and 1 regardless of their offsets in `document.items`. Reorder preserves
parentage and does not prescribe the flat array's global storage order. The focused
operation schema explains this scope, and an out-of-range error reports the sibling
count. Inspect parent IDs and sibling order before choosing the index.

Compact listings defer large document, operation, item, content, geometry and paint definitions. Their descriptions and `x-inkbolt-schema` annotations identify the lookup. Deferred paint accepts both solid RGBA arrays and paint objects. These intentionally abbreviated listings do not replace runtime validation: the shared Rust request types still reject unsupported semantics and unknown fields.

## Measurement and evidence

`python tools/measure_discovery.py` reports catalog and focused-schema sizes from an existing local build. It records executable and source fingerprints, source changes during measurement, request counts and elapsed discovery time. Use `--output <new-external-file.json>` to retain a create-only report outside the repository. It never builds, edits documents or awards checkpoint credit. Matching source identity across a run does not prove that a supplied executable was compiled from those sources; record the build separately.

The 9 October 2026 planning probe of the previous local build measured 68 tools over nine pages, 2,769,677 catalog wire bytes, 85,548 capability-response bytes and 165,107 full-schema-response bytes. This is a historical observation, not evidence of agent task success or an independently reproducible old-build benchmark.

`tests/agent_discovery.rs` checks the compact byte budget, reachability, reference closure, outline/selection behavior and advertised-command agreement. `tests/test_agent_discovery.py` exercises independent CLI/MCP processes, direct/routed pixel results, invalid inputs, durable replay, stale revisions, undo and create-only publication. Existing MCP tests continue to cover protocol framing, duplicate keys and cancellation. Real model-driven task benchmarks remain separate work in [agent readiness](AGENT_READINESS.md).
