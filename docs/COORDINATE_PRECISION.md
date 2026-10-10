# Coordinate fidelity

Negative and fractional positions remain editable throughout snapshots and the
supported SVG exchange. Inspect `capabilities.coordinate_precision` before
choosing a numerical or image comparison.

| Surface | Contract |
| --- | --- |
| Stored geometry and transforms | IEEE 754 binary64 (`f64`); input decimals become representable binary64 values at parsing |
| Snapshot transport | Exact stored finite binary64 values, including the smallest subnormal fractions; zero additional rounding |
| Direct SVG geometry and matrix literals | Decimal text that round-trips to the same stored binary64 value; zero absolute transport error |
| Direct clip and gradient coordinate literals | The same decimal round-trip contract, including transforms and stop offsets |
| SVG units, viewBox, relative/shorthand paths and transform lists | Normalize through binary64 arithmetic; resulting coordinates are then retained exactly |
| Generated geometry | The generating operation's documented tolerance, followed by exact transport of its resulting values |
| Preview/image coverage | Binary64 placement followed by output-space binary32 controls and quantized antialias coverage; neither exact geometric pixel area nor a measure of coordinate transport error |

Rectangles and ellipses retain their explicit coordinates and sizes in SVG. Paths
retain absolute move/line/cubic controls and winding. Nested local matrices remain
separate. There is no rounding to an integer, a fixed decimal count or the preview
pixel grid. Zero's sign is not a geometric distinction; arithmetic normalization
may change it. Finite values below binary64's range can round to zero at input;
values beyond its range are rejected. A decimal spelling longer than binary64
precision cannot be recovered from a snapshot.

Coordinates outside the canvas stay in the editable model and SVG. The viewport
clips their display. Existing limits still apply: geometry control points and
matrix components are bounded by 32768 in absolute value, shape dimensions/radii
have their existing minimums, and singular or renderer-singular matrices fail.
Explicit fractional canvas/unit/color semantics are documented in [VECTOR_CANVAS.md](VECTOR_CANVAS.md).
Complete extreme-scale acceptance remains a separate checkpoint.

Coverage applies the final binary64 matrix before rounding controls for the
backend. This prevents cancellation in a large shear from amplifying a previous
binary32 rounding of the local controls. Rectangle endpoint sums also remain in
binary64 until placement. Fills, generated strokes, image boundaries and geometric
masks share this path. The exact-rational original control corpus bounds final
coordinate error by `1e-5` output pixels; the rectangle endpoint fixture uses
`1e-6`. Pixel tests separately cover scale factors through 32768, negative origins,
reflection, nested placement, cubic controls, clipping and image footprints. These
are explicit fixture bounds; matrix construction, inverse sampling and subsequent
point arithmetic retain their documented floating-point limitations. The backend's
coverage quantization is distinct from these geometric bounds. Use explicit
supersampling when testing geometric area.

Hierarchy composition now tracks rounding residuals and propagates conservative
error bounds through all ancestors. The ordinary result is retained only when its
composition error, applied exactly to any control with coordinates within 32768,
is at most `1e-9` logical units per axis. Otherwise the complete product of the
stored binary64 matrices is computed as exact rational numbers, then each final
coefficient is rounded once to binary64 with a checked nearest-rounding interval.
This prevents successive nearly inverse large transforms from silently losing
their small residuals. It does not change the stored matrices or source controls.
Final point arithmetic and output-space binary32 rounding remain separate stages;
the composition bound alone is not a pixel-area or inverse-sampling certificate.

Validation, regional/tiled preparation and stroke budgets reuse identical
transform chains within a single immutable calculation. The cache holds at most
128 chains, each within the existing 16-ancestor limit. Full inspection and
selection also reuse calculated group bounds. Caches never cross document edits
or requests. Independent rational matrices, final bounds, cubic coverage through
output density 16, a 5,000-object shared hierarchy, cache-capacity overflow and
durable revision/undo/retry behavior are checked in
`tests/test_hierarchy_precision_cli.py`.

