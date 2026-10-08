# Calibrated print observation

`document.proof` observes the same flattened, matted CMYK8 samples delivered by `pdf_options.print`. It returns a calibrated RGB preview, four exact process-ink planes and measured colour differences. Agents can compare candidate profiles, locate large changes and inspect ink coverage before delivering a page. The command is read-only: it does not edit a document, publish files or send a print job.

```json
{
  "command": "document.proof",
  "document": {"...": "a valid engine document"},
  "options": {
    "print": {
      "profile": {"type":"file","source_path":"ABSOLUTE_PATH_TO_OUTPUT_ICC","sha256":"EXACT_LOWERCASE_SHA256"},
      "matte": [255,255,255],
      "intent": "relative_colorimetric",
      "raster_scale": 1
    },
    "view_intent": "absolute_colorimetric",
    "delta_e76_threshold": 2,
    "samples": [[0,0],[10,10]]
  }
}
```

Use the discovered schema for complete request shapes. Profile resolution, 4 MiB profile limit, exact file hash, required matte, separation intents, flattening and render settings share [PRINT_CMYK.md](PRINT_CMYK.md). Untagged document paints retain their explicit working-sRGB interpretation; a CMYK output profile is mandatory. A document RGB output association conflicts and must be explicitly cleared on a copy. `print.render_options` supplies antialiasing, effect bounds and an explicit HDR display view when needed. Uncropped rendering is rejected.

An optional `artboard_id` selects that board's standalone coordinates, excluding its world placement. `include_bleed:true` requires a board. Resolution is document PPI times `print.raster_scale`; scale changes sample density without altering physical size. Samples use integer top-left output-pixel coordinates after bleed and scaling. At most 64 entries are accepted, in caller order, including duplicates. The ordinary render budget is 1,048,576 evaluated pixels; padding and antialiasing also consume it. The entire JSON result is bounded to 32 MiB. Profile setup, rendering and each PNG encoding are bounded operations; cancellation is checked between them and each 4,096-pixel colour batch.

The result contains:

- `preview`: opaque RGBA8 PNG with the exact working sRGB ICC profile embedded. It depicts the selected colourimetric view of the actual separated bytes.
- `plates`: `cyan`, `magenta`, `yellow` and `black` grayscale8 PNGs. Their bytes are exact CMYK samples: zero means no ink; 255 means full ink. These scalar planes have physical density but no colour profile or transfer-curve declaration. They are diagnostic ink amounts, not display colours or print negatives.
- `difference`: mean and maximum D50 CIE76 distance, the explicit threshold, count strictly above it and a binary scalar PNG mask. White pixels exceed the threshold; black pixels do not. Equality is excluded.
- `display_clipping`: pixel and per-channel counts outside the strict linear-sRGB interval `[0,1]`, measured before clamping. No epsilon is applied. Very small excursions can count even when byte rounding hides them.
- `total_ink`: maximum and mean sum of the four normalized ink fractions, in `0..4`. Each plate also reports its minimum, maximum and mean fraction.
- `samples`: actual CMYK8, source/proof XYZ and Lab, linear display RGB, preview bytes and CIE76 distance at each requested coordinate.
- Profile, artifact and decoded-sample hashes; exact matte, scale, resolution, render settings and source revision. `cmyk_sha256` matches the corresponding print PDF image stream. Profile source paths and document descriptions are excluded.

`print.intent` supports all four rendering intents and controls separation. `view_intent` supports relative and absolute colourimetric observation of the actual resulting ink bytes. It selects A2B1, falling back to A2B0, and optionally scales by the declared media white. Absolute viewing retains the profile's paper-white influence; relative viewing normalizes it. Supplied gamut classification also uses colourimetric coordinates: absolute when separation is absolute, relative otherwise. Its receipt names this diagnostic intent separately. No optional black-point compensation or endpoint fixup is introduced.

PCS interpretation follows [ICC.1:2022](https://www.color.org/specifications/ICC.1-2022-05.pdf), sections 6.3.2, 10.10, 10.11 and Annex A. Lab table codes are interpreted according to their tag type, including legacy 16-bit Lab inside a v4 profile. A private numerical transform isolates table evaluation before the analytic Lab-to-XYZ step; it never replaces the original profile. Eight-bit XYZ connection tables fail explicitly because their interpretation is not standardized. CIE76 is Euclidean distance in D50 Lab, measured before display clipping and byte quantization, from the exact encoded matte products to the observed CMYK8 result.

Colour difference is not exact gamut membership. It includes profile mapping, lookup approximation and irreversible CMYK8 quantization. The threshold is a caller-selected diagnostic, not a certified printing tolerance. Pre-display differences and display clipping answer different questions and remain separate. Inkbolt does not apply an arbitrary monitor profile, simulate lighting beyond the stated PCS model or certify a printing condition.

The pinned colour engine uses multilinear interpolation for four-dimensional tables, 65,536 interpolation-weight bins for CMYK input, and finite internal lookup precision. Other colour engines can choose a different interpolation algorithm. Coarse nonlinear synthetic profiles can produce substantial differences between consumers; matching profile bytes alone does not guarantee identical appearance. Independent affine profile checks separate encoding and white-point correctness from that interpolation choice. Original nonlinear charts independently test the declared multilinear behaviour. The observed test tolerances are fixture-specific, not a universal bound for every ICC profile.

Named spot alternates become process colours under the existing explicit display contract; overprint fails unless display artwork has been explicitly baked. Retained spot/duotone recipes and exact named plates are described in [INK_RECIPES.md](INK_RECIPES.md). Combined calibrated process/spot delivery and profile-supplied gamut diagnostics are described in [COMBINED_PREPRESS.md](COMBINED_PREPRESS.md). Vector native overprint and managed device paints have separate verified contracts in [VECTOR_PLATES.md](VECTOR_PLATES.md) and [DEVICE_COLOR.md](DEVICE_COLOR.md); proof remains a physical colourimetric observation of the declared separation.

Run [proof_workflow.py](../examples/proof_workflow.py) for an original chart, source snapshot, two views, exact plates and threshold masks in a new output folder. Without `--profile`, the example uses a labelled analytic demonstration profile, not a calibrated printing condition. `tests/test_proof_cli.py` checks independent colour equations, legacy/modern encodings, actual PDF samples, density, artboards, source preservation, file identity, cancellation and read-only agent/session behaviour.
