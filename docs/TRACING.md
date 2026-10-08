# Editable image tracing

`image.trace` converts explicit straight RGBA8 pixels or a verified local image asset into a new vector document. The original implementation traces the exact boundary of classified pixel cells. It keeps every noncollinear grid corner, holes, disconnected regions and semitransparent color regions. Returned paths use ordinary editable line commands and nonzero fills; there is no hidden image inside the vector result.

```json
{
  "command": "image.trace",
  "id": "traced-icon",
  "source": {"type": "pixels", "width": 2, "height": 2,
             "rgba_hex": "1864d2ff00000000000000001864d2ff"},
  "options": {"mode": {"type": "exact"}, "alpha_min": 1,
              "min_region_pixels": 1, "max_hole_pixels": 0}
}
```

For an imported image, use `source: {"type":"asset","asset":<asset.import descriptor>}` and the explicit `asset_root` for stored bytes. The existing asset protocol validates content identity. Embedded descriptors also work. Tracing reads its source, writes no files and returns no partial document on failure. Retain the source asset separately when future retracing is needed. Use ordinary atomic edits, sessions, path tools and create-only publication for the result.

## Classification

`mode` is required. Unknown fields and unsupported modes fail.

| Mode | Fields and behavior |
| --- | --- |
| `exact` | Preserve each visible RGBA8 value as a separate color. |
| `binary` | `channel` is `alpha` or `luma`; `threshold` is 0..255, `invert` defaults false, and `color` is a visible RGBA8 fill. A pixel qualifies at or above the threshold, or strictly below when inverted. |
| `quantized` | `rgb_levels` and `alpha_levels` each require 2..256. Each channel rounds to the nearest equally spaced level, ties upward, then that level rounds to RGBA8, ties upward. |
| `palette` | `colors` contains 1..64 unique RGBA8 colors. The nearest entry minimizes squared distance in `(r*a,g*a,b*a,255*a)` using exact integers; the first entry wins ties. A transparent entry must be `[0,0,0,0]`. |

Binary luma uses **encoded sRGB**, `(2126*r + 7152*g + 722*b)/10000`, compared without intermediate rounding. It is a declared threshold signal, not linear-light luminance. Binary output alpha is the chosen fill's alpha. Exact and quantized modes retain or quantize source alpha; a palette can choose new alpha.

Before classification, fully transparent source pixels are always omitted. `alpha_min` (default 1, range 0..255) omits source pixels below that alpha. This gate applies before inversion, so transparent backgrounds cannot become foreground accidentally. Every zero-alpha result canonicalizes to zero RGBA; its invisible RGB remains available only in the original source.

## Noise, topology and geometry

After classification, `min_region_pixels` (default 1) removes same-color **four-connected** regions smaller than the declared area, leaving transparent cells. Then `max_hole_pixels` (default 0, disabled) fills transparent **eight-connected** regions at or below the declared area, only if they do not meet the canvas edge and every surrounding cell has the same color. Mixed-color surrounds, diagonal openings to the outside and larger holes remain. Hole decisions use one simultaneous pass after removal. Both area controls are bounded by 1,048,576 pixels.

The implementation emits oriented edges wherever a classified color borders another color or the canvas. Fixed right-turn pairing keeps diagonal foreground contacts separate. Clockwise outer contours and counterclockwise holes in downward-positive canvas coordinates give positive signed area for occupied cells. Complement connectivity is eight, including at pinched corners. A contour may revisit a corner at such a contact; it never traverses an edge twice. Only collinear intermediate vertices are removed. Colors and contour starts are sorted deterministically. One compound editable item holds all contours of each color.

The response reports exact integer area, unit-edge perimeter, foreground component/hole counts and command count per color. It verifies the traced signed area against classified pixel counts before returning a document. Its `contour_error_pixels: 0` refers to the **classified unit-cell boundary**, not an unknown smooth curve before image sampling. Smooth curve fitting and photographic reconstruction are not implemented. Original disk fixtures additionally measure the contour against their analytic input, independently of this grid guarantee.

At original integer placement and integer export scales, the vector covers the classified cells exactly. After rotation, fractional placement or noninteger scaling, vector coverage is antialiased; adjacent color items may show consumer-specific seams. The geometry remains exact. Native SVG consumers can round semitransparent straight-RGBA colors differently; the independent example records raw differences and separately verifies opaque black/white compositions within one 8-bit channel level, with exact alpha. Existing path simplification is an explicit subsequent operation with its own tolerance/topology contract; tracing does not silently smooth corners or fill holes.

## Provenance, edits and delivery

The receipt and `document.metadata.properties["inkbolt.trace"]` retain algorithm version, normalized parameters, dimensions, input/output pixel identities, connectivity, corner policy and changed-cell counts. The identity is SHA-256 over the existing `INKRGBA1` header, little-endian dimensions and row-major RGBA8 bytes. It contains no local paths. `comparison` measures maximum and RMS channel error against the source in premultiplied encoded sRGB plus alpha, with normalized channels; thresholding/noise losses are included.

Provenance describes the trace when generated. Subsequent path/paint edits retain that history without pretending the geometry still equals the classified grid. Snapshots preserve editable paths and provenance; public SVG metadata preserves the historical record unless explicitly stripped. SVG uses ordinary paths/fills under the public [nonzero winding specification](https://www.w3.org/TR/SVG2/painting.html#FillRuleProperty). Reimport creates independently editable paths with the existing SVG normalization/loss report. PNG/TIFF are image deliveries, not editable interchange. Source image bytes are never packaged into the vector result.

## Limits and verification

Source dimensions use existing image limits, with at most **1,048,576 pixels** per trace. Result limits are **64 colors**, **262,144 unit boundary edges**, **4,096 total path commands**, and existing document bytes/items/coordinate limits. A large simple region can fit; a noisy image can exceed the output budget. Limits fail explicitly instead of increasing thresholds or dropping detail. Large inputs use immutable assets to stay within the JSON request limit. Cancellation/deadline checks occur during classification, region exploration, boundary construction/walking, comparison and before returning; file reads are bounded but not forcibly interrupted.

`tests/test_tracing_cli.py` checks every binary 3x3 configuration against independent graph connectivity, winding samples, area, perimeter and decoded pixels; seeded color/alpha cases; nested holes and analytic original shapes; threshold/quantization/palette equations and error metrics; noise order and hole boundaries; source and asset hashes; editable changes, atomic failures and locks; snapshots, SVG reimport, scaled PNG, create-only delivery, MCP/session history; and pixel/color/command/edge/cancellation limits. See `examples/trace_workflow.py` for an original color icon, noise cleanup and editable/exported results.
