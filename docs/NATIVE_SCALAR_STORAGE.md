# Native scalar blocks for masks and selections

This is the format and migration contract for W4.6's grayscale block storage.
The storage primitive has full acceptance. [Item and filter mask integration](NATIVE_MASKS.md)
now has fresh full Windows/Linux acceptance. Native
selection authoring and whole-image mask application remain open. Existing
inline planes retain their representation and limits.

## Representation and compatibility

A scalar grid stores exactly one unsigned coverage byte per pixel: 0 means no
coverage, 255 means full coverage, and intermediate values are proportional
coverage. There is no alpha channel, color profile or transfer curve. It is not
an artwork image interpreted as a mask.

`scalar_store::Spec` contains `width` and `height`. Its version-1 manifest has
`version`, `spec`, ordered row-major `tiles`, and `sha256`. Blocks use the same
128-pixel edge, shortened edges, 67,108,864-pixel grid limit, 4,096-reference
limit and 65,536-pixel read/replacement bound as native image storage. Dimension,
reference and region checks precede allocation and file access.

The scalar format has its own identity domain:

| Offset | Value |
| --- | --- |
| 0–7 | ASCII `INKSCAL1` |
| 8–11 | Actual block width, unsigned little-endian 32-bit |
| 12–15 | Actual block height, unsigned little-endian 32-bit |
| 16 | 1, bytes per scalar |
| 17 | 1, scalars per pixel |
| 18–19 | Reserved zeros |
| 20 onward | Exact row-major grayscale coverage bytes |

Each block hashes its entire header and payload with SHA-256 and uses the shared
`<sha256>.native-tile` namespace. The manifest hashes ASCII `INKSCGR1`, the same
20-byte scalar header with whole-grid dimensions, the tile edge as a four-byte
little-endian integer, and every ordered block hash as 32 raw bytes. Distinct
headers and manifest prefixes prevent image/scalar identity substitution.

Image manifests, native image block bytes and their identities do not change.
Existing Rust image-store type aliases keep their image layout, serialized fields
and schema names. Scalar types use a separate schema namespace. No old document,
session, receipt or history row is rewritten. Old readers must reject the new
scalar format; no automatic conversion or migration of old masks is implied.

## Preparation, reads and publication

Image and scalar candidates share the same storage implementation and capacity
admission. Only the two built-in layouts can supply block framing and validation.
Candidates are immutable; edits retain complete changed blocks and share
unchanged buffers. Older candidates remain usable. Constructors, region reads,
replacement and transfer preparation do not write files. Full `verify` checks
all dependencies; a regional read proves only the blocks it touches. Immutable
candidates validate their manifest on construction, so window reads do not
rehash every unrelated block reference. Each loaded external block still
receives its complete size, header, sample-range and content-hash checks.

`from_rows` keeps one unfinished block band and completed unique blocks in
memory. It is not a disk-backed whole-image mask pipeline. `from_bytes` also
retains the caller's complete input. Integration must separately account for
these allocations; block storage alone is not a memory-budget result.

Explicit `publish` verifies dependencies and uses the existing create-only,
flushed-block publication protocol. Image and scalar blocks share the same
store lock, byte budget and entry budget. Existing files are verified, never
overwritten. Partial failure may leave complete unreferenced cache blocks;
retry verifies and reuses them. Original inputs and old blocks are retained.
See [native sample storage](NATIVE_SAMPLE_STORAGE.md) for filesystem and
interruption guarantees.

Version-1 transfers contain a scalar manifest and sorted, unique pending blocks
as exact lowercase hexadecimal bytes. The caller supplies a decoded-byte
budget; parsing, serialization and total live memory have separate limits.
Malformed framing, duplicate/unreferenced blocks, incorrect identities and
cross-layout substitutions fail before becoming a candidate. External inherited
dependencies still require full verification against an explicit root.

## Acceptance

Fresh full suites passed on the same unchanged 941-file inputs:

| Platform | Fresh stages | Rust tests | Python executed | Explicit skips | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows | 262 | 293 | 2,745 | 13 | 826.563 |
| Linux / WSL | 262 | 259 | 2,707 | 51 | 520.459 |

Every stage ran fresh, with no failures, deferred checks or reused passes.
Seven independent scalar tests cover exact file and manifest framing, shortened
blocks, pure edits/transfers, preserved old candidates through repeated edits,
corrupt/unselected dependencies, cross-layout rejection, shared image/scalar
capacity, concurrent publication and cancellation. An 8192×6144 scalar fixture
checks all 50,331,648 original and edited coverage bytes. Existing image storage,
session, publication and recovery contracts also pass.

Complete command, document and operation schema responses match the previous
engine exactly. The original feature registry is unchanged. Capabilities report
the scalar API as a library primitive at this storage-only milestone, with mask
integration then false. The subsequent [mask increment](NATIVE_MASKS.md) enables
item/filter integration; native selection and whole-image application remain false.

Initial focused acceptance took 174.8 seconds on Windows and 164.6 on Linux.
After eliminating repeated immutable-manifest hashing, Windows's storage-focused
checks took 60.2 seconds; its scalar checks were deferred using the older runtime
estimate, then passed in a separate 50.0-second run. Linux's complete focused
selection took 45.6 seconds. The seven scalar tests themselves took 1.76 seconds
on Windows and 1.64 on Linux after compilation, with the same every-sample oracle.
These are development-feedback observations, not repeated latency or whole-mask
memory measurements. The first compiler failure, its correction and the explicit
deferred report are retained.

Frozen source fingerprint:
`fe546a7550e86a01c727b3706776fa3dbd5666027eef3f8f8334534061d94771`.
Retained `w4-scalar-storage-acceptance-01/audit.json` SHA-256:
`2013a5b6cc8889ad6290de880297cc672f22acfe6c43d89cb9b95a0029fb8483`.
The audit binds source, full and focused reports, exact executables, schema
comparisons and retained failures. Post-acceptance documentation changes are
recorded separately. Native mask workflow, D7 memory and full W4 acceptance
remain open.

## Required integration

The subsequent [item/filter mask increment](NATIVE_MASKS.md) connects descriptors,
resource checks, proposals, saved revisions, backups and publication, retaining
linked/unlinked transforms, clip/outside values, inversion, density, feather and
sampling. Native selection integration remains open. Every selection consumer must resolve
the new representation or refuse it explicitly; no consumer may treat an absent
inline buffer as empty coverage.

Native mask application must process the complete requested image in bounded
storage and preserve its sample precision. Selection-to-mask must create real
scalar manifests. Rendering and export must resolve these masks through bounded
windows. The 50 MP edit/history/export oracle, platform checks and memory
measurement remain required before the W4.6 workflow is accepted. None of these
integration gates is satisfied by the storage primitive alone.
