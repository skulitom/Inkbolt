# Native pixel selections

Native selection authoring and consumers are verified within the contract below.
Fresh full Windows/Linux acceptance and independent target-image checks passed.
It advances W4.6 in [the primary plan](../FIX_PLAN.md), without completing W4.

## Representation and adoption

An active selection is a canvas-sized unsigned coverage plane in document pixel
coordinates. Existing inline descriptors retain `width`, `height` and `gray_hex`,
with no extra serialized field. A native descriptor adds `native`, containing a
[scalar manifest](NATIVE_SCALAR_STORAGE.md) and optional private pending blocks.
Its dimensions must match the canvas and manifest; `gray_hex` must be empty.
Mixed sources, invalid blocks and dimension mismatches fail explicitly.

New fill and geometric selections above the 262,144-pixel inline ceiling use
native storage automatically. Edits to an existing native selection retain its
storage. Native planes admit up to 67,108,864 pixels and 4,096 blocks, with the
existing 32,768 axis ceiling. An old snapshot or history entry is never rewritten.
Small inline behavior and serialized identities remain unchanged.

CLI/MCP publication needs an explicit resource root or a workspace. Pure Rust
authoring retains unpublished candidates backed by owned temporary extents;
public in-memory block constructors remain file-free. Shared request reservations,
document pending limits, cleanup and publication use the existing
[private edit contract](PRIVATE_NATIVE_EDITS.md). No new block, transfer or
snapshot version is introduced.

## Authoring and consumers

Fill, geometric shape, inversion and refinement process rows. Shape combination
uses replacement, maximum, saturating subtraction or minimum. Rectangle coverage
uses exact pixel area; ellipses and polygons retain the existing 256-subrow sum
order and fill rules. Native shape integration and refinement have a separate
536,870,912-work ceiling. Large antialiased geometry or broad refinement can
still exceed it; admitting storage does not remove computation limits.

Refinement keeps horizontal results for at most `2 * radius + 1` rows. Expansion
uses maxima, contraction minima and feathering triangular weights, with zero
outside the canvas. Horizontal values remain binary64 through the vertical pass;
only the final coverage byte is rounded. Output holds one tile band and a row,
and unchanged blocks share their existing identities and pending handles.

Canvas crop, extent and scale preserve coverage using bounded native reads and
row output. They retain the existing clamp/zero-border and reconstruction rules.
Advanced resampling retains its own work and source-decoding limits.

Selection-to-mask shares a native selection's complete grid. Linked masks map
document coordinates into the target's local coordinates; unlinked masks retain
document placement. Small inline selections keep the existing cropped inline
mask behavior. A crop too large for an inline mask uses native blocks, preserving
the active selection. Permanent application then follows the whole-image native
mask contract, including retained depth, hidden color and original sources.

Brush, retouch and repair sample selection coverage at world-mapped native pixel
centers. Their memory admission includes the selection cache; native selection
verification contributes to the shared source-preparation work allowance. Every
dependency is verified, including blocks outside the edited window. A missing,
changed or corrupt source never becomes zero coverage.

