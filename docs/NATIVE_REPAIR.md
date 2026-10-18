# Repair on stored and high-precision images

The `repair` operation accepts `raster`, `samples` and `stored_samples` targets,
donors and guides. Patch placement, exemplar fill, content-sensitive move and
guided edge correction share the algorithms and quality conditions in
[the repair contract](REPAIR.md). This extends the input representations;
it does not infer missing content or use a learned model.

This repair contract has fresh full Windows/Linux acceptance and independent
50 MP checks for all four actions, TIFF delivery, retries and history. The
original feature registry is unchanged. Mask and selection contracts have their
own acceptance; the complete W4 workflow and repeated scale gates remain open.
The evidence and remaining work are recorded below.

## Inputs and precision

Targets and sources may use RGBA or gray/alpha channels at unsigned 8-bit,
unsigned 16-bit or float32 depth. Encoded sRGB is required. Linear or profiled
sources fail with `UNSUPPORTED_REPAIR_ENCODING`; callers must convert explicitly.
A chromatic result cannot silently become gray: it fails with
`GRAYSCALE_CONVERSION_REQUIRED`. Source and target depths may differ.

Comparisons, synthesis and blending retain premultiplied float64 values until
the final encoding at the target depth. Guided-change and boundary quality
gates measure that final encoded result. Unchanged samples, including hidden
RGB and float bit patterns, stay byte-identical. Sources are frozen before the
operation, including self-source moves with overlapping destinations.

An entirely inline RGBA8 request retains its existing algorithm, work counts,
pixel identities and receipt representation. A request involving typed samples
uses `inkbolt-native-region-repair-v1`, reports each identity kind and retains
the target specification. Native identities bind the typed tile manifest;
ordinary raster identities retain their established RGBA8 image hash.

## Bounded views and donor search

The selected rectangle is limited to the existing 65,536-pixel local edit bound.
Processing retains selected pixels and the actual in-image neighborhood required
by the action. A move retains a separate destination neighborhood, so a distant
destination does not allocate the intervening image. All receipts use global
native-grid coordinates, including source decisions and changed bounds.

For fill and move, supply a `donor_region` on large sources:

```json
{
  "op": "repair",
  "id": "pixels",
  "options": {
    "region": {"x": 4095, "y": 3071, "width": 2, "height": 2},
    "action": {
      "type": "fill",
      "fill": {
        "source_id": "pixels",
        "donor_region": {"x": 4050, "y": 3040, "width": 24, "height": 24},
        "patch_radius": 1,
        "max_context_rms": 0.1
      }
    }
  }
}
```

Search remains exhaustive within the admitted donor region. Omitting that region
requests the complete source; a source that exceeds processing bounds is refused
with guidance to provide a smaller explicit region. The engine never silently
narrows the donor search, changes patch size or reduces source precision.
Self-source donors exclude the entire positive selected domain. Original
row-major priorities and tie-breaking rules remain unchanged.

The 128 MiB processing admission accounts for simultaneous local fields,
prepared resources, caches and complete replacement blocks. It is a component
bound, not a measured whole-process guarantee. Local work retains its
67,108,864-unit ceiling. Full dependency verification has a separate cumulative
536,870,912-unit allowance, shared with delegated patch/healing preparation and
result verification. Every required source block is verified even if it is far
outside the sampled windows. Receipts report local work, preparation work, their
sum, and target/source window cell counts. Existing request, snapshot, native
pending-block and legacy patch-history bounds remain applicable.

### Shared patch preparation

The current implementation passes operation-local verified image and selection
readers from patch search into blending. The result reader comes from the
constructed replacement candidate, so final quality checks do not prepare the
complete output image again. Every input dependency is still verified initially;
external block cache misses retain their hash checks. Readers are never reused
across requests or revisions.

Delegated blending inherits the local work already consumed by search, and its
memory admission includes the retained repair fields. Preparation receipts count
each prepared input once. Ordinary inline repair and standalone retouch retain
their existing response contracts. Limits and native sample precision are
unchanged. Fresh full Windows/Linux and 50 MP selected patch acceptance passed
as recorded below.

## Publication and history

Changed cells are grouped into bounded block-local replacements against one
prepared source. Version 2 retains complete changed blocks and reuses unchanged
ones. Version 1 retains its bounded patch representation; it is not silently
migrated. Pure edits and dry runs carry validated private candidates. Successful
CLI/MCP edits publish complete blocks through the existing create-only protocol.
Durable history and proposals bind the published projection, while previews can
resolve private candidate buffers.

Quality rejection, invalid input, resource exhaustion, cancellation or a later
failed operation discards the edit batch. No partial repair becomes a session
revision. Retry, undo/redo and historical source access use the existing session
contracts. This does not add a persistent synthesis graph.

## Selected patch acceptance

Focused feedback passed in 76.4 seconds on Windows and 62.2 seconds on Linux.
Fresh full suites then passed on matching unchanged 958-file inputs:

