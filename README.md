# Inkbolt

Local graphics editing for AI agents.

Inkbolt gives agents structured tools to create and revise vector artwork,
raster images and layered documents. Build graphics, inspect the result, make
precise edits and deliver files while keeping the source editable.

Use it through a **JSON command-line interface**, **MCP over stdio**, or the
**Rust library**. The engine runs locally, with no account, network service or
telemetry. It works with any client that can use these interfaces; no particular
model is required.

## What you can do

- **Create graphics:** combine paths, text, images and artboards for diagrams,
  illustrations, layouts and screen assets.
- **Edit images:** work with layers, selections, masks, adjustments and retouching,
  with native-depth pixel storage for supported workflows.
- **Review changes:** inspect document structure, request focused previews,
  compare revisions and check output settings before delivery.
- **Keep work editable:** save sessions with revision checks, undo/redo,
  named snapshots and recoverable publication receipts.
- **Deliver files:** export supported artwork to PNG, TIFF, SVG and PDF,
  using explicit color settings and outputs that do not overwrite existing files.

Each workflow has documented limits. Unsupported input or output semantics
produce explicit errors; declared approximations and conversion losses are
reported to the caller.

## Get started

Install Rust with rustup, then build from the repository root. The checked-in
toolchain file selects the development compiler and Cargo.lock pins dependencies.

**Windows**

```powershell
cargo build --locked
.\target\debug\inkbolt.exe examples/add-svg.json
.\target\debug\inkbolt.exe mcp --tools core
```

**Linux and macOS**

```bash
cargo build --locked
./target/debug/inkbolt examples/add-svg.json
./target/debug/inkbolt mcp --tools core
```

The example returns editable artwork as JSON. The final command starts the MCP
stdio adapter for a client to connect to. See the [MCP configuration
examples](examples/mcp-config.json) and [runnable workflows](examples/README.md)
for previews, saved sessions and file delivery.

Run `inkbolt --help` for request examples. Agents can discover compact tool
summaries and request the schema for a single operation as they work. Workspace
defaults and saved revision references keep repeated requests small.

## Documentation

| Start here | Details |
| --- | --- |
| [Examples](examples/README.md) | Runnable graphics and image workflows |
| [Agent interface](docs/AGENT_INTERFACE.md) | Commands, requests and results |
| [Tool discovery](docs/AGENT_DISCOVERY.md) | MCP tools and focused schemas |
| [Workspaces and sessions](docs/AGENT_WORKSPACE.md) | Local resources and saved revision references |
| [Platforms](docs/PLATFORMS.md) | Windows, Linux, WSL and macOS coverage |
| [Capabilities and limits](docs/IMPLEMENTATION.md) | Verified behavior and links to feature contracts |

## Project status

Inkbolt is under active development. Core editing, CLI/MCP, sessions and durable
receipts have Windows, Linux and macOS verification. Background export jobs are
currently Windows-only. Broader interchange, larger raster workloads and agent
usability improvements are ongoing. Check the [resource limits](docs/LIMITS.md)
and relevant feature contract before choosing a workflow.

The [primary plan](FIX_PLAN.md) tracks development priorities.
[Benchmark results](docs/BENCHMARK_RESULTS.md) record agent evaluations and their
limitations separately from engine feature coverage.

For development, use Python 3.11+ and `python tools/verify.py` for focused checks
within a three-minute budget; use `--thorough` for milestone verification.
Public clones use `--public`. See the [development loop](docs/DEVELOPMENT_LOOP.md),
[architecture](docs/ARCHITECTURE.md) and [contribution boundaries](docs/RESEARCH.md)
for setup, testing and source requirements.

## License

Inkbolt is [MIT licensed](LICENSE). Dependencies retain their own licenses;
see [third-party notices](THIRD_PARTY_NOTICES.md).
