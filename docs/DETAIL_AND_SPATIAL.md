# Detail and spatial filters

These operators use the editable [filter stack](FILTERS.md), with its masks, opacity, blending, border rules, viewport evaluation, preserved sources and undo history. Wrap detail controls as `{"type":"detail","operator":{...}}` and spatial controls as `{"type":"spatial","operator":{...}}`. They work in both document kinds on drawable items and isolated containers. Backdrop adjustment items, pass-through groups, high-depth inputs and SVG filter interchange remain explicitly unsupported.

```json
{
  "op": "filters", "id": "picture",
  "filters": [
    {"id":"clean", "border":"reflect", "operator":{"type":"detail","operator":{"type":"median","radius":1}}},
    {"id":"texture", "opacity":0.4, "operator":{"type":"detail","operator":{"type":"noise","amount":0.08,"seed":314,"distribution":"gaussian"}}},
    {"id":"blocks", "operator":{"type":"spatial","operator":{"type":"mosaic","size":4}}}
  ]
}
```

## Detail controls

All detail operators preserve the input alpha at each output position. They operate on straight encoded-sRGB color, with alpha-aware neighborhood color where specified, and return premultiplied f64 pixels to the stack. Invisible RGB stays canonical zero. Final output remains RGBA8; this does not provide HDR or 16/32-bit editing.

- `sharpen`: `amount` 0..8. Let C be the center's straight color. Average premultiplied RGBA at the four cardinal neighbors one document pixel away, then divide averaged RGB by averaged alpha to obtain R. If the neighborhood has zero alpha, use C for R. The result is `clamp(C + amount*(C-R))`, retaining the center's alpha. At amount 4 on opaque pixels, this is the five-point Laplacian kernel with center 5 and cardinal neighbors -1. The neighborhood distance scales with export resolution. Constant colors remain constant even across varying alpha.
- `unsharp`: `sigma` 0..16, `amount` 0..8 and `threshold` 0..1 (default 0). Obtain R by unpremultiplying the Gaussian reference defined in FILTERS.md, with the same zero-alpha fallback. Each channel independently sharpens only when `abs(C-R) >= threshold`. Threshold is in normalized encoded channel units, not bytes. Sigma zero or amount zero produces identity. The threshold comparison uses f64; the equality branch is intentional.
- `median`: integer `radius` 0..8. Within the square neighborhood, discard zero-alpha samples and choose each straight color channel's upper median independently. Retain the center alpha; a transparent center remains transparent. A nontransparent center guarantees a nonempty sample set. Partial-alpha neighbors each receive one vote. This removes isolated bright/dark defects without claiming edge-sensitive healing. Radius scales with export resolution; radius zero is identity.
- `noise`: `amount` 0..1, required unsigned 32-bit `seed`, `distribution` uniform (default) or gaussian, and `monochrome` true (default). Add `amount * N` to each straight RGB component, clamp to [0,1], and retain alpha. For uniform noise, N has nominal range (-1,1) and variance 1/3; amount is the half-range. For Gaussian noise, N approximates the standard normal distribution on a finite deterministic grid; amount is its standard deviation before clipping. Clipping can alter mean and variance near black/white. Monochrome shares one value across RGB; otherwise the channels have separate hash inputs. Amount zero is identity.

Sharpening overshoot clips to the unit gamut before filter-stack mixing. The engine does not hide this clipping or claim to retain high-depth detail. Median neighborhoods use the selected filter border rule; transparent extension contributes no median votes. Sharpen/unsharp normalize neighborhood color by alpha, so transparent black does not create a color fringe.

## Noise reproducibility

The noise field is addressed by `(seed, floor(output_x/export_scale), floor(output_y/export_scale), channel)`. It is anchored to document pixels, independent of item IDs, traversal order and previous random calls. Moving content through the field changes its texture; standalone artboard exports use their local output grid. Increasing export scale repeats the same noise value within each document pixel.

