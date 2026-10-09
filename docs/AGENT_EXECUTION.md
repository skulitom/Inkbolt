# Agent execution, comparisons and output publication

`volume.inspect` reads original dimensional controls and projected faces. Atomic `volume` and `volume_expand` edits share revision checks, safe retries and durable undo. Built-in CPU materials require no model or network service; isolated offline results are independently verified. See [VOLUMES.md](VOLUMES.md).

`appearance.inspect` is read-only. Appearance editing, independent expansion and explicit pixel baking use ordinary `document.edit` or `session.apply` with revision checks, retry receipts and undo. Baking returns a new embedded resource; create-only publication is a separate explicit action. See [APPEARANCE.md](APPEARANCE.md).

`sequence.import`, `sequence.inspect`, `sequence.open` and `sequence.export` share the CLI/MCP adapter. APNG publication uses the existing create-only flow; imports may retain already verified cache entries on later failure. See [SEQUENCES.md](SEQUENCES.md).

The Rust library, one-request JSON CLI and MCP stdio adapter share the same validated engine. There is no listener, account, telemetry or external application dependency. A caller's local process permissions determine which explicit input/store/output paths can be accessed; this interface is not a filesystem sandbox.

## Compare before committing more work

Use [focused previews and contact sheets](FOCUSED_PREVIEWS.md) to review regions, selected objects and standalone artboards. Views carry exact document identities and world/pixel or world/sheet maps. A dry-run `proposed_document` can be previewed before its checked proposal is committed.

`document.diff` accepts `before`, `after`, optional `before_resources`/`after_resources`, `compare_pixels` (false by default) and `control`. Both snapshots must have the same ID and document kind. Normal request/document bounds apply; for two large saved documents use `session.diff` with `session_root`, `session_id`, `from_revision`, `to_revision` and optional `compare_pixels`/`control`.

The result reports metadata changes, stable-ID additions/removals/changes, changed item fields, before/after item hashes, sibling position, world transforms, geometry bounds, effective visibility/locks, and resource descriptor hashes. Changed ancestors can produce derived changes in otherwise identical child items. Inline raster changes include exact changed-pixel count, end-exclusive bounds and maximum absolute RGBA8 channel difference when dimensions match. Resized inline rasters report dimensions instead of pretending there is a one-to-one pixel correspondence.

Optional rendered comparison uses scale 1 and requires equal canvas sizes; unsupported size comparisons fail explicitly while structural comparison remains available. Both snapshots resolve their respective saved resource roots. Result geometry bounds exclude clipping/strokes; rendered pixel differences compare working-sRGB RGBA8 array positions before output-profile conversion, without world-origin alignment. Revision alone is not a content change. This comparison is not an executable patch and does not enumerate every glyph/control-point difference separately.

Use [visual comparisons](VISUAL_COMPARISONS.md) (`document.diff.preview` / `session.diff.preview`) for explicit shared-grid alignment, resized extents, focused regions/items/artboards, before/after PNGs, a thresholded change mask and mapped change coordinates. Original identities, profiles, rendering settings and structural differences remain explicit; visual equality alone does not establish document equality.

Session comparisons capture both committed states in one read transaction, release its lock, then perform potentially expensive rendering. Later edits cannot alter the captured states. Output includes observed_current_revision. Missing revisions fail with REVISION_NOT_FOUND; references remain subject to history integrity checks.

## Publish a complete output without overwriting files

`document.preflight` accepts the same document, resources and output options and runs the shared preparation/encoding path without writing or reserving files. It reports either located repair guidance or the exact expected output receipt with `created:false`. Preflight does not guarantee later write permission, disk capacity or exclusive destination ownership. See [checks and preflight](DOCUMENT_CHECKS.md).

`document.publish` accepts document, optional resources, output, optional receipt and control. `session.publish` replaces document/resources with session_root, session_id and expected_revision. A new export requires the current head to match before capturing a snapshot; subsequent edits do not affect that export. A committed durable retry returns its original result without recapturing the source. Publication does not change session history.

