# Agent interface

For compact MCP discovery and focused `schema.lookup` queries, see [agent discovery](AGENT_DISCOVERY.md). Full CLI schemas and command results remain available. [Agent readiness](AGENT_READINESS.md) tracks the broader interface and workflow improvements separately from engine checkpoints.

Use an explicit [workspace](AGENT_WORKSPACE.md) for default resource/session roots and relative runtime paths. Top-level snapshot inputs also accept exact saved revision references; the same JSON preparation and typed execution serve CLI and MCP.

Snapshot file references require a path and exact byte hash from create-only publication. Durable session commands accept optional [compact responses](AGENT_RESPONSES.md), retaining pinned recovery references while omitting repeated snapshot bodies. Full responses remain the default.

Use `document.inspect.page` for content-bound pages of selected fields, resource inventories and path anchors. MCP `response_format:"preview"` sends image bytes once with explicit references and preserves all metadata. See [inspection and preview delivery](AGENT_INSPECTION.md).

Native layered exchange now maps nested normal/pass-through folders to explicit parent references, validates balanced boundaries and keeps empty groups without manufacturing pixels. Native import/export, declared loss receipts and durable agent workflows share this contract. Extended interchange remains partial and uncredited; larger axes, masks, text and embedded objects are still required.

Use `format:"layered_large"` for explicit version-two native publication with `.psb`; `layered.import` detects either supported container version. Discover both formats and current axis/storage limits through `capabilities.layered_interchange`. This partial extension does not complete the extended checkpoint.

Native pixel interchange: `layered.import` accepts a local source path, optional SHA-256 and explicit colour policy. `document.export` and create-only publication accept `format:"layered"`; supported ordinary RGB8 layers remain separate and editable. The basic native layered interchange checkpoint is verified; extended structures remain in scope. Read [LAYERED.md](LAYERED.md) for exact bounds, cache transparency, unsupported semantics and metadata rules.

Inspect native artwork process/spot planes, including retained-profile image sources with `document.prepress`; deliver those exact planes with `pdf_options.prepress`, an explicit CMYK `profile` and optional physical `marks`. Spots require `spot_fallback:"multiplicative_declared"`. Ordered artboards, asymmetric bleed, public/stripped metadata and create-only publication share the same preparation. Shared artwork masks and raster clipping stacks retain native ink values and return `coverage_sources` in plane and page receipts. All 26 native blend modes, knockout, filters and retained source objects expose their ink and coverage rules in receipts. Explicit HDR views follow NATIVE_CONTEXTS.md. Adjustment layers require `adjustment_policy:"profiled_process_preserve_spots"`; see NATIVE_ADJUSTMENTS.md. Discover `capabilities.native_prepress` and complete-checkpoint status through `implementation.status`. See [VECTOR_PLATES.md](VECTOR_PLATES.md).

Use `print.named_inks` with an explicit multiplicative CMYK alternate map to deliver process and recipe plates together. `document.proof` returns exact plates and reference appearance; `profile.gamut` inspects pinned ICC gamut tables. Discover `capabilities.profile_gamut` and the strict tool schemas. Missing tables and PCS overflow are explicit. See [COMBINED_PREPRESS.md](COMBINED_PREPRESS.md).

Use atomic `ink_recipe` edits to retain named inks, source curves and optional masks. Read `document.separations` for exact plates and a declared mixture preview; select `pdf_options.ink_recipe` for independent DeviceN PDF delivery. Discover bounds under `capabilities.ink_recipes`. See [INK_RECIPES.md](INK_RECIPES.md).

Use `pdf_options.print` with a supplied CMYK profile and explicit matte for calibrated flattened page delivery. `raster_scale` controls sample density without changing page dimensions. CLI, library and MCP share the contract; discover `capabilities.print_cmyk` and read [PRINT_CMYK.md](PRINT_CMYK.md).

`raw.retain`, `raw.recipe` and `raw.reopen` keep exact sensor captures and strict versioned sidecars. `raw_settings` replaces development controls atomically; `raw_expand` explicitly materializes native pixels. See [RAW_EDITING.md](RAW_EDITING.md) for lens, noise/detail, storage and history contracts.

`raw.develop` requires explicit sensor layout/calibration and development settings. It returns native sample artwork, a source-pinned recipe and range/clipping diagnostics. Discover packing and bounds under `capabilities.raw_development`. See [RAW.md](RAW.md).

`volume.inspect` exposes retained extrusion/rotation, camera, material and projected faces. `volume` and `volume_expand` use ordinary atomic edits and history. See [VOLUMES.md](VOLUMES.md) for current bounds and verification status.

`appearance.inspect` reads shared geometry and ordered paint passes. Atomic `appearance`, `appearance_expand` and `appearance_bake` edits preserve source snapshots, locks, history and explicit loss receipts. Discover bounds and supported controls under `capabilities.appearance`; see [APPEARANCE.md](APPEARANCE.md).

Four sequence commands expose ordered local import, exact timing inspection, editable frame reopening and PNG collections; ordinary publication also accepts APNG. See [SEQUENCES.md](SEQUENCES.md) for strict schemas, resource limits and loss boundaries.

A story can retain `hyphenation_rules`; paragraphs select them through `hyphenation.rules_id`. `story.inspect` reports inserted-hyphen metadata, virtual display direction and source-preserving glyph clusters. Named paints now include body, character ranges and list-marker styles, with normal palette/lock/transfer/native-ink contracts. See [STORIES.md](STORIES.md).

Shared story paragraphs accept optional `list` specifications for bullets and numbered/nested items. `story.inspect` and `text.inspect` distinguish body glyph intervals from generated marker intervals and expose labels/counters. Change list specifications with `story` edits; `story_range` continues to edit body text only. See [STORIES.md](STORIES.md) for positioning, limits, resource dependencies and history.

`story.inspect` reports a shared story's slot layouts, consumed source ranges and unplaced tail. `story` and `story_range` edits retain original paragraphs; `story_frame` items independently place ordered flow slots. `text.inspect` also accepts these placements. See [STORIES.md](STORIES.md) for overflow policy, columns, resource locks, persistence and current exclusions.

`text.hyphenate` inspects explicit weighted rules and exception overrides for a token batch. It returns source scalar break positions filtered by grapheme boundaries and edge minima, preserves original text and accepts cancellation/deadline controls. The inspection command does not alter layout or load dictionaries; story paragraphs can now select stored rule sets to render visible hyphens. See [HYPHENATION.md](HYPHENATION.md).

Use `object.import` to retain a local engine snapshot, `object.open` to reopen its exact source, and `object.status` to inspect or explicitly check a link. Atomic `object_replace`, `object_refresh` and `object_detach` operations retain ordinary session/history contracts. Link reads require an explicit root; refresh requires the observed source SHA-256. See [OBJECTS.md](OBJECTS.md).

Select raster `color_space:"linear_srgb"` explicitly with `working_space`; retained linear grids use `encoding:"linear_srgb"` and `depth:"f32"`. Edit `hdr_grade`, inspect `sample.measure`, import with `assume_linear_srgb` and select `render_options.view` for display delivery. See [HDR.md](HDR.md) for supported operations, signed ranges and explicit diagnostics.

Use `content.type:"samples"` with explicit grid `depth` and `channels`, import PNG/TIFF with `sample.import`, edit native bytes with `sample_replace`, convert depth/grayscale with `sample_convert`, and select TIFF delivery with `image_options.depth`/`channels`. Discover bounds, byte hashes and pending precision limits under item inspection and `capabilities.sample_precision`; see [SAMPLES.md](SAMPLES.md).

Vector print preparation: combine explicit artboard selection, saved bleed and native ink PDF delivery; page receipts expose trim, physical units and selected ink inventories. See [PREPRESS.md](PREPRESS.md).

