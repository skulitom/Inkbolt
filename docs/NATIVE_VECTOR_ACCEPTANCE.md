# Basic native vector acceptance

The original `vector.interchange.basic` requirement is unchanged:

> Save and reopen the required vector interchange subset with layers, paths and artboards; verify structure and bounded pixels.

The original acceptance fixture contains two named flat layers, two opaque
filled rectangular paths and one artboard. Its complete requirement is now
verified through native import, editable native delivery, independent native
open/save/reopen, and reimport. This credits one original checkpoint. The
extended interchange checkpoint remains in progress.

## Requirement and evidence

| Requirement | Implementation and verification |
| --- | --- |
| Editable layers, paths and artboard | `vector.import` retains layer membership/order, labels, closed path controls, RGB fills and the shared artboard. Native delivery writes these records without a snapshot or preview substitute. |
| Save and reopen | Create-only publication produces an editable native file. Both the imported original fixture and an independently authored equivalent open in the native consumer, save to new files and reopen with identical structure. Reimport checks the returned controls and layer membership. |
| Bounded pixels | The original 128 by 96 scene is opaque blue, with an opaque red 32 by 24 patch at (8, 8). An independent coordinate calculation checks every RGBA channel. Original native renders, engine renders, delivered native renders before/after save, and reimported engine renders all match exactly. |
| Remain editable | The public regression hides the reimported patch and verifies every resulting blue pixel, while preserving the input document and published source bytes. Additional tests cover layer/path visibility, locks and normal opacity. |
| Preserve sources and reject unsupported input | Read-only source hashes, create-only outputs, bounded parser failures, explicit color policy and unsupported-semantics errors are checked. Saved revision retries, undo, durable receipts, background jobs and CLI/MCP parity use the shared implementation. |

`tests/test_native_vector_delivery.py` contains the original acceptance geometry
and its independent pixel oracle, plus delivery, units, identity and publication
checks. `tests/test_native_vector_import.py` separately checks source controls,
container/compression validation, pixels, saved edits and source preservation.
The feature registry names the executable evidence. Exact native build identity,
original fixture provenance, raw observations, returned files and source hashes
remain outside the repository under the research policy. Milestone verification
binds the tested source tree and executable to those observations.

## Boundaries

This acceptance uses the original fixed geometry and scope. It does not replace
the extended requirement with a simpler case. Complex text/effects/links,
older-version loss handling and the complete extended acceptance remain open.
Malformed source rejection is already exercised, but it does not award partial
credit to that checkpoint.

The [import contract](NATIVE_VECTOR_IMPORT.md) and
[delivery contract](NATIVE_VECTOR_DELIVERY.md) define the admitted subset and
explicit failures, including empty delivery layers, nested containers, strokes,
resources, unsupported labels and nonzero bleed. Exact pixels for the original
opaque rectangular fixture do not imply identical external antialiasing, color
management or opacity quantization for other artwork. Additional controlled
curved, transformed, visibility and opacity cases preserve native reopen
structure/pixels and engine reimport pixels, with external rendering differences
recorded separately. Keep source files and loss receipts.

This checkpoint does not complete the separate seven-stage agent-readiness
goal. Current engine totals and remaining criteria are in the
[implementation report](IMPLEMENTATION.md).
