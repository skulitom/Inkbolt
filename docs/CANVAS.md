# Raster canvas operations

Use `document.edit` or a durable session edit with `{"op":"canvas","action":{...}}`. These operations currently require raster documents. They preserve layers, IDs, hierarchy, source pixel bytes, image crops, font descriptors and source files. A batch is atomic and creates one session undo point.

| Action | Required fields | Behavior |
| --- | --- | --- |
| `crop` | `x`, `y`, `width`, `height` | The integral rectangle in the current canvas becomes the visible output. Content moves by `[-x,-y]`; negative origins add transparent space. Artwork outside the canvas remains editable. |
| `extent` | `width`, `height` | Change visible canvas dimensions without scaling content. Optional `anchor` defaults to `center`. |
| `scale` | `width`, `height`, `sampling` | Scale the whole scene by `[new_width/old_width,new_height/old_height]`. Set every pixel/image item's sampler to `nearest`, `bilinear`, `area`, `bicubic` or `lanczos3`. |
| `resolution` | `ppi` | Change physical resolution metadata only. Pixel dimensions, artwork and rendered sample bytes stay unchanged. |

For example:

```json
{"op":"canvas","action":{"type":"crop","x":4,"y":2,"width":16,"height":12}}
```

The nine extent anchors are `top_left`, `top`, `top_right`, `left`, `center`, `right`, `bottom_left`, `bottom`, `bottom_right`. Each axis translates by zero, `floor((new-old)/2)`, or `new-old`. Floor also applies to negative odd differences, so the result is integral and deterministic. Extension is transparent where no retained artwork exists; it can reveal artwork outside the previous viewport. Add an ordinary background layer when another color is wanted.

Crop state is represented by the current dimensions and translated root items. Its resolved transformation and before/after dimensions are returned in the edit receipt and retained in session history. Reframing to the inverse rectangle reveals retained off-canvas artwork. To keep a cropped window while later enlarging the canvas, group its items and attach an editable geometric clip before reframing; the example does this explicitly. There is no destructive pixel deletion or hidden flattened replacement. Keep the original snapshot/session history to restore every document field, including canvas-bound auxiliary planes.

## Coordinate and sampling contract

Only printing roots and ordinary nonprinting work-path roots receive the scene transform; descendants follow their parents once. Local masks, clips, text, guides and frame geometry retain their settings. Unlinked grid masks, filter masks and artwork-mask references receive the same document-space transform. Shared mask-source trees stay in their original local coordinates, including locked source definitions. All affected ordinary items, including hidden descendants, must be unlocked. A resolution-only edit may leave locked artwork in place.

Scaling rerenders editable objects at their new placement. It does not resize a flattened composite or repeatedly resample stored source pixels. Pixel/image reconstruction uses the explicit method, with source-edge clamping inside the item/crop. Area, bicubic and Lanczos3 include footprint-aware reduction; see [RESAMPLING.md](RESAMPLING.md). Independent frame coverage still clips each item. Text and artwork masks rerender at output resolution; their original font sizes, local geometry and source settings persist. Selected image sampling does not replace each mask's own sampler. Standalone artboard exports keep their declared local dimensions and exclude the artboard placement transform, as before.

Nearest sampling chooses the floor of a source coordinate. To stabilize affine roundoff at exact pixel boundaries, a coordinate within `8 * f64::EPSILON * max(1,abs(coordinate))` of an integer snaps to that integer first. The same rule applies to nearest image, scalar-mask, displacement-map and resized selection/channel sampling. Values beyond that tolerance retain the ordinary floor decision. Reconstruction weights remain floating-point; an exact rational half-byte tie may round to either adjacent byte through f64 arithmetic, consistent with existing compositing.

Selections and named channels are canvas-sized scalar grids. Crop/extent copies intersecting bytes and pads with zero; their out-of-canvas values remain available through the original snapshot or undo. Scaling resamples each grid once with the chosen method and clamped edge samples. Channel names, roles and IDs persist. This differs from layer/source pixels, which remain unchanged outside the viewport. Masks already copied from a selection are independent item resources and follow their own coordinate rules.

Resolution is unchanged by crop, extent and scale. `resolution` accepts 1 through 9600 ppi, including fractions. PNG physical-resolution metadata rounds to integer pixels per meter. Export scale continues to multiply pixel dimensions and ppi together.

## Effects, limits and failures

When any viewport filter or layer effect is present, crop/extent/scale requires `"effect_policy":"preserve_parameters"`. Controls, including document-pixel radii, offsets, noise seeds and block sizes, stay unchanged; the new viewport and transformed item-local centers/masks are reevaluated. This can change edge appearance. Automatic effect-parameter scaling is not implemented. Pointwise adjustments and sibling clipping retain their normal scene semantics. Dissolve's item-local cells follow transformed content; its saved seed is unchanged.

Dimensions must be 1 through 32768 pixels; integral crop origins must be within -32768 through 32768. Transformed geometry still must pass ordinary coordinate bounds. Selection and aggregate channel storage limits are checked before allocating resized planes; ordinary document-byte, item, mask and render-work limits also remain active. Structural edits can succeed for canvases too large to render under current output limits; a later render fails explicitly. Errors include operation indices, and a failed batch returns no modified document.

Current resamplers are nearest, bilinear, area, bicubic and Lanczos3. The latter three include explicit footprint and work bounds, verified independently as described in [RESAMPLING.md](RESAMPLING.md). Vector canvas origins/unit/color extensions are separate requirements. Unsupported samplers, kinds, dimensions and filter policies fail explicitly.
