# Layered pixel interchange

Native editable text import remains unsupported; explicit text delivery is described below. When `layered.import`
encounters a recognized text record, its `UNSUPPORTED_LAYERED_SEMANTICS` error can
include `details.kind:"native_text_requirements"`. This reports character/UTF-16
counts, style/paragraph run counts, referenced face names, affine placement and a
text-data hash. It never returns a document or substitutes cached text pixels.
It also reports up to eight `shape_owner_labels` from the geometry extensions,
with truncation and trust flags. These are untrusted identifiers from the file,
not a validation of the geometry or a promise that a consumer recognizes them.
Optional `compatibility_markers` retain typed Boolean/enum metadata as untrusted
data with `semantics_validated:false`; they do not establish compatibility or
authorize ignoring legacy layout behavior.

Top-level counts and face names describe the local record, explicitly labelled
`reported_text_source:"local_record"`. `native_story_index` is the descriptor's
reference, independent of layer order or ID. When global text data exists,
`global_story` describes the selected authoritative story: character/UTF-16 and
run counts, referenced face names, source-text and global-data hashes, and
`local_text_matches`. A disagreement is reported rather than silently choosing
the local copy. Missing or invalid references never fall back to cached pixels or
local text. Without global text data, the local record is identified as the text
source; an absent table does not prove layout support.

`global_story.frame` resolves the selected story's independent frame reference.
It reports point or rectangular shape, encoded local bounds, a separate frame
transform, first-baseline metric/minimum and whether that control was explicit.
Frame indices are independent of story indices and layer IDs. Rectangle checks
require four connected straight cubic segments, each corner exactly once, with
no diagonal crossing; curves and other paths are not reduced to bounding boxes.
Coordinates and affine entries must be finite and within -32768..32768; rectangle
width/height must be 0.001..32768. The frame table permits at most 256 entries and
the selected story currently requires exactly one reference. Missing story layout
is reported as absent; an existing but broken reference never falls back to the
local shape cache. Unknown explicit shape kinds or first-baseline metrics fail.

The absent first-baseline control reports ascent and zero minimum. Explicit
controls report `fixed`, `ascent`, `cap_height`, `leading` or `x_height`, with a
minimum in 0..32768 local pixels. These values describe geometry requirements;
they do not certify font metrics, shaping or placement. The frame transform and
the outer layer transform remain separate. No density conversion or matrix
composition is applied in the diagnostic. `other_frames_validated`,
`remaining_frame_properties_validated`, `local_geometry_consistency_validated`
and `layout_semantics_validated` stay false, including for a singular matrix.
Columns, arbitrary shapes, other properties and complete reconstruction remain
unimplemented. Named geometry-extension owners are still untrusted.

These diagnostics check this local record's framing, matching local text sources, complete
UTF-16 run coverage without splitting surrogate pairs, and explicit per-run font
references. They do not validate layout semantics, later records or the whole
file. The global extension checks tagged-section framing and, for the recognized
version, the selected story's UTF-16 coverage and explicit font references.
`other_stories_validated`, `other_layer_references_validated`,
`style_semantics_validated`, `local_style_consistency_validated` and
`layout_semantics_validated` remain false. Parsing unknown dictionary fields does
not establish their meaning or permit discarding them. Global text can be
authoritative while local text or layout is stale. Editable reconstruction must
reconcile styles and geometry as well as characters; removing global layout can
change paragraph placement even when the characters match.
Inherited styles and unknown descriptor framing can prevent diagnostics.
Font names come from untrusted source data and do not identify exact font bytes.
Editable reconstruction still needs explicit content-pinned font bindings and
declared layout/rendering differences; no import option currently enables it.

