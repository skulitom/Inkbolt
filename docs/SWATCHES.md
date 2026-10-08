# Named colors and spot tints

Explicit `device` declarations additionally retain source profiles and intent, with profile assignment/conversion edits, source-component tints and exact ICCBased native PDF delivery. See [DEVICE_COLOR.md](DEVICE_COLOR.md). The legacy declarations below retain their existing preview rules.

`document.swatches` retains named process colors, spot-color declarations and reusable tints. Paints refer to stable IDs. Editing a definition updates its live users without rewriting their geometry, source pixels or text. Names are labels and can repeat; distinct IDs remain distinct resources. Snapshots, atomic batches and durable sessions preserve the declarations, references and original numeric values.

```json
{
  "swatches": {
    "accent": {"name":"Accent","definition":{"type":"process","color":{"space":"srgb","components":[0.125,0.5,0.875]}}},
    "ink": {"name":"Original warm ink","definition":{"type":"spot","alternate":{"space":"srgb","components":[0.75,0.25,0.125]}}},
    "pale": {"name":"Pale ink","definition":{"type":"tint","base":"ink","tint":0.25}}
  }
}
```

This object is part of a valid schema-v2 document. A swatch ID follows the ordinary portable ID rules. The name contains 1..256 UTF-8 bytes without control or invalid XML characters. A document holds at most 256 definitions; a reference chain contains at most eight definitions including its base. Missing references, cycles, nonfinite/out-of-range values and excessive chains fail explicitly. Schema-v1 documents cannot contain swatches.

## Declared color values

| Space | Stored values | Display interpretation |
| --- | --- | --- |
| `srgb` | `components:[r,g,b]`, each 0..1 | Encoded sRGB |
| `gray` | `component:g`, 0..1 | Encoded sRGB neutral `[g,g,g]` |
| `cmyk` | `components:[c,m,y,k]`, each 0..1 | Requires a separate, explicit `preview_srgb:[r,g,b]` for display |
| `lab` | D50 `components:[L,a,b]`, L in 0..100 and a/b in -128..127 | Requires a separate, explicit `preview_srgb:[r,g,b]` for display |

Process definitions contain `color`; spot definitions contain an `alternate` using the same declaration shape. A spot's stable base swatch ID is its ink identity. Tint definitions retain a base ID and a 0..1 amount, and can refer to process colors or spots through other tints. Every supplied finite binary64 component and tint persists unchanged; inspection and previews never replace the original declaration with RGB values.

CMYK and Lab declarations can be saved, inspected, copied and reopened without a preview. Rendering a paint that depends on one requires its caller-supplied preview; otherwise it returns `SWATCH_PREVIEW_REQUIRED`. Supplying a preview is an explicit display choice, not profile conversion or a print proof. ICC-driven process conversion, plate generation and extended prepress use the explicit native path in [VECTOR_PLATES.md](VECTOR_PLATES.md); ordinary RGB previews retain the requirements above. Native PDF ink/overprint delivery is described in [INK_DELIVERY.md](INK_DELIVERY.md). These declarations do not change the document's encoded-sRGB working space or image depth.

## Referenced paints and edits

```json
{"swatch":"pale","tint":0.5,"opacity":0.75}
```

Use this wherever the current model accepts a `Paint`: vector fill/stroke, text style/range, procedural raster fill, repeated or warped artwork, component style/content overrides and layer-effect color. Defaults are tint 1 and opacity 1. Fixed byte-color fields such as gradient stops, mesh knot colors, frame backgrounds and interpolation endpoint fills retain their existing schemas. Interpolation endpoint strokes still require their documented literal byte colors. Standalone repeat/warp inspection has no document palette; use document-level inspection for artwork containing references.

For display, multiply the retained tint chain and the paint tint to get T. Each encoded-sRGB channel is `1 + T * (alternate - 1)`; opacity remains an independent alpha. Zero tint is opaque white at opacity 1. These are defined display samples, not simulated ink mixing. Computation uses binary64 through compositing; final image delivery rounds to RGBA8 under the existing renderer. A literal `{"rgba":[r,g,b,a]}` also represents a precise normalized solid paint without early byte quantization. Existing four-byte solid paints remain unchanged. Output RGB profiles, sampling and image compression follow their existing downstream contracts.

```json
{"op":"swatch","id":"ink","swatch":{"name":"Cool ink","definition":{"type":"spot","alternate":{"space":"srgb","components":[0.125,0.75,0.5]}}}}
```

The `swatch` edit inserts or replaces a definition. A null `swatch` removes an unused definition; live paint references, tint aliases and saved variant values prevent removal. Changing a definition checks locks on affected items, their ancestors and dependent components/masks, including inactive saved variant styles. References remain attached to their stable IDs. Receipts retain before/after definitions and directly affected items. Changes participate in atomic rollback, revision conflicts, undo/redo and retry receipts.

`swatch.inspect` returns declarations, base/spot identity, effective tint, dependency IDs, available display RGBA, direct users, saved-variant users and a deterministic palette hash. `document.inspect` includes this inventory. Structural diffs report changed swatch resources and conservative transitive hashes on affected scene items; these hashes can include shared definitions shadowed by an instance override. They are dependency evidence, not a guarantee that every reported item's visible pixels changed.

Subtree duplication retains references to the same document palette. Cross-document transfer copies only used swatches and their transitive tint bases, assigns independent IDs with the existing prefix rule and rewrites every copied reference. Color names, values and tint amounts are retained. Later edits in either document remain independent. Transfer collisions and dependency failures leave both inputs intact.

## Delivery and explicit preview baking

Snapshots preserve complete swatch and tint semantics. PNG/JPEG/TIFF previews report referenced IDs and explicit losses: they deliver display samples, not named ink plates. Process-sRGB and encoded-gray SVG/PDF delivery uses precise numeric paints and reports loss of global references. Display SVG/PDF reject used spot or non-RGB declarations even when a display preview is available. Explicit native PDF delivery retains those ink operands; see [INK_DELIVERY.md](INK_DELIVERY.md). Unused palette definitions do not prevent vector delivery.

```json
{"op":"swatch_bake","ids":["card","badge"]}
```

Run this on an explicit document copy when display-only SVG/PDF is intended. It replaces named paints in the selected items and owned descendants with precise display-RGBA literals, removes overprint controls without simulating them, preserves the palette and returns a loss receipt. It respects locks and fails before publication if a preview is missing. Shared definitions outside the selection and inactive variant values remain live. Unlink an instance before baking that independent placement, or explicitly select its shared definition to change all its users. Baking a placement alone does not silently bake its shared source. The original snapshot and undo history retain the editable references.

Export receipts retain display diagnostics, including through artboard delivery and session publication. Create-only publication preserves existing destinations. No spot conversion, overprint, separation or native-format interchange checkpoint is implied by preview output.

The [original swatch workflow](../examples/swatch_workflow.py) saves exact declarations, recolors shared spot tints, publishes before/after previews and explicitly bakes a copy for SVG/PDF. `tests/test_swatches_cli.py` checks independent rational tint pixels, precise persistence, native-value retention, masks, strokes, effects, repeated artwork, components, text/variants, transfer, errors, locks and durable agent history.

Shared story body/range/list styles participate in named paints; inserted hyphens inherit source style. Inspection reports `story_users`, including unplaced retained resources. These resources guard color deletion; placed bindings propagate locks and hashes through components/masks. Native PDF and preview diagnostics include bound story paints. Baking selected bindings clones their complete story when other bindings stay live, or bakes the single source in place when all direct bindings are selected. Transfer remaps story paints and tint closure. See [STORIES.md](STORIES.md).
