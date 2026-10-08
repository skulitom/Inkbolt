# Color blending

Both document kinds support 26 deterministic color blend modes. The shared
`blending::mix` function takes two finite straight encoded-sRGB triples in [0,1].
Item, group, adjustment, clipping-member and filter contexts all use it. Alpha
and coverage are handled by each context after color mixing. No profile
conversion, linear-light compositing or external application parity is implied.

## Standard families

`normal`, `multiply`, `screen`, `darken`, `lighten`, `color_burn`, `color_dodge`,
`overlay`, `hard_light`, `soft_light`, `difference`, `exclusion`, `hue`,
`saturation`, `color` and `luminosity` use the public color equations in
[W3C Compositing and Blending Level 1, section 10](https://www.w3.org/TR/compositing-1/#blending).
Implementation and fixtures are original. Soft light uses the piecewise
cubic/square-root definition. Dodge retains zero backdrop at its singular corner;
burn retains unit backdrop at its singular corner.

Hue/saturation/color/luminosity process complete RGB triples. Their luminance
weights are 0.30/0.59/0.11 and saturation is max-minus-min. These are not the
linear-sRGB luminance weights used elsewhere for measurements. Changing
luminance translates the color and contracts toward the neutral axis when
needed to fit the gamut. Gray has zero saturation; tied channel extrema are
well-defined. Mixing never applies a separate hue function to each channel.

## Additional arithmetic families

These explicit Inkbolt equations operate on normalized channel values `b`
(backdrop) and `s` (source). Results clamp to [0,1]. They describe this engine's
contract, including singular endpoints and ties.

| Mode | Color result |
| --- | --- |
| linear_burn | b+s-1 |
| linear_dodge | b+s |
| vivid_light | burn(b,2s) for s<=0.5; dodge(b,2s-1) otherwise |
| linear_light | b+2s-1 |
| pin_light | min(b,2s) for s<=0.5; max(b,2s-1) otherwise |
| hard_mix | 1 when vivid_light>=0.5, otherwise 0 |
| subtract | b-s |
| divide | b/s; zero source gives 1, including 0/0 |
| darker_color | Complete RGB triple with smaller channel sum; backdrop wins ties |
| lighter_color | Complete RGB triple with larger channel sum; backdrop wins ties |

Hard mix's comparison is evaluated as b+s>=1, except (b=0,s=1) gives zero.
For that threshold and the two whole-color comparisons only, values within
`8*f64::EPSILON*max(1,abs(left),abs(right))` are treated as tied. This bounded
band stabilizes discontinuities after premultiplied-alpha round trips. Outside
it, comparisons are strict. Soft-light and other continuous branch boundaries
do not use this band. Endpoint division is explicit and never produces NaN.

## Context and precision

Ordinary items use source-over: divide premultiplied backdrop by its alpha,
mix colors, then combine the source-only, overlap and backdrop-only regions.
Opacity, geometry coverage and masks attenuate source alpha. A transparent
backdrop receives the source's original color regardless of blend mode.
Isolated groups mix their completed child composite with the surrounding
backdrop; pass-through children see the existing surrounding composite.
Pass-through groups themselves still require normal blending.

Clipped members change base color without increasing base alpha. Adjustment
layers interpolate before/after colors while preserving alpha. Filters use
replacement mixing and interpolate alpha; see [FILTERS.md](FILTERS.md).
These contexts deliberately differ from duplicating a filtered or adjusted
source and placing it above the original. All use f64 until the final RGBA8
encoding; fully transparent output has zero RGB. Original source bytes persist.

Independent pixel references allow either adjacent byte only within 1e-8
channel units of a mathematical half-byte rounding boundary. They do not allow
an arbitrary one-byte error. Discontinuous comparisons use the explicit band
above. Geometry coverage remains the backend's quantized 8-bit alpha.

Snapshots and persistent history retain blend settings. The `properties`
operation changes item blending; the `filters` operation changes each filter's
blend. Capabilities and generated CLI/MCP schemas enumerate exactly these modes.
PNG renders them. SVG export continues to reject non-normal blending explicitly.

Content fill, independent layer effects and seeded dissolve coverage are described in [LAYER_EFFECTS.md](LAYER_EFFECTS.md). Dissolve is a coverage control that can accompany every color mode. [Knockout groups](KNOCKOUT.md) now preserve independent footprints through isolated/pass-through nesting and all 26 color families.
