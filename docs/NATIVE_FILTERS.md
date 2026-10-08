# Native ink spatial filters

Native print preparation supports all 21 existing filter operators: the seven spatial operators described here plus surface, detail and creative treatments in [NATIVE_NONLINEAR_FILTERS.md](NATIVE_NONLINEAR_FILTERS.md). Disabled and zero-opacity entries retain their validated settings without evaluation. Retained raw/objects, adjustment layers and pixel warps remain required. The checkpoint count is unchanged.

## Spatial contract

The original positive kernels, pull coordinates, displacement fields, four border rules and limits in [FILTERS.md](FILTERS.md) and [DETAIL_AND_SPATIAL.md](DETAIL_AND_SPATIAL.md) apply directly to native process and named-ink fields. The shared evaluator traverses arbitrary channel counts, including all 28 named inks. It never converts native inks to display RGB. Retained source RGB profiles are converted to native ink amounts before filtering. No intermediate byte projection is performed.

At a pixel the native operation is `C + (1-W)*backdrop`, with ink contribution C, removed backdrop fraction W and common intrinsic alpha A. The same positive operator T transports C, W and A separately. Independent knockout shape uses the same T. This preserves unaddressed inks without moving or blurring the actual surrounding backdrop. Storing W directly retains very faint source coverage that later effects can amplify.

A filter's mask and opacity select its replacement at output pixel centers; they do not attenuate neighborhood input. Let q be mask times filter opacity, and Q, V, B the filtered contribution, removal and alpha. Normal replacement computes `(C,W,A)'=(1-q)*(C,W,A)+q*(Q,V,B)`. It is replacement, not a second source-over layer. Positive kernels retain normalized affine paint invariants; final numerical rounding is bounded to `0 <= C <= W <= A <= 1`.

## Filter blend and ordering

All 26 native blend modes use the device-CMYK and named-ink rules in [VECTOR_PLATES.md](VECTOR_PLATES.md). For a non-Normal filter blend, its backdrop is the original intrinsic content on transparency. Let b=C/A when A is nonzero, else zero. Resolve the filtered implicit group as `s=(Q+(B-V)*b*A)/B` when B is nonzero. Compute `R=B*((1-A)*s+A*mix(b,s))`. The replacement closes its inks, with removal B, and then interpolates `(C,W,A)'=(1-q)*(C,W,A)+q*(R,B,B)`. A zero-alpha replacement is empty. Thus non-Normal replacement can address inks that Normal overprint preserves; it does not read the enclosing artwork backdrop. These are explicit project device-ink semantics, not an equivalence claim for display-RGB filtering or physical press simulation.

The pipeline is drawable content, isolated-container closure, ordered filters, raster clipping members, layer decoration, item masks/clips/opacity/dissolve, and item blend/composition. Each clipped member filters before its own controls and before alpha-preserving clipping. Opaque backgrounds complete their filtered/decorated source before matte and clipping members. Pass-through containers continue to reject filters. Shape is transported independently of child/item opacity; replacement never changes it through color blending and numerical containment keeps it at least actual alpha.

Viewport dimensions include the selected artboard and requested bleed. Radial centers and displacement-map placements follow their item-local transforms; offset and vector amounts use document axes. Kernel radius, offsets, block size and sample density follow export scale. Supersampling averages the completed premultiplied ink planes.

## Bounds and evidence

Native preparation counts transport work for contribution, removed fraction, alpha and optional shape, plus replacement/blending and filter-mask preparation. All work and temporary buffers are included in the existing native channel-aware bounds before allocation. Traversal checks cancellation between rows, mosaic rows and replacement batches. Filter publication remains create-only and preserves source documents, image bytes, profiles and session history.

Capabilities expose `native_prepress.filters`; prepared planes and PDF page coverage receipts repeat the same contract. Original independent tests use full 2D rational/Decimal convolution, analytic right-angle pull maps, scalar coverage enumeration and conditional native blends. They cover all borders, singleton dimensions, all seven operators, all 26 replacement modes, all overprint policies, maximum named channels, masks, effects, clipping, knockout, faint coverage, profiled float sources, export scale, supersampling, artboard bleed, exact PDF transport, resource rejection and durable agent history. The nonlinear families are described in NATIVE_NONLINEAR_FILTERS.md; other native contexts retain their full implementation scope.
