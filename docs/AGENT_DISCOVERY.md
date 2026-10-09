# Agent discovery

Use `inkbolt mcp --tools core` for new agent connections. It lists eighteen everyday tools plus `inkbolt_run`, within a tested 96 KiB catalog budget. `inkbolt mcp` and `inkbolt mcp --tools full` retain the full per-command catalog for existing clients. Both modes use the same typed executor, editing semantics, output envelopes, images, cancellation and session receipts. Catalog mode changes discovery only. Use the separate [response mode](AGENT_RESPONSES.md) to shorten durable session replies and [paged inspection/preview format](AGENT_INSPECTION.md) for focused reads and image delivery.

The everyday tools cover document creation, inspection, object queries, edits and previews; session creation, reads, edits, dry runs, checked proposals, receipts, history, comparisons and publication; image/font import; and focused schema lookup. Specialist commands remain available through `inkbolt_run`:

```json
{"name":"inkbolt_run","arguments":{"command":"document.export","arguments":{"document":"<snapshot object>","format":"svg"}}}
```

The inner arguments are ordinary engine fields without `command`. Optional `response_format` belongs to the outer arguments. The dispatcher is conservatively annotated as potentially mutating; individual commands retain their actual effects. Unknown commands, recursive dispatch, unexpected fields and malformed nested arguments fail before execution. It cannot bypass revision checks, resource validation, locks, retries or create-only publication.

Both catalogs retain deterministic eight-tool pagination. Cursors belong to their catalog mode and cannot be exchanged between modes. Discovery mode is fixed for the lifetime of the process; no environment variable silently changes an existing client.

## Focused schemas

`schema.lookup` is a read-only CLI/library/MCP command. The original argument-free `schema` command still returns the complete engine schema unchanged in shape.

```json
{"command":"schema.lookup","name":"index"}
{"command":"schema.lookup","name":"document.create"}
{"command":"schema.lookup","name":"operation"}
{"command":"schema.lookup","name":"operation","select":"transform"}
{"command":"schema.lookup","name":"document.edit","select":"Operation","full":true}
```

`name` accepts any engine command or a shared type alias: `document`, `operation`, `action`, `item`, `content`, `geometry`, `paint`, `resources`. Command schemas describe the shared JSON interface without the command tag; they do not include MCP-specific text presentation fields. Top-level snapshot arguments include pinned saved-revision and hashed-file alternatives, and supported session commands include `response_mode`. A configured workspace adjusts defaultable roots before outlines and sizes are calculated; see [workspaces and references](AGENT_WORKSPACE.md). Shared type aliases and the legacy full schema retain the typed inline-snapshot contract.

Results report `detail`, `name`, `select` and the serialized `schema_bytes`. Schemas through 12 KiB return `detail:"full"` and `schema`, including every referenced definition. Larger schemas return `detail:"outline"`, fields, tagged variants and reachable definition names. An outline is not a validation schema. `full:true` always requests the complete selected schema. The index is already complete and rejects `select` and `full:true`.

`select` chooses one variant of the named root (for example the `transform` operation) or a referenced definition listed in that root's outline. Selection never changes execution. If a selected definition is itself a large tagged union, use its shared alias to select a variant, or request its complete schema. Definition names come from the current schema generator; shared aliases are the supported discovery names. Unknown names or selectors return `SCHEMA_NOT_FOUND` without echoing their text. Names/selectors are limited to 128 UTF-8 bytes.

Compact listings defer large document, operation, item, content, geometry and paint definitions. Their descriptions and `x-inkbolt-schema` annotations identify the lookup. Deferred paint accepts both solid RGBA arrays and paint objects. These intentionally abbreviated listings do not replace runtime validation: the shared Rust request types still reject unsupported semantics and unknown fields.

## Measurement and evidence

`python tools/measure_discovery.py` reports catalog and focused-schema sizes from an existing local build. It records executable and source fingerprints, source changes during measurement, request counts and elapsed discovery time. Use `--output <new-external-file.json>` to retain a create-only report outside the repository. It never builds, edits documents or awards checkpoint credit. Matching source identity across a run does not prove that a supplied executable was compiled from those sources; record the build separately.

The 9 October 2026 planning probe of the previous local build measured 68 tools over nine pages, 2,769,677 catalog wire bytes, 85,548 capability-response bytes and 165,107 full-schema-response bytes. This is a historical observation, not evidence of agent task success or an independently reproducible old-build benchmark.

`tests/agent_discovery.rs` checks the compact byte budget, reachability, reference closure, outline/selection behavior and advertised-command agreement. `tests/test_agent_discovery.py` exercises independent CLI/MCP processes, direct/routed pixel results, invalid inputs, durable replay, stale revisions, undo and create-only publication. Existing MCP tests continue to cover protocol framing, duplicate keys and cancellation. Real model-driven task benchmarks remain separate work in [agent readiness](AGENT_READINESS.md).
