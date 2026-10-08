# Explicit image reconstruction

Pixel layers and placed images accept `sampling:"nearest"`, `"bilinear"`, `"area"`, `"bicubic"` or `"lanczos3"`. The same choices apply to a raster `canvas` scale action and its canvas-sized selection/channel grids. Native snapshots, atomic edits and durable undo retain the choice. Source pixels and imported files remain unchanged. See [canvas operations](CANVAS.md) for anchors, resolution-only edits and retained crop bounds.

## Coordinates and kernels

Output pixel centers map through the inverse item/world transform into source pixels, whose centers are half-integers. A placed image's crop and frame dimensions also participate. Export scale is included each time; rendering an already reduced editable scene at a larger export scale reads its original source again.

The area footprint is the source-axis bounding rectangle of the inverse-mapped output pixel. Its widths are the sums of absolute components of each inverse Jacobian row. Axis-aligned and right-angle transforms give exact rectangular pixel footprints. Shear or arbitrary rotation uses a conservative separable rectangle enclosing the parallelogram; this can blur more than an oriented filter. No elliptical reconstruction is implied.

Each output sample uses separable, normalized weights. Source indices clamp to the selected crop's edge. Normalization includes the entire kernel before repeated edge indices are clamped, preserving constant fields. Every new kernel works in encoded-sRGB premultiplied f64 RGBA; there is no intermediate RGBA8 conversion.

| Method | Mathematical definition | Reduction |
| --- | --- | --- |
| `area` | Exact overlap length between the source footprint interval and each unit pixel cell on each axis | Uses the actual footprint at both reduction and enlargement |
| `bicubic` | Symmetric cubic convolution with parameter `a=-0.5`, support radius 2; equivalently cardinal cubic Hermite interpolation at unit scale | Each axis expands by `max(1,footprint_width)` before normalization |
| `lanczos3` | `sinc(x)*sinc(x/3)` for `abs(x)<3`, zero outside; `sinc(x)=sin(pi*x)/(pi*x)` and `sinc(0)=1` | Each axis expands by `max(1,footprint_width)` before normalization |

Nearest and bilinear keep their earlier point-reconstruction contracts; they do not gain an implicit reduction filter. Use an explicit area, bicubic or Lanczos3 choice for reduction filtering. This avoids changing existing snapshots' appearance.

Cubic and sinc kernels have negative lobes. After the complete two-dimensional weighted sum, clamp alpha to `[0,1]` and each premultiplied color component to `[0,alpha]`, then unpremultiply. This explicit projection bounds ringing and prevents invalid alpha or transparent-color fringes. It is not equivalent to clamping between horizontal and vertical passes. Scalar selection/channel results clamp to `[0,255]` only after both axes, then round once. Their bounded grids are actually resampled; layer source pixels remain immutable.

Final RGBA8 rounding retains the existing f64 convention. Independent exact-rational area/Hermite tests and 60-digit sinc calculations permit either adjacent byte at a half-byte boundary within `1e-8` channel units; other comparisons must agree. This tolerance describes the verification of quantization decisions, not an allowance for arbitrary one-byte errors. Geometry-edge coverage still uses the existing f32 backend and has its separate precision contract.

## Bounds and contexts

Each axis admits at most 65536 candidate taps. A conservative per-output work estimate is `nx*ny + 4*(nx+ny)`, including kernel setup. The sum across all advanced-sampled image/pixel items and the complete viewport must not exceed 67108864. Hidden items participate. Artboard ranges also add each independent view's reconstruction estimate to the existing aggregate export budget before rendering any artifact. Resized auxiliary planes share the same work bound and existing storage bounds. Overflow saturates into a limit error; excessive footprints never fall back to a cheaper sampler.

Coordinates outside the stable kernel-index range or intervals that lose representable precision fail explicitly. The source crop remains the reconstruction border; content outside it never bleeds into the output. Item/frame clips and masks still apply through their ordinary coverage contracts.

Scalar opacity masks and displacement fields currently accept only nearest and bilinear. Selecting a new kernel for either fails with `UNSUPPORTED`. A native mask application retains a pixel/image item's selected reconstruction method. SVG image export cannot encode these exact kernels and therefore fails explicitly; use PNG for appearance and snapshots for editing. Asset import formats, working depth and profile conversion are unchanged.

The mathematical references are [Keys' cubic-convolution paper](https://ncorr.com/download/publications/keysbicubic.pdf) and the public discussion of [reconstruction filters](https://www.pbr-book.org/4ed/Sampling_and_Reconstruction/Image_Reconstruction). The implementation, bounds, footprint policy, fixtures and verification are original; no external implementation is bundled.
