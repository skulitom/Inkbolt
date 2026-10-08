# Dimensional vector artwork

Both dimensional vector checkpoints are verified. The original engine retains closed geometry, extrudes it along negative Z, rotates it around a declared pivot, projects it and generates flat-lit vector faces. Forty-eight independent inverse-ray cases check orthographic/perspective visibility, concavity, holes, disconnected regions and lighting. Actual SVG/PDF path parsing, source preservation, expansion, resource rejection and isolated offline execution have separate evidence.

## Source and editing

Use `content.type:"volume"` with a `volume` specification. It requires `geometry`, `depth` and `material`. Optional controls are `fill_rule`, `rotation`, `pivot`, `translation`, `camera` and `tolerance`. `volume.inspect` accepts a document and item ID and returns retained source, projected geometry, 3D vertices/normals, face colors and far-to-near order. Atomic `volume` edits replace the specification on an ordinary vector or existing volume item.

```json
{"type":"volume","volume":{"geometry":{"shape":"rect","x":8,"y":8,"width":24,"height":20},"depth":8,"rotation":[20,35,0],"pivot":[20,18,-4],"material":{"type":"diffuse","color":[40,150,220],"ambient":[0.15,0.15,0.15],"lights":[{"direction":[-0.3,-0.4,1],"color":[1,1,1],"intensity":1}]}}}
```

The original profile lies at Z=0 and extrudes to Z=-depth. Zero depth produces a two-sided plane. Rotations are degrees about the explicit pivot, applied X then Y then Z; translation follows. The default pivot/rotation/translation is zero. Coordinates use a right-handed 3D basis with projected X/Y mapped directly to document X/Y. Ordinary item/ancestor transforms apply after projection. Separate volumes follow ordinary document stacking, without a shared 3D scene.

Closed profiles can be concave, nested or disconnected. Nonzero/even-odd filling determines exterior and hole boundaries; redundant nonzero interior contours do not produce walls. Source curves use the existing exact rational identity-map chord certificate. Tolerance defaults to 0.1 source units, in 0.000001..1. This bounds the generated profile relative to the original curve parameterization; it is not a screen-space or topology-preservation certificate. Generated polygonal contours undergo exact rational intersection, touch, area and nesting checks. Invalid or collapsed polygonal topology fails explicitly. Original source geometry remains unchanged.

## Camera and materials

The default camera is `{"type":"orthographic"}`, viewing from positive Z. Perspective is explicit:

```json
{"type":"perspective","principal":[32,32],"distance":100,"near":10,"far":200}
```

For a placed vertex `(x,y,z)`, perspective maps each X/Y offset from the principal point by `distance/(distance-z)`. Distance is 1..32768, near is 0.01..distance, far is distance..65536, and distance/near cannot exceed 128. Every source vertex must stay within that depth interval and ordinary coordinate bounds; no implicit camera clipping occurs.

`{"type":"unlit","color":[40,150,220]}` retains its encoded sRGB color. `diffuse` decodes the RGB8 albedo to linear sRGB, multiplies each channel by ambient plus directional Lambert terms, clamps to 0..1, then encodes the face paint to sRGB without intermediate byte rounding. Ambient/light colors are linear RGB in 0..1. A light direction points toward the light in post-rotation 3D space and is normalized explicitly; there are at most eight lights, each intensity 0..8. Materials are built into the CPU engine and require no model files, textures, GPU or accounts. Surface alpha is opaque; ordinary item opacity applies to the composited solid.

Back faces are culled. Original bounded plane partitioning splits visible faces where needed and orders them far to near. Plane classification/splitting and rigid projection use binary64 arithmetic; the existing rasterizer has its own edge quantization. The small independent fixtures compare every ideal face sample against inverse rays, and separately compare binary preview pixels outside a 1/32-pixel edge band. That band reflects the existing 26.6 vertex quantization and is not a universal preview error guarantee. Existing antialiasing can also round coverage independently on neighboring faces.

## Expansion and limits

`{"op":"volume_expand","id":"solid"}` produces an isolated group of ordinary independently editable vector faces. It freezes tessellation, depth, rotation, camera and lighting; the receipt reports these losses. Source snapshots and durable undo preserve the dimensional controls. PNG/SVG/PDF share the same generated faces; vector delivery keeps ordinary paths and does not retain the dimensional model.

There are at most 128 generated profile edges and 192 partitioned visible faces, within the ordinary 256-item/4096-command document limits. Depth is 0..4096. All transformed/projected coordinates must remain within +/-32768. Unknown controls, intersecting/touching polygonal contours, unsupported material types, out-of-range cameras and resource excess fail explicitly. Bevels, revolution, textures, cast shadows, transparent internal surfaces and cross-volume 3D occlusion are not implemented. Locks, atomic batches, copies and session history follow the existing document contract.

## Offline availability and evidence

All material and geometry processing is built into the local CPU engine. A Windows AppContainer with zero capabilities was used to verify execution without network access; the child token was inspected before each run. A connection probe succeeded outside the container and returned access denied inside it. Two independent runs each of inspection, expansion, PNG, SVG, PDF and snapshot delivery produced exactly the ordinary execution bytes. Input files were retained, inherited output handles captured results, and the owned container profile and file grants were removed afterward. The computer connection was unchanged. This uses the documented [Windows AppContainer isolation](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation) and [process launch contract](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer).

The independent corpus checks 307,200 source geometry/color channels and 614,400 channels from parsed native vector delivery against inverse-ray visibility and linear-light equations. Consumer preview checks retain fixed edge bands and byte bounds as described above. Source parameters, locks, masks, component placements, artboards, exact expanded pixels and durable retry/undo are covered by original tests.

Run `python examples/volume_workflow.py --output <new-directory>` for an original dimensional node, source snapshots, PNG/SVG/PDF delivery, editable face expansion and undo receipts.
