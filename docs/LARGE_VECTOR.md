# Large vector documents

Agents can opt into `resource_profile: "large_vector"` on `document.create`, `svg.import` or a vector snapshot. The `resource_profile` edit switches an existing document atomically; a downgrade fails if its contents exceed the standard budgets. Snapshots, semantic diffs and durable history retain this choice. Omitted profiles keep the standard contract and serialization.

| Storage bound | Standard | Large vector |
| --- | ---: | ---: |
| Stored or evaluated items | 256 | 8,192 |
| Aggregate geometry and clip commands | 4,096 | 131,072 |
| Serialized snapshot | 768 KiB | 8 MiB |
| SVG input bytes | 256 KiB | 8 MiB |
| SVG XML nodes | 4,096 | 65,536 |

Both profiles retain a 4,096-command limit on each individual path. Algorithm-specific generated geometry, text, paint, mask, image, nesting, rendering and output budgets remain independent. Increasing storage does not authorize a larger raster workload. Inline pixel storage remains 65,536 pixels, default whole output is at most 1,048,576 pixels (explicit tiled evaluation has its separately bounded subset), and shared render evaluation is limited to 67,108,864 work units. Native layered exchange and retained-object source parsing keep their separate bounds.

The CLI accepts at most 16 MiB per request; the stdio adapter allows an additional 16 KiB of framing. These transport limits apply to the complete request, including multiple documents and operations. A saved session state allows 8 MiB plus 16 KiB for resource roots; the document's own profile and the existing 64 MiB aggregate history ceiling still apply. History never silently evicts old states.

The original workload tests retain 5,000 individually editable colored cells through snapshots, SVG and PDF delivery, compare every PNG pixel to an independently constructed grid, and exercise grouping, undo, retries and revision conflicts through stdio. An independent XML parser and PDF reader check every object's coordinates and colors. A separate 20,000-point-wide canvas keeps its physical SVG/PDF size and exact distant pixel placement. Source SVG files remain byte-identical after import and failed operations.

SVG import, validation, edits, SVG/PDF serialization and PNG/preview drawing check the caller's cancellation token during work. `document.export` and `document.render` accept the shared optional `control` object; timeouts and cancellation propagate through the same local engine. Publication remains create-only and exposes no partial output. Blocking filesystem reads and individual codec calls are not forcefully interrupted.

Retained warp subdivision and dimensional profile preparation now receive the
caller's control explicitly. Recursive component, appearance, repeat,
interpolation and variant validation preserves it instead of creating an
uncontrolled validation context. Ordinary rendering, SVG/PDF delivery, native ink
preparation and explicit expansion pass the same control to the retained vector
evaluators. Dimensional and appearance inspection also observes the stdio
caller's cancellation token. This is cooperative cancellation, not a hard
real-time guarantee for every engine operation.

The dimensional profile planner rejects a workload as soon as exact arithmetic
proves more than 128 nonredundant interior vertices. It still accepts arbitrarily
subdivided straight runs within the independent source/expansion bounds. The
existing final edge limit, curve certificate, topology checks and source retention
are unchanged. `tests/test_vector_preparation_cli.py` checks active marker and
stdio cancellation, deadlines across delivery formats, recursive validation,
unchanged session history, collinear cubic subdivisions and the 128-edge boundary.

The base drawing work is charged once; artwork-mask preparation adds only its own work. This accounting is shared with retained source-tree preparation and leaves the independent ink-rendering calculation intact.

Large-vector scenes consisting of ordinary vector fills/strokes and neutral groups use regional evaluation. Each visible object's conservative transformed control bounds, including its generated stroke, are padded by two evaluation pixels and clipped to the viewport. Only that rectangle is allocated and visited. Paint coordinates stay in the original item space, sibling order is preserved, and hidden subtrees do not draw. Source validation and resource verification still run over the complete document. Scan, paint, composition and control work use the actual rectangles; peak buffers include the output and largest region. Dense overlap can still exceed the unchanged processing limit.

Neutral groups have normal blending, full opacity and no knockout, clips, masks, effects or filters. By default, a scene with other compositing controls, text, images or retained objects uses the existing bounded general renderer. Explicit tiled evaluation adds a conservative spatial index for supported mixed scenes with at least 128 expanded items; it retains composition and clipping semantics, rebuilds for every prepared revision, and keeps the independent work/memory limits. See [render quality](RENDER_QUALITY.md) for its supported subset and bounds. Regional evaluation does not silently remove those semantics. The original sparse workload of 5,000 half-unit squares on a 128 by 96 canvas, and the same scene on a 1,024-square preview, have analytic checks of every output pixel.

All coverage routes now transform controls in binary64 before converting the resulting output-space points to the coverage backend's binary32 representation. This includes vector fills, both stroke scaling policies, image boundaries and geometric masks. Rectangle endpoints are added before conversion; ellipses use the original 32-arc approximation at every quality setting. Stored controls and matrices remain unchanged. Exact-rational tests cover extreme scale/shear, reflection, negative origins and cubic controls; independent area tests use explicit supersampling. Ordinary antialiasing still quantizes coverage and does not promise exact pixel area. See [coordinate fidelity](COORDINATE_PRECISION.md).

Deep near-inverse hierarchies now have bounded composition error and an exact
fallback. A separate original 5,000-object sparse layout exercises that fallback
with analytic pixels. Bounded per-preparation chain reuse and memoized inspection
bounds avoid recalculating the same exact product for every object and ancestor.
The source controls, existing item/work limits and revision boundaries remain
unchanged; see the [hierarchy precision contract](COORDINATE_PRECISION.md).

Curved strokes now refine for their composed placement, anticipating all supported raster scales while retaining saved controls. Rendering, expansion, outlined SVG/PDF delivery, mask sources and native ink planes share the refined outline. Generated geometry limits include hidden content before regional planning; limit or cancellation failures leave no partial published artifact. Analytic arc-length/area fixtures and extreme-scale delivery tests cover this bounded fix. See [stroke precision](STROKES.md#evaluation-precision-and-limits).

Affine determinant validation and inverse calculation now certify their ordinary
arithmetic or use exact rational fallback. Cancellation no longer crosses the
existing determinant cutoff. Exact-boundary, inverse-coefficient and saved-history
fixtures cover this additional numerical boundary; the [precision
contract](COORDINATE_PRECISION.md) distinguishes these guarantees from subsequent
inverse composition, point arithmetic and raster sampling.

Item transforms, reparenting and scalar/artwork mask placement now evaluate their
complete inverse-parent expressions with bounded ordinary arithmetic or exact
rational fallback. This preserves valid cancelling edits without changing source
geometry or raising resource limits. Transfers, clips, masks, path points, layout
moves, dimensions, artboard export, preview mappings and SVG coordinate conversions
also use complete ordered expressions with interior inverses. Independent rational
and visible export fixtures cover these consumers. Input normalization, world
recomposition, final point arithmetic and sampling still require the complete
precision audit.

This remains partial implementation of `vector.resources.extended`. Complete independent resource and extreme-scale acceptance review is still required before the checkpoint earns credit. The total remains **161/167 (96.41%)**.
