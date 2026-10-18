# Inkbolt

Local vector and raster editing for AI agents.

Inkbolt is a graphics engine that agents can inspect and control through
structured commands. Create diagrams, illustrations, layouts and image assets;
preview and revise them; then export the result while keeping an editable source.

It runs locally through **MCP over stdio**, a **JSON command-line interface**, or
the **Rust library**. There is no account, network service or telemetry, and no
particular AI model is required.

## What you can do

- **Compose graphics** with vector shapes, text, images, layers and artboards.
- **Import artwork** from SVG, PNG, JPEG and TIFF. Supported SVG content stays
  editable, including styles, reusable symbols, placed images and positioned text.
- **Edit and repair images** with brushes, masks, adjustments, patch placement,
  region fills, content-sensitive moves and guided edge correction. Native image
  storage supports high-precision samples and reuses unchanged data across edits.
- **Review revisions** with previews, comparisons, saved sessions and undo/redo.
- **Deliver assets** as PNG, JPEG, TIFF, SVG or PDF within the supported workflows.
  Preflight reports output size and conversion losses before publication; file
  delivery preserves sources and refuses to overwrite existing outputs.

Agents can discover tools and request individual operation schemas as they work.
Unsupported features fail explicitly; approximations and conversion losses are
reported.

## How agents work with Inkbolt

1. Discover the relevant tools and create or import a document.
2. Make focused edits, preview the result and compare revisions.
3. Save the editable session, check the intended export and publish to a new file.

Saved sessions let an agent resume work later with the document's revision
history. See the [runnable examples](examples/README.md) for complete workflows.

## Get started

This README describes `main`. Choose a release download or build the latest
development version using the [installation guide](docs/INSTALLATION.md).

| Version | What to expect |
| --- | --- |
| [v0.82.0 release](https://github.com/skulitom/Inkbolt/releases/tag/v0.82.0) | Prebuilt Windows x64, Linux x64 and macOS Apple silicon archives, plus a Windows desktop extension bundle. See its release notes for included features. |
| Build from `main` | Adds larger image workflows, native JPEG import, high-precision repair, previews of large masks and lower-memory PNG/JPEG/TIFF exports. These additions are not in v0.82.0. |

For an MCP client, use this launch command with the path to an existing folder
where you want to work:

```text
inkbolt --workspace PATH_TO_EXISTING_FOLDER mcp --tools core
```

The [installation guide](docs/INSTALLATION.md) includes ready-to-adapt client
configuration. The core catalog keeps initial tool discovery compact; agents can
request more operations and their schemas when needed.

## Documentation

| Start here | Details |
| --- | --- |
| [Examples](examples/README.md) | Runnable graphics and image workflows |
| [Agent interface](docs/AGENT_INTERFACE.md) and [tool discovery](docs/AGENT_DISCOVERY.md) | Commands, MCP tools and schemas |
| [Workspaces and sessions](docs/AGENT_WORKSPACE.md) | Local resources and saved revision references |
| [SVG import](docs/SVG_IMPORT.md) and [image import](docs/SAMPLES.md#import-without-reducing-depth) | Supported inputs, preservation and conversion limits |
| [Image export](docs/STREAMING_IMAGE_OUTPUT.md) | PNG/JPEG/TIFF file output, preflight and memory bounds |
| [Large-image workflows](docs/SCALE_ADMISSION.md) | Verified image sizes, local edits and remaining workflow limits |
| [Image repair](docs/NATIVE_REPAIR.md) | Patch, fill, move and correction tools, supported precision and local edit limits |
| [Platforms](docs/PLATFORMS.md) | Windows, Linux, WSL and macOS coverage |
| [Capabilities and limits](docs/IMPLEMENTATION.md) | Verified behavior and links to feature contracts |

## Project status

Inkbolt is under active development. Core editing, CLI/MCP, sessions and durable
receipts have Windows, Linux and macOS verification; background export jobs are
currently Windows-only.

On `main`, Windows and Linux checks cover 50 MP images through local brush and
repair edits, saved history and TIFF delivery. Large masks support focused
previews. Each operation has its own size, precision and work limits;
large selections and whole-image mask application remain in development. See
[large-image workflows](docs/SCALE_ADMISSION.md), [image repair](docs/NATIVE_REPAIR.md),
[image masks](docs/NATIVE_MASKS.md) and [resource limits](docs/LIMITS.md) for the
verified scope.

Broader image workflows, editable format coverage and agent usability remain
active work.

The [primary plan](FIX_PLAN.md) tracks development priorities.
[Benchmark results](docs/BENCHMARK_RESULTS.md) record agent evaluations and their
limitations separately from engine feature coverage.

Contributors can start with the [development guide](docs/DEVELOPMENT_LOOP.md),
[architecture](docs/ARCHITECTURE.md) and [source requirements](docs/RESEARCH.md).
Routine verification targets 2-3 minutes, with full checks at milestones.

## License

Inkbolt is [MIT licensed](LICENSE). Dependencies retain their own licenses;
see [third-party notices](THIRD_PARTY_NOTICES.md).
