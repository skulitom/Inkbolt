# Inkbolt

Curved strokes now refine automatically for their current placement while preserving saved controls. Rendering, expansion and outlined exports share that geometry through the supported output scales. The full resource checkpoint remains partial; the verified total stays **161/167 (96.41%)**. See [stroke precision](docs/STROKES.md).

Sparse vector previews now evaluate only each object's affected region, and coverage places controls before rounding them for drawing. The original 5,000-shape sparse scene and extreme-transform regressions have explicit geometry/pixel checks. Resource acceptance remains in progress at **161/167 (96.41%)**; see [large vector documents](docs/LARGE_VECTOR.md).

Agents can opt into large vector documents, retaining thousands of editable objects through snapshots, SVG/PDF, PNG previews and saved history. Explicit storage profiles preserve independent processing limits. This is partial resource work; the verified total remains **161/167 (96.41%)**. See [large vector documents](docs/LARGE_VECTOR.md).

Agents can exchange authored scalar masks on pixel layers and folders while preserving source pixels, separate mask bounds, linking, disabled state, byte density and uniform empty planes. Native feather and combined-mask controls remain explicit unsupported cases. This partial extended interchange adds no checkpoint credit: **161/167 (96.41%)**. See [layered interchange](docs/LAYERED.md).

Agents can exchange nested normal and pass-through folders, including empty and hidden groups, while retaining original layer pixels and sibling order. Group transforms become absolute native pixel placements, and export receipts flag unnamed layers that native consumers may rename. This is partial extended interchange; the verified total remains **161/167 (96.41%)**. See [layered interchange](docs/LAYERED.md).

Agents can select standard or large native layered containers, preserving original RGB8 pixels and explicit profile policy. Large-container framing and thin canvases through 32,768 pixels are implemented; extended interchange remains in progress and adds no checkpoint credit. See [layered interchange](docs/LAYERED.md).

Agents can exchange a bounded native RGB8 pixel-layer subset while retaining original layer pixels, names and visibility. Basic native layered interchange is independently verified; see [layered interchange](docs/LAYERED.md).

Agents can prepare native process/spot planes and flattened PDF pages with physical print marks, retain source objects and shared inks, explicitly project HDR views and apply profile-managed adjustment layers. Checkpoint verification and remaining work are tracked in the [implementation report](docs/IMPLEMENTATION.md). See [source contexts](docs/NATIVE_CONTEXTS.md) and [native adjustments](docs/NATIVE_ADJUSTMENTS.md).

Agents can inspect native artwork ink planes, retain image profiles and native sample precision, apply shared masks, raster clipping stacks, native blend modes, knockout groups, seeded coverage, native layer effects and all 21 editable viewport filters, retain perspective/mesh/articulated image warps calibrated raw development retained native objects and explicit shared-ink bindings, and deliver flattened process/spot PDF pages with physical crop and registration marks. Broader native compositing remains in progress; this partial work adds no checkpoint credit. See [VECTOR_PLATES.md](docs/VECTOR_PLATES.md) and [NATIVE_FILTERS.md](docs/NATIVE_FILTERS.md).

Agents can deliver combined process and named ink plates, inspect reference previews and query profile-supplied gamut classifications. See [COMBINED_PREPRESS.md](docs/COMBINED_PREPRESS.md).

Agents can retain editable named-ink and duotone recipes, inspect exact scalar plates and deliver independent DeviceN PDF inks while preserving original channels and masks. See [INK_RECIPES.md](docs/INK_RECIPES.md).

Agents can inspect calibrated print previews, exact CMYK ink planes and measured colour differences while preserving editable artwork. See [PRINT_PROOF.md](docs/PRINT_PROOF.md).

Agents can export calibrated CMYK image pages with an explicit printing profile, matte and sample density while preserving editable sources. See [PRINT_CMYK.md](docs/PRINT_CMYK.md).

Agents can exchange exact BMP/TGA pixels, palette-based GIF stills/sequences and explicit associated TIFF alpha, with source preservation and declared metadata/profile limits. See [EXTENDED_IMAGE_IO.md](docs/EXTENDED_IMAGE_IO.md).

