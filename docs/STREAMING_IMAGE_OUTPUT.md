# Bounded image output

This implements W4.5 under [FIX_PLAN.md](../FIX_PLAN.md), ahead of coordinated
scale admission. The first implementation connects PNG output to bounded codec
bands and private encoded storage. The PNG phase passed fresh full Windows/Linux
acceptance, followed by the TIFF publication phase below. Current image and
encoded-output limits remain unchanged. JPEG output now also has fresh full Windows/Linux acceptance below. Coordinated
scale admission and complete scale acceptance remain open.

## JPEG output contract

Feed the locked JPEG encoder from bounded RGBA8 bands in tiled evaluation,
preserving neighboring-tile traversal and the existing native-reader cache.
Keep bands within 32 MiB, and buffer encoded writes within 64 KiB. The codec
retains at most one MCU row of three padded component planes (8 rows for full
chroma, 16 for half); profiles and renderer working storage are additional.
Whole evaluation keeps its existing bounded composition and RGBA8 frame.

Apply the existing explicit matte before output-profile conversion. Preserve
quality, sampling, density, quantization, metadata placement before the first
scan and exact historical encoded bytes. A failed or cancelled row callback
must poison subsequent encoded writes and return the original failure; filler
rows required by the codec's infallible callback cannot produce an artifact.
Check cancellation on each requested row and at most 64 KiB of encoded writes,
as well as completion; checking a filesystem marker for every entropy byte
would add avoidable work. Row errors still poison the very next write.
Check final writes and flushing before publication. Use the shared private
encoded file for delivery and count/hash-only storage for file-free preflight;
inline output necessarily retains encoded bytes and base64. No image or output
ceiling changes are part of this step. Require independent decoded-image,
compatibility, memory and fresh Windows/Linux evidence before acceptance.

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
Linux acceptance. TIFF publication acceptance follows below. Explicitly
budgeted JPEG output, coordinated larger ceilings and the complete independent
`scale-v2` gates remain required.

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

## TIFF publication contract

TIFF publication encodes directly into bounded private seekable storage,
without assembling an encoded byte vector or a base64 artifact first. Preserve
the current codec, strip layout, byte order, native projection, compression,
alpha, profile, density, metadata and artifact fields. Native tiled output keeps
its existing bounded strips; ordinary RGBA8 TIFF and whole native evaluation
retain their existing pixel buffers. This change does not claim a streaming
pixel path for every TIFF mode or increase any image/output ceiling.

The seekable sink must bound the final byte extent before writing, including
forward seeks and backpatches. Count overwritten bytes once. Check cancellation
on writes, seeks, flushes and final readback. A failed seek/write/finalization
poisons the complete payload. Read and hash the finished bytes with bounded
buffers before the existing staging/receipt protocol can publish them. Reuse
the private-file lifetime rules verified above.

Inline TIFF retains encoded bytes/base64 as its explicit result. File-free TIFF
preflight retains one bounded encoded buffer to support codec backpatches and
final hashing, without the base64 round trip. Its memory remains part of the
future scale gates; no constant-memory preflight claim is made. PNG preflight
continues to use its count/hash sink. Exact current inline/preflight/publication
bytes and historical durable retries must remain compatible.

Acceptance requires seek/extent/hole/overwrite boundaries, late failure and
cancellation, independent native samples and RGBA8 color/alpha checks, all
current depth/channel/compression combinations, no-file preflight, private
cleanup, CLI/MCP parity, existing no-overwrite/recovery tests, isolated memory
measurements and fresh full Windows/Linux verification.

## Verified TIFF publication phase

Fresh full suites passed on matching unchanged inputs, with no failed, pending,
outside-scope or reused checks:

| Platform | Stages | Rust tests | Python executed | Explicit skips | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows | 260 | 263 | 2,729 | 13 | 870.390 |
| Linux / WSL | 260 | 229 | 2,691 | 51 | 584.872 |

Six integration tests cover every native depth/channel/compression/evaluation,
independently decoded uncompressed/Deflate samples, stored blocks, profile and
associated-alpha equations, metadata/density, HDR, artboards, saved revisions,
MCP durable replay, file-free preflight and private cleanup. LZW reimport uses
the engine and is not independent codec evidence. Five new Rust checks cover
extent/seek/hole/overwrite bounds, cancellation, changed readback extent and
final directory-pointer failures in all three TIFF encoder routes. Existing
private-payload lifetime, no-overwrite, crash and recovery suites also ran.

All 48 retained inline artifacts match the accepted pre-change `6a674d2` build
byte for byte, including their fields. An actual receipt created by that build
replays under the new build without changing the output or its timestamp.

Three isolated Windows debug publications per arm and original fixture retained
OS lifetime peak commit and wall time. An independent TIFF tag/strip reader
checked every channel against the original row equations:

| Original fixture | Prior memory | New memory | Prior time | New time |
| --- | ---: | ---: | ---: | ---: |
| Empty 3072x1024 RGBA8 | 51.980 MiB | 21.008 MiB | 1.131 s | 0.994 s |
| Stored 2048x1536 grayscale delivered as RGBA16 | 81.891 MiB | 21.715 MiB | 5.431 s | 5.102 s |

Every publication has identical old/new bytes; native inputs remain unchanged.
Fixture generation and checking are outside the measured process. Separate
single preflight observations retained 43.004/69.879 MiB in the new build for
these two fixtures; preflight still holds one encoded buffer. These synthetic
diagnostics do not establish release latency, photographic performance, the
50 MP workflow or scale-v2 acceptance.

