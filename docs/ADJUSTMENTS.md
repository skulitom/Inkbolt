# Tone adjustment layers and pixel measurements

Raster documents accept editable tone layers. A layer modifies colors while retaining the underlying pixels, asset identities, alpha and source files. Normal document edits, snapshots, session undo/redo, conflict checks, diffs and create-only PNG publication apply. Vector documents reject adjustment content; broader effects, profile-managed color, filter stacks and high-depth storage remain separate requirements.

## Layer model and clipping

```json
{
  "id": "tone",
  "name": "Exposure and contrast",
  "content": {
    "type": "adjustment",
    "adjustment": {
      "clip_to": "picture",
      "operators": [
        {"type": "exposure", "stops": 0.5},
        {"type": "curve", "points": [[0,0],[0.25,0.2],[0.75,0.85],[1,1]]}
      ]
    }
  }
}
```

Omitted/null `clip_to` adjusts the accumulated backdrop below the layer in its current container. In an isolated group this means that group's composite; a pass-through group shares its surrounding backdrop. An adjustment creates no coverage over transparent pixels and never changes alpha.

A non-null `clip_to` binds to a stable sibling ID. The base must be the immediately preceding drawable item or isolated container, allowing a contiguous chain of adjustments bound to that same base between them. It cannot be an adjustment or pass-through group. The chain transforms the base's straight colors before its opacity, mask, geometric clip and blend into the backdrop. Alpha is retained, so a clipped adjustment affects only the base's coverage, including semitransparent edges. It cannot recolor unrelated backdrop pixels.

Deleting, moving or regrouping a referenced base fails if it would break this relationship. There is no implicit retargeting. Remove or explicitly revise its adjustments first, or move the complete base/chain together. Subtree duplication remaps internal base IDs. Independent adjustment order remains editable with ordinary sibling reordering. Clipped adjustments inside an isolated group can survive ungrouping when appearance is preserved; a backdrop adjustment is an isolation dependency and prevents appearance-losing ungrouping.

Adjustment items support inherited visibility, locks, opacity, all 26 shared color blend modes (see BLENDING.md), geometric clips, grayscale masks and linked/unlinked mask transforms. Their transform places their clip and linked mask; an unrestricted adjustment has no intrinsic geometry bounds. Mask density/feather/inversion and selection-to-mask creation work as for other items. Active pixel selections do not silently limit a tone operation: explicitly copy the selection into its mask when desired.

For original straight RGB `c`, the complete ordered operator result is `a`. The adjustment's blend mode calculates `b=a`, `b=c*a`, or `b=c+a-c*a`. Final color is `c+w*(b-c)`, where `w` multiplies item opacity, geometric clip coverage and grayscale-mask coverage. Source alpha remains unchanged. Layer transforms affect spatial coverage, not tone values. Every operator acts on the preceding result in f64; quantization occurs only at final RGBA8 output.

Use `op:"adjustment",id,adjustment` to replace the complete parameters of an existing adjustment layer. Use `add` for a new layer. All edits remain atomic; source pixels are retained in prior and current snapshots. `document.inspect`, `document.select` and `document.query` report adjustment parameters; queries accept content type `adjustment`.

## Operator definitions

Channels below are normalized to `[0,1]`. Unless specified otherwise, operations use straight **encoded sRGB**. After each operator, channels clamp to `[0,1]`; alpha never enters a tone formula. These are explicit Inkbolt equations, not a promise to match an external application's controls.

| Type | Parameters and equation |
| --- | --- |
| `invert` | `y=1-x` per RGB channel |
| `threshold` | `level` in `[0,1]`; RGB becomes white when `0.2126*r+0.7152*g+0.0722*b >= level`, black otherwise. This encoded-channel control is not a linear-light luminance measurement. |
| `levels` | `input:[black,white]`, `output:[black,white]`, `gamma`; `t=clamp((x-input[0])/(input[1]-input[0]))`, `y=output[0]+(output[1]-output[0])*t^(1/gamma)`. Input endpoints increase strictly; reversed output endpoints deliberately invert the mapping. |
| `posterize` | Integer `levels` from 2 through 256; `y=round(x*(levels-1))/(levels-1)` |
| `curve` | `points:[[x,y],...]`, optional `channel` (`rgb`, `red`, `green`, `blue`). Piecewise linear interpolation between points; untouched channels retain their values. Both endpoints are required at x=0 and x=1, x increases strictly, y may rise or fall. |
| `exposure` | `stops` in `[-16,16]`, optional `offset=0` in `[-1,1]`, optional `gamma=1`; decode sRGB to linear light, compute `clamp(linear*2^stops+offset)^(1/gamma)`, then encode to sRGB. Gamma acts in linear space before encoding. This bounded operator does not recover clipped HDR samples. |
| `brightness_contrast` | `brightness` and `contrast` in `[-1,1]`; first `v=clamp((x-0.5)*2^(4*contrast)+0.5)`, then shift v toward white for positive brightness or toward black for negative brightness. |
| `shadows_highlights` | `shadows,highlights` in `[-1,1]`; for encoded-channel weighted sum `Y=0.2126*r+0.7152*g+0.0722*b`, use `a=shadows*(1-Y)^2-highlights*Y^2`, then shift each original channel by a. Positive shadows brighten dark tones; positive highlights darken bright tones. This is a deterministic pointwise tonal operator, with no spatial neighborhood or hidden local-contrast radius. |

