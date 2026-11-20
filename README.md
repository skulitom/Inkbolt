# Inkbolt

Inkbolt is a local vector and raster editor for AI agents. An agent can open an
SVG, change one shape, preview the difference and export a PNG while keeping the
artwork editable. Saved sessions let it return to an earlier revision or pick up
where it left off.

Agents can use the same engine through MCP over stdio, a JSON command-line
interface or the Rust library. Inkbolt runs on your machine and works without
an account, network service, telemetry or a particular AI model.

## Get started

[Download the release for your system](https://github.com/skulitom/Inkbolt/releases/latest)
and extract it. Create a workspace folder, then configure your MCP client to
launch the extracted binary with that folder's absolute path. This command also
works with v0.82.0.

```text
inkbolt --workspace PATH_TO_EXISTING_FOLDER mcp --tools core
```

The release includes Windows x64, Linux x64 and macOS Apple silicon binaries
and a Windows desktop extension bundle. Builds after v0.82.0 also support
`--tools essentials`, a ten-tool catalog that lets agents discover individual
commands as needed. See the [installation and client setup guide](docs/INSTALLATION.md).

To try an edit directly from a checkout, run the following with the binary on
your path. It returns the edited vector document as JSON.

```text
inkbolt examples/edit-vector.json
```

## What you can make

These workflows describe the current source tree. The release notes list what shipped in each build.

| Task | How Inkbolt helps |
| --- | --- |
| Draw a diagram or illustration | Arrange shapes, text, images and artboards. Import editable SVG artwork, including reusable symbols and positioned text. [SVG import](docs/SVG_IMPORT.md) |
| Cut or join shapes | Combine filled paths, circles and ellipses in one undoable edit. Request `"output":"curves"` to keep supported boundaries editable as Bézier curves. [Shape combinations](docs/BOOLEANS.md#editable-curve-output) |
| Retouch an image | Select a region, feather a mask or repair a patch. Builds after v0.82.0 support 16-bit edits and share unchanged image data across revisions. [Selections](docs/NATIVE_SELECTIONS.md) · [Image repair](docs/NATIVE_REPAIR.md) |
| Review and deliver artwork | Compare revisions, undo a change, and preflight the output before writing a new PNG, JPEG, TIFF, SVG or PDF within the supported workflows. [Sessions](docs/AGENT_WORKSPACE.md) · [Runnable examples](examples/README.md) |

## Builds and platform support

See the [latest release notes](https://github.com/skulitom/Inkbolt/releases/latest)
for the packaged build. Work since v0.82.0 includes shape combinations,
native JPEG import, larger image edits and lower-memory exports. Windows and
Linux checks cover a 24 MP JPEG import, a 50 MP 16-bit edit through undo and TIFF
export, A2 delivery at 300 ppi and an 8192 × 8192 PNG render.
[Measured workflows and limits](docs/SCALE_WORKLOADS.md)

The core engine, CLI, MCP and saved sessions have been tested on Windows, Linux
and macOS. Background export jobs currently require Windows. The platform guide
records the revisions and tests for each system. [Platform support](docs/PLATFORMS.md)

## Explore the project

- [Agent interface](docs/AGENT_INTERFACE.md) and [tool discovery](docs/AGENT_DISCOVERY.md) cover requests, schemas and receipts.
- [Implemented capabilities](docs/IMPLEMENTATION.md) and [agent benchmarks](docs/BENCHMARK_RESULTS.md) describe supported behavior and measured task outcomes.
- The [development plan](FIX_PLAN.md) tracks remaining work. The [development guide](docs/DEVELOPMENT_LOOP.md) explains the 2–3 minute feedback loop and full milestone checks.
- [Architecture](docs/ARCHITECTURE.md) and [source requirements](docs/RESEARCH.md) are the starting points for contributors.
- The [vector editing MCP comparison](https://skulitom.github.io/Inkbolt/compare/svg-vector-editing-mcp-servers/) covers Inkbolt and eight other tools as reviewed on 18 October 2026.

Inkbolt uses the [MIT license](LICENSE). Dependencies retain their own
[licenses and notices](THIRD_PARTY_NOTICES.md).
