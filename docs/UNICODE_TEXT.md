# Unicode shaping and explicit font fallback

Both document kinds shape horizontal Unicode text using pinned monochrome local
fonts. The source text stays in logical Unicode order. Scripts, glyph substitutions,
mark placement, kerning and the selected language feed shaping before layout,
transforms, masks or path placement.

An ordinary text style can declare:

```json
{
  "font_id": "primary",
  "fallback_fonts": ["arabic", "indic", "east"],
  "language": "ar",
  "size": 20,
  "fill": [25, 100, 200, 255]
}
```

Import each font and its license using `font.import`, retain its descriptor in
`document.fonts`, and supply the explicit `font_root` when inspecting or delivering
text. Fonts remain external to snapshots. There is no operating-system font search,
download or implicit replacement. An omitted fallback list is empty; an omitted
language uses the shaper's default language. These optional fields are omitted from
old-style snapshots. Language tags have nonempty ASCII alphanumeric subtags separated
by hyphens, at most 64 bytes. They select available font language systems; unavailable
language systems follow OpenType's default selection.

Script runs follow grapheme boundaries. A grapheme's first specific script wins;
neutral graphemes inherit the preceding compatible script, then a following compatible
script, then their script-extension choice, or Common. Inheritance stops at LF
paragraph boundaries. Style boundaries may split a script run, but never a grapheme.
The pinned Unicode/script/shaping library versions are recorded in Cargo.lock.

For each script/style run, Inkbolt tries the primary face and then the ordered fallback
list, choosing the first face that shapes the entire run without an unavailable glyph.
If no face covers the whole run, it chooses the first complete face for each grapheme,
coalesces adjacent choices and reshapes them. Combining sequences are kept together within each directional shaping run. Canonical composition during shaping can satisfy coverage without
individual source-character cmap entries; the source string is not normalized.
Adjacent shaping runs receive line-local pre/post context for joining across style
or font boundaries. Cross-font ligatures are not synthesized.

Font coverage means successful glyph resolution, not a linguistic-quality guarantee
for arbitrary supplied fonts. A missing font or license is an error even when that
fallback is unused or the item is hidden. A list may contain at most seven fallbacks,
and its IDs including the primary must be distinct. All declared fonts participate
in deletion checks, dependent locks, transfer remapping and saved dataset references.

`text.inspect` reports each glyph's actual `font_id`, ISO 15924 `script`,
logical scalar cluster interval, advance, origin and ink bounds. Combining marks and
ligatures can share an interval. Actual selected faces supply metrics and outlines,
including fallback ascent and descent. Glyphs paint as individual ordered paths.

Frame `bidi:"single_run"` (default) retains one explicit `ltr` or `rtl` direction.
Set `bidi:"unicode"` for mixed-direction paragraphs and choose `direction:"auto"`,
`ltr` or `rtl` for paragraph bases. LF remains the supported paragraph separator.
Directional controls and line-local reordering are described in [BIDI_TEXT.md](BIDI_TEXT.md).
Vertical layout and other line separators remain unsupported.

Default-ignorable characters influence shaping and are then removed from glyph output;
for example ZWJ/ZWNJ control joining without requiring visible glyphs. Unsupported
variation-selector sequences follow the font/shaper default glyph. This does not
provide color-font or guaranteed emoji-presentation support.

Wrapping chooses the longest fitting grapheme prefix by measuring shaped candidates,
then prefers a fitting preceding ASCII-space boundary. Contextual substitutions can
make prefix widths nonmonotone, so fitting does not assume that widths increase with
length. Each resulting line is reshaped with its own joining context. A grapheme too
wide for the frame follows the declared overflow policy. Only standalone break spaces
are skipped; source spaces and characters remain in the snapshot. Language-specific
line-breaking, rendered hyphenation, columns, threading and lists remain separate requirements.
Read-only [hyphenation inspection](HYPHENATION.md) supports explicit weighted rules and exceptions; it does not yet alter text-frame wrapping.
Tracking applies between shaped clusters; nonzero tracking disables optional `liga`
substitution by default; an explicit `features.liga` setting overrides that default. Required script shaping remains enabled. Negative per-glyph advances
are explicitly unsupported.

Snapshots and durable sessions preserve source text, style ranges, font preferences
and language. PNG/JPEG/TIFF use the same positioned outlines. Vector SVG and
`text_outline` preserve delivered outline appearance and lose editable text/font
controls; retain the source snapshot and font store. SVG text import retains its
separate bounded single-line/font-binding contract. Variable axes and explicit OpenType feature controls are described in [FONT_CONTROLS.md](FONT_CONTROLS.md). PDF delivers the same positioned outlines with explicit losses of text editing, searching and embedded fonts; see [PDF.md](PDF.md).

The existing limits remain: 4096 source scalars per document, 64 ranges per frame,
eight pinned font descriptors, 8192 resolved glyphs and 131072 outline commands.
Shaping attempts, including failed fallback probes and wrapping candidates, share a
1,048,576 input-scalar work budget per frame. An exhausted budget fails explicitly;
no partial snapshot or publication is produced.

`tests/test_unicode_text_cli.py` uses original geometric OpenType fonts with known
Arabic positional substitutions, Indic pre-base reordering, mark anchors, Latin
ligatures, language-specific substitution and CJK/Hangul mappings. Independent glyph
IDs, scalar clusters, metrics, rectangle bounds and every output pixel are checked,
alongside editable delivery, resources, shared dependencies and durable MCP history.
`examples/unicode_text_workflow.py` accepts explicit local font files and a license,
and publishes six original label cases in both document kinds.

Public specifications: [OpenType GSUB](https://learn.microsoft.com/en-us/typography/opentype/spec/gsub),
[OpenType GPOS](https://learn.microsoft.com/en-us/typography/opentype/spec/gpos),
and [shaping clusters](https://harfbuzz.github.io/working-with-harfbuzz-clusters.html).
