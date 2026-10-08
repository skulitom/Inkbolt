# Basic vector print preparation

Profile-driven flattened CMYK image pages are available separately through `pdf_options.print`; see [PRINT_CMYK.md](PRINT_CMYK.md). Native ink pages retain the contract below, with extended separation/proofing requirements still open.

Agents can deliver ordered PDF pages that retain declared trim, per-edge bleed,
named spot inks and per-paint overprint. Save the editable snapshot alongside the
page output. Use `pdf_options.color:"native_inks"` and select artboards explicitly:

```json
{
  "format": "pdf",
  "pdf_options": {
    "color": "native_inks",
    "artboards": {"type": "ids", "ids": ["cover", "detail"]},
    "include_bleed": true
  }
}
```

Pass this inside `document.export`, or inside publication `output`. Selection
order determines page order. Each selected artboard delivers its own local
subtree independently of its canvas position, rotation or scale. Artboard width
and height declare trim size. Saved `bleed` insets enlarge the delivered viewport;
the engine exposes existing artwork in that region without extending artwork or
inventing pixels. Guides and unrelated canvas objects do not print.

Page receipts report logical dimensions, physical points, MediaBox, TrimBox and
UserUnit. At resolution `ppi`, each logical unit occupies `72/ppi` points.
MediaBox, CropBox and BleedBox include the requested bleed; TrimBox bounds the
finished page. PDF boxes use bottom-left coordinates, so the lower trim inset is
the source's bottom bleed. With `include_bleed:false`, all four boxes coincide
with trim. Large physical pages use an explicit UserUnit; multiply box coordinates
by that value to obtain points. See [PDF.md](PDF.md) for limits.

Named spot IDs remain distinct even when labels match. Native PDF Separation
resources retain their alternate spaces and exact tints. Process CMYK retains
declared components. Each paint carries its own `knockout`, `preserve` or
`preserve_nonzero` policy. Zero spot tint still addresses that spot channel; mode
1 preserves zero process components. These instructions require an ink-aware
consumer. See [INK_DELIVERY.md](INK_DELIVERY.md) for opacity, group isolation,
alternate color spaces and explicit unsupported combinations.

`swatch.inspect` inventories retained ink dependencies. Export receipts scope ink
diagnostics to selected pages; neither inventory is a measured plate-coverage
report. Unsupported content on a selected page fails before publication, and
existing output files are never replaced. Ordinary unselected artboards do not
participate in a selected page's export preflight. General document validation
still applies to the complete source.

Run `python examples/prepress_workflow.py --output <new-directory>` for original
two-page artwork, an editable snapshot, PDFs with and without bleed and all
receipts. `tests/test_prepress_cli.py` checks combined boxes, physical units,
ordered pages, spot identity, overprint, failed publication and durable history.
Independent verification additionally inspects PDF resources and compares native
process/spot channel samples with rational overlap equations on media and
trim-cropped pages at four resolutions, including UserUnit scaling.

This completes the basic vector preparation contract. Native plate generation,
pre-compositing output-profile conversion, flattened delivery and physical print
marks now have a separate partial implementation described in
[VECTOR_PLATES.md](VECTOR_PLATES.md). Broader native compositing remains required
for the extended checkpoint. No print jobs are sent. Consumer edge smoothing
and color-management differences are outside the declared ink-channel contract.
