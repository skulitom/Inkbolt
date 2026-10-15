# Shared native sample storage

See the generated [limit reference](LIMITS.md) for centralized resource ceilings.

`sample_store` provides immutable typed pixel blocks and pure edit candidates. `stored_samples` connects them to raster documents, opt-in PNG/TIFF import, exact local patch edits, native clone/heal retouch, paint/erase/smudge/mixer strokes, session proposals/history, resource checks and bounded rendering through the shared Rust/CLI/MCP engine. Existing inline sample grids keep their representation and limits. PNG imports decode ordinary rows or Adam7 pass rows and native TIFF imports decode bands of strips or tiles directly into native blocks. Opt-in [tiled output](RENDER_QUALITY.md) composes full-size images with bounded filters and layer effects for a declared subset; wider filter coverage, streaming decode for remaining formats, broad native operators and the complete practical-scale benchmark remain open. This integration earns no engine checkpoint or A5 completion credit.

The library first constructs a private immutable `Candidate`. Its manifest describes future content and pending blocks remain in memory. `replace` returns another candidate, sharing unchanged blocks; older candidates retain their original bytes. Explicit `publish` creates complete content-addressed files. Legacy document edits retain exact small patch bytes over the original published base manifest. Their pure edit and history behavior is unchanged.

W4.1's [migration and commit contract](NATIVE_COPY_ON_WRITE.md) describes the
explicit move from retained document patches to committed block manifests.
`sample_storage_migrate` opts a layer into storage version 2. Pure preparation
keeps pending blocks in shared memory; CLI/MCP document edits and session commits
publish them before returning or storing the manifest-only state. Review uses
`Candidate::transfer` and `Transfer::prepare` when an editable document is
requested. New stored imports default to version 2; `storage.storage_version:1`
explicitly retains the legacy format. Fresh Windows/Linux full suites passed
default adoption and profile/HDR migration. Growth now uses serialized
[store admission](NATIVE_COPY_ON_WRITE.md#aggregate-store-admission), counting
native bytes, interrupted stages and root entries without deleting old blocks.
Entirely deduplicated publication needs no spare capacity. Fresh full-suite
acceptance of admission passed on Windows and Linux; the larger-scale gates
remain pending.

## Data contract

`Spec` declares width, height, depth (`u8`, `u16`, `f32`), channels (`rgba`, `gray_alpha`) and encoding (`encoded_srgb`, `linear_srgb`, `profiled_rgb`). Native bytes are little-endian straight channels. Integer values are retained exactly. Binary32 validation rejects nonfinite values, requires normalized alpha and encoded values, and permits signed finite HDR color only under explicit linear encoding. Linear storage requires binary32 depth. Signed zero and subnormal bit patterns are preserved; validation does not quantize or normalize their bytes.

ICC profile assignment and conversion remain document-level meaning. The store binds the native encoding but does not contain or resolve an ICC profile. A future decoded/rendered cache must also bind the profile identity, sampling, placement and other interpretation inputs; the block digest alone is not a complete color/render key.

The version-1 block manifest uses fixed 128×128 blocks, with smaller final row/column blocks and row-major ordering. A manifest contains `version:1`, its `spec`, ordered lowercase SHA-256 tile identities, and a root `sha256`. This block format is separate from the layer's `storage_version`. It contains no machine-local paths. Descriptors are validated before arithmetic, allocation or path construction. Current bounds are 32,768 per dimension, 16,777,216 pixels, at most 2,048 block references, and 65,536 pixels per read/replacement region. Raster documents admit up to 16,777,216 aggregate stored source pixels independently of the unchanged inline and output budgets.

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

`Candidate::from_rows` gives its producer one reusable native row in ascending order. It validates every filled row, appends its segments to one unfinished block band, and retains completed unique blocks for later explicit publication. It produces the same canonical files and ordered manifest as `from_bytes`, including shortened edge blocks and exact signed-zero/subnormal binary32 bits. Cancellation is checked before and after every producer call and between completed blocks; a producer error or invalid sample returns without publication. Pending unique blocks remain in memory, so total memory still grows with image content and dimensions.

`Candidate::from_manifest` validates the descriptor without reading storage. `read_region` and `replace` load and verify only intersecting stored blocks; a maximum region result/replacement is 1 MiB of binary32 RGBA values. An edit crossing a block boundary retains complete replacement blocks, not merely its changed pixels. Immutable pending buffers are shared across candidate clones, and obsolete unreferenced pending blocks are dropped from the new candidate. The manifest and buffers are private through the Rust API.

Candidate construction, replacement and reads never create directories or files. Pending blocks resolve from memory; inherited stored blocks resolve against an explicit root. `verify` checks every referenced dependency, including blocks outside a selected read, without retaining all loaded bytes. Missing, malformed, wrong-sized, symlink and corrupt entries reject; selected-region success alone does not certify unrelated stored blocks. Explicit roots must be absolute and honor an attached workspace's path checks.

## Publication and recovery

`publish` verifies all candidate dependencies, then writes each needed unique block to an exclusively owned temporary, flushes/closes it, and creates the final name with a create-only hard link. A competing existing file must match its declared native bytes and identity. Corrupt files and foreign destinations are preserved. Publication reports per-invocation created/existing unique block counts; it does not create a historical request receipt or a durable document.

Cancellation is checked before candidate work, between blocks and before each final link. A multi-block cancellation/failure may retain complete cache entries. After every unique descriptor has completed, late cancellation does not relabel that cache result. Ordinary return/error removes only the current invocation's temporaries. Process death may leave partial or complete unpublished temporaries, and retry retains that evidence while verifying/deduplicating complete final blocks. There is no automatic sweep or garbage collection; original inputs and old blocks remain intact.

The tested environment is the existing trusted local Windows filesystem with hard-link support. This is process-interruption/cooperative-cancellation evidence, not a claim about power loss, hostile path replacement, remote stores or other platforms.

## Evidence and integration work

`src/sample_store/tests.rs` checks every sample across depth/channel/encoding combinations and clipped edge blocks. An independent byte layout verifies file and ordered manifest identities. A 1920×1080 RGBA16 fixture tests a four-block-boundary edit, unchanged surrounding data and complete older-candidate reconstruction. Tests cover deduplication, no-op changes, private pending forks, float extremes, malformed descriptors/data/regions, explicit roots, full dependency checks and corrupt-file preservation. Owned hidden child processes are killed before writing, before linking and after linking on both blocks; additional tests cover cancellation before/after links, concurrent publishers, and foreign corrupt content created after preflight. Children are reaped and only owned temporary test directories are removed.

`tests/test_stored_samples.py` exercises the actual CLI/MCP integration: every channel of an original 1920×1080 RGBA16 import, a four-block-boundary patch and unchanged surrounding pixels, precise TIFF output, all six native depth/channel combinations, all five sampling modes with transformed masks/filters, explicit profile/HDR interpretation, pure proposals, exact receipts, retries, undo/redo, backup/recovery, queued resource changes and historical completed jobs. It also checks malformed descriptors, bounds, cancellation, unselected corruption and unsupported delivery. These contract fixtures do not establish whole-workload latency or memory gates. Re-run the [recovery contracts](RECOVERY_CONTRACTS.md) and [scale workloads](WORKLOAD_MEASUREMENT.md) for broader claims.

`tests/test_native_import_rows.py` independently constructs every canonical block and manifest for PNG gray/RGB, with/without alpha, at both 8 and 16 bits across shortened block edges. Palette, low-bit and transparent-key expansion preserve hidden color and exact alpha. Interlaced PNG yields identical blocks through its pass-row path, and native TIFF through its chunk-band path; inline PNG keeps its existing representation. Late row/zlib failures, missing framing, invalid metadata and document settings create no blocks. Compact MCP dispatch matches CLI import and reuses existing files without changing their bytes or timestamps.

`tests/test_native_png_passes.py` independently enumerates the Adam7 cell and
constructs filtered streams with all five PNG filters and split compressed
chunks. Complete block identities cover every native channel/depth combination,
all low gray and palette depths, transparent keys, hidden color, narrow images,
empty passes and shortened block edges. Late filter, incomplete pass, checksum,
metadata and limit failures publish nothing. Rust fixtures also reject duplicate
or missing pixel coverage and observe cancellation during actual codec input.

`tests/test_native_tiff_bands.py` checks all native depths/channel layouts, both byte orders, interleaved/separate planes, strips/tiles, and uncompressed, LZW, both Deflate tags and PackBits. Independent canonical block bytes cover codec and native-block edges, signed zero/subnormal values, explicit HDR, missing alpha and white-zero normalization. Late compressed-chunk, alpha/range, metadata and limit failures publish no blocks. MCP reimport preserves existing bytes and timestamps. A Rust codec-reader fixture cancels during chunk input and proves no candidate is returned.

## Document and agent contract

Opt in with `sample.import` and `"storage":{"store_root":"C:/absolute/native-store"}`. Under `--workspace`, `"storage":{}` selects `.inkbolt/assets`. Omitting `storage` retains the existing inline import. The source limit stays 32 MiB; native import also caps decoded native channels at 64 MiB and uses 64 MiB decoder allocation limits. These are separate bounds, not a whole-process peak-memory guarantee.

Native PNG/TIFF imports capture the encoded source into a private seekable file
using 64 KiB buffers. Decode, metadata and source hashes use that same snapshot.
Scratch payloads live outside document resources and are released on handle close
or process exit. The operation's private staging budget is 96 MiB; existing source,
codec and pixel limits are unchanged. See [bounded import](STREAMING_SAMPLE_IMPORT.md).

Noninterlaced PNG uses `Candidate::from_rows`, normalizing byte order, expanded channels and opaque missing alpha one row at a time. Its `normalization.decode_storage` receipt is `rows_to_native_blocks`. It avoids complete decoded and normalized frame copies, but retains codec buffers, an unfinished block band and all completed unique pending blocks. Inline imports retain encoded bytes in memory and report `complete_decoded_frame`. Decoder completion, document validation and metadata recovery must all succeed before publication. PNG chunk CRC and zlib Adler-32 checks are required for both native and inline sample imports. Invalid document IDs, metadata or unsupported interpretations reject without creating blocks. A failed multi-block publication may retain valid immutable cache entries under the recovery contract above.

Interlaced PNG reports `adam7_passes_to_native_blocks`. Its original pass schedule
follows [PNG section 8.1](https://www.w3.org/TR/png-3/#8InterlaceMethods); each
decoded row must match the expected pass, line and length. Native samples scatter
directly into their final block positions. One coverage bit per pixel (at most
2 MiB) rejects overlaps and proves complete coverage before a candidate can be
returned. Byte order, transparency and missing alpha share ordinary row
normalization. Cancellation is checked before and after each codec row and during
block allocation/finalization. All unfinished block buffers stay resident until
all passes finish; deduplication happens afterward, one consumed block at a time.
The encoded source, codec buffers and one normalized row also remain resident.
This removes separate complete decoded and normalized frame copies, but is not
constant-memory decoding and does not lower or waive any existing byte limit.

Native TIFF reports `normalization.decode_storage:chunk_bands_to_native_blocks`. It retains one horizontal band of source strips or tiles across every separate plane, interleaves channels into the native row, and releases that decoded band before loading the next. Full padded row strides preserve compressed edge decoding; padding is excluded from native samples. Integer values and binary32 bit patterns retain their native precision, and missing alpha becomes opaque. Cancellation is checked around chunk reads and each produced row. A codec operation itself remains bounded and synchronous. Chunk-band height is source-defined: a single full-height strip can still require a complete decoded frame. The existing 64 MiB padded-tile work limit is unchanged. This path avoids a separate complete normalized frame, but is not a constant-memory import.

Raster content `{"type":"stored_samples","grid":{...}}` holds a storage version, `base` (the manifest), optional `profile`, and `sampling`. New stored imports use version 2 with the [block-edit contract](NATIVE_COPY_ON_WRITE.md). Missing `storage_version` means legacy version 1, which also admits `patches`. Each legacy patch contains a native `region` and exact little-endian `data_hex`. Patches apply in order. Legacy `sample_replace` verifies every base dependency, preserves all outside samples, and appends a patch only when native values change. It records before/after native manifest identities and `files_written:false`. At most 256 patches and 65,536 aggregate patch pixels are retained in version 1; cumulative touched-block work is capped at 16,777,216 pixels. Version 2 retains only the current manifest after committing, with separate pending-block budgets. Session history remains bounded in either mode; explicit continuation preserves earlier history.

Snapshots and session backups preserve the complete recipe, with the same explicit **external base resource dependency** as other asset-backed documents. They do not bundle native files. Bind the matching store through `asset_root`; saved references inherit session resource bindings. Render preparation checks the full base before applying patches, then caches at most 16 decoded tiles (262,144 pixels, 8 MiB of f64 RGBA). Each prepared reader permits at most twice its source pixel count in tile decoding. Cache pressure that would exceed that work rejects explicitly. Native verification, patch preparation, cache and scratch buffers participate in aggregate render budgets. No persistent cross-request cache is claimed.

Visible sources render through the existing full-precision sampler/compositor; hidden sources are checked by explicit document resource diagnostics, verified transfer and job admission/execution. A completed job receipt remains historical and can replay after source files disappear. Diagnostics expose base and recipe identities separately: a base manifest hash alone does not describe later patches or profile/sampling interpretation. Structural validation and metadata manifests do not claim file verification.

Default whole-image evaluation retains its 1,048,576-pixel limit. Explicit `render_options:{"evaluation":"tiled"}` admits up to 16,777,216 evaluated pixels, including padding and supersampling, with bounded composition tiles and the existing total-work limits. Native-depth TIFF uses bounded native strips; ordinary byte delivery keeps one complete final RGBA8 image. Encoded delivery is bounded at 32 MiB. Format-specific range/sequence budgets still apply. See [render quality](RENDER_QUALITY.md) for exact unsupported combinations and precision limits.

Existing transforms, sampling, retained scalar masks and backgrounds use the stored source. The explicit [large raster profile](LARGE_RASTER.md) enables ordinary editable vector overlays and up to 8,192 mixed raster-document items; native storage and independent processing bounds stay unchanged. [Clone and heal retouch](RETOUCH.md) accepts retained u8, u16 and f32 sources with bounded regional solver storage, frozen source sampling and pure exact patches. [Pixel brushes](PIXEL_BRUSHES.md) retain native depth for all four modes with bounded active-dab windows, frozen smudge sampling and pure patches. Whole evaluation continues to support its existing filters. Tiled evaluation supports bounded box, Gaussian, directional and surface neighborhoods with transparent, clamp or reflect borders, plus retained shadows, strokes and overlays; it still rejects other filters, wrapped borders, artwork masks, raw development and retained-object surfaces explicitly. Native sample conversion/profile edit operations, automatic-repair/mask baking, native ink separations, layered pixel export and structural SVG/PDF delivery also reject stored content. Complete native operator coverage, representative production compositions, complete measured scale gates and other original checkpoints remain required.