Agents can retain exact raw captures, revise lens correction and noise/detail settings, exchange pinned sidecars and undo changes. See [RAW_EDITING.md](docs/RAW_EDITING.md).

Agents can develop explicitly calibrated Bayer sensor buffers with exposure, white balance, colour conversion and native output precision. Source fingerprints, repeatable recipes and range diagnostics accompany each new image. See [RAW.md](docs/RAW.md).

Agents can retain curved union, intersection, subtraction and xor regions, edit individual components, and reuse them as selections or independent vector masks. Source controls and agent history remain editable. See [COMPOUND_REGIONS.md](docs/COMPOUND_REGIONS.md).

Agents can assign or convert retained source RGB profiles at native precision, choose explicit rendering intent and preserve source bytes/history. Colour interpretation precedes linear or encoded compositing. See [SAMPLE_PROFILES.md](docs/SAMPLE_PROFILES.md).

Agents can select foreground objects from local colour/edge evidence, retain editable masks, remove selected content, reduce noise and enlarge graphics with explicit reconstruction. These CPU workflows preserve original sources and require no model downloads. See [PIXEL_ASSISTANCE.md](docs/PIXEL_ASSISTANCE.md).

Agents can inspect and apply an optimal ordered row layout for diagrams and icon sheets, preserving editable objects and source history. The built-in CPU method has no model or network dependency. See [ASSISTANCE.md](docs/ASSISTANCE.md).

Agents can retain original profiles as editable extruded and rotated artwork, control cameras and local lighting, and expand projected vector faces with undo. Offline execution and independent geometry/delivery checks are verified. See [VOLUMES.md](docs/VOLUMES.md).

Agents can retain one vector source with ordered fills, strokes, vector maps and raster effects, expand independent editable objects or explicitly bake delivery, and undo each change. See [APPEARANCE.md](docs/APPEARANCE.md).

Agents can import ordered images or animated PNG, retain exactly timed editable frames, export PNG/APNG and deliver a selected still to Cutbolt with explicit losses. See [SEQUENCES.md](docs/SEQUENCES.md).

Agents can deliver ordered vector pages with declared trim, asymmetric bleed, spot inks and per-paint overprint, retaining editable snapshots and explicit page receipts. See [PREPRESS.md](docs/PREPRESS.md).

Agents can flow shared rich paragraphs through linked frames and columns, retain overflow, control spacing, generate nested lists and render rule-driven hyphens with inspectable source positions. Named paints, native ink delivery, independent resource transfer and saved history use the same source-preserving contract. See [STORIES.md](docs/STORIES.md) and [HYPHENATION.md](docs/HYPHENATION.md).

Agents can retain editable vector/raster sources inside raster layouts, reopen their exact source bytes, replace independent copies and explicitly check or refresh local links. See [OBJECTS.md](docs/OBJECTS.md) for source retention, reconstruction, resource and delivery contracts.

Agents can retain signed HDR radiance, composite in an explicit linear working space, inspect full-precision samples, edit reversible exposure and deliver native float TIFF or explicitly tone-mapped previews. See [HDR.md](docs/HDR.md) for supported operations and mode diagnostics.

Agents can import 8/16-bit PNG and 8/16/normalized-float TIFF without reducing depth, explicitly convert depth or grayscale policy, preserve source files and undo edits. See [SAMPLES.md](docs/SAMPLES.md) for exact contracts; explicit HDR contracts are in [HDR.md](docs/HDR.md).

Raster sample grids now retain explicit 8-bit, 16-bit or normalized floating-point RGB/grayscale values through editing, compositing and TIFF delivery. See [SAMPLES.md](docs/SAMPLES.md) for native replacement, depth selection and current conversion/HDR boundaries.

Agents can deliver exact named inks and overprint instructions in PDF, explicitly convert spot/process definitions and inspect separation diagnostics; see [INK_DELIVERY.md](docs/INK_DELIVERY.md).

Agents can retain named process colors, spot declarations and exact tint references, recolor shared artwork, copy independent palettes and explicitly bake display previews for delivery; see [SWATCHES.md](docs/SWATCHES.md).

Agents can measure rotated bounds and certified authored area/length, set physical dimensions and snap to explicit grids, items and oblique guides while retaining editable source; see [DIMENSIONS.md](docs/DIMENSIONS.md).

