# Editable motif layouts

A repeat item retains original closed vector geometry, a fill and structured placement controls. Use it for pattern fields, tiled backgrounds, repeated icons and radial diagram markers:

```json
{"id":"tiles","content":{"type":"repeat","repeat":{
  "geometry":{"shape":"rect","x":-4,"y":-3,"width":8,"height":6},
  "fill":[40,120,220,255],
  "origin":[12,12],
  "layout":{"type":"brick","columns":4,"rows":3,"step":[8,6],"offset":0.5}
}}}
```

The item is an ordinary printable leaf with existing transform, opacity, mask, clip, effect, blend and metadata properties. It can be placed in vector hierarchies, component definitions and nonprinting artwork-mask sources. Ordinary printable raster layers cannot contain it.

## Layout coordinates

`origin` defaults to [0,0]. The motif's `anchor` defaults to the center of analytic geometry bounds. Positions are anchors, not top-left corners. Indices are zero-based and grid output is row-major.

| Layout | Required controls | Position relative to origin |
| --- | --- | --- |
| `grid` | `columns`, `rows`, `step:[sx,sy]` | [column*sx, row*sy] |
| `brick` | Grid controls | Rows: [(column + (row mod 2)*offset)*sx, row*sy]. Columns: [column*sx, (row + (column mod 2)*offset)*sy] |
| `hex` | `columns`, `rows`, `radius` | Pointy: [sqrt(3)*radius*(column + (row mod 2)/2), 1.5*radius*row]. Flat: [1.5*radius*column, sqrt(3)*radius*(row + (column mod 2)/2)] |
| `radial` | `count`, `radius` | radius*[cos(angle), sin(angle)] |

Brick `axis` is `"rows"` by default or `"columns"`. `offset` defaults to .5 and may be 0..1. Steps can be negative and have magnitude .001..32768. Hex `orientation` is `"pointy"` by default or `"flat"`; radius is the circumradius of a matching regular hexagonal motif. Hex layout places any supplied closed motif; it does not change its shape automatically.

Grid/brick/hex `mirror` is `"none"`, `"columns"`, `"rows"` or `"both"`. Odd columns reflect x and odd rows reflect y, about the placement anchor. The motif may be asymmetric or contain holes.

Radial `start_angle` defaults to 0 degrees, `sweep` to 360 and `closed` to true. Angles increase from +x toward +y in document coordinates. A closed layout requires sweep +360 or -360 and uses `start_angle + sweep*i/count`, excluding a duplicate final seam position. An open arc requires at least two copies and a nonzero sweep of magnitude below 360, using `i/(count-1)` so both endpoints appear. Radius is .001..32768; start angle is -360..360. `orientation` is `"fixed"`, `"radial"` or `"tangent"`. Tangent direction follows the sign of the sweep. Quadrantal directions are exact.

## Transforms, winding and seams

`motif_transform` and `transform` default to identity. A motif point is evaluated by:

`transform * translate(origin + layout_position) * rotation * mirror * motif_transform * translate(-anchor)`.

The item and ancestor transforms then apply normally. Motif-transform translation is deliberately relative to the placement anchor and is also mirrored/rotated. Inspection returns the layout centers separately from the complete geometry matrices.

All transformed motifs become one compound path, and the fill paints once across its coverage. Shared coincident tile edges therefore do not acquire independent per-copy antialias or opacity seams. Overlapping nonzero motifs do not accumulate opacity. Geometric gaps or mismatched boundary shapes remain gaps; the engine does not invent boundary artwork or join unrelated edges. Raster coverage still has the existing f32/quantized edge contract.

Reflections reverse each closed contour's traversal to preserve its authored winding relative to the other copies, including holes. Cubic controls transform exactly up to floating-point roundoff. `fill_rule` defaults to `"nonzero"`; `"even_odd"` applies parity to the entire field and intentionally clears overlapping regions of even multiplicity.

The fill uses repeat-item coordinates across the entire field; it does not restart per copy. Existing solid/gradient/mesh/pattern paint support and export restrictions apply. Motifs are closed filled geometry. To repeat a stroke's outline, expand it into closed filled geometry first. Arbitrary multicolor source hierarchies and per-copy appearance overrides use shared components separately; they are not silently flattened into this single-fill model.

## Editing and delivery

`repeat.inspect` accepts `repeat`, `include_geometry` and optional `control`, returning count, row/column indices, centers, matrices, reflection flags, combined command count, bounds and optional geometry. Bounds exclude effects and clipping. `document.inspect` retains saved controls and `document.query` accepts type `"repeat"`.

`{"op":"repeat","id":"tiles","repeat":{...}}` replaces layout/motif/paint settings. `{"op":"repeat_expand","id":"tiles"}` produces one ordinary vector item with the same identity, appearance and combined geometry. The source remains in the input snapshot and durable undo history. The receipt reports copy count and the combined-fill convention.

Snapshots, transfer, component/mask references, session restart, retry receipts, undo/redo and create-only publication preserve their usual contracts. PNG and SVG use the same combined geometry as expansion. SVG explicitly reports loss of the editable motif/layout controls; keep a snapshot for future changes. Artboard exports include expanded command and work budgets before output.

Layouts allow 1..128 copies in total. Stored motif commands join ordinary document limits; generated repeats share the 4096-command budget, including hidden content. Full evaluated documents also obey ordinary coordinate, paint, mask, component, rendering and export bounds. Unknown controls, open motifs, invalid matrices, nonfinite values, invalid radial seams and excessive work fail explicitly. Inspection checks deadlines/cancellation around bounded planning.

Nineteen original CLI/MCP tests independently verify lattice coordinates, exact pixels, internal tile seams, arbitrary radial angles, winding/holes, preserved cubic controls, affine composition, paint-once overlaps, masks/effects, components, transfer, snapshots, durable edits and publication. A Rust test checks nonfinite direct-library inputs. Separate original fixtures and image/SVG consumers retain external delivery evidence.
