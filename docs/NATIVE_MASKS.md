# Native scalar masks

Item and filter masks now accept the [scalar store](NATIVE_SCALAR_STORAGE.md),
with fresh full Windows/Linux acceptance for the contract below.
Native selection authoring remains open. Whole-image application to typed inline
and version-2 stored sample layers is implemented under the separate
[private edit contract](PRIVATE_NATIVE_EDITS.md), with fresh full Windows/Linux
acceptance and complete 50 MP mask/edit/history/TIFF sample checks. Native
selections and the complete W4 workflow remain open.

## Representation and migration

Existing inline mask and selection descriptors keep their serialized fields,
including `gray_hex`. Item/filter masks have a new optional `native` field carrying
a scalar manifest and, during private review, validated pending blocks. Omitted `native` stays
omitted on serialization, preserving existing document and history identities.
The scalar manifest supplies the version; its dimensions must match the plane.
A native mask has empty `gray_hex` and exactly one scalar source. Constant
masks cannot also carry native blocks. No document, saved revision or resource
is silently migrated or rewritten.

The current entry point is the existing `mask` edit operation (or a filter's
`mask` field), with `native.base` holding a scalar manifest. The optional
`native.staged` carries a validated scalar transfer for pure library edits and
private review. The Rust `stored_scalars::Grid::from_candidate` constructor
retains shared buffers. Native selection descriptors are not admitted yet;
existing selection operations keep their representation and limits.
Rust callers constructing `Mask` literals supply `native: None` for inline data.

Native mask bytes are unsigned grayscale coverage, with no color profile or
alpha channel. Existing transform, linked/unlinked positioning, outside/clip,
invert, density, feather and nearest/bilinear sampling semantics are retained.
Planned native selections use document pixel coordinates. No absent inline data
may be interpreted as empty coverage by an old consumer.

## Windowed evaluation

Native masks verify the complete source before sampling. Raw bytes retain at
most four source tile rows; feathered results retain two processed tile rows.
Both caches use 128-pixel edges and retain shortened edge dimensions. Feather
windows evaluate the same horizontal-then-vertical triangular sums as inline
masks, including outside values and density after filtering. Bilinear sampling
uses the same four processed samples. Native item and filter masks share one cumulative
feather-work budget per prepared document; filter caches survive tiled rendering
and codec replays. Native ink rendering uses the same prepared masks.

Aggregate native mask sources are bounded at 67,108,864 pixels, independently of
the inline mask budget. Cache and scratch estimates participate in renderer and
native-ink memory admission. Source preparation reserves three work units per
pixel; cache misses retain the existing two-decoding-pass limit. Windowed
feathering has a separate 67,108,864-operation budget. Existing paint, rendering,
file-output and pending-block limits also apply. A large scalar descriptor does
not guarantee that a complete masked composition fits those separate budgets.

## Resources and history

Native coverage uses the document's explicit asset resource root, including
saved session bindings. Admission validates the manifest and pending transfer;
preparation verifies every referenced block, even outside a later sampled
window. A bounded cache retains exact scalar bytes. Cache misses verify the
loaded block and count cumulative decoding work. Invalid or changing sources
fail; zero coverage is never substituted for an I/O or integrity error.

Pure edits retain unpublished candidates. Durable CLI/MCP edits and session
commits publish complete immutable scalar blocks before storing a manifest-only
state. Private candidates participate in proposal previews, aggregate pending
budgets and review-transport bounds. Durable projection, resource checks,
undo/redo, backups, restoration and verified transfers must include scalar
dependencies. Original blocks and source images remain unchanged.

Retained objects admit published mask manifests and verify them recursively.
Their embedded snapshots reject pending scalar transfers: commit those blocks
before retaining the object. Backups retain history and explicit resource
bindings; their existing contract does not copy external resources.

## Required behavior and acceptance

Selection creation, combination and selection-to-mask must support full native
grids using bounded processing. Native masks must render through bounded windows
and retain all existing controls. Permanent application must process the whole
requested typed image while retaining its depth; a small-region-only bake does
not satisfy the 50 MP workflow. Large output candidates need bounded private
preparation before publication, rather than a complete in-memory RGBA16 frame.
Private preparation must have explicit ownership, cleanup and byte admission.

Consumers not yet integrated must reject native coverage explicitly, including
unsupported structural exporters. They must not produce an empty mask or ignore
the selection. These refusals must be listed separately from supported native
operations and do not close the remaining work.

Structural SVG and layered mask export currently reject native scalar masks.
Permanent application supports the existing bounded inline raster, image and
fill targets, plus typed inline samples and version-2 stored images. The native
path retains every color-channel byte and multiplies alpha at transformed native
pixel centers; it prepares changed blocks in bounded private storage. Legacy
stored layers require explicit migration. See the separate application contract
for precision, ownership, unchanged-block reuse and verified acceptance.

Acceptance requires independent small dense oracles for all mask controls and
sample depths, full-grid selection/mask checks, corruption and cancellation
failures, proposal/retry/history/resource-binding checks, and full fresh Windows
and Linux suites. The 50 MP RGBA16 mask/edit/history/TIFF workflow additionally
needs an every-sample oracle and the D7 process-memory measurement. Existing
inline response identities and the original feature criteria remain unchanged.

## Verified item/filter mask increment

Fresh full suites passed on matching unchanged 946-file inputs:

| Platform | Fresh stages | Rust tests | Python executed | Explicit skips | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows | 263 | 297 | 2,753 | 13 | 781.750 |
| Linux / WSL | 263 | 263 | 2,715 | 51 | 501.898 |

There were no failed, pending or reused stages. Four Rust tests and eight Python
tests cover independent coverage calculations, all six native sample layouts,
shortened tiles, linked/unlinked transforms, sampling, feathering, tiled/print
output, cancellation, corrupt dependencies, private proposals and durable
publication/retry/history/recovery. Twenty-two complete responses and saved-state
payloads/hashes match the previous engine for existing inline workflows.

An independent 8192x6144 scalar source (50,331,648 pixels) passed four bounded
preview cases on each platform. All 2,312 sampled output pixels matched the
independent coverage oracle; Windows/Linux RGBA output matched. This periodic
fixture uses 3,072 references to two unique blocks. It establishes large-source
admission and window semantics, not whole-image application or process memory.

The first Windows full run exposed unnecessary hierarchy work for unmasked
objects. After correction, the unchanged 5,000-object test passed within its
existing deadline. Two repeated exports fell from 25.4-25.6 seconds to 1.4-1.8
seconds with identical responses. Corrected focused checks took 94.3 seconds on
Windows and 48.7 seconds on Linux. Initial compiler/fixture failures, the full
timeout, focused corrections and both full runs are retained; these timings are
observations, not repeated scale gates.

Frozen source fingerprint:
`0fbc0ac9e188e4f68e21bd1fe9622daac3e1645a4a703f5e828aa2acf4b16f5e`.
Retained `w4-native-mask-integration-acceptance-01/audit.json` SHA-256:
`62d14656c3ce51cdfb5422cb41bb44f4e49e728b94d4c3d42a7b88c86bd3512f`.
The audit binds sources, executables, reports, independent checks and failures;
post-acceptance documentation changes are bound separately. At this increment,
whole-image application and memory were still open. The subsequent
[application acceptance](PRIVATE_NATIVE_EDITS.md#verified-whole-image-increment)
records full-image and Windows memory evidence; native selections and complete
W4 acceptance remain open.
No engine checkpoint, new release or complete W4 acceptance is claimed.
