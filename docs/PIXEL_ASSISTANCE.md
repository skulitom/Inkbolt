# Local pixel assistance

Agents can select an object from explicit foreground/background seeds, apply an editable mask, remove the selected pixels with local texture repair, reduce noise with a self-guided median, and enlarge a document with explicit reconstruction. These are original CPU operations. They need no learned model, model cache, GPU, account or network service. There is no semantic recognition, generative completion or invented high-frequency detail.

## Select and inspect

`assist.segment` accepts a document, an item `id`, `options`, an optional explicit `asset_root`, and ordinary execution `control`. Supported sources are inline RGBA8, encoded eight-bit RGBA/gray-alpha sample grids, and verified stored or embedded RGBA8 image assets. An image crop is applied before selection. Native source pixels are examined before masks, clips, opacity, filters and effects. High-depth, HDR and retained pixel deformations require explicit preparation; they are never silently reduced or baked.

```json
{
  "foreground": [[20, 18]],
  "background": [[0, 0], [47, 31]],
  "smoothness": 4096,
  "edge_scale": 4096,
  "include_costs": true
}
```

These are `options`, not a complete request. Seeds are integer `[x,y]` positions in the **cropped native pixel grid**, independent of document placement and display scaling. Each class requires 1..32 seeds. Positions must be unique across both classes. Multiple seeds supply multiple colour examples; every seed is a hard class constraint. The result can contain disconnected regions and holes.

The read-only result includes a binary native mask, source snapshot and pixel hashes, selected count, separate colour/boundary energy, an exact minimum energy/max-flow certificate, dependencies and measured work. `include_costs` adds `[foreground_cost,background_cost]` per row-major pixel and `[pixel_index,neighbor_index,cost]` for each right/down neighbour pair. This makes a decision independently inspectable, without model weights or a hidden confidence score.

The original optimizer uses these exact integer rules:

1. Each RGBA8 pixel becomes `[round(r*a/255),round(g*a/255),round(b*a/255),a]`. Hidden RGB in fully transparent pixels has no effect. This uses encoded sRGB bytes; it is not perceptual or linear-light colour distance.
2. Assigning a pixel to a class costs its minimum squared four-component distance to any seed in that class.
3. A differently labelled four-connected neighbour pair costs `floor(smoothness*edge_scale/(edge_scale+squared_distance))`. Smoothness is 0..65535; edge scale is 1..260100. Both default to 4096. Zero smoothness gives independent colour classification with hard seeds.
4. Hard seed costs exceed the sum of all maximum finite unary costs and all neighbour costs. The original bounded iterative flow solver computes an exact minimum cut. The cut's energy must equal maximum flow and all hard seeds must be satisfied, or the request fails. Among tied optima it returns the smallest foreground set (the intersection of minimum source-side cuts).

This is a precisely defined seeded colour/edge objective, not an assertion that its minimum is the intended object on every image. Similar colours, poorly chosen seeds, very small features and extreme smoothness can produce an undesired selection. Inspect the returned mask and costs and revise seeds or controls. The binary mask does not estimate fractional alpha matting; existing source alpha is retained when the mask is applied.

`{"op":"assist_mask","id":"pixels","options":{...}}` applies the same selection through atomic editing. The mask follows the item's transform; placed image masks include the native-to-display scale. Original pixel/asset/sample content stays unchanged. An existing pixel mask requires explicit `"replace_existing":true`. Locks, expected revisions, cancellation, undo/redo and retry rules are shared with ordinary edits. Read-only selection can inspect a locked item; editing it cannot bypass locks.

Limits are 65,536 cropped native pixels, 32 seeds per class and 67,108,864 selection work units. Stored image reading also retains the existing bounded asset limits and verifies the complete source asset identity. Cost construction, graph traversal and augmentation count toward the work budget. Selection returns no approximate mask on resource or deadline failure. Mask preparation, document validation and delivery retain their existing bounds. Stored assets need their explicitly supplied local root; embedded/inline inputs need no resource files. Unknown model or remote-service fields fail schema validation.

## Remove, denoise and enlarge

The selected mask composes with existing original operators; no second copy of those engines is introduced:

| Workflow | Atomic operation | Contract |
| --- | --- | --- |
| Remove an object | `repair` / `fill` | For an inline RGBA8 layer, put the returned mask's `gray_hex` in a full native `region`, and choose the original item as `source_id`. Local donor patches reconstruct the region; context and boundary error limits can reject unsuitable synthesis. Original pixels outside the mask stay exact. |
| Reduce noise | `repair` / `edge_correct` | Use the original item itself as `guide_id` for a self-guided weighted median. Radius, range sigma and maximum allowed change are explicit. The guide and target are frozen before the operation; no clean reference is supplied to the engine. |
| Enlarge | `canvas` / `scale` | Set the destination width/height and `sampling:"lanczos3"` (or another explicit supported kernel). Editable layer placement and original native samples remain retained. Reconstruction interpolates existing information; it does not recover unknown detail. |

Removal and denoising retain the inline RGBA8 scope of [REPAIR.md](REPAIR.md). Selection of an image asset or eight-bit sample grid does not silently convert it to that layer type. Reconstruction and border rules are in [RESAMPLING.md](RESAMPLING.md) and [CANVAS.md](CANVAS.md). Keep the original snapshot or use a persistent session; edits return new source states and session history preserves undo. Run removal from the original source snapshot, not an already extracted foreground view, unless retaining that mask is intentional.

## Original evidence and example

Run `python examples/pixel_assistance.py PATH_TO_ENGINE NEW_OUTPUT_DIRECTORY`. It writes original source snapshots, exact requests/responses, a selected cutout, local object removal, noisy/denoised charts, original/enlarged charts and comparison references into a new directory. The clean references are retained only for verification; the repair and denoise requests receive damaged/noisy inputs. Image assets remain immutable.

Tests enumerate all possible label assignments on small original grids and independently calculate costs, canonical ties and minimum energy. Larger original fixtures verify colour/edge coherence, alpha semantics, crops, display scaling, source files, byte-exact mask application and the maximum native grid. Quality checks reconstruct a withheld periodic texture exactly, reduce noisy-chart RMS to below 65% of the input without moving its edge, and compare every enlarged sample against an independent high-precision kernel calculation. Smooth-chart interior error must be less than half nearest-neighbour error; border pixels are still checked against the declared clamped reconstruction kernel. These bounds describe the original fixtures, not universal image-quality promises.

Private milestone evidence also records exact builds and dependency hashes, repeated execution in processes denied network access, stored asset availability, durable agent-client history and all required project checks. Built-in algorithm availability is explicit: there are no external model weights to install, download or silently substitute.
