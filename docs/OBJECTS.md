# Retained embedded and linked objects

Raster documents can place a complete editable vector or raster snapshot as `content:{"type":"object","object":...}`. The object retains the exact UTF-8 source string and its SHA-256, including original pixels, hidden transparent color, layers, fonts, geometry, metadata and nested sources. The parent placement has its own identity, transform, opacity, masks, clipping, effects and supported pixel deformation. Editing a placement does not rewrite its retained source.

## Import, reopen and replace

`object.import` accepts exactly one `source_path` or inline `snapshot`. It returns an object descriptor without writing any file. File imports may declare a `link_key`. The source must be an Inkbolt snapshot; external native formats remain separate interchange work. Existing image and SVG imports can produce editable snapshots for placement. Referenced image/font bytes stay in their pinned stores and resolve through the parent request's explicit `asset_root` and `font_root`.

`object.open` takes a parent `document` and item `id`. It returns both the exact retained `snapshot` string and a validated editable `document`. Default fields may be populated in the latter; the former preserves exact bytes. This command does not read the link. Edit the opened document using ordinary operations, import its new snapshot, then apply `object_replace` to the selected parent item. Existing inputs and other placements stay unchanged.

```json
{"op":"object_replace","id":"placed","object":{"snapshot":"...","sha256":"...","width":24,"height":24},"keep_frame":true}
```

`keep_frame` defaults to true and retains the previous placement width/height. False uses the replacement descriptor's dimensions. The item's transform, identity and appearance stay intact. Ordinary duplicate and transfer operations copy an independent retained value, including a link declaration when present. Refreshing or replacing one copy does not change another. Locks, atomic batches, durable sessions, undo/redo, diffs and retry receipts use the shared engine contracts.

## Explicit links

Links contain a portable flat `key`, such as `motif.json`, without an absolute path or traversal. A caller supplies the runtime `link_root`. Resolved files must remain directly inside that root; directory escapes fail explicitly. Neither document validation nor rendering reads a link. The saved snapshot is always the rendering source.

`object.status` takes `document`, `id` and optional `link_root`. It reports embedded, unchecked, current, changed, missing, invalid or unavailable state. Missing/invalid files do not discard the retained source. Changed files include their observed SHA-256.

```json
{"op":"object_refresh","id":"placed","link_root":"C:/workspace/sources","source_sha256":"<hash observed by object.status>"}
```

Refresh reads the file once, checks the exact expected hash, validates its snapshot and replaces only that object's retained source. It keeps the placement frame, reconstruction controls and view. A source changed since inspection fails with `OBJECT_SOURCE_CONFLICT`. Malformed, oversized and missing files fail before the batch commits. `object_detach` clears the link while preserving source bytes. No command writes to a link source. Session retries replay the committed result without rereading a changed or missing file.

## Rendering and delivery

Each source renders in its own document context to a straight f64 surface before parent reconstruction. `surface_scale` is an explicit integer from 1 through 4, default 1; it selects source evaluation resolution. Source geometry remains editable at every setting. This is bounded offscreen raster evaluation, not native vector page embedding. `sampling` selects nearest, bilinear, area, bicubic or Lanczos3 reconstruction. Pixel deformations currently require nearest or bilinear. Parent supersampling follows the ordinary renderer; it does not silently change the chosen source surface resolution.

Encoded sources decode before reconstruction into a linear parent. Native linear HDR sources require a linear parent or an explicit object `view`. Views retain the HDR source, apply the selected display transform to the completed source surface, and affect only this placement. High-depth values retain f64 working precision until final delivery. Transparent rendered composites have zero color; the retained source keeps hidden color and exact original sample bits.

PNG/JPEG/TIFF and artboard image delivery use the shared image controls and create-only publication. Snapshot delivery retains editing state. Native PDF/SVG object delivery is explicitly unsupported; image delivery does not imply editable object interchange. Descriptive metadata sanitization recurses into retained snapshots, computes new source hashes and detaches links in the sanitized copy. Ordinary snapshot export without a metadata policy retains exact originals. Resource manifests include nested pinned image/font identities without source contents or runtime paths.

## Bounds and diagnostics

Source snapshots and the complete parent retain the existing 768 KiB document limit. Placement dimensions require 0.001..32768. Nested retained sources are limited to four levels; rendering evaluates at most 32 object surfaces. The existing 67,108,864 work and 4,194,304 buffer-pixel budgets are also charged cumulatively across object evaluations, including completed surfaces. Limits can reject an otherwise individually valid source when placed in a larger composition. No lower-resolution fallback is selected silently.

Invalid hashes, duplicate JSON keys, unsupported source formats, mismatched HDR views, missing resource stores, source conflicts, locks and aggregate resource limits produce structured errors. Source files, fonts, image bytes and prior snapshots remain unchanged. Run `python examples/object_workflow.py --output <new-directory>` for an original retained motif, independent replacement and image delivery.
