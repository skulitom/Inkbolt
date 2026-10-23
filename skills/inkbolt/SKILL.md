---
name: inkbolt
description: Create, edit and export graphics on this computer with Inkbolt. Use when the user asks to make or change an icon, logo, badge, diagram, illustration, banner, social card or other image; to recolor, resize, crop, mask or retouch a PNG, JPEG, TIFF or SVG; or to export artwork as PNG, JPEG, SVG or PDF while keeping an editable source. Not for video or audio, for a PDF's text, or when the user wants HTML, CSS or plotting code rather than an image file. Local, no account, no API key.
---

# Inkbolt

Inkbolt is a local vector and raster graphics engine. This plugin starts it as an MCP server over stdio with the
user's project folder as its workspace: `inkbolt --workspace <project folder> mcp --tools core`. It needs no account,
API key or network, and it never overwrites files: sources stay as they are, and publishing creates new files only.

Use it when the result should be an image file the user can open, such as a PNG, JPEG, SVG or PDF. If they want code
that draws something (an HTML page, a chart in a notebook), write the code instead.

## When Inkbolt isn't installed

The plugin runs the `inkbolt` binary from PATH. If no `inkbolt` tools are available, or `/mcp` shows the server as
failed (often "CONNECTION_CLOSED"), the binary is missing. Say so, and with the user's agreement install it:

1. Download the archive for the system from https://github.com/skulitom/Inkbolt/releases/latest (Windows x64 `.zip`,
   Linux x64 or macOS Apple silicon `.tar.gz`) and check it against the release's `SHA256SUMS`.
2. Extract it and put the folder that holds `inkbolt` (`inkbolt.exe` on Windows) on PATH. On macOS, run
   `xattr -d com.apple.quarantine inkbolt` once, because the binary isn't notarized.
3. Check it with `inkbolt --help`, then restart Claude Code so the plugin's server starts.

Building from source is in https://github.com/skulitom/Inkbolt/blob/main/docs/INSTALLATION.md. Don't configure a
second `inkbolt` server with `claude mcp add` while this plugin is enabled.

## Tools

The compact catalog has eight tools. `inkbolt_run` reaches every other command as `{command, arguments}`, with the
same validation.

| Step | Tool |
| --- | --- |
| Find commands and arguments | `inkbolt_schema_lookup` (`name: "index"` first, then one command or type) |
| New artwork | `inkbolt_document_create` (`id`, `kind`: `vector` or `raster`, `width`, `height`) |
| Draw and change | `inkbolt_document_edit` (snapshot, `expected_revision`, 1 to 64 `operations`) |
| Bring in an SVG | `inkbolt_run` with `svg.import` (keeps supported content editable) |
| Bring in a photo | `inkbolt_asset_import` (PNG, JPEG, TIFF, BMP, TGA, single-frame GIF) |
| Look at it | `inkbolt_run` with `document.preview` (PNG), `inkbolt_document_inspect`, `inkbolt_document_check` |
| Write files | `inkbolt_run` with `document.publish` |
| Everything else | `inkbolt_run` with the command name from the index |

## Workflow

1. **Discover.** Call `inkbolt_schema_lookup` with `name: "index"`, then look up each command before its first use.
   Large schemas come back as outlines: repeat the lookup with one listed `select` value, rather than `full: true`.
2. **Start.** Create a document, import the user's SVG, or import their image. Keep the returned snapshot: every
   later call takes it.
3. **Edit.** Send `inkbolt_document_edit` the latest snapshot with `expected_revision` set to its `revision`. The
   quickest way to draw shapes is an `add_svg` operation with an SVG fragment; look up `name: "operation"` for the
   others (transforms, groups, canvas size, clips, masks, adjustments, retouching). Each edit returns the next
   snapshot at revision + 1, so always pass the newest one.
   - **Colours** are RGBA arrays: `#0B6E4F` is `[11, 110, 79, 255]`.
   - **To recolour a shape**, send a `vector` operation with the item's `id`, its unchanged `geometry` and the new
     `fill` (or `stroke`). `properties` changes only opacity, blend, visibility, lock and name.
   - **After `svg.import`**, items are named `svg-0`, `svg-1` and so on. `result.mapping` links each to the SVG's own
     `id`.
4. **Check.** Preview the result with `document.preview` and look at it before delivering. Fix what's wrong and
   preview again. `inkbolt_document_check` reports structure problems and text that overflows.
5. **Deliver.** Call `document.publish` with the snapshot and an `output` of `file_name`, `format` (`png`, `jpeg`,
   `svg`, `pdf` or `tiff`) and, for a subfolder, `output_root`. It refuses to overwrite an existing file: choose a
   new name rather than replacing the user's file. Publish an `svg` alongside a raster when the user may edit again.
6. **Report** the paths written, the sizes, and anything Inkbolt said it approximated or couldn't represent.

For work the user will come back to, save it as a session (`session.create`, then `session.apply` and
`session.publish`), which keeps revision history and undo.

## Good to know

- Paths are relative to the project folder. Paths outside it are refused.
- Text needs a local outline font that the user may use, imported with its licence file through `inkbolt_run` with
  `font.import`. If the project has none, ask for one, or keep the design free of text.
- Unsupported features fail explicitly. Read the error's `message`, `hint` and `details.schema_lookup` and change
  the request; don't retry it unchanged.
- Raster documents keep the original image samples, and edits stay editable until publishing.