The output object requires:

```json
{"output_root":"C:/Exports/design","file_name":"diagram.png","format":"png","scale":1}
```

The explicit absolute root must already exist and support create-only hard links. file_name is a portable single filename using ID characters, at most 128 bytes, without reserved device names or a trailing dot. Its extension must match PNG (.png), APNG (.png/.apng), JPEG (.jpg/.jpeg), TIFF (.tif/.tiff), SVG (.svg) or snapshot (.json). Paths, alternate streams, traversal and reserved temporary names fail. Optional artboard_id selects one independently clipped local artboard; include_bleed expands its viewport. Optional image_options inside output records JPEG quality/chroma/matte or TIFF lossless compression; see [IMAGE_IO.md](IMAGE_IO.md). Artboard publication accepts PNG/JPEG/TIFF/SVG; publish the full snapshot to retain editable document context.

The engine completes rendering first, writes at most 32 MiB to an exclusively created temporary file, flushes/closes it, and creates the destination hard link atomically. Existing files, directories, symbolic links and hard-link aliases are never replaced, even if bytes happen to match. OUTPUT_EXISTS instructs the agent to choose a new filename. Concurrent publishers have one winner. Render failures, prepublication cancellation and deadlines expose no partial destination.

Success returns path, source document/revision, board settings, format, media type, byte count, SHA-256 and export loss diagnostics. Publication is the commit point: late cancellation does not delete the completed file. A lost response can leave the outcome uncertain; inspect the chosen file and compare it with the expected export before choosing another name. Without the optional `receipt` argument, this command does not maintain a durable output ledger. Add `receipt:{receipt_root,request_id}` for prepared output recovery and idempotent retries through `publication.receipt` and `publication.recover`; see [durable publication receipts](PUBLICATION_RECEIPTS.md). It never treats an existing file as permission to overwrite.

Process termination before publication can leave a complete unpublished `.inkbolt-output-*.tmp` file. Other processes do not automatically delete it. Cancellation/error in a live process removes its own temporary file. Tests terminate an owned writer after flush and check retry behavior, cancellation/deadline cleanup and late cancellation after publication. Power-loss durability relies on the local filesystem and operating system; the process-interruption checks do not simulate failing hardware.

Three publication examples, using a document already returned by the engine:

```json
{"command":"document.publish","document":"<document object>","output":{"output_root":"C:/Exports/design","file_name":"diagram.svg","format":"svg"}}
```

```json
{"command":"session.publish","session_root":"C:/Work/sessions","session_id":"design","expected_revision":4,"output":{"output_root":"C:/Exports/design","file_name":"icon.png","format":"png","artboard_id":"icon","scale":2}}
```

```json
{"command":"session.publish","session_root":"C:/Work/sessions","session_id":"design","expected_revision":4,"output":{"output_root":"C:/Exports/design","file_name":"editable.json","format":"snapshot"}}
```

Replace the illustrative document placeholder with the actual object. Preview/export without file publication remains available through document.render/document.export/artboard.export.

## MCP stdio

For new agent connections launch `inkbolt mcp --tools core`; existing clients may retain `inkbolt mcp` or select `--tools full`. The compact catalog lists everyday tools and `inkbolt_run` for every engine command, with focused `schema.lookup` discovery. See [agent discovery](AGENT_DISCOVERY.md) for schemas, budgets and measurement. It reads one UTF-8 JSON-RPC object per newline and writes only protocol messages to stdout. The pinned supported protocol is 2025-11-25. Initialization negotiates that version, then the client sends notifications/initialized. An unsupported requested version receives the supported version so the client can decide whether to continue. No HTTP transport or callback server is introduced.