Shift means `x+(1-x)*a` when a is nonnegative and `x*(1+a)` otherwise. Levels endpoints and curve coordinates lie in `[0,1]`. Gamma lies in `[0.1,10]`. The sRGB transfer function uses the public [sRGB definition](https://www.w3.org/TR/css-color-4/#predefined-sRGB); profile assignment/conversion is separate unimplemented work.

Each layer has 1 through 16 operators; a document has at most 256; curves have 2 through 64 points. Each tone curve contributes eight evaluation units per output pixel, other tone operators four. Color operator costs are documented separately. These join the existing bounded paint/render work and artboard-range preflight. Invalid parameters, broken clipping references, excessive work and unsupported content fail explicitly, including hidden content validation.

Decimal JSON parameters are stored as f64, not exact rationals. Rounding uses nearest RGBA8 output after floating-point evaluation. Independent rational fixtures require exact bytes away from a mathematical half-byte boundary; at an exact tie, f64 approximation can select either adjacent byte. Tests permit only that tie ambiguity. High-precision exposure/gamma fixtures match their independent reference bytes. This does not introduce a general one-byte allowance for arbitrary errors. Fully transparent rendered output uses canonical zero RGB; stored source RGB remains intact.

## Reproducible measurements

`document.measure` accepts `document`, optional `options`, `asset_root` and `font_root`. It measures the **same scale-one, straight RGBA8 composite that PNG exports**, including transforms, masks and adjustments. The result is structured JSON suitable for saving as an independent numerical artifact. It does not mutate or resample a source document to a different size.

Options:

- `region:{x,y,width,height}`: integer canvas pixel rectangle, default full canvas. It must be nonempty and wholly inside the canvas.
- `use_selection`: false by default; true requires an active selection and uses its grayscale coverage as a weight.
- `alpha`: `ignore` (default), `exclude_transparent`, or `weight`.
- `samples:[[x,y],...]`: up to 256 pixel coordinates within the selected region. Samples return actual output RGBA, selection coverage and effective weight, even when that weight is zero.

For each pixel, selection weight S is 255 or its selection byte. Alpha weight A is 255 for ignore, 0/255 for exclude-transparent, or the alpha byte for weight. The exact integer weight is `S*A`, with denominator **65025**. All four histograms use that same weight, including the alpha histogram. Thus alpha-weighted measurements answer a different question from ignoring alpha; nothing silently drops transparent pixels. Zero-alpha RGB in this rendered source is zero, even if the original stored pixel retains nonzero RGB.

Each channel has 256 histogram bins, exact weighted sums and sums of squares, minimum/maximum of positive-weight pixels, weighted mean and population variance. The result also reports examined pixels, positive-weight pixel count, total integer weight, effective pixel count, source revision and depth. Empty weighted regions have zero histograms/sums and null min/max/mean/variance. Integer totals remain exactly representable within the current pixel limit; mean and variance are f64, with a tiny negative variance from cancellation clamped to zero.

Measurements currently declare **depth 8**. They do not imply high-depth storage, raw development or profile conversion, and reject unknown depth fields instead of silently converting. Resource resolution and rendering failures retain ordinary engine diagnostics. See [the original image-edit example](../examples/adjustment_workflow.py) for masked adjustments, before/after measurements, immutable source import and durable undo.

`type:"color",adjustment:{...}` adds editable hue/saturation, desaturation, channel mixing, balance, selective correction, 1D/3D lookups and gradient maps to the same stack. See [COLOR_ADJUSTMENTS.md](COLOR_ADJUSTMENTS.md) for exact equations, table order, clipping and resource bounds.
