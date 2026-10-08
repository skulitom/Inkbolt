# Native print image warps

Native print preparation accepts retained perspective, mesh and articulated
deformations on inline RGBA8 layers, placed/cropped image assets and normalized
RGB or grayscale sample grids at u8, u16 or f32 depth. Retained raw layers also support these maps after their explicit encoded development recipe; see [NATIVE_RAW.md](NATIVE_RAW.md). The original source and
editable controls remain unchanged. Map geometry, joint weights, inverse
conditioning and nearest/bilinear sampling follow [PIXEL_WARPS.md](PIXEL_WARPS.md).

Each output centre is mapped through inverse item/ancestor placement, then the
inverse local deformation. The original source crop is reconstructed with
associated alpha at its retained precision. Straight reconstructed RGB is
converted directly from its retained source profile to the requested process
profile, then composed into native process and named ink planes. Separating
source pixels before interpolation would give different results and is not this
contract. There is no intermediate display conversion or byte projection.

The deformed outer boundary is rasterized once. Internal mesh edges do not
create separate alpha surfaces. Covered boundary pixels whose centres fall
outside the shape sample the nearest destination boundary point through the
inverse map. The source alpha multiplied by geometry coverage supplies both
intrinsic alpha and the independent footprint used by knockout groups. Scalar
and artwork masks, clipping stacks, native filters, effects, fill/overall
opacity, dissolve and group blending retain their existing order. Supersampling
averages completed native ink contributions.

`image_sources[].pixel_warp` records the normalized retained controls and shared
evaluation rules. The same receipt accompanies native PDF pages; capability
discovery exposes those rules in `native_prepress.pixel_warps`. Exact plane
bytes, supplied output profiles, source receipts and create-only publication
remain shared with [VECTOR_PLATES.md](VECTOR_PLATES.md).

The existing inverse work limit of 67,108,864 units remains in force and is also
charged to the aggregate native print work budget. The maximum simultaneously
live map/path/construction storage is charged before image surface allocation.
This conservative allowance, in eight-byte value slots, is
`32*(columns+1)*(rows+1) + 16*columns*rows + 16*joints + 128`.
Perspective uses one cell; its fixed coefficients are included. Map plans are
consumed one image at a time. Existing source, coordinate, control, profile,
mask, output and cancellation limits remain in force. Advanced reconstruction
on warped items fails explicitly; select nearest or bilinear.

Original tests in `tests/test_native_warps_cli.py` use independent rational
homography solves, barycentric inverses, joint poses and unquantized associated
reconstruction. They cover source profiles/depths, crop, reflection, boundary
sampling, mesh seams, transforms, supersampling, all 21 filters, all 26 blends,
preserving effects, masks/clipping, selected pages/bleed, exact PDF planes and
durable agent edits/undo/retry. Retained object sources and adjustment layers remain
required before completing the extended native print checkpoint. This work
adds no checkpoint credit.

Retained objects also use the shared inverse placement and outer coverage, but
reconstruct an already composed native ink/alpha surface. No second source colour
conversion occurs at placement; see [NATIVE_OBJECTS.md](NATIVE_OBJECTS.md).
