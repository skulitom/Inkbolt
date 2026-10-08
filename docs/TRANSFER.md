# Transfer artwork between documents

The atomic `transfer` edit copies selected source subtrees into the destination snapshot, including the ancestor containers and transitive references needed to keep them structurally valid. It supports ordinary vector and raster document contents within their existing kind constraints. Both source and destination inputs remain unchanged; the returned document is the result. The same operation is available through CLI edits, MCP and durable session batches.

```json
{
  "op": "transfer",
  "transfer": {
    "source": {"...": "complete source snapshot"},
    "ids": ["library-layer"],
    "prefix": "imported",
    "parent": null,
    "verify_resources": false
  }
}
```

Use the generated request schema for a complete typed snapshot. `ids` contains 1..256 distinct existing source IDs. Selecting both an ancestor and a descendant copies that subtree only once. The source is validated before traversal, including inactive variant rows and reusable definitions. Unsupported cross-kind content fails normal document validation; it is never rasterized or converted implicitly.

## Identity and hierarchy

Every copied item retains its name, content and settings. Duplicate names are allowed; IDs identify objects. Copied IDs are `prefix-source_id`. The prefix uses 1..32 valid ID characters. If that combination would exceed 128 characters, the suffix becomes the lowercase SHA-256 of the source ID. Any collision with an existing or generated destination ID fails the whole batch with `ID_CONFLICT`; existing objects are never replaced. Image and font dictionaries use separate namespaces and the same mapping rule.

Selected subtrees keep source sibling order. Only their ancestor containers are added, without unrelated siblings, unless a dependency requires them. Closure includes component definitions, nested component replacement content, mask sources, clipped-layer bases and bound-adjustment bases. All copied parent/reference IDs and component override keys are remapped together. Receipts report the complete maps and any source IDs included as context rather than explicitly owned selections.

Ordinary copied roots append at the destination top level or beneath the optional `parent`. The parent's inverse world matrix adjusts those root transforms to retain source world coordinates. Resource definitions remain top-level, retain definition coordinates and keep sharing among the transferred placements. Each transfer creates independent definitions; editing one imported copy does not edit another transfer or its source. Existing dependency locks and reference validation prevent deleting definitions or overridden children while references remain. Removing a complete independent hierarchy is an ordinary atomic edit.

Source locks do not prevent a read-only copy and are retained in the result. A locked destination parent, ancestor or dependent instance prevents transfer into that container. Source and destination coordinate, item, path, resource, nesting and snapshot limits still apply; an inverse placement that cannot fit stored coordinates fails explicitly.

## Resources and document context

Only image/font descriptors used by the copied content are imported, including text style ranges and nested component replacement content. Unused source dictionaries and inactive source dataset references are not imported. Original image identities, crops, font faces, provenance and license identities persist. Embedded image bytes stay embedded; stored bytes remain in their content-addressed external stores. This edit performs no file copying or publication.

By default `verify_resources:false` has the same structural contract as ordinary snapshot edits. To verify imported external bytes before accepting the transfer, set it to true and supply the destination edit's `asset_root` and `font_root` (or the session's stored bindings). Missing, corrupt or differently bound bytes fail with the new destination resource ID. The caller must use stores containing the required immutable blobs; existing import commands can prepare stores from explicitly provided original files. Render/export always performs its normal resource checks. No system-font fallback, path guessing or network access occurs.

Source-selected variant values are copied as ordinary editable values. Dataset definitions, captured base values, canvas settings, pixel selection, channels and resolution stay with the source. Destination datasets and canvas state remain unchanged. The receipt names the source's selected dataset and discloses these boundaries. Full variant-library transfer is separate from artwork transfer.

Global source light directions are pinned as explicit local azimuths on copied shared-light shadow effects, including hidden effects and reusable definitions. The destination's global light stays unchanged. Later destination global-light edits therefore do not unexpectedly alter these imported directions; effects remain editable.

The destination viewport, backdrop and parent appearance govern compositing. Copying a selection cannot promise the appearance contributed by omitted siblings, a different background, canvas edges, or a destination parent's clips and opacity. Source hierarchy and coordinates are preserved, including linked/unlinked masks and editable artboard guides. Independent artboard export keeps its established local-viewport contract.

## Receipts, persistence and verification

Each edit receipt includes source document ID/revision, a SHA-256 of its typed JSON serialized with sorted object keys, selected IDs, included context, item/asset/font maps, pinned light bindings and resource-verification status. It contains no runtime resource paths. The source hash identifies the supplied normalized snapshot, rather than the formatting of an original JSON file.

Edits remain all-or-nothing, with expected-revision checks and cooperative batch cancellation. Session history retains the copied document and complete change receipt; undo/redo and safe retries use the existing durable contract. Request and snapshot byte limits remain unchanged. An oversized transfer fails explicitly rather than dropping artwork.

`tests/test_transfer_cli.py` verifies exact nested-layer pixels, duplicate names, independent rational affine placement, reference closure and remapping, masks/artboards, original font/image bytes, resource and ID conflicts, safe deletion, dependency locks, variants, lighting, limits and persistent MCP history. `examples/transfer_workflow.py` publishes an original reusable icon library and two independent placements, then edits one imported mark while preserving the source.

Output color profiles belong to document context. Artwork transfer retains the destination output_profile and its working-sRGB artwork values; a source output-profile association is not copied. Image import provenance and source-profile hashes remain attached to copied asset descriptors.
