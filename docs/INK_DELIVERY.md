# Native ink delivery

For combined ordered page, trim, bleed and ink delivery, see [PREPRESS.md](PREPRESS.md).

Named paints retain `overprint:"knockout"` (default), `"preserve"` or
`"preserve_nonzero"`. These controls are independent of tint and opacity.
Snapshots, transfer, atomic edits and durable history keep them with the paint.
Names remain labels; the base swatch ID determines a spot's ink identity.

## Classification and recoloring

The existing `swatch` operation recolors all live users and tint aliases. To
change a base definition between spot and process while retaining its exact
components, ID, name, references and paint controls:

```json
{"op":"swatch_convert","id":"accent","kind":"process"}
```

`kind:"spot"` performs the reverse classification. An optional `color` supplies
an explicit replacement process declaration, using the same shape as a swatch's
`color` or `alternate`. This is a caller-directed declaration change, not an ICC
conversion. Convert a tint's base definition; converting the alias itself fails.
The receipt retains before/after declarations and affected users. Locks on
dependent items, ancestors, components, masks and saved variants remain enforced.
Changing classification can change overprinted appearance because different ink
channels are affected. The operation retains overprint rather than guessing a
replacement printing policy.

## Explicit PDF ink mode

Use `pdf_options:{"color":"native_inks"}` with `document.export`, or within the
`output` of document/session publication. The default `color:"display"` retains
the existing RGB appearance contract. Combine native ink mode with the ordinary
`artboards` and `include_bleed` fields for ordered pages and physical page boxes.
When using this mode, select a single page through `pdf_options.artboards` rather
than publication's shorthand `artboard_id`.

- Spots use PDF Separation color spaces. Their names are `Inkbolt.<base_id>`;
  duplicate labels stay distinct and reserved output names cannot be introduced.
  The same ink resource is reused across pages. Nested tint amounts multiply
  without changing stored values. Alternate sRGB/encoded gray, CMYK or D50 Lab
  values remain explicit; no display preview is required.
- Process CMYK writes exact declared components multiplied by effective tint.
  Process Lab interpolates from `[100,0,0]`; its PDF space declares D50 white
  `[0.9642,1,0.8249]` and a/b ranges `[-128,127]`. Process sRGB and encoded gray
  retain the established white-to-color display tint formula. Encoded gray uses
  equal RGB components so no unspecified gray transfer curve is substituted.
- Spot tint functions interpolate from white in their declared alternate space:
  RGB white is `[1,1,1]`, CMYK paper is `[0,0,0,0]`, Lab white is `[100,0,0]`.
  Lab/CMYK alternate interpolation is a declared PDF fallback, distinct from the
  caller-supplied sRGB preview used by image exports.
- `knockout` sets fill/stroke overprint false. `preserve` sets both true with
  mode 0. `preserve_nonzero` sets both true with mode 1: exact-zero DeviceCMYK
  components leave underlying ink untouched. A spot always addresses its own
  channel, including zero tint, while preserving other channels when overprinting.
  Outlined strokes retain their own paint's controls independently of fills.
- Process overprint requires explicit CMYK. RGB, encoded gray and Lab process
  overprint fails because the engine has no implicit separation conversion.
  Converting a spot to one of these process spaces retains the paint control;
  the next native export reports the unsupported combination.

Native pages blend in DeviceCMYK. Unit-opacity leaves use ordinary forms so
their paints interact with the existing backdrop. Leaf item/fill opacity applies
once through a nonisolated group, retaining overprint interaction. Actual groups
and frames retain their established isolation: inks outside an isolated group
are not its internal backdrop. Paint alpha, item opacity and group opacity are
separate controls. Existing PDF exclusions for effects, masks, non-normal blends,
profiles and other unsupported content continue to apply.

This follows the public PDF overprint and transparency model; see the
[PDF Association's overprint explanation](https://pdfa.org/understanding-overprint/).
Print-ready profile conversion, proofing, plate raster generation and broader
prepress remain separate requirements. PDF consumer color management and edge
antialiasing can differ; native ink operands are not a promise of display pixels.
Some consumers also differ when combining nested nonisolated groups with paint
and item opacity. Verification checks native process/spot channels with an
ink-aware consumer; an ordinary composite preview is not a separation proof.

## Diagnostics and display copies

`swatch.inspect.ink_diagnostics` lists current named paints, resolved base values,
spot IDs, process spaces and overprint compatibility. It explicitly includes
hidden/shared resources and is a structural inventory, not plate coverage or
complete export preflight. Saved variants are reported as dependencies in the
ordinary swatch entries. Native PDF receipts contain an inventory for each
selected page and disclose consumer conversion of ordinary RGB content.

Image rendering and display SVG/PDF cannot simulate overprint and reject active
overprint paints. `swatch_bake` on an explicit copy produces an ordinary sRGB
display approximation and records loss of ink identity, tint references and
overprint. Baking does not simulate the overprinted result. Retain the original
snapshot and native PDF for ink-aware delivery.

The original [ink workflow](../examples/ink_workflow.py) saves the original spot
document, delivers native ink PDF, explicitly converts a copy to process and
saves both declarations and diagnostic receipts. `tests/test_ink_delivery_cli.py`
independently parses PDF color resources, numbers, overprint operators, groups,
page boxes and named glyph/stroke paints, and checks persistence and failures.
