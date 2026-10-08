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
are explicit fixture bounds; arbitrary ill-conditioned hierarchy composition and
inverse sampling retain their documented floating-point limitations. The backend's
coverage quantization is distinct from these geometric bounds. Use explicit
supersampling when testing geometric area.

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
