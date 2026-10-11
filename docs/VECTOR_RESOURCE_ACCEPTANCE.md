# Large-vector resource acceptance

The original `vector.resources.extended` requirement is unchanged:

> Support documented large-canvas/object workloads, resource limits, cancellation and bounded error at extreme scales.

Acceptance covers the original complete 10,000- and 20,000-point square pages,
5,000 separately editable half-unit objects, saved precision, explicit limits and
cancellation. These cases now pass their independent geometry, persistence,
pixel and resource checks. This credits one original checkpoint; broader
production workloads and the separate agent-readiness gates remain open.

## Requirement and evidence

| Requirement | Implementation and verification |
| --- | --- |
| Original 10,000-point square | The fractional corner rectangle keeps bounds within `1e-7` point of the independent decimal reference before and after save/reopen. A 100 by 100 overview preserves the blue marker interior and the original one-output-pixel boundary tolerance. The square is not replaced with a thin page. |
| Rejected excessive page preserves state | A saved edit requesting a million-point square fails with `INVALID_CANVAS`. An earlier operation in the same batch also rolls back. The complete saved state, current revision, source file and preview remain unchanged, and no successful request receipt is created. |
| Original 5,000 objects | Construction from an original JSON specification retains every half-unit rectangle at its independent grid position, with total area 1,250 square points. Save/reopen, SVG and PDF retain all 5,000 objects and coordinates. Every RGBA value matches the original quarter-pixel grid. Editing one object, retrying and undoing preserves the other objects and historical source. |
| Original 20,000-point square | Original physical controls and both page axes survive saved references and content-bound snapshot files. SVG physical dimensions and PDF MediaBox times UserUnit both describe the complete 20,000-point square. A bounded overview has an independent pixel-center oracle. |
| Measured construction and memory | Five sequential optimized trials per original case record every request, result and Windows process memory high-water mark. Construction of the 5,000-object saved document must finish within the original 30-second limit; every measured synchronous process must remain below the original 4 GiB ceiling. Preview calls also retain the separately declared three-second/256 MiB overview budget. Setup, oracle and model time are not reported as engine time. |
| Explicit independent limits | Standard and large-vector profiles retain separate item, aggregate/per-path geometry, snapshot, request, hierarchy, drawing, pixel and history limits. Boundary, dense-overlap, hidden-content and invalid-downgrade cases fail without partial publication or history changes. |
| Cancellation during work | Deadlines and cancellation reach import, validation, edits, retained geometry preparation and output. Active marker and stdio cancellation release the worker and leave no published artifact. Failed preparation edits preserve history and allow a corrected retry. This is cooperative cancellation; blocking filesystem reads and individual codec calls are not forcibly interrupted. |
| Bounded extreme-scale error | Independent rational and bit-pattern oracles check transport, normalization, hierarchical composition, affine inverses, complete placement expressions, point arithmetic and final coverage. The [coordinate precision contract](COORDINATE_PRECISION.md) distinguishes absolute error certificates, nearest-binary64 fallback and quantized pixel sampling; it does not claim universal exact real arithmetic or identical external antialiasing. |

`tests/test_vector_resource_acceptance.py` joins the original geometry to saved
construction, rejected edits, create-only delivery, reopening and CLI/MCP history.
`tests/test_vector_overviews.py` checks the bounded review path and its declared
appearance subset. `tests/test_large_vector_cli.py` and
`tests/test_vector_preparation_cli.py` cover storage/work boundaries and active
cancellation. The precision modules named in the registry add independent
arithmetic, visible-coverage and edit/history evidence beyond the original fixed
fixtures. Exact reference observations, build identity, original source hashes,
raw trials and the requirement audit stay outside the repository under the
[research policy](RESEARCH.md). Milestone verification binds those records to the
tested source and optimized executable.

## Boundaries

These are the original documented workloads and numerical contracts, not a
universal maximum-performance claim. The measured construction path parses an
original JSON object specification and creates a durable session. Its process
time is not a matched interactive-application or model benchmark. Memory records
describe each owned engine process, excluding the measurement driver and desktop.

Large storage does not authorize an unlimited full-resolution raster allocation.
Use the opt-in overview for its supported content, or the separately admitted
tiled renderer. Unsupported effects, generators or appearance controls in an
overview fail explicitly. Source documents retain their full controls. Thin
details can disappear at reduced density; precision decisions use source
coordinates and the declared geometry contract.

Four original engine checkpoints remain: general curved Booleans, extended
native vector exchange, extended page exchange and extended layered raster
exchange. Practical mixed production compositions,
nonlocal filtering, persistent caches, actual model trials and the complete
seven-stage readiness audit also remain open. See [large-vector limits](LARGE_VECTOR.md)
and the [agent-readiness plan](AGENT_READINESS.md).
