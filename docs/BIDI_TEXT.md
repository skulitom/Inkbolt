# Mixed-direction paragraphs

Set a text frame to `"bidi":"unicode"` to resolve Unicode 16 bidirectional
paragraphs. Its `direction` selects `ltr`, `rtl` or `auto` (first strong character
outside isolates, with LTR fallback). The default `bidi:"single_run"` retains the
previous explicit LTR/RTL shaping contract; `auto` is invalid in that mode.

```json
{
  "text": "A \u05d0\u05d1 12 B",
  "width": 240,
  "height": 80,
  "bidi": "unicode",
  "direction": "auto",
  "align": "start",
  "style": {"font_id": "body", "size": 20, "fill": [25, 100, 200, 255]}
}
```

LF separates paragraphs. Each paragraph resolves embedding levels once from its
complete logical source. Wrapping measures candidate lines using those levels;
line rules reset trailing whitespace and reorder runs after choosing a break.
Shaping orders and positions the glyphs within each directional/script/style run,
including Arabic joining, mark attachment, numeric sequences and mirrored punctuation.
Glyphs are not reversed a second time. Line-local pre/post context still crosses
style and font boundaries, following the supplied characters' joining semantics.

`align:"start"` and `align:"end"` follow the resolved paragraph base direction,
including on wrapped continuation lines. `left`, `center` and `right` retain their
physical meanings. Path text places the same visual sequence along its baseline;
start/end alignment follows the paragraph direction along the authored traversal.

Directional marks, embeddings, overrides and isolates are retained in source and
affect resolution in Unicode mode. Default-ignorable controls produce no glyphs.
Unsupported non-LF control characters and other paragraph/line separators still
fail explicitly in editable frames. The font-free analysis command accepts any
Unicode scalar string, allowing agents to diagnose those separators before editing.

`text.directions` takes `text`, a required `direction`, and optional ordered,
nonoverlapping `lines:[{"start":0,"end":4}]` in logical Unicode scalar indices.
Each range must fit inside one paragraph. Omitted/empty ranges analyze each complete
paragraph; empty input produces one empty line. The report includes Unicode version,
paragraph base directions, line levels, visual run ranges and scalar order. X9-removed
format controls have null levels and are omitted from scalar order. This order is
the UAX #9 result through L2, before shaping's combining-mark and mirroring rules;
it is not a rewritten text string or a glyph-order recipe.

`text.inspect` includes each line's resolved direction and bidi report, plus each
glyph's actual direction and embedding level. Glyph cluster intervals remain logical
scalar ranges (`indices:"unicode_scalars"`, `glyph_clusters:"logical_scalar_intervals"`);
`edit_boundaries:"graphemes"` describes valid text edits. Several glyphs can share
one range, and a range can include suppressed
controls. Styles, replacements and wrapping still require original grapheme boundaries.
Rare directional boundaries inside a grapheme are itemized before shaping; fallback
segments within the resulting run, preserving each scalar instead of dropping a
partially intersected grapheme. Source text is never visually reordered or normalized.

Pinned fonts, fallback, language, variable axes, OpenType features, masks, components,
transforms, source-preserving snapshots and durable history use the existing shared
contracts. No system fonts or network resources are consulted. Limits remain 4096
scalars, 8192 glyphs, 131072 outline commands and 1048576 shaping-work scalars.
Directional inspection accepts at most 4097 ordered line ranges; all source spans
must be disjoint. Explicit zero-length ranges are allowed.

Snapshots retain text, directions and controls; fonts remain external with pinned
identities and licenses. SVG and outline expansion deliver the positioned paths and
lose text editability. PNG/JPEG/TIFF use those same paths. PDF now delivers the
same resolved glyph outlines with independently verified appearance and explicit
font/search/editability boundaries; see [PDF.md](PDF.md). Vertical text, color fonts, language-specific line breaking, hyphenation,
columns and threading retain their separate documented boundaries.

The original geometric fixtures verify Arabic forms, Hebrew/Latin mixtures, digit
order, bracket mirroring, mark anchors, isolates/overrides, base-direction wrapping,
fallback, variable instances, path alignment, logical edits, exact pixels and history.
Private verification additionally runs the complete Unicode 16 BidiTest and
BidiCharacterTest suites through Inkbolt's public library inspection API: 861948
direction cases. These official suites cover through L2; the original glyph/delivery
checks separately cover shaping and outlines.

Public references: [Unicode bidirectional algorithm](https://www.unicode.org/reports/tr9/),
[unicode-bidi 0.3.18 API](https://docs.rs/unicode-bidi/0.3.18/unicode_bidi/struct.BidiInfo.html),
[shaping clusters](https://harfbuzz.github.io/working-with-harfbuzz-clusters.html).