The text-data parser allows at most 64 KiB, depth 16, 4,096 values, 512 entries per
container, 16,388 decoded bytes per string, 65 runs per run table and eight
referenced faces. It rejects duplicate keys, invalid Unicode, inconsistent runs,
nonfinite numbers and trailing data. Malformed/over-budget records return the
ordinary invalid-file/resource-limit errors without a requirements receipt.
Global text data has its own bounded implicit dictionary grammar: named values,
opaque byte strings and Unicode strings remain distinct. Only Unicode strings
can supply story text or font names. Its separate limits are 256 KiB, depth 32,
32,768 values, 4,096 entries per container, 512 global tagged records and 256
stories, with the same string, character, run and referenced-face bounds. Only
global version 14 is recognized. These bounds do not enlarge editable documents
or relax the local text-data grammar.
CLI and MCP preserve the same optional structured error details. This diagnostic
unit adds no engine-checkpoint credit.

`layered.import` and `document.export` with `format:"layered"` exchange a bounded native RGB8 pixel-layer subset. Publication uses `.psd`. The basic interchange checkpoint is **verified**, bringing the total to **161/167 (96.41%)**. Independent native application round trips preserve layer structure, original samples and visible composite pixels. The extended requirement for large-document structures, masks, text, groups and embedded objects remains required and uncredited.

`format:"layered_large"` publishes `.psb` with version-two framing. The importer selects framing from the file header. Layer-section, layer-info and channel lengths are unsigned 64-bit values; row-compression counts are 32-bit values. Only the format-defined tagged records use 64-bit lengths; all other sections retain their specified widths. The Rust library exposes `export_versioned` with `Version::Standard` or `Version::Large`.

This is partial extended interchange and adds no checkpoint credit. Version two currently supports axes through the existing engine limit of 32,768, including thin canvases wider or taller than the standard format's 30,000 limit. The 32 MiB file, 1,048,576 canvas-pixel and 65,536 stored-pixel limits remain. Larger engine axes, remaining group/mask semantics, text and full embedded-object exchange remain required; selecting a large container does not imply those semantics are supported.

```json
{"command":"layered.import","source_path":"C:/work/input.psd","id":"editable","color_policy":"assume_srgb"}
```

Use an absolute local path, optionally pinned with `expected_sha256`. Import reads the file without changing it and returns a document plus source, profile, omitted-record and merged-cache receipts. Untagged input requires `assume_srgb`. An exact working-sRGB profile preserves encoded bytes. Other embedded RGB profiles require `convert_srgb`, which converts layer RGB before composition and preserves alpha; it can change blending in the source profile space. Profiles are checked and never silently replaced by an assumption.

Layers retain original RGB and alpha samples, including invisible RGB under zero alpha, integer extents outside the canvas, Unicode names, bottom-to-top order, visibility, exact byte opacity/fill opacity and full locks. Numeric file IDs become fresh engine IDs. Export creates independent file IDs and records the original mapping in its receipt. Identical names are allowed. Source samples and physical density remain independent of the flattened preview.

Import accepts raw, PackBits row compression, ZIP and ZIP with 8-bit row prediction. Export uses PackBits; the Rust library also offers raw planes. Framing, counts, channel IDs, bounded decompression, trailing data and every editable appearance record are validated. Unknown appearance information fails explicitly. Descriptive, UI and thumbnail records may be omitted only where the receipt identifies them; this is not metadata round-trip support.

Incoming metadata has explicit schemas: descriptive layer timestamps, inactive provenance/generation records, ICC colour-management selection with no display-view override, known compositor preferences, filter-overlay colours, printing/slice metadata and empty guide records. Active colour overrides, nonempty guide geometry/identities, unknown metadata fields, extra alpha channels and unknown tagged records fail. The typed descriptor reader limits each record to 64 KiB, each container to 128 entries, identifiers to 128 bytes, text to 1,024 UTF-16 units, depth to eight and total values to 512. Duplicates, nonfinite numbers, contradictory fields and nonzero padding fail before returning a document.

Limits are 32 MiB per file, 1,048,576 canvas pixels, 65,536 retained layer pixels in total and 256 editable items and at most 512 serialized layer/boundary records. Standard dimensions are positive and at most 30,000; large-container dimensions can reach 32,768; every layer edge must lie within -32,768..32,768. Pixel layers need positive extents; supported folder records use zero bounds and empty sample channels. Names also obey the ordinary document limits. Density rounds to unsigned 16.16 pixels per inch. Unequal horizontal and vertical density fails.

