# Original graphics examples

`python examples/handoff_workflow.py --output NEW_ABSOLUTE_DIRECTORY [--cutbolt EXE]`
prepares two checked still revisions and an ordered sequence, retaining original
deliveries and source history. The optional local Cutbolt executable inspects and
renders every scene. See [the versioned handoff contract](../docs/HANDOFF.md).

Run `combined_prepress_workflow.py --output NEW_DIRECTORY` for an original six-plate chart, retained sources, reference proof, gamut masks and combined PDF. Optionally supply `--profile PATH`; the default synthetic profile is a demonstration, not a measured printing condition.

Run `python examples/recipe_workflow.py --output ABSOLUTE_NEW_FOLDER` for an original editable duotone chart, exact scalar plates, declared appearance preview, named-ink PDF and a curve revision. The output directory must not already exist.

`python examples/print_workflow.py --output NEW_DIRECTORY [--profile CMYK_ICC_FILE]` creates an original editable chart, profile-pinned print pages at two sample densities and receipts. Without a supplied profile it uses an original analytic fixture, clearly labelled as a demonstration rather than a calibrated printing condition.

`python examples/raw_edit_workflow.py --output NEW_DIRECTORY` saves four retained sensor developments with lens/noise/detail settings, sidecars, reopened snapshots and PNG/TIFF outputs. See [retained raw development](../docs/RAW_EDITING.md).

`python examples/raw_workflow.py --output NEW_DIRECTORY` develops an original Bayer chart at three settings, saving sensor bytes, pinned recipes, snapshots and PNG/TIFF outputs. See [raw development](../docs/RAW.md).

`python examples/compound_region_workflow.py --output <new-directory>` creates five editable curved compound masks, original source paths, snapshots, selections and PNGs. See [compound regions](../docs/COMPOUND_REGIONS.md).

`python examples/volume_workflow.py --output <new-directory>` creates an original dimensional diagram node, editable profile/camera/lighting source, PNG/SVG/PDF output and face expansion with undo.

`python examples/appearance_workflow.py --output <new-directory>` creates an original badge with multiple live paints, editable expansion, a filtered source, explicit baked SVG/PDF delivery and durable undo receipts.

`sequence_workflow.py --output <new-directory>` creates original timed icons, editable snapshots, APNG, ordered PNG files and a Cutbolt still recipe with explicit hold/matte losses. Add `--cutbolt <local-executable>` to inspect and compile the still in the sister engine.

`python examples/prepress_workflow.py --output <new-directory>` saves an editable two-page layout, native ink PDFs with and without bleed, and page/ink receipts. See [basic vector print preparation](../docs/PREPRESS.md).

Run `inkbolt examples/hyphenate.json` to inspect weighted break opportunities for two original synthetic tokens. Rules are explicit and input text is preserved; this read-only example does not render a paragraph. See [the hyphenation contract](../docs/HYPHENATION.md).

`object_workflow.py --output <new-directory>` creates an original editable motif, places two independent objects, replaces one source and publishes retained snapshots plus a PNG. Every destination is create-only; the original source remains unchanged.

Run `python examples/ink_workflow.py --output <new-directory>` to retain spot/process declarations, inspect overprint and publish native ink PDF. See [the ink contract](../docs/INK_DELIVERY.md).

`python examples/swatch_workflow.py --output <new-directory>` saves an original shared palette, recolors spot tints, publishes before/after previews and explicitly bakes a copy for SVG/PDF. See [named colors](../docs/SWATCHES.md).

`python examples/dimensions_workflow.py --output <new-directory>` saves an original editable card, measures and sets its physical dimensions, snaps to frame guides and publishes a snapshot, SVG and PNG. See [dimensions and snapping](../docs/DIMENSIONS.md).

`python examples/render_quality_workflow.py --output <new-directory>` creates an original editable icon, coverage/supersampled PNGs and a padded TIFF with explicit quality receipts. See [render quality](../docs/RENDER_QUALITY.md).

`pixel_warp_workflow.py --output <new-directory>` publishes four original coordinate charts with perspective, mesh, articulated and mirrored deformations, retained inputs, editable controls, inverse inspections and PNG/TIFF deliveries. See [the pixel deformation contract](../docs/PIXEL_WARPS.md).

