# Bounded native image import

This is the W4.2 implementation contract under [FIX_PLAN.md](../FIX_PLAN.md).
The first implementation captures encoded input in private seekable storage and
uses bounded PNG framing/metadata reads. Completed candidate blocks still remain
in memory. This document does not claim that the full streaming milestone or
larger-workload target has passed.

The encoded-source slice passed fresh full Windows/Linux acceptance, including
process termination and exact native import checks. See the
[evidence and memory diagnostic](DEVELOPMENT_STATUS.md#w42-private-encoded-source-snapshots-pixel-staging-open).

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

Initially, one import may reserve at most 96 MiB of aggregate logical private
staging bytes, with 64 KiB copy/scan buffers. Encoded input retains its 32 MiB
limit and native decoded work retains its 64 MiB limit until the coordinated W4
scale change is measured. File growth must be checked before writing; failed
writes must not release accounting for bytes the file may still contain. This
is an operation budget, distinct from resident memory, filesystem free space
and the persistent native-store budget. Concurrent live operations have separate
budgets; terminated operations must not retain private payload files.

Completed native pixels must eventually spill to private staging instead of
accumulating resident blocks. Ordinary rows need only the current block band;
Adam7 and planar TIFF need bounded random-access assembly and coverage checks.
Use exact typed headers and samples when deriving final block identities. Codec
chunks that cannot be read incrementally need an explicit allocation budget;
silently dropping previously admitted inputs is not an implementation shortcut.

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
