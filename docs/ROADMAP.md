# Roadmap and verified scope

Updated 3 October 2026. This is an initial setup, not a completion percentage.

| Milestone | Status | Acceptance |
| --- | --- | --- |
| Foundation | Implemented | Library and CLI create/validate both empty document kinds; schema, structured failures and limits tested |
| Publication boundary | Configured locally | External private root; required local policy; indexed-byte guard; negative publication tests |
| Research readiness | Private workstream | Exact target builds, original fixtures, bounded questions, source hashes, tool settings and retained evidence |
| Vector core | Planned | Paths, fills, strokes, groups and transforms with independent geometry/output checks |
| Raster core | Planned | Pixel buffers/tiles, layer order, masks, alpha and deterministic compositing fixtures |
| Sessions | Planned | Atomic edits, conflicts, safe retries, diffs, persistent undo/history and interruption tests |
| Agent adapter | Planned | MCP stdio exposes the same validated commands with protocol tests |
| Previews and exports | Planned | Explicit color and output roots; deterministic previews; no input overwrite |
| Typography and artboards | Planned | Licensed external fonts, layout limits and artboard-specific export |
| Broader interoperability | Planned | Bounded public-format subsets, loss diagnostics and exact-build external verification |
| Advanced editing | Planned | Selections, adjustments, filters, brushes, path operations and non-destructive workflows |

Start implementation with one original vector fixture and one original raster fixture. Select a minimal operation in each lane and prove its output before expanding. Private audit progress never counts as implemented editing behavior. Preserve unimplemented scope as the plan evolves.

Accounts, activation, cloud services, marketplaces, telemetry and GUI replication are outside the initial product scope. Underlying editing operations, local assistance and document interoperability remain in scope.