`warp_workflow.py --output <new-directory>` publishes four original perspective, nonlinear envelope, nested and curved vector fixtures with retained source controls, certified geometry/grids and matching expanded PNG/SVG deliveries. See [the warp contract](../docs/WARPS.md).

`repeat_workflow.py --output <new-directory>` publishes four original brick, hexagonal, mirrored-hole and radial pattern fields with editable motifs, inspection/expansion receipts and matching PNG/SVG deliveries. See [the repeat contract](../docs/REPEATS.md).

`interpolation_workflow.py --output <new-directory>` publishes four original shape/color progressions: straight steps, triangle-to-rectangle correspondence, curved diagram markers and a shrinking hole. It retains editable snapshots, inspection/expansion receipts and matching PNG/SVG deliveries. See [the interpolation contract](../docs/INTERPOLATION.md).

`vector_brush_workflow.py --output <new-directory>` creates three original graphics with editable motif routes, compound holes and variable-width patterns. It publishes preserved snapshots, matching editable/expanded PNGs, SVG outlines, expansion and difference receipts. See [the brush contract](../docs/VECTOR_BRUSHES.md).

Build with `cargo build --locked`. The create examples return empty documents. `edit-vector.json` and `edit-raster.json` are self-contained first-edit requests returning an editable snapshot in `result.document`.

The complete workflow is:

1. Invoke the edit request and retain `result.document`.
2. Inspect it using `{"command":"document.inspect","document":...}`.
3. Revise it using document.edit with its current expected_revision and operations.
4. Export using `{"command":"document.export","document":...,"format":"png"}` or SVG for supported vector content.
5. Decode base64 PNG data, or write UTF-8 SVG/snapshot data, to a new output file chosen by the caller.

`python examples/render_example.py --output-dir <new-directory>` demonstrates the workflow through the CLI and writes an editable snapshot, PNG and SVG. The output directory must not already exist. It also produces a separate small pixel-edit example and PNG. Every input is original synthetic geometry or pixel data; the helper never modifies input files.

Ordinary document.export returns data; document.publish/session.publish now offer separate create-only file publication. The helper is an optional example client with exclusive output creation, not a stored-session or general publication implementation.

For a grouped, clipped and aligned composition, add `--vector-request examples/layout-vector.json`. That request keeps original objects editable, groups each card, clips its contents, and distributes the cards against explicit layout bounds. The resulting SVG preserves the hierarchy and enabled geometric clips.

`paint-vector.json` creates three original gradient icon cards, with linear/radial color fields, editable vector symbols and layered translucent surfaces. `paint-raster.json` creates an editable freeform color panel next to an original repeating tile. Render both with a fresh output directory:

```powershell
python examples/render_example.py --vector-request examples/paint-vector.json --raster-request examples/paint-raster.json --output-dir outputs/paint-preview
```

The example client refuses an existing output directory and creates every file exclusively. The vector example supports SVG; freeform and inline pattern appearances are PNG/snapshot only. These JSON fixtures and all their artwork are original.

`image_workflow.py` takes an explicit PNG source and a fresh output directory. It imports the source once into a content-addressed store, places full/cropped/reflected/rotated copies, and writes an editable snapshot, asset inspection and PNG/SVG outputs. For example, use the original vector PNG generated above:

```powershell
python examples/image_workflow.py --source outputs/paint-preview/vector.png --output-dir outputs/image-preview
```

Untagged sources require `--color-policy assume_srgb`; other unsupported metadata is rejected. Keep the generated assets directory with the snapshot and pass it as asset_root when rendering again. The client checks that source bytes remain unchanged and refuses an existing output directory.

## Editable text diagram

`text_workflow.py` uses a permitted local outline font and its license to create an original labeled diagram. Pass absolute input paths and a new output directory:

```powershell
python examples/text_workflow.py --font C:/Fonts/PermittedFont.ttf --license C:/Fonts/OFL.txt --output C:/Exports/inkbolt-text
```

The script writes a new PNG, outlined SVG, editable snapshot and measured glyph report, with a pinned external font store. Inputs remain unchanged and an existing output directory is rejected. A font must cover the English example labels; its metrics may require larger frames. No external font is bundled. Noto Sans at its default instance was used for the private verification example.

## Multiple artboards

