# Retained vector appearance

An appearance object gives one editable source geometry several ordered fills and strokes. Agents can build outlined icons, layered diagram nodes and offset paint treatments without maintaining duplicate source paths. Each pass has a stable ID, and the document snapshot retains every source control.

## Create and inspect

Use this content in an ordinary item, or replace a vector item's content through the atomic `appearance` edit:

```json
{"type":"appearance","appearance":{"geometry":{"shape":"rect","x":8,"y":6,"width":32,"height":24},"passes":[{"id":"outline","stroke":{"color":[20,40,60,255],"width":6,"join":"miter"}},{"id":"body","fill":[30,160,220,255]},{"id":"inset","stroke":{"color":[240,250,255,180],"width":2}}]}}
```

`appearance.inspect` takes `document` and `id`. It returns the original geometry, fill rule, complete passes, compositing order and world bounds. Bounds union the mapped geometry of all passes, including disabled passes; strokes, raster effects and clipping are excluded. General object queries use type `appearance`. Edit the shared source through the complete appearance specification; general anchor edits target ordinary expanded vectors.

Passes run bottom to top. A pass requires a fill, a stroke or both; fill precedes stroke. It may also set `enabled` (default true), `opacity` (default 1), `blend` (default normal), `maps`, `tolerance`, `filters` and `effects`. Paint and stroke types reuse the existing contracts, including named paints and object/document stroke scaling. Inactive passes remain fully validated and retain resource dependencies.

## Ordered evaluation

Within each pass, ordered affine/perspective/envelope maps change source geometry, then fill and stroke paint that result, then ordered raster filters run, then decorations follow the existing layer-effect policy. Map order and filter order are significant. Decorations retain their existing behind-content and above-content placement rules; arbitrary interleaving of these pipeline stages is unsupported. See [WARPS.md](WARPS.md), [FILTERS.md](FILTERS.md) and [LAYER_EFFECTS.md](LAYER_EFFECTS.md).

Passes composite into an isolated stack. The owning item's transform, opacity, masks, clip, filters, effects and blend apply to that stack. Named paints, components, artboard views, artwork masks and cross-document transfer use existing resource and lock checks. Transfer pins inherited per-pass light directions to preserve their source meaning. Existing restrictions inside artwork mask sources still apply.

## Expand or bake explicitly

`{"op":"appearance_expand","id":"icon"}` replaces the appearance with an isolated group of ordinary editable vector objects. Each child retains the pass name and controls; live geometry maps are materialized under their saved error bounds. Raster filters and decorations remain live. The receipt identifies created objects and discloses loss of shared geometry and map controls. The input snapshot and session undo retain the original.

For delivery requiring ordinary pixels, use an explicit document-space viewport:

```json
{"op":"appearance_bake","id":"icon","asset_id":"icon-pixels","image_id":"icon-image","region":{"origin":[0,0],"width":64,"height":64,"scale":2}}
```

Baking renders the stack into a new immutable embedded RGBA8 asset, then places an image under an isolated group retaining the owner's outer controls. World-space capture followed by inverse placement preserves the current document-scaled strokes and transformed placement. The new asset and item IDs must be unused.

The declared viewport crops content outside its extent. Viewport filters are reevaluated in that region: use the full original canvas to preserve its boundaries. Resolution, paint identities, pass order and live vector/raster controls become pixels. Later enlargement or placement cannot recover their original resolution or editability. The receipt reports these losses; retain the original snapshot or undo history. Baking requires encoded sRGB, scale 1..4 and at most 65,536 generated pixels. It returns a new snapshot without writing files.

## Delivery and verification boundaries

PNG uses the shared renderer. SVG/PDF evaluate supported live passes into ordered vector paint objects; they retain their existing supported paint, blend, mask and color restrictions. Live raster filters and decorations fail explicitly for these vector formats: bake first when pixel delivery is intended. Snapshots preserve the full appearance. Use ordinary create-only publication and session history for agent workflows.

Original fixtures independently verify ordered paint arithmetic, vector-map and raster-filter order, expansion, source preservation and undo. A 32-case rational reference checks translucent intersections and box/offset/mosaic filters. Separate interpreters check actual native SVG/PDF path geometry, order, color and effective opacity. External renderer previews can differ through transparency quantization: five of 64 retained preview comparisons exceeded a fixed three-byte-level premultiplied bound, with a maximum of six. Those comparisons are recorded as exceptions, not passing pixel checks. No exact external-preview pixel guarantee is made.

## Limits and failures

An appearance has 1..16 uniquely named passes. Generated items, geometry, paint samples, masks, effects and filter work count toward existing document and execution budgets; expanded scenes must fit 256 items. Unlinked per-pass filter masks, recursively nested appearances and non-sRGB baking fail explicitly. Pass filter masks must use local linking. Unknown fields, missing paints, invalid controls, locks, unsupported delivery and resource excess fail atomically. Existing source documents and files are preserved.

Run `python examples/appearance_workflow.py --output <new-directory>` for an editable badge, expanded vectors, explicitly baked delivery, receipts and durable undo.
