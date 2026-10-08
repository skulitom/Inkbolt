# Editable opacity masks

Both document kinds accept an optional `mask` on drawable items, isolated or pass-through groups, frames and artboards. This is grayscale coverage, independent of the artwork's RGB values and existing alpha. It can fade an icon, soften a diagram group or reveal part of an image without replacing its pixels. Geometric `clip` and layer-to-layer alpha clipping are separate concepts.

```json
{
  "op": "mask",
  "id": "artwork",
  "mask": {
    "width": 4,
    "height": 1,
    "gray_hex": "004080ff",
    "transform": [20, 0, 0, 40, 0, 0],
    "linked": true,
    "enabled": true,
    "clip": true,
    "invert": false,
    "density": 1,
    "feather": 0,
    "sampling": "bilinear"
  }
}
```

The original row-major grid stores one grayscale8 value per pixel: zero hides and 255 reveals. Dimensions and `gray_hex` are required. An explicit `constant:true` mask has zero width/height and empty `gray_hex`; its entire field uses the outside value and density, without fabricated source pixels. Ordinary masks default to `constant:false` and still require positive dimensions. Other fields default to identity transform, linked/enabled/clip true, inversion false, density 1, feather 0 and nearest sampling. The mask operation replaces the complete mask; inspect its current settings before revising only selected fields. `mask:null` removes it. Disabled masks retain all data and settings. Snapshots, session history, named snapshots and retry receipts preserve the editable record.

## Coordinates and editing

A linked mask's transform maps mask coordinates into item-local coordinates. Item and ancestor transforms then move it with the artwork. An unlinked mask's transform maps directly into document coordinates, so it stays fixed when the artwork or its ancestors move. `mask_link` takes `{id,linked}` and converts the stored matrix to preserve its current document-space position. Merely replacing `linked` inside a new mask record does not perform this conversion.

`mask_transform` takes `{id,matrix,space}`. `replace` (default) writes the declared local/document matrix; `local` right-composes in mask coordinates; `world` left-composes in document coordinates, converting back to item-local coordinates when linked. Artwork geometry remains unchanged. There is no separate anchor field: supply the composed affine matrix. Reflection, rotation, scale, shear and fractional translation are supported within the existing coordinate and invertibility limits. Inspection and diffs expose the derived `mask_world_transform`.

Reparenting and ungrouping preserve child world coordinates. Duplication copies mask settings; an unlinked duplicate initially shares the same document-space position. Active masks prohibit appearance-losing ungrouping. Pass-through group masks weight the difference between the original and child-modified backdrop; see LAYER_CLIPPING.md. Locks on affected objects, ancestors or descendants apply. All mask edits use ordinary atomic batches and session conflict/retry rules.

Standalone artboard export converts every owned unlinked mask from document coordinates into the selected board's local coordinates. Requested bleed shifts those fields and the selected board's own linked mask by left/top bleed. Linked descendant masks follow their artwork. The source snapshot stays unchanged. Ancestor effects outside the selected board remain excluded by the existing artboard contract.

## Numerical contract

The engine interprets the grid as scalar coverage, not color. Original code performs these steps:

1. Divide source values by 255. Inversion replaces values **inside the original grid** with `1-v`.
2. Extend the grid to an infinite constant field: 0 when `clip:true`, 1 when `clip:false`. Inversion does not change this outside value.
3. Apply optional separable triangular feathering in mask-pixel coordinates. Integer radius `r` is 0 through 32; each one-dimensional coefficient is `(r+1-|d|)/(r+1)^2` for `-r <= d <= r`. Radius zero is identity. This is an explicitly defined finite kernel, not a Gaussian blur. Feathering can reveal or hide a strip beyond the original grid.
4. Apply density as `1-density*(1-v)` to the entire field, including the outside. Density zero reveals all artwork; density one uses the full mask.
5. Inverse-map each output pixel center into mask coordinates. Nearest sampling uses the containing cell. Bilinear sampling interpolates the four surrounding pixel-center values, including the constant outside field. Render scale changes the output sample positions; feather radius remains measured in mask pixels.
6. Multiply this scalar with geometric clip coverage, frame coverage and item opacity once, after the complete item or isolated group has rendered. Nested groups each apply their own masks before blending with their surrounding backdrop. Straight RGB stays unchanged by scalar attenuation, except that zero final alpha encodes zero RGB. Existing normal/multiply/screen blending remains in encoded sRGB.

Preparation and compositing use f64. The engine quantizes final output alpha once to RGBA8 with nearest rounding. Independent direct two-dimensional convolution and compositing fixtures allow at most one byte difference where floating-point accumulation order approaches a rounding boundary. Integer grayscale samples without intermediate effects are exact.

The isolated-result and final transparency model is informed by the public [CSS Masking specification](https://www.w3.org/TR/css-masking-1/#the-mask-image-rendering-model) and [Compositing and Blending specification](https://www.w3.org/TR/compositing-1/#generalformula). Inkbolt's mask record, finite feather kernel, outside/invert/density order and coordinate controls are original explicit contracts, not a claim of CSS import compatibility.

## Outputs and limits

PNG and numerical previews use the engine contract above. SVG embeds processed grayscale8 PNG fields in luminance masks, with explicit user-space units, affine placement, sRGB interpretation and nearest/bilinear consumer hints. An opaque constant background within the exported viewport represents the outside field. Prepared fields include a constant border for interpolation. SVG consumers may resample differently and the fields introduce grayscale8 rounding; PNG is authoritative for exact engine samples. Original mask pixels and reversible settings require the editable snapshot, and SVG reports this loss. Disabled masks produce no SVG artwork effect.

Mask pixels share the document's 65,536 inline-pixel budget with raster layers, embedded images and pattern tiles. Ordinary plane dimensions are 1 through 32,768; explicit constant planes have both dimensions zero; total snapshot size remains 768 KiB. Preparation pads each axis by `2*(feather+1)`: each mask allows 262,144 prepared pixels, and all masks together allow 1,048,576. Total preparation work is at most 67,108,864 taps, counted as prepared pixels times `2*(2*r+1)` for positive radius, or one for radius zero. Disabled masks also count toward storage and preparation budgets. Rendering reserves four mask-sampling work units per output pixel per active mask in the existing paint-work budget. Prepared fields use separate bounded f64 storage; convolution temporarily adds one field. Artboard ranges count repeated preparation, sampling and embedded mask pixels in their batch limits.

[Pixel selections](SELECTIONS.md) now provide rectangle/ellipse/polygon geometry, scalar set operations, morphology and selection-to-mask creation. Permanent application supports native pixel layers, placed images and procedural fills, with documented sampling and quantization. Other content requires explicit rasterization first. Reusable vector-mask paths and channel storage now have their own contracts in WORK_PATHS.md and CHANNELS_AND_SELECTIONS.md; layer-alpha clipping is documented in LAYER_CLIPPING.md. Broader selection refinement remains tracked separately.

Shared editable shapes, gradients and text can also serve as opacity masks; see [ARTWORK_MASKS.md](ARTWORK_MASKS.md) for their source references, independent transforms and numerical contract. Grid and artwork masks currently cannot coexist on one owner.
