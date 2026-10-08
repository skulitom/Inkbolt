# Native ink layer effects

Native print preparation supports the original shadow, lit-shadow, stroke and
overlay effects described in [LAYER_EFFECTS.md](LAYER_EFFECTS.md). Process and
named inks remain separate through decoration, scalar inspection and flattened
PDF delivery. RGB, gray, Lab and shared paint fields convert through the explicit
output profile before ink composition. A named ink's display preview never
replaces its native components. This extends partial native print preparation;
`vector.prepress.extended` remains in progress at 157/167 verified checkpoints.

Effect fields use the immutable source alpha after the item's clipping stack.
Shared original Gaussian, shifted sampling, disk and contour evaluators retain
the existing transparent viewport boundary, global/local light, effect scale,
paint coordinates and export scale. Shadows are below content; fill attenuates
content; overlays replace its conditional color; content covers the shadows;
strokes follow above it. Masks, geometric clips, item opacity and seeded dissolve
then affect the decorated result before its item blend. Opaque backgrounds
decorate their retained source before the matte and clipped members.

Normal shadow and stroke painting honors the effect paint's colorant addresses.
An overlay instead recolors a conditional silhouette. If current intrinsic alpha
is `a`, original source alpha is `A`, the contour supplies `C(A)`, and effect
strength including paint alpha is `q`, final alpha is `(1-q)*a + q*C(A)`.
Addressed inks interpolate toward `C(A)` times the declared native color.
Unaddressed inks retain their **current conditional fractions**, including any
ambient-ink contribution, as the replacement silhouette changes alpha. If the
current content is empty, those inks preserve the ambient contribution. This
explicit overlay contract differs from ordinary overprint painting, which
preserves unaddressed premultiplied amounts while increasing coverage.

Completed decoration on an isolated group remains isolated from its surrounding
backdrop. For knockout, the same fields decorate the intrinsic footprint with
content fill one, retaining zero-opacity child footprints. Non-monotone contours
can reduce a footprint, so it is enlarged when needed to contain actual alpha.
Clipped members preserve the base footprint; base effects run after that stack.

Ink composition stores each channel's removed backdrop fraction directly.
Subtracting a tiny fraction from one would round it away and corrupt a later
contour that amplifies faint coverage. The representation retains that fraction
through fill, masks, clipping, knockout and overlays, without an intermediate
byte projection. Ordinary binary64 precision and the existing geometry/profile
limits still apply; this is not arbitrary-precision arithmetic.

Enabled effect colors participate in native spot discovery. Disabled effects
retain validation and storage constraints but add no printed spot or evaluation
work. Extra ink surfaces, scalar fields, color batches and both footprint/alpha
passes consume the existing aggregate native budgets before allocation. Field
and color evaluation check cancellation; failed publication creates no output.
Capabilities and plane/PDF `coverage_sources.effects` share the same contract.

Original tests cover direct convolution and disk fields, ordered contours,
lighting, transformed gradient/pattern colors, retained-profile float pixels,
overprint and all blend families, knockout, clipping, dissolve, opaque
backgrounds, artboard bleed, output scale, tiny coverage amplification and
source-preserving history. Native filters, pixel deformation, retained raw/object
sources and adjustments remain required for broader flattening. Existing PDF
reader and color-engine limits in [VECTOR_PLATES.md](VECTOR_PLATES.md) remain in
force; exact ink sample transport is distinct from universal preview agreement.
