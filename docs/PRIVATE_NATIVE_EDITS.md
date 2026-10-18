# Private storage for whole-image native edits

Implementation contract for W4.6. The whole-image mask increment passed fresh
full Windows/Linux acceptance and independent 50 MP sample checks. Native
[selection authoring](NATIVE_SELECTIONS.md) has separate full Windows/Linux
acceptance; complete W4/scale-v2 acceptance remains open.

Whole-image edits may prepare immutable native blocks in an owned private file.
Only a bounded tile band and row are resident during construction. Existing
public memory constructors remain file-free. The file is inaccessible through
document JSON: it uses the same delete-on-close/unlinked handle primitive as
native imports and disappears when the last candidate releases it, including
process termination. Failed construction returns no candidate and releases its
reservation. No source file, resource store or session is changed by preparation.

Candidates retain content-addressed manifests and share their private handles
through clones. Window reads verify loaded block bytes. Local replacements keep
unchanged private blocks and add only changed memory blocks; old candidates stay
valid. Whole-image mapping also reuses unchanged published block references and
pending handles; a full-coverage mask adds no blocks. Candidate equality compares validated manifests and pending identities,
independent of whether matching private bytes are in memory or an owned file.
Equality never substitutes for verification of file contents.

Resident pending blocks retain the existing 64 MiB limit. Private native editing
has a separate bound of one 512 MiB payload plus at most 4,096 block headers per
shared operation control, also checked across distinct extents in a document.
Clones sharing one extent count once. A caller retaining independent candidates
or operation controls retains their independent reservations; this is not a
global process or filesystem quota. Transport still counts all logical pending
bytes, so an oversized requested review document fails before allocating hex.
Review without the document may preview the private candidate. Durable commits
publish verified immutable blocks and retain only the manifest, using the
existing create-only protocol, retry receipts and recovery boundaries.

There is no new on-disk block, manifest, document or transfer format. Existing
JSON and saved states do not migrate. Block storage version 2 is required for
whole-image stored edits; callers explicitly migrate legacy version 1 first.
Existing transfer receivers still reconstruct memory candidates within their
unchanged transport and resident budgets.

## Native mask application

`mask_apply` processes every pixel of a version-2 stored image, or an existing
bounded typed inline sample image. It evaluates the mask at the transformed
native pixel center, preserving linked/unlinked positioning, clip/outside,
inversion, density, feather and sampling within their existing work bounds.
The output keeps its dimensions, sample depth, channels, encoding, profile,
sampling and placement. All color-channel bytes remain exact, including hidden
color at zero alpha. Only alpha is multiplied by clamped coverage and quantized
once: nearest integer for unsigned samples, or one binary32 rounding after
binary64 multiplication. Full coverage retains original alpha bits. Existing
inline RGBA8, placed-image and fill application keeps its historical behavior.

The source is fully verified, then read one tile band at a time. Output is
prepared privately before removing the mask. Failures, cancellation and later
batch failures leave the source document and durable history unchanged. Filter,
effect and dissolve ordering restrictions remain. Existing feather/decode work
budgets may reject expensive large-mask controls; source-size admission alone
does not waive processing limits.

## Verified whole-image increment

Five private-storage Rust tests and six application Python tests cover native
layouts, exact color/alpha bits, shortened edges, profiles, signed radiance,
transformed controls, shared ownership, capacity/cleanup failures, corruption,
cancellation, unchanged-block reuse, mixed memory/file edits, transport limits
and proposal/retry/history/backup behavior. Existing scratch process-death checks
also ran in the fresh full suites. One initial fixture omitted the required
linear document color space; the retained failure was corrected without changing
runtime semantics. Initial full runs also caught an outdated scalar-store
capability assertion that still expected native mask application to be refused;
the assertion was corrected and both full suites reran fresh.

| Platform | Fresh stages | Rust tests | Python executed | Explicit skips | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows | 264 | 302 | 2,759 | 13 | 793.453 |
| Linux / WSL | 264 | 268 | 2,721 | 51 | 478.587 |

Every stage ran fresh on matching unchanged 951-file inputs, without pending,
failed or reused checks. Twenty-two complete inline responses and actual saved
state payloads/hashes matched the previous accepted engine. Focused feedback took
107.9 seconds initially, 20.7 seconds for the fixture correction, 110.2 seconds
on Linux, and 48.6 seconds for the larger review/transport checks.
The later capability assertion correction passed the entire Rust suite in
73.9-second Windows and 56.0-second Linux quick runs.

The independent 8192x6144 RGBA16 workflow used 3,072 distinct image blocks and
an authored scalar mask. Every original, masked, subsequently edited and TIFF
output sample matched an independent calculation. The check also covered an
oversized review refusal, review without image bytes, checked commit and retries,
undo/redo, pinned history and unchanged originals. Windows/Linux documents,
change receipts and the complete TIFF identity matched. The unchanged file
publication protocol produced a 402,653,614-byte create-only output.

Windows peak process commit across these calls was 35.219 MiB, below the 512 MiB
target. This is an OS lifetime high-water mark for each owned engine process,
not a sampled heap or a measure of the Python oracle. Unix memory remains
explicitly unavailable. Each operation ran once alongside full verification;
these are fidelity and memory diagnostics, not repeated latency acceptance.

Frozen source fingerprint:
`5b5fdf5c623bacf20c353bca90583cd41aed172f7d4fe8410d4cba36aafa7504`.
Retained `w4-native-mask-bake-acceptance-01/audit.json` SHA-256:
`711689955e04c2e20c5f802d5a872ede3ad34fe341b6f0048413264c1e6abc69`.
The audit binds source, debug/optimized identities, all full/focused logs,
fixtures, requests, outputs and oracle scripts. Documentation following acceptance
is bound separately. The optimized target runs precede only the recorded
`cfg(test)` assertion correction; every production source is identical.
Native selections have subsequent [bounded acceptance](NATIVE_SELECTIONS.md).
Selected patch repair preparation, other W4 operations, larger layered files,
repeated scale-v2 gates and verified Unix memory remain open. No new
engine checkpoint, release or whole-goal completion is claimed.