Native ink delivery: `pdf_options.color:"native_inks"`; inspect `swatch.inspect.ink_diagnostics`, edit `swatch_convert`, and retain per-paint overprint. See [INK_DELIVERY.md](INK_DELIVERY.md).

`swatch.inspect` reports named color declarations, tint dependencies, users and available display previews. The atomic `swatch` edit inserts/replaces definitions or deletes an unused resource; `swatch_bake` explicitly replaces selected current references with display-RGBA literals. Snapshot values remain exact, and vector delivery rejects unresolved spot/non-RGB semantics. See [SWATCHES.md](SWATCHES.md).

`geometry.measure` returns rotated geometry bounds, physical dimensions and certified authored contour metrics. The atomic `dimensions` and `snap` operations retain source content and expose placement receipts. Discover exact options and limits under `dimensions` and `snapping`; see [DIMENSIONS.md](DIMENSIONS.md). `document.measure` continues to measure composite pixels.

`render_options` on render/image-export/artboard-export requests, or inside publication `output`, controls antialiasing, supersample averaging and effect padding. Discovery reports exact choices under `render_quality`. Receipts report evaluation/output dimensions and origin; editable source and revision stay unchanged. See [RENDER_QUALITY.md](RENDER_QUALITY.md).

Inspect `capabilities.coordinate_precision` for exact stored-number transport through snapshots/SVG, normalization boundaries, coordinate limits and the separate display-coverage contract. See [COORDINATE_PRECISION.md](COORDINATE_PRECISION.md).

Raster background conversion uses `background` edits with `promote`, `restore_source` or `to_layer` actions. Original pixels/alpha and appearance stay editable, locks remain explicit, and inspection separates source geometry from the current-canvas matte. See [BACKGROUNDS.md](BACKGROUNDS.md) for clipping, duplication, conversion and delivery contracts.

Set optional `item.pixel_warp` on inline pixel layers or placed images, or use the `pixel_warp` edit with typed perspective/mesh/articulated controls. `warp:null` clears them without changing source pixels. `pixel_warp.inspect` accepts source-frame dimensions and forward/inverse samples, returning evaluated vertices, triangles and joint matrices. Inspect `capabilities.pixel_warps` and [PIXEL_WARPS.md](PIXEL_WARPS.md) for inverse, edge coverage, limits and native-edit boundaries.

Use `content.type:"warp"` with original geometry, paint and ordered affine/perspective/envelope `maps`. `warp.inspect` returns source controls, mapped samples, optional reusable grids and exact segment error bounds. The `warp` edit updates controls; `warp_expand` preserves the item as ordinary vector geometry. Tolerance is in warp-local units and paint/stroke apply after deformation. Inspect `capabilities.warps` and [WARPS.md](WARPS.md).

Use `content.type:"repeat"` with closed motif geometry, fill and typed layout settings. `repeat.inspect` returns count, centers, matrices and optional combined geometry. The `repeat` edit replaces controls; `repeat_expand` preserves the item as ordinary compound vector geometry. Coincident boundaries paint once; mirrored copies preserve authored winding. Inspect `capabilities.repeats` and [REPEATS.md](REPEATS.md).

Use `content.type:"interpolation"` with original vector endpoints and a count including both endpoints. `interpolation.inspect` reports placement, topology matching, colors and optional geometry. The `interpolation` edit replaces controls; `interpolation_expand` creates ordinary editable vector children. Curved spines, unequal topology, orientation, reversal and persistence are supported within the explicit solid-color and correspondence contract. Inspect `capabilities.interpolation` and [INTERPOLATION.md](INTERPOLATION.md).

Vector `stroke.brush` accepts original closed motif geometry, spacing/phase, fixed or uniform fitting, endpoint/corner motifs and clearance. Width profiles control uniform motif scale. Use the `vector` edit for changes, `document.inspect` for saved controls and `stroke_expand` for ordinary filled geometry. Shared hierarchy, masks, paint, snapshots, history and SVG delivery apply. Inspect `capabilities.vector_brushes` and read [VECTOR_BRUSHES.md](VECTOR_BRUSHES.md) for exact units, winding, scaling and limits.

One UTF-8 JSON request per invocation, at most 16 MiB. Pass a file path or write to stdin. `capabilities`, `schema` and `implementation.status` are argument shorthands. Stdout contains one JSON envelope. The engine exposes no network listener or hosted service. Document edits/exports return data; asset.import and font.import create immutable cache files under an explicit store_root.

| Command | Request fields besides command | Result |
| --- | --- | --- |
| capabilities | none | Actual commands, limits, supported subsets and unavailable features |
| schema | none | JSON Schema for the request union |
| implementation.status | none | All 167 acceptance checkpoints, status and named evidence |
| color.convert | source, destination, values; optional intent, control | Explicit device RGB/gray/CMYK and D50 Lab conversion, exact profile hashes, directional tables, PCS and clipping receipts; see DEVICE_COLOR.md |
| mesh.inspect | mesh; optional space, parameters | Shared-knot positions, tangents, colors, derivatives, inverse parameters and certified deformation bounds; see MESHES.md |
| artboard.export | document, format; optional image_options, selection, scale, include_bleed, asset_root, font_root | Ordered artifacts and source/trim bounds; whole-request success or structured failure |
| font.import | source_path, license_path, store_root; optional face_index (0) | Pinned font descriptor, with separately retained license text |
| font.verify | font; optional font_root | Verify font/license bytes and parse the requested face |
| text.inspect | document, id; optional font_root, include_outlines (false) | Source frame, glyph/line metrics, local/world ink bounds; optional painted outlines |
| sample.measure | document; optional points, asset_root, font_root | Full-precision rendered samples, minima/maxima and negative/above-white channel counts; no display projection |
| sample.import | source_path, id; optional resolution_ppi (96), color_policy | New inline native-depth raster document, immutable-source hash and interpretation/loss receipts; see SAMPLES.md |
| asset.import | source_path, store_root; optional color_policy, input_profile | Pinned image asset, created flag, source_format and metadata losses |
| asset.verify | asset; optional asset_root | Verify embedded/stored pixel identity and dimensions |
| asset.embed | asset; optional asset_root | An equivalent small embedded asset descriptor |
| document.create | id, kind, width, height; optional resolution_ppi | Empty schema-v2 snapshot at revision zero |
| document.validate | document | Validated, normalized snapshot |
| document.inspect | document | Stack order, IDs, visibility, locks and geometric bounds |
| document.boolean | document, ids, mode; optional curve_tolerance (0.125) | New root-coordinate polygon or null, exact area and explicit approximation/topology diagnostics; see BOOLEANS.md |
| channel.export | document, id; optional display (gray or ink) | Scalar or alternate-ink preview PNG with retained identity metadata; see CHANNELS_AND_SELECTIONS.md |
| document.measure | document; optional options, asset_root, font_root | Exact composite histograms/statistics/samples with selection and alpha weights; see ADJUSTMENTS.md |
| document.select | document, ids | Read-only explicit selection with parent, effective locks/visibility and world bounds |
| document.query | document, query | Read-only discovery by type/shape/world bounds, with optional anchor bounds and local/world handles; see PATHS.md |
| document.edit | document, expected_revision, operations; optional asset_root, font_root for image-guided sampling/outlines and control | New document, from_revision and ordered change receipts |
| document.separations | document; optional scale/control | Exact recipe ink planes, declared mixture preview and source hashes; read-only |
| document.proof | document, options with explicit print profile/matte and difference threshold; optional roots/control | Calibrated preview, exact CMYK planes, PCS differences and clipping diagnostics; read-only |
| document.prepress | vector document, options with explicit CMYK profile; optional roots/control | Native process/spot planes and continuous ink samples; partial extended prepress, read-only; see VECTOR_PLATES.md |
| document.render | document; optional scale, asset_root, font_root | Straight RGBA8 hex pixels and dimensions |
| document.export | document, format; optional image_options, scale, asset_root, font_root | Encoded artifact with media_type, encoding and data |

