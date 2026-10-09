# Shared native sample storage

`sample_store` provides immutable typed pixel blocks and pure edit candidates. `stored_samples` connects them to raster documents, opt-in PNG/TIFF import, exact local patch edits, session proposals/history, resource checks and bounded rendering through the shared Rust/CLI/MCP engine. Existing inline sample grids keep their representation and limits. Opt-in [tiled output](RENDER_QUALITY.md) composes full-size images with bounded filters and layer effects for a declared subset; wider filter coverage, streaming decode, broad native operators and the complete practical-scale benchmark remain open. This integration earns no engine checkpoint or A5 completion credit.

The library first constructs a private immutable `Candidate`. Its manifest describes future content and pending blocks remain in memory. `replace` returns another candidate, sharing unchanged blocks; older candidates retain their original bytes. Explicit `publish` creates complete content-addressed files. Document edits retain exact small patch bytes over the original published base manifest. Thus a dry-run or snapshot result contains its complete edit recipe without naming unpublished replacement blocks. Import publishes the immutable base; editing/history never needs a second filesystem commit.

## Data contract

`Spec` declares width, height, depth (`u8`, `u16`, `f32`), channels (`rgba`, `gray_alpha`) and encoding (`encoded_srgb`, `linear_srgb`, `profiled_rgb`). Native bytes are little-endian straight channels. Integer values are retained exactly. Binary32 validation rejects nonfinite values, requires normalized alpha and encoded values, and permits signed finite HDR color only under explicit linear encoding. Linear storage requires binary32 depth. Signed zero and subnormal bit patterns are preserved; validation does not quantize or normalize their bytes.

ICC profile assignment and conversion remain document-level meaning. The store binds the native encoding but does not contain or resolve an ICC profile. A future decoded/rendered cache must also bind the profile identity, sampling, placement and other interpretation inputs; the block digest alone is not a complete color/render key.

The v1 grid uses fixed 128×128 blocks, with smaller final row/column blocks and row-major ordering. A manifest contains `version:1`, its `spec`, ordered lowercase SHA-256 tile identities, and a root `sha256`. It contains no machine-local paths. Descriptors are validated before arithmetic, allocation or path construction. Current bounds are 32,768 per dimension, 16,777,216 pixels, at most 2,048 block references, and 65,536 pixels per read/replacement region. Raster documents admit up to 16,777,216 aggregate stored source pixels independently of the unchanged inline and output budgets.

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

`tests/test_stored_samples.py` exercises the actual CLI/MCP integration: every channel of an original 1920×1080 RGBA16 import, a four-block-boundary patch and unchanged surrounding pixels, precise TIFF output, all six native depth/channel combinations, all five sampling modes with transformed masks/filters, explicit profile/HDR interpretation, pure proposals, exact receipts, retries, undo/redo, backup/recovery, queued resource changes and historical completed jobs. It also checks malformed descriptors, bounds, cancellation, unselected corruption and unsupported delivery. These contract fixtures do not establish whole-workload latency or memory gates. Re-run the [recovery contracts](RECOVERY_CONTRACTS.md) and [scale workloads](WORKLOAD_MEASUREMENT.md) for broader claims.

## Document and agent contract

Opt in with `sample.import` and `"storage":{"store_root":"C:/absolute/native-store"}`. Under `--workspace`, `"storage":{}` selects `.inkbolt/assets`. Omitting `storage` retains the existing inline import. The source limit stays 32 MiB; native import also caps decoded native channels at 64 MiB and uses 64 MiB decoder allocation limits. This path still materializes decoded input plus native/candidate buffers and is not a streaming decoder or a measured peak-memory guarantee. Invalid document IDs, metadata or unsupported interpretations reject before publication. A failed multi-block publication may retain valid immutable cache entries under the recovery contract above.

Raster content `{"type":"stored_samples","grid":{...}}` holds `base` (the manifest), optional `patches`, optional `profile`, and `sampling`. Each patch contains a native `region` and exact little-endian `data_hex`. Patches apply in order. `sample_replace` verifies every base dependency, preserves all outside samples, and appends a patch only when native values change. It records before/after native manifest identities and `files_written:false`. At most 256 patches and 65,536 aggregate patch pixels are retained; cumulative touched-block work is capped at 16,777,216 pixels. Ordinary snapshot byte limits also apply. Patch consolidation and unbounded edit histories are not implemented.

Snapshots and session backups preserve the complete recipe, with the same explicit **external base resource dependency** as other asset-backed documents. They do not bundle native files. Bind the matching store through `asset_root`; saved references inherit session resource bindings. Render preparation checks the full base before applying patches, then caches at most 16 decoded tiles (262,144 pixels, 8 MiB of f64 RGBA). Each prepared reader permits at most twice its source pixel count in tile decoding. Cache pressure that would exceed that work rejects explicitly. Native verification, patch preparation, cache and scratch buffers participate in aggregate render budgets. No persistent cross-request cache is claimed.

Visible sources render through the existing full-precision sampler/compositor; hidden sources are checked by explicit document resource diagnostics, verified transfer and job admission/execution. A completed job receipt remains historical and can replay after source files disappear. Diagnostics expose base and recipe identities separately: a base manifest hash alone does not describe later patches or profile/sampling interpretation. Structural validation and metadata manifests do not claim file verification.

Default whole-image evaluation retains its 1,048,576-pixel limit. Explicit `render_options:{"evaluation":"tiled"}` admits up to 16,777,216 evaluated pixels, including padding and supersampling, with bounded composition tiles and the existing total-work limits. Native-depth TIFF uses bounded native strips; ordinary byte delivery keeps one complete final RGBA8 image. Encoded delivery is bounded at 32 MiB. Format-specific range/sequence budgets still apply. See [render quality](RENDER_QUALITY.md) for exact unsupported combinations and precision limits.

Existing transforms, sampling, retained scalar masks and backgrounds use the stored source. The explicit [large raster profile](LARGE_RASTER.md) enables ordinary editable vector overlays and up to 8,192 mixed raster-document items; native storage and independent processing bounds stay unchanged. Whole evaluation continues to support its existing filters. Tiled evaluation supports bounded box, Gaussian, directional and surface neighborhoods with transparent, clamp or reflect borders, plus retained shadows, strokes and overlays; it still rejects other filters, wrapped borders, artwork masks, raw development and retained-object surfaces explicitly. Native sample conversion/profile edit operations, brush/retouch/mask baking, native ink separations, layered pixel export and structural SVG/PDF delivery also reject stored content. Complete native operator coverage, representative production compositions, complete measured scale gates and other original checkpoints remain required.
