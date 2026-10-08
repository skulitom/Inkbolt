# Pixel selections and permanent mask application

A document can retain one optional `selection:{width,height,gray_hex}`. It is a canvas-sized row-major grayscale8 field in document pixel coordinates. Zero is unselected, 255 is fully selected, and intermediate values are partial coverage. `null` means no active selection, which differs from an explicit all-zero selection. Both document kinds can use this state; permanent application to pixel content requires a raster document.

Selections do not print and do not implicitly change other operations such as `pixel_fill`. They are separate from the read-only `document.select` query for object IDs. Snapshot exports and session history retain them. Inspection returns dimensions, nonzero end-exclusive bounds, selected/full pixel counts, coverage sum and a SHA-256 of the scalar bytes. Structural diffs include selection changes, even when rendered pixels are unchanged. Artboard export drops selection state only in its temporary normalized clone; the source document remains intact.

## Operations

| Operation | Arguments | Effect |
| --- | --- | --- |
| `selection_set` | `selection` | Replace explicit scalar data, or use null to deselect |
| `selection_fill` | `selected` | Create a full or empty active selection |
| `selection_shape` | `boundary`, `combine`, `antialias`, `fill_rule` | Rasterize a rectangle, ellipse or closed polygon, then combine coverage |
| `selection_invert` | none | Replace every selected value with `255-v` within the canvas |
| `selection_refine` | `mode`, `radius` | Expand, contract or feather the active field |
| `mask_from_selection` | `id`, `linked`, `replace_existing` | Copy the current coverage into an item's editable mask |
| `mask_apply` | `id` | Bake an enabled mask into a finite pixel plane at native pixel centers |

All operations participate in ordinary atomic batches, expected-revision checks and durable undo. Selection changes affect document state but do not modify locked artwork. Creating or applying an item mask checks item, ancestor and descendant locks. Existing selection data is required for invert, refine and mask creation, and for non-replacement combinations. Invalid operations never create a partial revision.

Boundaries are `{shape:"rect",x,y,width,height}`, `{shape:"ellipse",cx,cy,rx,ry}` or `{shape:"polygon",points:[[x,y],...]}`. Coordinates are finite logical pixels; positive dimensions/radii and the existing geometry bounds apply. Polygons close automatically and allow 3 through 1,024 points. `fill_rule` defaults to `nonzero`; `even_odd` supports crossed or repeated contours. Shape geometry may extend off canvas. Use `selection_fill` for explicit full/empty fields rather than zero-sized shapes.

`combine` defaults to `replace`. Add uses `max(old,new)`, subtract uses saturating `old-new`, and intersect uses `min(old,new)`, independently at each pixel. These are scalar set operations, not paint compositing. Inversion is limited to the document rectangle. Clearing a selection removes its state; it does not mean an empty active selection.

Antialiasing defaults true. Rectangles use exact pixel-intersection areas. Ellipses use analytic horizontal intersections, and polygons use f64 edge intersections with explicit winding/parity. The latter shapes integrate exact horizontal interval widths over 256 equally spaced midpoint subrows per pixel. This original evaluator is independent of the drawing backend's coverage quantization. The final field rounds coverage to grayscale8 once. Independent polygon clipping/area and higher-resolution ellipse integration fixtures agree within one byte; finite subrow sampling is not an exact integral for arbitrary complex boundaries. With antialiasing disabled, coverage is binary membership at pixel centers, using half-open crossings and intervals.

Refinement modes are `expand`, `contract` and `feather`; integer radius is 0 through 32 document pixels. Expansion and contraction use square neighborhoods with maximum/minimum coverage. Feathering uses the separable triangular kernel documented in [MASKS.md](MASKS.md), with zero outside the canvas. Radius zero preserves the field. Calculation retains f64 intermediates and quantizes once after both passes. Outside values do not wrap or clamp to an edge; contraction of a full selection therefore shrinks its canvas-edge boundary. Refinement changes selection data, while an opacity mask's feather control remains reversible metadata.

