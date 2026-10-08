# Creative filters

Original editable graphic treatments use the existing `filters` edit, library,
JSON CLI and MCP stdio. Wrap each operator as
`{"type":"creative","operator":{"type":"edge_ink","strength":1.5}}`.
The shared stack retains source content and supports masks, opacity, blend modes,
enable switches, snapshots and session undo. No textures, trained weights or
external services are required.

All operators evaluate the rendered item or isolated container in encoded sRGB.
Samples are premultiplied f64; colour arithmetic below uses straight values.
Final colour is clamped to [0,1]. Unless specified below, output keeps the centre
alpha and clears invisible colour. Missing or zero-alpha colour neighbours use
the centre colour, avoiding colour from hidden pixels. Shared transparent, clamp,
edge-duplicated reflect and wrap borders apply to the current render viewport.

| Operator | Controls and defined behaviour |
| --- | --- |
| `twist` | Item-local `center`, `radius` in 0.0001..32768 and `angle` in ±360000 degrees. For local offset z and r=length(z)/radius, pull from z rotated by angle×(1−r)² when r<1. Outside the circle and at zero angle, return the original sample. The item world transform maps back to a premultiplied bilinear source sample; alpha moves with colour. |
| `relief` | `angle` in ±360000 degrees, `distance` in 0..32 document units, `strength` in 0..8. Sample straight colours A and B at opposite offsets along the angle; return 0.5+strength×(B−A)/2 per channel. Zero distance/strength and constant fields produce neutral grey. |
| `high_pass` | `sigma` in 0..16 document units. Return 0.5+C−G per channel, where G is the shared premultiplied Gaussian result, unpremultiplied before subtraction. A zero-alpha reference uses C. Zero sigma gives neutral grey. |
| `extrema` | `radius` integer 0..8 document units and `mode` `minimum` or `maximum`. Select the channel-wise extreme over the square neighbourhood with positive alpha. Radius zero is identity. |
| `tone_fold` | `threshold` in [0,1]. Each channel C becomes 1−C only when C>threshold; equality retains C. |
| `edge_ink` | `strength` in 0..8. Use arithmetic-mean encoded RGB as the scalar field, horizontal kernel [−1,0,1] with vertical weights [1,2,1], and its transpose. Return white minus strength×sqrt(gx²+gy²)/4. The kernel spacing is one document unit. This is a graphic edge treatment, not a colourimetric luminance estimate. |
| `stroke_rank` | `radius` integer 0..8 document units, `angle` in ±360000 degrees, `quantile` in [0,1]. Bilinearly sample at integer output-pixel offsets along the direction, from −radius×scale to +radius×scale. Discard zero-alpha samples, sort each straight channel, and select index floor(quantile×(count−1)). Radius zero is identity. |
| `value_field` | Required u32 `seed`, `cell_size` in 1..4096 item-local units, integer `octaves` in 1..4, item-local `origin`, and RGB8 `low`/`high` colours. Replace colour with a smooth original coordinate-addressed field mapped between the two colours. Preserve source alpha; use an opaque fill item for an opaque generated texture. |
| `field_repair` | `keep_parity` 0 or 1 selects retained output-grid scanlines. Reconstruct each other row by averaging the adjacent retained premultiplied RGBA rows. Clamp to the nearest retained row at an edge. A one-row image is unchanged. This operator ignores the shared border option. It operates after export scaling, so parity always refers to output rows. |

`value_field` is fully specified for independent reconstruction. At octave o,
divide item-local (position−origin) by cell_size, multiply by 2^o and take the four
integer lattice corners. Hash `Inkbolt value field v1` followed by a zero byte,
the seed as little-endian u32, signed little-endian i64 x and y, and o as
little-endian u32. Read the first eight digest bytes as a little-endian u64,
discard its bottom 12 bits, then compute (n+0.5)/2^52. Interpolate the four values
with u²(3−2u) on each axis. Average octaves with weights 2^(−o). Hash inputs have
no item IDs or time dependence. Field coordinates follow the item and are
preserved when artboard export rebases its root.

## Representative family coverage

The required scope is a family inventory and representative numerical, edge,
ordering and unsupported-context checks. It is not a claim to reproduce every
individual effect in another application.

| Project-owned family | Representative implementation |
| --- | --- |
| Smoothing and selective focus | Existing Gaussian, box, directional, radial and surface filters with editable masks |
| Distortion | Existing offset and displacement; local radial twist |
| Noise and detail | Existing seeded uniform/Gaussian noise, median, sharpen and unsharp |
| Pixel blocks | Existing premultiplied mosaic |
| Procedural colour and texture | Coordinate-addressed multiscale value field; existing repeating paints |
| Graphic colour | Existing posterize/gradient maps; threshold-controlled tone fold |
| Directional marks | Line quantile treatment; compose with existing tone operators |
| Edge drawing and relief | Edge ink and directional relief |
| Neighbourhood utilities | High pass and minimum/maximum |
| Scanline reconstruction | Explicit retained-field interpolation |

All families share ordered evaluation; reordering operations can change output.
The supplied tests use original charts and independent rational neighbourhoods,
55-digit Gaussian kernels, complex-plane inverse maps and exact rational field
reconstruction. Snapshot and MCP history checks retain settings and source bytes.

## Bounds and unsupported contexts

The shared limit is eight filters per item, 64 per document and 67,108,864
estimated filter work units per render. Radius grows with export scale. Work
estimates include kernel samples, sorting and field hashes, including disabled
filters in admission checks. High pass reuses the existing bounded Gaussian
temporary buffers. No new dependency is introduced.

Pass-through containers, adjustment items and active filters in linear HDR
documents are rejected. Unknown operators, parameters, enum values and colour
spaces are rejected rather than silently mapped. Stored high-depth colour and
specialized raw development retain their separate contracts. These filters do
not perform semantic recognition, lens calibration or motion estimation.

`field_repair` is explicitly viewport/output-grid dependent. Padding, export
scale or antialias supersampling can change its line parity. Other neighbourhood
operators also use the current viewport border, so changing the viewport can
change edge pixels. Local field and twist controls follow item transforms;
relief, edge and rank directions refer to the viewport axes.
