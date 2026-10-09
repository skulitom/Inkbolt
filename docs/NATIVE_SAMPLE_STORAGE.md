# Shared native sample storage

`sample_store` is an original Rust library primitive for immutable typed pixel blocks and read-only edit candidates. **Document, session, import, render and CLI/MCP integration is pending.** Existing sample grids still use their inline representation and limits; the practical-scale benchmark's larger workloads remain open. This primitive earns no engine checkpoint or A5 completion credit.

The separation is intentional: a proposed edit must be visible to a dry-run renderer without writing resource files. The library first constructs a private immutable `Candidate`. Its manifest describes the future content, and its pending blocks are held in memory. `replace` returns another candidate, sharing unchanged blocks; older candidates retain their original bytes. Explicit `publish` creates complete content-addressed files. A document/history transaction is a separate later commit, not implied by successful block publication.

## Data contract

`Spec` declares width, height, depth (`u8`, `u16`, `f32`), channels (`rgba`, `gray_alpha`) and encoding (`encoded_srgb`, `linear_srgb`, `profiled_rgb`). Native bytes are little-endian straight channels. Integer values are retained exactly. Binary32 validation rejects nonfinite values, requires normalized alpha and encoded values, and permits signed finite HDR color only under explicit linear encoding. Linear storage requires binary32 depth. Signed zero and subnormal bit patterns are preserved; validation does not quantize or normalize their bytes.

ICC profile assignment and conversion remain document-level meaning. The store binds the native encoding but does not contain or resolve an ICC profile. A future decoded/rendered cache must also bind the profile identity, sampling, placement and other interpretation inputs; the block digest alone is not a complete color/render key.

The v1 grid uses fixed 128×128 blocks, with smaller final row/column blocks and row-major ordering. A manifest contains `version:1`, its `spec`, ordered lowercase SHA-256 tile identities, and a root `sha256`. It contains no machine-local paths. Descriptors are validated before arithmetic, allocation or path construction. Current bounds are 32,768 per dimension, 16,777,216 pixels, at most 2,048 block references, and 65,536 pixels per read/replacement region. These library bounds do not enlarge engine document or output budgets.

Each file is `<sha256>.native-tile`. Its original canonical byte layout is:

| Offset | Value |
| --- | --- |
| 0–7 | ASCII `INKTILE1` |
| 8–11 | Actual block width, unsigned little-endian 32-bit |
| 12–15 | Actual block height, unsigned little-endian 32-bit |
| 16 | Bytes per channel: 1, 2 or 4 |
| 17 | Channels per pixel: 4 or 2 |
| 18 | Encoding: encoded sRGB 0, linear sRGB 1, profiled RGB 2 |
| 19 | Reserved zero |
| 20 onward | Exact row-major native channel bytes |

The file identity hashes its entire header and payload. The manifest identity hashes `INKGRID1`, the same 20-byte typed header with whole-grid dimensions, the tile edge as unsigned little-endian 32-bit, and each ordered tile SHA-256 as 32 raw bytes. Version 1 is explicit; other versions reject. Grid dimensions, order, edge dimensions, depth, channels and encoding cannot be silently substituted. Identical complete blocks may share an identity, including repeated positions.

## Pure candidates and bounded reads

`Candidate::from_bytes` validates a bounded complete native frame and retains only unique immutable block buffers. This constructor is not a streaming image decoder: caller-owned input plus candidate memory can cover two whole native frames. At the maximum binary32 RGBA bound that is approximately 512 MiB plus headers/metadata and temporary allocations. Import integration must account for codec buffers and its own memory budget instead of assuming chunked storage alone solves memory use.

`Candidate::from_manifest` validates the descriptor without reading storage. `read_region` and `replace` load and verify only intersecting stored blocks; a maximum region result/replacement is 1 MiB of binary32 RGBA values. An edit crossing a block boundary retains complete replacement blocks, not merely its changed pixels. Immutable pending buffers are shared across candidate clones, and obsolete unreferenced pending blocks are dropped from the new candidate. The manifest and buffers are private through the Rust API.

Candidate construction, replacement and reads never create directories or files. Pending blocks resolve from memory; inherited stored blocks resolve against an explicit root. `verify` checks every referenced dependency, including blocks outside a selected read, without retaining all loaded bytes. Missing, malformed, wrong-sized, symlink and corrupt entries reject; selected-region success alone does not certify unrelated stored blocks. Explicit roots must be absolute and honor an attached workspace's path checks.

## Publication and recovery

`publish` verifies all candidate dependencies, then writes each needed unique block to an exclusively owned temporary, flushes/closes it, and creates the final name with a create-only hard link. A competing existing file must match its declared native bytes and identity. Corrupt files and foreign destinations are preserved. Publication reports per-invocation created/existing unique block counts; it does not create a historical request receipt or a durable document.

Cancellation is checked before candidate work, between blocks and before each final link. A multi-block cancellation/failure may retain complete cache entries. After every unique descriptor has completed, late cancellation does not relabel that cache result. Ordinary return/error removes only the current invocation's temporaries. Process death may leave partial or complete unpublished temporaries, and retry retains that evidence while verifying/deduplicating complete final blocks. There is no automatic sweep or garbage collection; original inputs and old blocks remain intact.

The tested environment is the existing trusted local Windows filesystem with hard-link support. This is process-interruption/cooperative-cancellation evidence, not a claim about power loss, hostile path replacement, remote stores or other platforms.

## Evidence and integration work

`src/sample_store/tests.rs` checks every sample across depth/channel/encoding combinations and clipped edge blocks. An independent byte layout verifies file and ordered manifest identities. A 1920×1080 RGBA16 fixture tests a four-block-boundary edit, unchanged surrounding data and complete older-candidate reconstruction. Tests cover deduplication, no-op changes, private pending forks, float extremes, malformed descriptors/data/regions, explicit roots, full dependency checks and corrupt-file preservation. Owned hidden child processes are killed before writing, before linking and after linking on both blocks; additional tests cover cancellation before/after links, concurrent publishers, and foreign corrupt content created after preflight. Children are reaped and only owned temporary test directories are removed.

Next integration must carry a per-action candidate resource view through actual edits, dry-run previews and checked proposals. Session commit must publish required complete blocks before persisting new references, preserve revision/retry semantics, and retain valid orphan blocks on failure. Snapshot APIs need an explicit complete result contract. Imports, diagnostics, transfers, backups, pinned jobs, resource rebinding, native operators and all output consumers must resolve the same exact identities. Until that work is implemented and tested, `capabilities.native_sample_store_library` explicitly reports library-only status and unchanged CLI limits. Re-run the [recovery contracts](RECOVERY_CONTRACTS.md) and [scale workloads](WORKLOAD_MEASUREMENT.md) when those paths change.
