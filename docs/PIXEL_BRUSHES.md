# Deterministic pixel brushes

`brush_stroke` paints, erases, smudges or mixes color in an existing inline pixel layer through the ordinary atomic edit API. `brush.inspect` returns normalized settings, a reproducible settings hash, dab count, path length, bounds and optionally every dab. All coordinates refer to the target's **native pixel grid**, before its scene transform. No tablet, driver, font, model, network or external brush asset is required.

```json
{
  "op": "brush_stroke", "id": "pixels",
  "stroke": {
    "points": [
      {"point": [8, 12], "size": 0.25, "opacity": 0.4},
      {"point": [32, 20], "size": 1, "opacity": 1}
    ],
    "diameter": 12, "hardness": 0.5, "spacing": 0.25,
    "flow": 0.6, "opacity": 0.8,
    "mode": {"type": "paint", "color": [30, 100, 210, 255]}
  }
}
```

Send the operation in `document.edit` or a session edit with the expected revision. To inspect it first, send `{"command":"brush.inspect","stroke":<settings>,"include_dabs":true}`. Inspection does not require or modify a document. Source snapshots remain unchanged; session edits retain undo/redo and safe request retries. The result contains ordinary RGBA8 pixels. Save the stroke request and its starting snapshot to replay with different controls; it is not a persistent live brush effect inside the document.

## Placement and programmatic dynamics

The stroke follows a piecewise-linear path of 1..1024 `points`. Each point has a finite coordinate within +/-32768 and optional `size`/`opacity` factors in 0..1, both defaulting to 1. Consecutive coincident nodes use the last node's controls. Size and per-dab opacity interpolate linearly with traveled distance. A stationary path makes one dab; zero size or opacity makes a nonpainting dab.

`diameter` requires 0.25..512 native pixels. `spacing` requires 0.01..4 (default 0.25), multiplied by the **base diameter**, independent of changing size. Dabs start at distance zero, then at integer multiples of that spacing. `include_end` defaults true and adds the terminal point if needed; it does not duplicate a spacing point already at the end within the declared floating-point tie allowance (16 relative machine epsilons). Equivalent path subdivisions retain placement/control values within f64 roundoff; settings hashes still distinguish the supplied control lists.

`scatter` defaults to zero and accepts 0..4 effective radii. Each dab's x/y displacement is uniform in the corresponding square. A SHA-256 stream over `inkbolt.brush.scatter.v1\0`, little-endian u32 `seed` (default 0) and u64 dab index yields two little-endian u32 words. Each word maps to `2*(word+0.5)/2^32-1`, then multiplies the effective radius and scatter. This sequence is independent of item IDs, clipping, texture and pixel iteration order. Inspection exposes both unscattered path points and actual centers. Bounds enclose all geometric dabs, including nonpainting controls; changed-pixel bounds are reported separately after editing.

## Tip coverage, texture and selection

`hardness` is 0..1, default 1. With effective radius R, the radial profile is 1 inside `hardness*R`, zero outside R, and `(R²-distance²)/(R²-(hardness*R)²)` in between. The integral over an unclipped plane is `pi*R²*(1+hardness²)/2`. A zero-size tip has zero coverage.

Coverage integrates this profile over each native pixel's unit square. Hard tips use original analytic circle/rectangle area. Soft tips integrate circle area over squared radius, splitting at geometric transitions and using adaptive Simpson evaluation. The absolute numeric convergence target is 1e-7 per pixel, with bounded recursion; unresolved convergence fails with `BRUSH_PRECISION`. This is a numerical stopping criterion, not an interval certificate. Independent vertical polynomial-slice integrals, analytic total mass and large/fractional edge fixtures verify final RGBA8 samples within one channel level. The implementation does not use a fixed subpixel stamp grid.

Optional `texture` contains `width`, `height`, `gray_hex`, `origin` (default `[0,0]`) and positive `scale` (default `[1,1]`, each 0.001..1024). At each native pixel center, nearest repeating texture lookup multiplies integrated coverage by its gray value/255. Texture is anchored in the native grid, not stretched separately onto each dab. Tiles have 1..4096 samples; bytes, bounds and fields are strict.

