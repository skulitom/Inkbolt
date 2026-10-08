# Explicit RGB color profiles

For explicit CMYK page output, use [PRINT_CMYK.md](PRINT_CMYK.md). Its supplied four-channel printing profile is separate from document RGB output association.

Inkbolt defaults to encoded sRGB and also supports an explicit linear working space. At image boundaries, agents can convert profiled RGB input into encoded working values and associate an output profile with a document. This association changes delivery settings; it does not reinterpret or rewrite existing artwork values. Retained source-profile assignment/conversion, all four intents and native 8/16/float inputs are described in [SAMPLE_PROFILES.md](SAMPLE_PROFILES.md), including the version 0.73 builtin white-point correction. Document working-space changes, CMYK/Lab/grayscale device paints, proofing and supplied gamut diagnostics have explicit separate contracts in [DEVICE_COLOR.md](DEVICE_COLOR.md) and [PRINT_PROOF.md](PRINT_PROOF.md).

## Profile values and limits

A profile is either `{"type":"builtin","name":"srgb"}`, `{"type":"builtin","name":"linear_srgb"}`, `{"type":"builtin","name":"display_p3"}`, or `{"type":"icc","data":"<base64 ICC bytes>"}`. Supplied bytes are retained exactly. Builtins have fixed definitions, aligned ICC tag framing, an unset ICC profile ID and a fixed 2000-01-01 creation date, so wall-clock time cannot change their identity. Receipts use SHA-256 of the actual embedded profile. The working-space conversion uses the same quantized ICC definition as the sRGB builtin.

Profiles are limited to 256 KiB and 128 tags, with bounded tag tables, offset/overlap checks, parser allocations, lookup tables and transfer curves. RGB ICC v2/v4 input, display and output classes with XYZ or Lab connection space are accepted when the requested conversion is supported. The external color engine supplies matrix/TRC and lookup conversion; Inkbolt validates framing, direction and bounds. RGB profiles with Lab connection space do not imply a Lab working document or Lab sample import. Unsupported connections and non-RGB samples fail explicitly.

Conversion uses relative colorimetric intent with black-point compensation disabled and CICP overrides disabled. The scalar floating-point API evaluates through the dependency's finite-resolution tables, then Inkbolt clips finite output to the destination range and rounds once to RGB8. Alpha is copied exactly, including source hidden RGB during import. Out-of-gamut clipping and byte quantization are not reversible. A scoped, joined worker with a reserved 32 MiB stack constructs high-precision tables safely on Windows; conversion uses bounded 4096-pixel RGB buffers. No worker, service or listener remains after the operation.

## Source conversion

`asset.import` accepts `color_policy:"convert_srgb"`. Embedded ICC profiles in RGB PNG, JPEG and TIFF are then interpreted and converted into the working space before immutable pixel identity is computed. PNG iCCP data, ordered or reordered multipart JPEG ICC APP2 segments and TIFF ICC tags are supported. Missing/duplicate JPEG segments, malformed profiles and contradictory PNG declarations fail before storage.

For an untagged image, add `input_profile` using a profile value. An explicit profile cannot override tagged PNG sRGB/gamma/chromaticity semantics. If both embedded and explicit ICC profiles exist, their bytes must agree. `convert_srgb` alone does not assume a color space for an untagged image: choose `assume_srgb` or declare its profile. Existing `require_srgb` and `assume_srgb` policies continue to reject ICC inputs. Grayscale profile conversion, HDR declarations, EXIF orientation and other unsupported image semantics remain explicit failures.

The asset retains original source SHA-256, source profile SHA-256 and `interpretation:"converted_srgb"`. The import receipt describes destination interpretation, intent, unchanged alpha and quantization/gamut losses in `color_conversion`. Normalized pixel identity is independent of source encoding and metadata; equal converted pixels deduplicate. Input files and occupied store entries are never overwritten.

## Destination association and exports

Use an ordinary atomic edit:

```json
{"op":"output_profile","profile":{"type":"builtin","name":"display_p3"}}
```

Set `profile:null` to clear it. The optional `output_profile` field persists in schema-v2 snapshots, variants' document context, artboard views and durable session history. `document.inspect` reports its byte hash and conversion contract without echoing the binary data. Structural diffs report association changes even when working-space pixels are unchanged. Cross-document artwork transfer retains the destination's profile.

PNG, JPEG and TIFF exports convert rendered working samples and embed the exact destination ICC bytes. Native vector PDF uses the same association as a calibrated page/group blending profile while preserving source components and embedding explicit source profiles; see [PDF.md](PDF.md). PNG uses iCCP without a conflicting sRGB chunk; JPEG emits bounded numbered ICC segments; TIFF emits its profile tag. Artboard ranges, bleed, scale and create-only publication share the same policy. Artifacts and publication receipts include `color_profile` metadata. All original resource, pixel/work and output-size budgets remain applicable.

JPEG's explicit matte is interpreted and composited in working sRGB **before** destination conversion; compression follows. Its normal lossy-quality contract remains. PNG/TIFF compression preserves the converted samples exactly, although color conversion itself can lose information. Clearing the association restores existing PNG sRGB tagging and untagged-sRGB JPEG/TIFF output. SVG with a nonempty output-profile association fails explicitly; clear it to export working-sRGB SVG, or use a profiled image. Snapshots preserve the association without converting content. Numerical previews and comparisons remain in working sRGB.

## Independent evidence

`tests/test_profiles_cli.py` constructs original ICC headers, fixed-point matrix/TRC and RGB lookup data. It checks independent transfer equations, exact metadata bytes/hashes, hidden colors and alpha, PNG/TIFF sample conversions, JPEG multipart framing, color-policy conflicts, strict bounds, malformed inputs, unchanged sources, artboard ranges and bleed, publication, snapshots, transfer, diffs and MCP undo/redo. Builtin timestamps and sRGB identity are explicit regressions.

Private verification compares an original 17-level RGB cube against LittleCMS 2.16 through external Pillow 10.3.0, using the exact declared working/destination profiles. Conversion tolerances are at most three byte levels for these fixtures. JPEG decoding is checked separately within three levels before conversion because nonlinear transfer curves can amplify tiny decoder differences in dark samples. Explicit-matte JPEG output at quality 100/full chroma uses a separate eight-level bound including compression. These are measured fixture acceptance limits, not universal guarantees for arbitrary profiles. Original [profile delivery examples](../examples/profile_workflow.py) preserve editable sources and exact profile bytes. The external verification tools and generated evidence remain private.
