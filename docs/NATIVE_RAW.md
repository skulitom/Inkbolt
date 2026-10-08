# Retained raw sources in native print preparation

Native print preparation accepts retained calibrated sensor layers whose saved
development recipe explicitly chooses `srgb8` or `srgb16` output and `clip`
range policy. It preserves the exact sensor buffer, padding, calibration,
development settings and versioned recipe. The source remains editable; native
printing does not replace it with developed pixels.

Each visible source is developed once through the original [raw processing
path](RAW_EDITING.md), using the active deadline and cancellation control.
Calibration, demosaicing, white balance/exposure and camera conversion precede
ordered noise reduction, lens reconstruction and detail enhancement. The saved
output policy clips, encodes and quantizes the developed source at its declared
depth. Lens alpha is retained at that depth. Native source reconstruction then
operates on these samples before continuous process-profile conversion and ink
composition. No additional eight-bit preview is inserted.

Nearest, bilinear, area, bicubic and Lanczos3 reconstruction retain the existing
sampling contracts. Retained perspective, mesh and articulated warps require
nearest or bilinear. Native filters, all blend modes, masks, clipping stacks,
effects, backgrounds, groups and page selection use the same developed alpha
and source colours. Recipe resolution does not change the parent document's
physical resolution. See [NATIVE_PIXEL_WARPS.md](NATIVE_PIXEL_WARPS.md) and
[VECTOR_PLATES.md](VECTOR_PLATES.md).

Image and PDF receipts include the sensor `source_sha256` and byte count,
the complete recipe, its `recipe_sha256`, and the developed sample hash and
depth. Recipe hashing uses the same pretty JSON plus final newline as
`raw.recipe`. Capabilities disclose the development and sampling order in
`native_prepress.raw_sources`. Different settings on the same sensor buffer
retain one source identity and distinct recipe/developed identities.

Development work is charged before evaluation: 128 units per source pixel,
plus `16*(2*radius+1)^2` for each noise/detail stage with nonzero amount, plus
128 for a lens stage, and one unit per original byte. These costs join the
aggregate native work budget. Retained developed grids reserve four eight-byte
slots per total source pixel. Temporary development storage reserves 32 slots
per largest source pixel plus the largest decoded sensor byte buffer, rounded
to eight-byte slots. Ordinary reconstruction, map, mask and ink buffers remain
separately charged. Existing sensor dimensions, recipe, source-byte and aggregate
stored-pixel limits also apply.

Signed or scene-linear raw output is not implicitly clipped or tone-mapped into
a normalized printing profile. Choose an explicit encoded raw recipe for this
path; the original linear source and its separate delivery options remain
available. Retained objects now use the native source path in [NATIVE_OBJECTS.md](NATIVE_OBJECTS.md). Explicit plate bindings are described in [INK_BINDINGS.md](INK_BINDINGS.md). Explicit HDR views and native adjustment contexts follow [NATIVE_CONTEXTS.md](NATIVE_CONTEXTS.md) and [NATIVE_ADJUSTMENTS.md](NATIVE_ADJUSTMENTS.md). Direct raw printing still requires an encoded recipe; a signed linear source needs an explicit retained HDR view.

`tests/test_native_raw_cli.py` uses independent calibrated stencils, rational
noise/lens/detail references and native-depth reconstruction. It covers all four
Bayer patterns and three byte packings, padding, both encoded depths, source
and recipe identities, all native warp/filter/blend types, transparent borders,
sampling, masks/clipping, page bleed, bounds, exact PDF bytes and durable agent
settings/undo/retry.
