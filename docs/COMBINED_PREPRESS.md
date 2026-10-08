# Combined ink delivery and gamut diagnostics

Agents can deliver calibrated process artwork together with independent named spot or duotone plates, inspect reference proofs and query a supplied profile's gamut table. All work stays local. The engine preserves editable sources and never sends a print job.

## Process plus named plates

Retain an `ink_recipe` as described in [INK_RECIPES.md](INK_RECIPES.md). Add `named_inks` to the ordinary [print settings](PRINT_CMYK.md), in either `pdf_options.print` or `document.proof`'s `options.print`:

```json
{
  "profile":{"type":"file","source_path":"ABSOLUTE_PATH_TO_OUTPUT_ICC","sha256":"EXACT_LOWERCASE_SHA256"},
  "matte":[255,255,255],
  "raster_scale":1,
  "named_inks":{
    "model":"multiplicative_cmyk",
    "alternate_cmyk":{"blue":[0.8,0.5,0,0],"warm":[0,0.6,0.8,0]}
  }
}
```

Supply exactly one normalized CMYK quadruple for each recipe ink ID. The process artwork uses the unchanged profile conversion and explicit matte. Each named plate uses its retained source curve and optional mask. The PDF image interleaves the exact four process bytes followed by the named bytes in recipe order, using PDF DeviceN/NChannel, reserved process names and `Inkbolt.<id>` spot names. The embedded CMYK profile and explicit colorant definitions accompany delivery. The process and named samples remain independent; their values are not folded into each other.

For reference appearance only, each CMYK component is `1 - (1 - process) * product(1 - tint * alternate)`. The original PDF calculator evaluates that same supplied formula. `document.proof` observes the continuous fallback through the process profile, using 65,536 backend interpolation-weight bins rather than reducing it to another byte image. The retained recipe's separate RGB corner model remains unchanged and is used for recipe-only delivery. No physical interaction or spectral calibration is inferred from either supplied appearance model.

Proof results add ordered `named_plates`, `total_ink_including_named`, hashes of process and combined bytes, the supplied model and per-sample `named8`/`fallback_cmyk`. The four existing `plates` remain exact process samples. Both sets are scalar grayscale8 PNGs with physical density and without color transfer tags. A reference preview is an opaque, ICC-tagged sRGB PNG. All outputs preserve the source document and are reproducible; file publication remains create-only.

Combined delivery requires the whole canvas, 1..8 named inks and integer scale 1..4. Artboard selection, bleed, another document RGB output association and native vector-ink delivery conflict explicitly. Crop an editable copy with its channels first when a smaller region is needed. The existing render, profile, PDF and 32 MiB proof-output bounds apply. Ordinary paint alternates enter the process artwork; only an explicit recipe creates additional plates. Vector overprint simulation is outside this raster contract.

PDF readers can use their own color-management paths. In independent synthetic charts, all 163,840 process/spot samples survived native separation exactly and one reader's display matched the reference within one byte level. Another reader differed by up to 58 byte levels, including when the same fallback was delivered as plain calibrated CMYK. Therefore the reference PNG defines the supplied proof view; identical preview pixels across PDF readers are not promised. These measurements concern original fixtures, not arbitrary profiles or physical printing.

## Gamut table inspection

`profile.gamut` accepts the same pinned profile source, `xyz_d50` (at most 4,096 finite triples), a colorimetric `intent`, and optional cancellation/deadline `control`. Coordinates are working D50 XYZ. Relative mode uses those directly; absolute mode first applies the source-to-profile media-white scale, reported in the receipt. The command returns the profile/tag hashes, table type, encoded PCS coordinates, scalar values and classifications without editing or publishing anything.

The original evaluator follows the public [ICC.1:2022 specification](https://www.color.org/specifications/ICC.1-2022-05.pdf), including gamutTag, lut8Type, lut16Type, lutBToAType and parametricCurveType. It supports CMYK output profiles in versions 2 and 4, XYZ or Lab PCS, 3-input/1-output gamut tables, sampled and all five parametric curve forms, matrix stages, anisotropic modern grids and 8/16-bit CLUT storage. Legacy 16-bit Lab encoding is chosen by tag type. Eight-bit XYZ tables, non-colorimetric interpretation and unsupported tables fail explicitly.

Evaluation uses original binary64 arithmetic, exact decoded fixed-point parameters, linear curve interpolation and tetrahedral CLUT interpolation with descending fractional-coordinate order. It preserves exact zero versus nonzero table results. A zero is classified `in_gamut`; a nonzero value is `out_of_gamut`. Coordinates outside the tag's PCS encoding are `outside_pcs_encoding` with a null value; the source is not silently clamped into the gamut. This reports the supplied profile's classification, not independently certified press behavior or an exact geometric gamut volume. Color libraries using integer intermediates can disagree exactly at boundaries. Independent floating-point library checks covered 8,019 samples across 11 original table families with matching classifications and maximum scalar difference below 0.000000083.

`document.proof` accepts `gamut:"if_available"` (default), `"required"` or `"off"`. Available results add out-of-gamut and unclassified scalar PNG masks, counts, maximum table value and requested sample classifications. They evaluate the matted process-source PCS before separation; they do not infer a physical gamut for arbitrary named inks. Missing tables produce an explicit unavailable receipt, or `GAMUT_UNAVAILABLE` in required mode and in `profile.gamut`. Disabled mode returns `status:"disabled"`.

These diagnostics remain separate from D50 CIE76 round-trip difference and display clipping. A difference threshold is never substituted for missing gamut membership. Unknown fields, malformed ranges/offsets/channels, changed file hashes and excessive work fail explicitly. Run [combined_prepress_workflow.py](../examples/combined_prepress_workflow.py) for a source snapshot, six exact plates, preview, gamut masks and combined PDF in a new folder.