Work paths are nonprinting geometry in either document kind. The `work_path`, `selection_path` and `clip_from_path` edit operations retain editable regions, derive pixel selections and copy vector masks. See [WORK_PATHS.md](WORK_PATHS.md) for fields, numerical coverage, source/target locks and persistence.

Raster items also support `clip_to` and the `layer_clip` operation for alpha-preserving sibling clipping groups. See [LAYER_CLIPPING.md](LAYER_CLIPPING.md) for ordering, base opacity, blend and pass-through group semantics.

Vector `component_source` definitions and `instance` placements support shared edits, local variants, replacement and atomic unlinking. Snapshots retain bindings; SVG exports expanded copies with explicit editability losses. See [COMPONENTS.md](COMPONENTS.md).

Both document kinds support `variants_set`, `variant_select` and `variants_clear` for typed data rows, captured property baselines, inheritance and repeatable export. Inspection and snapshots retain the entire variant state; artifact receipts identify the selected row and its state hash. See [VARIANTS.md](VARIANTS.md).

## Snapshot and geometry contract

`kind` is `vector` or `raster`. Width/height are integers in logical pixels, 1..32768. Coordinates use a top-left origin, x rightwards and y downwards. Resolution is 1..9600 ppi, default 96; it changes physical-size metadata, not the logical pixel extent. Color is encoded sRGB RGBA8; paint interpolation can use linear RGB, while compositing stays encoded sRGB. Profile conversion and high-depth storage remain unimplemented.

Schema-v2 has `schema_version`, `id`, `kind`, `width`, `height`, `color_space`, `revision`, `resolution_ppi` `items` and optional `assets` and `fonts`. Empty resource dictionaries are omitted. Storage is flat; optional parent IDs form a hierarchy. Siblings render bottom to top in their array order. IDs contain 1..128 ASCII letters, digits, dots, hyphens or underscores. Item IDs are globally unique; names can repeat. Legacy v1 empty snapshots are accepted at revision zero and 96 ppi; validation emits default fields and the first edit promotes them to v2.

Every item has `id`, `content` and optional `name` (default empty), `visible` (true), `locked` (false), `opacity` (1), `fill_opacity` (1), `coverage` ({type:"smooth"}), `effects` ([]), `blend` (normal), `transform` (identity), `parent` (null) and `clip` (null). An affine matrix `[a,b,c,d,e,f]` maps `(x,y)` to `(a*x+c*y+e,b*x+d*y+f)` relative to the parent. Vector transforms support translation, scale, rotation, reflection and shear. Singular/near-singular matrices are rejected. Stored pixel layers, placed images and procedural fill layers support affine transforms. Pixel/image content uses explicit nearest or bilinear sampling; procedural fields are evaluated without image resampling.

Vector content is `{type:"vector", geometry, fill, stroke, fill_rule}`. Geometry is a `rect` with x/y/width/height, an `ellipse` with cx/cy/rx/ry, a `path` with commands, or an editable `rounded_rect`, `polygon`, `regular_polygon` or `star` described in [PATHS.md](PATHS.md). Commands are `move`/`line` with `to:[x,y]`, `cubic` with control1/control2/to, and `close`. Each contour starts with move and needs a drawable segment; after close, begin a new contour with move. Open filled paths close implicitly for filling. `fill_rule` is nonzero or even_odd. Geometry inspection computes actual cubic/ellipse extrema after transformation, excludes stroke width and does not clip to the canvas or discard hidden items. Parametric expansions count toward the ordinary command budget; SVG carries explicit paths and reports the loss of editable primitive parameters.

Colors are `[r,g,b,a]`, integer bytes 0..255. Fill is a paint or null. Stroke is null or a color/width object, where color accepts a paint, with optional cap (butt/round/square), join (miter/round/bevel) and miter_limit (default 4). Width is 0.001..1024; miter limit 1..16. Strokes are centered and scale with the object. Object opacity applies once to the combined fill/stroke image. 26 shared color blend modes are available in both document kinds; see [BLENDING.md](BLENDING.md) for equations, endpoint and tie behavior. Blending follows source-over in encoded sRGB; geometry coverage is antialiased and quantized to 8-bit alpha by the CPU backend. Fully transparent rendered pixels are canonical zero; original straight-alpha source colors are retained in snapshots.

Raster content is `{type:"raster", width, height, rgba_hex, sampling}`. Sampling defaults to nearest; bilinear uses premultiplied color in encoded sRGB, including subpixel movement. Hex is row-major straight RGBA8, exactly eight ASCII hexadecimal characters per pixel; mixed case is accepted. Layer extent may differ from the document and can be translated off-canvas. The inline format is for small editable pixel buffers; placed assets hold larger immutable images outside snapshots. Mutable tile storage remains planned.

## Paints and editable fill layers

A paint is a solid `[r,g,b,a]` byte array or a tagged field. Vector `fill` and stroke `color` both accept paints; existing solid JSON remains valid. All fields accept an optional affine `transform` (identity), applied in item-local coordinates before the item's world transform. Sampling is at output-pixel centers. Bounds still describe geometry, independent of paint extent.

| type | Required fields | Optional fields |
| --- | --- | --- |
| linear | start, end, stops | spread, space, transform |
| radial | center, radius, stops | spread, space, transform |
| freeform | anchors | space, transform |
| pattern | width, height, rgba_hex | transform |

`stops` contains 2..64 `{offset,color}` entries with nondecreasing offsets in 0..1 and RGBA8 colors. Equal offsets produce a hard transition: the last stop at that position wins. Outside the first/last stop, their colors extend. `spread` is pad (default), repeat or reflect; repeat wraps t modulo 1 and reflect folds a period of 2, including negative coordinates. Linear endpoints must be at least 0.001 apart. Radial fields use a centered circle with radius 0.001..32768; an affine paint transform provides elliptical gradients. Off-center focal circles are unsupported and their fields are rejected.

`space` is srgb (default) or linear_rgb. RGB and alpha interpolate separately in straight form, matching SVG gradient semantics. Linear RGB uses the sRGB transfer function before/after interpolation. A transparent colored stop retains its color contribution until compositing; premultiplied interpolation is not implied. The gradient result is composited in encoded sRGB. Fully transparent rendered pixels are canonical zero, while snapshots retain their original colors.

Freeform fields use 2..64 `{point,color}` anchors, at least 0.001 apart. The original evaluator blends colors with weights proportional to inverse squared Euclidean distance in paint coordinates, normalized to sum to one. At an anchor its color is exact. This explicit point-field model does not imply mesh patches or compatibility with another application's freeform behavior.

Patterns repeat an original inline RGBA8 tile at its pixel width/height with nearest sampling, including negative coordinates. Paint transforms provide scale, rotation and offset. Tiles contain 1..4096 pixels and count toward the shared inline storage limit; alpha colors stay intact in snapshots. Rectangular grid repeats are implemented. Brick/hex/radial/mirrored layouts, vector motif expansion and external resource references remain separate work.

Raster procedural content is `{type:"fill",width,height,paint,dither}`. It covers a local rectangle from (0,0), supports affine item transforms, clips, groups, opacity and blending, and stays editable without allocating a pixel array. The fill operation changes paint/dither while retaining bounds and identity. `dither` is none (default) or ordered4x4, with RGB noise `(rank+0.5)/16-0.5` output-byte units. Rank rows are `[0,8,2,10]`, `[12,4,14,6]`, `[3,11,1,9]`, `[15,7,13,5]`, anchored to layer-local integer cells; alpha is unchanged. This reproducible sub-byte noise reduces banding at final RGBA8 quantization; it does not add color depth. Keep none for exact palette samples.

