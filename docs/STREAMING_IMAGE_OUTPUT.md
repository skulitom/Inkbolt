# Bounded image output

This implements W4.5 under [FIX_PLAN.md](../FIX_PLAN.md), ahead of coordinated
scale admission. The first implementation connects PNG output to bounded codec
bands and private encoded storage. The PNG phase passed fresh full Windows/Linux
acceptance; current image and encoded-output limits remain unchanged. Other
output formats and complete scale acceptance remain open.

Tiled PNG publication assembles only the current bounded output band; it does not
allocate a separate complete RGBA8 frame, encoded byte vector or base64 response.
A short image can fit within one band. Preserve tile coordinates,
antialiasing, transparent sample normalization, output profiles, density,
metadata policy, artboards and receipt fields. Whole evaluation retains its
existing bounded composition surfaces. Inline export necessarily retains its
encoded/base64 result, but uses the same encoder as file publication.

Keep the RGBA8 output band within 32 MiB and the compressed PNG chunk buffer
within 64 KiB; codec row buffers and compression scratch remain additional.
Check cancellation between tiles, bands and encoded writes. Enforce the existing
output byte bound before accepting a write, including headers and metadata.
Explicitly finish the compressor and final PNG chunk; errors from final writes
must prevent publication. An encoding change may change compressed bytes, but
inline export, preflight and publication of the same current inputs must agree
exactly. Previously durable receipts keep their original bytes and identities.

Preflight counts and hashes the encoded stream without creating any file or
reserving the destination. File publication retains the exact stream in private
temporary storage: exclusive delete-on-close handles on Windows, owner-only
files unlinked before payload on Unix. Private payloads disappear on normal
failure, cancellation and process exit. Their disk extent is bounded separately
from render memory. Copy to the existing output staging file with bounded,
checked reads; verify its length/hash before entering the established durable
receipt and create-only hard-link commit protocol. Never infer ownership from
equal bytes or remove an existing destination. Prepared receipt recovery, late
cancellation and historical retry behavior remain unchanged.

Acceptance requires original independently checked images across short bands,
native storage, antialiasing, profiles, metadata, artboards and HDR display views;
byte agreement across CLI/MCP export, preflight and direct/durable publication;
write/finalization failures, cancellation, size boundaries, no-overwrite races
and existing process-crash/recovery suites. Compare isolated peak process memory
with the prior build on retained synthetic content, then run fresh Windows and
Linux acceptance. Streaming TIFF, explicitly budgeted JPEG output, coordinated
larger ceilings and the complete independent `scale-v2` gates remain required.

## Verified PNG phase

Fresh full Windows and Linux acceptance passed all 259 stages per platform
on matching unchanged inputs, without failures, pending checks or reused results.
Windows ran 258 Rust and 2,723 Python tests with
13 explicit skips in 959.047 seconds; Linux ran
224 Rust and 2,685 Python tests with
51 explicit skips in 591.040 seconds.

The seven new integration tests independently check native samples, a
32768-pixel-wide enlarged source, profile transfer, transparency, supersampling,
HDR display views and artboard bleed;
they also compare inline, preflight and direct/durable publication bytes.
Rust checks cover size/cancellation poisoning, bounded verified copy, Unix
permissions, process-death cleanup and a rejected final PNG chunk. The owned
child signals only after writing and reading its complete private payload;
the parent then terminates that exact child and verifies cleanup on both systems.
Existing publication, history, recovery, metadata and rendering suites also ran.

An isolated Windows debug-build comparison retained three publications per arm
and fixture. Pillow 10.3.0 independently decoded every row against the original
generator. Median whole-process peak commit and wall time were:

| Original synthetic fixture | Prior memory | New memory | Prior time | New time |
| --- | ---: | ---: | ---: | ---: |
| Empty 4096x4096 canvas | 73.086 MiB | 13.500 MiB | 7.475 s | 7.211 s |
| Stored 4096x2048 row-hashed grayscale | 93.137 MiB | 22.336 MiB | 24.184 s | 24.063 s |

Memory excludes the fixture/oracle driver; these are OS lifetime peaks of each
owned engine process. Every output channel and immutable native input passed.
The new output path uses less memory in these diagnostic runs; timings are
recorded separately and do not establish production performance.
This is not release-performance, photographic, 50 MP or complete scale evidence.

Source fingerprint: `2df00b88dab8796c134466463580bd169bdde60a6609863d54dfe8e16cd975e3`.
Retained `w4-png-output-acceptance-02/audit.json` SHA-256:
`0fbefa78af9480c8d8dbebc3a181f19d064b49ee5aa8138b5db1d9184092b4b4`. The audit rereads the frozen source and full logs,
binds the measured binary to Windows acceptance and indexes all three measurement
attempts, including the initial driver error. The first full runs reproduced a
wide-native decode-work regression and were stopped with their logs retained.
A 32 MiB band allowance now keeps the native
reader traversal together where it fits, without raising cache/work limits.
The existing wide-source pixel/history suite passes on both platforms.
Earlier fixture/probe failures remain retained; the oversized probe and restricted
Linux process inspection were replaced by the deterministic owned-child check.
Existing cache, work and image limits are preserved.
See [development status](DEVELOPMENT_STATUS.md#w45-bounded-png-output-other-formats-and-scale-open).

The locked PNG [stream writer](https://docs.rs/png/0.18.1/png/struct.Writer.html#method.stream_writer_with_size)
provides bounded chunk encoding; no new dependency is introduced.
