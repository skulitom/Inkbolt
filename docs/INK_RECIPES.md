# Editable ink recipes

A retained `ink_recipe` maps saved grayscale source channels to one through eight named ink plates. It supports monotones, duotones and multitone graphics, or unrelated spot artwork on separate channels. Curves and optional scalar masks stay editable, and the original sources stay unchanged. The recipe is nonprinting until an agent explicitly requests separation or recipe PDF delivery.

Use `document.edit` with `{"op":"ink_recipe","recipe":{...}}`; set `recipe:null` to clear it. Each ink has a unique portable `id`, a descriptive `name`, a source `channel`, an `alternate_srgb` colour and a `curve`. An optional `mask_channel` controls the final amount. Names can repeat; IDs determine plate identity. Source channels may have alpha or spot roles: this explicit recipe supplies output identity and interpretation instead of inheriting that metadata. Existing channel removal fails with `CHANNEL_IN_USE` while a recipe references it. A batch can clear or replace the recipe before removing a channel.

```json
{
  "inks": [
    {"id":"blue","name":"Blue ink","channel":"gray","alternate_srgb":[30,80,170],"curve":[[0,1],[0.5,0.4],[1,0]]},
    {"id":"warm","name":"Warm ink","channel":"gray","mask_channel":"coverage","alternate_srgb":[190,80,30],"curve":[[0,0.7],[0.5,0.2],[1,0]]}
  ],
  "preview":{"type":"transmittance","paper_srgb":[255,255,255]}
}
```

Curves contain 2..64 normalized input/output pairs. Inputs increase strictly from zero to one; outputs may increase or decrease independently. For each source byte, the engine interpolates at `source/255` using exact rational values of the stored binary64 knots. It multiplies by the mask fraction and rounds once to the nearest unsigned eight-bit ink amount, with ties upward. No mask means full coverage. A plate byte of zero means no ink and 255 means full ink. Masks are scalar coverage, not an additional ink or an ordinary artwork opacity control.

`document.separations` takes a document, optional integer `scale` from 1 through 4, and optional cancellation/deadline `control`. It returns one grayscale8 PNG per ink, an opaque sRGB preview PNG, source/mask/sample/artifact hashes, min/max/mean ink amounts and explicit delivery losses. Scalar plates carry physical density but no ICC or transfer-curve declaration. The preview embeds its sRGB ICC bytes. Scaling repeats source cells exactly and multiplies sample density, preserving physical size. The complete JSON result is limited to 32 MiB and output to 1,048,576 pixels.

Two supplied appearance models are supported:

- `transmittance` decodes the supplied paper and ink sRGB colours into linear RGB. Each full-ink corner multiplies the paper by the active ink components. This is a declared graphic approximation, not a calibrated physical press model.
- `corners` supplies `linear_rgb`, an array of exactly `2^ink_count` normalized RGB triples. Corner zero is paper; the first ink is the least significant bit and changes fastest. This permits independently supplied mixture colours.

Corners are rounded once to unsigned 16-bit values. Preview pixels use multilinear interpolation between those exact corners at the delivered ink amounts, then sRGB encoding. The receipt includes the actual corner table. Preview work is bounded by `pixels * (ink_count + 1) * 2^ink_count <= 67,108,864`; the same bound applies to preview and recipe PDF delivery, before mixture evaluation or tint-function construction. No spectral interaction, monitor calibration or press certification is inferred from the supplied model.

For PDF, export or publish with `format:"pdf"` and `pdf_options:{"ink_recipe":{"raster_scale":1}}`. The PDF 1.7 page contains a DeviceN image with exact independent ink samples named `Inkbolt.<id>`. A bounded Type 4 calculator tint function interpolates the declared 16-bit corners in linear RGB, applies sRGB encoding, and supplies an embedded sRGB ICC alternate. Its original arithmetic uses only constants, stack selection, addition, multiplication, division, exponentiation and one fixed transfer-curve branch; no file or external procedure execution is involved. Physical page size remains tied to document resolution. These public PDF constructs are described in the [PDF Association colour reference](https://pdfa.org/download-area/cheat-sheets/Color.pdf). A separation-capable reader can preserve actual named plates; a display reader can use the alternate appearance or its own colour-management policy. Display pixels across consumers are not universally identical.

This PDF mode delivers the whole recipe canvas. Combining it with calibrated process delivery, native vector paints, artboard selection, bleed or a document RGB output profile fails explicitly. Ordinary artwork, unrelated channels and its alpha do not implicitly enter recipe delivery. Conversely, ordinary PNG/SVG/PDF rendering ignores the nonprinting recipe. Use an explicit recipe mask for coverage, and retain the full snapshot for editable sources and history. For combined calibrated process/spot pages, use the separate explicit `print.named_inks` mode described in [COMBINED_PREPRESS.md](COMBINED_PREPRESS.md).

Canvas crop/extent/resampling operates on the saved source planes before applying curves. Extending the canvas pads scalar sources with zero; a curve mapping zero to full ink therefore produces full ink in that area unless an explicit mask is supplied. Internal standalone artboard views clear canvas auxiliary channels and the associated recipe. Item transfer leaves the destination recipe/channels unchanged and does not import a source document's global recipe. These are document-level resources, not item paint properties.

Snapshots, inspection, semantic diffs, atomic batches, persistent sessions, undo/redo and retry receipts retain recipes. Inspection and separation receipts identify the actual source and mask hashes. Public/strip PDF metadata policies and create-only publication share the ordinary engine contract. No command sends a print job. Use [recipe_workflow.py](../examples/recipe_workflow.py) for an original editable duotone chart, scalar plates, preview, PDF and a revised curve. The focused tests cover exact independent rational calculations, corner ordering, actual PDF streams, boundaries and agent history.

Independent synthetic charts cover one, two, three, five and eight inks, two sample densities, masked/unmasked curves and both appearance models. All 97,280 delivered ink values matched a separate PDF consumer exactly. Two independent display consumers matched the declared preview within one byte on those 40 charts; that observed bound is specific to the tested fixtures and consumer versions. A separate stack interpreter verifies the generated tint arithmetic against rational tensor weights. Research tools and detailed receipts remain external.
