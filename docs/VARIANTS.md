# Editable dataset variants

One vector or raster document can retain typed data rows that control selected item properties. An agent can generate label/image alternatives, show or hide elements, reposition layers and export each result without losing the base artwork. Values are data, not scripts, expressions, file paths or network references.

## Define, select and export

Use `document.edit` with `variants_set` to capture current values for declared bindings and save named datasets:

```json
{
  "op": "variants_set",
  "definition": {
    "bindings": [
      {"key":"placement","item_id":"tile","property":"position"},
      {"key":"show_badge","item_id":"badge","property":"visible"}
    ],
    "datasets": {
      "wide": {"values":{"placement":{"type":"position","value":[20,10]}}},
      "quiet": {"parent":"wide","values":{"show_badge":{"type":"visible","value":false}}}
    }
  }
}
```

`{"op":"variant_select","dataset":"quiet"}` applies the resolved row. A null `dataset` restores captured base properties. Each selection starts from the captured values, then applies parent data from oldest to newest and finally child values. It never accumulates the previous selection's values. Missing keys inherit; unknown keys, missing parents, cycles and wrong types fail. One key may control several targets of the same property type.

Selection returns binding-to-value mappings, the selected name and changed item IDs. Ordinary inspection exposes the entire saved variant state. Normal item inspection, queries and render/export commands see the selected properties, including visibility, world bounds and text/image identity. Diff records both item changes and variant metadata changes. Export each selected snapshot through `document.export` or create-only `document.publish`; existing files cannot be overwritten. Artboard exports use the selected row.

## Controlled properties

Each value is `{"type":"property-name","value":...}` and must match its binding's `property`:

| Property | Value | Controlled subset |
| --- | --- | --- |
| name | String | Item name; duplicate names remain allowed |
| visible | Boolean | Own visibility, with normal ancestor behavior |
| opacity | Number in 0..1 | Overall opacity |
| fill_opacity | Number in 0..1 | Content fill opacity |
| position | Two finite coordinates | Local affine translation; existing scale/rotation/shear stay intact |
| transform | Six finite affine values | Complete local transform; existing matrix limits apply |
| text | `{text,ranges}` | Editable text and character style ranges; omitted ranges are empty |
| image | Asset ID | Pinned image binding; frame, crop and sampling stay intact |

Text bindings require text items. Their value retains the full string and optional ordinary `{start,end,style}` character ranges, including explicit font IDs. Frame size, base style, wrapping and other layout controls remain separate. Existing font coverage, glyph, overflow and layout restrictions still apply; no automatic font fallback is implied. Image bindings require placed images and existing document asset descriptors. A different image must still support the retained crop. Import resources explicitly before defining rows. Variant values cannot read external paths.

## Base preservation and editing

Snapshots retain `variants: {definition,base,selected}`. The `base` array stores only controlled properties, in binding order. Source geometry, pixels, resources and unrelated fields remain ordinary editable state. Switching restores those captured subsets and preserves unrelated edits made since the definition was created. In particular, a position binding leaves later scale/rotation edits intact. An ordinary duplicate is independent; it is not automatically added to the original's bindings.

Direct edits that change a controlled value fail with `VARIANT_CONTROLLED`. Revise the definition or clear it first. Replacing a definition with `variants_set` restores the old captured properties, captures the new bindings and selects the base. `{"op":"variants_clear"}` restores the base and removes metadata. `{"op":"variants_clear","bake":true}` retains current artwork and removes variant controls. Neither changes original input files. These are atomic operations with normal revision checks, undo/redo and durable retry receipts.

The stored artwork must match its selected row; inconsistent hand-edited snapshots fail validation. Duplicate bindings to the same property are rejected, as are simultaneous position and transform bindings on one item. Missing bound items prevent deletion; clear/redefine bindings first. Changed items honor own, ancestor, descendant and shared-component/mask locks. Selecting a row that leaves a locked property unchanged is permitted. Baking only removes metadata and preserves locks and pixels.

Inactive data rows keep their image and text-range font references alive. Resource removal rejects those references; resource replacement honors the referencing item locks. Every row, inherited row and captured baseline receives full structural validation, including inactive values and source dimensions. Actual external resource bytes and text layout are verified when the selected document is rendered or exported using explicit resource roots. Missing files fail with existing resource errors; no substitution occurs.

## Persistence, export and limits

Snapshots and sessions retain editable definitions, inherited values, the captured base and selected row. PNG/SVG contain only the selected result and report that loss explicitly. Artifact and publication receipts include the selected name and SHA-256 of the complete variant state for reproducible mapping. SVG also retains its existing text/component and appearance losses. Temporary board/mask/component export views strip variant metadata after validating the complete document; source snapshots remain intact.

Definitions have 1..64 bindings and 1..32 datasets, with at most eight inheritance levels. Keys, dataset names and target IDs use normal portable ID syntax. The whole snapshot remains within 768 KiB, and every resolved row must satisfy all existing document, geometry, mask and component limits. Unknown properties and executable expressions are unsupported. Dataset switching is bounded synchronous work within the existing atomic batch cancellation boundary; no background task or network service is added.

Run `python examples/variant_workflow.py --output <new-absolute-directory>` for original vector/raster layouts, inherited and independent rows, snapshots, image exports and change receipts.