The native density numbers always represent pixels per inch. A pixels-per-centimetre display preference does not rescale them. Separate width/height display units do not change the pixel canvas.

Delivery requires a raster document in working sRGB, original inline RGBA8 or equivalent native sample grids, nearest sampling and integer translation. Scale is one. Text or objects without their explicit delivery policies, other blend modes, pixel filters/effects, warps, extra channels, backgrounds and unmapped resources fail rather than being flattened implicitly. Opacity and fill opacity must already be exact byte fractions; arbitrary floating values are not silently quantized. Descriptive output metadata needs explicit `metadata_policy:{"mode":"strip"}`. Retain engine snapshots for variants, history, private notes and other editing state not represented in this subset.

The merged preview stores RGB composited against white plus a separate straight alpha plane, as required by compatible native readers. Reconstructing straight RGB from this 8-bit preview can lose precision at low alpha. The editable layers keep their original unassociated pixels. Independent consumers can also differ in final compositing rounding. Import validates the entire cache but reconstructs editable artwork from the layer channels.

The command is available in the Rust library, JSON CLI and MCP stdio. Ordinary create-only publication, source hash verification, cancellation, durable sessions, safe retries and undo/redo apply. Capability reporting describes the verified basic subset and its unsupported extended semantics.


## Nested folders

Normal isolated and normal pass-through groups retain sibling order, parentage, Unicode and duplicate names, visibility, exact byte opacity and whole-object locks. Empty and hidden folders remain editable. An importer pairs folder boundaries before returning any document; malformed nesting, more than 16 ancestor levels, more than 256 editable items or more than 512 serialized records fails. Non-normal group blends, group fill opacity, knockout, layer-role containers and folder records with cached pixel extents remain unsupported.

Native pixel positions are absolute. Export evaluates integer translations through the parent hierarchy without changing the source document; import uses identity group transforms and the equivalent absolute pixel positions. Scaling, rotation and fractional placements of plain pixel layers fail. With the explicit embedded-object or text delivery policy below, folder transforms may be resolved into child object or text placements; masks still need supported integer bounds. Folder open/closed state is identified as omitted UI metadata. Known minimum-reader compatibility values are checked and listed in the omission receipt; unknown versions and unknown appearance records fail.

Empty names are stored exactly in the file, but native consumers can generate names on opening or saving. The delivery receipt lists `empty_name_source_ids`, and its losses explain this behavior. Assign explicit names when stable external names matter. Original file bytes and engine source documents remain unchanged.

This completes a verified unit of extended interchange, not the entire checkpoint. Remaining mask controls, editable text, full embedded-object exchange, larger axes and the remaining group semantics retain their original acceptance requirements.

## Authored scalar masks

The current reader/writer retains gray8 mask planes independently of original layer RGBA, including normal and pass-through folders. Controls cover separate integer bounds, linked or document-fixed placement, disabled state, black/white outside coverage and exact byte density. Explicit constant masks retain empty planes and uniform outside coverage. RGB profile conversion does not change scalar mask bytes. Delivery receipts include mask bounds, original gray hash and retained controls.

Nonzero native feather, obsolete inversion flags, derived/combined masks, vector parameters, noninteger placement and implicit resampling fail explicitly. The engine triangular feather control is a different operation. Display-overlay metadata and inactive mask/effect ordering are listed in omission receipts; effects remain unsupported in this interchange subset. Masks count toward the same retained-pixel budget even while disabled.

Independent native import and return checks retain source RGBA, authored gray samples, bounds, linking, disabled state and density, with matching visible samples for the synthetic fixtures. This partial unit adds no completed checkpoint: **161/167 (96.41%)** remains the verified total. Feather and combined-mask controls, editable text, embedded objects, larger axes and remaining group semantics still require implementation and verification.

## Explicit embedded-source import

Embedded native RGB8 layered sources can be imported as retained editable objects with an explicit reconstruction and sharing policy:

```json
{"command":"layered.import","source_path":"C:/work/placed.psd","id":"editable","color_policy":"convert_srgb","embedded_objects":{"sampling":"nearest","sharing":"independent_copies"}}
```

