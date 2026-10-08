# Parametric shapes, discovery and path edits

Vector items, nonprinting work paths and geometric clips accept rounded rectangles, arbitrary polygons, regular polygons and stars in addition to rectangles, ellipses and explicit paths. Shape parameters remain editable in snapshots and session history. Rendering, analytic bounds, transforms, gradients, opacity masks and SVG all use the same expansion into line/cubic commands.

| Geometry | Fields |
| --- | --- |
| `rounded_rect` | `x,y,width,height,radii:[topLeft,topRight,bottomRight,bottomLeft]` |
| `polygon` | `points:[[x,y],...]` |
| `regular_polygon` | `cx,cy,radius,sides,rotation` |
| `star` | `cx,cy,outer_radius,inner_radius,points,rotation` |

Sizes and positive radii are at least 0.001 logical pixels. Rounded-corner radii may be zero; negative radii fail. The original four requested values persist, while effective radii shrink by one common factor if adjacent sums exceed an edge. This follows the proportional overlap rule in the public [CSS corner specification](https://www.w3.org/TR/css-backgrounds-3/#corner-overlap). Each rounded corner is defined by a quarter cubic with tangent coefficient `4*(sqrt(2)-1)/3`. These explicit cubics, including their analytic extrema, define Inkbolt's rendered geometry.

Polygons require 3 through 1,024 points and at least three distinct positions. Adjacent duplicates and repeated closure points are accepted. Collinear vertices can define zero filled area while retaining stroke geometry; crossed polygons use the declared fill rule. Regular polygons allow 3 through 256 sides; stars allow 3 through 128 tips, with positive inner radius no greater than outer radius. Equal star radii define a regular `2*points` polygon. Zero primary dimensions/radii and collapsed one/two-position polygons fail explicitly.

Rotation defaults to zero and is in degrees within +/-360,000. Zero places the first vertex on the positive x axis; positive angles advance toward positive y. Fractional/negative coordinates are supported within existing geometry bounds. Expanded vertices and controls also undergo ordinary coordinate validation. Commands from expanded shapes count against the complete 4,096-command document budget, including clips. SVG exports explicit paths and reports that editable shape parameters require the original snapshot.

## Discover objects and anchors

`document.query` takes `{document,query}` and returns IDs, inspection records, source revision and declared bounds semantics. Its filters are:

- `types`: any of work_path, vector, raster, image, fill, text, group, frame or adjustment. Empty means all; layer roles are groups and artboard roles are frames.
- `shapes`: any of rect, ellipse, rounded_rect, polygon, regular_polygon, star or path. A nonempty list requires vector content or a work path.
- `region:{bounds:[left,top,right,bottom],relation}`: compare inclusive world geometry bounds. Relation is `intersects` (default) or `contains`, where the region must contain the item's entire bounds. Touching bounds match. Empty containers have no bounds and do not match a region.
- `visible_only`: true by default, using inherited visibility flags. This does not infer visibility from opacity or occlusion.
- `include_locked`: false by default. Locked items, locked ancestors and locked affected descendants are excluded from editable discovery. Set true to inspect them explicitly.
- `include_anchors`: include path endpoint records, with command/contour/anchor indices, local/world positions and cubic handles.
- `anchor_bounds`: optionally filter anchors by inclusive document coordinates, and return only items with matching path anchors. This implies anchor inspection.

Results follow document storage order. Each returned item includes `edit_blocked_by_locks`, which also accounts for descendants, while `effective_locked` describes the item and its ancestors only. Bounds exclude strokes, masks and clipping and are not an exact filled-area hit test. Parametric objects have no explicit anchor records until converted to paths. Queries are read-only and create no persistent selection state. `document.select` still inspects explicit item IDs; pixel selections remain the separate scalar field documented in SELECTIONS.md.

## Atomic path edits

An edit operation is `{op:"path",id,action}`. Actions below use the path's current command indices. Every topology edit can renumber them, so inspect again after an edit and use `expected_revision` or session conflict checks before applying a later selection. Multiple operations share ordinary atomicity and lock checks; failures publish no partial candidate.

| Action type | Fields | Behavior |
| --- | --- | --- |
| `convert` | none | Expand the item's current primitive into an explicit path |
| `anchors` | `points:[{command_index,to}]`, `space`, `move_handles` | Move distinct selected endpoints |
| `handles` | `command_index`, optional `control1/control2`, `space` | Set at least one handle of a cubic command |
| `split` | `command_index,t` | Split a line or cubic strictly inside parameter interval `(0,1)` |
| `simplify` | `tolerance`, optional `space`, `max_span`, `contours` | Reduce segments with exact deviation and topology certificates; see SIMPLIFICATION.md |
| `reverse` | optional `contours:[indices]` | Reverse selected contours; empty/omitted means all |
| `join` | `first,second,mode,close` | Join two open contours, optionally closing the result |

`space` defaults to local and also accepts world. World points convert through the inverse complete item transform. Anchor entries can address move, line and cubic endpoints; close commands have no endpoint entry. `move_handles` defaults true: moving an endpoint translates the incoming cubic's second handle and the immediately following cubic's first handle by the same local delta. False leaves both handles at their existing coordinates. An explicitly repeated endpoint remains a separate anchor; coincident coordinates do not imply welded identity. Handle edits use absolute coordinates and do not automatically mirror or smooth adjacent controls.

Split uses original de Casteljau interpolation for cubics and linear interpolation for lines. The mathematical curve, direction, connectivity and contour closure stay unchanged; f64 arithmetic introduces ordinary roundoff. Independent samples over five split parameters agree within `1e-11` logical pixels for the documented synthetic fixture. No flattening tolerance or lossy approximation is introduced by splitting. End parameters, missing indices, move and close commands fail explicitly.

Reversal swaps cubic control order and traversal direction. Closed contours retain their original starting point; an implicit closing line can become explicit, and a final straight closing edge can be represented by close. Open contours start at their previous endpoint. Reversing one contour of a compound nonzero path can deliberately change holes; reversing the entire geometry preserves filled occupancy. Winding, reversed holes, crossed contours and touching boundaries are checked independently through snapshots, PNG pixels and parsed SVG.

Join requires distinct open contours. `mode:"coincident"` is the default and requires exact endpoint equality. `bridge` inserts a straight connection when endpoints differ; no endpoints are silently snapped. The first contour traverses into the second, and the joined contour occupies the earlier of their two contour positions. Other contours retain relative order. `close:true` adds an explicit closing relationship; otherwise the result stays open. Reverse a contour first when a different endpoint should be joined. Style and item identity remain shared across the compound path.

Path command semantics follow the public [SVG cubic path definition](https://www.w3.org/TR/SVG2/paths.html#PathDataCubicBezierCommands). Primitive conversion, splitting, reversal and editing are original engine code. Rectangle/polygon/star/rounded-rectangle conversion preserves the engine's existing outline exactly up to f64 arithmetic. Converting an analytic ellipse uses four quarter cubics and changes its mathematical outline slightly; independent normalized radial samples measure a maximum below 0.0003. Keep an ellipse primitive when its analytic representation is needed. Snapshots/history preserve the original before conversion.

Curve simplification now returns checked deviation bounds, preserved-topology evidence and retention reasons in the edit receipt. See [SIMPLIFICATION.md](SIMPLIFICATION.md) for exact guarantees, conservative candidates, coordinate metrics and work limits. Rectangle/polygon boolean operations are available through [BOOLEANS.md](BOOLEANS.md); the full advanced curved checkpoint remains in progress. Variable-width strokes, arrowheads, stroke expansion and broader geometry features remain separate tracked requirements.