| Platform | Fresh stages | Rust tests | Python executed | Explicit skips | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows | 265 | 306 | 2,768 | 13 | 865.000 |
| Linux / WSL | 265 | 272 | 2,730 | 51 | 570.046 |

All 265 stages ran fresh on each platform, without failed, pending or reused
results. Tests cover six sample formats, inline and both stored representations,
soft selected clone/heal against independent references, quality rejection,
off-window corruption, private review, retry/history and inherited work, memory
and cancellation. Ninety-six complete responses from the previous engine match,
including inline saved-state payloads and hashes.

An independent 8192x6144 RGBA16 workflow checked every selection byte and image
sample through shape/feather, mask application, selected brush, self-source patch,
separate-donor patch, TIFF output and five undo/redo steps. The separate donor is
a 512x512 image; the 50 MP target and document aggregate limits are unchanged.
Preparation uses 301,989,888 units for the selected self-source patch and
302,776,320 for the separate donor, below the existing 536,870,912 ceiling.
Delegated blending adds no repeated full-source preparation. Local edit bounds
remain unchanged; this is not a whole-image patch-size claim.

All 25 requests and eight independent complete sample/plane checks passed on each
platform, including the expected oversized-review refusal. Documents, change
receipts, selection hashes and TIFF hashes match across platforms. Original
source blocks and the donor are unchanged. Windows peak process commit was
**36.719 MiB**; Unix memory remains unavailable. These are one-run fidelity and
admission checks alongside the full suites, not repeated scale-v2 latency gates.

The initial target fixture placed two 50 MP images in one document and correctly
hit its aggregate pixel limit. Both failed attempts are retained; the corrected
fixture uses the smaller donor without changing any engine limit. The initial
focused Clippy failure and correction are also retained.

Frozen source fingerprint:
`e2106b0d79d7c081d9ceccf16fea8bd7a15fba42a0953ded4916935a1db1ab15`.
Retained `w4-shared-patch-acceptance-01/audit.json` SHA-256:
`66f128f73126f9f7878df86b243ac6842a775c2c0187099b4613d162bbbb52c2`.
The audit binds sources, full/focused logs, failures, executables, requests,
responses, complete independent oracles and target artifact inventories.
Post-acceptance documentation changes are recorded separately. Native
segmentation, remaining W4 operations, larger layered files, repeated scale-v2
and verified Unix memory remain open. No new checkpoint or release is claimed.

## Initial native repair acceptance

Focused feedback passed in 63.3 seconds on Windows and 83.8 seconds on Linux.
Fresh full suites then passed on matching unchanged inputs:

| Platform | Fresh stages | Rust tests | Python executed | Explicit skips | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows | 262 | 286 | 2,745 | 13 | 939.453 |
| Linux / WSL | 262 | 252 | 2,707 | 51 | 589.039 |

No full-suite stage failed, remained pending or reused a result. The checks
include all six native sample formats and three representations, exhaustive
donor replay, independent dense healing and guided quantiles, soft coverage and
alpha, disconnected move windows, unchanged hidden float bits, explicit color
refusals, out-of-window corruption, quality/cancellation/lock failures, pure
proposals, retry and undo/redo. Fifty-four complete responses from the previous
executable matched exactly, including inline work counts and document identities.
The first focused run's incorrect corruption/proposal expectations and missing
limit bindings were corrected; that failed report is retained.

Original 8192×6144 true-RGBA16 inputs (50,331,648 pixels) passed independent
checks for fill, distant move, guided correction and searched patch placement on
Windows and Linux. Every stored sample, exported TIFF sample, restored state and
pinned original was checked. Quality rejection left resources and history
unchanged. Windows and Linux produced identical documents, repair receipts and
TIFF hashes. The largest measured Windows process commit was **35.828 MiB**,
below the 512 MiB target. Unix memory remains explicitly unavailable.

These were one-run diagnostics while full suites were active, not repeated
latency acceptance or general photographic reconstruction evidence. The later
[mask](NATIVE_MASKS.md) and [selection](NATIVE_SELECTIONS.md) contracts record their
separate acceptance. The shared-preparation follow-up above resolves the later
50 MP selected patch refusal. The [native region selection follow-up](NATIVE_SEGMENTATION.md) has separate
acceptance. Proxy/refine selection, larger brush/retouch regions,
larger layered files, repeated scale-v2 and verified Unix memory remain open. Full W4
and the overall agent-readiness goal are not complete. The registry stays 163/167;
v0.82.0 is unchanged.

Frozen full-suite source fingerprint:
`cf957a7b033bd9bd5227a3744af1b7d4f5ec496b6acf811a445a02f45f517a66`.
Retained `w4-native-repair-acceptance-01/audit.json` SHA-256:
`f66eadebe2f33cee488f733711bd1e2f667941d0ff10d64057e3ba7a1a1a0238`.
The audit binds source, complete/focused logs, failures, exact executables,
requests, responses, independent oracles and target artifact inventories.
Post-acceptance documentation updates are recorded separately.
