# Masks made from editable artwork

Agents can reuse shapes, gradients and text as an opacity mask without replacing them with a fixed pixel grid. Both document kinds accept nonprinting `mask_source` containers. Their vector and text children remain ordinary editable items with stable IDs. A reference on a drawable, group, frame or adjustment applies the source as alpha or encoded-sRGB luminance coverage. Existing grayscale masks retain their separate contract in [MASKS.md](MASKS.md).

Create the source before attaching references. A minimal atomic batch is:

```json
[
  {"op":"add","item":{"id":"reveal","content":{"type":"mask_source"}}},
  {"op":"add","item":{"id":"window","parent":"reveal","content":{"type":"vector","geometry":{"shape":"rect","x":0,"y":0,"width":40,"height":30},"fill":[255,255,255,128]}}},
  {"op":"artwork_mask","id":"artwork","mask":{"source":"reveal","region":[0,0,80,60],"mode":"alpha"}}
]
```

The referenced `artwork` must already exist. One source may serve several owners. Editing `window` updates all of them. Copying a masked owner preserves its reference; copying the source subtree creates a separate editable definition which can be assigned explicitly. Remove every reference before removing its source. This includes disabled references. Every operation validates the candidate, so detach operations precede removal in the same atomic batch. Snapshots and durable session history retain sources and references.

## Source and coordinate contract

Sources must be top-level resources containing only vector shapes, text and isolated groups. Child geometric clips, visibility, opacity, normal blending, ordinary paints and nested transforms are supported. Source-root transform, visibility, opacity and geometric clip apply within each instance. Raster content, frames, work paths, filters, pass-through groups, layer clipping and opacity masks inside a source fail explicitly. Source roots and their descendants never paint on the page or appear in visible-only queries. Use `visible_only:false` to discover their editable items. Source roots have no intrinsic bounds; child geometry bounds are in source coordinates, independent of a particular reference.

`artwork_mask` requires a `source` ID and `region:[x,y,width,height]`. Defaults are `mode:"alpha"`, identity `transform` and `region_transform`, and `linked:true, enabled:true, clip_region:true`. The region is a rectangle with nonnegative extents; a zero extent hides the complete owner. `region_transform` maps region coordinates into source content coordinates. The source root transform affects its artwork, independently of this region. Outside the transformed region, coverage is zero. `clip_region:false` retains the rectangle and its transform as editable settings but applies the source without region clipping; a zero stored extent then has no effect.

A linked reference's `transform` maps source content coordinates into owner-local coordinates. The owner's world transform follows it. An unlinked reference maps directly into document coordinates. `artwork_mask_link` with `{id,linked}` converts the matrix to preserve current world placement. Replacing the whole record with a different `linked` value does not perform this conversion. `artwork_mask_transform` accepts `{id,matrix,space}`: `replace` writes the reference matrix, `local` right-composes in mask coordinates, and `world` left-composes in document coordinates. Inspection exposes `artwork_mask_world_transform`.

Use `artwork_mask:null` to detach, or replace the complete record with `enabled:false` to preserve settings without an effect. Grid and artwork opacity masks cannot coexist on one item. Owners in nested groups can each have masks; recursive masks inside sources are unsupported. Group ungrouping rejects active masks which would lose appearance. Reparenting retains ordinary owner world placement. Locks on the source subtree or on any referencing owner, ancestor or affected descendant block source edits, including additions and font replacement. Derived diffs include a source-subtree hash on referencing owners.

## Evaluation and output

Each active reference renders its editable source at the requested output scale onto a transparent floating-point buffer. Ordered source-over composition uses premultiplied encoded-sRGB f64 channels. Alpha mode uses the resulting alpha. Luminance mode uses `0.2125*R + 0.7154*G + 0.0721*B` on those premultiplied channels, equivalent to straight-color luminance multiplied by alpha. The coefficients follow the public [SVG luminance-to-alpha matrix](https://www.w3.org/TR/SVG11/filters.html#feColorMatrixElement). Linear-RGB source compositing is not implemented. Paint interpolation may use its declared interpolation space, as elsewhere in the engine.

The transformed region's antialiased coverage multiplies that scalar. Owner opacity, geometric clip, frame coverage and the mask attenuate the complete owner result once, after its filters. An adjustment uses the mask to weight its correction, retaining alpha. Pass-through groups interpolate between their original and modified backdrop. Layer-clipped content retains the existing base-alpha contract. Sources use the same f32 coverage backend as other artwork, while color, mask scalars and composition remain f64 until final RGBA8 output. No grayscale8 intermediate is introduced.

Standalone artboard export retains referenced source subtrees, rebases owned unlinked references and shifts board-owned linked references into bleed. Source coordinates remain unchanged. The original document is preserved.

SVG export creates vector mask content per enabled reference, with unique IDs, explicit user-space coordinates, alpha/luminance mode, sRGB interpretation and a transformed rectangular region clip. A padded bounding rectangle avoids clipping the same antialiased region twice. Unbounded references export with no region attributes and an explicit SVG 2.0 version. Text becomes glyph outlines under the existing SVG contract. The receipt discloses loss of shared editing identity, linked state, unused sources and disabled settings. Keep the native snapshot for these properties. [SVG import](SVG_IMPORT.md) now constructs these editable sources and references, including separate content/region units and explicit versioned defaults. Supported source paints also remain subject to the existing SVG paint subset.

## Limits and verification

Documents allow 32 references, including disabled ones. Source items, geometry, paints, text and fonts share ordinary document limits. Active references together retain at most 1,048,576 output coverage samples. Compositing accounts for one f64 scalar per reference per viewport pixel, with three additional full RGBA buffers for source preparation beyond the ordinary group/text depth estimate. Aggregate repeated instance rendering and paint work are checked before allocating viewport buffers; repeated glyph outlines are capped at 131,072 commands. Transformed instance geometry is validated at render time, so an otherwise valid stored reference can fail when its transformed source exceeds world limits. Hidden sources and owners retain validation and budgeting.

SVG allows 4096 source item copies per output and artboard range, after ordinary outline expansion for each output. Artboard PNG range work counts repeated source subtrees and region sampling; each output additionally enforces its full paint/glyph work and memory limits. No partial artifact batch is returned on failure.

`tests/test_artwork_masks_cli.py` independently checks rational alpha/luminance composition, gradients, fractional region areas, transformed membership, nested masks, adjustment and layer-clipping behavior, locks and reference deletion, discovery and derived diffs, artboard bleed, original geometric-font pixels, SVG XML evaluation, resource failures, and persistent MCP retry/reopen/undo. Run the create-only [example](../examples/artwork_mask_workflow.py) to see two diagram panels sharing one editable reveal pattern.
