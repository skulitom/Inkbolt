# PDF appearance and page delivery

## Reopen a page for editing

Use `pdf.import` to open a page of filled vector artwork and embedded images. This
request opens the first page of a local file in a CLI or MCP workspace.

```json
{"command":"pdf.import","id":"proof","source_path":"artwork.pdf","page_index":0,"color_policy":"encoded_srgb"}
```

The result contains a native `document`, the source file's SHA-256, the page
count, boxes and rotation, and a `mapping` from new item IDs to the PDF
object and decoded byte offset that produced them. Use the document in
`session.create`, recolor a path with the `fill` operation, or edit its cubic
control points. Publish a revised PDF under a new name.

The importer reads classic cross-reference tables and raw or Flate-compressed
page and form streams. Source builds after v0.85.1 also accept ASCII85 around
either representation. They follow the page tree and inherited resources. The
intersection of the crop and media boxes sets the canvas, including fractional
dimensions, page rotation in quarter turns and physical `UserUnit` scaling.
One document unit is one point. Omit `page_index` to open page zero.

The drawing subset includes line and cubic paths, rectangles, compound fills
with either winding rule, graphics-state save and restore, transforms, clipping
paths, and repeated Form XObjects with local resources and bounding boxes.
Transparency groups retain fill and group opacity. DeviceGray and
DeviceRGB use the requested encoded-sRGB interpretation. Painted contours
remain editable. A path may have originated as a rectangle, an expanded stroke
or lettering. Its PDF geometry cannot identify the original editing operation.
The receipt records this loss and the source file remains available.

Source builds also reopen standard RGB blend modes on fills, images and
isolated transparency groups. For example, a path exported with Multiply
can be recolored after import and still multiply against the artwork behind
it. A form with its own transparency group applies the caller's opacity
and blend once to the assembled group. An ordinary form passes them on
to its painted objects. A nonisolated group invoked with a non-normal
blend currently receives a located refusal.
Color burn and color dodge require a PDF 2.0 header or catalog version so
their channel endpoints retain the same meaning after editing.

An Indexed fill with a DeviceGray or DeviceRGB base becomes an editable
solid color. Its palette may contain up to 256 entries in a literal string,
hexadecimal string, or raw or Flate-compressed stream, with optional ASCII85
encoding on either kind of stream. The import receipt
records that the original palette and indices remain in the source file.
Inkbolt uses these palettes when exporting exact RGB fills on blended pages.

MuPDF 1.28.0 and Poppler 26.07.0 each checked 15 overlapping-color pages
before and after a foreground recolor. For all 60 comparisons, every pixel
of the re-export matched a PDF authored directly with the intended colors
and blend. Linux produced the same 30 re-exported files byte for byte as
Windows. In a separate MCP test, a second process retried a Hue recolor
after a disconnect and recovered the edit receipt. The original, edited and
undone revisions each rendered pixel for pixel like the corresponding reference.

Each admitted image XObject becomes a self-contained PNG asset in the document.
Repeated placements share its samples and can be moved independently with the
`transform` edit. Image rows retain their original orientation, including when
the page or placement is rotated. The `image_sources` receipt maps each asset
to its PDF object and optional soft-mask object. The asset records the identity
of the normalized pixels and PNG. The source receipt identifies the original PDF.

Images may use 1-, 2-, 4- or 8-bit DeviceGray or DeviceRGB components, nearest
sampling, and identity or inverted decode ranges per component. Raw and
Flate-compressed samples support packed rows. Flate streams can also use TIFF
horizontal prediction or any of the five PNG row filters. A same-size grayscale
image soft mask supplies straight alpha. Hidden color samples survive zero alpha.
The per-image limit is 4,194,304 pixels. The document asset, snapshot and
decoded-stream limits also apply.

Source builds can also reopen palette images with a DeviceGray or DeviceRGB
base. Packed 1-, 2-, 4- and 8-bit samples select a palette entry. An explicit
`Decode` array remaps the sample values before the importer rounds and clamps
each index. Color-key masks use inclusive ranges on the original decoded
sample codes, before color conversion. If an image also has a soft mask,
the soft mask supplies the alpha. The receipt records the palette size,
active color-key ranges and mask precedence. Moving one copy of an image
preserves its pixels and the placement of every other copy.

Eight independently authored pages exercised both palette bases, packed
rows, predictors and transparency. Poppler rendered all eight sources,
their re-exports and their edited placements exactly like the corresponding
plain RGB controls. MuPDF agreed on seven source pages. On the eighth,
its rendering of an explicit `Decode [0 2]` selected a different palette
entry at 16 pixels. It matched the RGB controls on all opaque re-exports.
On the soft-masked re-exports, six pixels differed by one 8-bit level.

Palette, grayscale and RGB pages saved by Pillow 12.0.0 and 12.3.0 can be
opened directly within the image contracts above. For an
`ASCIIHexDecode` image, the importer accepts the standard `>` end marker
or a stream ending exactly after the last complete sample byte. An odd
final digit needs the marker. The image receipt records which ending it
read. Some writers put generation 65536 on the empty cross-reference
free-list head. Page import reports this in `source.free_head_generation`
when it encounters that entry. Every live object still needs a valid
generation and matching file offset.

