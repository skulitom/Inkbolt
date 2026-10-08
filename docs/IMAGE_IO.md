# Image import and delivery

Additional BMP, TGA, GIF and associated TIFF alpha contracts are in [EXTENDED_IMAGE_IO.md](EXTENDED_IMAGE_IO.md).

Native-depth PNG/TIFF sample import is described in [SAMPLES.md](SAMPLES.md); signed linear binary32 TIFF and explicit display views are described in [HDR.md](HDR.md).

Inkbolt imports PNG, JPEG and TIFF into immutable straight RGBA8 assets, and exports rendered documents or artboards to these image formats. The library, JSON CLI and MCP stdio share the same behavior. Keep snapshots and resource stores for editable layers, text, masks and effects; an image is a flattened result.

## Import

Use `asset.import` with explicit absolute `source_path` and `store_root`. Content signatures select the decoder; filename extensions do not determine interpretation. The result carries `asset`, `created`, `source_format` and `losses`. Each asset retains a SHA-256 of its original file and an independent SHA-256 of normalized dimensions/pixels. Import reads the source and publishes a new content-addressed blob, never overwriting an existing source or store entry. Identical normalized pixels deduplicate even across formats. Transparent RGB samples are preserved during import; subsequent rendering uses the existing transparent-black output contract.

Default `color_policy:"require_srgb"` accepts explicitly tagged sRGB PNG. Untagged JPEG/TIFF import requires `color_policy:"assume_srgb"`; that interpretation is recorded in the descriptor. This is an explicit interpretation of untagged samples, with no color-profile conversion. Embedded RGB ICC profiles instead require `color_policy:"convert_srgb"`; an explicit input_profile can declare untagged input. See [COLOR_PROFILES.md](COLOR_PROFILES.md) for conversion, output association and profile limits. Assumption policies still reject embedded ICC profiles; other unsupported color/orientation metadata fails explicitly.

| Format | Accepted semantics | Explicit boundaries |
| --- | --- | --- |
| PNG | Existing grayscale, palette, RGB/RGBA, interlaced, up to 8-bit normalized channels | No high depth, animation, non-RGB profiles, EXIF or HDR reinterpretation |
| JPEG | 8-bit grayscale or RGB, baseline and progressive scans | No CMYK/high depth or APP1/APP13/APP14 metadata; APP2 only for explicit RGB ICC conversion; malformed, truncated and trailing bytes fail |
| TIFF | Classic TIFF or BigTIFF, either byte order, strips/tiles and chunky/planar samples; grayscale/RGB and explicitly associated or unassociated grayscale-alpha/RGBA8; uncompressed, LZW, Deflate or PackBits | One image only, top-left orientation, unsigned 8-bit samples; no non-RGB profiles, transfer functions, alternate chromaticities, nested image directories or raw interpretation; white-is-zero grayscale requires no alpha |

Source resolution and descriptive metadata are reported as losses and represented only by the source-byte hash. Placement dimensions and document resolution are explicit engine settings. Unspecified TIFF alpha, unsupported photometric encodings and additional pages fail rather than producing a partial or reinterpreted image. PNG chunk checks, JPEG marker/scan framing and bounded TIFF decoding precede storage. Source bytes are capped at 32 MiB, decoded dimensions at 32768 per axis and 16777216 pixels; decoder buffers are capped at 64 MiB. Existing asset/document storage limits also apply.

## Export

`document.export` and `artboard.export` accept `format:"jpeg"` or `format:"tiff"` plus optional `image_options`. `document.publish` and `session.publish` accept the same options inside `output`. PNG, SVG and snapshot formats reject a supplied image-options object. Unknown fields and inapplicable settings fail explicitly.

```json
{"format":"jpeg","scale":1,"image_options":{"quality":95,"chroma":"full","matte":[245,245,245]}}
```

