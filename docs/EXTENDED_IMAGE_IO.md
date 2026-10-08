# Additional image formats and alpha policies

The Rust library, JSON CLI and MCP stdio now share BMP, TGA and exact-palette GIF exchange. Existing PNG/JPEG/TIFF metadata and ICC contracts remain in [IMAGE_IO.md](IMAGE_IO.md) and [COLOR_PROFILES.md](COLOR_PROFILES.md). These formats deliver flattened images; editable artwork remains in snapshots. Imports preserve source files and their byte identities. Publication is create-only.

## BMP and TGA

`asset.import` recognizes BMP signatures and bounded TGA headers/footer without relying on filenames. These inputs are untagged: select `color_policy:"assume_srgb"`, or use `convert_srgb` with an explicit RGB `input_profile`. Neither format embeds an ICC profile in this contract. A saved output profile causes export to fail; clear the association explicitly or choose a profiled PNG/JPEG/TIFF.

BMP input accepts a 40-byte information header, uncompressed 24-bit RGB or 32-bit RGB with an unused fourth byte, and positive/bottom-up or negative/top-down height. Row padding is skipped; the fourth byte never becomes undeclared alpha. Palette, bitfield and extended profile headers are unsupported. File size, pixel offset, dimensions, planes, row sizes and complete framing are checked before storage. Export `format:"bmp"` writes bottom-up BMP24 with four-byte row alignment and density rounded to whole pixels per meter. Transparency requires `image_options:{"matte":[255,255,255]}` or another explicit RGB matte, composited in encoded working sRGB by the same integer equation as JPEG.

TGA input accepts raw or run-length packets in RGB24, RGBA32, gray8 and gray-alpha16, all four pixel origins and an optional image ID. Output `format:"tga"` writes top-left RGBA32 with a version-2 extension declaring useful unassociated alpha. An eight-bit attribute descriptor in legacy input retains alpha; zero attribute bits mean opaque pixels. Extension alpha types 0/1 ignore attributes, 2/3 retain them, and 4 unassociates premultiplied samples. Undefined retained attributes are interpreted as straight alpha under this declared contract. Invalid associated values above alpha fail. Interleaved storage, palettes, gamma/aspect/color transforms, auxiliary tables and developer metadata dialects remain explicit errors.

BMP/TGA exports cannot carry the descriptive metadata envelope. If descriptions, a manifest or provenance would be included, choose `metadata_policy:{"mode":"strip"}` without manifest/provenance or use another carrier. TGA has no physical-density field in this contract. Source coordinate and descriptive records remain represented by source-byte identity; import never silently changes placement or document resolution. Both formats support artboard ranges, bleed, render-quality controls, normal resource bounds and create-only publication.

## GIF stills and sequences

Use `format:"gif"` for a still or every ordered frame of a retained sequence. There is no automatic colour quantization, alpha threshold or timing rounding. Every frame must fit an exact palette of at most 256 entries. If any frame is transparent, one entry is reserved in every palette, leaving at most 255 opaque colours per frame. Alpha must be zero or 255. Hidden transparent colours normalize to zero. More colours or graded alpha fail with `UNSUPPORTED_GIF_PALETTE` or `UNSUPPORTED_GIF_ALPHA`.

Frame delays must be exactly representable as 0..65535 centiseconds, or `UNSUPPORTED_GIF_TIMING` is returned. Zero delay is retained; consumers choose actual scheduling. Total plays are 0 for infinite or 1..65536. A positive stored loop-extension count represents repetitions after the initial play. Single-play output omits the loop extension. Each encoded frame covers the complete canvas and restores the transparent background before the next frame. The deterministic writer uses literal LZW codes with bounded resets; compression ratio is not optimized.

`asset.import` accepts one-frame GIF and explicitly rejects multi-frame input. To retain timing, use:

```json
{"command":"sequence.import","id":"animation","source":{"type":"gif","source_path":"C:/work/original.gif","background":"transparent"},"color_policy":"assume_srgb","store_root":"C:/work/assets"}
```

The reader expands full variable-width LZW dictionaries, including deferred clear codes, and handles global/local palettes, four-pass interlacing, frame rectangles, transparency, keep/background/previous disposal, and finite/infinite looping. The default `background:"transparent"` defines the initial canvas and restore-background disposal. `background:"logical_screen"` instead uses the global palette's declared background colour. This choice resolves a format convention explicitly; it does not guess a consumer's backdrop. Sequence input requires the explicit untagged sRGB policy. A still can also use an explicitly supplied RGB input profile. Unknown application extensions, interactive timing, plain-text graphics and nonzero pixel-aspect declarations fail.

The selected public/stripped Inkbolt metadata envelope round-trips in a GIF comment and is returned as untrusted data. Other comments are represented only by source identity. Metadata does not automatically become editable document records. GIF output rejects an associated ICC output profile and does not write physical-density fields. Sequence storage, editing, timing inspection, undo/redo, retry and source reopening use the existing [SEQUENCES.md](SEQUENCES.md) contracts.

GIF import is bounded to 32 MiB, 256 frames and 16,777,216 aggregate decoded pixels. Sequence storage additionally requires at most 32 distinct frame states and a renderable canvas. Malformed inputs fail before the prepared GIF frames are published. Export keeps existing aggregate frame, render-work, output-size and cancellation limits.

## Associated TIFF alpha

RGBA8 TIFF export accepts `image_options:{"alpha":"associated"}`; default `unassociated` preserves the existing straight-alpha output. ICC conversion occurs before association, then each destination byte becomes `(color*alpha+127)/255` with integer division. The exact alpha byte and the matching TIFF ExtraSamples declaration are retained. Associated storage loses hidden RGB and low-alpha precision; loss receipts state this explicitly.

Eight-bit RGB/gray TIFF asset import accepts both declared alpha modes. Associated colour is divided by alpha with nearest-integer rounding; zero alpha requires zero colour. This precedes any ICC conversion. Unspecified alpha still fails. Explicit native-depth TIFF sample delivery/import retain their separate unassociated contract; associated delivery combined with a native-depth option fails rather than ignoring the request.

## Evidence

`tests/test_legacy_image_cli.py` checks original row/origin/compression fixtures, alpha equations, metadata/profile combinations, artboards, quality controls, malformed data, unchanged sources and publication. `tests/test_gif_cli.py` checks independent palettes, dictionary widths and special LZW codes, disposal and interlacing, exact timing, limits, metadata and durable agent history. [The format example](../examples/format_workflow.py) produces original deliverables and a two-frame sequence in a new directory.

Implementation derives from public container specifications: [BMP header fields](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/ns-wingdi-bitmapinfoheader), the original TGA 2.0 specification, and [GIF89a](https://www.w3.org/Graphics/GIF/spec-gif89a.txt). Synthetic fixtures and independent decoders verify delivery; no source application implementation is used.
