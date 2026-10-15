# Editable character positioning

`text.frame.positioning` retains absolute and cumulative relative placements in
one editable frame, alongside ordinary font and style ranges. This is the shared
layout for [SVG span ranges and coordinate lists](SVG_IMPORT.md#editable-span-ranges).
The declared span-range contract has full Windows/Linux acceptance; span-specific
compositing remains unsupported.
Omitting the field preserves the existing paragraph layout.

```json
{
  "origin": [10, 20],
  "anchor": "start",
  "positions": [
    {"index": 1, "dx": 3, "dy": 2},
    {"index": 4, "x": 50, "anchor": "middle"}
  ]
}
```

The origin is the first alphabetic baseline position in frame-local coordinates;
it defaults to `[0,0]`. Indices address Unicode scalars, including one index for
each supplementary character. Entries must be unique, increasing and inside the
text. Absolute `x` or `y` starts a new independently shaped and anchored chunk;
the omitted axis continues from the preceding unanchored pen. Absolute entries
must lie on grapheme boundaries. `dx`/`dy` accumulate before their character;
positive y moves down. A relative entry inside a shaped cluster is deferred to
the next cluster, preserving ligatures and combining marks. A trailing deferred
shift contributes to the continuation pen. This changes positioning, not tracking.

Anchors are `start`, `middle` and `end`. The chunk's glyph advance intervals
determine its left and right extents, including negative gaps. The selected edge
or midpoint is aligned to its initial position after the first relative shift.
Each chunk uses the frame's positioning anchor unless its first entry overrides
it. An anchor override requires index zero or an absolute entry. Anchoring does
not move the continuation pen for a following chunk. `text.inspect` reports a
line record per chunk, including its source range and signed final pen advance;
glyph positions and outlines describe the actual geometry.

Positioning requires `wrap:false`, `direction:"ltr"`, `bidi:"single_run"` and
`align:"left"`, with no newline, path, paragraph leading or first-baseline control.
The existing per-range font, fill, size, tracking, scale and baseline shift remain
available. Style baseline shift moves glyphs without moving the continuation pen.
Coordinates, cumulative shifts, advances and glyph cells must stay finite and
within the existing local coordinate ceiling. The character ceiling also bounds
position entries. Ordinary frame overflow policy applies to positioned cells and
ink; clipping remains the original frame rectangle. Capabilities expose these
rules under `text_positioning`.

Range replacement retains an entry at the start on the first replacement
character, discards entries on other removed characters and shifts later indices
by the change in scalar count. Insertion retains an entry at its start on the
first inserted character. Deletion removes the start entry. Style-only edits keep
all entries. A new grapheme boundary conflict fails validation atomically. Full
frame replacement supplies a new positioning object; variant text substitutions
retain indexed entries and must still satisfy validation.

Snapshots, components, session proposals/retries and history preserve these
fields. PNG, SVG outlines, PDF outlines and `text_outline` share positioned
layout. Editable layered delivery refuses positioning until that format has a
verified mapping; it cannot silently discard these controls. Font bytes and
licenses retain the existing explicit resource contract.

`tests/test_text_positioning_cli.py` uses original geometric and shaping fixtures
with independently calculated origins, rectangles and character-index edits.
The [span milestone](DEVELOPMENT_STATUS.md#w3a7-complete-within-the-span-range-contract)
records matching fresh full Windows/Linux acceptance, importer coverage and the
remaining representation boundaries.
