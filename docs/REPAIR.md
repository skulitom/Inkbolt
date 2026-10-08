# Content-sensitive region repair

The atomic `repair` operation adds patch placement, local exemplar fill, content-sensitive move and guided edge correction to native pixel layers. Explicit source/guide IDs refer to inline raster items in the same document. Every operation freezes its input grids, preserves input snapshots and supports durable undo/redo and safe retries. No model, network service, application or device is required.

```json
{
  "op": "repair", "id": "pixels",
  "options": {
    "region": {"x": 12, "y": 9, "width": 8, "height": 6},
    "action": {
      "type": "fill",
      "fill": {"source_id": "pixels", "patch_radius": 1, "max_context_rms": 0.1}
    }
  }
}
```

Send it through `document.edit` or `session.apply`'s edit action. `region` follows [RETOUCH.md](RETOUCH.md): a nonempty integer rectangle within the target, with optional row-major gray8 `gray_hex`. Positive coverage defines the repair domain; fractional values blend the final result. `use_selection:true` multiplies coverage by the canvas selection sampled at world-mapped native centers. `opacity` defaults to 1, accepts 0..1 and controls the complete action. Zero-coverage bytes stay exact. Sources/guides ignore scene appearance and transforms; source locks allow reads, while target/dependency locks are enforced. Unsupported nonpixel inputs fail explicitly.

All image comparisons and interpolation use normalized **premultiplied encoded sRGB plus alpha**. Final straight RGBA8 encoding happens after the action's blending; repeated patches do not repeatedly quantize intermediate pixels. Unchanged hidden RGB stays intact. Parameter hashes, original/result pixel hashes, bounds, changed pixels, work and action-specific evidence accompany each edit.

## Patch placement

Use an action such as:

```json
{
  "type": "patch", "source_id": "source",
  "source_origin": [11, 10], "search_radius": 2,
  "context_radius": 1, "max_context_rms": 0.12,
  "blend": {"type": "heal", "screening": 0, "tolerance": 1e-9}
}
```

The source origin maps to the region rectangle's top-left corner. Search considers every integer origin within plus/minus `search_radius` in each axis; its default is 0, maximum 32. `context_radius` is 1..4, default 1. Context is the union of unselected target cells in those square neighborhoods around the positive domain, clipped to the image. Every selected/context sample must map into the source. A self-source placement must also avoid all selected source cells; known blemished pixels cannot become donors.

Each valid translation receives the mean squared difference across all four premultiplied channels of context cells. The minimum wins. Exact score ties prefer the least squared displacement from the requested source origin, then source row-major order. `max_context_rms` is required, accepts 0..1 and rejects a winning RMS above that limit. A nonempty domain with no surrounding context, or no valid donor placement, fails with `REPAIR_QUALITY`.

`blend` is the existing retouch `clone` or `heal` mode, including explicit healing controls. The chosen translation delegates to the verified native retouch operation. The receipt retains the selected origin, candidate/context counts, match RMS and full healing/clone measurements. The source remains unchanged. This is a translated patch; broader affine cloning is available through `retouch`.

## Local exemplar fill

The `fill` action takes a `fill` settings object:

- `source_id`: required explicit frozen donor layer; it may be the target itself.
- `donor_region`: optional source-native rectangle with an optional **binary** 0/255 mask. Omitted/null allows the complete source grid.
- `patch_radius`: 1..4, default 1; donor patches are complete `(2r+1)` square neighborhoods.
- `synthesized_weight`: 0.01..1, default 0.5, controls the matching confidence of previously synthesized context.
- `max_context_rms`: required 0..1 quality limit for every chosen patch.

Every donor patch must fit completely in the source and its allowed donor mask. For a self-source, the entire positive target domain is excluded from donors throughout the operation. Donor bytes never come from synthesized results.

At each step, the unknown target center with the most currently known context cells wins; exact ties use target row-major order. Its square context is clipped to the target image. Original known cells have weight 1; previously synthesized cells have the declared confidence. Every valid frozen donor patch is scored by the weighted mean squared premultiplied RGBA difference across that context. The exact minimum wins, with source row-major ties. The donor fills every still-unknown cell in the target patch. New pixels become known context for later decisions, while donors remain frozen.

Each patch must satisfy the RMS limit before progressing. Missing context, no complete valid donor, work exhaustion or excessive patch count fails atomically. There is no hidden approximate search, adaptive downsampling or relaxed threshold. The receipt records every target/donor center, context size/weight/RMS and filled count, plus the global candidate count and worst accepted RMS. These decisions can be independently replayed.

