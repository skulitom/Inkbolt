# Artboards over shared artwork

Set `frame.scope:"scene"` on a vector artboard to export a rectangular view of
one shared layer tree. Objects can cross several artboards while retaining one
identity, hierarchy and editable geometry. A layer visibility or path edit affects
every view that contains it. The default `scope:"subtree"` retains the existing
owned-child contract and is omitted from serialized snapshots for compatibility.

```json
{
  "id": "detail",
  "name": "Detail",
  "transform": [1, 0, 0, 1, 160, 32],
  "content": {
    "type": "frame",
    "frame": {"role": "artboard", "scope": "scene", "width": 64, "height": 64}
  }
}
```

Scene artboards are root-level viewport markers with no owned children or
background. They require translation-only placement, visibility, full opacity,
normal blending and no clip, mask, effect, filter or other appearance modifier.
Unsupported placement fails explicitly. Names, locks, guides, bleed and optional
fractional `logical_size` work as ordinary saved frame attributes. Moving,
resizing, duplicating or deleting a view never moves or duplicates its artwork.
Place background artwork in the shared layer tree when needed.

PNG/image exports, SVG, PDF pages, publication and focused previews use the same
standalone view. Export preparation copies and translates the shared artwork into
local coordinates, rebases unlinked document masks and removes scene artboard
markers. Layer visibility, compositing and hierarchy remain intact. The source
snapshot and resources are unchanged. Bleed extends the requested rectangle;
canvas origin and dimensions do not crop artwork before the view is prepared.
Viewport filters evaluate in each output viewport, as in existing artboard exports.

Scene and subtree artboards may coexist. Selection preserves existing ID/range
ordering. Each `artboard.export` artifact declares its `scope`; mixed or scene
requests report `artboard_per_item_local`. Other owned artboards remain ordinary
clipped artwork when seen through a scene view. A scene view prepares the entire
shared scene, including off-view resources, under the existing per-output and
aggregate work, pixel and byte limits. Missing resources and unsupported delivery
semantics fail the whole request before publication. There is no spatial resource
pruning or incremental-render guarantee.

Independent tests check crossing artwork, exact rectangle pixels, bleed,
fractional coverage, shared edits, mask placement, preview coordinate maps,
PDF path coordinates, SVG hierarchy, mixed scopes, saved retries/undo and range
budgets. This shared-artwork model supports the native interchange work; native
file import, editable native delivery and the original interchange acceptance
criteria remain unfinished.