A document holds at most 4096 total stops/anchors. Rendering allows 134217728 paint work units (output pixels times the sum of paint costs: one per solid/linear/radial/pattern, one per freeform anchor). Singular, excessive or invalid paint transforms, unordered stops, missing tile pixels and unsupported fields fail explicitly before an edit is published.

## Image asset workflow

Import PNG, JPEG or TIFF with absolute `source_path` and `store_root`. The default color_policy is require_srgb; an untagged image requires explicit assume_srgb. JPEG/TIFF require this explicit assumption for untagged samples or convert_srgb with embedded/declared RGB profiles; see [IMAGE_IO.md](IMAGE_IO.md) for sample/codec limits and exact loss policies. PNG grayscale/palette/truecolor inputs up to 8-bit channels normalize to straight sRGB RGBA8, preserving transparent pixel colors. Interlaced input is supported. Outside explicit RGB ICC conversion, a tagged non-sRGB interpretation or ICC profile fails; HDR color metadata, 16-bit pixels, animation or EXIF metadata (including orientation) fails explicitly on this byte-asset path. Use `sample.import` to retain supported 16-bit PNG/TIFF or normalized floating-point TIFF samples. All chunk CRCs, stream completion, dimensions and allocation bounds are checked before publication. Text/density/other ancillary metadata is disclosed as a loss, not silently retained.

The result asset has width, height, sha256, storage:{type:"stored"} and import provenance containing source_sha256 and declared_srgb/assumed_srgb interpretation. The content identity hashes `INKRGBA1` (eight ASCII bytes), little-endian u32 width/height and row-major RGBA8 bytes. A store file is exactly those bytes, named `<sha256>.rgba8`. Import uses a flushed temporary file and a create-only hard link; the explicit root must support that operation. Existing identities are verified and never replaced, including corrupted entries. Interrupted imports can leave an unreferenced temporary file; session recovery covers document transactions separately from imports. Imports never modify their input. Source hashes describe the bytes read at import, not ongoing authenticity of an external path.

Use asset_put to install that descriptor under a project-owned asset ID in the snapshot. Place it as `{type:"image",asset_id,width,height,crop,sampling}` in either document kind. Frame dimensions are logical pixels, independent of source size. Crop is null (whole source) or `{x,y,width,height}` in whole source pixels, nonempty and wholly inside the source. Cropping never alters the stored asset. Sampling defaults to nearest; bilinear combines premultiplied encoded-sRGB colors then unpremultiplies, preventing invisible source colors from causing fringes. Sampling clamps at crop-edge pixels. These are point reconstruction filters, not area/bicubic/Lanczos downsampling.

For a pixel-aligned 1:1 placement, set frame dimensions to source dimensions and use an identity or integer translation. Transform/clip/group/opacity/blend work on the placed frame. Alpha coverage applies to the transformed frame; source sampling uses its inverse transform at each output pixel center. Exported PNG is the authoritative engine image. SVG embeds cropped PNG data with an image-rendering hint; a consumer can choose different resampling. SVG losses identify that limit and the omitted asset identity/provenance/uncropped content.

Pass asset_root to document.render or image/SVG export when a referenced asset uses stored storage. Paths are never retained in a snapshot. Every referenced stored image, including hidden/fully transparent ones, is verified before rendering; a missing or corrupt identity fails with asset_id. document.validate/inspect check structure and inventory without touching the store. asset.verify checks actual bytes. Snapshot export needs no asset root and does not imply stored bytes were checked.

asset.embed returns storage:{type:"embedded",rgba_hex} for an image fitting the shared inline budget. Its content identity and provenance remain unchanged; install it with asset_put to make a portable small snapshot. For larger documents, retain/copy the immutable store alongside snapshots. The engine does not delete store files.

External file updates do not mutate existing snapshots. Reimport the updated path, then explicitly replace an asset descriptor with asset_put or use a new asset ID and relink selected items with image. Replacement checks locks on every referencing item and ancestor, and validates all retained crops. If new dimensions invalidate an existing crop, add a new asset ID, relink/change the frame/crop, and remove the old descriptor in a valid batch. asset_remove rejects referenced IDs. Document changes preserve old snapshots and cache identities.

## Fonts and editable text

`font.import` requires absolute source_path, license_path and store_root. It reads a bounded scalable monochrome SFNT face (face_index defaults to 0), hashes the complete source and retains nonempty UTF-8 license text under its own SHA-256. A descriptor is `{sha256,license_sha256,face_index,bytes}`. Stored filenames are `<sha256>.font` and `<license_sha256>.license`; publication is flushed, create-only and verifies an existing destination instead of overwriting it. Sources are never changed. License retention records the supplied text; the engine does not determine whether a particular usage is licensed. No font binary belongs in this repository.

Install a descriptor with `font_put`. Content is `{type:"text",frame:{text,width,height,style,ranges,align,direction,wrap,leading,overflow,path}}` in either document kind. Style requires font_id, size in document pixels and fill paint; tracking defaults to zero. Ranges are optional `{start,end,style}` entries, sorted and disjoint, with complete styles. Indices count Unicode scalar values, use a half-open interval, and must lie on extended grapheme boundaries. `text_range` preserves unaffected styles; replacement inherits the starting character style or the base style at the end unless a style is supplied. Editing returns a new snapshot and leaves the old contents intact.

Width/height are a local frame, not glyph bounds. Wrap defaults true; line breaking prefers ASCII spaces and otherwise uses grapheme boundaries. Break spaces remain in source text but do not create leading gaps on the next line. Explicit LF makes a paragraph boundary. Alignment is left (default), center or right, based on shaped advance. Direction is one explicit ltr (default) or rtl run direction; it is not a bidirectional paragraph algorithm. Unicode script runs use explicit ordered pinned-font fallback and optional language-system selection. Explicit bidi controls fail. Missing complete graphemes fail with MISSING_GLYPH; mixed bidi paragraphs and language-sensitive line breaking remain planned.

Size is 0.01..1024, tracking is within +/-1024, and leading is optional 0.001..4096. Positions are unhinted font-design metrics scaled to document units. Baseline uses the maximum font ascent on that line including the base style. Default leading uses maximum ascent minus descent plus line gap. Tracking inserts spacing between shaped clusters; nonzero tracking disables optional standard ligatures. Negative resultant advances fail explicitly. Each style run is shaped independently; style changes break cross-run kerning and contextual shaping. OpenType feature controls, variable axes, vertical text and advanced paragraph features remain planned; editable text on paths is described in PATH_TEXT.md. Variable fonts use only their default instance; color/SVG/bitmap font artwork is rejected.

Overflow defaults error: rendering, glyph inspection and outline conversion fail if the font line box, advance or ink exceeds the frame. Use clip for an editable frame crop or visible to retain off-frame ink. Ordinary document inspection/alignment uses the declared frame and needs no font loading. `text.inspect` resolves fonts and reports un-clipped glyph ink, per-glyph source ranges and origins, and line advances/baselines; include_outlines adds original cubic path geometry. Snapshots preserve strings and font hashes, not font binaries or store paths.

Document output_profile and atomic output_profile edits persist explicit RGB delivery profiles; color conversion and exact embedded profile bytes are described in [COLOR_PROFILES.md](COLOR_PROFILES.md). Numerical previews remain in working sRGB.