`sampling` must select `nearest`, `bilinear`, `area`, `bicubic` or `lanczos3`. `independent_copies` explicitly converts native shared-source placements into independently replaceable engine objects. Source IDs and placed IDs remain in receipts so this change is visible. Omitting the policy rejects placed objects with an actionable error. Use `object.open`, edit the returned source and apply `object_replace`; ordinary session revision, retry and undo contracts apply. Engine snapshot delivery retains this editability. Native layered object delivery requires the separate explicit export policy below. Neither bounded mapping completes the extended checkpoint.

The importer validates modern placement descriptors, any matching legacy record, affine corners, source size/density, still-frame state, unwarped state and the unique referenced source table. It recursively decodes the editable source, including supported groups and masks, and applies the selected profile policy to each document. The source file is never modified. Placed and merged caches are decoded and hashed but never substitute for editable sources. Native interpolation and edge coverage can differ from the selected engine reconstruction, including scaled opaque sources; losses report this explicitly. This is not a claim of native composite equality.

Receipts include original source byte hashes, filenames, record versions, normalized snapshot hashes, source interpretations, omitted metadata, placement matrices and cache hashes. Native payload bytes remain in the original input; an imported object contains a normalized engine snapshot. Filenames are descriptive only and never opened. External links, aliases, non-layered payloads, selected layer comps, animation, active warps, perspective and unknown descriptor fields fail. Exactly empty annotation and external-link lists are admitted and listed as omitted nonappearance records.

Both container versions and the four input compressions use the same bounds. Embedded sources can have an all-zero allocation tail of at most 1 MiB only after a completely decoded merged stream and only when the entire embedded payload is a multiple of 1 MiB; ordinary top-level files still reject all trailing bytes. Maximum nesting is four, with 1,024 decoded editable items, 8 MiB of decoded source/mask/merged samples, 768 KiB per normalized source snapshot and an 8 MiB conservative snapshot-allocation budget including unique sources and independent placement copies. Per-document limits above still apply, as do ordinary engine rendering limits.

## Explicit embedded-source delivery

For `document.export`, set `layered_options:{"embedded_objects":"native_reconstruction"}` with `format:"layered"` or `format:"layered_large"`. Put the same options inside `output` for publication, preflight and durable jobs. The Rust library exposes `export_with_options` for either compression and container version. Omitting the policy keeps object export unsupported. Supplying layered options for another format fails.

Delivery writes each placement as an independent native embedded source with editable working-sRGB RGB8 layers, supported folders and authored masks. Each source uses the large container, even inside a standard outer file. Source frame size and physical density remain distinct from the affine destination corners, including resized object frames, rotations, reflections and parent transforms. Repeated engine snapshots get separate native source identities so replacing one does not alter another. Nested objects use the same explicit policy. Exact source snapshots and external files remain unchanged.

The native consumer chooses interpolation and edge coverage after editing or recomposition. Engine sampling and surface-scale settings are recorded in receipts but are not native controls. Per-layer caches and the merged preview come from the engine reconstruction; they are never substituted for the embedded editable source. This policy accepts visible reconstruction differences; it is not a native pixel-equality promise. Receipts identify source snapshot and delivered payload hashes, source dimensions/density, corners, generated IDs, sharing policy and nested losses.

Only independently retained working-sRGB sources with fully mapped editable semantics are delivered. External object links, HDR views, descriptive metadata inside a source, source filters/effects, unmapped resources and source pixel resampling fail. Text requires the additional policy below, including in nested sources. Strip metadata explicitly from a source copy before placing it; stripping the outer document does not authorize changing retained snapshots. Supported object masks remain separate authored planes and need an integer document-space placement; no mask resampling is implicit.

Delivery keeps the per-document canvas, item and stored-pixel limits, including object caches and masks in the 65,536 stored-pixel total. Nested delivery also bounds decoded logical samples to 8 MiB, editable items to 1,024, aggregate native source payloads to 32 MiB and nesting to four. Each source-table record is zero-aligned; incoming padding must be absent or exactly the required all-zero alignment. Cancellation and create-only publication apply to every nested source. Larger axes, editable text, additional group/mask semantics and the original extended acceptance remain open; **161/167** is unchanged.

