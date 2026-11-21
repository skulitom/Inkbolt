# PDF appearance and page delivery

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

## Appearance contract

- Paths retain line/cubic controls, transforms, compound winding and geometric
  clips. Frames always clip. Ellipses use the shared four-cubic approximation.
  Strokes become shared evaluated outlines, including their declared curve
  tolerance, dashes, variable widths, arrowheads, brushes and scaling space.
- Text uses the same pinned font instances, feature selection, Unicode shaping,
  bidi resolution, marks and path placement as rendering and outlined SVG.
  Each positioned glyph remains a vector path. No font files, searchable text,
  semantic tags or editable text objects are embedded. Keep the original snapshot
  and licensed resource store to retain source text, font controls and editability.
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
by [PREPRESS.md](PREPRESS.md). Font embedding, encapsulated page input and editable
PDF reimport remain required by the separate extended page criterion.

Public format reference: [ISO 32000-1 entry](https://committee.iso.org/standard/51502.html)
and [PDF specification archive](https://pdfa.org/resource/pdf-specification-archive/).

Raster background roles deliver the explicit canvas matte beneath retained source artwork within the supported page blending space. Hidden backgrounds suppress the matte. Effects, adjustments and layer clipping still require a different delivery path. [Raster backgrounds](BACKGROUNDS.md)
