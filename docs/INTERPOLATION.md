# Editable object interpolation

An interpolation item retains two original vector endpoints and generates an explicit number of steps for icons, diagrams and shape/color progressions. It is an isolated leaf in the saved hierarchy:

```json
{"id":"sequence","content":{"type":"interpolation","interpolation":{
  "from":{"geometry":{"shape":"rect","x":4,"y":8,"width":4,"height":4},"fill":[240,40,20,255]},
  "to":{"geometry":{"shape":"rect","x":52,"y":20,"width":12,"height":8},"fill":[20,80,240,255]},
  "count":5
}}}
```

`count` includes both endpoints and must be 2..128. Step `i` uses fraction `i/(count-1)`. Order is source to destination, with later steps above earlier ones. Parent transforms, opacity, clipping, masks, effects and blend mode apply to the isolated sequence. Shared components and nonprinting mask sources can contain sequences; ordinary printable raster layers cannot.

## Endpoints and paint

Each endpoint has `geometry`, optional solid RGBA8 `fill`, optional `stroke`, `opacity` (default 1) and optional `anchor`. Coordinates are local to the interpolation item. Default anchors are analytic geometry-bounds centers, excluding stroke. Without a spine, centers follow the straight line between these anchors. Shapes are interpolated relative to their anchors.

Fills and stroke colors interpolate premultiplied color and alpha, in `space:"srgb"` (default) or `"linear_rgb"`, then encode once to RGBA8. Zero-alpha intermediate colors have zero RGB. Original endpoint colors, including hidden RGB, remain exact. A missing fill/stroke fades to or from transparency and is absent at its endpoint. Endpoint opacity interpolates separately.

Stroke widths interpolate linearly. Two present strokes must have identical controls apart from width and solid color. This includes matching dash, width-profile, arrow, brush and scaling settings. A missing stroke uses the other's width and style while fading its color alpha. Other paints or differing controls fail explicitly; agents can first expand painted strokes into their own filled endpoint geometry. This API accepts vector geometry endpoints, not arbitrary layer/text/image objects.

## Different topology and explicit correspondence

Primitives expand to lines/cubics for intermediate geometry. Each contour has equal parameter spans per authored segment. Correspondence uses the union of both contours' segment-boundary fractions, exact polynomial subdivision and linear interpolation of corresponding controls. A line remains a line when matched to another line; cubic controls remain editable. This is segment-based correspondence, not arc-length resampling of endpoint shapes.

Contours pair by index by default. An unmatched contour collapses to, or grows from, its own control-hull center relative to its endpoint anchor. An open/closed mismatch becomes separate collapse and grow pairs. Optional `contours` entries `{"from":0,"to":1,"to_start":2}` let agents reorder correspondence and rotate a closed destination's seam by segment index. Every contour must appear exactly once; an unmatched side is `null`. Open and closed contours cannot be directly paired.

Authored winding is preserved; `fill_rule` is `"nonzero"` by default or `"even_odd"`. Intermediate geometry can cross or collapse according to the chosen correspondence. No automatic winding correction or topological equivalence is promised. Exact source geometry is retained at the endpoint steps, with a rigid placement applied only when needed by position/orientation.

## Curved spines, orientation and reversal

Optional `spine` contains one-contour `geometry`, `start`/`end` fractions (defaults 0/1; `0 <= start < end <= 1`), `reverse` (default false), `normal_offset` (default 0) and `tolerance` (default .001, allowed .000001..=.25). All distances use item-local coordinates. Original bounded cubic measurement supplies equal-distance samples along the selected span. Primitive spines use their ordinary line/cubic expansion.

`orientation:"fixed"` preserves authored axes. `"tangent"` rotates local +x to the traversal tangent. Normal offset follows the left normal of traversal, so reversing the spine also reverses the normal side. At a segment join, the shared distance table chooses the outgoing nonzero segment; the final endpoint uses the terminal incoming tangent.

`reverse_order:true` reverses the shape/color/opacity sequence while leaving the chosen positions in order. It is independent of `spine.reverse`. Closed spines include both endpoints, which may coincide; use an explicit subspan to omit a repeated seam position. A collapsed spine or undefined tangent fails explicitly.

`interpolation.inspect` takes `interpolation`, optional `include_geometry` and optional `control`. It returns centers, tangents, endpoint anchors, fractions, colors, strokes, bounds and the spine length interval/measurement report. The report's position bound concerns the baseline; normal offset and rotated geometry also depend on tangent error. The API does not claim a global angular error bound. Bounds exclude strokes and clipping.

## Editing, persistence and delivery

Use `{"op":"interpolation","id":"sequence","interpolation":{...}}` to replace controls. `document.inspect` returns saved controls and `document.query` accepts type `"interpolation"`. Snapshots, transferred subtrees and durable sessions retain the full specification. Existing lock, dependency-lock, atomic batch, revision, retry, restart and history rules apply.

`{"op":"interpolation_expand","id":"sequence"}` replaces the item with an isolated group retaining its appearance and inserts ordinary editable vector children. Stable child IDs avoid existing IDs. The receipt lists created IDs; the input snapshot remains unchanged. Rendering, SVG and expansion share generated geometry. SVG reports loss of interpolation controls, while snapshots preserve them. Artboard delivery includes generated work in its preflight limits.

## Bounds and verification

Stored endpoints, stroke motifs and spines join the 4096 document-command limit. Matching is limited to 4096 commands, and generated intermediate commands are bounded before generation. The fully materialized document must satisfy ordinary geometry, stroke, pixel/work, hierarchy and 256-item limits, including invisible sources. A spine has at most 1024 expanded commands and 32768 measurement leaves; interpolation spines share 65536 leaves per evaluated document. Existing placed component/mask and artboard limits also apply. Up to 512 explicit contour pairs are accepted. Cancellation/deadline checks surround bounded inspection and participate in existing edit/publication boundaries.

Twenty original CLI/MCP tests cover rational correspondence, exact split cubic controls, premultiplied colors, analytic pixels, independent numerical arc integration, reversal/orientation, unequal topology, seam edits, strokes, hierarchy/effects, components/masks, transfers, durable edits, SVG/artboards and strict/resource failures. A Rust library test exercises nonfinite controls and coordinate overflow. The original example and separate image/SVG consumers provide retained delivery evidence.