Each Pillow version wrote four original pages. The opaque palette pages
re-exported pixel for pixel in MuPDF and Poppler. RGB palette samples also
matched exactly under transparency. The JPEG-encoded alpha and grayscale
pages differed by at most one 8-bit level. On full-color JPEGs the maximum
page difference was two levels in MuPDF and one in Poppler.
Linux reopened the same eight source files and produced the same image
identities and re-exported PDFs byte for byte as Windows. To carry the
editable image and its revisions to another machine, see
[moving artwork with embedded image data](SESSION_BACKUPS.md#moving-artwork-with-embedded-image-data).

Source builds after v0.85.1 also reopen JPEG-compressed image objects
(`DCTDecode`). The importer accepts 8-bit
baseline and progressive Huffman-coded grayscale and RGB frames. The JPEG
dimensions and component count must match the PDF dictionary. A three-component
frame uses YCbCr by default. A PDF `/ColorTransform 0` requests direct RGB.
If the JPEG carries a supported APP14 marker, its transform takes precedence
over either setting. The image receipt reports `app14_color_transform` and
the resulting component interpretation. A grayscale soft mask retains its
own marker in the nested receipt. PDF decode ranges apply to the decoded components.
The page transformation sets the orientation, including for JPEGs that carry
an EXIF orientation. A grayscale JPEG can also supply the soft mask. The
importer checks scans and decoded working storage before invoking the codec.
Marker versions 100 and 101 support codes 0 and 1 with zero required flags.
Embedded profiles and four-component JPEGs remain outside this subset.
[DCT marker format, section 18](https://pdfa.org/norm-refs/5116.DCT_Filter.pdf)

Pillow 12.0 wrote baseline and progressive direct-RGB PDFs. Four more
pages paired direct RGB or YCbCr JPEGs with an opposing PDF dictionary
setting. All six re-exports differed from the corresponding source by at
most two 8-bit channel levels in both MuPDF and Poppler. The four standalone
JPEGs produced the same asset samples as their embedded counterparts.
Windows and Linux produced byte-identical exports on all six pages.

Six synthetic JPEGs covered baseline and progressive grayscale, full-resolution
color and 4:2:0 color. Windows and Linux recovered identical samples. Grayscale
and full-resolution color matched an independent JPEG decoder exactly. For the
two 4:2:0 images, its largest channel difference was 2 on the 8-bit scale.
With and without a soft mask, MuPDF and PDFium each compared 24 original and
edited page deliveries. Every channel was within 2 of the source rendering.

On Windows and Linux, 48 synthetic pages recovered every authored image sample.
Each page placed an image twice. Moving the rotated copy produced 96 original
and edited deliveries for comparison. PDFium matched all 96 independently
authored plain-sample controls at 144 dpi. For 20 comparisons, PDFium rendered
the packed TIFF-predicted source differently from its own plain-sample control.
MuPDF agreed on the predicted and plain sources in every case. Its re-export
comparisons were exact on opaque images and within one 8-bit channel level on
images with alpha.

Painted text, inline images, stencil masks, interpolated
images, preblended soft masks, shadings, CMYK images, remapped color
spaces, graphics-state masks, knockout, annotations and unsupported blend modes return an error.
Content errors identify the selected page and object, with a byte offset for
drawing operators. Import applies the classic container reader's object and
page limits, a 16 MiB source and cumulative decoded-stream budget, and the
selected vector profile's native item and document limits. The same checks
apply when a form is invoked repeatedly. [PDF graphics specification](https://pdfa.org/resource/iso-32000-2/)

### Editing process and spot fills

Source builds after v0.85.1 can reopen a page made of opaque DeviceCMYK and
named spot fills. Each distinct process color becomes a swatch with its four
original components. A spot swatch carries its original PDF plate name in
`pdf_colorant`, its full-strength CMYK alternate and a separate tint on each
paint. When replacing a spot declaration with the `swatch` operation, keep
its `pdf_colorant` to retain the plate name. A swatch edit changes every path
using that ink. A `fill` edit can
change the tint of a single path. To deliver the revised print page, use
`document.export` with `"format":"pdf","pdf_options":{"color":"native_inks"}`.

The import receipt reports `native_cmyk_and_spot_no_display_conversion`.
Display rendering requires an explicit preview or color conversion. The
supported Separation functions run linearly from paper to full ink. Inkbolt
reads type 2 declarations and recognizes type 4 expressions whose four
outputs it can establish symbolically. A page combining RGB imagery with
native fills, painted transparency, overprint, conflicting plate definitions
or a different tint curve receives an error.
[Independent plate checks](DEVELOPMENT_STATUS.md#reopening-print-colors-for-editing)

### Opening writer-generated drawing and image pages

Some PDF writers select a default font and line spacing before drawing
anything. Source builds after v0.85.1 open pages containing that setup
(`BT`, `Tf`, `TL`, `ET`) and an empty page-transition dictionary.
The receipt records the unpainted setup and the default transition.
Showing or clipping glyphs, and nonempty transition dictionaries, still
produce a located error.

Page content, forms, palettes and image planes can use `ASCII85Decode`
alone or before `FlateDecode`. A JPEG image or JPEG soft mask can use it
before `DCTDecode`. Parameters apply to the corresponding stage. Both
the intermediate bytes and the final decoded stream count against the
page budget. The decoder requires the `~>` end marker.
[PDF stream filter specification and errata](https://pdf-issues.pdfa.org/32000-2-2020/clause07.html)

Six ReportLab 4.4.7 pages reopened on Windows and Linux, covering a filled
path and a placed JPEG in three writer configurations. The six original
re-exports and six edits were byte-identical across platforms. The edits
recolored each path or moved each image. Three companion pages containing drawn
text returned an error. At 72 and 144 dpi, Poppler reproduced the paths
exactly and MuPDF differed by at most one 8-bit channel level. On the
JPEG pages Poppler differed by at most three levels and MuPDF by up to 55.
Plain-RGB controls isolated that difference to how the readers decoded the
source's 4:2:0 JPEG. Both readers rendered the exported image within three
levels of samples independently decoded with Pillow, at both placements.

Five original source fixtures cover a rectangle, an equivalent authored path,
a renamed item, a transformed translucent cubic and overlapping shapes. On
Windows and WSL, all five pages reproduced the source pixels at 1× and 2×.
Recoloring a recovered path matched the corresponding edit in the source.
MuPDF and PDFium each rendered all ten reopened and recolored deliveries
pixel-for-pixel identically to their respective controls at 288 dpi. The
synthetic suite also checks nested form resources, clipping, opacity across
overlapping fills, rotated pages, session retry, undo and create-only delivery.

Print-mark ranges and omitted-option defaults are reported in
`capabilities.pdf.mark_limits`. Marked, process and ink-recipe writers share the
same page-coordinate and UserUnit bounds as ordinary PDF delivery.

See the generated [limit reference](LIMITS.md) for centralized resource ceilings.
`capabilities.pdf.maximum_page_coordinate` and `maximum_user_unit` report the
existing page sizing bounds used by the writer. These coordinate and multiplier
limits remain separate from document dimensions and output byte budgets.

Explicit `pdf_options.print` instead produces flattened calibrated CMYK image pages using a supplied output profile, matte and sample density. See [PRINT_CMYK.md](PRINT_CMYK.md). The native path contracts and restrictions below apply when print settings are omitted.

`document.export` accepts `format:"pdf"`. It returns a deterministic PDF 1.7 file (PDF 2.0 for explicit managed colours, a calibrated page profile, color burn or color dodge)
as base64, a `pages` receipt and explicit fidelity losses. Nested knockout
artwork that needs independent shape and paint masks or blends against surrounding artwork also uses PDF 2.0. `document.publish` and
`session.publish` deliver the same bytes to a new `.pdf` file. Existing files are
never replaced. No external application, converter or additional dependency is
needed by the engine.

Omit `pdf_options` to export the canvas as one page. To export artboards as pages:

```json
{
  "format": "pdf",
  "pdf_options": {
    "artboards": { "type": "ids", "ids": ["cover", "detail"] },
    "include_bleed": true
  }
}
```

Use these fields with a document export request, or inside publication `output`.
`all` follows hierarchy order; `range` uses zero-based, end-exclusive indices;
`ids` retains explicit order and rejects missing or duplicate artboards. A selected
artboard defaults to its owned subtree in local coordinates, independent of its
placement on the canvas. A vector artboard with `frame.scope:"scene"` instead
selects the shared artwork through its translated viewport; see
[scene artboards](SCENE_ARTBOARDS.md). Bleed extends that viewport using the saved per-edge
insets. Publication's existing `artboard_id` and `include_bleed` can select a single
page instead; combining `artboard_id` with `pdf_options` is an error.

Physical dimensions derive from `document.resolution_ppi`: one logical unit is
`72 / resolution_ppi` points. PDF export requires `scale:1`. Page receipts expose
logical dimensions, physical points, MediaBox, TrimBox and UserUnit. PDF boxes use
bottom-left coordinates. On an unmarked page, CropBox and BleedBox equal MediaBox.
TrimBox excludes the included bleed. UserUnit is at least one, increasing by whole units to keep
the largest MediaBox coordinate at most 14400; the supported maximum is 75000.
No output density rounding changes the requested physical dimensions.

### Crop and registration marks

Add `"marks": {}` inside `pdf_options` to put crop and registration marks
around each selected vector page or the whole canvas. Use `"marks": {"crop":
true, "registration": false}` for crop marks alone. Both display colour and
`"color": "native_inks"` support marks. Paths and named inks keep their
ordinary delivery semantics. The engine clips the artwork at the BleedBox
and draws marks in the added margin using the PDF `All` separation.
Opaque RGB paints can print on a clear page with marks. For translucent paint,
masks, gradients or blend groups, the exporter checks that opaque artwork
covers the full BleedBox of each selected page. It recognizes a visible raster
document matte, an opaque rectangular fill, a frame background or an opaque
image crop. Ancestor opacity, clips and masks affect this check. Multiple
partial shapes may look opaque together without passing it.

For display delivery on a chosen paper color, set `"pdf_options": {"marks": {},
"matte": [42, 96, 178]}`. The three sRGB bytes set the paper behind the
completed artwork. The color fills transparent areas and preserves how shapes
blend with one another. The same matte is available without marks. Omitting it
retains the document's own paper and allows clear areas in an unmarked export.
When a marked page needs RGB blending, `pages[].opaque_rgb_paper` identifies
the covering item, document matte or export matte. An explicit choice is also
recorded in `pages[].matte`. If coverage cannot be established, preflight
identifies the issue and publication leaves the destination free.
Native CMYK page blending retains its existing vector transparency support.
For a calibrated RGB-only page, the artwork's form carries the profile.
Calibrated native-ink pages require opaque knockout paints for marks. When a
page uses named spots, its `ArtworkBlend` resource retains the declared profile.

MediaBox and CropBox include the margin. The marked page receipt reports
the full sheet in `physical_points`, the artwork including bleed in
`artwork_physical_points`, and the crop segments and registration centres in
`marks`. Gap, stroke width, length and radius use physical points at every
page scale. For flattened native plates, use the existing
[`pdf_options.prepress.marks` setting](VECTOR_PLATES.md).
Rust callers using a full `pdf::Options` struct literal can use `marks: None` and
`matte: None` for the default display output, or `..Default::default()`.

### Selectable labels on marked sheets

Combine `"marks": {}` and `"text": "require_searchable"` inside `pdf_options`
to keep labels selectable at their printed positions. This applies to vector
pages in display color and to supported native-ink text. The margin shifts
the artwork and its word selections by the same physical distance. For a
named-ink label, a single glyph can carry several source letters, as in
the `fi` ligature. Composed clusters painted with a named ink retain the
item-level fallback.

On twelve sheets with asymmetric bleed, MuPDF and PDFium found and copied all
29 tested words at their marked positions. At 288 dpi the artwork inside each
bleed box matched the corresponding unmarked export. A separate plate renderer
matched all 54 process and spot plates inside the bleed. It also found the
registration marks on every plate and the named-ink lettering on its spot plate.

## Searchable text

Set `pdf_options.text` on a vector PDF export, preflight or publication.

| Mode | What the reader receives |
| --- | --- |
| `outlines` (default) | Positioned vector outlines. Existing requests produce the same PDF bytes. |
| `searchable` | Embedded text where supported. Other text items keep their outlines and the receipt counts the reason for each fallback. |
| `require_searchable` | Embedded text for every drawn text item or an error identifying the item and reason before publication. |

Inkbolt uses the pinned font and positions each glyph
from the document layout. A ligature drawn with one glyph can copy as several
source characters, such as `fi`. Installable and editable embedding permissions
are supported. If a static TrueType or CFF font forbids subsetting, Inkbolt
embeds the complete standalone font. Restricted, preview-and-print-only and
bitmap-only permissions fall back to outlines. Supply fonts you have the right
to distribute.

When two Unicode sequences use the same glyph in a CID-keyed CFF face, each
sequence retains its own mapping. The PDF shares one embedded font program
across the required encodings. A letter and its positioned accent have one
selectable character on the page. A drawing made of text glyphs carries the
source sequence around those components. A drawing made of gradient-filled
paths uses the outer character's Unicode mapping.

Left-to-right runs support both ligatures and clusters made of several glyphs.
For example, a base letter and a separately positioned accent copy together as
the original Unicode sequence. On a curved baseline, the letter and accent
can follow different tangents. Inkbolt preserves each glyph's position, scale
and rotation. Source builds support translucent RGB text supplied as byte
channels or a precise `rgba` value. A translucent accent over its base letter
adds a second layer of color where they overlap. The reader still copies
the original letter and accent once.

Windows and Linux produced 32 byte-identical PDF pairs. The fixtures covered
subset and whole-font TrueType and CFF, clear and painted backgrounds, and
four page color settings (untagged, sRGB, linear sRGB and Display P3).
MuPDF and pdftotext recovered each source accent once. At 288 dpi, MuPDF and
pdftoppm matched the outlined reference at all 192 sampled positions per
platform, including the overlap and the area painted by the letter alone.
Repeated letters with the same positioned accent and fill shared a font
resource on each page.

For a variable TrueType or CFF2 font with permission to subset,
Inkbolt embeds a static font at each set of axis settings used on the page.
For example, a regular label and a wide label can share one source font,
keep their different shapes and advances, and both copy as their original
text. The editable document retains the original font and axis settings.
Variable fonts that require whole-font embedding use outlines.

Source builds can also deliver searchable text with axial or radial gradients.
Use pad spread and encoded-sRGB interpolation. Each painted character or
shaping cluster becomes a positioned PDF Type 3 color glyph with its original
Unicode. Its drawing uses the font's contours and the gradient's position in
the artwork. A translucent accent paints over its base letter. Repeated letters
can show different colors along the same gradient. The color glyph references
the embedded source font, subject to the same permissions as solid text.
`pdf.text_delivery.gradient_color_glyphs` counts these painted characters
when present. [Rendering and extraction checks](DEVELOPMENT_STATUS.md#searchable-gradient-text-in-exported-pdfs)

Generated glyphs and text on knockout pages use the fallback. A left-to-right
run containing strong right-to-left source characters also falls back
(`right_to_left_source`). See the right-to-left line contract below.
Flattened print, prepress and ink-recipe exports reject the searchable option.
The PDF carries positioned text. Paragraph structure, accessibility tags and
editable layout remain outside this contract.

Read `pdf.text` for the delivered representation and `pdf.text_delivery` for
the requested mode, embedded glyph and font-program counts, and outlined items
by reason. Counts accumulate across the selected pages. Items on one page
share a font program when they use the same font and axis settings. The snapshot retains the original text,
styles and linked stories.

### Searchable right-to-left labels

Source builds after v0.84.0 can export a Hebrew or Arabic label such as
`אב באב` or `بت تبت` with `pdf_options.text` set to `require_searchable`.
Use `bidi:"unicode"` and `direction:"auto"` on the text frame. Readers can find
a word in the PDF and copy its letters in reading order. A frame can contain
both left-to-right and right-to-left lines. Each line keeps its shaped glyph
positions, fonts and paints. Overlapping translucent letters blend in the same
order as their outlines.

This applies to upright horizontal lines with one advancing glyph per source scalar.
Words can contain strong right-to-left characters (Unicode classes R and AL)
with a single ordinary space between words. Translation and positive
axis-aligned scaling are supported. Mixed directions on one line, combining
marks, multi-character ligatures, bidi controls, neutral punctuation,
repeated or edge spaces, custom tracking, individually shifted baselines,
path text, rotation, reflection and named ink use the outline fallback.
`searchable` preserves the entire item's outlines and reports the reason.
`require_searchable` reports the item before publication. Command-line text
extractors can add directional controls around a correctly ordered line.

Windows and Linux produced byte-identical searchable PDFs for 18 Hebrew and
Arabic labels with solid, axial and radial fills. The fixtures used original
TrueType and CFF geometry fonts and DejaVu Sans 2.37. MuPDF and PDFium found
all 18 labels and copied their words from the intended page regions. Across
36 word selections, the largest difference between MuPDF's horizontal search
bounds and Inkbolt's shaped advances was 0.015 points (rounded up). At 288 dpi
MuPDF's total glyph coverage differed from the outlined controls by at most
0.74%. Over MCP, both platforms preflighted a pinned editable source, published
the predicted PDF hash and preserved the file on a second publication attempt.

### Searchable variable TrueType instances

Each embedded program contains the used glyphs at the requested design
coordinates. Inkbolt takes the outlines and advances from the same pinned
font instance used for layout, rounds contours to integer font units and writes
a static TrueType subset. Readers can display and copy the result without
the original variable font.

The regression fixture sets three weight and width combinations on one page,
reuses one of them, and checks the embedded contours, advances, vertical metrics,
permissions and Unicode mappings. In a separate four-setting comparison,
two PDF readers extracted `AB fi`, including the two characters of the ligature.
At 288 dpi the maximum difference in total glyph coverage between searchable
and outlined output was 0.12% across those four samples.

### Searchable CFF2 text

Both static and variable monochrome CFF2 faces can supply searchable labels.
For example, set `pdf_options.text` to `require_searchable` to keep a print
label selectable at its chosen weight and optical size. The saved document
retains its pinned source font and design axes. On export, each used instance
becomes an embedded static TrueType subset with its shaped advances and
source Unicode.

Inkbolt resolves each glyph's local font dictionary and variation coordinates.
It subdivides cubic segments until a quadratic fits within 0.25 font units
on each axis, then rounds the controls and endpoints to integer font units.
The resulting curves stay within 0.75 font units per axis of the evaluated
outlines. Embedding requires permission to include a subset. In permissive
mode, faces that require their whole program use outlines.

The verification covers a static face, a two-axis fixture with separate local
glyph dictionaries, and a production serif face at four weight and optical-size
settings. Across 16 PDFs with solid or gradient text, MuPDF and PDFium each
found both words and returned the expected text from all 32 selected regions.
An independent font reader compared 40 nonempty glyphs with the source at the
same axes. Their bounds differed by at most 0.5 font units. At 288 dpi the largest
difference in total rendered coverage from an outlined PDF was 0.21%. Individual
edge pixels differ, especially on light strokes.

## Appearance contract

- Paths retain line/cubic controls, transforms, compound winding and geometric
  clips. Frames always clip. Ellipses use the shared four-cubic approximation.
  Strokes become shared evaluated outlines, including their declared curve
  tolerance, dashes, variable widths, arrowheads, brushes and scaling space.
- Text uses the same pinned font instances, feature selection, Unicode shaping,
  bidi resolution, marks and path placement as rendering and outlined SVG.
  The default export draws each glyph as an outline. To let readers search and
  copy the text, request [searchable text](#searchable-text). Keep the snapshot
  and pinned fonts to edit the source.
- Solid RGBA, isolated/pass-through groups and item/fill opacity are supported.
  Axial and radial pad gradients retain encoded-sRGB color and per-stop opacity.
  Shapes with fill and stroke composite before item opacity is applied.
- Verified placed images retain exact cropped RGB8 samples and a gray8 alpha
  soft mask, with interpolation disabled. Inline raster layers also work.
  Nearest sampling is required; other kernels fail explicitly.
- Instances, vector warps, repeats and interpolation materialize from the same
  original evaluators used by the engine. Nonprinting work paths, mask source
  definitions and guides do not print.

The default display mode uses DeviceRGB with encoded working samples. Explicit `pdf_options.color:"native_inks"` retains named inks and overprint under the [native ink contract](INK_DELIVERY.md). Consumer color management,
antialiasing and image reconstruction may differ from engine previews. Exact
consumer pixels and print-profile fidelity are not promised. Effects, filters, dissolve, pixel warps, layer
clipping, adjustment layers, ordered dither and
other paint/sampling semantics return explicit errors. Hidden referenced fonts
and resources are still validated. Unsupported items outside selected owned
subtrees do not enter those exports. A scene view prepares all shared artwork,
including off-view resources and unsupported items.

### Knockout groups

In a source build after v0.84.0, a visible shape with zero item opacity can
cut a hole in earlier siblings in a working-RGB PDF or on a
native CMYK page. Set `content.knockout:true` on the enclosing group. Paint alpha controls how
much of the earlier artwork is removed. Item and fill opacity control how
much of the incoming shape is painted. A half-transparent paint with item
opacity zero therefore removes half of the earlier artwork in its footprint.
The receipt reports the number of delivered groups in `pdf.knockout_groups`.

Each child contributes its completed fill, stroke, clip and opacity mask.
Paths and glyphs stay vector, and a raster child shares its original image
and alpha between the paint and the cutout. Inside a group or frame, each
descendant can have its own item and fill opacity. For example, a blue shape
at 40% item opacity can cut through a red sibling behind the whole subgroup.
A second shape at zero item opacity still contributes its footprint to that
cutout. Group masks and clips apply to both the visible paint and the cutout.

When painted alpha and footprint vary independently, the PDF carries both
fields. `pdf.knockout_field_masks` counts the masks that combine them to
attenuate earlier siblings. These masks use a grayscale PDF 2.0 blend.
In an isolated knockout group, each direct child blends against transparent.
In a pass-through knockout group, each child blends against the artwork
visible at group entry. For example, a Multiply shape above a red sibling
can multiply the blue artwork behind the group. The sibling survives only
outside the incoming shape's footprint. All sixteen standard RGB modes are
supported. Nested groups share their premultiplied color and alpha until
the next paint operation needs the composed artwork. The receipt counts
groups composed against a saved backdrop in
`pdf.knockout_backdrop_groups`. It reports authored blend modes separately.
Reader precision can affect colors, especially Hue and Saturation in older
readers. [Measured reader differences](DEVELOPMENT_STATUS.md#blending-against-the-artwork-behind-a-knockout-group)

For print, set `pdf_options.color` to `native_inks` and leave the document's
RGB output profile unset. Both group modes retain native CMYK and named spot
plates with normal blending. Crop and registration marks can be added on
these pages. A pass-through knockout group can preserve inks that were
already on the page. For example, a magenta overprint inside the group can
leave a spot from an earlier group on its own plate. A zero-opacity child
still cuts earlier siblings according to its intrinsic coverage.

When a fill, stroke or outlined glyph needs the original inks, the exporter
saves the visible artwork and applies the named ink to that copy. The original
path clips the result, and its paint, item and group opacity still apply. An
isolated group starts with a clear backdrop. The
`pdf.external_overprint_paints` receipt counts paints that use the saved
artwork. Process overprint requires explicit CMYK components.
[Ink controls](INK_DELIVERY.md#explicit-pdf-ink-mode) · [Plate measurements](DEVELOPMENT_STATUS.md#native-cmyk-and-spot-knockout)

For the writer that successively attenuates earlier siblings, the limit is
24 attenuations including scene ancestry. Every knockout page has a limit
of 32 nested form and soft-mask references. On a page that saves external
backdrops, the writer additionally counts expanded resource visits,
including repeated references to the same form or graphics state. The
limit is 65,536 per page. Any exceeded limit returns `RESOURCE_LIMIT`
before publication. RGB display delivery uses the default working space or its explicit sRGB
profile. To add marks to a painted knockout group, provide opaque artwork
across the bleed area or choose an export matte.
Keep the snapshot for editable group
controls. [Footprint equations](KNOCKOUT.md#pixel-equations) · [Reader measurements](DEVELOPMENT_STATUS.md#knockout-groups-in-vector-pdf)

### Opacity masks on shapes and groups

Source builds after v0.84.0 can export an item's grayscale `mask` to PDF.
For example, along the middle of a 24 × 12 shape, this mask fades from fully
visible at x = 6 to fully transparent at x = 18.

```json
{"width":2,"height":1,"gray_hex":"ff00","clip":true,"sampling":"bilinear","transform":[12,0,0,12,0,0]}
```

The exporter applies the field once to the completed item, including any
overlapping fill and stroke. A group mask acts on its combined children.
Linked and document-space placement, feather, inversion, density and outside
coverage follow the same rules as preview. Nearest sampling produces a
grayscale image with interpolation disabled. Bilinear sampling uses adjacent
two-dimensional shadings with shared boundary samples. Only the opacity grid is sampled. Paths,
glyph outlines and gradient paints retain their vector form.

Inline and stored grayscale grids share this path. Constant fields fold into
item opacity. The receipt's `pdf.grid_masks` counts active masks drawn on the
selected pages. `pdf.grid_mask_samples` counts padded cells examined, including
cells checked for uniform coverage. Those cells and `pdf.image_pixels` share
the 4,194,304-sample budget across pages. Embedded mask samples round to
16 bits. Fine check patterns and stripes can look softer than the PNG proof. Use an
overprint-capable separation preview to inspect masked inks. On marked RGB pages, masks with partial
coverage can print over document paper or an explicit export matte.
[Mask coordinates and feathering](MASKS.md#numerical-contract) · [Measured reader differences](DEVELOPMENT_STATUS.md#grayscale-masks-in-vector-pdf)

### Masks made from editable artwork

In source builds after v0.84.0, `document.export` and publication preserve
an enabled `artwork_mask` as a PDF vector soft mask. For example, two icons
can reference the same gradient, one using its opacity and one using its
brightness. Each icon gets its own mask placement and region clip in the PDF.
Keep the Inkbolt snapshot to edit their shared source after delivery.

Alpha mode uses the combined source opacity. Luminance mode paints each
source color into an isolated grayscale group using Inkbolt's encoded-sRGB
weights. Both modes preserve source order, opacity, geometric clips and
pinned-font outlines. The resulting mask applies once to the completed owner,
including overlapping fill and stroke or a group's children. A named paint
inside a mask needs a resolvable display color. In native-ink mode the owner's
ink and overprint still reach the page.

`pdf.artwork_masks.alpha` and `pdf.artwork_masks.luminance` count painted
references across the selected pages. Placed mask paths consume the PDF path
and object budgets. They generate no image samples. RGB and native CMYK pages can carry these masks. Marked RGB transparency
requires [opaque paper across the bleed area](#crop-and-registration-marks). Readers can differ in edge sampling and rounding.
[Source and placement rules](ARTWORK_MASKS.md) · [Reader measurements](DEVELOPMENT_STATUS.md#artwork-masks-in-vector-pdf)

### Gradients that fade to transparent

In a source build after v0.84.0, give each gradient stop an RGBA color. For
example, this vector fill fades from opaque blue to transparent blue over
128 document units.

```json
{
  "type": "linear",
  "start": [0, 0],
  "end": [128, 0],
  "stops": [
    {"offset": 0, "color": [30, 100, 220, 255]},
    {"offset": 1, "color": [30, 100, 220, 0]}
  ]
}
```

PDF export writes a color shading and a grayscale opacity shading with the
same transform, stop offsets and padding. Both stay vector-based in fills and
strokes. Equal stop opacities use one constant graphics-state opacity.
`pdf.gradient_opacity_masks` counts the varying-opacity paints on the
selected pages. A repeated offset makes a hard stop. At output pixels that
touch the stop, readers can render visibly different edge colors. The receipt
flags that behavior. A marked RGB page can carry a fading gradient over opaque paper.
[Measured examples](DEVELOPMENT_STATUS.md#gradient-opacity-in-vector-pdf) · [PDF transparency specification](https://pdfa.org/resource/iso-32000-2/)

### RGB blend modes

Source builds after v0.84.0 preserve standard blend modes on display PDFs. For example, a vector shape with `"blend":"multiply"` stays a vector
path and multiplies against the artwork beneath it. Inkbolt applies the blend
once to the composed fill and stroke. An isolated group's blend applies to
its combined children. Children of pass-through groups see the surrounding
artwork.

The supported modes are normal, multiply, screen, darken, lighten, color burn,
color dodge, overlay, hard light, soft light, difference, exclusion, hue,
saturation, color and luminosity. `capabilities.pdf.display_blend_modes` lists
the request values. `pdf.blend_modes` identifies the non-normal PDF operators
actually used. The page can use default DeviceRGB or the exact working sRGB
profile. Other blending profiles and native ink delivery reject non-normal
vector blends. For marks and blends on the same page, follow the [full-bleed paper rules](#crop-and-registration-marks).

On a page with blending, Inkbolt writes solid 8-bit path colors as exact RGB
bytes in indexed PDF color spaces. This keeps adjacent source colors distinct
when a reader would round a decimal paint operand down. The reader still
performs the blend. Near gray, even a one-level difference between channels
can produce a visible hue or saturation shift in some readers. Older readers
can also shift these two modes on saturated colors. Partial opacity can change
rounding. For delivery that requires the preview's exact
pixels, export a PNG proof. [Measured reader results](DEVELOPMENT_STATUS.md#vector-pdf-blend-delivery)

Color burn and color dodge select PDF 2.0 for its corrected channel endpoint
rules. The export receipt flags a visible difference in readers using the older
formulas. Burning white with black can produce black, and dodging black with
white can produce white. The corrected results are white and black respectively.
[PDF Association on the endpoint correction](https://pdfa.org/why-pdf-2-0-is-the-new-pdf-bible/)

## Calibrated page colour

An explicit document `output_profile` embeds its exact RGB ICC bytes as the page and isolated artwork groups' blending space. Gradient opacity masks use DeviceGray so their values remain scalar opacity. The profile must support both conversion directions. Every resource scope maps otherwise untyped RGB paint and images to the fixed builtin sRGB profile through `DefaultRGB`; retained managed paints keep their source profiles and per-paint intent. No source numbers are rewritten. Physical Lab and profiled grayscale/CMYK paints retain their declared interpretation. Untagged CMYK paint and spot alternates fail in this calibrated RGB mode; assign an explicit printing condition or use the native process delivery contract. An explicit CMYK vector canvas also requires its native delivery policy.

Managed paint and calibrated page sources explicitly disable optional black-point compensation through PDF 2.0 `UseBlackPtComp OFF`. The file header and receipt declare version 2.0. Older consumers can ignore this setting, and different lookup interpolation or legacy v2 perceptual black normalization can still change appearance. See the [PDF Association application note](https://pdfa.org/resource/pdf-2-0-application-note-001-black-point-compensation/) for the format control. Native ink delivery without a page profile retains its DeviceCMYK blending contract. Flattened print, native plate and independent ink-recipe paths retain their separate output-profile rules.

## Content compression

Page drawing commands and reusable form streams of at least 128 bytes use
`FlateDecode` when the encoded payload and its filter declaration make the PDF
smaller. This also applies to the drawing commands on print and prepress pages.
Small forms remain inexpensive to emit on pages with thousands of shapes.
PDF readers recover the original drawing commands losslessly. Images, ink
samples, ICC profiles and metadata keep their existing encodings.

The exporter charges the full uncompressed object size against the 32 MiB
budget. The same inputs produce the same bytes within a build. A saved
publication receipt identifies the particular file delivered.

## Metadata, bounds and verification

Public/strip metadata policy runs on each selected export view before outlining.
Public document/item descriptions and optional path-free resource manifests and
sanitized provenance are embedded as JSON in an RDF/XML metadata stream. The
envelope schema is `inkbolt.pdf.metadata.v1`, containing ordered page entries with
their artboard IDs and optional ordinary `inkbolt.metadata.v1` packets. Unselected
item descriptions and private record maps are excluded. Resource manifests retain
the existing all-resources-in-export-view contract, including unused descriptors.
Stripping descriptions does not anonymize visible artwork or erase source files.

Limits are 32 pages, 262144 generated path commands, 32768 PDF objects, 4194304
image pixels and padded opacity-grid samples across all copies/pages, and 32 MiB output. Existing scene,
font, generated-geometry and metadata limits also apply. Export completes in
memory before create-only publication; cancellation is checked before work and
before the publication commit point. There is no partial page batch on failure.

Original fixture tests independently inspect xref offsets, resource references,
page boxes, paths, font-derived geometry, gradients, image samples, metadata,
publication and session history. Additional private verification uses independent
PDF parsing and rendering against original geometry/image oracles. Source
snapshots remain unchanged. The basic page and extended vector typography
criteria cover these declared contracts. Native spot output is covered by
[INK_DELIVERY.md](INK_DELIVERY.md); combined trim/bleed/ink preparation is covered
by [PREPRESS.md](PREPRESS.md). Broader searchable typography, encapsulated page
input and editable reimport beyond the filled-path subset remain open under
the extended page criterion.

Public format reference: [ISO 32000-1 entry](https://committee.iso.org/standard/51502.html)
and [PDF specification archive](https://pdfa.org/resource/pdf-specification-archive/).

Raster background roles deliver the explicit canvas matte beneath retained source artwork within the supported page blending space. Hidden backgrounds suppress the matte. Effects, adjustments and layer clipping still require a different delivery path. [Raster backgrounds](BACKGROUNDS.md)
