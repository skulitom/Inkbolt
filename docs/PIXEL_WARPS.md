# Retained pixel deformation

An image or inline pixel item can carry an optional `pixel_warp`. Original
pixel bytes, asset identity and crop remain unchanged. The `pixel_warp` edit
replaces these controls, or clears them with `warp:null`. Snapshots, duplicate
items, transfers and durable session history retain them independently.

The map operates in the image's local frame: `[0,width] × [0,height]`.
For a cropped asset, that frame corresponds to the declared crop. Item and
ancestor transforms apply after deformation. Effects, opacity, geometric
clips, grayscale/artwork masks, layer clipping and compositing then use the
ordinary rendered item. Layout bounds use the deformed boundary.

## Map types

`{type:"perspective",corners:[topLeft,topRight,bottomRight,bottomLeft]}` maps the
entire source rectangle to a convex quadrilateral. Corners are absolute local
positions. Reflected orientation is supported. The original rational homography
calculation shared with vector warps supplies forward/inverse coefficients;
pixel sampling evaluates them in f64.

`{type:"mesh",columns:2,rows:2,points:[...]}` uses a regular source grid with two
intervals per axis and nine row-major absolute destination positions. Each cell
has a fixed top-left to bottom-right diagonal. Both triangles use affine
interpolation, giving a continuous piecewise affine deformation. Boundary and
interior controls remain editable.

`{type:"articulated",columns:2,rows:4,joints:[...],weights:[...]}` computes the
destination grid from a weighted joint hierarchy. Each joint declares a
bind-frame `pivot`, relative rotation `angle` in degrees, optional
`translation` (default zero), and optional `parent` index. A parent must precede
its child. Local rotation is about the declared bind pivot; its matrix is
multiplied by the parent pose. Each vertex has one weight per joint.
Weights in `[0,1]` must sum to one within `1e-10` and are normalized during
evaluation. The weighted transformed bind positions become the mesh controls.
Zero-weight joints remain declared dependencies. Joint matrices and evaluated
vertices are inspectable.

## Inverse, clipping and sampling

Every destination triangle must be nondegenerate with a consistent orientation.
The boundary must be simple, without nonadjacent contacts or any overlapping
edges. These conditions on the triangulated rectangular disk ensure a unique
inverse in its interior; global reflection is permitted. Folds, self-overlaps
and collapsed cells return `NONINVERTIBLE_WARP`. Near-singular triangles fail
with `UNSUPPORTED` before rendering.

The renderer maps each output pixel center through the inverse item/ancestor
transform and then the inverse deformation. Nearest or premultiplied bilinear
sampling reads the original crop. Mesh seams use a single boundary coverage
pass, so triangle edges do not composite separate alpha surfaces.

Coverage outside the deformed boundary is transparent. When an antialiased
boundary pixel has its center outside the shape, its color comes from the
nearest destination boundary point mapped back to the source. Projective edge
positions use the projective inverse, not linear source-edge interpolation.
Equal-distance edges use boundary order. Ordinary document/frame/item clipping
still applies. Pixel reconstruction is f64 and RGBA8 quantization happens through
the existing compositing/export pipeline; this is not the exact geometric
certificate used by retained vector warps.

Area/bicubic/Lanczos reconstruction currently fails explicitly on deformed items;
select nearest or bilinear. Native brush, retouch/repair and permanent mask
application require clearing deformation first, editing the source, then
reapplying its saved controls. Literal native `pixel_fill` and source content
replacement remain available and retain the modifier. This avoids silently
using an affine-only selection/donor coordinate interpretation.

PNG/JPEG/TIFF exports render the retained map. Snapshots preserve editability.
SVG export explicitly rejects pixel deformation; it does not emit an undeformed
image. Shared image components, asset replacement, transfer, artboards and
canvas scaling retain controls and ordinary lock/dependency checks.

## Inspection and limits

`pixel_warp.inspect` accepts `warp`, source-frame `width` and `height`,
`samples` (forward), `inverse_samples`, `include_mesh` and ordinary
`control` options. The combined sample limit is 256. Out-of-domain points return
null. Results include saved controls, mapped points and reverse checks, optional
source/destination vertices, triangle indices, boundary indices, joint matrices
and local bounds. Exact declared control vertices map to their paired vertices.
At other boundary locations, f64 encoding can move a forward sample just
outside the exact polygon; inspect null inverse results accordingly.

Grid interval counts are 1–16 per axis; joints are 1–16. Coordinates remain within
±32768, source-frame dimensions within `0.001..=32768`, and joint angles within
±360 degrees. Minimum destination triangle altitude is `1/1024` local units;
twice-area divided by squared longest edge must be at least `1/1048576`.
Perspective homogeneous corner weights have the existing `[1/1024,1024]` limit.

Destination vertices, joints and scalar weights participate in the document's
4096-control budget, including hidden items. Inverse sampling work is bounded by
67,108,864 units across items, using output pixels times
`2*columns*rows + 2*columns + 2*rows + 4` per map. Artboard ranges add this cost to
their shared budget. Ordinary source-pixel, asset, output, world-coordinate and
compositing limits also apply. Unsupported or over-budget edits are atomic.

Original tests in `tests/test_pixel_warps_cli.py` independently solve projective
maps, invert triangles with rational arithmetic, evaluate joint poses, check
coordinate-chart colors and premultiplied interpolation, inspect boundary
sampling, reject overlaps, verify seamless alpha, and exercise source retention,
locks, sessions, transfers and publication.
