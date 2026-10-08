# Editable color controls

Color adjustments run inside the existing raster adjustment-layer pipeline:

```json
{"type":"color","adjustment":{"type":"hue_saturation","hue":120,"saturation":0.1,"lightness":0}}
```

Put these operators in `content.adjustment.operators` alongside tone operators. The stack remains ordered, editable and persistent. Masks, clips, stable `clip_to` references, layer opacity/blending, snapshots, undo and resource limits follow [ADJUSTMENTS.md](ADJUSTMENTS.md). Original pixels and imported asset bytes remain unchanged. Operators transform straight encoded sRGB triples in f64 and retain alpha. RGB clamps to `[0,1]` after **each** operator, before the next operator runs. The final renderer performs RGBA8 quantization. There is no silent color-profile conversion, CMYK conversion or high-depth storage implied.

## Hue, saturation, gray and channel mixing

`hue_saturation` accepts `hue` in degrees from -360000 through 360000, `saturation` in `[-1,1]` and `lightness` in `[-1,1]`, all defaulting to zero. It converts encoded RGB to HSL, adds hue cyclically, shifts saturation and lightness toward one for positive controls or toward zero for negative controls, then converts back. A shift is `x+(1-x)*a` for positive a and `x*(1+a)` otherwise. Achromatic input has hue zero, so adding saturation to gray starts from red unless hue is also supplied. Black and white retain zero chroma. Conversion uses the public [HSL color definition](https://www.w3.org/TR/css-color-4/#the-hsl-notation); numerically stable light/dark branches avoid division by zero for extremely small nonzero chroma.

`desaturate` accepts optional `amount` in `[0,1]` (default one) and `method`:

- `luma` (default): `gray=0.2126*r+0.7152*g+0.0722*b` using encoded channels.
- `average`: arithmetic RGB mean.
- `lightness`: `(max(RGB)+min(RGB))/2`.

It interpolates each channel toward gray by the supplied amount. This encoded luma is a tone-control definition, not a physical linear-light luminance measurement.

`channel_mixer` takes a row-major `matrix` of three RGB coefficient rows and optional `offset:[r,g,b]` (zero by default). Output row i is the dot product with original RGB plus offset i, followed by clamping. Coefficients and offsets are finite within `[-4,4]`; negative values and sums greater than one are intentional. Equal rows produce monochrome output; permutation matrices exchange channels exactly. All three rows evaluate the same input, so earlier output rows do not feed later rows.

## Color balance and selective correction

`balance` takes optional `shadows`, `midtones` and `highlights` RGB triples in `[-1,1]`, defaulting to zero, and `preserve_luma` (default true). Let Y be the original encoded luma. Tonal weights are `(1-Y)^2`, `2*Y*(1-Y)` and `Y^2`; they sum to one. Each channel shifts toward white or black by its weighted control sum.

When preserving luma, compute the mapped luma M and chroma offsets `d=mapped-M`. Output is `Y+k*d`, where k is the largest value at most one that keeps every channel in `[0,1]`. This restores the original encoded luma and compresses chroma only as required by the gamut boundary. It can reduce saturation near black and white. With preservation disabled, each channel's shift is retained directly. This is an explicit original balance contract.

`selective` accepts 1 through 9 unique `corrections`, each `{band,cmyk:[c,m,y,k]}`, with controls in `[-1,1]`. The optional `mode` is `relative` (default) or `absolute`. These subtractive control names are RGB correction parameters; they do not declare or convert a CMYK image.

Bands are reds, yellows, greens, cyans, blues, magentas, whites, neutrals and blacks. For HSL hue H, lightness L and RGB chroma D=max-min:

- Chromatic bands have centers 0,60,120,180,240,300 degrees. Weight is `D*max(0,1-circular_distance(H,center)/60)`.
- Whites, neutrals and blacks use weights `(1-D)*L^2`, `(1-D)*2*L*(1-L)` and `(1-D)*(1-L)^2`.

All nine weights form a partition of one. Pure neutral pixels have no chromatic membership. Every correction uses the same input weights, and the channel changes add as `delta[i]=-sum(weight*(control[i]+black_control))`. Absolute mode adds delta and clamps. Relative mode first clamps delta to `[-1,1]` and uses the signed shift equation. Missing bands contribute zero. Duplicate bands fail rather than applying an accidental repeated correction.

## Lookup tables

Tables carry original explicit values in snapshots; no table files, SDKs or network sources are read. Both types accept optional `domain:[[minR,minG,minB],[maxR,maxG,maxB]]`, defaulting to zero/one, and `strength` in `[0,1]`, default one. Each finite domain endpoint lies in `[-16,16]` and each maximum strictly exceeds its minimum. Input coordinates normalize independently into the domain and clamp to its edges. There is no extrapolation.

Table values are RGB triples in `[-16,16]`, intentionally allowing out-of-gamut results. Interpolate first, mix that result with original RGB by strength, then clamp to `[0,1]`. Thus partial strength can retain values that would differ if table corners were prematurely clipped. Strength zero is identity.

| Type | Data | Evaluation |
| --- | --- | --- |
| `lut1d` | `values`: 2 through 4096 RGB triples | Each input channel independently indexes the corresponding table channel; linear interpolation between adjacent entries |
| `lut3d` | `size`: 2 through 33; `values`: exactly size cubed RGB triples | Red varies fastest, then green, then blue: index=`(blue*size+green)*size+red`; trilinear interpolation of eight corners |

A document holds at most 65536 lookup entries across all adjustment operators, including hidden ones. The existing 768 KiB snapshot and 1 MiB request limits also apply, so a large table with lengthy decimal values can hit the byte limit first. Smaller tables or concise exact values can fit without changing the contract. External table formats and profile-managed tables are separate interoperability work; malformed dimensions are rejected before evaluation.

## Gradient mapping

`gradient_map` takes 2 through 64 `stops:[{offset,color:[r,g,b]},...]`, optional `space` (`srgb` default, or `linear_rgb`) and optional `strength` (one by default). Offsets and colors lie in `[0,1]`; offsets are nondecreasing. Colors have three components because this operation retains source alpha.

Original encoded luma selects the ramp coordinate. Below/above its endpoint offsets, the endpoint color extends. Equal offsets define a hard transition, with the last stop winning at the boundary. RGB interpolation happens in the requested encoded or linear-light space; linear results encode back before mixing by strength. This changes color while retaining coverage; transparent pixels remain transparent.

## Precision, work and verification

The common f64/half-byte rounding contract in ADJUSTMENTS.md applies. Independent tests use rational swatches, a separate HLS implementation, high-precision sRGB encoding and multiaffine polynomials whose 3D lookup interpolation has a closed-form result. HLS comparison bounds the independent floating calculation to `2e-10` of an output byte before rounding; it does not grant a broad one-byte error tolerance. Luma-preserving balance stays within half an output byte of encoded luma after quantization on the tested charts.

Each color operator contributes 16 evaluation units per output pixel, except 3D lookup uses 32 and selective correction uses `16+4*correction_count`. Layer/document operator counts, table storage, rendering and artboard-range budgets remain enforced. The tests also check masks, transparent pixels, parameter updates, snapshots, MCP session undo and source preservation. Invalid controls or unsupported values fail atomically.
