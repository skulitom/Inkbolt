# Inkbolt

Local graphics editing for AI agents.

Inkbolt lets agents create graphics, preview their work, make precise revisions
and export the result while keeping an editable source. Use it for diagrams,
illustrations, layouts and image assets.

It runs locally through **MCP over stdio**, a **JSON command-line interface**, or
the **Rust library**. There is no account, network service or telemetry, and no
particular AI model is required.

## What you can do

- **Build compositions** from vector shapes, text and images.
- **Revise artwork** with targeted edits, layers, masks and image adjustments.
- **Review and continue** using previews, saved sessions, undo/redo and revision
  comparisons.
- **Deliver assets** as PNG, TIFF, SVG or PDF within the supported workflows,
  preserving source files and refusing to overwrite existing outputs.

Agents can discover tools and request individual operation schemas as they work.
Unsupported features fail explicitly; approximations and conversion losses are
reported.

## Get started

Install Rust with rustup, then build from the repository root using the pinned
toolchain and dependencies.

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
adapter. See the [client configuration examples](examples/mcp-config.json), or
run `inkbolt --help` for command-line request examples.

## Documentation

| Start here | Details |
| --- | --- |
| [Examples](examples/README.md) | Runnable graphics and image workflows |
| [Agent interface](docs/AGENT_INTERFACE.md) and [tool discovery](docs/AGENT_DISCOVERY.md) | Commands, MCP tools and schemas |
| [Workspaces and sessions](docs/AGENT_WORKSPACE.md) | Local resources and saved revision references |
| [Platforms](docs/PLATFORMS.md) | Windows, Linux, WSL and macOS coverage |
| [Capabilities and limits](docs/IMPLEMENTATION.md) | Verified behavior and links to feature contracts |

## Project status

Inkbolt is under active development. Core editing, CLI/MCP, sessions and durable
receipts have Windows, Linux and macOS verification; background export jobs are
currently Windows-only. Broader format support, larger image workloads and agent
usability remain active work. See the [resource limits](docs/LIMITS.md) for current
bounds.

The [primary plan](FIX_PLAN.md) tracks development priorities.
[Benchmark results](docs/BENCHMARK_RESULTS.md) record agent evaluations and their
limitations separately from engine feature coverage.

Contributors can start with the [development guide](docs/DEVELOPMENT_LOOP.md),
[architecture](docs/ARCHITECTURE.md) and [source requirements](docs/RESEARCH.md).

## License

Inkbolt is [MIT licensed](LICENSE). Dependencies retain their own licenses;
see [third-party notices](THIRD_PARTY_NOTICES.md).
