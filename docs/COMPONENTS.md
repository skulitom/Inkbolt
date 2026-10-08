# Reusable components

Vector documents can store one editable definition and place it repeatedly. A top-level item with `content: {"type":"component_source"}` owns ordinary child items and never prints directly. Each copy uses `content: {"type":"instance","instance":{"source":"definition-id","overrides":{}}}`. Its normal parent, affine transform, opacity, clips, masks, effects and blending apply to an isolated copy of the source hierarchy. The source root is also an isolated boundary, retaining its own appearance and transform. Changing the original child geometry updates all copies that have not replaced that content.

Definitions use global stable item IDs. Instances own no stored children; their evaluated children are private to rendering. Source definitions may contain nested instances, ordinary frames, geometry, text, images and any content permitted by the existing vector document contract. Artboards cannot belong to a definition or be introduced through an override. Raster documents and imported SVG `use` elements remain unsupported by this component API.

## Local variants and replacement

`overrides` maps IDs owned directly by the definition's stored subtree to optional `name`, `visible`, `opacity`, `fill_opacity`, `blend`, `transform`, `content` and `vector_style` properties. Nested definition children require an override on the nested instance's content with its own source/override map. Unknown target IDs and unknown fields fail. An omitted property follows the source; a transform replaces the source item's local transform.

`vector_style` has `fill`, `stroke` and optional `fill_rule`. When present, omitted/null fill and stroke clear those paints; an omitted fill rule retains the original. Geometry continues following source edits. Whole `content` overrides replace the source content and remain subject to normal hierarchy, resource and document validation. Resource-root replacement is forbidden. Scalar overrides on the source root are allowed. Override IDs must also exist when replacing the source definition; clearing the override map is explicit by omission or `{}` in the new binding.

Use ordinary `add`, geometry, text and property edits to construct and revise definitions. `{"op":"instance","id":"copy-id","instance":{"source":"other-definition","overrides":{}}}` replaces an existing instance binding and its entire override map. Ordinary duplication preserves sharing. Referenced definitions and overridden items cannot be removed while their references remain. Source, nested source, font, image and shared-mask changes honor dependent artwork locks, including locked groups. Failed operations leave the input snapshot unchanged.

## Unlink, masks and persistence

`{"op":"instance_unlink","id":"copy-id"}` turns that instance into an isolated group with independent editable children, recursively expanding nested references. The existing instance ID, parent and appearance survive. Generated IDs are deterministic hashes of placement/source identity with explicit collision avoidance. The operation reports `source`, `created_ids`, `unlinked` and `source_preserved`. Definitions remain available to other copies. Ordinary limits apply to the entire resulting stored document; an expansion that exceeds them fails atomically.

Linked masks keep item-local coordinates. Unlinked grid, filter and artwork masks stored inside a definition use the enclosing definition's coordinate space and are rebased independently for each placement. After unlinking, they use ordinary document-space semantics: current output is preserved, while later movement behaves like any other unlinked mask. Artboard extraction preserves these coordinate rules and retains transitive definitions and mask sources. Components placed inside an artwork-mask source must satisfy that source's narrower content/appearance restrictions after expansion.

Snapshots, sessions, undo/redo and retry receipts retain definitions, overrides and unlink results. Inspection reports instance bindings and a `component_source_sha256`; diffs flag definition-driven changes even when an instance's stored fields did not change. This conservative fingerprint includes transitive definition/mask items, global lighting and the document's asset/font dictionaries. Artwork-mask fingerprints include nested component resources and font descriptors. Fingerprints describe dependencies, not pixel equality; use rendered comparisons when needed.

PNG uses evaluated copies. SVG emits independent expanded groups and explicitly reports the loss of sharing and overrides, alongside any other existing export losses or unsupported semantics. Retain the snapshot for future shared edits. Publication remains create-only and leaves input files intact.

## Bounds and limits

Geometry bounds use evaluated nested transforms and exclude strokes/clipping as elsewhere in the engine. Sources themselves have no printing bounds. Type queries accept `component_source` and `instance`; source children remain discoverable and effectively invisible.

At most 32 definitions and eight nested definition references are allowed. Cycles, missing references, invalid overrides and invalid unused definitions fail explicitly. Both stored and expanded views must fit existing 256-item, 4096-source-command, 768-KiB snapshot, coordinate and appearance limits. Validation checks each unused definition together with shared mask resources conservatively. All render, text, filter, stroke and artboard work budgets still apply to evaluated copies; hidden instances do not bypass these checks.

Run `python examples/component_workflow.py --output <new-absolute-directory>` for original repeated icons with a shared geometry edit, a local color variant, one detached copy, PNG/SVG/snapshot exports and change receipts.