`use_selection` defaults false. When true, an explicit active selection is required. The native pixel center maps through the item's complete world transform and samples the canvas selection's containing cell; outside the canvas gives zero weight. It multiplies the texture/coverage weight. Selection bytes stay unchanged. Layer masks, geometric clips, visibility, effects and scene opacity retain their rendering roles; the brush edits underlying pixel content and does not bake those controls.

## Flow, whole-stroke opacity and modes

All processing uses floating-point **premultiplied encoded sRGB plus alpha**. `flow` (default 1) and per-point opacity multiply every dab's coverage. Overlapping dabs accumulate. After all dabs, `opacity` (default 1) interpolates the complete resulting pixel buffer with its original premultiplied buffer. This separates whole-stroke strength from repeated deposition. One final straight RGBA8 encoding occurs per stroke. Untouched bytes, including invisible RGB of zero-alpha pixels, are retained. Newly cleared pixels canonicalize to zero RGBA.

| Mode | Original, explicit behavior |
| --- | --- |
| `paint` | Required RGBA8 `color`; premultiplied source-over with weighted source alpha. Transparent paint is a no-op. |
| `erase` | Multiply the destination's premultiplied color and alpha by one minus the dab weight. Whole-stroke opacity applies afterwards. |
| `smudge` | First dab deposits nothing. Each later dab translates a sample from the previous dab's center to the current center, reading a frozen copy of the **pre-dab** target. Premultiplied bilinear sampling then interpolates the current pixel toward the sampled color/alpha. `border` is `transparent` (default) or `clamp`. Only this target layer is sampled. Scatter changes the actual transport displacement. |
| `mixer` | Required `color`, `pickup` and `load` (each 0..1). Reservoir starts at the declared color. Before each deposition, interpolate reservoir toward that color by load, then toward the coverage/texture/selection-weighted pre-dab target average by pickup. Deposit the resulting reservoir using source-over and the ordinary dab weight. An empty footprint has no pickup. Reservoir state lasts for this stroke only. |

Mixer pickup weights exclude flow and point opacity; these control deposition. Zero size, zero point opacity, zero flow or zero whole-stroke opacity skips that dab's processing while retaining the current center for later smudge displacement. The mixer defines a bounded color-reservoir model, not a physical fluid simulation. Source-over follows the public [compositing equations](https://www.w3.org/TR/compositing-1/#simplealphacompositing); brush placement, coverage, texture, transport and reservoir design are original.

## Limits, persistence and delivery

The target must be inline `raster` content in a raster document, under existing 65,536 aggregate stored-pixel limits. Convert a copy explicitly when starting from a rendered scene or an immutable image asset; image links, text and containers are not silently rasterized. Every target/dependency lock is honored. Invalid controls, missing selections, limits, cancellation or any later failure in the batch discard the complete candidate.

At most 8192 dabs and 67,108,864 work units are allowed per stroke. Units count footprint pixels, circle-area integration evaluations, copied smudge-buffer pixels and final encoding. An inexpensive footprint lower-bound check can reject oversized work before painting; actual numeric work is also counted. Cancellation/deadline checks run during preparation, preflight and evaluation and before publishing the candidate. Work checks fail explicitly without changing spacing, precision or controls. Native edges clip deposition; smudge's declared border policy controls reads.

Each edit change receipt includes the algorithm, normalized settings hash, source/result pixel identities, dab count/extent, path length, measured work and changed-pixel count/end-exclusive bounds. Inspection returns the complete normalized settings and optional dab data. Save the original request alongside snapshots when retaining exact brush instructions matters; session receipts/undo retain operation outcomes. PNG/TIFF delivery is lossless for the resulting native RGBA8 samples within the existing scene/export contract. Repeatability is for the same build and floating-point environment; cross-platform transcendental last bits and RGBA8 half-thresholds are not promised byte-identical.

`tests/test_pixel_brush_cli.py` independently checks integrated coverage/hardness, spacing and subdivision, dynamic size/opacity, flow versus stroke opacity, SHA-256 scatter, textures and transformed selections, erase, frozen-surface smudge, reservoir mixing, source bytes, hashes/bounds, limits, locks, batch rollback, snapshots, MCP/session undo/retry and create-only output. `examples/pixel_brush_workflow.py` saves original inputs, each stroke, inspections, edit receipts and image/snapshot deliveries for all four modes.
