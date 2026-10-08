# Local layout assistance

`assist.layout` automatically arranges explicit artwork IDs into horizontal rows inside an explicit area. It chooses row breaks for the smallest total height while preserving input order and object sizes. This is useful for icon sheets, ordered diagram panels and asset layouts. It is an original deterministic CPU algorithm, with no learned model, model cache, GPU, account or network dependency. It does not generate semantic artwork.

```json
{
  "command": "assist.layout",
  "document": "SUPPLY_DOCUMENT_OBJECT",
  "options": {
    "ids": ["first", "second", "third"],
    "bounds": [8, 8, 120, 120],
    "gap": [6, 8],
    "horizontal": "center",
    "vertical": "center"
  }
}
```

The document placeholder above must be replaced with a document object. The command is read-only. It returns source identity and revision, row breaks, target and actual bounds, proposed local transforms, an exact rational minimum height, evaluated candidate count and measured placement error. Use the same options in `{"op":"assist_layout","options":{...}}` through `document.edit` or `session.apply` to apply the proposal. The edit recomputes from the document at the expected revision, preserves all source geometry and content fields, and returns the same report in its change details. Persistent sessions retain the original through undo, redo and retry receipts. Applying a proposal to another source requires replanning; the report is not an executable signed patch.

## Packing contract

- Supply 1..64 unique visible artwork IDs in the desired order. Ancestors and their descendants cannot both be selected. A selected group moves its complete subtree. Item, ancestor, descendant and shared-dependency locks are enforced.
- Bounds are `[min_x,min_y,max_x,max_y]` in document units, with positive extent and each coordinate within the existing absolute 32768-unit limit. Gaps default to zero and must be finite in 0..32768. Negative origins and fractional coordinates are supported.
- A row consists of consecutive IDs. Its width is the sum of item widths and horizontal gaps; its height is the tallest item. Rows begin at the area's top and have the requested vertical gap. The optimizer minimizes total row height, then row count, then lexicographic exclusive row ends. It evaluates at most 2080 candidate spans. This is a global optimum for this ordered shelf model; it is not free two-dimensional bin packing.
- Horizontal alignment positions the whole row within the area. Vertical alignment positions each object within its row. Each supports `start` (default), `center` and `end`. No object is resized, rotated, reordered in the scene or flattened.
- Packing uses existing **unclipped geometry bounds**. Text uses its frame. Strokes, effects, alpha silhouettes, clips, visibility inside groups, unselected artwork and fixed document-space masks do not influence these bounds. Leave adequate gaps for paint; unselected artwork is not treated as an obstacle. The existing mask and clipping coordinate rules remain in force after translation.
- Frames, adjustments, work paths and nonprinting resource sources cannot be selected or included in a selected subtree. Empty or zero-extent bounds fail. Ordinary artwork inside an artboard is supported; the artboard itself remains fixed. External font/image files are not loaded to calculate geometric bounds. Rendering still requires the document's ordinary explicit resources.

Widths and heights are exact differences of the existing binary64 bound endpoints. The row optimization and fit tests use exact rational arithmetic: decimal `0.1` plus `0.2` is slightly greater than stored `0.3`, and the optimizer does not silently round that excess away. The returned fraction describes the optimization of those stored bounds, not a new exact-curve measurement certificate.

Placement uses binary64 translation through inverse parent transforms and preserves each local linear transform. A candidate is revalidated and its actual bounds compared to the proposed geometry. Maximum allowed coordinate error is **0.0000001 document units** per bound endpoint; the observed error is returned. Containment and gaps inherit that bound (two adjoining objects can differ by twice that amount). An ill-conditioned transform that exceeds the bound fails with `LAYOUT_PRECISION`. `LAYOUT_NO_FIT` means the width or minimum ordered height cannot fit. Invalid controls, unsupported contexts, locks, cancellation and resource excess fail explicitly; no partial edit is returned. Repeating a request on the same snapshot is deterministic. Repeatedly editing an already placed document is not an exact floating-point idempotence guarantee.

## Agent workflow and verification

Run `python examples/assisted_layout.py PATH_TO_ENGINE NEW_OUTPUT_DIRECTORY` for an original editable module sheet, proposal, before/after images, SVG and PDF. The example writes a new directory and preserves the source snapshot. CLI, Rust library and MCP stdio use the same planner and atomic edit operation.

The independent partition oracle enumerates every row partition for small original fixtures; it does not reuse the engine's dynamic program. Tests cover cases where greedy packing is worse, exact fractional fit boundaries, every alignment, sheared/reflected/rotated parents, preserved hierarchy and geometry, full pixel arrays, limits, invalid fields, locks, durable undo/retry and failure atomicity. Private milestone evidence additionally records a larger independent corpus, actual delivered geometry and an execution environment with network access denied. Model availability is explicit: this built-in method requires no external weights. Unsupported learned-model and remote-service fields are rejected; there is no download or fallback.

Image subject selection, object removal, upscale and denoise assistance are tracked separately; this layout contract does not claim those raster checkpoints.
