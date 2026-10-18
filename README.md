# Inkbolt

Local vector and raster editing for AI agents.

Inkbolt is a graphics engine that agents can inspect and control through
structured commands. Create diagrams, illustrations, layouts and image assets;
preview and revise them; then export the result while keeping an editable source.

It runs locally through **MCP over stdio**, a **JSON command-line interface**, or
the **Rust library**. There is no account, network service or telemetry, and no
particular AI model is required.

[Install and connect](docs/INSTALLATION.md) · [Try the examples](examples/README.md) ·
[Download a release](https://github.com/skulitom/Inkbolt/releases)

**Compared with** eight other SVG and vector editing MCP servers, local and hosted, in
[SVG and vector editing MCP servers for AI agents: 9 compared](https://skulitom.github.io/Inkbolt/compare/svg-vector-editing-mcp-servers/)
(checked 18 October 2026): Inkbolt measured over MCP, the others read from their code and docs, and when to choose
each instead.

## What you can do

- **Compose graphics** with vector shapes, text, images, layers and artboards.
- **Import artwork** from SVG, PNG, JPEG and TIFF. Supported SVG content stays
  editable, including styles, reusable symbols, placed images and positioned text.
- **Select and mask** with rectangular selections, feathered edges and
  image-guided masks from foreground/background seeds, including opt-in whole-image
  selection with native boundary refinement. Keep masks editable
  while preserving the original image samples.
- **Edit and repair images** with brushes, adjustments, patch
  placement, region fills, content-sensitive moves and guided edge correction.
  Native image storage supports high-precision samples and reuses unchanged data
  across edits.
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

Start with a release download, or build from source for the latest verified
development features. This README describes `main`; the release notes describe
what is included in each download. See the [installation guide](docs/INSTALLATION.md)
for setup on your system.

| Version | What to expect |
| --- | --- |
| [v0.82.0 release](https://github.com/skulitom/Inkbolt/releases/tag/v0.82.0) | Prebuilt Windows x64, Linux x64 and macOS Apple silicon archives, plus a Windows desktop extension bundle. See its release notes for included features. |
| Build from `main` | Adds larger image workflows, native JPEG import, large rectangular selections, guided region and whole-image masks for high-precision images, selected patch repair and lower-memory image exports. These additions are not in v0.82.0. |

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
| [Selections](docs/NATIVE_SELECTIONS.md) and [masks](docs/NATIVE_MASKS.md) | Select regions, refine coverage, preview and apply masks |
| [Image-guided selection](docs/NATIVE_SEGMENTATION.md) and [whole-image refinement](docs/PROXY_SEGMENTATION.md) | Seeded masks, source precision and declared sampling limits |
| [Image repair](docs/NATIVE_REPAIR.md) | Patch, fill, move and correction tools, supported precision and local edit limits |
| [Platforms](docs/PLATFORMS.md) | Windows, Linux, WSL and macOS coverage |
| [Capabilities and limits](docs/IMPLEMENTATION.md) | Verified behavior and links to feature contracts |

## Project status

Inkbolt is under active development. The core engine, CLI/MCP, saved sessions
and file-delivery receipts are tested on Windows, Linux and macOS. Background
export jobs currently require Windows. The [platform guide](docs/PLATFORMS.md)
records tested revisions and the scope of each platform's coverage.

Selected [50 MP image workflows](docs/SCALE_ADMISSION.md) have independent
Windows/Linux checks, including masks, local brush and patch edits, undo/redo
and TIFF delivery. Each operation retains its own size, precision and work
limits; this does not establish support for every operation at that size.

The latest [image-guided selection](docs/NATIVE_SEGMENTATION.md) works on stored
and high-precision images, with Windows/Linux acceptance. It analyzes a region
of up to **65,536 source pixels** (for example, 256 x 256) and preserves the
original image samples. For larger masks, [whole-image selection](docs/PROXY_SEGMENTATION.md)
uses a coarse pass and refines its boundary at native resolution. This mode can
miss small features outside the refined area; its approximation is explicit.

Work in progress includes larger edit regions and layered files, broader curve
combinations and editable format interchange. Agent usability
and complete large-image workflows also remain part of the active plan.

The [primary plan](FIX_PLAN.md) tracks development priorities.
[Benchmark results](docs/BENCHMARK_RESULTS.md) record agent evaluations and their
limitations separately from engine feature coverage.

Contributors can start with the [development guide](docs/DEVELOPMENT_LOOP.md),
[architecture](docs/ARCHITECTURE.md) and [source requirements](docs/RESEARCH.md).
Routine verification targets 2-3 minutes, with full checks at milestones.

## License

Inkbolt is [MIT licensed](LICENSE). Dependencies retain their own licenses;
see [third-party notices](THIRD_PARTY_NOTICES.md).
