# Ordered image sequences

Agents can import an explicitly ordered image collection or animated PNG, retain editable frame states, inspect exact durations, deliver PNG files or APNG and reopen any frame as an editable still. All commands share the Rust library, JSON CLI and MCP stdio. No playback service or network connection is involved.

## Frame model and editing

`document.variants.sequence` holds `{plays, frames}`. Each frame is `{id, dataset, delay: {numerator, denominator}}`. IDs are unique portable strings; the dataset must exist in the retained variant table. A frame applies the ordinary inherited variant values to a temporary source copy. It can change text, images, geometry placement, visibility or appearance through existing bindings. Repeated datasets remain separate ordered frames. Ordinary still rendering uses the currently selected dataset.

`sequence_set` installs or replaces the complete timeline atomically; `sequence: null` removes only timing. `sequence_frame` selects a frame by ID through the existing lock-aware variant selector. Variant definitions can change while retaining a valid sequence; removing referenced rows fails. Clear the sequence before clearing its variant table. Snapshots, diffs, session undo/redo and safe retries retain complete timing and original artwork.

`sequence_from_layers` takes an explicit ordered `ids` list, one `delay` and optional `plays` (default zero). It requires no existing variant table and 1–32 unique unlocked independent printable roots. It creates visibility datasets and selects the first frame. Selected roots are shown one at a time; unlisted objects retain their current visibility and may supply a shared backdrop. Source content and captured base visibility remain editable. Group subtrees are supported; clipped roots, adjustment layers and nonprinting definitions cannot become independent frames.

Delays retain their original unsigned 16-bit numerator/denominator. A zero denominator means 100; a zero numerator requests the consumer's fastest advance. `plays: 0` means indefinite repetition. `sequence.inspect` returns original fractions and cumulative start/end/total times as exact rational **decimal strings**, avoiding numeric overflow from unrelated denominators. It does not promise wall-clock playback precision.

## Import

`sequence.import` requires `source`, an absolute `store_root` and a document `id`; optional `resolution_ppi` defaults to 96 and `color_policy` defaults to `require_srgb`. `control` supplies cancellation/deadline options.

Two source forms are supported:

```json
{"type":"images","plays":2,"frames":[
  {"source_path":"C:/assets/second.png","delay":{"numerator":1,"denominator":24}},
  {"source_path":"C:/assets/first.png","delay":{"numerator":3,"denominator":100}}
]}
```

```json
{"type":"apng","source_path":"C:/assets/animation.png","compositing_space":"linear_srgb"}
```

Image lists preserve the supplied order, including duplicate files; they never sort or discover a directory. Every frame must have identical dimensions. Existing PNG/JPEG/TIFF asset import and explicit color policies apply; JPEG remains an opaque decoded source. Source receipts retain input identities and interpretation.

Animated PNG import accepts 8-bit samples, plus palette/low-depth grayscale that expand losslessly to RGBA8. It validates CRCs, frame counts, sequence numbers, rectangles and data ordering before decoding. It handles partial rectangles, SOURCE/OVER, all three disposal operations, transparency and Adam7. A separate default image is retained as a hidden `poster` item and never supplies the animation's initial backdrop.

