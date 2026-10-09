# Visual revision comparisons

`document.diff.preview` compares `before` and `after` snapshots of the same document ID and kind. Each input may be inline, an exact saved revision or a hash-pinned snapshot file. `before_resources` and `after_resources` independently inherit saved bindings or accept explicit roots. Workspace defaults and containment follow the ordinary request contract.

`session.diff.preview` accepts `session_root`, `session_id`, `from_revision`, `to_revision`, optional `options` and `control`. Workspace sessions can omit the root. Both immutable revisions and their saved resources are captured in one read-only transaction, released before rendering. `observed_current_revision` is separate from the compared revisions. Neither command changes documents, history, request receipts, sources or output files.

Session comparison captures use a read-only database connection and therefore do not perform hot-journal recovery after an interrupted writer. Recover and inspect such a store first with `session.verify` or an ordinary session read; retain its database and journal together. See [session recovery](SESSIONS.md).

```json
{
  "command": "session.diff.preview",
  "session_id": "poster",
  "from_revision": 3,
  "to_revision": 4,
  "options": {
    "focus": {"type": "items", "ids": ["heading", "badge"], "margin": 8},
    "scale": 2,
    "threshold": 0
  }
}
```

Options default to canvas focus, scale 1, threshold 0, ordinary render settings and `include_structural:true`. `before_render_options` and `after_render_options` explicitly select each side's antialiasing, padding and HDR display view. Linear scenes requiring tone mapping fail with `HDR_VIEW_REQUIRED` unless the corresponding view is supplied. Different render settings are retained in each side's `full_render` receipt; any resulting pixel differences are included.

## Coordinates and focus

The three `artifacts` (`before`, `after`, `mask`) share dimensions and pixel coordinates. Document views align in world coordinates; resized or moved canvas windows expand the common bounds and use transparent black outside each source's rendered extent. No image registration or resampling hides movement. Origins must differ by an integer number of output pixels at the selected scale (only 1e-9 pixel arithmetic roundoff is tolerated). Incompatible phases return `INCOMPATIBLE_PIXEL_GRIDS`; select a compatible scale or a standalone artboard view explicitly.

| Focus | Behavior |
| --- | --- |
| `canvas` | Union of the complete rendered pixel extents, including the last partially covered pixel for fractional canvases |
| `region` with `bounds:[min_x,min_y,max_x,max_y]` | Round outward on the before image's grid; clip to the union of rendered extents |
| `items` with unique, nonempty `ids` and optional nonnegative `margin` | Union the selected geometry from **both** snapshots, retaining old/new locations and added/removed items; an ID missing from both fails. Hidden geometry participates; strokes/effects do not expand bounds. Other artwork remains visible |
| `artboard` with `id` and optional `include_bleed` | Compare the standalone owned artboard subtree in artboard-local coordinates, with original appearance and bleed semantics. The artboard must exist on both sides. Placement changes remain in structural differences and the separate world mappings |

`actual_bounds` describes the shared image in `bounds_space` (`document` or `artboard_local`). Requested region/item bounds remain explicit; canvas/artboard requests use null `requested_bounds` for their rendered union. `clipped_to_render` reports clipping to the union. Each side retains its original full-view metadata, source PNG hash and coordinate map. Use `comparison_mapping`, not the original view's `mapping`, for the three common-grid images. Matrices map pixel edges; pixel centers are `(x+0.5,y+0.5)`. Changed/highlighted end-exclusive pixel bounds also return four world corners separately for each side, including rotated or moved artboards. Empty differences return null bounds/corners.

## Color and numerical meaning

Comparisons use sRGB RGBA8 display pixels. Original output ICC profiles are validated, recorded and included in source identity, but are **not applied** to these review images. This avoids comparing differently encoded delivery bytes as though they represented the same color. Root output profiles are removed only from ephemeral preview copies; sources remain intact. The existing preview compositor, artboard materialization, HDR view, sample projection and loss annotations are reused. These PNGs carry sRGB tags and a fixed review density of 96 ppi; coordinate scale is explicit and does not derive from that density.

`pixels.changed_pixels`, `changed_bounds` and `maximum_channel_delta` include every nonzero absolute difference in any rendered RGBA8 channel. `highlighted_pixels` and `highlighted_bounds` use the **strictly greater than** `threshold` rule (integer 0..255). The mask is opaque magenta for highlighted pixels and transparent black elsewhere. Threshold 255 highlights nothing but preserves exact counts. This is a channel comparison, not a perceptual color metric. Output-profile-only, hidden, off-view and sub-byte retained-sample changes can have no displayed difference. Inspect structural changes, print proof or retained samples for those purposes.

Structural comparison is included by default and has the existing stable-ID, resource, geometry and source-hash contract. `include_structural:false` returns an explicit null; visual equality alone does not establish document equality. Original document hashes and revisions are always retained. Legacy `document.diff` and `session.diff` retain their positional, equal-size scale-1 pixel comparison; they now use controlled rendering and document validation, but do not acquire the new alignment semantics.

## Limits and review workflow

Both full source views retain existing render limits, including at most 1,048,576 evaluation pixels each with padding and supersampling. The common cropped image is independently limited to 1,048,576 pixels. A large union can use a smaller region; a small region does not bypass either source's full evaluation limits. PNG decoding and intermediate buffers are bounded. This implementation reuses complete previews and does not claim incremental rendering or a measured peak-memory improvement. Cancellation/deadline failures return no partial result.

1. Use `session.dry_run` with `include_document:true` to prepare a hypothetical revision.
2. Compare its `proposed_document` against the pinned base with `document.diff.preview`; provide the proposal's resources explicitly if its bindings changed.
3. Review structural changes, the aligned images and exact/thresholded regions. Run `document.check` and `document.preflight` as needed.
4. Apply the checked proposal. The committed revision can be compared with `session.diff.preview`; later head changes do not alter the requested historical result.

The compact MCP catalog exposes `session.diff.preview`; the document variant is available through `inkbolt_run` and the full catalog. `response_format:"preview"` sends each distinct PNG payload once with explicit references and retains the exact result for reconstruction. Equal before/after images share a payload; existing attachment/count budgets and inline overflow rules apply. CLI results retain ordinary base64 artifacts.

`tests/test_visual_diff.py` checks independent per-pixel masks and bounds, alpha and threshold boundaries, resized/shifted/fractional grids, old/new item focus, artboard world maps, ICC-only changes, explicit HDR views, checked proposals and pinned history/files, MCP reconstruction, no-write behavior and resource limits. Typed Rust guards reject nonfinite option values before producing images. These contract tests add no engine checkpoint credit or autonomous model benchmark evidence.