The version-one byte contract hashes the ASCII bytes `Inkbolt noise v1` plus a NUL, followed by seed, x and y as little-endian u32 values, then channel as one byte (0 for monochrome, otherwise 0/1/2). Interpret digest bytes 0..8 and 8..16 as little-endian u64, shift each right by 12, then compute `u=(integer+0.5)/2^52`. Both uniforms are strictly between zero and one with exactly representable half-grid offsets. Uniform noise is `2*u1-1`. Gaussian noise uses `sqrt(-2*ln(u1))*cos(2*pi*u2)`. This is the classical Box-Muller transform; the finite uniform grid bounds the largest possible absolute normal sample by `sqrt(106*ln(2))`. Hashes and integer addressing are portable; transcendental f64 functions may vary in their last bits across platforms. Final byte results and distribution bounds are tested on the current runtime.

The distribution definitions can be checked against the public [NIST distribution reference](https://itl.nist.gov/div898/handbook/eda/section3/eda366.htm). The noise implementation is original coordinate hashing over the existing locked SHA-256 dependency, with no runtime seed generation, file dependency or network access.

## Spatial controls

- `offset`: finite `offset:[x,y]`, each component in -256..256 document pixels. Output position (x,y) samples the source at `(x-offset_x, y-offset_y)` using premultiplied bilinear interpolation and the selected border rule. Positive offsets move content toward positive coordinates. `[0,0]` is identity.
- `displace`: an editable `map` plus finite `amount:[x,y]`, each in -256..256 document pixels. The map stores `width`, `height`, row-major `vectors` in [-1,1]Â², an optional item-local affine `transform` and `sampling` (nearest by default, or bilinear). At each output pixel center, invert the item-world/map transform to read the vector field. The source is sampled at `(x+amount_x*vector_x, y+amount_y*vector_y)`. Positive displacement is a *pull* toward the positive source coordinate. Zero vectors or zero amount produce identity.
- `mosaic`: integer `size` 1..128 document pixels. Partition the viewport into square blocks from its top-left origin. Average premultiplied RGBA over each block and replace all its pixels with that mean. Partial blocks at right/bottom use only existing viewport samples. The algorithm visits each pixel twice, independent of block size. Size 1 is explicit identity at all export scales; larger blocks scale with export resolution. The border setting is retained but unused because blocks do not sample outside the viewport.

Displacement maps clamp to their nearest edge outside the field. Map nearest sampling selects local pixel cells; bilinear sampling interpolates around pixel centers. Map sampling and the filter's source-image border rule are separate controls. Map transforms follow item hierarchy; displacement vector components and offsets remain aligned to document axes. Standalone artboard export shifts a map owned by the artboard for bleed, matching its other local controls. Spatial source interpolation includes alpha, so moving transparent pixels does not inject their hidden color.

The general pull-mapping convention is described in the public [displacement filter specification](https://www.w3.org/TR/filter-effects-1/#feDisplacementMapElement). Inkbolt's signed two-component fields are its own representation, not an imported channel map or a native-format compatibility claim.

Each map contains exactly width*height vectors, at most 4096, with dimensions in 1..256. Map samples count toward the document's 65536 aggregate inline sample budget, including disabled filters. Serialized document limits also apply. Maps reject singular transforms, nonfinite coordinates and out-of-range controls. Median neighborhoods, Gaussian references, hashing, map sampling and block averaging contribute to the existing filter-work and artboard budgets; Gaussian detail reuses its completed buffer and preserves the existing two-extra-buffer bound.

`examples/detail_workflow.py` combines median cleanup and seeded texture, then appends displacement and mosaic controls over an original pinned chart. It saves separately named outputs and snapshots, compares revisions, and undoes both stages without modifying the source. Tests use exact rational neighborhoods/order statistics, 45-digit Gaussian references, independent SHA-256 noise evaluation, fixed-seed distribution checks, original coordinate maps and session recovery. Additional representative creative families are implemented in [CREATIVE_FILTERS.md](CREATIVE_FILTERS.md), with explicit family coverage, limits and independent verification.
