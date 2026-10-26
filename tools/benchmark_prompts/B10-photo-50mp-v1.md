# B10: Edit a 50 MP photograph (photo-50mp-v1)

Open `original.tiff`, an original synthetic studio scene, 8192 by 6144 pixels,
16-bit RGBA in encoded sRGB with straight alpha. Preserve this source,
`fixture-profile.json` and this prompt. Repair only rectangle (5114,3835,20,16)
in zero-based pixel coordinates by copying the same-layer original rectangle
96 pixels left. Copy every 16-bit channel exactly, including alpha. Keep every
other sample unchanged. Do not rescale, quantize or change color interpretation.

Deliver `edited.tiff`: full-size, single-image, uncompressed, interleaved RGBA16
TIFF with unsigned channels, RGB photometric interpretation, straight alpha and
top-left orientation. Retain an editable native layer. Deliver `preview.png`,
the exact 20 by 16 repaired region in RGBA8, mapping each channel to 8-bit with
`(value * 255 + 32767) // 65535`. Use new output files. The judge checks every
TIFF sample, including low bits and all unrelated regions.

With Inkbolt, use `sample.import` with `storage:{}` and
`color_policy:"assume_srgb"`. Choose your own document/session/request IDs;
keep layer `pixels` and all other default document properties. Save revision 0.
Review one clone repair through `session.dry_run` with `include_document:true`,
then commit that same proposal. Deliver the exact import result as
`import-report.json` and the dry-run result as `review.json`. Keep immutable
native blocks. Use tiled evaluation for previews and TIFF publication.

Deliver `before.json` (revision 0), `edited.json` (reviewed edit, revision 1),
and `historical.tiff` from the original saved revision. Undo once and deliver
`undo-source.json` (revision 2), then redo once and deliver `editable.json`
(revision 3, matching the final session head). Verify history. Deliver
`publication-report.json` with exactly `edited` and `historical` entries
containing the unchanged TIFF publication results, including their hashes.
Deliver `session.json` with your actual IDs and exactly this shape:

```json
{"session_id":"your-session","requests":{"create":"your-create-request","edit":"your-reviewed-edit-request","undo":"your-undo-request","redo":"your-redo-request"}}
```

For the no-engine baseline, use the supplied pinned Python/Pillow environment
and ordinary file/shell tools. Retain the edited native layer in `edited.tiff`
and deliver `editable.json` with exactly this manifest:

```json
{"width":8192,"height":6144,"image":"edited.tiff","depth":"u16","channels":"rgba","encoding":"encoded_srgb","transform":[1,0,0,1,0,0]}
```

Multichannel Pillow conversion can lose 16-bit precision. Standard-library
byte/array processing can retain exact samples; Pillow can produce the focused
PNG. The judge independently checks TIFF bytes and reopens the result with the
pinned tool. Import/proposal, saved revisions, undo/redo, immutable engine tiles
and session integrity are separate engine-only checks, inapplicable to baseline.

This separate large variant has a fixed ceiling of **512 MiB peak committed
memory per engine/tool process** across import, review, repair and delivery.
External runs must spawn work under the configured client, without offloading
to pre-existing workers. On Windows, the largest process peak in the owned tree,
including launcher and client, supplies a conservative upper bound. A larger or
unavailable observation does not establish the requirement; client-written
memory claims are ignored/rejected. Linux commit measurement remains unavailable
and fails this check explicitly. Resident memory cannot replace it.

Results belong only to `photo-50mp-v1`. They do not replace or combine with the
original 1920 by 1080 B10 fixture and its unchanged 256 MiB budget.
