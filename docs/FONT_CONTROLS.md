# Editable font instances and OpenType controls

Text styles in vector and raster documents retain explicit per-font variation
coordinates and OpenType feature values. These controls apply to ordinary labels,
paragraphs and path text before item/parent transforms and compositing.

```json
{
  "font_id": "body",
  "fallback_fonts": ["alternate"],
  "font_variations": {
    "body": {"wght": 650, "wdth": 110},
    "alternate": {"wght": 500}
  },
  "features": {"liga": 1, "kern": 1, "ss01": 0},
  "size": 20,
  "fill": [25, 100, 200, 255]
}
```

Variation-map keys must be IDs in that style's font preference list. A style can
configure at most eight faces with at most 16 axis controls each. Controlled fonts
may have at most 16 axes. Unspecified axes use the font's default values; there is no
implicit optical-size setting. Fonts without explicit controls retain their default
instance. A fallback can have different axes or stay at its default instance.

Axis and feature tags contain exactly four printable ASCII bytes. Coordinates must
be finite and within that font's advertised range. Missing axes, out-of-range values
and unreadable/unsupported variation tables produce explicit errors. Inkbolt never
silently clamps an out-of-range request or ignores an unknown axis. All declared
instances are checked when fonts resolve, including unused fallbacks and hidden text.

`font.inspect` accepts a pinned `font` descriptor, explicit `font_root` and optional
`variations` coordinate map for that one font. It returns axis minimum/default/maximum,
the requested and effective user coordinates, normalized coordinates after font axis
remapping, available feature tags, glyph count and instance ascent/descent/line gap.
This command reads the verified font and license without changing either.

User coordinates remain f64 in editable snapshots. The pinned font backend accepts
f32 user coordinates and uses normalized F2Dot14 coordinates, including supported
font-defined remapping. Inspection makes that effective precision explicit. Font-unit
metrics use the backend's integer rounding/truncation; independent consumers may differ
by one font unit at a fractional metric boundary. Outlines are unhinted. Do not infer
screen-hinting or sub-font-unit metric identity across unrelated font engines.

The selected instance is shared by glyph shaping, advance calculation, paragraph
metrics, outline extraction, bounds, path placement and delivery. Both glyph variation
phantom advances and explicit horizontal metric variations are supported by the pinned
font backend. Font-wide metric variations apply through the font's selected metric
source, such as its declared typographic metrics. Source bytes and descriptors remain
unchanged as controls change.

`features` has at most 64 tag/value pairs. A value of zero disables the feature;
positive values enable it or select a font-defined numbered alternate. Positive
controls must identify a tag available in the selected face's GSUB/GPOS tables or
legacy kerning data. An unavailable positive tag fails with
`FONT_FEATURE_UNAVAILABLE`. Disabling an absent tag is a supported no-op.
Availability is at font level: a feature can leave an unrelated script, language,
glyph sequence or out-of-range alternate selection unchanged according to the font
and shaping rules. Inspection is not a promise that every glyph changes.

Language selection and script itemization use the [Unicode text contract](UNICODE_TEXT.md).
Controls apply to the whole style run; use grapheme-aligned character style ranges
for different settings within a label. Explicit `liga` takes precedence over the
default optional-ligature disabling used with nonzero tracking. Tracking still applies
between shaped clusters, so it does not split an explicitly enabled ligature.

`text.inspect` includes requested variation coordinates and effective feature
overrides for each glyph, alongside the actual selected font/script and logical source
interval. Use `font.inspect` for the effective normalized axis coordinates.
The existing `text` and `text_range` edits change these controls atomically with other
snapshot edits. Empty maps clear explicit controls and are omitted from serialization.
Structural validation checks types, tags, finite coordinates and references; actual
axis ranges and selected-feature availability require font resolution during
inspection, layout, rendering or delivery.

Shared components, masks, transforms, datasets, subtree transfer, snapshots and durable
sessions preserve the styles. Transfer remaps both font references and instance-map
keys. Deletion/lock checks retain every referenced face. Missing or corrupt font/license
bytes remain explicit errors; no system font replacement or network lookup occurs.

PNG/JPEG/TIFF deliver the positioned variable outlines. Vector SVG and `text_outline`
freeze those outlines, preserving appearance while losing text/axis/feature editability.
Keep the original snapshot and pinned font store. The existing bounded SVG text import
does not infer these controls from unsupported source attributes. PDF delivers the
same variable glyph outlines; see [PDF.md](PDF.md) for editing/search/font and color
boundaries. Vertical layout and color fonts remain separate requirements.
Mixed-direction paragraphs are described in [BIDI_TEXT.md](BIDI_TEXT.md).

`tests/test_font_controls_cli.py` independently checks two-axis equations,
positive/negative/intermediate coordinates, axis remapping, glyph/metric variations,
ligature and numeric alternate control, legacy kerning, exact glyph pixels, path
placement, affine transforms, outline/SVG delivery, range edits, fallback instances,
transfer keys, diagnostics, locks and durable MCP history. The original variable
fixture is assembled from public OpenType table specifications with the Python
standard library. It includes no downloaded font or private application material.

Public specifications: [variation overview](https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview),
[axes](https://learn.microsoft.com/en-us/typography/opentype/spec/fvar),
[glyph variations](https://learn.microsoft.com/en-us/typography/opentype/spec/gvar),
[metric variations](https://learn.microsoft.com/en-us/typography/opentype/spec/mvar).