`artboard_workflow.py` builds three original layouts (landscape, portrait and icon), using the same permitted-font inputs as the text example and a new output directory. Each artboard owns its editable content; card frames nest inside the layouts. It writes a contact sheet, full snapshot, independent PNG/SVG exports, bleed variants for a board range, and inspection/export receipts. The crossing edge stripe makes trim-versus-bleed behavior visible. Guides remain in the snapshot and do not print.

```powershell
python examples/artboard_workflow.py --font C:/Fonts/PermittedFont.ttf --license C:/Fonts/OFL.txt --output C:/Exports/inkbolt-artboards
```

## Saved sessions and recovery

`session_workflow.py` opens an explicit editable snapshot in a new local session, creates a named snapshot, hides an item, undoes that change and retries the original edit. It checks that the retry returns the old receipt without changing the current head and that undo restores byte-identical PNG output. Source bytes remain unchanged. The example client requires a new output directory and writes before/edited/restored PNGs, a snapshot and a receipt report there. Keep the external resource stores alongside the saved session.

```powershell
python examples/session_workflow.py --source C:/Exports/inkbolt-artboards/document.json --item landscape-accent --font-root C:/Exports/inkbolt-artboards/fonts --output C:/Exports/inkbolt-session
```

See [session contracts](../docs/SESSIONS.md) for direct JSON calls, named snapshots, cancellation and bounded storage. The engine stores session state; this example client writes the returned export bytes.

## MCP connection and fixed evaluations

`mcp-config.json` is a client configuration template: replace the executable path, then launch it with the mcp argument. No network listener is used. [Agent execution](../docs/AGENT_EXECUTION.md) shows discovery, edits, comparison and output publication. All CLI commands are also named MCP tools.

`mcp_evaluation.md` contains ten fixed read-only agent questions. `tests/test_mcp_evaluation.py` seeds original artwork in a temporary durable session, then solves each question using inspection, paged history, saved receipts, geometry/pixel comparisons and native image exports. Its answers are independently calculated and checked exactly; no external assets, services or model API are needed.

`python examples/mask_workflow.py C:/absolute/new-directory` creates three original diagram fragments, fades the middle group with an editable grayscale mask, exports PNG/SVG/snapshots through create-only publication and restores the original pixels with session undo. The new directory retains every artifact and its session; mask controls remain editable in `masked.json`. See [mask semantics](../docs/MASKS.md).

`python examples/selection_workflow.py C:/absolute/new-directory` creates an original PNG pattern, imports a pinned copy, selects/subtracts/softens a region, creates an editable mask, applies it at native pixel resolution and reverses both edits through session undo. All source bytes, store bytes, snapshots and exported outputs are retained separately. See [pixel selections](../docs/SELECTIONS.md).

`python examples/path_workflow.py C:/absolute/new-directory` creates a diagram with rounded cards, a polygon, a star and a cubic connector. It discovers objects by type/bounds, converts the star, splits the connector, discovers two anchors in world coordinates and moves them atomically. It publishes editable snapshots, PNG and SVG, compares changed pixels and undoes both edits to restore the original parametric shapes. See [shapes and paths](../docs/PATHS.md) for lock filters, revision-scoped indices and explicit geometry limits.

`python examples/adjustment_workflow.py C:/absolute/new-directory` generates an original color chart, imports an immutable copy, applies exposure/contrast through an editable masked tone layer, saves exact before/after and selection-weighted measurements, exports and undoes the edit. Source/cache bytes and original snapshots remain unchanged. See [adjustments and measurements](../docs/ADJUSTMENTS.md).

`python examples/color_workflow.py C:/absolute/new-directory` creates and pins an original color chart, applies a masked 3D lookup, revises it to a two-color palette map, saves numerical measurements and independently named outputs, and undoes both edits. See [color controls](../docs/COLOR_ADJUSTMENTS.md).

`python examples/filter_workflow.py C:/absolute/new-directory` pins an original chart, softens it through a masked box filter, appends an editable radial filter, publishes separate snapshots/PNGs, compares revisions and undoes both stages. See [editable viewport filters](../docs/FILTERS.md).

`python examples/detail_workflow.py C:/absolute/new-directory` pins an original chart, applies editable median cleanup and seeded noise, appends displacement/mosaic styling, publishes snapshots and PNGs, compares revisions and restores both previous images with undo. See [detail and spatial filters](../docs/DETAIL_AND_SPATIAL.md).