Source preparation retains the shared 536,870,912-unit ceiling. Patch repair
now shares operation-local verified image and selection readers with delegated
retouch and uses its constructed result for quality checks. The subsequent
[shared-preparation acceptance](NATIVE_REPAIR.md#selected-patch-acceptance) verifies
selected self-source and separate-donor patches on a 50 MP target within that
unchanged ceiling. Document aggregate and local edit limits still apply.

Saved channels retain their bounded inline contract and reject native channel
descriptors. Channel calculation, work-path selection, image-guided selection and
composite measurement can read native selections within their existing dense
canvas limits. This does not establish native segmentation or large saved ink
channels. Structural layered delivery retains its explicit selection refusal.

## Inspection, history and acceptance

Ordinary structural inspection and diffs report a native manifest identity and
`statistics: null`. They do not invent empty bounds or zero coverage.
`document.inspect` with `selection_statistics: true` reads and verifies the plane
and returns the existing bounds, coverage counts, coverage sum and row-major
byte SHA-256. Its `asset_root` can be explicit, workspace-derived or inherited
from an exact saved revision. Cancellation applies to these reads.

Private review, transport admission, durable projection, commit, retained-object
validation, undo/redo and session resource bindings include selection blocks.
Published snapshots contain manifests; oversized requested review documents fail
before hexadecimal expansion. Private review and failed edits do not publish
blocks or alter the original document. Retained objects reject pending coverage
and verify published selection resources under the existing object contract.
`document.check` with resource checks verifies selection bytes and locates errors
at `/selection/native`. `session.verify` checks saved states and history integrity;
it does not verify the external resource files. Backups retain their explicit
resource bindings and do not copy external blocks.

Acceptance must include independent complete coverage and image-byte oracles,
inline compatibility, transformed consumers, canvas operations, review/commit/
retry/history, corruption, cancellation, both full platform suites, and a complete
50 MP selection-to-mask/edit/export workflow. Focused checks do not establish
that milestone or close the remaining scale, segmentation and layered-file work.

## Verified native selection increment

Fresh full suites passed on matching unchanged 957-file inputs:

| Platform | Fresh stages | Rust tests | Python executed | Explicit skips | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows | 265 | 304 | 2,766 | 13 | 850.500 |
| Linux / WSL | 265 | 270 | 2,728 | 51 | 561.903 |

All stages ran fresh, with no failed, pending or reused results. Seven Python
and two Rust selection tests cover independent integer coverage/refinement,
all-pixel inline comparisons, transformed consumers, canvas reconstruction,
private ownership and cleanup, corruption outside the edit window, cancellation,
review/proposal/retry/history, recovery and pinned resources. Forty-two complete
inline responses and saved-state payloads/hashes match the previous accepted engine.

The independent 8192x6144 RGBA16 workflow checks all 50,331,648 selection bytes,
every original and edited image sample, and every TIFF sample. It covers
rectangular selection and feathering, full statistics, selection-to-mask,
whole-image mask application, selected brush/retouch, publication retry and all
undo/redo states. Sample precision and original source blocks are preserved.
Windows/Linux documents, change receipts, selection hashes and TIFF hashes match.
Maximum Windows process commit was 36.094 MiB; Unix memory is unavailable.
These are one-run fidelity/admission checks, not repeated scale-v2 latency gates.

The initial full suites found changed missing-selection errors in brush/retouch;
the correction restores the existing errors for brush, retouch and repair.
Focused feedback then passed in 75.2 seconds on Windows and 51.1 seconds on Linux.
Initial focused failures, both failed full runs and the 50 MP selected patch
repair work-budget failure are retained. The accepted target explicitly verifies
that refusal leaves the revision and resources unchanged, then uses direct
selected retouch. This describes the initial selection milestone; the subsequent
[shared patch follow-up](NATIVE_REPAIR.md#selected-patch-acceptance) resolves the
refusal without weakening a source-preparation limit or acceptance criterion.

Frozen source fingerprint:
`8bd1f5a32423efe9dd03bb0e71b71fdaf0aaf06a7a624935ca95598b61723dc5`.
Retained `w4-native-selection-acceptance-02/audit.json` SHA-256:
`5a16271d3153bb3bf03ea5985eae65bf2ab3affe357097fa0d5d667ca55b7eaf`.
The audit binds sources, executables, reports, complete independent oracles,
compatibility results and retained first attempts. Subsequent documentation
changes are recorded separately. The [native region selection follow-up](NATIVE_SEGMENTATION.md) has separate
acceptance. Proxy/refine selection, large saved channels,
larger layered files, repeated scale-v2 and Unix memory
remain open. The unchanged registry stays 163/167; full W4 and the broader
agent-readiness goal are not complete.
