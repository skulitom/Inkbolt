# Native JPEG import contract

This is the W4.3 implementation contract under [FIX_PLAN.md](../FIX_PLAN.md).
Fresh full Windows/Linux acceptance passed within the existing input and canvas
limits. A corruption probe found that the locked decoder accepts premature
entropy termination; original strict Huffman admission rejects those inputs
before decoding or publication. See the retained
[acceptance and memory evidence](DEVELOPMENT_STATUS.md#w43-native-jpeg-import-scale-admission-open).
The complete scale gates remain open. Subsequent [scale admission](SCALE_ADMISSION.md)
has separate full Windows/Linux acceptance and independent 24 MP decode checks.

## Request and preserved behavior

Admit 8-bit grayscale/RGB baseline and progressive JPEG through `sample.import`,
using the existing optional native store and private source/pixel staging.
The caller must supply `orientation:"apply"` or `orientation:"ignore"` for JPEG;
neither policy is implicit. Existing PNG/TIFF calls, their Rust entry points,
receipt wording, default fields and historical request identities must remain
unchanged. An orientation option on another format must fail explicitly.

Preserve the encoded input exactly. Decode, framing, metadata, source byte count
and source SHA-256 must refer to the same captured bytes. Imports never modify
the source. The native result uses unsigned 8-bit samples with opaque alpha;
grayscale remains native gray/alpha. Explicit document resolution still governs
physical size; source density does not resize the result.

Retain the existing explicit sRGB interpretation contract. Recognized sRGB
declarations may establish declared sRGB; otherwise untagged samples require
`assume_srgb`. Reject unsupported embedded profiles, color transforms, component
depths, coding modes and multi-image semantics before publication. JPEG cannot
be treated as linear binary32 radiance. No implicit profile conversion is added.

## Orientation and metadata

Read primary-image EXIF orientation from bounded classic-TIFF metadata. Validate
byte order, types, counts, offsets, duplicate relevant tags and referenced
directory structure. Never apply thumbnail orientation to the primary image.
Malformed or conflicting orientation must fail even under `ignore`.

`apply` maps all eight defined orientations into the actual output samples,
swapping width/height where required. Missing orientation means the standard
top-left order, after the caller has chosen a policy. `ignore` retains coded
sample order. Receipts distinguish absent/present source orientation, the chosen
policy, effective mapping and output dimensions. The stored document does not
retain a second orientation instruction that could rotate the pixels again.

Recover the existing bounded Inkbolt JPEG metadata envelope from its supported
pre-scan comment carrier. Preserve its untrusted status and explicit failure for
invalid/duplicate/missing parts. General EXIF/XMP/IPTC editing is not introduced;
any accepted descriptive metadata that is not retained must be declared as a
loss. Recognized color or geometric semantics cannot silently disappear.

## Decoder and publication budgets

The locked `jpeg-decoder` 0.3.2 API returns a complete decoded buffer. Its output
limit is not an early bound on progressive coefficient/plane allocations.
Before calling decode, inspect the complete captured framing and derive checked
memory/work admission from dimensions, component sampling and coding/scans.
Charge decoded output, padded component planes, progressive coefficients and
temporary codec rows separately from private pixel storage. The output budget is
192 MiB; the conservative working estimate is bounded at 384 MiB, including 4 MiB
of auxiliary allowance. Scan count is capped at 128 and cumulative padded-sample
work at 2,147,483,648. EXIF is bounded to eight directories and 1,024 entries.
Do not allocate from unvalidated fields.

After framing/memory admission, validate Huffman codes, exact component block
counts, scan progression, coefficient runs/refinements, byte stuffing, all-one
padding and restart intervals. Progressive validation retains one occupancy bit
per padded coefficient; it does not reconstruct coefficient values or pixels.
This state is released before the actual codec runs. Premature markers, excess
entropy and EOB runs crossing scan/restart boundaries fail. Cancellation is
checked during reads and between data units, including runs consuming no bits.
One correctly numbered terminal restart at an exact interval boundary is admitted.

The adapter may retain one bounded decoded JPEG frame, then normalize/orient one
native output row at a time into private storage. Drop the decoder and its
retained coefficients before native normalization where possible. Do not retain
an additional complete normalized RGBA frame for native publication. Inline
output retains its existing small-image cap. Check cancellation during framing,
codec reads, normalization and publication; a codec computation remains bounded
and synchronous. Resource admission is not a whole-process memory guarantee.

Validate complete marker/entropy framing, later progressive scans, final EOI,
trailing data, metadata, sample count and the document before any persistent
block is published. Preserve the existing immutable block, retry, source,
no-overwrite and failed-publication recovery contracts.

## Acceptance

Use original synthetic baseline/progressive fixtures, grayscale and RGB,
subsampling, odd dimensions, both EXIF byte orders, all eight orientations and
absent orientation. Independently check decoded samples and orientation maps;
compare native blocks with admitted inline results and an independent decoder
where lossy reconstruction requires a tolerance. Verify unsupported/malformed
late data, large declared dimensions, codec/scan budgets, cancellation, duplicate
metadata, no publication on preparation failure, MCP parity and history/retry
compatibility for existing formats. Measure whole-frame and progressive memory
on content-bound builds, then run fresh Windows/Linux acceptance. The 24 MP JPEG
and complete `scale-v2` gates remain required after coordinated scale admission.

References: [locked decoder API](https://docs.rs/jpeg-decoder/0.3.2/jpeg_decoder/struct.Decoder.html),
[JPEG marker specification](https://www.w3.org/Graphics/JPEG/itu-t81.pdf), and
[public EXIF orientation/tag definitions](https://home.jeita.or.jp/tsc/std-pdf/CP-3451D.pdf).
