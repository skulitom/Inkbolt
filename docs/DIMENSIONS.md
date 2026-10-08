# Dimensions, measurements and snapping

Agents can inspect rotated geometry bounds, set physical dimensions and snap selected artwork to explicit points, grids, guides or item anchors. All operations use the document's declared resolution. Measurements are read-only; dimension and snap edits retain source geometry, pixels, shared definitions and existing appearance controls. These commands also work through MCP stdio and durable sessions.

## Geometry measurements

```json
{"command":"geometry.measure","document":{},"options":{"ids":["panel"],"unit":"mm","angle":30,"tolerance":0.0001,"area_tolerance":0.000001}}
```

Replace `document` with a valid snapshot. Select 1..256 unique, disjoint IDs. Units are `px` (default), `pt`, `pc`, `mm`, `cm` and `in`: one inch is exactly 72 points, 6 picas, 25.4 millimeters, 2.54 centimeters or `resolution_ppi` logical pixels. This conversion uses exact rational arithmetic on the stored resolution. It does not alter document resolution or output scale.

`angle` selects axes rotated clockwise from the document axes, in degrees within +/-360000. Each result contains bounds and width/height in the requested units, and four corresponding corners in document coordinates. Bounds are computed from actual geometry in the requested axes. Groups union descendant geometry; frames use their own rectangle, text uses its frame rather than glyph ink, and images use their source or deformed boundary. Resource definitions and adjustment layers have no measurable bounds. Visibility, opacity, stroke widths, effects, clipping and masks do not change these geometry measurements. Set `bounds_only:true` to omit boundary integration.

`boundary_length` sums authored open or closed contour lengths. Closed contours include their closing segment; open contours do not acquire an implicit closure. Retraced segments count for every traversal. `signed_area` is the signed algebraic integral of closed contours, in squared units; it is null if any selected leaf contour is open. Reflection reverses its sign. Opposite winding subtracts holes; self-intersections can cancel area. A group's result sums its leaves, including overlaps; a frame measures only its own boundary. These metrics do not represent a filled union, clipped appearance or painted-pixel coverage. Use filled-geometry operations or pixel measurements when those are the required semantics. Existing `document.measure` remains the separate composite pixel histogram/sample command.

Each metric reports `value`, `absolute_error_bound`, outward-rounded `lower`/`upper`, and exact rational `lower_exact`/`upper_exact`. Length tolerance defaults to 0.0001 units and must be in 1e-6..100; area tolerance defaults to 0.000001 squared units and must be in 1e-9..10000. The absolute error bound is at most the requested tolerance. Line/cubic signed integrals use exact rational arithmetic. Cubic lengths use exact subdivision with chord lower bounds and control-polygon upper bounds. Ellipses use their analytic affine ellipse, rational quadrant parametrization, chord/tangent length bounds and a bounded pi interval for area. Rectangles retain their declared sizes without subtracting rounded far-offset endpoints.

The certificate concerns authored geometry under the engine's composed binary64 world matrix. Hierarchy matrix composition, rotated bounds and edits still use ordinary binary64 arithmetic; bounds are not certified by the length/area tolerance. Generated components, warps, repeats, interpolation and deformed image boundaries retain their documented evaluation contracts. Certificates measure that evaluated geometry and do not erase its prior approximation error. Primitive path expansion retains its existing declared approximation. Failure to meet the subdivision budget (65536 work units across the request, depth 32) returns `RESOURCE_LIMIT`. A requested tolerance below representable numeric output precision returns `NUMERIC_PRECISION`. Cancellation and deadlines return explicit errors without partial measurements or mutation.

## Set dimensions without rewriting the source

```json
{"op":"dimensions","id":"panel","dimensions":{"width":24,"unit":"mm","angle":30,"anchor":{"x":"min","y":"max"},"preserve_aspect":true}}
```

Use this in `document.edit` or `session.apply`. At least one of `width`/`height` is required. Omitting one retains that axis size unless `preserve_aspect:true`, which requires exactly one supplied dimension and applies the same scale to both axes. The default anchor is center/center; each coordinate also accepts `min` or `max`. The selected bounds anchor stays fixed in document coordinates. Resizing scales the world geometry in the declared rotated axes and maps the result back through the parent inverse. Receipts retain prior dimensions, requested dimensions, scale, anchor and world transform.

Both existing dimensions must be nonzero. Requested sizes must map to 0.001..65536 logical pixels, and the result must satisfy all existing matrix, coordinate and resource limits. Text frame resizing transforms its placement; it does not reflow text or rewrite font sizes. Image resizing retains the original samples. Stroke scaling, effects and linked/unlinked masks retain their existing contracts; see [TRANSFORMS.md](TRANSFORMS.md). Selected items and descendants must be unlocked. Ordinary atomic batches, rollback, revisions, history and retry behavior apply.

## Snap to explicit references

```json
{"op":"snap","ids":["panel","badge"],"snap":{"targets":[{"type":"grid","origin":[0,0],"spacing":[4,4],"angle":0},{"type":"guide","frame_id":"page","id":"margin"}],"max_distance":2,"unit":"mm","mode":"together","anchor":{"x":"min","y":"min"}}}
```

`targets` contains 1..64 entries. Point coordinates, grid origins/spacings and maximum distance use the requested physical unit; guide positions remain in their authored frame coordinates. `angle` on the snap options selects source-bound axes. Item targets accept their own `angle` and `anchor`. A grid's angle rotates its axes around its origin. Existing frame guides become infinite document-space lines, including under rotation, reflection and shear. Guide intersections are candidates by default; `intersections:false` disables them. Numerically parallel guide pairs, whose normalized direction cross product is at most 1e-10 in magnitude, are omitted and counted in the receipt.

Together mode snaps the union bounds anchor with one shared translation, preserving relative spacing. Individual mode snaps each item's bounds anchor separately. Source and reference bounds are frozen before the operation. A reference cannot be a selected item or move under a selected ancestor; a reference group cannot contain selected artwork. A parent frame remains usable because its frame bounds and guides do not depend on child placement. Shared-resource references retain their frozen pre-operation values. Locked references are readable; selected locks are enforced.

Only candidates within the Euclidean maximum distance qualify. Explicit point/grid/item/intersection candidates take priority over single-guide projections, then nearest distance wins, then input order. Grid half-way ties choose the lower index on each axis, including negative indices. Each change reports whether it matched, source/target points, translation, physical distance and chosen reference. No match retains the items and reports `matched:false`; an accepted edit batch still advances revision. Explicit point and grid-origin coordinates outside +/-32768 logical pixels fail validation. Derived candidates outside that range are excluded; no off-limit candidate can move artwork. Grid spacing is 0.001..32768 logical pixels and maximum distance is 0..32768. Snap decisions use binary64 calculations and have no exact rational distance certificate.

The original [layout workflow](../examples/dimensions_workflow.py) saves a source, measures a card, applies physical sizing and guide snapping, and publishes SVG/PNG plus the edited snapshot. `tests/test_dimensions_snapping_cli.py` checks independent rational/analytic area and length formulas, ellipses, retracing, rotated bounds, unit conversion, oblique guides, tie rules, source preservation, components, pixel frames, cancellation and durable agent history.
