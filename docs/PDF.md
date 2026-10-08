# PDF appearance and page delivery

Explicit `pdf_options.print` instead produces flattened calibrated CMYK image pages using a supplied output profile, matte and sample density. See [PRINT_CMYK.md](PRINT_CMYK.md). The native path contracts and restrictions below apply when print settings are omitted.

`document.export` accepts `format:"pdf"`. It returns a deterministic PDF 1.7 file (PDF 2.0 for explicit managed colours or a calibrated page profile)
as base64, a `pages` receipt and explicit fidelity losses. `document.publish` and
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
artboard exports its owned subtree in local coordinates, independent of its
placement on the canvas. Bleed extends that viewport using the saved per-edge
insets. Publication's existing `artboard_id` and `include_bleed` can select a single
page instead; combining `artboard_id` with `pdf_options` is an error.

Physical dimensions derive from `document.resolution_ppi`: one logical unit is
`72 / resolution_ppi` points. PDF export requires `scale:1`. Page receipts expose
logical dimensions, physical points, MediaBox, TrimBox and UserUnit. PDF boxes use
bottom-left coordinates. CropBox and BleedBox equal MediaBox; TrimBox excludes
the included bleed. UserUnit is at least one, increasing by whole units to keep
the largest MediaBox coordinate at most 14400; the supported maximum is 75000.
No output density rounding changes the requested physical dimensions.

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
- Solid RGBA, normal compositing, isolated/pass-through groups, item/fill opacity,
  axial/radial pad gradients with encoded-sRGB interpolation and constant alpha
  are supported. Gradient duplicate-stop discontinuities retain their two sides.
  Shapes with fill and stroke composite before item opacity is applied.
- Verified placed images retain exact cropped RGB8 samples and a gray8 alpha
  soft mask, with interpolation disabled. Inline raster layers also work.
  Nearest sampling is required; other kernels fail explicitly.
- Instances, vector warps, repeats and interpolation materialize from the same
  original evaluators used by the engine. Nonprinting work paths, mask source
  definitions and guides do not print.

The default display mode uses DeviceRGB with encoded working samples. Explicit `pdf_options.color:"native_inks"` retains named inks and overprint under the [native ink contract](INK_DELIVERY.md). Consumer color management,
antialiasing and image reconstruction may differ from engine previews. Exact
consumer pixels and print-profile fidelity are not promised. Non-normal blending, knockout, effects, filters, dissolve, pixel warps, layer
clipping, active opacity/artwork masks, adjustment layers, ordered dither and
other paint/sampling semantics return explicit errors. Hidden referenced fonts
and resources are still validated. Unsupported items outside selected artboards
do not enter the selected export view.

## Calibrated page colour

An explicit document `output_profile` embeds its exact RGB ICC bytes as the page and isolated-group blending space. The profile must support both conversion directions. Every resource scope maps otherwise untyped RGB paint and images to the fixed builtin sRGB profile through `DefaultRGB`; retained managed paints keep their source profiles and per-paint intent. No source numbers are rewritten. Physical Lab and profiled grayscale/CMYK paints retain their declared interpretation. Untagged CMYK paint and spot alternates fail in this calibrated RGB mode; assign an explicit printing condition or use the native process delivery contract. An explicit CMYK vector canvas also requires its native delivery policy.

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
embedded image pixels across all copies/pages, and 32 MiB output. Existing scene,
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

Raster background roles deliver the explicit canvas matte beneath retained source artwork within this normal-blend subset. Hidden backgrounds suppress the matte. Other restrictions, including masks, effects, adjustments and clipping groups, remain explicit. See [BACKGROUNDS.md](BACKGROUNDS.md).