## Explicit editable text delivery

Explicit `frame.first_baseline` controls currently require an additional native
authoring mapping and are rejected for this delivery format. Retain them in an
engine snapshot or use an output that renders the shared frame layout.

For either layered format, supply `layered_options.text` with `reconstruction:"native_layout"` and an explicit `shape_owner`. The latter is the receiving consumer's geometry-extension identifier: 1..128 ASCII letters or digits. Obtain it from a compatible original reference file's structural diagnostics or the consumer's contract, and verify delivery there. Inkbolt carries this identifier as data; it does not select an application or execute it. An arbitrary or unrecognized identifier can prevent paragraph geometry from reopening correctly.

Use `font_root` for direct export, or `resources.font_root` for document publication, preflight and jobs; sessions use their saved resources. Rust callers use `layered::export_with_fonts`. The source font files and their retained licenses must match the document's pinned identities. Each static TrueType outline face needs one unambiguous Unicode PostScript name. Other outline formats require a separate verified mapping. Different files or face indices with the same name are rejected across the complete delivery, including nested objects. At most eight face names are admitted. Fonts and licenses stay external: the receiving consumer resolves names and may use different font bytes. No installed-font lookup, substitution or font embedding occurs in Inkbolt.

The bounded subset preserves source text, character style ranges, opaque solid RGB fills, font sizes, tracking, explicit leading and Boolean `kern`, `liga` and `dlig` controls. Engine scalar indices become UTF-16 run lengths without splitting surrogate pairs. Newlines become native paragraph separators. Default-style gaps remain explicit, and a terminal separator belongs to the last style. Font sizes and other decimal units remain decimal tokens. Native tracking requires integral thousandths of em; delivery rounds to the nearest integer, with ties away from zero. `tracking_quantization` records each changed authored style index, source pixels, native units and delivered pixels. Engine source text and preview spacing remain unchanged. Automatic leading resolves to explicit per-style font metrics; this is a declared reconstruction change.

Frames must be horizontal, left-aligned LTR with single-run direction handling and no path. `wrap:false` delivers point text with the engine's first baseline incorporated into its affine placement; `wrap:true` delivers an explicit local paragraph box. Parent transforms are resolved into the text matrix. Point text accepts error/visible overflow; paragraph text accepts error/clipped overflow. Nominal point-frame bounds are not native editing constraints. Unicode bidirectional layout, fallback fonts, variable instances, language settings, other features, character alpha/non-solid paints and unmapped item controls fail explicitly.

Layer opacity, fill opacity, supported scalar masks and grouping remain separate from text and its preview cache. Text inside embedded objects requires both delivery policies. Per-layer and merged caches use pinned source fonts and engine rendering. The receiving consumer can reshape, reflow and rerasterize text differently; kerning, baselines, line breaks, hinting and antialiasing are not promised equal. Caches are never an editable source or evidence of native recomposition equality.

`layered.text` receipts identify each source item, text hash, character/UTF-16 counts, point/paragraph shape, supplied owner, source frame, native matrix and pinned font descriptors/names. They explicitly report `native_layout_equality:false`, `recipient_file_identity_pinned:false` per face and external fonts. Nested receipts and losses remain with the embedded-source receipt. Source documents/files remain unchanged. Publication is create-only; CLI, MCP, preflight and durable jobs share this contract.

Text allows at most 4,096 characters, 65 character runs after inserting default gaps, 65 paragraphs and a 64 KiB native text record. Caches and masks share the existing 65,536 stored-pixel and 8 MiB nested decoded-sample budgets. Independent original byte fixtures test ranges, Unicode, fonts, affine placement, caches and durable workflows. Native point/paragraph reopen-and-edit evidence is retained privately. Editable incoming text, global story semantics, further style/layout mappings and the original extended checkpoint remain open; this unit adds no checkpoint credit.
