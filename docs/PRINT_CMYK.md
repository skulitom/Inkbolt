# Profile-driven CMYK image pages

Agents can deliver a flattened PDF page with four calibrated ink channels while
retaining the editable source. Use `document.export`, `document.publish` or
`session.publish` with `format:"pdf"` and explicit print settings:

```json
{
  "pdf_options": {
    "print": {
      "profile": {"type":"icc", "data":"<base64 output profile>"},
      "matte": [255,255,255],
      "intent": "relative_colorimetric",
      "raster_scale": 1
    }
  }
}
```

The supplied profile defines the printing condition. RGB builtins cannot serve
as CMYK destinations. Accepted profiles are bounded ICC v2/v4 output profiles
with CMYK device channels, XYZ or Lab connection space and both A2B0 and B2A0
tables. CMYK profiles have a separate 4 MiB allowance for four-dimensional tables;
RGB profiles retain their existing 256 KiB limit. The 128-tag, table-overlap and
bounded parser allocation checks apply. Directional table channel counts are
checked before conversion. Floating
PCS override tables are explicitly unsupported. Supplied profile bytes remain
unchanged and are embedded in the PDF image's ICCBased colour space with `N:4`.

For a profile too large for the 1 MiB JSON request limit, use
`{"type":"file","source_path":"<absolute local ICC path>","sha256":"<lowercase SHA-256>"}`
as the print profile. The engine reads a bounded regular file, verifies its exact
bytes against the required hash and embeds that same byte buffer. Missing,
changed or oversized profiles fail before publication. The input file remains
untouched; its local path is not included in PDF metadata or profile receipts.
The transport limit and RGB profile limits are unchanged.

Relative colourimetric intent is the default. Absolute colourimetric intent adds
explicit source/destination media-white scaling. A missing colourimetric B2A1
table falls back to B2A0. No black-point compensation or endpoint substitution is
applied. Perceptual and saturation select B2A0 and B2A2 (with the declared B2A0 fallback), with the ICC v4 reference-medium bridge from ordinary colourimetric RGB. Legacy v2 connections retain direct PCS values and do not guess a black normalization. These two intents use the original continuous tensor evaluator; colourimetric separation preserves the pinned floating-point path. Receipts identify the connection policy. Other consumers can differ for coarse nonlinear tables or legacy v2 perceptual black normalization; exact profile bytes do not imply identical pixels.

Each selected page uses the ordinary renderer, including its supported masks,
effects, adjustments, native sample interpretation and composition. The result
becomes straight display RGB8. The required matte is encoded sRGB; its exact
byte/alpha product is composited before profile conversion, without another byte
rounding step. The colour engine evaluates bounded floating-point lookup tables;
each resulting C, M, Y and K ink fraction is rounded once to a byte. K is an
independent channel. The final image is opaque and has no alpha soft mask.

`raster_scale` is an integer from 1 to 4. Physical page size remains
`logical_size * 72 / document.resolution_ppi` points; the image density is
`document.resolution_ppi * raster_scale`. This separates sample density from
physical layout. To change a raster source's declared physical density, use the
existing `canvas` resolution edit, with ordinary undo/redo. Outer PDF `scale`
remains 1. Optional `print.render_options` supports the usual antialiasing,
averaging, cropped effect padding and explicit HDR view. `crop_to_canvas:false`
is rejected because the selected viewport defines the physical page. Linear HDR
requires a declared view; no implicit tone mapping is introduced.

Existing `pdf_options.artboards` and `include_bleed` select ordered independent
pages with MediaBox, CropBox, BleedBox, TrimBox and UserUnit. Unselected artwork
does not enter a selected page's raster view. Receipts report physical points,
sample dimensions/density, profile identity, render settings and a hash of each
page's exact CMYK samples. Public/strip metadata is selected per page and records
the actual profile and density. Profile content itself is not sanitized.

Print settings cannot be combined with `color:"native_inks"` or a document RGB
output-profile association. Explicitly clear that association first. Named ink
display previews become process CMYK; spot plates are not retained. Unsupported
overprint fails until the caller explicitly bakes a display copy. For retained
spot/overprint instructions use the separate [native ink contract](INK_DELIVERY.md).

Limits remain 32 pages, 1048576 evaluated pixels per render, 4194304 image pixels
across the PDF, 32 MiB output and the ordinary resource/work limits. Cancellation
is checked around bounded page rendering, during colour conversion and before
publication. Rendering is not interrupted halfway through its bounded operation.
Delivery completes before create-only publication; source snapshots, occupied
destinations and session history are preserved. No print jobs are sent.

This is calibrated PDF 1.7 image delivery, without PDF/X certification. A consumer
can reconvert colours for a different output condition. Matching the intended
profile avoids unnecessary CMYK round trips. Flattening loses editable layers,
vector/text structure, native precision and transparency in the PDF; retain the
snapshot and resources. Gamut proofing, plate rasters, duotones and broader
prepress remain separate checkpoints.

`tests/test_print_cmyk_cli.py` uses original analytic XYZ/Lab lookup profiles,
independent colour equations, exact PDF structure, source/history checks and
negative cases. The original example `examples/print_workflow.py` accepts a local
output profile or generates a clearly labelled synthetic demonstration profile.
Independent verification compares actual PDF channels against a separate colour
engine and checks page/profile interpretation with independent PDF tools.

Public format references: [ICC.1:2022](https://www.color.org/specifications/ICC.1-2022-05.pdf)
and the [PDF specification archive](https://pdfa.org/resource/pdf-specification-archive/),
particularly ICCBased colour spaces and matching output-device interpretation.

Independent original XYZ/Lab ICC v2/v4 charts match a separate colour engine
within one byte level across 425984 CMYK channel values. An independent PDF
consumer and separate colour engine agree within one byte level across 491520
display channel values when using that consumer's observed perceptual display
policy. These are measured fixture bounds. Earlier consumer probes with different
colour policies showed larger differences and remain recorded privately; exact
preview parity across PDF consumers is not promised. The requested engine
separation intent is verified directly from actual PDF CMYK bytes.

`document.proof` observes the exact separated image samples and returns calibrated views, process-ink planes and measured colour differences. See [PRINT_PROOF.md](PRINT_PROOF.md) for its colourimetric and interpolation boundaries.
