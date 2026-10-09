# Large raster layouts

`resource_profile:"large_raster"` explicitly enables larger raster documents and ordinary vector overlays over retained pixel sources. Use it on `document.create`, a raster snapshot, or the atomic `resource_profile` edit. `sample.import` still creates a standard document; change its profile before adding a large layout. This option combines the existing immutable native blocks, bounded spatial renderer and neighboring-tile traversal. It does not increase their work, pixel, cache or memory budgets.

| Storage bound | Standard raster | Large raster |
| --- | ---: | ---: |
| Stored or expanded items | 256 | 8,192 |
| Aggregate geometry and clip commands | 4,096 | 131,072 |
| Serialized snapshot | 768 KiB | 8 MiB |
| Commands in one path | 4,096 | 4,096 |

Ordinary vector geometry, fills and strokes are editable overlays under this explicit profile. Vector-only retained operators, vector canvas semantics and vector interchange retain their separate kind checks. Standard raster documents keep their existing content rules. A downgrade must satisfy both the destination storage bounds and its content rules; it never silently deletes or rasterizes overlays. `large_vector` remains vector-only, and SVG import rejects `large_raster`.

Inline mutable pixels remain bounded at 65,536; immutable native sources retain their separate 16,777,216 aggregate pixel allowance. Default whole rendering keeps its existing output and work limits. Opt-in `render_options.evaluation:tiled` uses conservative spatial membership for mixed scenes, full native sample precision and bounded composition buffers. Dense overlapping layers can still reject. Bounded box, Gaussian, directional and surface filters use expanded tile neighborhoods. Other filters, wrapped borders, effects, artwork masks, raw development and retained-object surfaces remain outside the tiled subset; a larger storage profile cannot bypass these checks. See [native storage](NATIVE_SAMPLE_STORAGE.md) and [render quality](RENDER_QUALITY.md).

Snapshots, semantic differences, proposals, receipts and history retain the profile and sources. Proposal review is pure; failed profile changes leave the current revision intact. Atomic edits may remove excess items and downgrade together. Historical revisions retain the original profile even after later edits, undo and redo. The complete request remains bounded at 16 MiB; session state allows 8 MiB plus resource roots, and the existing aggregate history ceiling remains independent. Native resources stay external and immutable.

The original `native-layout-v1` workload has a 2560x1440 RGBA16 base, 2,500 ordinary vector annotations and 2,500 raster annotations, geometric clips and a translated isolated group. An atomic revision replaces a 2x2 native region and moves one annotation of each kind. Independent arithmetic checks every native channel before and after editing and in historical output, including restored annotation footprints, unaffected pixels and source preservation. This strengthens the separate smaller wide-native composition; neither case substitutes for the fixed seven-workload suite.

`tests/test_large_raster.py` also covers explicit defaults, kind checks, snapshots, independent item/path/command/byte/pixel limits, failed downgrade, MCP proposals and receipts, undo/redo, dense-scene rejection and cancelled publication. `tools/measure_native_layout.py` measures fresh original workspaces with the same release process, machine identity and raw evidence contracts as the other [scale workloads](WORKLOAD_MEASUREMENT.md). Its independent regression gate binds this fixture and its complete driver/helper closure. These bounded cases do not establish complete practical-scale acceptance or earn an original engine checkpoint.
