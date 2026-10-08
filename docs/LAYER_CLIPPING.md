# Layer clipping and group compositing

Raster items can declare `clip_to:"base-id"` to participate in a sibling clipping group. The base's transparency bounds the group; clipped layers change its color without increasing its alpha. This supports an image or texture inside a shaped region, stacked color treatments and editable overlays. Sources, masks, transforms and IDs remain independent. See the [original example](../examples/layer-clipping.json).

Use `{op:"layer_clip",id,clip_to}` as an edit operation, with null to release the relationship. Snapshot creation also accepts the optional item field. This item-level field is distinct from `content.adjustment.clip_to`, which binds a color adjustment to a drawable before its compositing. Both relationships persist in snapshots, MCP sessions and grouped undo/redo.

## Ordering and identity

A clipping group consists of one unclipped drawable base followed by zero or more clipped drawable siblings. Every clipped sibling names that same base. Nonprinting work paths and bound color adjustments can occur between them. An ordinary drawable, pass-through container or backdrop adjustment starts a new boundary. References cannot point forward, across parents, to another clipped member, to a nonprinting path, or to a backdrop-dependent container.

Pixel layers, placed images, procedural fills, text, isolated groups, frames and artboards can be bases or clipped members in raster documents. A pass-through group cannot serve as either, because its appearance depends on the surrounding backdrop rather than an independently defined alpha field. Vector documents retain geometric clips; item-level layer clipping currently rejects vector documents explicitly.

Changing a relationship honors locks on the changed item, its ancestors and affected descendants. A sibling base's lock does not prevent an independent overlay from changing the final composite. Deleting, reordering, reparenting or grouping items must leave valid relationships after each operation; an invalid edit aborts the complete batch. To restructure a chain, release its affected relationships, edit structure, then restore them within one atomic batch. Duplication of an owned group remaps internal base IDs; duplicate edits preserve the originals. A clipped container cannot be ungrouped while its clipping membership is active.

## Pixel equations and order

Rendering uses encoded-sRGB f64 premultiplied intermediates and one final straight-RGBA8 encoding. Each drawable first renders its content and filters, followed by its own contiguous bound adjustments. For the base this produces straight color `B` and alpha `A`. A clipped source supplies straight color `S` and effective alpha `w`, including source opacity, mask, vector clip and frame boundary.

For each clipped member, in stack order:

`B_new = (1-w)*B + w*blend(B,S)`; `A_new = A`.

The supported blend functions are normal (`S`), multiply (`B*S`) and screen (`B+S-B*S`). Zero-alpha base pixels remain transparent. The base's own opacity, mask, vector clip and frame boundary apply once after the entire clipping group has been assembled. Its blend mode then composites that complete result into the surrounding backdrop. This preserves translucent and antialiased base edges; multiplying the base alpha separately for each source would incorrectly darken them.

Bound adjustments immediately after a base affect that base before its clipped members. An adjustment following a clipped member binds to that member and operates before the member enters the clipping group. The same rule applies recursively inside an isolated container. Hiding the base suppresses its complete clipping group; hiding a member suppresses only that member. Discovery's effective visibility follows ancestor and clipping-base visibility flags, while bounds still describe unclipped geometry and visibility still does not measure actual nonzero alpha.

## Pass-through groups

Isolated groups render children against transparency and composite the result once. Pass-through groups (`isolated:false`) let child blends and backdrop adjustments see the surrounding backdrop. With pass-through group opacity, a grayscale mask or a geometric clip, Inkbolt retains the original backdrop `P`, evaluates the children to `Q`, and interpolates all four premultiplied channels as `P + weight*(Q-P)`. The weight is the group opacity times its enabled masks/clips. Outside that coverage, the original backdrop remains unchanged.

Group transforms position descendants and linked masks normally. Pass-through groups require normal group blending; child normal/multiply/screen modes remain available. Filters on pass-through groups still fail explicitly; use an isolated container for filters. Active group effects, clipping membership or isolation dependencies prevent appearance-losing ungrouping.

## Inspection, export and limits

`document.inspect`, `document.select` and `document.query` report `clip_to`; diffs identify changes to it and can compare final pixels. Standalone artboard export retains clipping relationships inside the owned subtree and removes only the selected root artboard's external clipping membership, just as it removes ancestor context. The original snapshot stays unchanged. Raster SVG export remains unsupported; PNG is the authoritative composite and snapshots retain editable relationships.

The 256-item, 16-ancestor, pixel/work and snapshot limits still apply. The render budget includes buffers held while a clipped source or effectful pass-through group is evaluated. With maximum buffered-container depth `d`, the base estimate is `d+2` full RGBA intermediates; documents containing layer clipping add `d+1`, plus the existing text/filter scratch allowances. This conservative estimate can reject a large document before allocation. No new dependency, format, network service or external resource mutation is involved.

Independent tests check every output pixel against rational alpha/blend equations, verify nested transformed boundaries, preserve filtered/antialiased alpha, exercise group isolation and backdrop adjustment interpolation, and verify references, visibility, duplication, artboards, sessions, locks and failure limits.
