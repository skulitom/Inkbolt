# Editable vector strokes

Optional `stroke.brush` replaces the ordinary ribbon with original rigid filled motifs along the path, including width profiles, editable spacing, custom endpoints/corners and both scaling policies. See [VECTOR_BRUSHES.md](VECTOR_BRUSHES.md). Brush expansion may retain cubic motif commands. Default cap/join/miter settings are required and dash/arrow combinations fail explicitly.

Vector content has an optional `stroke` with a shared `color` paint, `width`, `cap`, `join` and `miter_limit`. Width is 0.001..1024; caps are `butt`, `round` or `square`; joins are `miter`, `round` or `bevel`; miter limits are 1..16 (default 4). `scaling:"object"` (default) transforms the entire locally evaluated stroke with the item and ancestors. `scaling:"document"` evaluates width, dashes, arrows and tolerance in document logical units after transforming the centerline. Paints remain item-local. See [TRANSFORMS.md](TRANSFORMS.md) for composition, pivots, independent placements and fixed-width behavior. Geometry bounds and alignment exclude the live stroke; expanded outlines are ordinary filled geometry and contribute their own bounds.

```json
{
  "color": [30,100,210,255],
  "width": 2,
  "cap": "round",
  "join": "round",
  "dash": {"array": [6,4], "offset": -2},
  "width_profile": [[0,0.5],[0.5,2],[1,1]],
  "end_arrow": {"kind":"triangle","length":8,"width":6}
}
```

Use the existing `vector` edit to replace geometry and appearance in an atomic batch. Inspection returns saved stroke controls. Snapshots and durable sessions retain them through undo, redo and retries. Paint sampling, masks, content fill, item opacity and effects apply through the ordinary pipeline. Overlapping ribbons, dashes and arrowheads receive stroke paint once in the combined nonzero coverage field.

## Dash lengths and phase

The optional `dash` object retains an `array` and signed `offset` in the declared stroke units. Intervals alternate painted length and gap length. Odd lists repeat twice before cycling. Positive offsets advance into the pattern; negative offsets wrap. Each contour starts the same pattern independently. Closed contours join across the seam when a painted run crosses it. Caps apply at dash ends, and joins apply at interior evaluated vertices. An empty or all-zero list is solid. A zero painted interval can form a round or square dot; butt caps have no area. A gap ending exactly at the terminal point does not start another zero-length dash there.

Arrays have at most 64 entries, each zero or a finite number in 0.001..32768. Offset defaults to zero and lies in -32768..32768. Stored odd lists, signed offsets and all-zero patterns remain editable. Defaults remain solid, butt-capped, miter-joined strokes.

## Width profiles and arrowheads

`width_profile` is an optional list of 2..64 `[position,factor]` knots. Positions increase strictly from 0 to 1 along the complete evaluated contour length; factors interpolate linearly. Actual width is `width * factor`. Factors lie in 0..1024 and actual widths cannot exceed 1024. Zero permits tapered tips or an empty shaft. Omission or an empty list means factor 1. Profiles restart at each contour, continue through dash gaps and require equal endpoint factors on closed contours. A zero-length contour uses position 0.

Each evaluated segment is a trapezoid between its endpoint cross-sections. Joins connect those sections at the common node width. Outer joins use a bevel, circular sector or miter intersection, with bevel fallback when the distance from vertex to miter tip divided by half-width exceeds `miter_limit`. Inner boundaries retain the center vertex to preserve coverage when a ribbon folds or is wider than a short segment. Round exact reversals retain circular coverage. This is Inkbolt's explicit piecewise ribbon model.

`start_arrow` and `end_arrow` independently accept `{kind,length,width}`. Kinds are `triangle`, `chevron`, `diamond`, `ellipse` and `bar`; length and width are finite dimensions in the declared stroke space in 0.001..1024. They do not scale with the width-profile factor or disappear in dash gaps. Each contour gets its requested endpoints. The shaft is trimmed to half the arrow length from that endpoint, with a butt cut at the attachment; dash phase and width-profile positions still refer to the complete original contour. Overlapping trims can leave arrows with no shaft. Arrow tips lie on the original endpoints, and the body extends backward by `length` along the outward tangent, centered across `width`. Original cubic handles determine endpoint directions, skipping coincident handles; a wholly degenerate contour uses -x at the start and +x at the end. Closed contours can have coincident tips with distinct outgoing and closing tangents.

In arrow coordinates with the tip at `[0,0]`, length `L` and half-width `W`, triangle vertices are `[0,0],[-L,W],[-L,-W]`; chevrons add a notch at `[-0.65L,0]`; diamonds have their widest section at `-L/2`; bars fill `[-L,0] Ãƒâ€” [-W,W]`. Ellipses are centered at `[-L/2,0]` with radii `L/2,W`. These are project-owned shapes, independent of external marker inventories.

## Editable expansion

Apply `{"op":"stroke_expand","id":"link","fill_id":"link-fill","stroke_id":"link-outline"}`. Both child IDs must be valid, distinct and unused. The item must be an unlocked vector with a stroke; affected dependency locks also apply.

