# Larger native brush and retouch windows

This W4.6 increment extends local edit regions on version-2 native block layers.
Fresh full Windows/Linux suites and independent 50 MP target-image checks pass
within this contract. It does not complete W4 or the repeated scale-v2 gates.

| Operation | Version-2 native layer | Inline or legacy stored layer |
| --- | ---: | ---: |
| Brush deposition bounding rectangle | 262,144 pixels | 65,536 pixels |
| Retouch selected rectangle | 131,072 pixels | 65,536 pixels |

The brush bound includes gaps between dabs and zero-coverage cells. All four
modes retain their original ordering: smudge reads the surface frozen before each
dab, mixer pickup covers the complete dab, and stroke opacity and native-depth
encoding are applied once after all dabs. Retouch retains the entire selected
domain and its actual one-cell in-image boundary; cloning freezes its donor,
and healing solves the same global selected-domain equations. It does not split
the healing system into independently solved tiles.

Large output windows are divided into their intersections with native blocks.
Each intersection contains at most 128 x 128 pixels; each affected block is
charged and replaced once. Immutable unchanged blocks keep their identities.
The public sample-store read/replace API still admits at most 65,536 pixels.
Legacy patch history is not silently migrated. Small-window execution and
receipt representation retain their existing paths.

Both operations retain the 128 MiB conservative processing limit and 67,108,864
local-work limit. Full source/selection verification retains its separate shared
536,870,912-unit allowance. Memory admission includes complete intersecting
replacement blocks, source and selection caches, and simultaneous raw/working/
solver/output buffers. A thin window can exceed memory admission even below its
pixel ceiling. No image-wide floating-point buffer is introduced. These component
bounds do not replace whole-process measurements.
Existing snapshot, request, pending-block and optional review-document transport
limits remain applicable; a larger operation window does not enlarge them.

Cancellation, dependency corruption, quality/precision failure and later failed
operations discard the batch. Publication, dry-run proposals, retry identities,
immutable sources and undo/redo use the existing native block/session contract.

`tests/test_large_edit_windows.py` checks maximum-size paint and overlapping
clone windows across all six depth/channel formats, independent circular brush
coverage, unaligned four-mode deposition and frozen smudge sampling, maximum-size
healing, a nonzero independently solved screened domain, MCP proposals and
history, cancellation, legacy refusal and memory rejection before resource I/O.
Existing native brush/retouch and capability-limit checks remain required.

## Acceptance

| Platform | Fresh stages | Rust tests | Python executed | Explicit skips | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows | 268 | 308 | 2,790 | 13 | 1043.797 |
| Linux / WSL | 268 | 274 | 2,752 | 51 | 700.588 |

Every stage ran fresh on matching unchanged inputs, without failures, pending
checks or reused results. The seven focused window tests include independent
screened-healing equations as well as maximum-window sample comparisons.
All 36 complete small-window brush/retouch responses match the previously
accepted executable across six sample formats. Focused development feedback
passed in 114.2 seconds on Windows and 112.3 seconds on Linux; the additional
Windows healing/cancellation checks passed in 70.6 seconds.

Separate 8192 x 6144 RGBA16 workflows exercise a maximum 512 x 512 brush window
with a native 362 x 362 selection, followed by a maximum 512 x 256 frozen-source
clone. Every original, edited, historical and exported TIFF sample matches an
independent synthetic source calculation. Native block identities, pure review,
failed batches, retry receipts, undo/redo and immutable original files pass.
The two platforms produce identical TIFF hashes and change details. Saved-state
hashes are checked independently and bind each platform's own resource paths.
Brush and clone receipts occupy 1,419 and 2,034 JSON bytes respectively.

Windows peak process commit was **37.285 MiB**, below the unchanged 512 MiB
workflow target. Unix process memory remains explicitly unavailable. These are
one-run fidelity/admission measurements, not repeated latency acceptance.

Frozen source fingerprint:
`5c641a8f74b867e4932f79d3b927041a6e6201c6f6637e383bdb8996c2f9f679`.
Retained `w4-large-edit-windows-acceptance-01/audit.json` SHA-256:
`15a2b5c9988acc16c24599918ebc3956e028328f2841e782722fa324e164a7b8`.
The audit binds complete suite logs, exact executables, target workflow requests
and responses, per-sample oracles, session states and compatibility comparisons.
Later documentation updates are recorded separately. Larger layered files,
complete scale-v2 workflows, Unix memory and the original four checkpoints
remain open; the feature registry stays 163/167.

See [brush semantics](PIXEL_BRUSHES.md), [retouch semantics](RETOUCH.md) and
[native storage](NATIVE_COPY_ON_WRITE.md) for the unchanged operation contracts.