Agents can choose image resolution, geometric antialiasing, encoded or linear-light sample averaging and explicit effect bounds while retaining editable sources. PNG/JPEG/TIFF, artboard ranges and create-only agent publication share these controls; see [RENDER_QUALITY.md](docs/RENDER_QUALITY.md).

A local vector and raster editing engine for agents. Sister to Cutbolt: Cutbolt handles time; Inkbolt will handle paths, pixels and layered documents.

**Status: 161/167 verified (96.41%); basic layered pixel interchange, 8 October 2026.** Agents can retain profiled CMYK, Lab and grayscale paints, choose all four rendering intents, inspect supplied gamut diagnostics and deliver exact profiles in calibrated PDF pages. Assignment, conversion, source preservation and durable agent workflows are verified; see [DEVICE_COLOR.md](docs/DEVICE_COLOR.md). Agents can preserve fractional canvas and artboard sizes, nonzero origins, physical units and explicit RGB/CMYK page intent; see [VECTOR_CANVAS.md](docs/VECTOR_CANVAS.md). Agents can preserve negative/fractional geometry exactly through stored snapshots and SVG literals, with explicit normalization and preview boundaries; see [COORDINATE_PRECISION.md](docs/COORDINATE_PRECISION.md). Agents can retain original pixels and transparency while creating opaque backgrounds, restore the source or convert to ordinary editable layers, and independently edit duplicates with explicit locks; see [BACKGROUNDS.md](docs/BACKGROUNDS.md). Agents can publish ordered artboard pages with native vector paths, verified glyph outlines, transparency, bleed and explicit physical sizes; see [PDF.md](docs/PDF.md). Agents can combine left-to-right and right-to-left scripts, preserve paragraph direction across wrapping, inspect reading order and deliver mirrored punctuation and attached marks; see [BIDI_TEXT.md](docs/BIDI_TEXT.md). Agents can discover local font axes/features, retain per-font instances, control ligatures/alternates/kerning, and deliver consistent glyph outlines, metrics and path text; see [FONT_CONTROLS.md](docs/FONT_CONTROLS.md). Agents can shape script runs with ordered pinned font fallback, joining context, combining marks and language-specific substitutions, preserving original text and inspecting actual glyph/font selection; see [UNICODE_TEXT.md](docs/UNICODE_TEXT.md). The Rust library and JSON CLI create editable vector and pixel documents with rounded rectangles, polygons, stars and compound paths. Agents can retain original pixels while editing perspective, mesh and joint-driven deformations, inspect unique inverse maps and deliver clipped, seam-free sampled images; see [PIXEL_WARPS.md](docs/PIXEL_WARPS.md). Agents can retain original vector geometry under editable perspective and nonlinear envelope stacks, inspect control positions and curved grids, and expand paths with exact rational error certificates; see [WARPS.md](docs/WARPS.md). Agents can retain closed vector motifs in brick, hexagonal, radial and mirrored layouts with shared seam coverage, editable transforms and ordinary vector expansion; see [REPEATS.md](docs/REPEATS.md). Agents can generate a fixed number of editable steps between shapes and colors, including unequal topology, curved spines, orientation, reversal and atomic expansion; see [INTERPOLATION.md](docs/INTERPOLATION.md). Agents can retain original brush motifs along paths, edit spacing and variable width, control corners/endpoints and expand matching filled artwork; see [VECTOR_BRUSHES.md](docs/VECTOR_BRUSHES.md). Agents can repair patches, fill from local content, move selected objects while reconstructing their original region, and correct noise using edge guidance, with explicit match/change/seam limits; see [REPAIR.md](docs/REPAIR.md). Agents can clone and heal explicit pixel regions with frozen sources, affine sampling, masks, measured boundaries and independently verified solver accuracy; see [RETOUCH.md](docs/RETOUCH.md). Agents can paint, erase, smudge and mix native pixels with integrated tip coverage, programmatic dynamics, textures and seeded scatter; see [PIXEL_BRUSHES.md](docs/PIXEL_BRUSHES.md). Agents can trace original images into editable color/alpha contours with exact cell boundaries, preserved corners/holes and explicit noise controls; see [TRACING.md](docs/TRACING.md). Agents can place editable text on straight or curved baselines, control offsets/side/overflow and inspect glyph poses before outline delivery; see [PATH_TEXT.md](docs/PATH_TEXT.md). Agents can create shared color meshes, move interior knots, edit transparency and inspect smooth joins, with continuous raster output and bounded sampled SVG delivery; see [MESHES.md](docs/MESHES.md). Agents can retain document/object descriptions, separate private working notes, publish public or stripped metadata, inspect resource manifests and retain deterministic delivery provenance; see [METADATA.md](docs/METADATA.md). Agents can explicitly convert ICC-tagged RGB input and associate reproducible output profiles with documents for PNG/JPEG/TIFF delivery; see [COLOR_PROFILES.md](docs/COLOR_PROFILES.md). Image import and delivery support JPEG and TIFF alongside PNG, with explicit JPEG mattes and quality, lossless TIFF alpha, immutable imports and create-only publication; see [IMAGE_IO.md](docs/IMAGE_IO.md). Agents can copy selected layers and artwork between documents with ancestor context, shared-component/mask dependencies, independent IDs and explicit resource verification; see [TRANSFER.md](docs/TRANSFER.md). Affine transforms now support explicit object-scaled or fixed document-width strokes through hierarchy, pivots, reflections and shear; see [TRANSFORMS.md](docs/TRANSFORMS.md). Vector strokes now retain editable dash patterns, phase, width profiles and five endpoint arrowhead shapes, with original shared outline geometry for rendering, SVG exchange and atomic editable expansion. Reusable vector components now share editable definitions across placements, with local overrides, nested copies, replacement and safe unlinking; see [COMPONENTS.md](docs/COMPONENTS.md). Editable datasets now control text, images, visibility, placement and appearance subsets in both document kinds, with inherited variants and captured base values; see [VARIANTS.md](docs/VARIANTS.md). Agents can discover objects by type and world bounds, inspect selected anchors, edit anchors/handles and split, join, reverse or simplify contours with checked deviation and topology. Agents can also combine filled geometry with union, intersection, subtraction and xor, with exact polygon area, shared evaluation of equivalent curve pieces and exact rational contact splits and topology-certified chord boundaries; unresolved curved contacts fail explicitly. Nonprinting work paths now provide editable raster regions, path-derived selections and copied vector masks. Raster canvas operations now crop, resize the visible extent, scale editable content with nearest, bilinear, area, bicubic or Lanczos3 sampling and update physical resolution. Printable items now support separate content fill and overall opacity, editable shadows/strokes/color overlays with shared or local lighting, independent geometry scaling, custom coverage curves and gradient colors, plus seeded dissolve coverage combined with all 26 color blend modes. Groups now support editable knockout with distinct footprints, nested isolation/pass-through behavior and all 26 blend modes. Raster layers now support alpha-preserving clipping groups, with editable pass-through opacity and masks. The engine also supports shared editable artwork masks built from shapes, gradients and text, layers, transforms, clips, grayscale masks, alignment, gradients/patterns, immutable PNG/JPEG/TIFF assets, pixel selections/refinement, saved alpha/ink channels, component calculations, color-range/connected selections, mask application, reversible tone/color adjustment layers with lookup tables and gradient maps, editable masked blur/detail/spatial stacks, selection/alpha-weighted histograms and samples, styled text and independently exported artboards. Edits run as atomic batches, with optional persistent sessions, undo/redo, named snapshots and safe retry receipts. See the [implementation report](docs/IMPLEMENTATION.md) for verified progress against all 167 planned checkpoints. MCP stdio exposes all engine commands, with change comparisons and create-only file publication. Bounded SVG import now creates editable shapes, groups, gradients, geometric clips, shared editable artwork masks and single-line text with explicitly bound fonts from local UTF-8 files or inline text, with source receipts and explicit unsupported-feature errors. Broader page import and editable PDF reimport remain required; extended print preparation is verified.