In full mode every engine command has a discoverable tool named `inkbolt_` followed by its command with dots replaced by underscores, for example inkbolt_session_apply. Tool arguments are the command's fields without command. Input schemas are generated from the Rust request types with local reachable definitions; compact mode explicitly defers large shared types to lookup. Nullable types use equivalent anyOf alternatives for client portability. Duplicate JSON keys and unknown engine fields fail. tools/list uses deterministic pages of eight tools and mode-specific opaque nextCursor values. The catalog declares side-effect annotations and forbids task-augmented execution.

The full catalog follows `capabilities.commands`; compact mode lists the everyday tools and a dispatcher. `inkbolt_svg_import` creates a new editable vector document from bounded inline SVG text or an explicit local file, including bounded local gradient/clip definitions, returning source hashes, ID mapping and normalization losses. See [SVG import](SVG_IMPORT.md). `inkbolt_document_query` discovers editable objects by type/shape/bounds and returns optional revision-scoped path anchors. Use its source revision for an edit conflict check; rediscover after a topology change. The default lock filter includes affected descendants, and explicit inspection of locked items remains available. Shape and path contracts are documented in [PATHS.md](PATHS.md). `inkbolt_document_measure` returns reproducible composite histograms and samples with explicit selection/alpha weighting; see [ADJUSTMENTS.md](ADJUSTMENTS.md).

Tool results include a structuredContent envelope (`ok` plus result or error) and isError. Optional response_format is json (default), markdown or preview. JSON/Markdown retain matching full text and structured envelopes; PNG exports also include native image blocks, limited to four images and 8 MiB of base64 preview data. Preview uses summary text and one PNG payload location with explicit references, retaining overflow bytes in structured content. See [inspection and preview transport](AGENT_INSPECTION.md) for reconstruction and supported image locations. The output schema describes the common envelope; command-specific result semantics remain in the engine documentation.

