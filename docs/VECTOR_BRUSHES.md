# Structured vector brushes

Vector `stroke.brush` retains original filled motifs along the centerline. Agents can decorate routes, construct repeating icon borders and vary artwork size while retaining path and spacing edits. This is a rigid motif model: glyphs rotate and scale at measured positions; they do not warp or stretch through bends. No asset catalog or hardware is required.

```json
{
  "color": [30,100,210,255],
  "width": 4,
  "width_profile": [[0,0.5],[0.5,2],[1,0.5]],
  "brush": {
    "motif": {"shape":"rect","x":-0.5,"y":-0.5,"width":1,"height":1},
    "spacing": 3,
    "phase": 0,
    "fit": "fixed"
  }
}
```

Use the ordinary `vector` edit to replace geometry/appearance, `document.inspect` to inspect saved controls, and snapshot/session history to retain editable brushes. See [the workflow](../examples/vector_brush_workflow.py) and [strokes](STROKES.md).

## Coordinates, spacing and width

Each motif is closed project geometry centered as authored around its local origin. Its x axis follows the evaluated centerline tangent; positive y follows the left normal in the numeric coordinate system. Multiply both axes by `stroke.width` and the linearly interpolated width-profile factor at its center. Original cubic motif controls survive this affine mapping. Shapes and ellipses use the existing primitive-to-path conversion; compound motifs retain their authored nonzero winding.

Spacing is 0.001..1024 base widths, independent of the variable-width factor. Signed phase is -32768..32768 base widths, reduced modulo spacing. With `fit:"fixed"`, centers occur at `(phase mod spacing + k*spacing)*width`. Open contours include a center exactly at the endpoint; closed contours omit that duplicated seam. Each contour restarts phase and the whole 0..1 profile.

`fit:"uniform"` chooses `N=max(1,round(length/(spacing*width)))` intervals, with half values rounded up. Their step is `length/N` and phase becomes `(phase mod spacing)/spacing` of one fitted interval. Only positions on the contour are retained. This adjusts center spacing, never motif shape. A zero-length contour has one body placement at its origin, regardless of phase, with +x direction and profile position zero. Zero scale contributes no commands.

The shared original f64 stroke evaluator subdivides cubic centerlines into a bounded polyline. Its saved `curve_tolerance` controls chord deviation and allocated length gap. Centers, directions, profile distances and corner decisions use that evaluated polyline. This is a declared evaluation model, not an exact symbolic arc-length or global appearance error bound.

## Endpoints and corners

Optional `start_motif` and `end_motif` replace the body center at each open endpoint and orient along forward traversal, including at the start. `end_clearance` (default 0) suppresses body centers whose distance from an endpoint with a motif is at most that many base widths. Closed contours have no endpoint motifs; mixed compound paths apply them only to their open contours. A degenerate open contour can have coincident start/end motifs.

Optional `corner_motif` places a separate motif at original path-command junctions, including the closed seam. Flattened interior cubic subdivisions are never corners. Consecutive repeated points do not create duplicate anchors. `corner_angle` (default 30, range 0.1..180 degrees) is the minimum absolute turn between the adjacent evaluated segment directions. `corner_orientation` is `bisector` (default), `incoming` or `outgoing`; an exact reversal uses the outgoing direction for its bisector fallback. `corner_clearance` (default 0) suppresses nearby body centers by contour distance, using cyclic distance across closed seams. Its range and units match endpoint clearance: 0..1024 base widths. Clearances affect center placement, not a geometric collision or trimming promise.

Body motifs are followed by endpoints and corners in generated command order. All contours combine into one nonzero coverage field and receive stroke paint once. Overlapping shapes, holes and opposite winding follow ordinary nonzero semantics; expansion does not Boolean-weld them. Endpoint and corner motifs use the same local width-profile factor as body motifs.

## Scaling, delivery and persistence

`scaling:"object"` evaluates locally and transforms complete motif geometry through ancestors. `scaling:"document"` transforms the centerline first, then evaluates widths and spacing in document logical units, separately for each component or mask placement. Paints remain item-local. Artboard output evaluates in the independent board viewport.

`stroke_expand` retains the original centerline/fill as a child and creates a second child with ordinary filled line/cubic motif contours. The parent keeps appearance, masks, effects and hierarchy. Later transforms scale the expanded geometry; session undo restores the live brush. Document-scaled reusable definitions must first be unlinked into a placement before expansion.

SVG delivers the same ordinary filled outlines and explicitly reports loss of editable brush controls. Snapshot output preserves the complete original controls and motif geometry. PNG and the other image outputs share live outline evaluation. Bounds/alignment of a live stroke still describe its centerline; expand a copy when filled-artwork bounds are needed.

## Validation and limits

Motifs must be closed, valid geometry with all expanded control coordinates within Ã‚Â±16 normalized units. Their stored command counts join the document's 4096-command budget. Brush spacing/corner/end controls are strict; custom corner/end settings without corresponding motifs fail. Brush spacing/end/corner semantics cannot be combined with dashes, arrowheads, or nondefault cap/join/miter controls. Those combinations return `UNSUPPORTED`.

The existing width, profile, paint, geometry, stored snapshot, generated-outline, mask-instance, artboard-range and rendering limits remain enforced. Closed profiles require equal endpoint factors. Hidden content also counts. Conservative placements are capped at 8192 per stroke, including unused endpoint/corner upper bounds. Per contour, the body bound is `ceil(1.00000001*control_polygon_length/(spacing*width))+2`; corner and endpoint bounds are added. Work is total bound times the largest expanded motif command count, plus body bound times corner bound for clearance comparisons. Work joins the existing 32768 document, 131072 repeated-mask and 524288 range caps.

A distance roundoff allowance is `16*f64_epsilon*(point_count*length + sum(max(abs(x),abs(y))))` over evaluated centerline points. Nonzero body distances within that allowance of the terminal distance snap to the terminal distance, avoiding almost-duplicate closed seams. Endpoint/corner clearance comparisons include the same allowance. If it exceeds one quarter of the actual fitted or fixed step on a nonzero contour, evaluation returns `UNSUPPORTED` rather than merging numerically ambiguous placements. The start position remains exactly zero.

A live pattern may fit generated-outline limits while expansion exceeds the stricter stored-command budget. Expansion then fails atomically and leaves the editable source intact. No partially expanded snapshot is returned.

## Verification

Twenty original CLI/MCP tests independently check exact axis-aligned pixels, analytic profile areas and affine placements, all three corner orientations, seam clearance, endpoints/reversals, compound holes, a 20000-segment independent cubic-distance reference, preserved cubic motif controls, object/document scaling, opacity/masks/effects, shared resource placements, editable spacing, snapshot/SVG/artboard delivery, durable restart/undo/redo/retries, strict failures and aggregate work limits. A Rust library test rejects nonfinite controls. The private delivery checks use separate image/SVG consumers and retained original fixtures.