`python examples/channel_workflow.py C:/absolute/new-directory` pins an original chart, isolates one connected color region, refines it, retains alpha/ink channels, exports separate channel previews, masks the image and undoes both stages. Sources, metadata and snapshots remain separate and preserved. See [channels and selections](../docs/CHANNELS_AND_SELECTIONS.md).

`python examples/simplify_workflow.py C:/absolute/new-directory` reduces an original eight-segment diagram connector, retains its exact deviation certificate, publishes PNG/SVG/snapshots and restores the original commands and exports with session undo. See [curve simplification](../docs/SIMPLIFICATION.md).

`python examples/boolean_workflow.py C:/absolute/new-directory` subtracts an opening and notch from an original frame rectangle, stores the exact area/geometry report, adds the result while keeping hidden source rectangles, exports PNG/SVG/snapshots and undoes the edit. See [geometry combinations](../docs/BOOLEANS.md).

`work-path.json` creates an editable cubic work path, derives a grayscale selection and masks a colored fill. See [reusable paths](../docs/WORK_PATHS.md).

`layer-clipping.json` clips an editable gradient fill to a translucent region with a hole inside a transformed group. See [layer clipping](../docs/LAYER_CLIPPING.md).

`import-svg.json` imports an original inline SVG diagram with two editable nodes, a cubic connector and a triangular arrow. The result includes a source hash, original-ID mapping and normalization losses; pass its document to the usual edit, session and export commands. See [SVG import](../docs/SVG_IMPORT.md).

`import-svg-paints.json` imports a gradient icon with a compound clipping window and a reusable gradient template. The resolved paints and clip are independent editable copies; the receipt preserves source definition identities and reports that normalization.

`python examples/svg_text_workflow.py --font C:/Fonts/face.ttf --license C:/Fonts/LICENSE.txt --output C:/Graphics/new-svg-label` imports an original labeled SVG using an explicit pinned face, edits its label in a persistent session and writes PNG, outlined SVG, snapshots, a pixel difference and an exact undo. Optional --label and --replacement select the text. The source font, license and generated source SVG remain unchanged; an existing output directory is rejected.

`python examples/artwork_mask_workflow.py C:/absolute/new-output-directory` creates two panels with one editable gradient/shape mask source, revises both through a single source edit and verifies durable undo. Outputs are published create-only. See [the mask contract](../docs/ARTWORK_MASKS.md).

`python examples/svg_mask_workflow.py --font C:/Fonts/example.ttf --license C:/Fonts/LICENSE.txt --output C:/Graphics/new-mask-example` imports an original labeled SVG with a shared gradient/shape mask, changes both panels through one source edit and restores exact output with undo. Source files and existing destinations are preserved.

`canvas_workflow.py --output NEW_DIRECTORY` builds an original layered icon, crops and enlarges it, pads the output, sets physical resolution, publishes snapshots/PNGs and undoes the grouped edit exactly. It requires no external assets. See [canvas contracts](../docs/CANVAS.md).

`resample_workflow.py --output NEW_DIRECTORY` creates original transparent artwork and publishes smaller/larger snapshots and PNGs using area, bicubic and Lanczos3 while preserving source pixels. See [reconstruction contracts](../docs/RESAMPLING.md).

`blend_workflow.py --output NEW_DIRECTORY` creates an editable 26-cell color blend chart, publishes before/after snapshots and PNGs, and preserves both original source planes in every cell. The cell manifest identifies each mode and its placement. See [blend contracts](../docs/BLENDING.md).

`effects_workflow.py --output NEW_DIRECTORY` creates original translucent artwork with a hole, adds editable shadow/stroke/overlay effects, and exports full-fill, reduced-fill, reduced-opacity, zero-fill and seeded-dissolve variants. Original pixels and snapshots remain intact. See [layer effects and coverage](../docs/LAYER_EFFECTS.md).

`python examples/knockout_workflow.py --output <new-directory>` publishes four original editable overlapping-card variants with normal, isolated-knockout, pass-through-knockout and zero-opacity-cutout behavior. Source geometry and paint remain intact; existing files are never overwritten.

`python examples/extended_effects_workflow.py --output <new-directory>` publishes an original translucent icon and three editable variations using shared/local light, contour curves, gradient colors and effect scaling. The original pixels remain unchanged.

