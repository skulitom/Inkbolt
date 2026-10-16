# Inkbolt

Local vector and raster editing for AI agents.

Inkbolt lets agents create graphics, preview their work, make precise revisions
and export the result while keeping an editable source. Use it for diagrams,
illustrations, layouts and image assets.

It runs locally through **MCP over stdio**, a **JSON command-line interface**, or
the **Rust library**. There is no account, network service or telemetry, and no
particular AI model is required.

## What you can do

- **Build compositions** from vector shapes, text and images.
- **Bring in SVG artwork** with styles, reusable symbols, placed images and
  positioned text. Keep supported content editable and request omission reports
  when an input uses unsupported features.
- **Work with images** using PNG/TIFF import, high-precision samples and local
  image storage that preserves earlier revisions while reusing unchanged data.
- **Revise artwork** with targeted edits, layers, masks and image adjustments.
- **Review and continue** using previews, saved sessions, undo/redo and revision
  comparisons.
- **Deliver assets** as PNG, TIFF, SVG or PDF within the supported workflows,
  preserving source files and refusing to overwrite existing outputs.

Agents can discover tools and request individual operation schemas as they work.
Unsupported features fail explicitly; approximations and conversion losses are
reported.

## Get started

Download a [release](https://github.com/skulitom/Inkbolt/releases/latest) or follow
the [installation guide](docs/INSTALLATION.md) to build from source, then connect
your agent through MCP or use the command line.
Prebuilt archives are available for Windows x64, Linux x64 and macOS Apple
silicon, with a desktop extension bundle for Windows.

For an MCP client, use this launch command with the path to an existing folder
where you want to work:

```text
inkbolt --workspace PATH_TO_EXISTING_FOLDER mcp --tools core
```

The [installation guide](docs/INSTALLATION.md) includes ready-to-adapt client
configuration. The core catalog keeps initial tool discovery compact; agents can
request more operations and their schemas when needed.

Try the [runnable examples](examples/README.md) for creating artwork, revising
images and exporting assets.

## Documentation

| Start here | Details |
| --- | --- |
| [Examples](examples/README.md) | Runnable graphics and image workflows |
| [Agent interface](docs/AGENT_INTERFACE.md) and [tool discovery](docs/AGENT_DISCOVERY.md) | Commands, MCP tools and schemas |
| [Workspaces and sessions](docs/AGENT_WORKSPACE.md) | Local resources and saved revision references |
| [SVG import](docs/SVG_IMPORT.md) and [image import](docs/STREAMING_SAMPLE_IMPORT.md) | Supported inputs, preservation and conversion limits |
| [Platforms](docs/PLATFORMS.md) | Windows, Linux, WSL and macOS coverage |
| [Capabilities and limits](docs/IMPLEMENTATION.md) | Verified behavior and links to feature contracts |

## Project status

Inkbolt is under active development. Core editing, CLI/MCP, sessions and durable
receipts have Windows, Linux and macOS verification; background export jobs are
currently Windows-only. Broader format support, larger image workloads and agent
usability remain active work. See the [resource limits](docs/LIMITS.md) for current
bounds.

This README describes the development branch. Check the
[release notes](https://github.com/skulitom/Inkbolt/releases) for the features
included in a particular download.

The [primary plan](FIX_PLAN.md) tracks development priorities.
[Benchmark results](docs/BENCHMARK_RESULTS.md) record agent evaluations and their
limitations separately from engine feature coverage.

Contributors can start with the [development guide](docs/DEVELOPMENT_LOOP.md),
[architecture](docs/ARCHITECTURE.md) and [source requirements](docs/RESEARCH.md).

## License

Inkbolt is [MIT licensed](LICENSE). Dependencies retain their own licenses;
see [third-party notices](THIRD_PARTY_NOTICES.md).
