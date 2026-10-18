# Larger native images and file delivery

This implements the coordinated admission part of W4 in [FIX_PLAN.md](../FIX_PLAN.md).
Target-sized checks and fresh full Windows/Linux acceptance passed. Complete storage, larger layered
files and independent scale-v2 gates remain open; these limits do not complete W4.

## Separate budgets

| Boundary | Current ceiling | Scope |
| --- | ---: | --- |
| Raster source and tiled evaluation | 67,108,864 pixels | Includes padding and supersampling; maximum dimension remains 32,768 |
| Native block references | 4,096 | 128-pixel edges; partial edge blocks also consume references |
| Native encoded source | 544 MiB | Captured into private seekable storage |
| Native decoded extent | 512 MiB | Private disk extent, sufficient for 8192×8192 RGBA16 |
| Private native edit extents | 512 MiB plus at most 4,096 block headers | Shared control and distinct document extents; resident/transport limits remain separate |
| Aggregate import staging | 1,056 MiB | Source plus decoded extent, reserved before writes |
| Native TIFF padded work | 512 MiB | Separate from each actual codec allocation |
| PNG/TIFF codec allocation | 64 MiB | Unchanged; source-defined chunks can still be refused |
| Native JPEG decoded output | 192 MiB | Its separate conservative working estimate remains 384 MiB |
| PNG/JPEG/TIFF file output | 544 MiB | Private streaming output or file-free preflight |
| Inline and other encoded output | 32 MiB | Includes base64 delivery; file capacity does not enlarge responses |
| Native edit source preparation | 536,870,912 units | Shared by all stored readers in one brush/retouch operation |
| Tiled render work | 536,870,912 units | Preparation and all band visits charged cumulatively |

The output allowance covers a 512 MiB RGBA16 extent plus codec and metadata
headroom. It is an upper bound, not a guarantee that every admitted image, codec,
compression choice or metadata combination will fit. Binary32 RGBA at the full
pixel ceiling exceeds the native extent budget. Native JPEG may hit its working
or scan-work ceiling before its decoded-output or pixel ceiling.

Whole rendering keeps its 1,048,576-pixel and 67,108,864-work limits. Tiled work is
separate from resident compositor storage, spatial-index membership, paint,
filter, effect, resampling and artwork-mask budgets. A simple stored source uses
three preparation units per source pixel; tile composition and every replay add
their actual cost. Retained objects share the root request's aggregate work
budget while each child also satisfies its own evaluation limits. Native cache
size and the two-source-decoding-pass allowance are unchanged. Local brush and
retouch computation keeps its previous work and memory bounds; full-source
verification is charged separately and is never skipped. Edit receipts retain
total work and additionally report source preparation and local work.

Ordinary assets and sequences share the larger pixel ceiling but retain their
in-memory input, codec, work and output bounds. Buffered formats can retain a
complete final RGBA8 frame, up to 256 MiB. Use native storage and tiled PNG/JPEG
or explicit-depth TIFF file delivery for the bounded image workflow. These
component bounds are not a whole-process memory guarantee.

## Compatibility and verification

No snapshot, native block, history or receipt version changes. File output uses
the existing create-only publication protocol. Durable receipts admit the larger
extent only for PNG, JPEG and TIFF; other formats retain their earlier bound.
Preflight uses the same file-output ceiling without creating a destination.
TIFF preflight retains its verified two-pass encoding and cumulative work checks.

Focused Windows/Linux checks cover separate inline/file admission, source growth,
size rejection, exact native bytes, receipt replay, cumulative rendering and
generated discovery limits. The final boundary follow-up passed in 86.7 seconds
on Windows and 65.9 seconds on Linux; it is separate from full acceptance:

| Platform | Fresh stages | Rust tests | Python executed | Explicit skips | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows | 261 | 286 | 2,735 | 13 | 787.906 |
| Linux / WSL | 261 | 252 | 2,697 | 51 | 494.359 |