`python examples/dashed_stroke_workflow.py --output <new-directory>` publishes two original editable diagram-link patterns with different phase, plus PNG/SVG/snapshot artifacts and their structural/pixel comparison. Existing paths are retained, and all output publication is create-only.

## Editable stroke outlines

Run `python examples/stroke_outline_workflow.py --output C:\Temp\inkbolt-stroke-outlines` with a new destination. It publishes three original diagram links with width profiles, endpoint arrows and dashes, then creates equivalent editable filled paths. PNG outputs match byte for byte; source snapshots, SVG exports, expansion and change receipts are retained. See [STROKES.md](../docs/STROKES.md).

`python examples/variant_workflow.py --output <new-absolute-directory>` creates original vector and raster layouts, switches inherited and independent datasets, publishes snapshots and images, and proves that each selection can restore the captured source properties.

`python examples/transform_workflow.py --output <new-absolute-directory>` publishes original diagram links before and after anchored nonuniform scaling. One stroke scales with its object; the other keeps document-unit width and dash spacing. Snapshots, PNG/SVG files, expansion and comparison receipts preserve the source and disclose frozen-outline behavior.

`python examples/transfer_workflow.py --output <new-absolute-directory>` publishes an original layered component library, imports two independently editable copies into another document and changes only one copied mark. Source snapshots and existing output paths are preserved; transfer maps and pixel comparisons are retained.

### JPEG and TIFF delivery

Run `python examples/image_io_workflow.py --output C:/Exports/new-image-study` with a new destination directory. The original synthetic gradient retains an editable snapshot, publishes lossless PNG/TIFF and explicit-matte JPEG, then imports each file into an immutable asset store and publishes round-trip previews. It retains source bytes and receipts for independent pixel/error review. See [IMAGE_IO.md](../docs/IMAGE_IO.md).

### Explicit color profiles

Run `python examples/profile_workflow.py --output C:/Exports/new-profile-study` with a new destination. Original vector tiles retain a source snapshot, then publish sRGB, linear-sRGB and Display-P3 deliveries as PNG/TIFF/JPEG with exact ICC profiles, editable snapshots, conversion receipts and unchanged working-space previews. See [COLOR_PROFILES.md](../docs/COLOR_PROFILES.md).

`metadata_workflow.py --output <new-absolute-directory>` creates original diagram tiles with document/object descriptions and private working notes, publishes source/public/stripped snapshots and PNG/JPEG/TIFF/SVG, then recovers recognized image descriptions. Public manifests and provenance contain no runtime paths; full masters stay available for editable recovery.

`mesh_workflow.py --output <new-absolute-directory>` publishes an original mesh before and after an interior-knot color/alpha/position edit, with editable snapshots, derivative inspection, PNG/TIFF/SVG delivery, comparison and create-only publication receipts. See [MESHES.md](../docs/MESHES.md).

`path_text_workflow.py --font <local-font> --license <font-license> --output <new-absolute-directory> [--text INKBOLT]` retains a curved label before and after flipped traversal and a normal-offset edit. It publishes editable snapshots, glyph/baseline inspection, independent outlined copies and PNG/TIFF/SVG receipts while preserving the source font and license.

`python examples/trace_workflow.py --output <new-directory>` generates an original color/alpha icon with small defects, preserves its input PNG and asset identity, and publishes exact and cleaned traces as editable snapshots plus PNG/TIFF/SVG. Each result retains parameters, topology and source/grid hashes. See [TRACING.md](../docs/TRACING.md).

`python examples/pixel_brush_workflow.py --output <new-directory>` preserves an original pixel fixture and saves paint, erase, smudge and mixer requests, normalized inspections, edit receipts, snapshots and PNG/TIFF deliveries. See [PIXEL_BRUSHES.md](../docs/PIXEL_BRUSHES.md).

`python examples/retouch_workflow.py --output <new-directory>` preserves an original blemished texture and its donor pixels, then saves clone, heal and masked/screened heal requests, measured receipts, editable snapshots and PNG/TIFF outputs. See [RETOUCH.md](../docs/RETOUCH.md).

Run python examples/repair_workflow.py --output <new-directory> to preserve four original tasks and publish patch, content-sensitive fill/move and guided edge correction results. Each task includes its original target/source, analytic expected pixels, parameters, measured decisions and lossless PNG/TIFF/snapshot receipts. See [REPAIR.md](../docs/REPAIR.md).