Rendering and outline work require an explicit font_root. All referenced fonts, including hidden items, verify their hashes and retained licenses; there is no installed-font lookup, silent substitution or network access. PNG renders text, while SVG exports glyph outlines and reports the loss of editable text semantics. `text_outline` is available for vector documents: the original item ID becomes an isolated group, deterministic unused child IDs hold paths, and rectangular overflow clipping becomes an inner group clip. Path-text clipping instead omits glyphs with off-path midpoints before expansion. Item transforms, opacity, blending and existing clips remain intact. Each glyph paints and outlines separately, preserving translucent overlaps. Outline conversion and SVG expansion can fail ordinary item, hierarchy or geometry limits; PNG text has a separate bounded outline budget. Keep the original snapshot and font store for editing.

## Atomic editing

Each batch requires the exact revision of the supplied document, contains 1..64 operations and increments revision once. Any failure discards the whole candidate. Original snapshots stay unchanged. Validation runs after every operation, so an invalid intermediate state cannot be repaired by a later operation in the same batch.

| op | Fields | Behavior |
| --- | --- | --- |
| frame | id, frame | Resize/revise a frame or artboard without changing its children; also sets role/background/bleed/guides |
| guide_put | id, guide:{id,axis,position} | Add/replace a nonprinting guide within the selected frame |
| guide_remove | id, guide_id | Remove a guide by its frame-local stable ID |
| font_put | id, font | Add/replace a pinned font descriptor, honoring locks on every reference |
| font_remove | id | Remove an unreferenced descriptor; stored font/license files stay intact |
| text | id, frame | Replace an editable text frame, retaining its item identity/transform |
| text_range | id, start, end; optional text, style (at least one) | Replace characters and/or complete character style; scalar indices on grapheme boundaries |
| text_outline | id | Vector documents: convert text to a group of editable glyph paths, preserving item appearance |
| asset_put | id, asset | Add/replace a document asset; validate every reference and honor their locks |
| asset_remove | id | Remove an unreferenced asset descriptor; cache files stay intact |
| image | id, asset_id, width, height; optional crop, sampling | Relink/change an image frame and crop without changing source pixels |
| sampling | id, sampling | Set nearest or bilinear for an inline pixel layer or placed image |
| add | item; optional index | Insert a new unique ID; default at top |
| remove | id | Remove an unlocked item |
| duplicate | id, new_id; optional index | Independent content copy retaining properties; source stays unchanged |
| group | ids, new_id; optional name, isolated, role | Wrap a contiguous sibling range, preserving child IDs and sibling order |
| ungroup | id | Remove an appearance-neutral group and compose its transform into children |
| reparent | id, parent; optional index | Move a subtree while preserving world geometry and IDs |
| group_options | id, isolated | Change group isolation with validation of supported combinations |
| selection_set / selection_fill | selection / selected | Restore, clear, fill or empty the nonprinting pixel selection |
| selection_shape | boundary, combine, antialias, fill_rule | Create/combine rectangle, ellipse or polygon coverage |
| selection_invert / selection_refine | none / mode, radius | Invert or expand/contract/feather active coverage |
| mask_from_selection | id, linked, replace_existing | Copy coverage into a mask without moving its world position |
| mask_apply | id | Apply an enabled mask at native pixel centers on a raster pixel layer, image or fill |
| mask | id, mask | Replace or remove an editable grayscale opacity mask; see MASKS.md |
| mask_link | id, linked | Switch item-local/document coordinates while preserving world placement |
| mask_transform | id, matrix, space | Transform only the mask in replace/local/world coordinates |
| clip | id, clip | Set, revise, disable or release an editable geometric clip |
| align | ids, axis, anchor, reference | Align selected world geometry to an explicit reference |
| distribute | ids, axis, mode, reference | Distribute at least three selected objects by gaps or centers |
| reorder | id, index | Move to the declared final stack position |
| properties | id; optional name, visible, locked, opacity, fill_opacity, coverage, blend | Change supplied properties only |
| transform | id, matrix; optional space, anchor | Replace, world-compose or local-compose a matrix, optionally around an explicit anchor |
| vector | id, geometry, fill, stroke; optional fill_rule | Replace editable geometry/appearance of a vector item |
| stroke_expand | id, fill_id, stroke_id | Atomically replace a stroked vector with an isolated group preserving its centerline/fill and an editable filled outline |
| transfer | transfer: {source, ids, prefix, parent?, verify_resources?} | Copy selected source subtrees with ancestor context, transitive references and complete ID maps; preserve source snapshots and external bytes |
| adjustment | id, adjustment | Replace ordered tone operators and optional stable clip_to binding on an existing raster adjustment layer |
| path | id, action | Convert primitives; edit selected anchors/handles; split, reverse or join contours with revision-scoped command indices; see PATHS.md |
| fill | id, paint; optional dither | Replace an editable procedural fill layer paint; omitted dither resets to none |
| pixel_fill | id, rect:{x,y,width,height}, color | Replace pixels within the layer-local integer rectangle |

Locked objects and ancestors reject edits. An operation affecting a whole subtree also rejects locked descendants. Unlock through a properties operation containing only id and locked:false; a locked ancestor must be unlocked first. A following operation may edit. Pixel fill rectangles must be nonempty and wholly inside the layer. Duplication does not mutate the source and retains its locked state. Group duplication requires `descendant_ids`, an exact old-to-new ID map for every descendant. Unknown IDs, properties and operations fail explicitly. Failed batches return a zero-based operation_index when applicable.

## Hierarchy, clips and layout

Group content is `{type:"group", isolated:true, role:"group"}`. Role can be `group` or `layer`; both share the same hierarchy and compositing semantics. Parent references must identify a group, frame or artboard, be acyclic and stay within 16 ancestor levels. Empty groups are valid and inspect with null bounds. Inspection exposes world transforms, unclipped geometry bounds, storage index, sibling index and effective visibility/locks. The document.select object query is read-only and returns explicit IDs. Persistent nonprinting pixel selections are a separate scalar field and operation family; see [SELECTIONS.md](SELECTIONS.md).

An isolated group composites its children against transparency before blending the result with its backdrop. Group opacity applies once, including overlapping children. A pass-through group (`isolated:false`) blends children directly against the surrounding backdrop; group opacity and masks interpolate the original and child-modified premultiplied backdrop. It requires normal group blending and rejects group filters. Unsupported combinations fail explicitly. Hiding a parent hides all descendants. Removing a group removes its subtree. Add/reorder/reparent indices are sibling positions, not global array positions.

Grouping requires a contiguous range under one parent so unrelated stacking does not change. Ungroup composes transforms into children and preserves sibling order and IDs. It rejects active clips or masks, group opacity/blending or isolation dependencies that would change appearance. Reparent preserves geometry, while inheriting the new parent's visibility, opacity and clipping. A world-space transform applies in document coordinates even below a transformed parent; a local transform composes into the item's own coordinates. Optional anchor:[x,y] changes the supplied matrix M to T(anchor)*M*T(-anchor) before composition. Anchor coordinates are document coordinates for world, item-local for local, and parent coordinates for replace. Geometry, images and pixel layers share this contract.

A clip is `{geometry, fill_rule, transform, enabled}` with the same geometry types as vector content, default nonzero filling, identity local transform and enabled=true. It belongs to the item's local coordinates and moves with that item. It masks the complete rendered object/group, supports compound holes, and combines with ancestor clips. Set clip=null to release it; enabled=false retains settings without changing output. Reversible grayscale opacity masks also work on both kinds and isolated containers; their exact attenuation, feathering, linkage, export and budget contracts are in [MASKS.md](MASKS.md). Geometric clipping works for both document kinds; pixel-layer alpha clipping against another layer is not implemented.

Alignment axis is x or y; anchor is min, center or max. Reference is `{type:"canvas"}`, `{type:"selection"}`, `{type:"item",id}` `{type:"bounds",bounds:[min_x,min_y,max_x,max_y]}` or `{type:"guide",frame_id,id}`. Calculations use unclipped geometric world bounds, excluding strokes. The entire selected group moves; selecting both an ancestor and its descendant for layout is rejected. Locked items and empty-group bounds also reject the operation.

