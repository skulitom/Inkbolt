# Inkbolt

Local vector and raster editing for AI agents.

Inkbolt gives agents an editable graphics workspace for diagrams, illustrations,
layouts and image assets. Create or import artwork, make focused changes, inspect
previews and export the result while keeping the source and revision history.

It runs locally through **MCP over stdio**, a **JSON command-line interface**, or
the **Rust library**. There is no account, network service or telemetry, and no
particular AI model is required.

[Install and connect](docs/INSTALLATION.md) · [Try the examples](examples/README.md) ·
[Download a release](https://github.com/skulitom/Inkbolt/releases)

## What you can do

- **Compose graphics** with vector shapes, text, images, layers and artboards.
- **Import artwork** from SVG, PNG, JPEG and TIFF. Supported SVG content stays
  editable, including styles, reusable symbols, placed images and positioned text.
- **Select and mask** image regions with feathered edges or foreground/background
  seeds. Keep masks editable and preserve the original image samples.
- **Edit and repair images** with brushes, adjustments, patches, region fills,
  content-sensitive moves and guided edge correction. Native storage supports
  high-precision samples and shares unchanged data across edits.
- **Review revisions** with previews, comparisons, saved sessions and undo/redo.
- **Deliver assets** as PNG, JPEG, TIFF, SVG or PDF within the supported workflows.
  Preflight reports output size and conversion losses before publication; file
  delivery preserves sources and refuses to overwrite existing outputs.

Agents discover tools and request individual operation schemas as they work.
Unsupported features fail explicitly; declared approximations and conversion
losses are reported.

## How agents work with Inkbolt

1. Discover the relevant tools and create or import a document.
2. Make focused edits, preview the result and compare revisions.
3. Save the editable session, check the intended export and publish to a new file.

Saved sessions let an agent resume work later with the document's revision history.

## Get started

**This README describes `main`.** Download a release for a packaged build, or
build from source for the newer features below. Follow the
[installation guide](docs/INSTALLATION.md) for your system and MCP client.

| Version | What to expect |
| --- | --- |
| [v0.82.0 release](https://github.com/skulitom/Inkbolt/releases/tag/v0.82.0) | Windows x64, Linux x64 and macOS Apple silicon archives, plus a Windows desktop extension bundle. Release notes describe the included features. |
| Build from `main` | Adds larger image editing, native JPEG import, guided selections and masks, patch repair, editable layered imports, focused previews for large images, and lower-memory exports. The large-image workflows described below require this newer source build. |

For an MCP client, use this launch command with the path to an existing folder
where you want to work:

```text
inkbolt --workspace PATH_TO_EXISTING_FOLDER mcp --tools essentials
```

Source builds offer the ten-tool essentials catalog for compact discovery; use
`--tools core` with the v0.82.0 release. Agents can request more
operations and their schemas when needed.

## Documentation

| Start here | Details |
| --- | --- |
| [Examples](examples/README.md) | Runnable graphics and image workflows |
| [Agent interface](docs/AGENT_INTERFACE.md) and [tool discovery](docs/AGENT_DISCOVERY.md) | Commands, MCP tools and schemas |
| [Workspaces and sessions](docs/AGENT_WORKSPACE.md) | Local resources, saved work and revision references |
| [SVG import](docs/SVG_IMPORT.md), [image import](docs/SAMPLES.md#import-without-reducing-depth) and [layered import](docs/LAYERED_NATIVE_IMPORT.md) | Editable inputs, source precision and conversion limits |
| [Selections](docs/NATIVE_SELECTIONS.md), [masks](docs/NATIVE_MASKS.md) and [image repair](docs/NATIVE_REPAIR.md) | Image editing workflows and operation limits |
| [Large-image workflows](docs/SCALE_WORKLOADS.md) | 24 MP import, 50 MP editing, A2 delivery and 8192 x 8192 rendering; [brush and retouch bounds](docs/LARGE_EDIT_WINDOWS.md) |
| [Image export](docs/STREAMING_IMAGE_OUTPUT.md) | PNG/JPEG/TIFF file output, preflight and memory bounds |
| [Capabilities and limits](docs/IMPLEMENTATION.md) | Verified behavior and links to feature contracts |
| [Platform support](docs/PLATFORMS.md) and [benchmark results](docs/BENCHMARK_RESULTS.md) | Tested systems, agent evaluations and remaining gaps |
| [Workload measurements](docs/WORKLOAD_MEASUREMENT.md) | Reproducible runtime and memory checks, including Linux CLI and MCP sessions |

For context on other tools, see
[SVG and vector editing MCP servers for AI agents: 9 compared](https://skulitom.github.io/Inkbolt/compare/svg-vector-editing-mcp-servers/).
The comparison was checked on 18 October 2026: Inkbolt was measured over MCP;
the other servers were reviewed through their code and documentation.

## Project status

Inkbolt is under active development. The core engine, CLI/MCP, saved sessions
and file-delivery receipts are tested on Windows, Linux and macOS. Background
export jobs currently require Windows. The [platform guide](docs/PLATFORMS.md)
records tested revisions and the scope of each platform's coverage.

The following [large-image workflows](docs/SCALE_WORKLOADS.md) have passed
independent output checks on **Windows and Linux**:

| Workflow | Checked size |
| --- | --- |
| Baseline and progressive JPEG import | 24 MP |
| 16-bit image editing: cloned patch, selected brush, repair, feathered mask, undo/redo and TIFF export | 50 MP |
| A2 page delivery as PDF and PNG | 300 ppi |
| Rendering and PNG export with opaque, translucent and transparent regions | 8192 x 8192 |

These checks use fixed original fixtures and preserve source files and revision
history. Windows regression budgets use five baseline repetitions and a
separate five-repeat check. Each operation retains its own size, precision and
work limits; cross-platform performance acceptance remains in progress.

[Image-guided selection](docs/NATIVE_SEGMENTATION.md) supports direct analysis of
bounded regions and an opt-in whole-image mode. The latter uses a coarse image
and refines boundaries at full resolution; it can miss small features. Both
preserve the original image samples.

Editable RGB8 [layered imports](docs/LAYERED_NATIVE_IMPORT.md) have also been
checked at 8192 x 8192 on Windows and Linux. Larger canvases require an explicit
import option. The native path reads larger encoded files in bounded chunks;
its contract lists separate file, metadata and content limits.

Work in progress includes broader layered-file interchange, broader curve combinations,
editable format interchange, agent usability and cross-platform performance
acceptance.

The [primary plan](FIX_PLAN.md) tracks development priorities.
[Benchmark results](docs/BENCHMARK_RESULTS.md) record agent evaluations and their
limitations separately from engine feature coverage.

Contributors can start with the [development guide](docs/DEVELOPMENT_LOOP.md),
[architecture](docs/ARCHITECTURE.md) and [source requirements](docs/RESEARCH.md).
Routine verification targets 2-3 minutes, with full checks at milestones.

## License

Inkbolt is [MIT licensed](LICENSE). Dependencies retain their own licenses;
see [third-party notices](THIRD_PARTY_NOTICES.md).