The original ID becomes an isolated group retaining its transform, parent, visibility, opacity, content fill setting, blend, clips, masks, effects and filters. A neutral child preserves the original centerline geometry, fill and fill rule, with no stroke. A second neutral child stores the generated closed line contours with the original stroke paint and nonzero filling. Empty stroke coverage omits that second child and reports `stroke_id:null`. The change receipt reports command count, tolerance, child IDs, source scaling, future filled-geometry scaling and whether coverage was empty. Sources remain unchanged; the returned snapshot is the expanded result. Session history restores the editable stroke controls.

Expansion freezes the current evaluated outline and maps document-scaled outlines back into item coordinates. Later transforms scale the filled geometry normally. Direct expansion of document-scaled strokes in reusable source definitions fails explicitly because placements can require different outlines; unlink an intended component placement first. Filled outlines can contain overlapping or self-intersecting contours; expansion does not promise a welded Boolean boundary. Ordinary path edits, transforms, fills and geometry operations remain available. If the result exceeds stored geometry, item, coordinate or document limits, the entire edit fails without partial changes.

## Evaluation, precision and limits

Original f64 geometry now evaluates all strokes. This replaces the previous backend dash/stroke conversion and separate cap fallback; curved or antialiased edge pixels can differ from version 0.32.1. Cubics subdivide by de Casteljau until control points lie within `curve_tolerance` of the chord and the allocated control-polygon/chord length gap passes. Length error is divided across curves and child intervals. Dash cuts and profile positions use the resulting polyline length. Parametric shapes use the existing documented path conversion.

`curve_tolerance` defaults to 1/64 declared stroke unit and accepts 0.0000001..1. Evaluation automatically tightens this saved maximum for the current placement. With linear matrix `[a,b,c,d]`, the conservative stretch bound is `sqrt(max(abs(a)+abs(c),abs(b)+abs(d)) * max(abs(a)+abs(b),abs(c)+abs(d)))`; document-scaled strokes use identity after mapping the centerline. The evaluated tolerance is `min(saved, (1/64)/max(1,16*stretch))`. The factor 16 anticipates the maximum raster density (export scale 4 with supersampling 4), so rendering, expansion and outlined exports share one outline at the current placement. Internal refinement can fall below the saved-control minimum without rewriting source controls. Expansion receipts report both `curve_tolerance` and `evaluated_curve_tolerance`, plus `outline_resolution:16`.

Circular and elliptic sectors use the evaluated tolerance for conservative sagitta subdivision. These are centerline chord, allocated length and round-sector subdivision bounds, not a certified global offset, topology or raster-error bound. Future transforms of expanded geometry do not regenerate the outline. A generated subdivision vertex may coalesce with an authored cut only at the same rounded point with bounded position/radius roundoff; distinct authored cuts or knots below coordinate precision still fail explicitly.

The licensed tiny-skia 0.12.0 backend fills the generated nonzero outline once. Its display rasterization uses f32 geometry and a 4Ãƒâ€”4 antialias grid encoded as gray8; gray8 storage does not imply exact pixel-area coverage. Exact geometry checks and independently sampled display checks are separate. Paint evaluation and compositing retain their existing f64 contract.

Limits are cumulative and include hidden content:

- At most 16,384 flattened points per contour, subdivision depth 24 and 65,536 generated outline commands per document. Transformed outlines must stay within the existing Ã‚Â±65536 geometry bounds. Expansion also obeys the 4096 per-path stored geometry/clip command budget and the selected document storage profile.
- Dash traversal uses the control-polygon bound `(ceil((1.01 * length_upper + edges + 1) / period) + 2) * intervals + edges`. Document, repeated-mask render and PNG artboard-range caps are 32,768, 131,072 and 524,288 work units.
- Generated commands times output height share a 67,108,864 scan-work cap across a render and its mask instances. PNG ranges include this work in their existing aggregate budget.
- SVG counts generated outline copies, including mask instances: at most 131,072 commands per export and 262,144 per artboard range. Ordinary native SVG strokes do not generate outline copies.

Existing paint, pixel, mask, buffer, output and storage limits also apply. Failures are explicit, never partial exports or substituted solid strokes.

## SVG exchange

Object-scaled constant-width strokes with default tolerance retain native editable cap, join, miter and dash attributes. Import resolves inherited attributes and inline styles, converts supported absolute units and preserves local values. Percentages, relative units and malformed/unsupported declarations fail explicitly, including unused invalid declarations. SVG consumers can use different curve-length and rasterization approximations.

Width profiles, arrowheads, document scaling or a custom tolerance export as filled outline geometry with a stated loss of editable stroke controls. Original fills retain their own fill rule; stroke gradients remain attached to the outline paint. Shared masks evaluate each reference placement; artboards evaluate their independent export coordinates. Keep snapshots to retain profile/arrow controls, or expand explicitly when editable path outlines are the intended deliverable. Arbitrary SVG marker elements and vector effects are outside the declared import subset and fail explicitly.

Public reference: [SVG stroke, join and dash semantics](https://www.w3.org/TR/SVG2/painting.html#StrokeShape). The ribbon model, arrow shapes, evaluation, expansion and synthetic fixtures are original Inkbolt designs; no application implementation or specification sample code was copied.
