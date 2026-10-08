# Reversible raster backgrounds

An agent can give a raster document an explicit opaque background while retaining
the original pixels, alpha, transform, masks, filters and effects of its base
layer. No source resource is rewritten. The snapshot stores an optional
`background: {"item_id":"base","matte":[30,80,150]}` record.

Use a `background` operation in `document.edit` or a session edit:

```json
{"op":"background","id":"base","action":{"type":"promote","matte":[30,80,150]}}
```

`promote` selects an unclipped root pixel/image/fill/text layer, isolated group or
frame and moves it to the bottom of the printable roots. There can be one
background. Replacing it removes the previous role, leaving its retained source
as an ordinary layer. Existing clipping chains must remain valid; an operation
that would separate a base from its followers fails atomically. Work paths and
shared nonprinting definitions can precede the background. Pass-through groups
and adjustment layers cannot be backgrounds.

The engine evaluates the source with its own appearance controls, composites it
over the specified RGB8 matte across the **current canvas**, then applies bound
adjustments and clipped sibling layers. Those siblings see an opaque base even
outside the original source grid. Source opacity zero leaves the matte visible;
turning off the layer's visibility suppresses the matte and its clipping group.
Erasing source pixels reveals the matte and retains editable transparency in the
source. Blend modes mix source color with the matte in encoded sRGB, using the
existing compositing contract. Layer geometry bounds continue to describe the
retained source; `document.inspect.background.canvas_bounds` reports matte extent.

Two explicit conversions serve different editing purposes:

```json
{"op":"background","id":"base","action":{"type":"restore_source"}}
```

`restore_source` removes the role and matte, recovering the current retained
source, including its alpha and appearance controls. It keeps the layer's current
stack position. Edits made to that source after promotion remain edits; this action
does not undo them. Use session undo to return to a historical source state.

```json
{"op":"background","id":"base","action":{"type":"to_layer","source_id":"retained","matte_id":"paper"}}
```

`to_layer` preserves the opaque appearance as an ordinary isolated named layer.
Its existing root identity, visibility, name and metadata remain stable. Two new
children use the caller's distinct unused IDs: a canvas-sized solid fill matte and
the retained original source. Source descendants follow that source child;
external clipping references continue to name the original root. The matte uses
the canvas size at conversion, so later canvas expansion can reveal transparency.
No pixels are flattened or resampled. Ordinary hierarchy and item limits apply.

Locks remain explicit. A locked background or locked descendant blocks conversion,
removal and edits affecting it. Replacing a background checks both old and new
subtrees. Duplication retains the copied source and its explicit lock state but
does not copy the document's background role; editing an unlocked duplicate leaves
the original unchanged. Cross-document transfer likewise copies ordinary sources.
Removing the background clears its role; dangling clipping references must be
removed or unlinked first. Reorder/reparent operations that violate the bottom-root
invariant fail atomically. Session undo, redo, retry receipts and document diffs
include the role.

PNG/JPEG/TIFF and render output include the completed matte. PDF includes it within
the existing supported normal-blend subset; PDF's other explicit restrictions still
apply. Snapshots retain the role and all sources. Artboard-only export excludes an
unrelated canvas background; it retains the role when the selected artboard itself
is the background. Shared artwork-mask evaluation never includes the canvas matte.
Vector documents do not accept this raster-only role.

Run `python examples/background_workflow.py --output NEW_DIRECTORY` for original
transparent pixels, a retained background, an edited duplicate, conversion and
source-restoration deliveries. Rational pixel equations, independent file readers,
lock/reference rejection and persistent-history checks are in
`tests/test_backgrounds_cli.py`.
