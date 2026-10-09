# Retained pixel sample depths

This page describes the normalized encoded-sRGB path. Explicit signed scene-linear HDR grids, working space, reversible grading and display conversion are described in [HDR.md](HDR.md).

Agents can author RGB or neutral grayscale samples at explicit 8-bit, 16-bit or normalized binary32 depth. Raster documents accept `content.type:"samples"` with a `grid` containing `width`, `height`, `depth`, `channels`, `data_hex` and optional `sampling`. Discovery is under `capabilities.sample_precision`; item queries use type `samples` and report dimensions, depth, channels, sampling and a hash of the retained bytes.

| Field | Contract |
| --- | --- |
| `depth` | `u8`, `u16` or `f32`; required |
| `channels` | `rgba` or `gray_alpha`; required |
| `data_hex` | Row-major straight channel samples, little endian, with the exact declared length |
| Integer range | Unsigned 0..255 or 0..65535, normalized by the corresponding maximum |
| Float range | Default encoded sRGB requires finite IEEE binary32 in 0..1. Explicit `encoding:"linear_srgb"` supports finite signed binary32 color in a linear raster document; alpha stays in 0..1 |
| Color interpretation | Encoded sRGB; grayscale expands to equal encoded RGB components, with independent alpha |
| `sampling` | `nearest` by default; `bilinear`, `area`, `bicubic` and `lanczos3` use shared premultiplied reconstruction |

The original byte string remains editable and survives snapshots, transfer, durable sessions and undo/redo. Zero-alpha source color remains in that string. Rendering expands samples into the existing f64 compositor, including masks, filters, adjustments, layer opacity and transforms. It does not first create an 8-bit intermediate. Geometry coverage still uses the existing f32 backend and its coverage precision; masks and placed byte assets retain their declared depths. The default path is normalized encoded sRGB. Explicit linear HDR has a separate declared working-space contract; wider primaries remain unsupported.

`sample_replace` replaces a nonempty, in-bounds native rectangle with bytes of the grid's existing depth and channel layout:

```json
{"op":"sample_replace","id":"pixels","region":{"x":0,"y":0,"width":1,"height":1},"data_hex":"3930307531d4ffff"}
```

This example supplies four little-endian unsigned 16-bit values. Replacement is atomic, checks item and ancestor locks, preserves every byte outside the rectangle and records before/after text hashes. It does not apply the active selection or the item's transform. Retained pixel deformation must be cleared first. Changing sampling or canvas placement preserves native sample bytes. The existing byte brush, retouch and permanent mask application paths reject this content; retained masks and adjustments can still change its rendered appearance.

TIFF delivery accepts `image_options.depth` and `image_options.channels` on document export, artboard export and create-only publication:

```json
{"format":"tiff","image_options":{"depth":"u16","channels":"rgba","compression":"deflate"}}
```

Explicit options select a full-precision render followed by the requested final sample projection. Unsigned values round to the nearest integer; binary32 uses the platform's IEEE conversion. Arithmetic uses binary64, so a mathematically exact integer half-way tie after compositing may choose either neighbor within floating-point roundoff. Alpha is unassociated and output color is zero when output alpha rounds to zero. Compositing may normalize signed zero; native import and unchanged source snapshots retain its bits. Uncompressed, LZW and Deflate delivery retain the resulting samples losslessly. Gray-alpha output requires exactly equal rendered RGB values; chromatic input returns `GRAYSCALE_CONVERSION_REQUIRED`. There is no implicit luma conversion. Density, metadata privacy, artboard order, antialiasing and padded render bounds keep their shared contracts.

Omitted TIFF depth/channel options retain the existing RGBA8 export behavior. Selecting only one option defaults the other to `u8` or `rgba`. PNG, JPEG and ordinary previews remain 8-bit; a `sample_precision` receipt identifies the retained sources and output projection without changing source values. TIFF receipts also report the actual depth/channel layout. Output profiles on the explicit-depth TIFF path fail rather than passing through an RGB8 conversion. SVG and PDF do not currently deliver retained sample grids. High-depth brush/mask baking and non-RGB working modes remain separate pending work. See HDR.md for explicit linear float delivery and display views.

## Import without reducing depth