JPEG quality is an integer 1..100, default 90. Chroma is `full` (4:4:4, default) or `half` (4:2:0). If any rendered alpha is below 255, an explicit three-byte RGB `matte` is required; otherwise `ALPHA_POLICY_REQUIRED` prevents output. Matte compositing happens in encoded sRGB, rounded to the nearest byte: `(color*alpha + matte*(255-alpha) + 127) / 255`, using integer division. Opaque images need no matte. JPEG cannot retain alpha and remains lossy even at quality 100. Resolution is rounded to whole pixels per inch and written as JFIF density.

```json
{"format":"tiff","scale":2,"image_options":{"compression":"deflate"}}
```

TIFF compression is `none`, `lzw` or `deflate` (default). The default unassociated mode retains rendered straight RGBA8 samples losslessly, with explicit unassociated alpha and top-left orientation. Output is classic TIFF with inch resolution rounded to 0.001 pixels per inch. Without output_profile, JPEG/TIFF outputs use untagged sRGB interpretation and embed no ICC profile. An associated RGB profile converts samples and embeds its exact bytes; see COLOR_PROFILES.md. Export receipts report these limitations and the effective encoding settings.

Optional `render_options` selects geometric antialiasing, supersampling and effect margins before encoding; see [RENDER_QUALITY.md](RENDER_QUALITY.md). All image formats share the rasterizer, resource verification, scale 1..4, pixel/work limits, selected variant and artboard coordinate semantics. Artboard ranges return all artifacts or one failure identifying the affected artboard. Bleed and selected board ownership work identically across formats. Create-only publication accepts `.jpg`/`.jpeg`, `.tif`/`.tiff` and the existing format extensions, case-insensitively; it reports byte hash, dimensions through the artifact, revision, encoding settings and losses. Publication never overwrites an existing file. Encoded JPEG/TIFF outputs are capped at 32 MiB; artboard batches also retain their cumulative pixel/work/encoded-data budgets.

## Verification and fidelity

`tests/test_image_io_cli.py` generates original TIFF structures independently, checks byte orders, planar/chunky samples, compression, alpha semantics, exact normalized hashes, resolution tags, malformed/unsupported inputs, source preservation, artboard ranges, create-only publication and durable MCP sessions. Existing PNG tests retain their independent chunk/filter decoder.

The original 96 by 64 smooth RGB fixture uses `(30+x, 40+2*y, 50+floor((x+y)/2))`. Maximum channel-error bounds are 4 at JPEG quality 100, 6 at quality 90 and 9 at quality 75, for both declared chroma settings. These are fixture acceptance tolerances, not guarantees for arbitrary artwork. Independent external JPEG decoding additionally checks PSNR thresholds of 43, 39 and 35 dB respectively, and a second encode/decode cycle against a bound three levels larger. JPEG decoder comparisons allow up to three byte levels for independent IDCT/color rounding. Sharp edges, noise and repeated lossy saves can have much larger errors; choose PNG/TIFF when pixel equality matters.

Private milestone verification uses separate Pillow/libtiff and tifffile writers/readers, plus original TIFF strip parsing with Python zlib for Deflate. It covers baseline/progressive JPEG, grayscale/color, explicit mattes, lossless pixels, multiple strips, tiles, planar images, BigTIFF, both byte orders and rejected profile/page semantics. External verification packages stay outside the repository; the normal test suite uses the Python standard library. See the original [image delivery example](../examples/image_io_workflow.py). Non-RGB profiles, additional intents, depth and broader metadata workflows remain separate requirements in the unchanged registry.

Recognized Inkbolt descriptive envelopes now round-trip through PNG iTXt, numbered JPEG comments and TIFF ImageDescription. Imports return them as separate untrusted metadata; normalized pixels and source hashes retain their existing contracts. Descriptive stripping keeps density, top-left pixels and explicit ICC interpretation intact. General external metadata dialects remain unsupported; bounded BMP/TGA origin normalization and additional formats are described in EXTENDED_IMAGE_IO.md. See [METADATA.md](METADATA.md).
