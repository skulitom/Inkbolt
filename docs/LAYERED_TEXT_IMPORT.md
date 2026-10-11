# Editable point-text import

`layered.import` can reconstruct an explicit, bounded point-text subset into
editable engine text in either layered container version. This is an implementation
increment; the original extended raster checkpoint and general native saved-file
interoperability remain open.

Set `text_fonts.reconstruction:"engine_layout"` and supply the existing explicit
font bindings and font root. Without this option, text continues to return
structural requirements and optional font-binding diagnostics. CLI, MCP and the
Rust `import_with_text_fonts` function share this behavior. Workspace defaults
can supply the font root. Sources and resource stores are never modified.

```json
{
  "text_fonts": {
    "reconstruction": "engine_layout",
    "font_root": "C:\\Work\\Graphics\\fonts",
    "bindings": [{"face_name": "ChosenFace-Regular", "font": "<font.import result>"}]
  }
}
```

Replace the illustrative `font` placeholder with the complete content-addressed
descriptor returned by `font.import`, including its retained license identity.
There is no installed-font lookup or fallback. The chosen static outline face
must have the exact declared name and all required glyphs and enabled features.
Its identity is the caller's explicit choice, not proof of the source font file.

The admitted subset requires one horizontal, left-aligned line, no wrapping or
hyphenation, explicit character controls, opaque solid RGB fill, uniform explicit
leading and supported point geometry. Size, integral native tracking, horizontal
and vertical scale, baseline shift, and `kern`/`liga`/`dlig` controls become editable
styles. Explicit source language codes map to `en-US`, `en-GB`, `fr` and `tr`,
including per-run language-dependent shaping. Missing language stays unspecified;
other codes fail instead of selecting a default. Delivery retains these exact
tags; regional guesses and aliases are unsupported. UTF-16 run boundaries convert
to engine character indices without splitting
surrogates; normal engine grapheme and range validation still applies. Global
kerning admits font metrics only. Manual and optical modes fail. Other native
features, inherited/default styles, distinct terminal insertion styles, unknown controls, native antialias settings,
warps, paragraph/linked frames and variable fonts
require additional mappings and fail explicitly.

With `color_policy:"convert_srgb"`, the embedded RGB profile converts all authored
fill components to working sRGB before eight-bit rounding. This includes every
style range and uses each nested source's own profile. It does not convert text
through its cached pixels. The existing explicit-profile and untagged-source
policies apply; assumptions never replace a conflicting embedded profile.

Without a global table, complete local authoring and geometry are required.
With a global table, the explicit story index selects source text and styles;
stale local text never overrides them. Every global story and frame must have
exactly one layer reference. Missing, duplicated, shared or unreferenced records
fail. Only explicitly admitted global containers are supported; this does not
accept arbitrary native saved-file tables. Unknown nested layout fields and
nontrivial frame geometry fail even when structural diagnostics can describe them.

The native affine point matrix places a fixed-zero engine baseline. A nominal
1x1 frame with visible overflow stores the point without inventing a width from
cached glyph bounds. Subsequent text and font-size edits retain that baseline.
Linked masks are rebased to preserve their world placement; unlinked masks,
groups, visibility, opacity and supported locks retain their existing contracts.
Embedded editable sources receive the same explicit bindings and reconstruction
option, and their text receipts remain nested with the source receipt.

Receipts report source text identity, local/global selection, chosen font-binding
identity, matrix, cached sample hash and reconstruction differences. Cached layer
and composite pixels are decoded and checked but never become text content.
Engine shaping, metrics and antialiasing can differ from the originating consumer.
RGB components are rounded to eight bits after any profile conversion. Conversion
receipts identify the source profile, relative colorimetric intent, disabled black
point compensation and clipping policy. The profile transform can clip internally;
receipts explicitly report that a total clipping count is unavailable. No native layout or pixel equality is
claimed. Existing file, item, run, pixel and nested-source budgets remain in force.

The fixed-zero point form can be delivered again with explicit native text
delivery options. Other explicit first-baseline controls remain unsupported by
that writer. Session edits, retries, undo and normal image delivery operate on
the retained text and chosen fonts. Original independent byte fixtures and a
geometric test font verify analytic pixels, rotations, stale global/local data,
Unicode ranges, masks, groups, nested sources and durable text edits. They do not
substitute for the original extended interchange acceptance fixture.

Language verification includes an original font with a language-specific glyph
substitution, independent authoring-byte checks and native readback of single and
mixed language runs. The native check establishes language retention only; its
external font was deliberately unavailable and supplies no rendering-equality credit.