All full-suite stages ran fresh on matching unchanged inputs, without failures,
pending checks or reused results. Original 167-checkpoint criteria and the
163/167 registry remain unchanged. Earlier generator/padded-TIFF fixture failures,
the SVG aggregate fixture failure, the failed full Linux sweep and interrupted
full runs are retained.
The interrupted runs are not acceptance. Test corrections preserve rejection
above the new limits, including the specific SVG aggregate-pixel diagnostic.

The later [hosted Windows/Linux/macOS matrix](PLATFORMS.md) passed all 261
stages fresh at `c8945ca`, with matching unchanged source inputs and passing
minimum-compiler checks. Those reports and logs are retained separately from
the target-size measurements below. Unix memory verification and background
jobs remain open.

## Independent target-size evidence

Optimized Windows and Linux binaries ran original synthetic inputs. The oracle
checks complete images and stored blocks; fixture generation and independent
decoding run outside the measured engine process.

| Original case | Independently checked outcome | Maximum Windows process commit |
| --- | --- | ---: |
| 8192×8192 true RGBA16 TIFF | Every native block, every exported TIFF sample, file-free TIFF preflight identity, durable retry and every PNG channel | 35.781 MiB |
| 8192×6144 true RGBA16 image (50,331,648 pixels) | Four-block patch, textured local brush, every native sample, TIFF delivery/retry, pinned original, both undo states and session verification | 34.867 MiB |
| 6000×4000 baseline and progressive JPEG | Every decoded channel against pinned Pillow 10.3.0; maximum difference one code value within the existing three-value tolerance | 283.957 MiB |
| Sparse A2 page at 300 ppi (4961×7016) | Every PNG pixel and independently parsed PDF geometry, color and page dimensions | 13.832 MiB |

The RGBA16 sources use independent full-depth values, rather than expanding
8-bit samples. The brush changes an exactly specified local footprint; the
patch and unchanged pixels are checked separately. All original files remain
unchanged. The initial 50 MP brush attempt failed on source-preparation work;
that failure is retained with the subsequent implementation and passing runs.

Each operation was measured once. These are admission and fidelity diagnostics,
not repeated latency acceptance or general photographic/complex-layout evidence.
Windows figures use lifetime process commit peaks from the owned process handle.
Linux memory remains explicitly unavailable. The original scale-v1 and B10
budgets are unchanged. Full scale-v2 still requires the complete 50 MP native
brush/repair/mask/history workflow, larger layered-file coverage, repeated
workload gates and independently verified Unix memory. The subsequent
[native repair contract](NATIVE_REPAIR.md) has separate full Windows/Linux
acceptance and 50 MP evidence for all four repair actions. Whole-image native
[mask application](PRIVATE_NATIVE_EDITS.md) subsequently passed fresh full
Windows/Linux acceptance, every-sample 50 MP checks and the Windows memory target.
[Native selections](NATIVE_SELECTIONS.md) subsequently passed full Windows/Linux
acceptance and complete 50 MP shape/feather/mask/selected-brush/retouch/history/TIFF
checks. Selected patch repair still exceeds its shared source-preparation budget
at that size; its refusal preserves the revision and resources. Complete W4,
repeated scale-v2 and Unix memory acceptance remain open.

Frozen full-suite input fingerprint:
`7d9dda670159acf7caea6470674fce5b2ef6f657677f60ba56fc335f8ced5e83`.
Retained `w4-scale-admission-acceptance-04/audit.json` SHA-256:
`62cc65cb7a89f08bb13c254386ae42d5e428faf2307106f3c9dea9dd7b04873f`.
The audit retains source, full/focused logs, failures, both optimized binaries,
original fixtures, requests, responses, output inventories and independent
oracle scripts. Only test fixtures and active documentation changed after
the optimized target runs; all engine/dependency inputs are identical. Subsequent
status updates are documented separately from the frozen test candidate.
