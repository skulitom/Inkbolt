# Affine transforms and stroke scaling

Transforms retain editable source geometry. An item matrix `[a,b,c,d,e,f]` maps a local point to `[a*x+c*y+e, b*x+d*y+f]`. Coordinates use a top-left origin with positive y downward. Matrix multiplication applies the right operand first; the world matrix is the ordered product of ancestor matrices followed by the item matrix. Reflection, rotation, nonuniform scale and shear use this same contract.

## Composition and pivots

The atomic `transform` edit takes `id`, `matrix`, optional `space` and optional `anchor:[x,y]`. `space` defaults to `replace`. With parent world matrix P, current item matrix L and supplied matrix M:

- `local`: store L*M.
- `world`: store inverse(P)*M*P*L.
- `replace`: store M in parent coordinates.

An anchor wraps M as translate(anchor)*M*translate(-anchor) before that operation. Thus an anchor is in item-local coordinates for `local`, document coordinates for `world`, and parent coordinates for `replace`. A matrix with translation can move the anchor; only its linear part is pivoted.

These edits evaluate the complete ordered expression, including anchors and the
parent inverse. The ordinary path bounds coefficient error applied to any point
within 65536 on each axis by `1e-9` logical units per axis. If that bound cannot be
certified, exact rational arithmetic computes the complete expression from its
binary64 inputs and rounds only the final coefficients to nearest binary64.
This avoids losing a small local result to cancellation between large intermediate
transforms. Reparenting and scalar/artwork mask linking and transforms use the same
bounded expression evaluator, with at most eight factors after the parent inverse.

Other coordinate conversions share an ordered evaluator with at most nine forward
or inverse factors. This includes transfers, copied clips, mask and artboard
placement, dimensional edits, world path points and preview mappings. Alignment,
distribution, assisted layout and snapping retain the original local linear part
when applying world translations. The complete input expression is evaluated
before rounding; previously calculated input bounds and matrices remain separate.

The exact fallback promises nearest final coefficients, not the ordinary path's
absolute point bound. Source geometry is retained; world recomposition, final
point arithmetic and sampling remain separate numerical stages. Existing matrix,
geometry, hierarchy and resource limits still apply after an edit. The standalone
library `geometry::inverse` has its own coefficient contract and does not by itself
certify later compositions. See [coordinate precision](COORDINATE_PRECISION.md).

```json
{"op":"transform","id":"connector","space":"world","matrix":[3,0,0,2,0,0],"anchor":[8,40]}
```

This scales around document point `[8,40]` without changing the source centerline. Inspection reports the composed world matrix and unclipped geometry bounds. Bounds exclude live strokes, visibility and opacity. Locks, dependency locks, expected revisions and all-or-nothing batches apply.

## Explicit stroke policies

Vector strokes accept `scaling:"object"` or `scaling:"document"`:

| Policy | Centerline | Width, dashes, arrows and tolerance |
| --- | --- | --- |
| `object` (default) | Editable local geometry | Evaluate the outline locally, then transform it with the item and ancestors |
| `document` | Map controls through the complete world matrix | Evaluate the outline in document logical units after placement |

Omitting `scaling` preserves existing object-scaled behavior and snapshot serialization. The policy is retained through vector edits, duplication, variants, reusable components and durable sessions. Unknown values fail explicitly.

Document scaling keeps line widths, dash intervals/phase, arrow lengths/widths and curve tolerance constant under changes to item or ancestor scale. Width-profile positions follow evaluated document-space contour length. Cap and join geometry is constructed in that space, including reflected, sheared and closed contours. Paint coordinates continue to follow the item; a gradient is not detached by the stroke policy. Masks, clipping, fill/overall opacity and effects retain their existing contracts. Layer-effect strokes are separate decorations with their own documented units.

Export scale converts logical units into output pixels for both policies. For example, a document-scaled width of 2 produces a 6-pixel-wide horizontal line at PNG scale 3. It is not a fixed physical or device-pixel width. Independently exported artboards remove board placement and ancestor context first; their local viewport becomes the document coordinate system for fixed-width evaluation. Shared mask references and component copies each evaluate their actual placement separately.

Evaluation tightens the saved maximum curve tolerance for the current placement using a conservative linear stretch bound and raster density 16. Document-scaled strokes refine the already transformed centerline; object-scaled strokes account for the composed world matrix. Saved controls remain unchanged, and all outline consumers share the same geometry at that placement. See [stroke precision](STROKES.md#evaluation-precision-and-limits).

## Expansion and SVG

`stroke_expand` freezes the current evaluated outline as ordinary editable filled geometry. Document-space outlines are mapped back through the current inverse world matrix into the original item's coordinates. The existing group/centerline/outline structure preserves paints and appearance. Receipts expose `source_scaling` and `future_scaling:"filled_geometry_follows_object"`.

After expansion, future resizing scales the filled outline normally. Keep the live stroke or undo expansion when future constant-width behavior is needed. A reusable component or mask source can have several placements with different fixed-width outlines. Expanding a document-scaled stroke directly inside such a definition therefore returns `UNSUPPORTED`. Unlink the desired component placement first and expand its independent child. Source definitions and other placements remain intact.

SVG exports document-scaled strokes as filled paths and reports loss of editable stroke controls and future fixed-width behavior. Per-reference mask outlines use their actual placement. Snapshot export retains the policy. SVG `vector-effect` import remains outside the supported subset and fails explicitly; no silent policy inference occurs.

## Precision and bounds

Hierarchy products use conservative error tracking and an exact rational fallback
when ordinary composition could move a stored control by more than `1e-9` logical
units before final point arithmetic. The fallback rounds only the completed
matrix coefficients and verifies their nearest binary64 rounding. Identical
chains and inspection bounds are reused within one immutable preparation, with a
fixed cache bound and no reuse across edits. This preserves small residuals in
deep sequences of large shears and nearly inverse transforms. See
[coordinate fidelity](COORDINATE_PRECISION.md) for the precise scope and independent
large-layout, numerical, coverage and history fixtures.

Affine geometry and stroke evaluation use original f64 calculations. Raster coverage uses f32 coordinates and quantized antialiasing. Inverse mapping for editable expansion or SVG adds normal floating-point roundoff, so arbitrary ill-conditioned transforms do not carry a universal byte-identical edge-pixel guarantee. Stored and world coordinates, matrices and generated outlines must pass their existing bounds. A matrix must be finite, each entry at most 32768 in magnitude, absolute determinant at least 1e-8, and nonsingular at renderer precision. Singular or unrepresentable semantics fail explicitly.

The limits in [STROKES.md](STROKES.md) apply in the declared evaluation space. Hidden items still consume work. Mask copies and independent artboard outputs are checked at their actual transforms before output. Expansion also checks ordinary stored path/item/coordinate limits and may fail even when a live outline can render. Such failures leave the source document and existing outputs unchanged.

Determinant decisions compare exact stored binary64 values against the unchanged
binary64 minimum, so cancellation cannot move a matrix across that threshold.
The inverse's ordinary coefficient error is bounded before use; unstable cases
compute all inverse coefficients rationally. See the [inverse precision
contract](COORDINATE_PRECISION.md) for the fast-path bound and the separate limits
of final point arithmetic, inverse composition and sampling.

Independent rational matrix algebra, analytic segment normals/areas, complete expected pixel grids, explicitly mapped cubic controls, placement-specific masks/artboards, limits and durable MCP history are covered by `tests/test_transform_policies_cli.py`. The original `examples/transform_workflow.py` publishes a diagram comparison using both policies.
