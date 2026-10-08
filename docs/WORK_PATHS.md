# Reusable paths and pixel regions

Work paths store named, nonprinting geometry in either document kind. Agents can keep an editable outline while deriving pixel selections or independently editable vector masks. They use ordinary stable item IDs, parents, transforms, locks, duplication, query, snapshots and session undo/redo.

Add an item with `content:{type:"work_path",geometry,fill_rule}`. All existing geometry kinds are accepted; `fill_rule` defaults to `nonzero`, with `even_odd` also available. Work paths never paint pixels and are omitted from SVG with a loss diagnostic. Retain the snapshot for path persistence. Their geometry contributes to ordinary item/container bounds and alignment; these bounds describe geometry, not painted pixels.

Work paths accept name, visibility, locks and transforms. Visibility affects discovery but never makes a work path print. Opacity must remain 1 and blending normal; clips, grayscale masks and filters on the work path itself fail explicitly. Effects on its ancestors do not alter a region derived by explicit source ID. Nonprinting work paths do not interrupt a sibling chain of clipped adjustments and cannot serve as an adjustment base.

## Operations

| Operation | Fields and behavior |
| --- | --- |
| `work_path` | `id,geometry,fill_rule`: replace the geometry/rule of an existing work path; retains item identity and transforms |
| `path` | Existing convert, anchors, handles, split, reverse, join and certified simplify actions work on work paths, with the same revision-scoped indices and local/world coordinates |
| `selection_path` | `id,combine,antialias`: derive a canvas-sized grayscale selection from the source's world geometry and fill rule; combine defaults to replace, antialias to true |
| `clip_from_path` | `id,path_id,replace_existing`: copy a source region into the target item's vector clip; replacing any existing clip requires explicit `replace_existing:true` |

Both region operations accept work paths or vector items as sources. Paint, stroke, opacity, visibility, locks, clips, masks and ancestor effects do not define the source region. Reading a locked source is allowed; changing a path or a mask target respects inherited locks. All operations participate in the existing atomic batch and session contracts.

`selection_path` fills implicitly closed contours, including open source contours. Add/subtract/intersect use the existing pixelwise maximum/saturating difference/minimum; they require an active selection. A selection is a copied pixel field and does not update when its source changes. Use `mask_from_selection` on a colored fill or image to apply the resulting coverage, or save it as a reusable channel. The [original example](../examples/work-path.json) creates a cubic region and a masked color fill. `pixel_fill` retains its existing rectangular replacement semantics and does not implicitly consult the active selection.

`clip_from_path` copies geometry and fill rule and stores `inverse(target_world) * source_world` as the new item-local clip transform. Current world placement is preserved up to f64 matrix arithmetic and ordinary transform validation. The copy follows subsequent target transforms; moving/deleting the source does not change it. Existing clip editing can transform, disable or replace it. A geometric clip and a grayscale mask on the target multiply; copying does not discard the grayscale mask. Work-path targets fail the existing appearance validation; pass-through container clips weight their change to the backdrop. This is an independent copy, not a live reference.

`work_path_combine` retains independent source curves and per-operand winding under editable union/intersection/difference/xor trees. These regions support selections, independent vector-mask copies, component handle edits and saved history without requiring a flattened path. See [COMPOUND_REGIONS.md](COMPOUND_REGIONS.md) for geometry, coverage and delivery limits.

`document.boolean` also accepts ordinary work paths. It returns root-coordinate geometry which an agent can add as another work path while preserving the operands. Polygon combinations and certified supported curve combinations retain the limits in [BOOLEANS.md](BOOLEANS.md). General algebraic flattened-curve contacts remain incomplete under the separate advanced vector-boolean criterion; retained compound regions do not claim that certificate.

## Coverage and limits

Path selections use original f64 horizontal-interval integration over 256 midpoint subrows per output row. Cubics split at y-derivative roots; each monotone interval finds its scanline crossing with at most 56 bisection steps. Signed crossings implement winding and parity, with half-open y intervals counting shared vertices once. Horizontal edges and zero-area traces contribute no fill. Horizontal pixel overlaps are integrated before one grayscale8 rounding. With antialias disabled, pixel centers determine binary coverage.

This is numerical sampling, not exact area or a topology certificate. Features between subrows can disappear, and f64/byte rounding remains observable. Paths retain their original f64 controls. Primitives expand into line/cubic commands; an ellipse uses the documented four-quarter-cubic approximation. Geometric clips continue using the display backend's f32 antialiased coverage, which can differ from a path-derived pixel selection. Use a selection-derived grayscale mask when that coverage contract is required.

Selections retain the 262,144-pixel canvas limit, 67,108,864-work-unit evaluation limit and snapshot byte limit. Before sampling, estimated work is covered rows times subrows times `(canvas_width + weighted_edges + sorting)`. A line costs one edge unit and a monotone cubic interval 57; sorting costs `edge_count * (floor(log2(max(1,edge_count))) + 2)`. Ordinary 256-item and 4,096-command document budgets include work paths and copied clips. Oversized work fails before publishing any change. No external dependency, listener or resource store is added.

Independent tests verify analytic polygon and cubic area, turning-curve roots, both winding rules, reversal, implicit closure, fractional set algebra, world placement, filled pixels, masks, nonprinting exports, locks, resource failures, MCP sessions, reopening, snapshots, retries and undo/redo.
