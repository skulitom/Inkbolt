# Native surface, detail and creative filters

Native print preparation supports all 21 existing filter operators. Surface, four detail operators and nine creative operators extend the seven spatial operators in [NATIVE_FILTERS.md](NATIVE_FILTERS.md). This completes the native filter family implementation; it does not complete the broader print checkpoint. Native pixel warps, retained raw/object sources and adjustments remain required.

## Addressed colour

Native state stores ink contribution C, removed backdrop fraction W and common alpha A. For an alpha-preserving colour operator, each addressed ink has conditional density `D=C/W`. An ink with W=0 is unaddressed and remains unchanged. This differs from deliberately painted zero ink, where W>0 and D=0. Neighbourhood averages use `sum(C)/sum(W)` independently for each ink, falling back to the centre when no neighbour addresses that ink. Rank operations discard neighbours with zero W. Output is `C'=W*clamp(D')`; W, A and independent footprint remain unchanged.

Operator polarity follows complement light `L=1-D`, using direct density equations to retain tiny values without subtracting them from one unnecessarily. These are explicit project device-ink semantics. A native print treatment need not equal filtering a display-RGB preview, and no spectral press simulation is implied.

| Operator | Native density result |
| --- | --- |
| sharpen | `D + amount*(D-R)`, where R is the W-weighted mean at four cardinal neighbours |
| unsharp | Same correction using the declared Gaussian reference, only when `abs(D-R) >= threshold` |
| median | Lower median of addressed neighbour densities, equivalent to upper median of complement light |
| noise | `D - amount*N`; clamp after the declared uniform/Gaussian variate |
| relief | `.5 + strength*(Dplus-Dminus)/2` from opposite bilinear samples |
| high_pass | `.5 + D-R` with the W-weighted Gaussian reference |
| extrema minimum / maximum | Maximum / minimum addressed density, respectively |
| tone_fold | `1-D` when `D < 1-threshold`, otherwise D; equality retains D |
| edge_ink | Each addressed ink independently returns `strength*hypot(Sobel_x,Sobel_y)/4` |
| stroke_rank | Sort addressed sampled densities descending and select `floor(quantile*(count-1))` |

All results clamp to [0,1]. Original neighbourhood sizes, document-axis distances, border handling and export scaling remain defined by [DETAIL_AND_SPATIAL.md](DETAIL_AND_SPATIAL.md) and [CREATIVE_FILTERS.md](CREATIVE_FILTERS.md). Edge ink deliberately isolates edges in each native ink; it does not replace all inks with a display-gray approximation.

`creative.value_field` evaluates the original scalar field in item-local coordinates, interpolates its encoded RGB low/high colours, and converts each interpolated sample through the declared print profile before replacing addressed process densities. It retains named-ink values and addressing: RGB endpoints do not invent named-ink recipes. Conversion uses bounded batches with no byte projection.

Independent native noise uses the original version-one process coordinate hash at channel indices 0..3. Monochrome uses its shared channel-zero value for every addressed ink. With monochrome false, named inks hash ASCII `Inkbolt ink noise v1` plus NUL, seed/x/y as little-endian u32, UTF-8 ink-ID byte length as little-endian u32, then the exact ID bytes. Uniform and Box-Muller extraction share the existing 52-bit half-grid definition. Adding or reordering unrelated named inks cannot change an ink's noise stream.

## Surface and positive creative maps

Surface filtering compares complete native tuples `(C/A,W/A,A)`, with the normalized terms zero when A=0. A neighbour is accepted only when every absolute component difference is at most the declared threshold. The same accepted set equally averages original C, W and A together. This preserves overprint while distinguishing missing ink from painted zero. The centre always belongs to its own neighbourhood, so the divisor cannot vanish.

Independent knockout footprint uses neutral colour and alpha-only threshold gating, then contains actual alpha after replacement. Its selected neighbours can differ from the colour/address gate. Alpha-preserving operators retain footprint; colour changes never manufacture geometric coverage.

Twist and field repair share positive arbitrary-channel transport with display rendering. Twist maps local positions through the original radial angle field and returns unchanged samples outside its radius or at zero angle. Field repair interpolates only retained scanlines; it preserves retained lines and singleton height. Both transport ink, removed fraction, alpha and footprint with identical weights.

The existing native filter stack still controls replacement opacity, per-filter masks and all 26 native blend modes. Non-Normal replacement resolves against original intrinsic content on transparency and closes the replacement inks as documented in NATIVE_FILTERS.md. Filters precede clipping members, layer effects and item controls. Artboard bleed rebases local fields; output scale and supersampling retain the shared coordinate rules.

## Limits and evidence

Channel-aware preflight includes all native fields, range gates, hashing, scalar profile batches and order-statistic scratch storage. Median and rank use bounded selection arrays; Gaussian references retain bounded temporary surfaces. Traversal checks cancellation in rows, neighbourhood rows and colour batches. Native profile/source values and original documents remain editable and unchanged; publication is create-only.

Original tests use direct full-neighbourhood rational/Decimal equations, independent scalar field/hash evaluation and conditional-state references. Coverage includes every operator, borders, singleton and identity cases, all blend modes, varying fill/stroke overprint, faint ink, stable named identities, masks, maximum named inks, independent footprint gates, source profiles, scale, supersampling, selected artboard bleed, exact PDF samples and durable agent edits/undo/retry. The registry remains the authority for the full checkpoint count.
