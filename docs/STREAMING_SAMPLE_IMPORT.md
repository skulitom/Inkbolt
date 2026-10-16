# Bounded native image import

This is the W4.2 implementation contract under [FIX_PLAN.md](../FIX_PLAN.md).
Native imports capture encoded input and assemble native pixels in private
seekable storage, with bounded PNG framing/metadata reads. Source/pixel staging
passed full Windows/Linux acceptance within their original ceilings. Separate
native extent and codec admission passed fresh full Windows/Linux acceptance,
including independent larger-image checks and retained memory measurements. The
complete streaming milestone and larger-workload target remain open.

Fresh full Windows/Linux acceptance includes process termination, shared capacity,
exact native imports, publication and history checks. The retained memory
diagnostic compares the prior and staged implementations on original images.
See the [evidence and measured tradeoffs](DEVELOPMENT_STATUS.md#w42-private-source-and-pixel-staging-scale-admission-open).

## Required behavior

Native PNG/TIFF imports must bound encoded-input buffering, decoded codec bands
and retained unpublished pixels independently. Retain all currently admitted
ordinary/interlaced PNG and chunky/planar, strip/tile TIFF inputs, native sample
bits, color/refusal policies, metadata, source identities and legacy/default
storage receipts. Inline import keeps its separate small-image limits.

The source is read through its explicitly checked path and never written. Copy
its bytes in bounded chunks into an owned private seekable file while computing
the receipt's SHA-256 and byte count. Decode and recover metadata from that same
immutable byte view. An open source handle alone is not an immutable snapshot.
The receipt describes the copied bytes, as the previous in-memory snapshot did;
it does not certify that an unrelated process never changed the original file.

Walk PNG framing and CRCs incrementally, retaining only bounded headers and
recognized metadata. Reject unsupported color, animation and orientation data,
late checksum/metadata errors, missing IEND and trailing bytes as before. TIFF
metadata and pixel readers share the captured source; metadata values retain
their independent size limits. Cancellation is checked between input chunks,
codec rows/bands and publication steps.

## Private staging and failure boundary

Temporary encoded/pixel data belongs to the operation, not to the document or
its resource store. Use newly created, exclusively owned scratch files in the
process's temporary directory, with no caller-supplied scratch filename. They
are never serialized, returned as resource references or reused by another
operation. Workspace/source/output paths retain their existing argument checks.
Private scratch is implementation storage outside the workspace; malformed input
must still leave the workspace and native store untouched.

On Windows, create the scratch file with exclusive sharing and operating-system
deletion on handle close. On Unix, create it with owner-only permissions and
unlink it before writing payload bytes. Closing the final handle, including on
process termination, releases its payload. A Unix interruption between creation
and unlink may leave an empty file; no payload may be written before unlink
succeeds. Never delete unknown files or sweep the temporary directory.
The lifecycle uses the documented [Windows file flags](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
and [Rust file options](https://doc.rust-lang.org/std/os/windows/fs/trait.OpenOptionsExt.html).
No claim is made about power loss, hostile filesystem replacement or filesystem
implementations that do not provide the required semantics.

One import may reserve at most 288 MiB of aggregate logical private staging
bytes, with 64 KiB copy/scan buffers. Encoded input retains its 32 MiB limit;
the private native extent admits up to 256 MiB. The 16,777,216-pixel bound is
unchanged, including its existing tile-count and dimension restrictions. This
allows all native depths within that pixel bound when source codec chunks fit
their independent budgets. File growth must be checked before writing; failed
writes must not release accounting for bytes the file may still contain. This
is an operation budget, distinct from resident memory, filesystem free space
and the persistent native-store budget. Concurrent live operations have separate
budgets; terminated operations must not retain private payload files.

Native pixels assemble in a row-major private file whose complete logical extent
is reserved before decoding. Ordinary PNG uses one reusable native row. Adam7
updates one native row at a time and retains one coverage bit per pixel, rejecting
overlap and incomplete coverage. TIFF decodes one source chunk at a time, then
merges each actual row segment into the file; separate planes preserve previously
written components. Padded codec strides remain unchanged. Typed native samples
are validated after complete assembly, including planar floating-point alpha.

Finalization reads one canonical block at a time to validate samples and derive
the existing typed identities. Publication verifies those identities again and
shares store admission with public in-memory candidates. The public `Candidate`
API remains pure and continues to retain its pending blocks in memory; private
files belong only to the importer. Existing decode-storage receipt labels remain
unchanged, including `chunk_bands_to_native_blocks` for TIFF.

Source, native extent and total staging limits are 32, 256 and 288 MiB.
Codec output/intermediate allocations retain their separate 64 MiB bounds.
Aggregate native TIFF padded tile work is separately bounded at 256 MiB; inline
TIFF retains its 64 MiB padded-work limit and 16 MiB codec allocation limits.
A single source-defined TIFF chunk can still cover a complete image and is
rejected if its codec allocation exceeds 64 MiB, even when the complete native
extent would fit on disk. No whole-frame allocation receives the disk allowance.
These limits do not establish a whole-process memory ceiling; no previously
admitted layout is silently removed. Encoded-source, canvas, render, output and
persistent-store limits are unchanged.

Validate the complete decoded content, metadata and document before publishing
any persistent block or returning a document. Publish through the existing
[serialized store admission](NATIVE_COPY_ON_WRITE.md#aggregate-store-admission),
counting deduplicated destinations and public staging aliases. Final publication
may retain complete orphan blocks under its existing interruption contract;
private preparation must not create a document, receipt or resource-store file.
No manifest, native block, document, session or receipt format changes are needed.

## Delivery and acceptance

1. Introduce and verify private scratch/source snapshots, reader-based PNG
   admission and metadata, and seekable PNG/TIFF decode. This removes the retained
   encoded-input vector; completed block retention remains explicitly unfinished.
2. Add bounded private pixel staging and integrate ordinary PNG, Adam7 and every
   admitted TIFF layout. Replace whole-frame retention checks with separate
   resident band/work and private staging admission, preserving exact behavior.
3. Verify exact independent native bytes, profiles/HDR interpretation, metadata
   and source receipts; malformed late input; cancellation; actual process death;
   competing imports; full stores; no-overwrite publication; and legacy/default
   receipt compatibility. Reimport must preserve existing block bytes and times.
4. Measure input, codec-band, retained-pixel and overall process memory on original
   fixtures that force staging. Run focused Windows/WSL feedback within 180 seconds
   and fresh full platform acceptance at the integrated milestone.

The first delivery unit is not complete streaming import. The 50 MP RGBA16 /
512 MiB edit/export workflow, larger ceilings, JPEG, streaming output and
independent `scale-v2` acceptance remain required under W4.
Private pixel staging and one-chunk TIFF retention are accepted within their
original limits. Separate codec/staging admission passed larger-fixture
measurement and full platform acceptance within the unchanged canvas ceiling. Coordinated 8192-square canvases,
larger encoded inputs/outputs and independent scale acceptance remain required.
