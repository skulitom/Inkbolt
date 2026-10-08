# Fill, layer effects and coverage

Printable drawable items and isolated groups support `fill_opacity` (0..1,
default 1), an editable `effects` list and a `coverage` control. Defaults are
omitted from snapshots; existing snapshots keep their original meaning. The
`properties` edit changes fill/coverage, and `effects` replaces the full list.
Both work through the Rust library, JSON CLI and MCP, with locks, atomic
validation, inspection, semantic comparisons and persistent undo.

## Evaluation order

1. Render geometry, pixel/image sampling or children; evaluate editable filters
   and bound adjustments. Assemble any clipped members, including their own
   fill/effects, while retaining the base alpha.
2. Retain this completed source alpha `A` for every layer effect. Build shadows
   below the content in effect-list order.
3. Multiply source premultiplied RGBA by `fill_opacity`. Apply color overlays in
   list order, then composite that result over the shadows.
4. Apply strokes above that result, in list order. Every effect uses the same
   original `A`; effects do not feed their coverage into later effect geometry.
5. Apply item masks, clips, overall opacity and coverage sampling; blend the
   complete decorated image with the backdrop using the selected color mode.

Fill fades content while preserving the effects' source and strength. Overall
opacity fades the complete decorated result. Thus fill zero can leave an
outline or shadow visible; opacity zero hides everything. With no effects,
fill and opacity multiply source coverage and are equivalent. Color-mode
equations remain those in [BLENDING.md](BLENDING.md); this engine does not
substitute undocumented mode-specific fill equations.

## Editable effects

An effect contains `id`, `operator`, `color` (RGBA8 or a shared paint field),
`enabled` (default true), `opacity` (0..1, default 1), `scale` (default 1) and
optional `contour` knots (default identity). IDs are unique within their item. Disabled
entries retain all controls and remain subject to validation/count limits.

| Operator | Parameters | Coverage and color |
| --- | --- | --- |
| shadow | offset `[dx,dy]` in -256..256; sigma 0..16 | Gaussian blur of A, shifted with bilinear sampling and colored |
| lit_shadow | distance 0..256; sigma 0..16; optional azimuth in -360..360 | Shared or local light direction determines the shadow offset |
| stroke | integer radius 0..32; position outside/inside/center | Euclidean disk maximum/minimum alpha difference, colored |
| overlay | no additional parameters | Color replacement conditional on original source coverage |

All effects operate on the current render viewport with transparent samples
outside it. A layer's off-viewport geometry is retained in the snapshot but
does not contribute to these viewport effects. Render a larger canvas or a
larger artboard bleed to include it. This viewport model matches the editable
filter domain; it is not an unbounded offscreen appearance evaluation.

Offsets, Gaussian sigma and stroke radius are document-pixel values, multiplied
by effect scale and export scale. Item transforms place the source before effects run; they do
not rotate or resize the effect parameters. Radius `r` samples integer offsets
with `dx*dx+dy*dy<=r*r`. If D and E are the disk maximum and minimum of A,
outside stroke coverage is D-A, inside is A-E, and center is D-E. Radius zero
has zero coverage. A centered stroke spans radius r on each side. Stroke
effects are raster alpha decorations, separate from editable vector strokes.

Gaussian weights are proportional to `exp(-0.5*(distance/sigma)^2)`, truncated
at ceil(3*sigma) and normalized along each axis. Sigma zero copies A. The blur
is shifted after convolution; a fractional offset interpolates four samples.
Shadows use ordinary source-over onto the shadow plane. Strokes use ordinary
source-over above content. Color alpha and effect opacity multiply coverage.

For an overlay with effective strength `q=color_alpha*effect_opacity`, current
premultiplied content P and alpha a become `P*(1-q)+A*q*color` and
`a*(1-q)+A*q`. This preserves original source alpha when fill is one, including
translucent edges, and can show the colored silhouette when fill is zero.

Effect kinds have fixed placement; list order orders shadows (both shadow
operators together), overlays and strokes within their respective categories.
Multiple effects remain independently editable. Arbitrary category placement
is not implied.

## Shared lighting, scaling, curves and gradient colors

Documents retain `global_light:{azimuth:225}`; the default value is omitted
from snapshots. The `global_light` edit takes a `light` object with that field.
Angles are degrees clockwise from positive canvas x in downward-positive y,
pointing toward the light source. A lit shadow uses offset
`-distance*[cos(azimuth),sin(azimuth)]`. Cardinal directions are exact. Omit its
operator's `azimuth` to follow document lighting, or supply a local override.
Explicit-offset shadows remain unchanged by global lighting. A light edit
respects locks on every globally linked effect owner and its subtree, including
disabled effects. Standalone artboard exports use the saved angle in the board's
local export coordinates, just as other effect parameters use that viewport.

