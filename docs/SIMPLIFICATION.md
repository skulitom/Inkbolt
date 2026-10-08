# Curve simplification with checked geometry

`{op:"path",id,action:{type:"simplify",tolerance,space:"local",max_span:8,contours:[]}}` reduces the number of line/cubic segments or replaces a sufficiently straight cubic with a line. It operates on explicit vector paths; convert primitives first. `tolerance` is a finite distance in 0..32768. `space` is local (default) or world. `max_span` is 2..32 (default 8). Empty/omitted `contours` means every contour; explicit indices must be distinct and valid.

The operation preserves item identity, style, transforms, masks, clips, contour order, starting anchors, open/closed state and unselected contours. Source-edge indices in its report refer to the input path's zero-based edges within each contour, excluding move/close commands. Ordinary anchor indices change after a reduction; query them again. The complete edit batch remains atomic, locked paths reject edits, and session undo restores the original commands exactly.

## Proposed reductions

One deterministic left-to-right pass tries the largest allowed span first. It tries a line, then cubic least-squares fits using uniform or endpoint-projection parameter intervals. The fit samples each original segment at quarters, with endpoints fixed. It is only a proposal: floating-point fitting cannot authorize an edit. Single cubics may become lines, which removes two control points even though the edge count does not change. Earlier accepted spans are not reconsidered in that operation, so every deviation certificate compares directly against disjoint segments of its original input; errors never accumulate through internal passes.

Every source segment and the proposed segment must have a strictly increasing projection along the span's endpoint chord. This is proved by nonnegative projections of the three derivative control vectors and a positive endpoint difference for every source segment. Loops, reversals and ambiguous or degenerate spans are retained. It then checks both deviation and topology as described below. A candidate failing either check is retained or replaced by a smaller provable span. Retention is reported explicitly; no tolerance relaxation or unverified fallback occurs. This conservative algorithm does not promise a globally minimal path or simplification of every input span.

## Exact deviation certificate

Encoded finite f64 coordinates, the supplied tolerance and the composed world matrix are converted to exact binary rationals. Lines are degree-elevated exactly. For each original segment, restrict the candidate cubic to that segment's declared global parameter interval using exact rational arithmetic. Subtract the two sets of cubic Bernstein controls, apply the metric's linear transform to each difference, and find the maximum squared control-vector length D.

Bernstein weights are nonnegative and sum to one. The curve difference is therefore a convex combination of these vectors, so its length is at most `sqrt(D)` throughout the entire interval. Accept only when `D <= tolerance^2`, comparing exact rationals. The increasing, continuous parameter map covers both curves, giving the same bound in both directions. This is a geometric bound, not just an estimate from sampled points.

Local mode uses the identity metric. World mode uses the engine's composed f64 affine matrix, including hierarchy, reflection and shear; its stored values are then treated exactly by the certificate. Translation cancels. This does not remove the ordinary floating-point error in the preceding matrix composition or the renderer's f32/coverage quantization. Stroke joins and raster tessellation may change edge samples after segmentation changes; the bound applies to the mathematical centerline geometry, not pixel equality or painted stroke area.

## Preserved topology

For a proposed span, form the exact convex hull of every original and proposed control point. It contains the full straight interpolation between corresponding old/new curve points throughout a deformation. The strict projection condition keeps each intermediate span injective with the same direction and fixed endpoints.

Compare this swept hull against the control hull of every other current segment in the compound path. Include explicit closing edges, and also implicit closing edges of open contours when the item has a fill. Exact separating-axis tests must prove that the hulls are disjoint or intersect only at one fixed, shared endpoint. Contact faces are projected along the separating line: an overlap interval of positive length is rejected, even if a sampled view looks harmless. Strict comparisons use arbitrary-precision rationals; no epsilon merges nearby boundaries. All other current segments, including earlier accepted reductions, participate in the check.

Consequently the span cannot create, remove or move an intersection with the remaining path during this deformation, or intersect itself. Composing accepted deformations preserves the compound path's connections, crossings, winding orientation and holes. Existing crossing/loop regions can remain unchanged while independent regions simplify. The proof is scoped to this item's compound path, including its fill closure; it does not preserve geometric relationships to other items, stroke outlines, masks or clipping boundaries. Those can move within the stated centerline tolerance, just as with an ordinary geometry edit.

## Evidence returned to agents

The edit change has `details` containing:

- Input/output/removed edge counts, `changed`, tolerance and metric matrix.
- A floating upper `deviation_bound`, independently checked against the exact value before returning it.
- `maximum_deviation_squared`, encoded as an exact integer or rational string, and the certificate identifier.
- Every reduction's contour, original edge indices, resulting edge index/type, exact parameter boundaries and exact squared bound.
- Counts of retained candidate attempts by monotonicity, deviation or topology, and charged work units. These are attempt counts, not unique retained-edge counts.

A valid call with no provable reduction succeeds with `changed:false` and explicit reasons. As with other edits, a successful call advances revision, even if geometry stays the same. Limits or malformed/unsupported requests fail the whole batch. Session receipts retain the report, and same-request retries return it without recalculating. The report is not stored as geometry in the document.

One operation has a 400,000-unit certificate budget, charged for hull preparation, projections, monotonicity and segment restriction. Span size, the ordinary 4,096-command document cap and finite coordinate bounds also bound exact arithmetic. A large or crowded path can exceed this conservative budget; choose selected contours or a smaller span. Session receipt size remains capped at 65,536 bytes, so very large rational reports can also fail atomically. The operation never silently truncates its proof or commits a partial result.

The reduction algorithm and fixtures are original. Exact arithmetic uses the external, locked [num-rational interface](https://docs.rs/num-rational/0.4.2/num_rational/type.BigRational.html); package licenses are retained in THIRD_PARTY_NOTICES.md. Independent tests use Python fractions and power-basis polynomial substitution rather than the engine's de Casteljau implementation. They verify exact reported bounds, sampled deviations, selected-contour preservation, winding/occupancy, shared boundaries, tiny offsets, fill closure, lock/work failures and session recovery. Existing split/join/reverse checks complete the extended curve-editing contract.

Run `python examples/simplify_workflow.py C:/absolute/new-directory` to reduce an original diagram connector, retain the certificate and restore the original with undo.