Methods: initialize, ping, tools/list, tools/call, notifications/initialized and notifications/cancelled. Unknown methods fail explicitly. Prompts, resources, sampling, elicitation, protocol tasks, progress notifications and HTTP are not advertised. The protocol implementation follows the public [base specification](https://modelcontextprotocol.io/specification/2025-11-25/basic), [stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports), [lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle), [tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) and [cancellation](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/cancellation) contracts. No SDK implementation is copied into Inkbolt.

The reader stays responsive while one worker executes tools in arrival order. At most eight tool calls may be outstanding. Protocol IDs must be unique within the connection (string up to 256 UTF-8 bytes or integer within the exact JSON-safe range). After 4096 request IDs, reconnect; durable session request IDs continue to work across connections. A message is limited to 16 MiB + 16 KiB of protocol overhead; normalized engine arguments remain capped at 16 MiB. Responses are capped at 96 MiB. These are storage/transport ceilings, not targets for model context use.

Each tool gets a 60-second cooperative deadline. Request control options can shorten it and add a caller-owned cancellation marker. notifications/cancelled sets the shared token and suppresses the response; it never promises to undo an already committed mutation. On EOF, outstanding tokens are cancelled and the worker exits after bounded work reaches its checks. Session receipts recover uncertain editing outcomes. Import publication remains bounded but cannot be forcibly interrupted; read-only rendering checks cancellation before and after work. Edit batches, verification and file publication have finer cooperative checks. No async protocol-task or hard real-time guarantee is implied.

Three tool-call examples:

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"inkbolt_capabilities","arguments":{}}}
```

```json
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"inkbolt_document_create","arguments":{"id":"icon","kind":"vector","width":128,"height":128}}}
```

```json
{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"inkbolt_session_diff","arguments":{"session_root":"C:/Work/sessions","session_id":"design","from_revision":0,"to_revision":3,"compare_pixels":true}}}
```

An independent standard-library client tests framing, handshake, pagination, schemas, errors, cancellation and a complete editing/export/undo workflow. The official MCP Inspector 2.9.0 CLI also checks initialization, all tools, strict schema portability and successful/error tool calls over stdio. Its packages stay in the external development cache and are not runtime dependencies. Ten fixed read-only agent questions live in examples/mcp_evaluation.md; tests seed original artwork, solve each through MCP and compare the exact answers. These checks validate tool workflows, not an LLM model's planning quality.

`inkbolt_channel_export` returns a saved scalar plane as grayscale PNG or a named-ink alternate-color preview, with identity metadata and explicit fidelity limits. Channel edits and image-guided selection run through the existing atomic edit tools; see [CHANNELS_AND_SELECTIONS.md](CHANNELS_AND_SELECTIONS.md).

`inkbolt_document_boolean` returns combined geometry without changing source items. Inspect empty-result, tolerance and topology diagnostics, then materialize a nonempty result with an atomic edit. Equivalent noncollinear curve pieces share exact coincidence normalization. Curved results require a simultaneous-deformation certificate; unresolved contacts return an explicit error without partial geometry. Supported rational contacts split exactly before evaluation; general algebraic parameter/contact support remains in progress. See [BOOLEANS.md](BOOLEANS.md).

`inkbolt_svg_import` also imports single-line editable text with explicit font_bindings and font_root. Fonts are hash-pinned and license-verified; missing bindings/glyphs and unsupported text semantics fail. Persist the returned snapshot with session.create and resources.font_root, then use ordinary text edits, differences and undo. See [SVG_IMPORT.md](SVG_IMPORT.md).

`asset.import` accepts explicit RGB ICC conversion through color_policy=convert_srgb and optional input_profile. The existing edit tools accept output_profile association/clearing; PNG/JPEG/TIFF artifacts and publication receipts report the exact embedded profile hash. Working previews remain sRGB. Profile contracts and strict failures are in [COLOR_PROFILES.md](COLOR_PROFILES.md).

Metadata uses the same bounded document/edit/export contracts over MCP. Export policies retain public descriptions or strip them, with optional resource manifests and reproducible provenance. Snapshot defaults retain private working records; image/SVG delivery excludes private maps. Imported descriptions never create resource paths or establish trusted authorship. Publication receipts identify the applied policy and metadata envelope hash. See METADATA.md.

Use `inkbolt_mesh_inspect` to check knot placement, smooth derivatives, Jacobians and inverse geometry before editing a mesh. `mesh_knot` in ordinary or durable edit batches changes interior offsets and color/alpha atomically. Keep a snapshot for editing and review `mesh_textures`/losses when publishing SVG. See [MESHES.md](MESHES.md).

For curved labels, set the text frame `path`, inspect using `inkbolt_text_inspect`, then use the ordinary edit/history/publication tools. Source text and baseline remain editable in snapshots; SVG carries placed outlines and `text_paths` diagnostics. Inspect `path.drawn` for midpoint-clipped glyphs. No tool, transport or dependency was added. See [PATH_TEXT.md](PATH_TEXT.md).

`inkbolt_image_trace` is a read-only source conversion tool. Inspect its color/topology diagnostics and classification error before accepting the returned vector document. Retain the source and provenance for retracing, use a session for subsequent path/paint changes, and publish new outputs explicitly. See [TRACING.md](TRACING.md).

`inkbolt_brush_inspect` returns deterministic placement/settings without mutation. Use `brush_stroke` in a revision-checked document/session edit, inspect its changed-pixel receipt, then preview and publish. Keep the starting snapshot and request for replay; session undo/retry preserve outcomes. See [PIXEL_BRUSHES.md](PIXEL_BRUSHES.md).


Recovery contracts for sessions, publications, jobs and resource imports are inventoried in [recovery acceptance](RECOVERY_CONTRACTS.md). Cache imports retry by rereading unchanged original sources and verifying existing immutable blobs; only the documented session/publication/job commands retain historical request outcomes. Cancellation and partial-cache boundaries are explicit there.