Affine determinant validation now uses certified intervals, with exact rational
fallback whenever rounding could cross the existing `1e-8` cutoff. Both the
stored coefficients and cutoff are interpreted as their exact binary64 values.
Finite component limits and the separate renderer-precision nonsingularity check
still apply. This rejects below-cutoff matrices even when rounded product
subtraction appears larger, and accepts supported matrices whose rounded
determinant previously became zero.

Inverse calculation bounds determinant, numerator and division error. The ordinary
inverse is retained only when its coefficient error, applied exactly to any point
within 65536 on each axis, is at most `1e-9` logical units per axis. Otherwise the
complete inverse is calculated rationally and each coefficient is rounded once
to binary64 with a checked nearest-rounding interval. The fallback promises
nearest coefficients, not the fast path's absolute point bound. Final point
arithmetic, inverse composition and sampling remain separate; ill-conditioned
matrices can still magnify their rounding. This does not promise an arbitrary
inverse round trip or exact pixel area. Original Fraction boundary fixtures,
independent inverse bit patterns, interval-corner tests and CLI/MCP atomic history
checks cover this contract in `geometry::affine::tests` and
`tests/test_affine_inverse_cli.py`.

Reparenting, item transforms and scalar/artwork mask linking and transforms now
certify the complete inverse-parent expression. Anchor translations and all
ordered factors participate before the final saved matrix is produced. The fast
coefficient error is bounded by `1e-9` logical units per axis when applied exactly
to points within 65536 on each axis. Otherwise the complete expression is
calculated rationally from its binary64 inputs and only its final coefficients
are rounded to certified nearest binary64 values. At most eight factors are
accepted by this internal evaluator. The fallback's guarantee is nearest
coefficients, not a universal absolute point bound.

Independent Fraction fixtures reproduce previously rejected valid reparenting
and identity edits, translations aligned to ill-conditioned parents, anchored
reflections, scalar/artwork mask linking and visible no-op artwork. Saved CLI/MCP
retries, undo and rejected edits retain their history contracts. See
`tests/test_relative_transforms_cli.py`. This scope does not cover every inverse
consumer: other coordinate conversions, world recomposition, final point
arithmetic and raster sampling retain their separate contracts. No source geometry
or original checkpoint criterion changes.

Import normalizes external SVG syntax. For example, relative controls add to the
current point, smooth controls reflect their predecessor, and quadratics become
cubic controls. Unit conversion and viewBox placement also perform arithmetic.
These operations cannot promise bitwise identity with an uncomputed mathematical
real value. Independent exact-rational fixtures bound normalization error to
`1e-12` logical pixels and composed world bounds to `1e-11` for the documented
moderate-scale tests. Those are fixture bounds, not a universal error bound for
arbitrarily conditioned transforms. [Transform limits](TRANSFORMS.md) and each
geometry operation's error contract remain authoritative.

Snapshots preserve editable primitive parameters, fonts, reusable sources and
other original controls. SVG delivers evaluated outlines for parametric shapes,
text, advanced strokes and other explicitly expanded features. Keep the snapshot
when those controls matter. Import creates new IDs and may introduce groups; source
byte, item, hierarchy and command limits continue to apply on repeated exchange.
Unsupported semantics fail rather than being rounded away.

An independent SVG consumer can use different numeric storage and edge coverage.
The [SVG precision specification](https://www.w3.org/TR/SVG2/types.html)
allows variation in numeric precision, while recommending higher precision for
coordinate transformations. Inkbolt's editable transport contract is stronger
than a promise about a particular consumer's preview pixels. A fractional rectangle
can retain every coordinate exactly while corner antialias samples differ from
exact rectangle/cell intersection area. Compare geometry for precision and use
the declared renderer contract for image comparisons.

`tests/test_coordinate_precision_cli.py` checks raw binary64 encodings, independent
XML parsing, exact-rational normalization and world geometry, clip/gradient
coordinates, repeated exchange, complete round-trip image equality, analytic
interior/exterior coverage, durable edits/undo and unchanged source files.
`python examples/coordinate_workflow.py --output NEW_DIRECTORY` saves a fractional
original, SVG, reimported snapshot and previews without overwriting a destination.