Inkbolt runs locally without a hosted API, network listener, account or telemetry. Requests and responses are structured JSON, with strict fields and explicit errors. Snapshot editing returns a new document; session commands persist revisions under an explicit local root. Exports can return data or publish a complete new file under an explicit output root; existing destinations are never overwritten.

## Run

Requires Rust/Cargo and Python 3.11+ for development checks. Dependencies are pinned in Cargo.lock and fetched to the normal external package cache.

```powershell
cargo build --locked
.\target\debug\inkbolt.exe capabilities
.\target\debug\inkbolt.exe examples/create-vector.json
.\target\debug\inkbolt.exe examples/create-raster.json
.\target\debug\inkbolt.exe schema
.\target\debug\inkbolt.exe mcp
python tools/verify.py
```

Send one request on stdin, or pass one request file. Success is `{"ok":true,"result":...}` with exit code 0. Failure is `{"ok":false,"error":{"code":"...","message":"..."}}` with exit code 1. Snapshot edits and ordinary exports return data without writing output files. document.publish/session.publish add explicit create-only output publication. Session commands store versioned editing state in an explicit local database; see [session persistence](docs/SESSIONS.md) for recovery, limits and examples. `asset.import` and `font.import` publish create-only content-addressed copies to explicit local roots, preserving their sources. Fonts require retained license text and remain external to snapshots. See [the agent interface](docs/AGENT_INTERFACE.md) and [original examples](examples/README.md).