Distribution mode is gaps or centers. Gaps order by existing minimum coordinate; centers order by existing center; ties use stable IDs. The first and last objects meet the reference's outer edges, with equal intervening gaps or center steps. Insufficient space can produce negative gaps (overlap). Layout moves are converted into each parent's local coordinates. Pixel layers can retain fractional translations; their selected sampling rule determines the rendered result without rounding the transform.

For document.edit, revision checks compare the supplied snapshot and replaying that input produces the same result. Use session.apply for a durable shared head, idempotent retries and persistent undo/redo. Snapshot edits support cooperative cancellation but leave persistence to the caller.

## Artboards, frames and guides

Frame content is `{type:"frame",frame:{role,width,height,background,bleed,guides}}`. Role defaults to frame; choose artboard for an independently exportable container. Dimensions are integer logical pixels, 1..32768. Background is optional RGBA8 (default transparent). Name and ID are ordinary item fields. Item transforms position the frame, while child transforms remain local to it. Frames/artboards are always isolated and always clipped to their frame rectangle, combined with any explicit item clip. Off-frame artwork remains editable and persisted. Resize changes the viewport, without scaling or discarding children. All 26 color modes plus item opacity use the existing isolated-container compositing model. Ordinary document bounds/alignment use the frame rectangle, excluding off-frame children, bleed and guides.

Nested frames and artboards can parent any supported document content, including further frames. Existing add, duplicate, remove, reorder, reparent and transform operations work with them. Duplicate requires the exact descendant ID map and retains child contents, off-board artwork, frame roles, bleed and guides. Reorder uses the existing sibling index; artboard export order follows hierarchy preorder with siblings in bottom-to-top stack order. Removing a container removes its owned subtree. Frame changes and guide edits honor item/ancestor/descendant locks. Group ungroup/isolation operations do not release frame clipping; use explicit reparenting when moving artwork outside its frame.

Bleed is `{top,right,bottom,left}` with omitted sides defaulting to zero; each edge is an integer 0..4096. Nonzero bleed requires role artboard. It does not affect ordinary canvas rendering or geometric layout. Guides are optional `{id,axis,position}` lines, where axis x is a local vertical line and axis y a local horizontal line. Guide IDs are unique within a frame; positions are finite and within +/-32768 and may be outside the frame. Guides never paint or clip pixels. `guide_put` replaces the matching ID or appends it; `guide_remove` fails for a missing ID.

A guide reference for alignment is transformed to world coordinates. It must have a constant coordinate along the requested world axis (tolerance 1e-8); diagonal or mismatched guides fail UNSUPPORTED. The guide's frame or its ancestor cannot belong to the moving selection. Frame/item references give ordinary rectangular bounds for distribution; selected nested items move through their parent transforms as before. Inspection reports frame attributes on items and a named, ordered artboard inventory including local dimensions, world transform and bounds.

`artboard.export` accepts formats png, jpeg and tiff for either document kind or svg for vector documents (SVG requires scale 1). Selection defaults to `{type:"all"}`. `{type:"ids",ids:[...]}` preserves requested ID order and requires unique artboard IDs. `{type:"range",start,end}` uses zero-based, end-exclusive indices in the current hierarchy preorder. Empty or invalid ranges fail. Ancestor and nested artboards may both be selected as separate independent outputs.

Each output contains only that artboard's owned subtree, expressed in its local coordinates. The artboard's placement transform and all ancestor visibility/transforms/clips/effects are excluded; its own visibility, opacity, blending, explicit clip and opacity mask remain. Unrelated pasteboard artwork and other boards do not enter that output. This standalone contract is disclosed in the response; whole-document rendering retains full ancestor context. Font/image resources resolve within each selected subtree. Background extends into requested bleed. Owned off-board geometry can become visible in the bleed strip, while explicit clips still restrict it.

`include_bleed` defaults false. When true, output dimensions are trim width/height plus respective bleed edges; immediate children, the explicit clip and the board's own linked mask shift by left/top bleed in an internal clone. Unlinked masks throughout the owned subtree convert from document coordinates into the selected board's local export coordinates. Total logical dimensions must remain within 32768. Image scale applies after this calculation and scales physical-resolution metadata. Each artifact entry reports id, name, logical_size, scale, source_bounds in original board coordinates, trim_box in output logical coordinates and the encoded artifact. The selected root artboard also leaves any external layer-clipping group in the temporary view; owned internal clipping relationships remain. Source snapshots, local transforms, guide data and original pixels stay unchanged. A request returns all artifacts only after every selected export succeeds; no output files are written. Failures identify artboard_id alongside an applicable asset_id, font_id or item_id.

SVG retains frame background, clipping, local transforms and content as isolated groups. Guides, frame/board roles, bleed settings, logical export order, locks and editability metadata require the original snapshot; losses are reported. Text remains outlined in SVG. Independent board snapshots are not a separate export format: save the complete document snapshot for multi-board persistence.

## Rendering and export

Render scale is an integer 1..4, default 1. Pixel layers and images use their selected nearest/bilinear sampler at output pixel centers for these preview/export scales; this does not mutate source pixels. PNG returns base64 RGBA8 with sRGB and physical-resolution metadata; its resolution scales with output pixels to preserve physical size. `document.render` returns the same decoded pixels as hexadecimal data for numerical review.

`format:"snapshot"` returns an editable JSON document as UTF-8 text. `format:"svg"` returns UTF-8 SVG for the supported vector subset. Both require scale=1. SVG preserves solid, linear and centered radial paints, including stop alpha, spread, interpolation space and local paint transforms on fills and strokes. SVG rejects non-normal blend modes, raster documents, freeform fields and inline pixel-pattern paints. Use PNG for those appearances and snapshots for editable settings. It reports that locks and revisions are not preserved as artwork semantics; retain the snapshot for editing. `svg.import` imports the bounded geometry/gradient/clip/artwork-mask/single-line-text subset from inline UTF-8 text or explicit local files, with deterministic ID mapping, source hashes and normalization losses; unsupported content fails the entire import. Export supports more SVG semantics than import. See [SVG_IMPORT.md](SVG_IMPORT.md). External native-document interchange is not implied by snapshot export.

No export command takes an output path. The caller decodes/writes `result.data` to a new location and owns overwrite policy. See examples/README.md for a complete workflow.

## Limits and failures

Standard snapshots: at most 768 KiB, 256 items including groups, 16 ancestor levels, 4096 geometry/clip commands and 65536 total inline pixels (pixel layers, grayscale masks, pattern tiles and embedded assets). Local geometry coordinates are within +/-32768; transformed control points within +/-65536. Rasterization: at most 1048576 output pixels, 67108864 output-pixel/item work units and 4194304 aggregate floating-point pixel slots across nested group/frame buffers plus the root and painted-object intermediate; documents with text reserve an additional full-size text intermediate. Text paint paths also count as rendering passes. These are declared early resource boundaries, not completion of the full precision/scale checkpoints. Geometry is f64; raster coverage is f32. Unrepresentable backend geometry returns RENDER_ERROR when detected; subpixel edge fidelity is bounded by coverage quantization, not exact vector coordinate precision.

Asset dictionaries contain at most 64 descriptors and 16777216 total declared pixels. Image input is capped at 32 MiB; the decoder has a 64 MiB internal allocation budget. SVG embedded image copies are capped at 16777216 pixels across all image instances. Import/render may hold bounded temporary decode/verification buffers in addition to source pixels.

Documents hold at most 32 artboards, 512 guides total and 64 guides per frame. All frames count toward the 256 item and 16 ancestor limits. Artboard image batches preflight 4194304 output pixels total, 134217728 output-pixel/subtree-item work units and the existing per-output limits. SVG batches preflight 4194304 embedded image-copy pixels. All batches cap accumulated encoded artifact data at 32 MiB. Text paths retain existing per-output render-work limits.