`sample.import` takes an absolute `source_path`, a new document `id`, optional `resolution_ppi` (96 by default) and `color_policy`. By default it reads PNG or TIFF into a new inline sample document, returns a SHA-256 receipt and never writes files. Optional `storage.store_root` publishes immutable native blocks for larger sources and returns `stored_samples` content; under a workspace, `storage:{}` opts in with the default asset store. See [native sample storage](NATIVE_SAMPLE_STORAGE.md) for external resource binding, exact retained patches and limits. Import preserves 8/16-bit PNG and unsigned 8/16-bit or normalized binary32 TIFF values, including straight alpha and hidden color. Gray input stays gray-alpha; missing alpha becomes opaque. PNG palette/low-bit samples expand to 8-bit explicit channels, and Adam7 interlacing is supported. TIFF supports either byte order, interleaved or separate planes, strips or tiles, and uncompressed, LZW, Deflate or PackBits encoding. White-is-zero grayscale is inverted into the engine's ordinary intensity convention.

The default `require_srgb` policy requires explicit sRGB PNG metadata. Untagged PNG and supported TIFF need `assume_srgb`, which declares how their samples are interpreted. Embedded profiles, alternate transfer functions/chromaticities, orientation transforms, associated alpha, undeclared HDR/nonfinite floats, raw/nested TIFF directories and multi-image TIFF fail explicitly. `convert_srgb` is unsupported on this path. Existing `asset.import` retains its separate byte-image and profile conversion contract.

Source descriptions recover separately as untrusted receipt metadata. Source density does not override the requested document resolution. Inline import is limited to 32 MiB of source, 65536 inline pixels, bounded decoder memory and the ordinary 768 KiB snapshot limit. TIFF padded tile work is bounded to 64 MiB, with 16 MiB inline decoder allocations. The snapshot limit may bind before the pixel limit for floating-point RGBA grids. Native stored import instead admits up to 16,777,216 source pixels and 64 MiB of native channels, with unchanged output limits. Invalid or oversized input never yields a partial document.

## Explicit depth and grayscale conversion

The atomic `sample_convert` edit applies to a sample grid or promotes a legacy inline RGBA8 layer. It retains identity, placement, sampling, appearance and pixel-deformation controls, checks item/ancestor locks and participates in durable undo/redo:

```json
{"op":"sample_convert","id":"pixels","conversion":{"depth":"u16","channels":"gray_alpha","gray":"linear_luminance"}}
```

`depth` and `channels` are required. Optional `encoding` and `view` control explicit HDR conversion as described in HDR.md. `gray` only applies to gray-alpha output:

| Policy | Meaning |
| --- | --- |
| `require_neutral` (default) | All source RGB components must be exactly equal; chromatic input fails |
| `encoded_luma` | Weighted encoded RGB: `(2126 R + 7152 G + 722 B) / 10000` |
| `linear_luminance` | Decode the standard piecewise sRGB transfer, apply those weights in linear light, then re-encode |

Gray-to-RGB repeats the intensity in each color component. Alpha converts independently without premultiplication; hidden color is not discarded when alpha rounds to zero. The selected grayscale policy also applies to hidden color. Integer conversion rounds once at the requested depth; binary32 uses IEEE conversion. Encoded-luma conversion between integer depths uses exact integer weights and rounds half-way ties upward. Other arithmetic retains the declared binary64 rounding boundary. No-op depth/layout requests retain the original byte string exactly, including signed zero and hex casing. Receipts report input/output depths/layouts, decoded-byte hashes, quantized channel count and maximum depth-quantization error; that error excludes the intentional color-to-gray transform.

Run `python examples/sample_conversion_workflow.py --output <new-directory>` to create an original 16-bit PNG, import it, convert an editable copy to linear-luminance grayscale and publish retained snapshots and explicit-depth TIFFs. Conversion, import and the HDR path share the extended-precision acceptance criterion. All parts require complete independent verification before checkpoint credit.

Run `python examples/sample_workflow.py --output <new-directory>` to author an original precise ramp, edit a rectangular patch, and publish a retained snapshot, 16-bit and float TIFFs and an 8-bit preview. Tests use exact native code values, rational compositing/convolution, independent reconstruction kernels and a separate TIFF tag/sample reader. External decoder evidence remains in private development receipts.
