# Layered pixel interchange

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

Delivery requires a raster document in working sRGB, original inline RGBA8 or equivalent native sample grids, nearest sampling and integer translation. Scale is one. Text, objects without an explicit delivery policy, other blend modes, pixel filters/effects, warps, extra channels, backgrounds and unmapped resources fail rather than being flattened implicitly. Opacity and fill opacity must already be exact byte fractions; arbitrary floating values are not silently quantized. Descriptive output metadata needs explicit `metadata_policy:{"mode":"strip"}`. Retain engine snapshots for variants, history, private notes and other editing state not represented in this subset.

The merged preview stores RGB composited against white plus a separate straight alpha plane, as required by compatible native readers. Reconstructing straight RGB from this 8-bit preview can lose precision at low alpha. The editable layers keep their original unassociated pixels. Independent consumers can also differ in final compositing rounding. Import validates the entire cache but reconstructs editable artwork from the layer channels.

The command is available in the Rust library, JSON CLI and MCP stdio. Ordinary create-only publication, source hash verification, cancellation, durable sessions, safe retries and undo/redo apply. Capability reporting describes the verified basic subset and its unsupported extended semantics.


## Nested folders

Normal isolated and normal pass-through groups retain sibling order, parentage, Unicode and duplicate names, visibility, exact byte opacity and whole-object locks. Empty and hidden folders remain editable. An importer pairs folder boundaries before returning any document; malformed nesting, more than 16 ancestor levels, more than 256 editable items or more than 512 serialized records fails. Non-normal group blends, group fill opacity, knockout, layer-role containers and folder records with cached pixel extents remain unsupported.

Native pixel positions are absolute. Export evaluates integer translations through the parent hierarchy without changing the source document; import uses identity group transforms and the equivalent absolute pixel positions. Scaling, rotation and fractional placements of plain pixel layers fail. With the explicit embedded delivery policy below, folder transforms may be resolved into child object placements; masks still need supported integer bounds. Folder open/closed state is identified as omitted UI metadata. Known minimum-reader compatibility values are checked and listed in the omission receipt; unknown versions and unknown appearance records fail.

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

Only independently retained working-sRGB sources with fully mapped editable semantics are delivered. External object links, HDR views, descriptive metadata inside a source, text, source filters/effects, unmapped resources and source pixel resampling fail. Strip metadata explicitly from a source copy before placing it; stripping the outer document does not authorize changing retained snapshots. Supported object masks remain separate authored planes and need an integer document-space placement; no mask resampling is implicit.

Delivery keeps the per-document canvas, item and stored-pixel limits, including object caches and masks in the 65,536 stored-pixel total. Nested delivery also bounds decoded logical samples to 8 MiB, editable items to 1,024, aggregate native source payloads to 32 MiB and nesting to four. Each source-table record is zero-aligned; incoming padding must be absent or exactly the required all-zero alignment. Cancellation and create-only publication apply to every nested source. Larger axes, editable text, additional group/mask semantics and the original extended acceptance remain open; **161/167** is unchanged.