`unicode_text_workflow.py --font latin=C:\fonts\latin.ttf --font arabic=C:\fonts\arabic.ttf --font indic=C:\fonts\indic.ttf --font east=C:\fonts\east.ttf --font marks=C:\fonts\marks.ttf --license C:\fonts\LICENSE.txt --output C:\deliveries\unicode-new` publishes original labels with explicit ordered fallback, language tags, glyph/font inspections and retained vector/raster snapshots. Supply fonts with the required script coverage and a license applicable to all five inputs.

`font_controls_workflow.py --font <absolute-font-path> --license <absolute-license-path> --output <new-directory>` publishes original labels at explicit weight/width coordinates, with optional ligatures/alternates/stylistic controls and path placement. Supply a font supporting the example axes, ranges and features; use `font.inspect` to inspect it first. Sources and editable vector/raster snapshots are retained.

`bidi_text_workflow.py --font <permitted-local-font> --license <license-file> --output <new-directory>` publishes fourteen original mixed-direction vector/raster labels with source snapshots, directional/glyph inspection, PNG/TIFF and vector SVG. The supplied font needs Latin, Hebrew/marks, Arabic, digits and parentheses. See [BIDI_TEXT.md](../docs/BIDI_TEXT.md).

Run `python examples/pdf_workflow.py --output <new-directory>` for an original two-page vector diagram with separate previews, ordered PDF pages, asymmetric bleed and retained editable source. PDF text, color and import boundaries are documented in [PDF.md](../docs/PDF.md).

`python examples/background_workflow.py --output NEW_DIRECTORY` retains original transparent artwork through background promotion, independent duplicate editing, ordinary-layer conversion and source restoration, with PNG/TIFF/PDF deliveries.

`python examples/background_workflow.py --output NEW_DIRECTORY` retains original transparent artwork through background promotion, independent duplicate editing, ordinary-layer conversion and source restoration, with PNG/TIFF/PDF deliveries.

`python examples/coordinate_workflow.py --output NEW_DIRECTORY` saves an original fractional layout, SVG, reimported snapshot and matching previews while preserving all source coordinates.

`sample_conversion_workflow.py --output <new-directory>` creates an original 16-bit PNG, imports retained samples, converts a copy to explicit linear-luminance grayscale and publishes snapshots, native-depth TIFF and a display preview. See [sample contracts](../docs/SAMPLES.md).

`hdr_workflow.py --output <new-directory>` retains an original signed radiance chart, applies reversible exposure, measures full-precision values and publishes native float TIFF plus explicit clip/Reinhard previews. See [HDR contracts](../docs/HDR.md).

`assisted_layout.py PATH_TO_ENGINE NEW_OUTPUT_DIRECTORY` produces an original icon sheet, an inspectable optimal row proposal, preserved source and arranged snapshots, and before/after PNG plus SVG/PDF delivery. See [local assistance](../docs/ASSISTANCE.md).

`pixel_assistance.py PATH_TO_ENGINE NEW_OUTPUT_DIRECTORY` runs original selection, editable mask, texture removal, self-guided denoise and upscale workflows, retaining source snapshots, exact requests/responses and independent comparison references. See [local pixel assistance](../docs/PIXEL_ASSISTANCE.md).

`creative_workflow.py OUTPUT_DIRECTORY` creates ten original, editable graphic treatments and PNG deliveries in a fresh directory. See [CREATIVE_FILTERS.md](../docs/CREATIVE_FILTERS.md).

`sample_profile_workflow.py --output NEW_DIRECTORY` demonstrates source-profile assignment versus conversion on an original float chart, with editable snapshots and PNG deliveries. See [SAMPLE_PROFILES.md](../docs/SAMPLE_PROFILES.md).

`python examples/format_workflow.py --output <new-directory>` produces original BMP/TGA/GIF/TIFF deliveries and an editable timed sequence; the output directory must not exist.

`proof_workflow.py --output NEW_DIRECTORY [--profile OUTPUT_ICC]` retains an original source chart, compares relative/absolute colourimetric views, writes exact process-ink planes and difference masks, and exports the matching print PDF. Omission uses an explicitly labelled analytic demonstration profile. See [PRINT_PROOF.md](../docs/PRINT_PROOF.md).