Effect `scale` must be in 0.001..1024. Stored and scaled geometry must remain
within the existing document-pixel limits: sigma <=16, stroke radius <=32,
each explicit offset component <=256 and lit-shadow distance <=256. Export
scale subsequently multiplies these parameters. Fractional effective stroke
radii evaluate the integer sample disk directly without rounding the radius.
The `effects_scale` edit multiplies every saved effect scale on an explicit
nonempty set of unique item IDs by `factor` (0.001..1024), including disabled
entries, with atomic validation and ordinary locks. It never changes source
geometry, pixels, gradients or child effects implicitly. Overlay coverage has
no spatial size parameter, so this scale does not change an overlay by itself.

A contour is an ordered array of 2..64 `[input,output]` knots in 0..1. Inputs
must increase strictly, the first point must be `[0,0]`, and the last input
must be 1. Outputs can rise or fall; piecewise linear interpolation defines
the mapping C. An empty array means identity. Zero remains zero, so a contour
cannot paint regions with no source effect coverage. Shadows apply C after
blur and shift; strokes apply it to their disk difference field. Overlays
use C(A) in place of A in the conditional replacement formula above. Thus
custom overlay contours can intentionally change alpha; identity contours
retain the earlier alpha-preservation contract. Every effect still samples
the same original source alpha, not preceding effects' coverage.

Effect colors accept the same solid, linear, radial, freeform and repeating
pattern paints as document artwork, including gradient spread, transparency,
color interpolation and paint transforms. Sample colors at output pixel
centers in item-local coordinates through the full world transform. The
effect geometry scale does not change this paint coordinate system. Use the
paint's own transform to scale or reposition its gradient/pattern. This keeps
color layouts attached to transformed artwork while allowing independent
shadow distance, blur and outline thickness. Paint alpha and effect opacity
multiply the mapped coverage. For overlays, sampled color alpha defines q.
All controls survive inspection, diffs, snapshots and persistent undo/redo.

## Repeatable dissolve

Coverage is `{type:"smooth"}` or `{type:"dissolve",seed:U32}`. Dissolve turns
the final source alpha into binary coverage; it is independent of the color
blend mode and can accompany any of the 26 modes. The alpha probability already
includes source transparency, fill, effects, masks/clips and overall opacity.
Clipped members sample this probability before mixing into the base; their
binary coverage still preserves the base's alpha.

At each output pixel center, inverse-map to item-local coordinates, then floor
x and y into signed unit cells. Hash the byte prefix `inkbolt.coverage.v1\0`,
the seed as little-endian u32, and the cell x and y as little-endian i64 with
SHA-256. Read the first four digest bytes as little-endian u32, k. The pixel
is covered when its alpha is strictly greater than `(k+0.5)/2^32`. Exact zero
and one stay zero and one. Covered pixels retain their straight source color;
uncovered pixels contribute nothing. There is no mutable random state.

The pattern follows item transforms. Export scale resolves the same local
unit cells, rather than generating a new random pattern. Distinct items with
the same seed and local coordinates share the pattern; changing an ID has no
effect. Set distinct seeds for independent textures. A snapshot preserves the
seed; undo restores the exact pattern. Patterns near transformed cell boundaries
use the engine's f64 inverse transform and floor convention.

## Bounds and interchange

There are at most eight effects per item and 64 per document. Render work for
all enabled effects, including hidden items, is bounded at 67,108,864 declared
work units. With s = effect scale * export scale, per-pixel shadow work is
`2*(2*ceil(3*sigma*s)+1)+24`, stroke work is
`(2*ceil(radius*s)+1)^2+16`, overlay work is 12 and dissolve work is 32.
Each effect additionally charges its contour knot count and, for a paint
field, eight plus the shared paint work cost. Effect paints join the same
document pixel, stop/anchor and serialized-size limits as ordinary artwork.
Disabled controls and paints remain validated and count toward storage.
Two additional full RGBA buffers are conservatively reserved when any effects
are stored. Artboard ranges also aggregate this work before producing outputs.

Pass-through groups, adjustments, work paths and mask-source artwork reject
non-default fill/effects/coverage controls explicitly. SVG exports ordinary
fill by multiplying its opacity; layer effects and dissolve are rejected even
if hidden or disabled. PNG and snapshots retain the supported behavior.
Native mask application rejects effects/dissolve to prevent changing evaluation
order. Canvas edits with filters or effects require explicit
`effect_policy:"preserve_parameters"`; parameters stay fixed while the source
and viewport change. Original source documents, media and effect settings are
never destructively baked by these controls.

The existing f64/8-bit coverage and final RGBA8 rounding contracts apply.
Independent fixtures verify exact alpha algebra, full effect boundaries,
Gaussian fields, local signed hash cells, all color modes, transformed exports,
resource limits and durable history. No external application, model or network
service is needed.