## From selection to editable mask

`mask_from_selection` crops the selection to its nonzero bounds and copies all coverage inside that rectangle. Empty selections become a one-pixel zero mask. Outside the copied field is hidden. The selection itself remains unchanged. `linked` defaults true: the operation converts document coordinates through the inverse item world transform, so attachment preserves the selection's current position. Choose false for a mask fixed in document coordinates. Later link switches and mask transforms follow [MASKS.md](MASKS.md).

An existing mask causes an explicit error unless `replace_existing:true` is supplied. The copied mask starts enabled, uninverted, at density 1 and feather 0 with nearest sampling. Its source already includes any antialiasing or refinement in the selection. Subsequent mask controls remain independent of the original selection.

```json
{
  "operations": [
    {"op":"selection_shape","boundary":{"shape":"rect","x":20,"y":12,"width":80,"height":48}},
    {"op":"selection_refine","mode":"feather","radius":2},
    {"op":"mask_from_selection","id":"picture","linked":true}
  ]
}
```

## Applying the mask

`mask_apply` supports inline RGBA8 pixel layers, placed images and procedural fill layers in raster documents. It samples the enabled mask at each native source-pixel center mapped through the item's complete world transform. It multiplies source alpha by scalar mask coverage, then encodes straight RGBA8 once. RGB remains unchanged except that zero final alpha stores zero RGB. The mask record is removed; item ID, name, stacking, visibility, opacity, blend mode, parent and geometric clip remain. A disabled mask must be enabled before application; remove it instead to discard it.

Placed images use their integer crop's native dimensions. The result becomes an inline pixel layer, with a compensating item scale and inverse clip-coordinate adjustment preserving the placed frame. Its original asset descriptor, immutable store bytes and imported source remain untouched. Supply `asset_root` to `document.edit` for stored images; session editing uses its saved resource binding. Procedural fills evaluate the original paint and dithering at local pixel centers before mask attenuation and final rounding, then become inline pixels with nearest sampling.

Application samples a continuous transformed mask onto the finite native grid. Fractional transforms, bilinear reconstruction, zoom or later transforms can therefore produce different edge samples from a still-live mask. Existing alpha is also quantized to 8 bits before later item opacity or blending. Use a live mask when its continuous behavior is required; retain the snapshot or session history to reverse application. Text, vector content and containers need explicit rasterization before permanent pixel application; that conversion remains separate work and these combinations fail explicitly. No flattening or silent conversion of a group is performed.

## Limits

One selection allows at most 262,144 scalar pixels, separately from the existing 65,536 inline pixel/asset/pattern/mask budget. The complete snapshot still has a 768 KiB limit. Polygon/ellipse integration work is bounded by visible rows times subrows times `(visible columns + edges*(floor(log2(edges))+2))`, at most 67,108,864 units; ellipse edge count is two and binary coverage uses one subrow. Rectangle coverage is bounded directly by selection size. Refinement has the same work cap, counting `2*pixel_count*(2*radius+1)` taps. Large or highly complex operations fail before expensive evaluation.

Copying to a mask and permanent application must fit ordinary inline-pixel, mask-preparation and snapshot limits. A large selection can be valid while its copied mask exceeds a separate budget. Selection, mask and baked pixel data can coexist and all relevant budgets apply. Source assets remain external and licensed; application never overwrites them. Connected/color-range selection, image-guided edge refinement and saved alpha/ink channels are specified in [CHANNELS_AND_SELECTIONS.md](CHANNELS_AND_SELECTIONS.md). Broader mutable tiles and selection paths remain tracked requirements.

An item with editable viewport filters cannot use native pixel mask application: filtering precedes the item mask, and baking that mask into the source would reverse the order. This combination fails explicitly; the mask remains editable. See [FILTERS.md](FILTERS.md).