After synthesis, region/selection coverage and whole-action opacity interpolate once with the original target. Positive soft-mask cells are synthesized as complete unknowns; their fractional coverage affects final replacement. Empty domains preserve the target. A zero-opacity request still evaluates the selected action and quality conditions.

## Content-sensitive move

```json
{
  "type": "move", "offset": [10, 6],
  "fill": {"source_id": "pixels", "patch_radius": 1, "max_context_rms": 0.1}
}
```

`offset` is an integer native-grid translation. Every positive source cell's destination must stay inside the target image. First, exemplar fill reconstructs the complete selected source domain, using the same frozen donor rules. Region/selection coverage blends that repair into the original. Then the frozen original selected pixels replace the corresponding destination pixels using the same coverage. Finally, whole-action opacity interpolates the combined result with the original target once.

This order preserves the object through overlapping moves and avoids reading modified pixels. A full-coverage object retains its original visible RGBA content at full opacity; transparency uses premultiplied replacement, rather than source-over accumulation. Soft masks can retain portions of both background and object. Zero offset validates fields, source and donor mask, then preserves pixels without a donor search. Source snapshots remain available independently of undo history.

## Guided edge correction

```json
{
  "type": "edge_correct", "guide_id": "source",
  "radius": 2, "range_sigma": 0.04,
  "max_change_rms": 0.6, "minimum_effective_samples": 2
}
```

Guide and target native dimensions must match. The guide may be the target itself or a separate original edge reference. For each selected pixel, the algorithm considers the clipped square neighborhood of radius 1..16. The spatial weight is the separable integer tent `(r+1-|dx|)*(r+1-|dy|)`. It multiplies `exp(-guide_MSE/(2*range_sigma²))`, where MSE is the mean squared difference across four normalized premultiplied guide channels. `range_sigma` is 0.0001..1. Neighbor order is fixed.

For each target premultiplied channel, the weighted median is the first value whose cumulative weight reaches half the total. Values sort ascending, with source row-major ties. All channels use the same weights, retaining valid premultiplied ordering. Region/selection coverage and opacity blend the result with the original.

`minimum_effective_samples` defaults to 1 and accepts 1..1089. Effective support is `(sum weights)² / sum(weights²)`; a pixel below the requested minimum rejects the action. Required `max_change_rms` accepts 0..1 and bounds the **final quantized** per-pixel premultiplied change. This can reject an overly aggressive correction rather than silently reducing its strength. The receipt reports minimum support and maximum change. A separate clean guide can remove isolated noise while preserving thin high-contrast structures; a corrupted self-guide can intentionally protect the corruption as an edge.

## Quality, fidelity and limits

Optional common `max_boundary_rms` accepts 0..1 and checks the final encoded result. It measures four-channel premultiplied differences across the affected-domain/unselected four-connected boundary. A move uses the union of source and destination coverage. Exterior image faces are excluded, and the measurement is null when no in-image boundary exists. The gate only applies when a boundary exists. A failed quality gate discards the complete edit batch and leaves a persistent session head unchanged.

The quality thresholds are measurable numerical conditions, not a general guarantee of plausible photograph reconstruction. Repeated or ambiguous textures can admit several equally good matches. The algorithm neither infers object meaning nor promises to recover content absent from its explicit donors. Independent tests verify exact original periodic textures, an analytic smooth chart with predeclared reconstruction tolerances, original object moves, thin-edge preservation, exhaustive donor minima, weighted quantiles, masks, alpha and rejection cases. These complement the declared match/change/seam limits.

At most 4096 synthesis patches and 67,108,864 work units are allowed. Work counts target preparation, patch/context visits, donor comparisons, guided-neighborhood passes, output passes and any delegated retouch work; fixed per-cell arithmetic is not separately counted. Existing 65,536 aggregate inline-pixel and request bounds still apply. Full search can be expensive: narrow an explicit donor region or split a request when appropriate. Limits never silently reduce radius, precision or candidate coverage. Cancellation/deadlines are checked during search and before publication.

Snapshots and sessions preserve resulting editable pixel content. Save the starting snapshot and request to replay alternate settings; no live synthesis graph is stored in the document. `python examples/repair_workflow.py --output <new-directory>` writes four original tasks, preserved inputs, exact expected fixtures, requests, measurements and lossless PNG/TIFF/snapshot deliveries.