Source fingerprint: `c32922061ede418fe97d2925125e00464310c4e4d114280b03eeb8ead8fab2f6`. Retained audit
`w4-tiff-output-acceptance-02/audit.json` SHA-256:
`951ae7dd8641a1e3fc158b928a2533ac45d0123a44baff3ac715cb8a6ae7c58d`.
The audit binds unchanged measured engine code to the accepted source; its
only measurement-source difference is synthetic-test failure reporting. It
retains the source, full logs, measurements, compatibility outputs and earlier
failed focused checks. Initial
failures concerned test placement and fixture assumptions; their corrections
did not relax engine checks. Focused Windows/Linux feedback completed in
55.2/74.8 seconds. The first two full Windows runs were stopped after an external
B10 client failed;
retained same-build standalone and parallel reruns passed, but the cause remains
unestablished. The synthetic test now retains bounded failure details; no
timeout or production client logging policy changed. The fresh full Windows
rerun recorded here is acceptance, not proof of a timing fix. Prior unrelated
recovery timing intermittency also remains open.

At that TIFF milestone, JPEG budgeting was still pending; its subsequent
acceptance follows below. Coordinated scale admission and complete independent
scale acceptance remain required. This change is outside v0.82.0 and adds no
original engine-checkpoint credit.

The locked PNG [stream writer](https://docs.rs/png/0.18.1/png/struct.Writer.html#method.stream_writer_with_size)
provides bounded chunk encoding; no new dependency is introduced.

## Verified JPEG phase

Fresh full suites passed on matching unchanged inputs. Every stage ran fresh;
none failed, remained pending or reused a result:

| Platform | Stages | Rust tests | Python executed | Explicit skips | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows | 261 | 269 | 2,734 | 13 | 1003.969 |
| Linux / WSL | 261 | 235 | 2,696 | 51 | 566.980 |

Five new integration tests cover independent matte/profile input equations,
stored images across bands, MCU padding, metadata/density, byte agreement across
inline/preflight/publication, saved-revision MCP receipts, no-overwrite behavior,
file-free preflight, late alpha refusal, cancellation, private cleanup, HDR views
and artboards. Six Rust checks cover the infallible-row error bridge, cancelled
rows, bounded encoded-write cancellation, final-marker and flush failures, split multipart metadata and incomplete
headers. Existing renderer, PNG/TIFF, private-storage and recovery suites ran too.
The initial focused Windows/Linux checks passed in 91.3/128.2 seconds;
after bounded cancellation-marker polling, focused Windows checks passed in
66.9 seconds.

All 50 retained complete inline artifacts match the accepted pre-change
`8232222` build byte for byte. They cover quality 1/90/100, both chroma settings,
whole/tiled evaluation, profiles, explicit matte, supersampling, metadata and
band boundaries. A receipt created by the old build replays under the new build
without changing its file bytes or timestamp.

Pillow 10.3.0 independently decoded twelve original 97x271 smooth colour cases
with and without an output profile. Every channel passed the predeclared maximum
error bounds of 9/6/4 byte values at quality 75/90/100, respectively. A separate
8192x65 native image enlarged to 32768x260 also retained exact old/new artifacts;
its independently decoded maximum error was 1 within the declared bound of 3.
These are fixture-specific error bounds, not guarantees for arbitrary artwork.

Three isolated Windows debug publications per arm and fixture retained OS
lifetime peak commit and wall time. Pillow checked every decoded channel against
the original generator. All twelve publications retained identical old/new
encoded bytes and immutable native inputs:

| Original fixture | Prior memory | New memory | Prior time | New time |
| --- | ---: | ---: | ---: | ---: |
| Empty 4096x4096 canvas with explicit white matte | 168.199 MiB | 13.082 MiB | 10.848 s | 9.125 s |
| Stored 2048x1536 row-hashed grayscale | 48.883 MiB | 19.742 MiB | 5.921 s | 5.493 s |

The constant matte decoded exactly; the stored fixture's largest error was one
byte value at quality 100. The generator and oracle are outside the measured
engine process. Single new-build preflight observations used 13.102/19.758 MiB
for the same fixtures. Timings remain diagnostic: these runs do not establish
release latency, photographic performance, the 50 MP workflow or scale-v2.

Source fingerprint: `1ae1cefc5de6fde022ad419b402cebd016afa9dab5f312c8bd640abbf4d0cbbe`. Retained audit
`w4-jpeg-output-acceptance-02/audit.json` SHA-256:
`848f8ec54f74a55831577d07f20137b1cc06d80bbc7744fc2735938e32a2ba11`. The audit rereads all frozen source and logs, binds the measured
binary to full Windows acceptance, and checks compatibility/fidelity outputs
and original native inputs. Earlier focused failures remain retained: unused
code after extraction and an incorrect segment-length test expectation were
corrected without relaxing engine behavior. A separate timing diagnostic then
found filesystem cancellation probes on tiny codec writes. Bounded polling
removed that overhead while preserving row-error poisoning and completion
checks; the earlier full suites and measurements remain retained separately.
Earlier unrelated benchmark and
recovery intermittency is not claimed fixed.

JPEG publication and file-free preflight now avoid complete encoded buffers;
tiled evaluation avoids complete RGBA8/RGB frames. Whole evaluation and inline
responses retain their declared storage. Coordinated larger-scale admission,
bounded large TIFF preflight and independent scale acceptance remain open.
This change is outside v0.82.0 and adds no original engine-checkpoint credit.
