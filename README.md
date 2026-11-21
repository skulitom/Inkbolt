# Inkbolt

Inkbolt is a local vector and raster editor for AI agents. An agent can open an
SVG, change one shape, preview the difference and export a PNG while keeping the
artwork editable. Saved sessions let it return to an earlier revision or pick up
where it left off.

Agents can use the same engine through MCP over stdio, a JSON command-line
interface or the Rust library. Inkbolt runs on your machine and works without
an account, network service, telemetry or a particular AI model.

## Get started

[Download the archive for your system](https://github.com/skulitom/Inkbolt/releases/latest)
and extract it into a folder you can write to. The archive includes an
editable [postcard](examples/first-png.json). Open PowerShell or a Unix shell
in the extracted folder and render it with one command.

```text
./inkbolt --workspace "$PWD" examples/first-png.json
```

Open `postcard.png` next to the executable. To try another palette, change a
fill in the JSON and give the output a new filename. For the first launch on
macOS, see [installation](docs/INSTALLATION.md#linux-and-macos).

To connect an agent, create a folder for its artwork. Configure your MCP client
to launch the extracted executable with that folder's absolute path.

```text
inkbolt --workspace PATH_TO_EXISTING_FOLDER mcp --tools essentials
```

The agent starts with ten tools and can look up editing commands as it works.
A desktop extension is also available for Windows. [Installation and client setup](docs/INSTALLATION.md)

## What you can make

| Saved diagram | After one edit |
| --- | --- |
| ![Two blue blocks connected by a curved arrow](https://skulitom.github.io/Inkbolt/compare/svg-vector-editing-mcp-servers/data/outputs-v0.82.0/original.svg) | ![The left block is lower and the right block is green](https://skulitom.github.io/Inkbolt/compare/svg-vector-editing-mcp-servers/data/outputs-v0.82.0/edited.svg) |

One edit moved the left block down 10 units and changed the right block's
fill. Undo restored the starting SVG byte for byte. [Restored SVG](https://skulitom.github.io/Inkbolt/compare/svg-vector-editing-mcp-servers/data/outputs-v0.82.0/restored.svg)

| Task | How Inkbolt helps |
| --- | --- |
| Draw a diagram or illustration | Arrange shapes, text, images and artboards. Import editable SVG artwork, including reusable symbols and positioned text. [SVG import](docs/SVG_IMPORT.md) |
| Cut or join shapes | Combine filled paths, circles and ellipses in one undoable edit. The resulting Bézier handles stay editable. [Shape combinations](docs/BOOLEANS.md#editable-curve-output) |
| Retouch an image | Select a region, feather a mask or repair a patch. Keep 16-bit samples and share unchanged image data across revisions. [Selections](docs/NATIVE_SELECTIONS.md) · [Image repair](docs/NATIVE_REPAIR.md) |
| Review and deliver artwork | Compare revisions, undo a change, and preflight a PNG, JPEG, TIFF, SVG or PDF before saving it. For multi-page PDFs, select the artboards to deliver and include their bleed. [Sessions](docs/AGENT_WORKSPACE.md) · [PDF export](docs/PDF.md) · [Runnable examples](examples/README.md) |

## Builds and platform support

Measured Windows and Linux workflows include a 24 MP JPEG import, a 50 MP
16-bit edit through undo and TIFF export, A2 delivery at 300 ppi and an
8192 × 8192 PNG render. [Measured workflows](docs/SCALE_WORKLOADS.md) · [50 MP agent trials](docs/B10_LARGE.md#five-matched-windows-trials) · [Engine limits](docs/LIMITS.md)

The v0.84.0 release includes tested downloads for Windows x64, Linux x64,
Apple silicon and Intel Macs. Background export jobs currently require Windows.
[Downloads](https://github.com/skulitom/Inkbolt/releases/tag/v0.84.0) · [Platform test results](docs/PLATFORMS.md#v0840-platform-checks)

Building from `main` also lets you keep paths and text outlines in an unmarked
RGB PDF when artwork uses a mask or a knockout group. For example, a shape
can cut a window through its group to reveal the artwork behind it.
[PDF masks](docs/PDF.md#masks-made-from-editable-artwork) · [Knockout groups](docs/PDF.md#knockout-groups)

## Explore the project

- [Agent interface](docs/AGENT_INTERFACE.md) and [tool discovery](docs/AGENT_DISCOVERY.md) cover requests, schemas and receipts.
- [Implemented capabilities](docs/IMPLEMENTATION.md) and [agent benchmarks](docs/BENCHMARK_RESULTS.md) describe supported behavior and measured task outcomes.
- The [development plan](FIX_PLAN.md) tracks remaining work. The [development guide](docs/DEVELOPMENT_LOOP.md) explains the 2–3 minute feedback loop and full milestone checks.
- [Architecture](docs/ARCHITECTURE.md) and [source requirements](docs/RESEARCH.md) are the starting points for contributors.
- The [vector editing MCP comparison](https://skulitom.github.io/Inkbolt/compare/svg-vector-editing-mcp-servers/) covers Inkbolt and eight other tools as reviewed on 18 October 2026.

Inkbolt uses the [MIT license](LICENSE). Dependencies retain their own
[licenses and notices](THIRD_PARTY_NOTICES.md).