Font dictionaries hold at most 8 descriptors, each up to 8 MiB, with license text up to 64 KiB. Documents hold at most 4096 text characters, 64 style ranges per frame, 8192 resolved glyphs and 131072 resolved text outline commands. A frame allows at most 1048576 input-character visits across wrapping, shaping and fallback attempts.

Errors include FONT_ROOT_REQUIRED, FONT_MISSING, FONT_CORRUPT, FONT_IN_USE, FONT_STORE_ERROR, INVALID_FONT, INVALID_FONT_LICENSE, MISSING_GLYPH, TEXT_LAYOUT_ERROR, TEXT_OVERFLOW, ASSET_ROOT_REQUIRED, ASSET_MISSING, ASSET_CORRUPT, ASSET_IN_USE, ASSET_STORE_ERROR, COLOR_POLICY_REQUIRED, INVALID_IMAGE, INVALID_REQUEST, INVALID_DOCUMENT, INVALID_OPERATION, NOT_FOUND, LOCKED, REVISION_CONFLICT, RESOURCE_LIMIT, UNSUPPORTED, RENDER_ERROR, EXPORT_ERROR, IO_ERROR and REQUEST_TOO_LARGE. Errors do not echo source data or local file paths. Stored image failures during document rendering/export include asset_id; font resolution failures include font_id. Text layout preparation failures include item_id; artboard batch failures also include artboard_id. Call `schema` for exact request shapes and `capabilities` before planning unsupported work. Full typography, broader image/document import, additional effects and filter families, advanced selection refinement, explicit rasterization of text/containers for mask application, and color conversion are upcoming capabilities.

## Persistent editing

The `session.create`, `session.read`, `session.apply`, `session.receipt`, `session.history` and `session.verify` commands wrap the same validated snapshot model in durable local storage. All take an explicit absolute `session_root` and `session_id`. Mutations require `request_id`, and `session.apply` also requires `expected_revision`. Use `schema` for the full typed request and [SESSIONS.md](SESSIONS.md) for action fields, persistence boundaries, cancellation, limits and recovery. `document.edit` also accepts the optional `control` object documented there; existing calls default to no deadline or cancellation marker.

## Agent adapters and published outputs

`document.diff` / `session.diff` compare stable-ID structure, geometry, resources and optional rendered pixels. `document.publish` / `session.publish` create one complete new PNG/APNG/JPEG/TIFF/SVG/snapshot file in an explicit existing root; every existing destination is rejected. `inkbolt mcp` exposes all engine commands as individual stdio tools with generated input schemas, structured results, native PNG previews and cooperative cancellation. See [AGENT_EXECUTION.md](AGENT_EXECUTION.md) for exact fields, protocol boundaries, limits and examples.

Pixel selections use an additional bounded grayscale8 canvas field of at most 262144 pixels, still subject to the full snapshot byte cap. Permanent mask application can read a stored image through `document.edit`'s optional `asset_root`; sessions use their existing resource binding. See SELECTIONS.md for native sample positions, scalar set/refinement rules, quantization and limitations.

Raster documents also accept `{type:"adjustment",adjustment:{operators,clip_to}}` content. It retains source pixels and applies declared tone equations to the backdrop or an explicitly bound preceding base. Masks/clips limit correction; alpha stays unchanged. `document.measure` evaluates scale-one RGBA8 output with exact histogram weights. See [ADJUSTMENTS.md](ADJUSTMENTS.md) for equations, ordering, stable reference rules, rounding and depth limits.

Adjustment stacks accept a `color` operator containing typed hue/saturation, desaturation, channel mixer, balance, selective correction, lookup or gradient-map settings. See [COLOR_ADJUSTMENTS.md](COLOR_ADJUSTMENTS.md). These controls retain alpha and source assets; profile conversion remains separate.

Items now retain editable `filters` arrays. The `filters` edit replaces the ordered stack; inspection and semantic diffs expose it. Both document kinds support box/Gaussian/directional/radial/surface operators with per-filter masks, border handling, opacity and all 26 shared color modes. Controls, viewport evaluation, limits and unsupported contexts are specified in [FILTERS.md](FILTERS.md). Two extra full-frame buffers are reserved for filtered renders; filter masks share the mask storage/preparation budget.

Printable items and isolated groups also support content `fill_opacity`, editable shadow/stroke/overlay `effects` and seeded `coverage:{type:"dissolve",seed}`. The `effects` operation replaces the decoration list; `properties` changes fill and coverage. Defaults are omitted from snapshots. Effects retain original source alpha while fill fades content; overall opacity fades the decorated result. See [LAYER_EFFECTS.md](LAYER_EFFECTS.md) for equations, category order, local-cell hashing, limits and explicit unsupported contexts. Geometry-bound queries still exclude decorations.

The `detail` and `spatial` filter wrappers add sharpening/unsharp/median/noise and offset/displace/mosaic operators. Capabilities report the operator lists, seed contract and map limits; strict request schemas describe their editable settings. See [DETAIL_AND_SPATIAL.md](DETAIL_AND_SPATIAL.md).

Saved channels and image-guided selections use `channel_put`, `channel_remove`, `channel_calculate`, `channel_load` and `selection_sample` within ordinary atomic edits. `document.inspect` and diffs include their nonprinting state. Full contracts and limits: [CHANNELS_AND_SELECTIONS.md](CHANNELS_AND_SELECTIONS.md).

Path `simplify` edits return `changes[].details` with exact rational deviation evidence and retained-candidate reasons. Persistent edits keep it in `receipt.changes[].details`. See [SIMPLIFICATION.md](SIMPLIFICATION.md) for topology scope and limitations.

Shared editable artwork masks use top-level `mask_source` containers, ordinary vector/text children and the `artwork_mask`, `artwork_mask_link` and `artwork_mask_transform` edits. Discover resources with `visible_only:false`; structural diffs include dependent source hashes. Limits are 32 references, 1048576 aggregate viewport coverage samples and 4096 SVG copies; full contracts and unsupported combinations are in [ARTWORK_MASKS.md](ARTWORK_MASKS.md). SVG mask import now creates these sources with independent content/region unit transforms. `clip_region:false` represents an unclipped source field, including explicit SVG 2.0 definitions with no region attributes.

Raster documents support `{"op":"canvas","action":{...}}` with crop, anchored extent, nearest/bilinear/area/bicubic/Lanczos3 scale and resolution-only actions. Layers and source pixels persist; auxiliary planes follow their canvas-bound contract. Filtered documents require explicit effect policy. See [CANVAS.md](CANVAS.md) for coordinates, rounding, locks and limits.

Area, bicubic and Lanczos3 reconstruct immutable image/layer sources with explicit footprint and work budgets. Scalar mask and displacement-field samplers remain nearest/bilinear; SVG rejects the new image kernels explicitly. See [RESAMPLING.md](RESAMPLING.md).

Groups and layers accept `content.knockout:true`. `group` can create the same setting; `group_options` edits it alongside required `isolated`, preserving knockout when omitted. Inspection exposes the `group` object; snapshots, semantic diffs, duplication and history retain the field. [KNOCKOUT.md](KNOCKOUT.md) defines intrinsic-alpha footprints, zero-opacity replacement, nested blending and resource bounds. SVG, mask-source knockout and unbound adjustments inside knockout subtrees fail explicitly.