## Direction

- Vector: paths, fills, strokes, groups, transforms, typography and artboards.
- Raster: tiled pixels, layers, masks, selections, compositing and adjustments.
- Shared: stable object IDs, explicit color semantics, transactional sessions, previews, undo and repeatable exports.
- Agent workflow: inspect, plan, apply, review, recover; expose the same contracts through CLI, library and MCP stdio.

See [vector strokes](docs/STROKES.md), [knockout groups](docs/KNOCKOUT.md), [layer effects and coverage](docs/LAYER_EFFECTS.md), [color blending](docs/BLENDING.md), [image reconstruction](docs/RESAMPLING.md), [raster canvas operations](docs/CANVAS.md), [editable artwork masks](docs/ARTWORK_MASKS.md), [SVG import](docs/SVG_IMPORT.md), [layer clipping](docs/LAYER_CLIPPING.md), [reusable paths and pixel regions](docs/WORK_PATHS.md), [geometry combinations](docs/BOOLEANS.md), [curve simplification](docs/SIMPLIFICATION.md), [channels and image-guided selection](docs/CHANNELS_AND_SELECTIONS.md), [detail and spatial controls](docs/DETAIL_AND_SPATIAL.md), [editable filters](docs/FILTERS.md), [color controls](docs/COLOR_ADJUSTMENTS.md), [adjustments and measurements](docs/ADJUSTMENTS.md), [shapes and paths](docs/PATHS.md), [pixel selections](docs/SELECTIONS.md), [editable masks](docs/MASKS.md), [architecture](docs/ARCHITECTURE.md), [roadmap](docs/ROADMAP.md), [dependencies](docs/DEPENDENCIES.md), and [research boundaries](docs/RESEARCH.md).

## Private research and publication

The original source, contracts and synthetic fixtures belong here. Application-specific research, target identities and audit evidence belong in an external private directory. Audit tools are development tools, not runtime dependencies.

This checkout has a Git-private content policy and local pre-commit check. They are not transferred by cloning. To prepare another checkout, supply its private policy file and an external research directory:

```powershell
python tools/setup_private.py --research-root "<external-private-directory>" --policy "<external-policy-file.json>"
python tools/check_repo.py
python tools/check_repo.py --staged
```

The check fails when policy is missing and inspects actual staged bytes, including forced additions. Ignore rules and hooks reduce accidental publication; they do not prove provenance or replace full history review. A hidden folder is a visibility convenience, not access control.

Original Inkbolt code is [MIT licensed](LICENSE). Dependencies retain their own licenses, reproduced in [third-party notices](THIRD_PARTY_NOTICES.md). The repository material checker is adapted from Cutbolt under the same license; its notice is retained.

For MCP clients, copy [the configuration example](examples/mcp-config.json) and replace its executable path with your built binary. The adapter is a subprocess using stdin/stdout, not a background network service. See [agent execution](docs/AGENT_EXECUTION.md) for tool discovery, cancellation, diffs, output receipts and limits.
