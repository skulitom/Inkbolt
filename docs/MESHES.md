# Editable color meshes

A `mesh` paint describes an original rectangular field of shared bicubic patches. Agents can use it for smooth icon shading, backgrounds and controlled transparent color transitions. The same field works in vector fills and strokes, procedural raster fills and other shared-paint consumers. Geometry coverage and layer composition remain separate.

```json
{"type":"mesh","space":"srgb","mesh":{"origin":[0,0],"size":[64,48],"columns":2,"rows":2,"knots":[{"color":[230,70,40,255]},{"color":[40,170,190,255]},{"color":[100,60,180,64]},{"color":[230,190,80,192]}]}}
```

Knots are row-major. Each knot has straight RGBA8 `color` and optional `offset:[x,y]` in paint-local units (default zero). `origin` and `size` define the fixed rectangular boundary; samples outside it are transparent. `transform` is the existing invertible affine paint transform. Interior offsets move the corresponding color knots. Boundary offsets must be zero. Reflection, rotation, shear and overall placement use `transform`; folded grids and curved outer boundaries are explicitly unsupported.

`mesh_knot` edits a vector fill/stroke or procedural raster fill atomically:

```json
{"op":"mesh_knot","id":"shading","target":"fill","column":1,"row":1,"color":[100,150,220,96],"offset":[2,-1]}
```

`target` defaults to `fill`; `stroke` selects a vector stroke. Supply at least one of `color` or `offset`. Indices are zero-based. Existing item, ancestor and shared-definition locks apply. Snapshots, semantic comparisons and durable undo/redo preserve every knot, alpha value, grid dimension, transform, interpolation space and export-sampling setting.

`mesh.inspect` accepts `mesh`, optional `space` (`srgb` or `linear_rgb`) and `parameters:[[u,v],...]`. Parameters range from zero through `columns-1` and `rows-1`. Its result reports physical positions, geometry tangents, Jacobians, interpolated color/alpha and their derivatives, encoded colors and inverse parameters. Inspection is read-only and exposes the contraction and color-derivative bounds used by the renderer.

## Numerical contract

Original tensor Hermite interpolation uses one-sided differences at the boundary and centered differences at interior knots. Mixed differences complete each shared knot jet. Geometry and color use those same shared derivatives on either side of a patch join, so first derivatives agree up to f64 roundoff. Each color channel's three derivatives are scaled together at a knot when necessary to keep all adjacent Bernstein controls inside `[0,1]`. This keeps RGB and alpha bounded while preserving knot values and continuous first derivatives. Alpha is always linear and straight; RGB interpolation is explicitly encoded sRGB or linear RGB. Continuity is measured in that declared space.

Displacements are normalized to grid units. Outward-rounded Bernstein derivative bounds constrain the maximum row sum of the displacement Jacobian to `q <= 0.75`. The map is identity plus this displacement, with zero displacement on the outer boundary. The bound guarantees a unique inverse and positive orientation over the rectangle. Projected fixed-point inversion uses at most 128 iterations; its early stopping threshold is `1e-13 * (1-q)` grid units. Reported bounds concern the encoded polynomial controls; normal floating-point evaluation roundoff remains. Large or folding offsets return `MESH_GEOMETRY_LIMIT` before any document mutation is committed.

Boundary classification compares physical coordinates with the saved origin and far corner before normalization. Boundary inspection pins those endpoints exactly; normalized interior values are clamped only after the physical containment check. This prevents cancellation at fractional origins from making a valid corner transparent, while points beyond the physical rectangle remain outside. Small extents at large origins retain ordinary f64 coordinate resolution.

PNG and TIFF use the continuous mesh evaluator and preserve the existing final RGBA8 quantization contract. JPEG retains its separate lossy/alpha policy. Raster procedural fills retain optional existing dithering. Masks, opacity, blends and effects use their existing ordering and coordinate semantics.

## SVG delivery and losses

SVG retains vector shape/stroke geometry and embeds a sampled PNG mesh paint. `svg_samples_per_cell` defaults to 16, accepts 1..256, and applies in each axis. The exported texture dimensions are `(columns-1)*samples` by `(rows-1)*samples`. Samples lie at texel centers in the physical mesh rectangle; moved knots are resolved by the continuous inverse before sampling. Pattern bounds cover the current canvas viewport in every actual placement, including shared mask sources. They are not a promise for off-canvas reuse or a subsequently enlarged SVG viewport.

Each artifact and publication receipt includes `mesh_textures` with paint ID, dimensions, PNG SHA256 and a per-channel premultiplied interior reconstruction error bound. The bound uses color-derivative limits, `1/(1-q)`, the sRGB transfer slope when applicable and RGBA8 rounding. It assumes a convex reconstruction using source texel centers at most one texel away in each axis. It excludes mesh-footprint and geometry edges, consumer color changes and additional consumer rounding. Those conditions are reported alongside the bound. `image-rendering="pixelated"` is a consumer hint; a renderer may choose different reconstruction.

Snapshots retain editable meshes. SVG carries an explicit editability/sampling loss; its embedded texture cannot recover knots, and the current bounded SVG importer rejects these pattern/image paints. Increase sampling within the declared resource limits for tighter delivery bounds, or deliver PNG/TIFF for the engine's exact raster appearance. No unreported substitution with a flat color occurs.

## Limits and evidence

- 2..8 rows and columns; exactly `rows*columns` knots, at most 64.
- Rectangle size 0.001..32768; origin and far corner within ±32768.
- At most 1,024 inspection samples; ordinary document paint/storage/work limits also apply.
- At most 65,536 texels per mesh and 131,072 aggregate SVG texels per document or artboard range, checked before producing output. Shared mask references are conservatively counted again.
- SVG pattern coverage coordinates must remain within ±1 billion.

`tests/test_meshes_cli.py` verifies rational four-corner pixels, a separate Hermite/Newton model, shared first derivatives, extreme-color limiting, linear-light RGB and transparent alpha, near-limit inverse/Jacobian behavior, reflection/shear/hierarchy, strokes, masks, actual embedded PNG pixels and reconstruction bounds, create-only publication, artboards/bleed/range limits, locks, atomic rollback and MCP durable history. Independent external decoders and an SVG consumer verify the original example and delivery fixtures; retained receipts remain outside the repository. Run `examples/mesh_workflow.py --output NEW_DIRECTORY` for an editable original graphic, an interior-knot edit and publication receipts.