Extended effects accept shared `Paint` values in `color`, a geometry `scale`, and optional piecewise linear `contour` knots. `lit_shadow` follows saved document `global_light` unless its operator supplies a local `azimuth`. The `global_light` edit updates dependent effects with lock checks; `effects_scale` multiplies every effect scale on explicitly selected items. Inspection and diffs expose all saved settings. See [LAYER_EFFECTS.md](LAYER_EFFECTS.md) for angle conventions, gradient coordinates, mapped alpha, effective kernel limits and paint storage bounds.

## Stroke controls and expansion

Vector `stroke.dash` accepts `{ "array": [6, 4], "offset": -2 }`; omission retains solid strokes. `stroke.scaling` selects `object` (default, item-local units) or `document` (fixed logical width, dashes and arrow dimensions after full placement). Odd lists repeat; empty/all-zero lists are solid; phase restarts per subpath. `document.inspect` now includes each vector item's `stroke`, and `capabilities.vector_strokes` reports supported controls and evaluation limits. Optional `width_profile` knots vary width in the declared stroke space along each contour; `start_arrow` and `end_arrow` add triangle, chevron, diamond, ellipse or bar tips. The `stroke_expand` edit creates editable filled paths while preserving root appearance and the source centerline. A saved `curve_tolerance` in the declared stroke space controls evaluated subdivision. Use atomic edits and snapshot/session transport; SVG emits advanced controls as filled geometry with explicit editability losses. See [STROKES.md](STROKES.md) for validation, SVG exchange, precision and work budgets.

Affine composition, inverse, pivot, hierarchy and stroke-scaling contracts are documented in [TRANSFORMS.md](TRANSFORMS.md). Document-scaled strokes export to SVG as filled outlines; expansion freezes their current width behavior. Reusable source definitions cannot freeze different placement-dependent outlines at once; unlink the intended component copy before expansion.

The `transfer` edit accepts a complete source snapshot and copies selected artwork into the current destination. It preserves source snapshots, retains referenced resource descriptors and reports all generated IDs. Optional destination-root verification detects missing/corrupt blobs before accepting the copy. Ancestor/context and variant boundaries are explicit in [TRANSFER.md](TRANSFER.md).

Metadata records belong to documents or items. Use the atomic `metadata` operation (`id` omitted for the document, `value:null` to clear); records support title, description, author, rights, note, unique tags, properties and a private map. Inspect returns records and a path-free resource manifest. `metadata_policy` on document/artboard export or publication controls `public`/`strip` mode and optional manifest/provenance. Image/SVG delivery excludes private maps; snapshots preserve source records unless an explicit policy requests a sanitized copy. Recognized image metadata is returned separately as untrusted descriptions on import. See [METADATA.md](METADATA.md) for exact carriers, limits and privacy scope.

Mesh paints and `mesh_knot` support editable shared color fields and transparency in vector fills/strokes and raster fill layers. `mesh.inspect` returns numerical evidence without rendering or mutating source documents. SVG artifact/publication receipts include `mesh_textures` with hashes and conditional interior reconstruction bounds. See [MESHES.md](MESHES.md).

An optional text-frame `path` retains a single editable baseline with offsets, flip and tolerance. Use `wrap:false` and no paragraph leading/line breaks. Existing `text` and `text_range` operations edit the source; `text.inspect` exposes baseline intervals and glyph poses. SVG/publication `text_paths` report measured layout while snapshots preserve editability. See [PATH_TEXT.md](PATH_TEXT.md).

## Image tracing

`image.trace` returns a new editable vector snapshot and provenance from explicit RGBA8 pixels or a verified image descriptor with an explicit asset root. Binary, exact, quantized and palette classification, area-based noise removal, uniform-surround hole filling and cooperative cancellation use the same CLI/library/MCP contract. All output is ordinary editable path geometry; source bytes stay unchanged. See [TRACING.md](TRACING.md) for formulas, topology, fidelity and limits.

## Pixel brushes

`brush.inspect` plans explicit stroke dabs and returns normalized settings, hashes and bounds. The atomic `brush_stroke` operation edits an inline raster item by ID; its change receipt reports source/result identities, changed pixels and measured work. Programmatic control needs no tablet. See [PIXEL_BRUSHES.md](PIXEL_BRUSHES.md) for the paint/erase/mixer/smudge equations, selection/texture coordinates, limits and replay boundaries.

The atomic `retouch` operation takes an explicit source item, a native-grid region, source affine mapping and clone/heal options. It returns source/result identities, boundary measurements and true solver residuals. Source sampling ignores scene appearance and never reads its own edits; source locks permit read access while target locks remain enforced. See [RETOUCH.md](RETOUCH.md) for complete coordinates, equations, quality limits and source retention.

Use the atomic repair operation for patch, fill, move or edge_correct actions. Patch/fill/move require explicit donor sources and context-error limits; edge correction requires a guide and final-change limit. Optional final boundary limits reject unacceptable results without publishing a partial snapshot or session revision. Receipts expose chosen donor patches, quality measurements and source identities. See [REPAIR.md](REPAIR.md).

Text styles accept an ordered `fallback_fonts` list and optional `language`. Glyph inspection exposes the actual selected font and ISO 15924 script; line-local context preserves script joining across style/font boundaries. Source text stays editable, and missing faces/complete graphemes fail explicitly. Direction defaults to the prior single-run contract; opt into mixed paragraphs with `bidi:"unicode"`. See [UNICODE_TEXT.md](UNICODE_TEXT.md) for exact selection, coverage, resource and delivery contracts.

Use `font.inspect` with a pinned descriptor, explicit `font_root` and optional `variations` map to discover axes, instance metrics and feature tags. Text styles accept `font_variations` keyed by primary/fallback font IDs and a `features` tag/value map. Source coordinates and controls persist through edits, snapshots, transfer and sessions; actual font instances drive advances, outlines and path placement. See [FONT_CONTROLS.md](FONT_CONTROLS.md) for limits, precision and selected-font diagnostics.

`text.directions` resolves Unicode 16 paragraph and line order without fonts. Text frames support `bidi:"unicode"`, `direction:"auto"` and direction-sensitive start/end alignment; `text.inspect` reports resolved runs and actual glyph directions/levels. See [BIDI_TEXT.md](BIDI_TEXT.md).

`document.export` and publication accept `format:"pdf"`. Use `pdf_options.artboards` with all/ids/range selection for a multi-page document, optionally with bleed; omission exports the canvas. PDF requires scale one and exposes page boxes, physical sizes, outlined-text losses and resource budgets. Source text and editing controls remain in snapshots. See [PDF.md](PDF.md).

`assist.layout` returns a read-only exact ordered-shelf proposal; `assist_layout` applies the same options atomically at the expected revision. It preserves sizes/order and source content, requires no model or network, and reports placement error. Read [ASSISTANCE.md](ASSISTANCE.md) for geometric bounds, dependency and fit limits.

`assist.segment` returns a native binary object mask and an exact integer minimum-cut certificate from explicit foreground/background seeds. `assist_mask` applies it atomically with source pixels retained. Local removal, self-guided denoise and upscale compose with existing `repair` and `canvas` operations. See [PIXEL_ASSISTANCE.md](PIXEL_ASSISTANCE.md) for source types, strict dependencies and quality bounds.

Additional image formats: `bmp` and `tga` share document/artboard export and publication. `gif` exports a still or every sequence frame. `sequence.import` accepts `{type:"gif",source_path,background:"transparent"}` with explicit `assume_srgb`. TIFF RGBA8 delivery accepts `image_options.alpha` as `unassociated` or `associated`. Read [EXTENDED_IMAGE_IO.md](EXTENDED_IMAGE_IO.md) for exact palette/timing, alpha, profile and metadata boundaries.

Explicit large vector documents use the persisted `resource_profile` field and profile edit. Discover both budgets in `capabilities.resource_profiles`; see [LARGE_VECTOR.md](LARGE_VECTOR.md). Rendering and export requests accept cooperative `control` settings.
