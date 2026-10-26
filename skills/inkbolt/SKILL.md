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

The core catalog has 22 tools; `tools/list` sends them in three pages. `inkbolt_run` reaches every other command as
`{command, arguments}` with the same validation, and also runs the commands behind the direct tools (for example
`document.preview`, `font.import`, `session.create`) if a client shows only the first page.

| Step | Tool |
| --- | --- |
| Find commands and arguments | `inkbolt_schema_lookup` (`name: "index"` first, then one command or type) |
| New artwork | `inkbolt_document_create` (`id`, `kind`: `vector` or `raster`, `width`, `height`) |
| Draw and change | `inkbolt_document_edit` (snapshot, `expected_revision`, 1 to 64 `operations`) |
| Bring in an SVG | `inkbolt_run` with `svg.import` (keeps supported content editable) |
| Bring in a photo | `inkbolt_asset_import` (PNG, JPEG, TIFF, BMP, TGA, single-frame GIF), then place it (step 2) |
| Use a font | `inkbolt_font_import` (the font file and its licence) |
| Look at it | `inkbolt_document_preview` (PNG), `inkbolt_document_inspect`, `inkbolt_document_check` |
| Write files | `inkbolt_run` with `document.publish`, or `inkbolt_session_publish` for a saved session |
| Save and come back later | `inkbolt_session_create`, `inkbolt_session_apply`, `inkbolt_session_history` |
| Everything else | `inkbolt_run` with the command name from the index |

## Workflow

1. **Discover.** Call `inkbolt_schema_lookup` with `name: "index"`, then look up each command or operation before
   its first use. Large schemas come back as outlines: repeat the lookup with one listed `select` value, rather than
   `full: true`.
2. **Start.** Create a document or import the user's SVG; both return a snapshot, which every later call takes.
   Importing an image returns a receipt, not a document. To place the image in a layout, create a document, then add
   an `asset_put` operation (the receipt's `asset`) and an `add` operation whose item content is
   `{"type": "image", "asset_id": ..., "width": ..., "height": ...}`. A placed image can't take pixel edits: to
   retouch or paint on a photo, bring it in as pixels with `sample.import` through `inkbolt_run` (`id`,
   `source_path`, and `storage: {}` so the pixels go to the workspace's store; without it, all but small images fail
   with `RESOURCE_LIMIT`). In v0.82.0 `sample.import` reads PNG and TIFF only, and native JPEG import needs a build
   from `main`: convert a JPEG to PNG first, for example by placing it as an image and publishing a PNG.
3. **Edit.** Send `inkbolt_document_edit` the latest snapshot with `expected_revision` set to its `revision`. The
   quickest way to draw shapes is an `add_svg` operation with an SVG fragment; look up `name: "operation"` for the
   others (transforms, groups, canvas size, clips, masks, adjustments, retouching). Each edit returns the next
   snapshot at revision + 1, so always pass the newest one.
   - **Colours** are RGBA arrays: `#0B6E4F` is `[11, 110, 79, 255]`.
   - **To recolour a shape**, send a `vector` operation with the item's `id` and its whole current vector content
     (`geometry`, `fill`, `stroke`, `fill_rule`), changing only the colour asked for. The operation replaces the
     content, so a field left out is cleared: no fill, no stroke, or fill rule `nonzero`. `properties` changes only
     opacity, blend, visibility, lock and name.
   - **After `svg.import`**, items are named `svg-0`, `svg-1` and so on. `result.mapping` links each to the SVG's own
     `id`.
   - **Text** takes two steps after `inkbolt_font_import`, which returns the font's pinned descriptor. A `font_put`
     operation adds it to the document (`{"op": "font_put", "id": ..., "font": <descriptor>}`), and the `add_svg`
     operation's `font_bindings` (`{"family": ..., "font_id": ...}`) maps the SVG's `font-family` to it. Without the
     binding, `<text>` fails with `SVG_FONT_NOT_BOUND`.
4. **Check.** Look at `inkbolt_document_preview` before delivering. Fix what's wrong and preview again.
   `inkbolt_document_check` reports structure problems and text that overflows.
5. **Deliver.** Call `document.publish` through `inkbolt_run` with the snapshot and an `output` of `file_name`,
   `format` (`png`, `jpeg`, `svg`, `pdf` or `tiff`), an optional `scale` for raster formats and, for a subfolder,
   `output_root`. It refuses to overwrite an existing file: choose a new name rather than replacing the user's file.
   For vector artwork, publish an `svg` alongside a raster when the user may edit again. Raster documents can't be
   exported as SVG; keep them editable in a saved session instead.
6. **Report** the paths written, the sizes, and anything Inkbolt said it approximated or couldn't represent.

For work the user will come back to, save it as a session (`inkbolt_session_create`, then `inkbolt_session_apply`
and `inkbolt_session_publish`), which keeps revision history and undo.

## Good to know

- Paths are relative to the project folder. Paths outside it are refused.
- Text needs a local outline font that the user may use, with its licence file. If the project has none, ask for
  one, or keep the design free of text.
- Unsupported features fail explicitly. Read the error's `message`, `hint` and `details.schema_lookup` and change
  the request; don't retry it unchanged.
- Raster documents keep the original image samples, and edits stay editable until publishing.
