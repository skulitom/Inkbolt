# Scene-linear HDR editing and delivery

Raster documents can explicitly select `color_space:"linear_srgb"`. This changes compositing to linear-light sRGB primaries. Retained sample grids declare `encoding:"linear_srgb"` and `depth:"f32"` for signed finite binary32 radiance, including values above reference white, negative color components and subnormals. Alpha remains straight and finite in 0..1. Omitted grid encoding means normalized encoded sRGB, preserving the original document contract.

Linear sample sources require a linear document. A linear document can also contain ordinary encoded sample grids, byte layers, placed images, procedural fills and text. Encoded image channels decode before interpolation; paint shaders evaluate their existing encoded-color contract and decode each result before coverage and compositing. Gradients retain their authored interpolation contract. Existing geometry coverage, byte masks and paint precision do not become arbitrary-precision planes.

Use `working_space` to change a raster document's compositing space explicitly. It preserves source bytes and checks all item locks. This operation changes how sources combine; it does not reinterpret stored source encoding. Convert linear grids explicitly and clear HDR grades before returning to encoded compositing. Cross-document transfer requires matching working spaces.

## Retain and inspect radiance

`sample.import` accepts `color_policy:"assume_linear_srgb"` for straight-alpha binary32 RGB or grayscale TIFF. This is an explicit interpretation of untagged straight samples. Both byte orders, strips/tiles, separate color planes and supported lossless compression retain the native values. The command never changes its input file. Profiles, associated alpha and multi-image/raw/nested TIFF still fail explicitly; linear PNG import and automatic HDR detection are unsupported.

`sample_replace` retains its exact in-bounds native rectangle contract for signed linear binary32 grids. Source color survives zero alpha in snapshots, editing and history. Rendered transparent composite color is zero; compositing may normalize signed zero. Native source bytes are the authority for exact bit preservation.

`sample.measure` takes a document, optional `points` (at most 256 `[x,y]` canvas pixel positions), and optional asset/font roots. It returns full-precision straight rendered values before output projection, per-channel minima/maxima and counts of negative and above-white color channels. It uses scale one, existing coverage and render limits, and returns no byte preview or tone map. Item inspection separately reports sample encoding and retained byte hashes.

## Reversible exposure and compositing

```json
{"op":"hdr_grade","id":"pixels","grade":{"exposure":1.5,"gain":[1,0.9,1.1]}}
```

An HDR grade multiplies linear RGB by `2^exposure * gain[channel]` and preserves alpha. Exposure is in -32..32 stops; each finite channel gain is in 0..16. The saved item property leaves source pixels untouched. `grade:null` removes it. Grades support drawable items and isolated groups; they apply to the group's completed surface before its own coverage, clipping and opacity. Item/ancestor locks, atomic batches, snapshots, semantic diffs, persistent history and safe retries retain their shared contracts. Pass-through groups and resource containers cannot carry grades. Artwork-mask definitions retain their existing encoded scalar contract and reject HDR grades.

The linear renderer supports normal, multiply, additive (`linear_dodge`), darken, lighten, difference and subtract blending. Color arithmetic is unclipped; normal alpha compositing remains bounded. Subtract retains negative results. Hierarchy, isolated/pass-through groups, ordinary masks, geometric clips, alpha clipping, fill/overall opacity, transforms, pixel deformations, canvas operations and artboards share the existing engine paths. Encoded matte colors decode before opaque-background composition.

Nearest, bilinear, area, bicubic and Lanczos3 reconstruction average associated linear samples. For negative-lobed kernels, alpha projects into 0..1 while preserving reconstructed straight radiance when positive alpha exceeds one; nonpositive alpha produces transparent zero. RGB is not clipped to display white. Supersampling averages associated linear radiance before any view conversion.

Normalized adjustment operators, active filters/decorative effects, knockout and the other blend families currently reject with `UNSUPPORTED_HDR_MODE`. HDR output-profile conversion and native page/vector delivery are also unsupported. These diagnostics prevent existing normalized operators from silently clipping radiance. Disabled effects/filters remain retained. Ordinary encoded documents keep their existing behavior.

## Explicit display conversion

PNG, JPEG, ordinary previews and integer TIFF delivery require an explicit view for a linear document:

```json
{"render_options":{"view":{"tone_map":"reinhard","exposure":-1}}}
```

The view runs after full-precision compositing and supersample averaging. It applies exposure, then maps each linear color component independently:

| Map | Linear result before sRGB encoding |
| --- | --- |
| `clip` | Clamp to 0..1 |
| `reinhard` | For `x=max(0,radiance * 2^exposure)`, use `x/(1+x)` |

Both maps clamp negative display components to zero and then apply the standard piecewise sRGB encoding. Alpha is unaffected until the requested output-depth projection. The component-wise Reinhard map is a global display transform; it is not a local-contrast or hue-preserving operator. The view's exposure bounds are -32..32 stops. Source radiance and revision do not change. Missing views fail with `HDR_VIEW_REQUIRED`; views on encoded documents fail explicitly.

Explicit TIFF `depth:"f32"` without a view publishes signed linear radiance. A view with any supported TIFF depth publishes encoded display samples instead. Gray-alpha delivery still requires exactly equal rendered RGB. Native output reports `color_space:"linear_srgb"`; untagged TIFF reimport requires the explicit linear policy above. Compression is lossless after binary32 projection. Nonfinite intermediate results and values outside finite binary32 delivery fail before publication. Output never overwrites an existing destination.

`sample_convert` accepts optional `encoding` and `view`. Encoded-to-linear conversion decodes RGB and requires binary32 output. Linear-to-encoded conversion requires a view; hidden color converts even when source alpha is zero. For linear gray-alpha output, use `require_neutral` or `linear_luminance`; the latter weights linear RGB directly by 2126/7152/722 over 10000 and retains signed or above-white results. Encoded-luma policy is invalid for linear output. Changing encoding/depth is an explicit source edit with undo history; item grade controls remain separate.

Run `python examples/hdr_workflow.py --output <new-directory>` to retain an original signed radiance chart, apply reversible exposure, inspect numerical values and publish a linear float TIFF with two different display views. All existing document, request, import, render, source-preservation and publication limits continue to apply.
