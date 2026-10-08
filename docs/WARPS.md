# Retained vector deformation

`content.type:"warp"` stores original geometry, fill/stroke, fill rule, an ordered
`maps` array and a local error `tolerance`. Agents can update the whole spec with
the `warp` edit and inspect source/control positions before producing ordinary
editable vector paths with `warp_expand`. Expansion preserves the item ID and
appearance; the input snapshot and session history retain the source.

The model supports original line/cubic geometry and ordinary expanded primitives.
It applies to a vector item or a vector item inside a shared mask source.
Reusable component placements, parents, effects, masks, transfer, artboards,
durable sessions, PNG and SVG use the same evaluated geometry. SVG carries an
explicit loss of retained deformation controls. Snapshots retain all controls.

## Maps and coordinates

- `affine`: a standard `matrix:[a,b,c,d,e,f]`.
- `perspective`: `domain:[x,y,width,height]` and four `corners` in domain order
  top-left, top-right, bottom-right, bottom-left. The corners define an exact
  rational projective map of the rectangle. A strictly convex reflected order
  is permitted. Singular, concave and crossed quadrilaterals fail. Normalized
  homogeneous corner weights must lie in `[1/1024,1024]`.
- `envelope`: the same rectangular `domain` and `points`, a row-major 4 by 4
  array of absolute destination positions. These define a tensor bicubic
  Bernstein surface over normalized domain coordinates. Boundary controls can
  curve the edges; interior controls deform the interior. They are control
  positions, so only the four corner controls are interpolation points.

Maps run in array order on the previous map's result. This is editable nesting,
including multiple nonlinear maps within the degree/work limits. For each
perspective/envelope step the entire positive homogeneous control hull must fit
its declared input domain. Out-of-domain hulls fail with `WARP_DOMAIN`, even if a
curve would happen to lie inside it. There is no implicit extrapolation or
clipping. A later ordinary item clip can clip the result.

The stack maps centerline/fill geometry first. Paint and stroke use the resulting
ordinary geometry in item-local coordinates; width is not itself deformed by
the maps. Expand a stroke to filled outlines first to deform its outline.
Filled source contours must be explicitly closed, including their implicit
closing line. Open centerlines require `fill:null`. Fill rules remain ordinary
`nonzero` or `even_odd`. Envelopes may fold; no inverse, bijection, topology or
minimum feature-size guarantee is claimed. Pixel warping, arbitrary hierarchy
envelopes and direct text deformation are separate operations; expand original
shapes/text to paths when appropriate.

Item and ancestor transforms apply after deformation. The tolerance is in
**warp-local units**; subsequent scaling can amplify it. Geometry bounds describe
the emitted path and exclude stroke, effects and clipping.

## Inspection and reusable grids

`warp.inspect` accepts `warp`, up to 256 `samples`, optional `grid`,
`include_geometry`, `include_segments` and ordinary `control` options.
It returns saved maps, mapped sample positions, emitted bounds/command count,
maximum certified error, arithmetic work, and optional ordinary path geometry.
Each segment receipt identifies its source contour/edge, dyadic parameter
interval, encoded endpoints, degree and error bound.

An optional `grid:{domain:[x,y,width,height],columns:2,rows:2}` builds source-domain
lines through the same stack. Counts denote intervals, so that example yields
three vertical and three horizontal lines. The result includes open path
geometry and segment certificates. Agents can add it as a nonprinting work path
or an ordinary stroked vector item. Perspective grids have projective placement;
envelope grids expose nonlinear interior curvature. Grid geometry is an
inspection result and is not silently added to the source document.

## Error certificate

Input floats are interpreted as exact binary rational numbers. Original curve
segments become homogeneous rational Bernstein curves `N(t)/W(t)`. Affine and
projective maps transform those coefficients exactly. Tensor bicubic composition
uses exact Bernstein polynomial products, raising degree by at most six per
envelope. No intermediate approximation is inserted between maps.

For a candidate leaf, `L(t)` is the linear interpolation of its **encoded output
endpoints**. The engine constructs exact Bernstein coefficients of
`D(t)=N(t)-W(t)L(t)` by degree elevation and multiplication. If the minimum
positive denominator coefficient is `w` and maximum absolute coefficients of
the two numerator coordinates are `dx` and `dy`, then
`sqrt(dx²+dy²)/w` bounds the Euclidean deviation from that chord throughout the
leaf. Acceptance compares squared rationals against the requested tolerance.
The reported floating bound is rounded upward and checked against the exact
squared bound; underflow receives a conservative finite upper bound.

Rejected leaves split exactly at one half. Shared endpoints stay shared, and
every original edge receives contiguous complete parameter coverage. The
certificate includes endpoint encoding error. It is relative to the ordinary
line/cubic expansion of primitives: an ellipse's existing four-cubic
representation has its own approximation to the analytic ellipse, outside this
additional deformation bound. Raster antialiasing and SVG consumer edge coverage
are also separate from geometric deviation.

## Explicit limits

There are 1–8 maps; source geometry has at most 256 line/cubic edges after
primitive expansion and closing-edge insertion. Tolerance is `0.000001..=1`,
default `0.01`. Coordinates lie within ±32768; domain dimensions lie within
`0.001..=32768`. Grids support 1–16 intervals per axis.

Exact curves have degree at most 128, rational coefficient numerators and
denominators at most 8192 bits, subdivision depth at most 24, and at most
4096 generated commands. Source controls count toward the stored 4096-command
budget. A shared 2,000,000-unit arithmetic budget and aggregate generated-command
budget cover all warp items, including hidden items. Work units are conservative
accounting units, not elapsed time or CPU instructions. Inspection samples and
grids share its budget. Too-deep composition is rejected before evaluation;
resource exhaustion fails explicitly without changing or publishing the source.
Ordinary document, style, transform and rendering limits still apply.

Original executable coverage is in `tests/test_warps_cli.py`. It includes a
separate rational linear-system solver for projective maps, direct tensor
evaluation, exact sampled checks against every segment certificate, nesting,
curved grids, persistence, bounds, fills/holes, shared sources, exports and
resource errors. `examples/warp_workflow.py` produces four original retained
fixtures with inspection, expansion and delivery receipts.
