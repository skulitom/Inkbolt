# Editable viewport filters

Items carry an optional `filters` array in first-to-last evaluation order. Each filter has a stable item-local `id`, an `operator`, `enabled` (default true), `opacity` (default 1), `blend` (one of the 26 modes in [BLENDING.md](BLENDING.md); default normal), `border` (default transparent) and an optional grayscale `mask`. The `filters` edit operation atomically replaces the complete array, allowing settings changes, reordering, insertion and removal through the same CLI/library/MCP contract. An empty array removes the effects. Snapshots, duplication, semantic comparisons and durable session history retain all settings and original source content.

```json
{
  "op": "filters", "id": "picture",
  "filters": [
    {"id": "soften", "operator": {"type": "gaussian", "sigma": 2}, "border": "reflect"},
    {"id": "motion", "operator": {"type": "directional", "length": 6, "angle": 30, "samples": 33}, "opacity": 0.4}
  ]
}
```

## Evaluation domain and order

The input is the object's rasterized image in the current render viewport, after its geometry/world transform but before its item opacity, geometric clip, opacity mask, blend mode and any following clipped adjustment chain. An isolated group supplies its complete child composite. Parent effects then operate on the composite as usual. This makes filters useful for both pixel images and editable vector artwork. Source geometry, imported assets and pixel bytes remain unchanged.

The domain is explicitly the render viewport: content outside that viewport has already been clipped before filtering. Effects can spread outside an object's geometry within the viewport. Borders extend the viewport grid, not the object's rectangular bounds or alpha silhouette. Export artboards to evaluate their independent local viewport; use bleed to provide additional filter area. Queries still return geometric bounds, not blurred bounds. This is a viewport effect, not a native-resolution image rewrite.

Radii, sigma and directional length use document pixels, multiplied by export scale (1 through 4). Object scaling does not scale these controls. Directional angles use document axes with positive angles turning toward positive y. Radial centers use item-local coordinates and follow the complete world transform; radial angle and zoom act in document axes. Standalone artboard exports remove ancestor placement and shift the board's own center and linked masks for bleed. Unlinked masks convert to the export coordinate system.

Input storage/output are encoded-sRGB RGBA8. Internally, premultiplied encoded-sRGB color and alpha use f64, including all filter stages, with one final straight-RGBA8 quantization. Invisible source RGB does not bleed into visible edges. These filters do not imply linear-light, profile-managed or high-depth workflows. Unsupported document depth/color representations fail during request validation. Integer export scale evaluates a newly rasterized grid; it is not merely scaling a previously filtered bitmap.

## Operators

| Operator | Controls and numerical definition |
| --- | --- |
| `box` | Integer `radius` 0..32. Uniform square convolution over `(2r+1)^2` samples, implemented as two separable passes. Zero radius is identity. |
| `gaussian` | Finite `sigma` 0..16. Sample the Gaussian at integer offsets through `ceil(3*sigma)` on each axis, normalize the discrete one-dimensional weights to one, then apply their outer product. Zero sigma is identity. At export scale, scale sigma before finding support. |
| `directional` | `length` 0..64, finite degree `angle` within Â±360000, odd `samples` 3..129 (default 33). Average equally spaced, bilinearly sampled positions from `-length/2` to `+length/2` along the declared direction, including endpoints. Zero length is identity for normal full-strength mixing. |
| `radial` | Item-local `center`, degree `angle` within Â±180, `zoom` within Â±1 (default 0), odd `samples` 3..129. For equally spaced `t` from -1/2 to +1/2, rotate the vector from center to output position by `angle*t`, multiply it by `1+zoom*t`, translate back and bilinearly sample. Average those samples. Angle and zoom zero give identity. This supports symmetric spin, zoom and their combination; sampling count controls discretization. |
| `surface` | Integer `radius` 0..16, `threshold` 0..1. Average samples in the square window whose maximum absolute difference from the center's straight R, G, B and alpha is at most threshold. Transparent samples have canonical zero straight RGB. The center always qualifies. Threshold zero preserves exact regions; threshold one becomes a box filter. The hard range gate is intentional and deterministic. |

