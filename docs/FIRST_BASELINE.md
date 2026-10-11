# First-line placement

Ordinary text frames can retain an explicit `first_baseline` setting. It places
the first baseline relative to the frame's local top, independently of the item
transform and clipping rectangle. Omitting it preserves existing ascent-based
placement and snapshot serialization.

```json
{"first_baseline":{"metric":"cap_height","minimum":12}}
```

`metric` is `ascent`, `cap_height`, `x_height`, `leading` or `fixed`. The resulting
offset is the greater of the selected metric and `minimum`; `fixed` uses the
minimum alone. The minimum defaults to zero and must be finite, in 0..=32768
local pixels. Leading uses the frame's explicit leading or its existing natural
first-line spacing.

As with ordinary frame ascent, font metrics include the base style and the font
instances contributing glyphs to the first line. Cap height and x-height use the
maximum scaled positive metric among those instances, including fallback and
variation instances. During layout, missing, zero or negative metrics fail with
`FONT_METRIC_MISSING` and the affected font ID. Choose another metric or a fixed
offset explicitly; no native-consumer fallback or glyph-shape estimate is guessed.
An empty first line uses the base style. Fonts used only on later lines do not
need the selected first-line metric.

All lines receive the same vertical translation from their existing layout.
Character ranges, line breaks, advances and relative line positions are unchanged.
The frame retains its original extent and transform; ordinary overflow checks,
visible overflow and rectangular clipping still apply. A high offset can cause
bottom overflow; cap/x-height or a small fixed offset can put ink above the frame.
No extra space is silently added and no overflow is silently hidden.

Inspection reports actual baseline positions. Pixel rendering, outlines, SVG and
PDF use the shared layout. Snapshot, session, retry and undo/redo operations retain
the control and original font identities. Path text has its own baseline and
rejects this setting. Native layered delivery admits the fixed-zero unwrapped
point form used by [editable point import](LAYERED_TEXT_IMPORT.md). Other explicit
first-baseline controls and linked-story paragraph controls remain unsupported
there and must not be silently dropped. General native text reconstruction remains unfinished;
it adds no credit to the original 167 checkpoints.
