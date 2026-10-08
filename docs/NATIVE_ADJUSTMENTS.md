# Explicit adjustment layers in native print preparation

Native plane inspection and native PDF delivery accept:

```json
{"adjustment_policy":"profiled_process_preserve_spots"}
```

Set this field in `document.prepress.options` or `pdf_options.prepress` alongside
the explicit CMYK output profile. Visible adjustment layers require this policy;
omission fails with `UNSUPPORTED`. It makes the conversion boundary explicit.

For each affected pixel, the output profile's colourimetric AToB table observes
the current straight process CMYK colour. The observation converts to linear
sRGB, clips to the display range, and encodes sRGB. Existing ordered RGB adjustment
operators and the adjustment's RGB blend mode then apply. The layer's opacity,
geometric clip and scalar/artwork mask interpolate the RGB result. The printing
profile converts that result back into CMYK using the selected colourimetric
intent. All calculations remain binary64 until final plane delivery.

The original operator equations remain those in [ADJUSTMENTS.md](ADJUSTMENTS.md)
and [COLOR_ADJUSTMENTS.md](COLOR_ADJUSTMENTS.md): tone controls, colour controls,
curves, lookups and gradient maps are not reinterpreted as ink-density operators.
All 26 existing RGB adjustment blend modes retain their meaning.

This profile observation and separation need not be an inverse pair. A changed
RGB result can therefore change black generation or other CMYK amounts. When the
complete RGB result is unchanged, the exact original ink amounts are retained.
Zero-opacity, zero-mask and hidden adjustments leave amounts unchanged.

Named spot amounts, identities and their overprint retention remain unchanged.
They do not enter process-RGB observation, and RGB controls do not recolour them.
Change a named ink's declaration or explicit binding separately. Source pixels,
profiles, retained snapshots and document revision are never changed by inspection
or export.

## Backdrop and base-clipped adjustments

A backdrop adjustment changes the actual current container result without adding
alpha or a new knockout footprint. Pass-through groups may modify their inherited
backdrop even when they contain no new painting. Their process-colour change is
retained as a signed contextual contribution and attenuated by the group's controls.
An empty isolated source has no alpha and gains no paint from an adjustment.
The root native page starts as opaque zero-ink paper, so a root backdrop adjustment
can change that paper's process colour.

A stable `clip_to` adjustment chain modifies its base before the base's own
opacity, masks, clipping, effects and blend. It observes process colour conditional
on the base's intrinsic alpha, including process ink retained from the surrounding
backdrop. Modified process channels close at that base alpha; named channels keep
their original amounts and retention. Each base control applies once. Background
matte conversion precedes the base's adjustment chain.

Existing document restrictions still apply: a backdrop adjustment inside a knockout
group needs an explicit footprint and is rejected; a base-clipped adjustment is
supported. Normalized adjustments in a linear HDR document remain invalid until
the caller chooses an appropriate explicit conversion boundary.

Receipts under `coverage_sources.adjustments` disclose the selected policy,
conversion, clipping, spot and alpha rules. Work and temporary colour batches are
charged before rendering; cancellation/deadlines apply throughout. PDF publication,
source replacement, undo/redo and retries share the ordinary agent contract.

`tests/test_native_adjustments_cli.py` checks independent profile/coverage equations,
RGB blending, masks, isolation, pass-through context, stable base chains, no-effect
identity, bounds, source/history preservation and exact PDF planes. Complete
checkpoint status remains in [IMPLEMENTATION.md](IMPLEMENTATION.md).
