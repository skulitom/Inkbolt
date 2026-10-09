# Versioned document presets

`preset.list` lists the fixed version-1 recipes. `preset.create` returns a new
editable document, its artboard parent ID and explicit preview/delivery settings.
Both commands are pure: they write no files, create no sessions and modify no
existing documents. CLI, library and both MCP catalogs share the same types and
validation. In the compact MCP catalog, call them through `inkbolt_run`; discover
their focused schema with `schema.lookup` and `name:"preset.create"`.

```json
{"command":"preset.create","version":1,"id":"cover","preset":{"type":"screen","size":"presentation_hd","kind":"vector","background":{"type":"transparent"}}}
```

The required version pins the recipe's dimensions, policies and defaults.
Unsupported versions and unknown fields fail. The response includes the fully
defaulted specification and its SHA-256, plus the initial document's SHA-256.
The specification hash covers compact, sorted-key JSON of `specification`; the
document hash covers the engine's typed serialization. These identify returned
values, not a signature or a lock on future edits. Retain the specification and
delivery settings alongside the editable source.

## Screen artwork

| Size | Pixels |
| --- | --- |
| `icon256` | 256 x 256 |
| `presentation_hd` | 1920 x 1080 |
| `presentation_qhd` | 2560 x 1440 |
| `social_square` | 1080 x 1080 |
| `social_portrait` | 1080 x 1350 |
| `social_story` | 1080 x 1920 |

These are project-owned geometric choices, not promises about any external
service's current upload requirements. Choose `kind:"vector"` or `"raster"`
and an explicit background: `{"type":"transparent"}` or
`{"type":"solid","color":[255,255,255]}`. The background remains an editable
artboard property. Screen documents use sRGB, 96 PPI and an artboard called
`canvas`. Set new content's `parent` to the returned `content_parent_id` so it
belongs to independent artboard delivery.

The delivery is straight-alpha RGBA8 PNG at scale 1, using bounded tiled coverage
evaluation and stripped descriptive metadata. Sources keep their descriptions
and private metadata. Solid backgrounds are artwork, not a hidden export matte.
Default resource storage is `standard`; an explicit `resource_profile` must
match the chosen kind. Creating a raster preset does not allocate a full pixel
grid or import a photograph; use native block imports for large pixel sources.

## Physical print pages

```json
{"command":"preset.create","version":1,"id":"page","preset":{"type":"print_page","paper":"a4","orientation":"portrait","resolution_ppi":300,"color":"display_rgb","bleed_px":{"top":36,"right":36,"bottom":36,"left":36}}}
```

Paper choices are `a4` (210 x 297 mm), `a5` (148 x 210 mm) and `letter`
(8.5 x 11 inches). Orientation and resolution are explicit; supported resolutions
are 72, 96, 150 and 300 PPI. The vector document and `page` artboard retain the
fractional logical trim size. Only preview storage dimensions use its ceiling;
PDF physical size does not change with that rounding or with resolution.

Bleed defaults to zero. `bleed_px` uses existing integer logical pixels per edge,
at the chosen resolution. For example 36 pixels at 300 PPI is **3.048 mm**, not
3 mm. The response reports exact requested trim units and binary64 bleed sizes
in inches, ordered top/right/bottom/left. No millimetre bleed is silently rounded.
Place bleed artwork beyond the artboard's trim edges while keeping its parent
set to `page`. The returned PDF settings select that artboard and include bleed
when any edge is nonzero. The preview selects trim only.

Choose `display_rgb` for ordinary RGB appearance PDF, or `native_inks` for
retained process/named ink declarations and a CMYK logical page. Neither option
chooses a printer profile, asserts calibrated output, embeds fonts or guarantees
print-shop acceptance. Native-ink pages return `preview:null`: use
`document.prepress` with an explicit supplied profile to inspect calibrated
plates. For profile-bound print delivery, configure the existing
[print](PRINT_CMYK.md) or [native prepress](VECTOR_PLATES.md) settings explicitly.
All existing PDF losses and unsupported semantics remain in effect.

## Agent workflow

1. Discover a recipe and create it with a supported version and explicit policies.
2. Save `document` with `session.create`, using compact responses.
3. Inspect and add artwork under `content_parent_id`. Preserve stable object IDs.
4. Use `session.dry_run` on the expected revision; review its proposal and mapped
   preview. For large documents, use the returned tiled `preview` options with
   `document.preview`, or a focused region. A default dry-run preview still has
   the ordinary whole-render limit.
5. Apply with `session.apply_proposal`. Retain the request ID and proposal so a
   lost response can be retried without repeating the edit.
6. Add `output_root` and a fresh `file_name` to `delivery` and preflight the pinned
   edited revision. Workspace defaults can supply `output_root`. The returned
   settings are valid publication fields; do not send `artboard_id` or
   `include_bleed` as ordinary `document.export` fields.
7. Publish through `session.publish` or `document.publish`, optionally with a
   durable receipt. Save an editable snapshot separately and verify history.

Presets do not guarantee that later edits fit rendering/export budgets, meet
every delivery requirement or stay within the original trim. Preflight the
actual edited revision; unsupported operators continue to fail explicitly.
Publication remains create-only. Default policies are fixed by recipe version,
but byte-identical rendering across different engine builds is not promised.

Run [the original workflow](../examples/preset_workflow.py) to create reviewed
screen artwork and a physical print page, save editable sources and demonstrate
durable edit retry and publication receipts. It requires a new absolute output
directory; an interrupted example may leave completed outputs in that directory.
It is a scripted contract example, not an autonomous model benchmark.

Independent tests verify all physical paper/orientation/resolution combinations,
asymmetric PDF boxes, exact alpha/background pixels, native CMYK declarations,
CLI/MCP parity, validation, history, retries and create-only output. This advances
A7; it awards none of the six original unfinished engine checkpoints.
