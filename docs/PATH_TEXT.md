# Editable text on a path

Text frames in either document kind can retain an optional `path` baseline. Agents can place curved labels and badge text, edit the original baseline or characters, inspect every glyph, and publish outlines while keeping an editable snapshot.

```json
{
  "text":"ABAB", "width":80, "height":60, "wrap":false,
  "style":{"font_id":"pinned","size":10,"fill":[25,100,200,255]},
  "align":"center", "overflow":"error",
  "path":{
    "geometry":{"shape":"path","commands":[
      {"verb":"move","to":[5,35]},
      {"verb":"cubic","control1":[12,0],"control2":[54,0],"to":[65,30]}
    ]},
    "start_offset":0, "normal_offset":0, "flip":false,
    "tolerance":0.001
  }
}
```

Use this frame in ordinary `text` content with an explicitly installed font descriptor. `text` replaces the frame, including baseline controls; `text_range` edits characters or styles while retaining the path. Setting `path:null` restores rectangular layout. Snapshots and durable history retain the original geometry, font references, offsets, flip, alignment, tracking, colors and overflow settings. Sources are not overwritten by exports or outline conversion.

## Placement

The baseline is one contiguous contour of lines and cubic curves, open or closed. Existing primitive geometry can be expanded into such a contour. Ellipses use the existing four-cubic representation; inspection explicitly reports that conversion. Distance-table error bounds apply to those expanded curves and exclude conversion from an analytic ellipse. Compound contours are rejected.

Path text requires `wrap:false`, no line breaks and no paragraph leading. Existing single-direction shaping, font kerning, grapheme-aligned style ranges and tracking apply before placement. Unicode script itemization, explicit pinned-font fallback and language systems apply to path labels too; see [UNICODE_TEXT.md](UNICODE_TEXT.md). Explicit variable-font and OpenType controls also apply before path placement; see [FONT_CONTROLS.md](FONT_CONTROLS.md). Mixed bidi paragraphs and vertical writing remain separate capabilities. Missing glyphs/fonts fail explicitly.

`start_offset` shifts the entire layout by a signed distance along the baseline. Alignment first places the shaped advance at the left, center or right of the measured path length. Each glyph is placed rigidly around its shaped x-origin plus half its shaped advance. Its local x axis follows the tangent there. Font positioning offsets are retained. `normal_offset` moves it along the tangent's right-hand normal in the document's downward-y coordinate system. Paint coordinates remain text-item-local, so gradient fills continue across the lettering.

`flip:true` reverses traversal and tangent direction. This rotates glyphs to the opposite side of the same baseline without reflecting letter shapes. At a polyline corner the outgoing tangent is used; flipped traversal uses the corresponding incoming tangent. Closed paths have one finite lap; overflow does not silently wrap or repeat text.

Frame `width` and `height` remain nominal bounds for object alignment and ordinary geometry queries. They do not replace the path length or clip path-text glyphs. Use `text.inspect` for actual local/world ink bounds and the per-glyph path placements.

## Overflow and delivery

- `error` rejects layout when the shaped advance interval extends past the baseline.
- `clip` omits glyphs whose midpoints fall outside the finite baseline. A glyph with an on-path midpoint may overhang an endpoint. Inspection retains every shaped glyph and identifies omitted glyphs with `path.drawn:false` and no ink bounds.
- `visible` continues the endpoint tangents beyond the path. Ordinary coordinate/resource limits still apply.

Midpoint culling and endpoint tangent continuation are consistent with the public [text-on-path layout concepts](https://www.w3.org/TR/SVG2/text.html#TextPathElement). Inkbolt defines its own rigid tangent placement; it does not claim byte-for-byte layout equivalence with a browser's native textPath implementation.

PNG/TIFF render the placed outlines; snapshots retain editable text and baseline geometry. `text_outline` converts vector text into an isolated group with individual filled glyph paths and preserves the original item identity, transform, opacity, effects and masks. SVG uses these placed outlines and explicitly reports lost text/baseline editability. Bounded SVG reimport can recover the outlined artwork, not its original characters or baseline relationship. Native SVG textPath import remains unsupported.

SVG artifacts and publication receipts include `text_paths`: source item IDs and their baseline reports. Error bounds are in text-item-local units; a world transform scales them. Retain the source snapshot and pinned font store for editing. Path clipping has already culled off-path glyphs before ink inspection or outline conversion; later geometric clips and visibility are excluded from reported ink bounds.

SVG consumers can encode antialiased edges differently from the PNG renderer. Verification compares glyph control positions and outlines directly, retains measured native edge differences, and independently checks coverage at four-times resolution integrated into common pixel cells. Exact byte equality across independent SVG rasterizers is not promised.

## Numerical contract and limits

Original adaptive de Casteljau subdivision forms a distance table. Each leaf checks its control-polygon/chord length gap and the deviation from a line with uniform parameter spacing. The latter check prevents a collinear but nonuniform cubic from incorrectly placing text by linear parameter alone. Lookup interpolates within a leaf, evaluates its cubic point and normalizes its derivative. The table reports a length interval and a conservative baseline-position error allowance incorporating total gap, same-parameter deviation and f64 accumulation/subdivision rounding. Alignment and flipped traversal are included in that allowance. This is a baseline-point bound, not a bound on every point of a rotated glyph: tangent variation and normal offset also affect distant outline points.

Endpoint samples pin the saved expanded-curve endpoints exactly. A zero endpoint derivative uses its first nonzero limiting control direction; an undefined interior tangent fails with `PATH_TEXT_TANGENT`. Existing font/outline and world-coordinate validation still applies.

Default tolerance is 0.001 local units, with a supported range of 0.000001..0.25. Offset magnitudes are at most 32768. A baseline permits at most 1024 expanded commands and 32768 distance-table leaves, with a depth limit of 24; the document permits at most 65536 leaves. Source commands join ordinary document command limits. Existing 4096-character, 8192-glyph, 131072-outline-command and font budgets remain in force. Failure produces no partial publication.

`tests/test_path_text_cli.py` independently verifies geometric glyphs, font-kerning placement, adaptive Simpson arc integrals, cubic tangents, closed paths, offset/flip/alignment, clipping and extrapolation, subdivision invariance, nonuniform straight cubics, fractional endpoints, ellipse conversion, source persistence, outline/SVG comparisons, resource limits, artboards, create-only publication and durable MCP edits. External image/SVG decoder evidence remains private. `examples/path_text_workflow.py` accepts an explicit local font and license and publishes an original curved label before and after a baseline/side edit.