OVER defaults to linear sRGB light values, then rounds displayed RGBA channels to nearest bytes after each frame. `encoded_srgb` is an explicit compatibility choice; the receipt records it. SOURCE retains every source channel. Compositing begins with transparent black; BACKGROUND clears only the frame rectangle and PREVIOUS restores its preceding canvas. Fully transparent composites normalize RGB to zero. Original files remain unchanged. Public format guidance: [PNG Third Edition](https://www.w3.org/TR/png-3/), animation chunks and alpha processing. The original adapter uses the locked external PNG codec; it does not copy a reference compositor.

APNG requires declared sRGB or explicit `assume_srgb`; ICC conversion, alternate color encodings, HDR, orientation transforms and 16-bit animation fail explicitly. Those static-image capabilities retain their separate commands and limits. File descriptions are returned in receipts where supported, not silently applied to artwork. Resolution is the caller's explicit document setting.

Each distinct full-canvas state becomes an immutable image asset, an editable image item and a visibility dataset. Equal states share an asset/dataset; timeline entries preserve all repetition and delays. Assets use create-only content-addressed storage. APNG decoding and document validation finish before asset publication. An interrupted publication or a later failure in an image-list import may leave valid cache assets; no partial document result is returned, no existing asset is replaced and original source files are preserved.

## Delivery and still handoff

`sequence.export` accepts `document`, optional `resources`, `scale`, `render_options`, `metadata_policy` and `control`. It returns ordered PNG artifacts, stable numbered filenames, SHA-256 identities, dimensions, raw delay fractions and play count. It writes no files. Retain its receipt with all frame files: PNG alone carries no animation timing. The existing PNG output-profile, metadata, alpha and quality contracts apply. All frames must succeed before a collection is returned.

`document.export`, `document.publish` and `session.publish` accept `format: "apng"`. Publication accepts `.png` or `.apng`, resolves resources and renders the complete sequence before creating a new destination. Output consists of full-canvas straight RGBA8 frames using SOURCE and no disposal. Delays and plays are preserved; the first animation frame is the static/default image. A hidden imported poster is retained in the source but is not reexported as a separate default. Metadata and density use the PNG delivery contract. APNG output is encoded sRGB; saved output profiles fail explicitly. Render sampling, padding and explicit HDR display views use the shared renderer; native high-depth animation is not implied. APNG is not an artboard-range format.

`sequence.open {document, id}` returns a new still snapshot at that frame, with editable source content and explicit timing/binding losses. Read-only opening/export works on locked artwork; selecting a different frame as an edit obeys locks. Publishing an ordinary still directly from a sequence also reports omitted order, duration and plays. Static files flatten the rendered result; the source snapshot and resources preserve editability.

For a Cutbolt handoff, open the selected frame, publish a PNG and bind its exact bytes/hash into a scene. Choose the destination hold and background explicitly. The original [sequence example](../examples/sequence_workflow.py) prepares a scene with one 1/25-second hold and a declared opaque background. Its optional `--cutbolt` argument runs local inspection and lossless scene compilation. This transfers a still, not the sequence clock or editable layers; the receipt records those losses and the encoded-sRGB matte composition. Keep the Inkbolt source, frame snapshot and recipe. It does not infer a movie frame rate or convert arbitrary fractions onto a video clock.

## Limits and verification

There are at most 256 ordered frames and 32 distinct imported states or selected layer roots, under the existing variant/binding/resource limits. Each render canvas fits the ordinary 1,048,576-pixel evaluation limit. Aggregate import/output pixels are at most 16,777,216 (including any imported poster); evaluated scene work, including supersampling/padding and item count across frames, is capped at 67,108,864. Each frame also passes the renderer's complete shape/effect/resource budgets. APNG uses a bounded 32 MiB writer; PNG collections have an aggregate encoded-output bound. Normal request, document and resource limits still apply. No audio, realtime playback or implicit interpolation is introduced.

Cancellation is checked between frame operations, compositor rows, encoding writes and before publication. One bounded render or codec call completes before its next check. Image-cache publication has the partial-cache boundary described above. Existing destination files and original documents remain unchanged after errors.

`tests/test_sequences_cli.py` supplies twelve original contract checks. Independent verification additionally compares 50 sequences/388 frames against rational and high-precision color references, including every pair of source/destination alpha bytes in both compositing spaces. An independent FFmpeg decoder checks every exported frame; stored assets, PNG collections, timing, source snapshots and an actual Cutbolt still render are checked separately. Official Inspector verifies schema discovery, imports/exports, history, retry, cancellation and create-only publication. Private outputs stay outside the repository.

Exact-palette GIF sequence import/export, explicit background interpretation, binary alpha and exact centisecond timing are described in [EXTENDED_IMAGE_IO.md](EXTENDED_IMAGE_IO.md).
