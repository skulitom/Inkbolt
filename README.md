# Inkbolt

An original local vector and raster editing engine for agents. Cutbolt handles time; Inkbolt handles paths, pixels and layered documents. Use the Rust library, structured JSON CLI or MCP over stdio. No listener, account, telemetry or external editing application is required at runtime.

**Engine scope: 161/167 independently verified checkpoints (96.41%).** Six checkpoints remain open. This bounded capability score does not measure production readiness or remaining effort. See the [implementation report](docs/IMPLEMENTATION.md) and [feature registry](docs/features.json).

Agent usability is a separate [readiness workstream](docs/AGENT_READINESS.md). Compact discovery, focused schemas, workspace defaults, pinned saved/file references, compact session responses and [paged inspection](docs/AGENT_INSPECTION.md) reduce repeated context. [Focused previews and contact sheets](docs/FOCUSED_PREVIEWS.md) include exact coordinate maps; [visual revision comparisons](docs/VISUAL_COMPARISONS.md) add aligned images and change masks. MCP preview format sends each PNG payload once. [Document checks and export preflight](docs/DOCUMENT_CHECKS.md) support explicit repairs. Durable jobs, larger raster workloads and complete readiness evidence remain on that plan.

## Start locally

Build with Rust/Cargo. Development verification also uses Python 3.11+. Dependencies are locked in Cargo.lock and remain in the external package cache.

```powershell
cargo build --locked
.\target\debug\inkbolt.exe examples/create-vector.json
.\target\debug\inkbolt.exe examples/create-raster.json
.\target\debug\inkbolt.exe mcp --tools core
```

For an MCP client, use [the configuration example](examples/mcp-config.json) with your executable path. The compact catalog exposes everyday tools and a dispatcher for every engine command. Existing clients can keep `inkbolt mcp` or explicitly select `mcp --tools full`. See [discovery and schemas](docs/AGENT_DISCOVERY.md).

Add `--workspace C:\Work\Graphics` before `mcp` or a request file to select an existing workspace with default session/resource stores. Snapshot arguments can reference an exact saved revision, for example `{"session_id":"poster","revision":3}`. See [workspaces and references](docs/AGENT_WORKSPACE.md) for path, resource and compatibility rules.

Set `response_mode:"compact"` on session creation, reads, edits and receipt recovery to receive pinned references and summaries. Full responses remain the default; see [compact responses](docs/AGENT_RESPONSES.md).

Send one JSON request on stdin, or pass one request file. Discover one operation without loading the complete schema:

```json
{"command":"schema.lookup","name":"operation","select":"transform"}
```

Success is `{"ok":true,"result":...}` with exit code 0; failure is `{"ok":false,"error":{"code":"...","message":"..."}}` with exit code 1. `capabilities` reports detailed limits; `schema` retains the complete request schema; `implementation.status` returns the checkpoint registry.

## Editing workflow

1. Create or import a document with explicit color and resource policies.
2. Inspect objects, geometry and resources before building an atomic edit batch.
3. Save a session for revisions, durable retry receipts, grouped undo/redo and named snapshots.
4. Use a [session dry run](docs/SESSION_PROPOSALS.md) to inspect predicted changes and previews, then apply its checked proposal.
5. Review [focused views or a contact sheet](docs/FOCUSED_PREVIEWS.md), compare and [preflight the result](docs/DOCUMENT_CHECKS.md), then publish to a new destination.

Snapshot edits and ordinary exports return data. `document.publish` and `session.publish` write complete outputs without overwriting existing files. Image/font imports preserve source files and publish content-addressed copies to explicit local stores; fonts require retained license text. See [agent commands](docs/AGENT_INTERFACE.md), [sessions](docs/SESSIONS.md), [publication and comparisons](docs/AGENT_EXECUTION.md), and [runnable examples](examples/README.md).

## Current boundaries

The engine covers vector geometry, typography, artboards, retained raster edits, masks, effects, color, print preparation and bounded interchange. Each capability has specific limits and unsupported cases; the registry's verified status applies to those exact acceptance criteria.

The standard vector profile holds 256 items; an explicit large-vector profile holds 8,192. Inline mutable pixel storage is limited to 65,536 pixels, and rendered output to 1,048,576 pixels. Storage allowances do not increase independent processing budgets. See [large documents](docs/LARGE_VECTOR.md) and capability reporting before selecting a workload.

Sessions retain external resource bindings, not a self-contained resource archive. History has explicit limits and no silent eviction. Live backup/migration, persistent render jobs and production-sized raster editing remain readiness work. Unknown semantics fail explicitly.

## Development and provenance

Read [architecture](docs/ARCHITECTURE.md), [roadmap](docs/ROADMAP.md), [agent readiness](docs/AGENT_READINESS.md) and [research boundaries](docs/RESEARCH.md) before extending behavior. Historical feature updates are retained in [implementation history](docs/PROGRESS_HISTORY.md).

Required checks:

```powershell
cargo fmt --check
cargo clippy --locked -- -D warnings
cargo test --locked
python tools/verify.py
python tools/check_repo.py --staged
```

`python tools/verify.py --jobs 4` optionally runs the same Python modules in isolated concurrent processes and checks the complete discovery count. Serial execution remains the default. Concurrent verification timings are not performance benchmarks.

The original source, contracts and synthetic fixture generators belong here. Application-specific research and evidence remain in the external private root. Configure each new checkout with its external research directory and private content policy using `tools/setup_private.py`; hooks and policies do not transfer through cloning. Both candidate and staged-byte repository checks remain mandatory before commits. They supplement provenance review and do not prove originality.

Original Inkbolt code is [MIT licensed](LICENSE). Dependencies retain their licenses and notices; see [dependencies](docs/DEPENDENCIES.md) and [third-party notices](THIRD_PARTY_NOTICES.md). Never commit third-party binaries, copied implementation, original application assets or raw private research.
