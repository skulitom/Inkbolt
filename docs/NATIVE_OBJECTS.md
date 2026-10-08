# Retained objects in native print preparation

Native print preparation evaluates retained editable objects as isolated native
CMYK and spot-ink surfaces over transparency. It preserves exact source snapshot
bytes, source resources and explicit link state. Rendering never refreshes a
linked file implicitly. The parent is still a raster document under the existing
[retained object contract](OBJECTS.md); the source may be vector or raster.

Source paints convert before native ink composition. Native operands, overprint,
groups, masks, clipping, filters, effects, normalized images and encoded raw
recipes use the same native evaluator inside the source. Its declared
`surface_scale` and the selected print antialias policy determine the retained
surface resolution. Associated ink amounts and alpha are averaged without an
intermediate byte or display-colour projection. Unpainted source regions stay
transparent; an explicit white paint or background is opaque.

Placement reconstructs the completed native surface using nearest, bilinear,
area, bicubic or Lanczos3. The associated ink/alpha tuple is projected into the
normalized zero-to-alpha range after the complete two-dimensional kernel. The
existing crop-edge clamp and conservative inverse-pixel footprint apply.
Perspective, mesh and articulated maps share the existing nearest/bilinear
restriction and one outer geometry coverage pass. Parent transforms, controls,
masks, clipping, effects and blends apply after placement. The source boundary is
isolated: it replaces every parent ink at its reconstructed alpha, including
inks absent from the source. It does not act as pass-through parent artwork.

Root spot IDs remain unchanged. Each object source's printed spot receives a
slash-prefixed placement path, such as `/placed/ink` or `/placed/inner/ink`.
Source IDs cannot contain slash, so these paths cannot collide with root IDs or
other placements. Equal labels or local IDs in different objects stay distinct.
Unrelated source edits do not rename plates. Receipts retain source IDs, names
and their placement mapping; PDF colourant names escape the path separators
while retaining the same decoded identity. Explicit cross-source plate binding is available through
[INK_BINDINGS.md](INK_BINDINGS.md); there is no implicit merging by name or
alternate colour.

Preparation builds the complete visible source tree before rendering it.
The existing four-level and 32-source bounds apply. The conservative per-node
native work and buffer allowances are summed across the tree, including source
raw development, profiles, masks, filters and retained surfaces. Placement charges
33 possible sampled components per reconstruction tap plus its fixed allowance.
The whole tree shares the limits of 28 printed spots and 16 distinct visible
source profiles. The active deadline and cancellation control reach each source
plan and evaluation. All publication remains create-only.

`image_sources` entries of type `object` report the exact snapshot hash and byte
count, native dimensions, surface scale, reconstruction, source link without a
file read, spot mapping and nested image/coverage receipts. The same receipts
appear in native PDF pages. Capabilities expose the contract through
`native_prepress.object_sources`.

Explicit HDR views and retained nonprinting metadata follow [NATIVE_CONTEXTS.md](NATIVE_CONTEXTS.md). Native adjustment layers require the declared policy in [NATIVE_ADJUSTMENTS.md](NATIVE_ADJUSTMENTS.md). Root delivery restrictions remain explicit. Registry status governs checkpoint credit; all 167 acceptance criteria remain unchanged.

`tests/test_native_objects_cli.py` checks independent rational ink/alpha fields,
all five reconstruction methods, surface scales, retained warps, transparent and
white regions, nested spot collisions, native blend/filter integration, parent
controls, profiles/raw sources, pages, external resources, bounds, exact PDF
bytes, source retention and durable agent edits/undo/retry.