Gaussian mathematics and premultiplied filtering are described in the public [Filter Effects specification](https://www.w3.org/TR/filter-effects-1/#feGaussianBlurElement). Inkbolt uses its own bounded discrete convolution and viewport contract; no SVG filter interchange compatibility is implied.

All neighborhood samples use one explicit border rule. Transparent supplies premultiplied zero; clamp repeats the nearest edge; wrap repeats the grid; reflect repeats the sequence `a,b,c,c,b,a` for a three-pixel row. Bilinear sampling extends each integer neighbor using this rule. Normalized filters preserve a constant field with clamp, wrap or reflect. A transparent border attenuates alpha near viewport edges. Gaussian truncation changes the continuous infinite kernel; the discrete kernel is normalized exactly in the mathematical definition and up to f64 roundoff in execution.

## Masks and mixing

Each filter supports the shared [grayscale mask](MASKS.md) controls, including linked/unlinked placement, density, inversion, feathering, sampling, clipping and disabling. The mask selects where the *filtered result replaces the input*; it does not prevent source samples outside that mask from contributing to the neighborhood. A disabled filter is skipped. A disabled mask supplies full coverage. Shared item masks apply later to the entire final object.

Let the input and filtered premultiplied pixels be `(P,A)` and `(Q,B)`, and let `t = filter_opacity * mask_coverage`. Normal mixing returns `(1-t)*P+t*Q` and alpha `(1-t)*A+t*B`. Thus a blur may spread alpha, and opacity zero restores the original pixel. This is replacement interpolation, not another source-over copy of the object.

For a non-normal color mode, obtain straight input `C=P/A` and effect `D=Q/B`, with zero color for zero alpha. Compute the declared RGB blend `M(C,D)`, then `E=(1-A)*D+A*M(C,D)`. Replace Q in the preceding formula with `B*E`; alpha follows the same interpolation. The shared blend equations operate on complete RGB triples, including the hue/saturation/color/luminosity families. Channels clamp into the premultiplied output gamut after mixing. No intermediate RGBA8 conversion occurs.

Comparisons at thresholds and kernel arithmetic use f64. Final bytes round to nearest with upward half-byte ties. Independent rational fixtures allow either adjacent byte only at a mathematically exact half-byte tie, where decimal-to-f64 rounding can move the result across that boundary; they do not allow a blanket one-byte error. Gaussian fixtures use a separate 45-digit Decimal reference.

## Limits and explicit failures

- At most 8 filters per item and 64 per document, including disabled/hidden entries. Filter IDs must be unique within each item.
- Render filter work is capped at 67,108,864 declared sample units. Surface neighborhoods and bilinear path samples receive additional cost. Artboard ranges aggregate work before rendering. Filter presence reserves two additional full-frame floating-point buffers under the existing buffer cap. Mask storage, preparation and feather work also count toward their shared limits, including disabled entries.
- Filters require drawable content or an isolated group/frame. Backdrop adjustment items and pass-through groups reject filters. Use an isolated container to filter multiple children.
- Ungrouping a filtered container is rejected because it would change appearance. Native pixel mask application on an item with filters is rejected because baking the later item mask into its earlier source would change effect order.
- PNG exports render effects. Snapshots preserve their editability. SVG export rejects filter stacks, including disabled stacks, instead of dropping their settings. General effect expansion, profile conversion, high-depth filtering and broader effect families remain separate required work.

`examples/filter_workflow.py` demonstrates original assets, stack revision, private output publication and byte-identical undo recovery. Independent tests cover full two-dimensional rational convolution, high-precision Gaussian kernels, directional/radial coordinate charts, surface thresholds, alpha fringes, masks, stacks, groups, scale, artboard bleed, limits and persistent MCP sessions.

Detail and spatial operators extend this same stack through the `detail` and `spatial` operator wrappers. See [detail and spatial controls](DETAIL_AND_SPATIAL.md) for sharpening, unsharp thresholds, median cleanup, seeded noise, offsets, editable displacement maps and mosaic blocks. Their depth, alpha, border and scaling behavior is explicit.
