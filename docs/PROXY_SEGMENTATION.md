# Proxy selection with native boundary refinement

This W4.6 extension has fresh full Windows/Linux acceptance and independent
50 MP and maximum-size mask/history/export evidence within the contract below.
The existing [native-region contract](NATIVE_SEGMENTATION.md) remains unchanged.

## Explicit mode and approximation

`options.proxy` opts into two stages and declares integer `step` and
`refine_radius`. `options.region` retains cropped-native coordinates; omission
selects the complete source. Seeds stay in those coordinates. Original source
samples are not converted. The response identifies `proxy_then_refine` explicitly.

For a saved 8192 x 6144 image, this requests a 256 x 192 proxy and a native
boundary band with radius 16. Choose seeds on opposite sides of the intended
boundary; all coordinates use the source image's cropped native grid:

```json
{
  "command": "assist.segment",
  "document": {"session_id": "selection", "revision": 0},
  "id": "pixels",
  "options": {
    "foreground": [[0, 0]],
    "background": [[8191, 6143]],
    "proxy": {"step": 32, "refine_radius": 16, "include_preview": true}
  }
}
```

Use the same options with `assist_mask` to attach the full-resolution mask.
Rust callers can construct `assistance::segment::ProxyOptions` directly and
pass it through `assistance::segment::Options::proxy`. The public alias retains
the existing JSON and schema representation. An external integration test checks
typed construction, inspection, the independently expected mask digest and
source preservation; targeted Windows/Linux verification passed in 90.5/45.9
seconds after exposing this type.

The step is explicitly chosen in `1..1024`, and the radius in `1..64`.
These parameter ranges do not guarantee admission: a complicated boundary can
exceed the node or work budget. Preview and full cost detail are opt-in. Edit
receipts always omit those payloads and identify their omission with
`preview_included:false` and `cost_arrays_included:false`.

The region is partitioned into `step`-wide/tall cells, with short last cells.
Each cell samples its lower center native pixel at the source's declared analysis
precision. Seed color prototypes come from the original native seed pixels.
Coarse unary costs multiply color distance by cell area; neighbor costs multiply
the existing integer edge cost by their shared native boundary length. Seeds pin
their containing cells. Opposite-class seeds in one cell fail explicitly; there
is no silent seed relocation or fallback.

The coarse labels are projected to native cells. Refinement includes pixels
within `refine_radius - 1` Chebyshev steps of either endpoint of an internal
four-neighbor coarse-label transition. Thus a straight boundary has a band
`2 * refine_radius` pixels wide. The region's outer edge is excluded from the
objective, as in ordinary native-region selection. All labels outside the band
stay fixed. Native color costs, edges within the band and edges to fixed neighbors
form a second exact integer cut. Original seeds remain hard constraints.

The second certificate is for this conditional native objective. It excludes
the unchanged outside-only constant and does not claim a global native optimum.
Its final energy cannot exceed the projected coarse labels' energy in that same
conditional objective. Ties retain the smallest foreground set within the band.
Coarse sampling can miss small features outside the band; the response declares
this loss and its sampling displacement. Float analysis keeps its separately
declared feature quantization. No semantic recognition or alpha matting is added.

## Storage, inspection and limits

The complete region mask uses native scalar blocks and owned temporary storage;
it is zero outside the region and retains the source's crop/display placement.
Read-only inspection returns source identities, mask measurements/hash, both
certificates and optional bounded preview/cost detail. It does not publish blocks
or return an unusable reference to private temporary data. `assist_mask` attaches
the full mask through existing atomic edit/publication and history machinery;
its change receipt stays compact. Preview sampling and its native mapping are
reported. Optional PNG previews use the existing single-copy MCP transport.

Energy and capacity values in this new mode use decimal strings so that large
weighted integer certificates survive clients that parse JSON numbers as doubles.
Coordinate indices, pixel counts and work counters remain bounded ordinary integers.

The existing 65,536-node coarse graph and local-work ceiling remain. The new mode
admits at most 262,144 native refinement nodes under an explicit 256 MiB processing
budget; optional cost details must fit that budget too. It does not raise the
ordinary native-region graph/memory limits. Native decoding and output staging
share the existing preparation ceiling; each loaded block remains verified.
Tile-ordered sampling prevents repeatedly decoding full image bands for a few
coarse pixels. Oversized bands, seed collisions, work exhaustion, memory refusal,
unsupported encodings and cancellation return errors without an approximate
success or partial edit.

Focused checks currently pass on Windows and Linux. They include exhaustive
small objectives across six sample formats and three storage representations,
the maximum native boundary, actual work/memory/node refusals, transformed crops,
single-copy MCP preview, private session review, retries and history. Independent
50 MP target runs on both platforms check every native mask, original/edited
sample and TIFF sample, with a row-dependent boundary that refinement corrects.
Fresh full-suite acceptance and exact-source target checks are recorded below.
Existing legacy/native selection behavior remains separately accepted.

## Required acceptance

- Independent coarse-cell/area/boundary arithmetic and exhaustive native-band
  objectives, including short cells, diagonal corners, disconnected bands,
  outside fixed labels, hard seeds and ties.
- Step-one agreement with native selection; all six sample formats and storage
  representations; float precision, crop/transform mapping and source preservation.
- Explicit refusal and cleanup for collisions, oversized bands, work, memory,
  corruption outside sampled regions and cancellation.
- Full-size mask pixels, native block identities, inspect/edit/preview consistency,
  compact receipts, CLI/MCP parity, private review, retry, undo/redo and publication.
- Unchanged successful existing responses and saved-state identities; targeted
  feedback within the normal budget and fresh Windows/Linux complete suites.
- An independent large-image workflow at native resolution, including retained
  precision, full-mask/export/history checks and measured Windows process memory.
  Unix memory and repeated scale-v2 gates remain separate requirements.

## Verified acceptance

| Platform | Fresh stages | Rust tests | Python executed | Explicit skips | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows | 267 | 307 | 2,783 | 13 | 996.797 |
| Linux / WSL | 267 | 273 | 2,745 | 51 | 645.059 |

All stages ran fresh on matching unchanged inputs. Eight proxy/refine integration
tests check exhaustive weighted coarse and conditional native objectives, hard
seeds, ties, short cells, six sample formats and three storage forms; step-one
agreement with native selection; actual budget refusals; transformed crops;
single-copy previews; source preservation and atomic session/history behavior.
The boundary union also matches independent native transition dilation for every
labeling of several small grids. A deliberate unsampled island demonstrates the
declared outside-band loss. All 192 complete successful legacy/native inspection
and edit responses match the preceding accepted executable.

Independent Windows/Linux workflows checked every original, mask, edited and
TIFF sample at both 8192 x 6144 and 8192 x 8192. The smaller case refines 196,608
native pixels; the maximum case reaches both the 65,536 coarse-node and 262,144
native-node limits. A row-dependent boundary is offset from the sampled grid;
refinement lowers the independently calculated conditional energy and restores
the complete expected native mask. Coarse/native costs, hard bounds, previews,
block identities, compact receipts, private review, retries and undo/redo pass.
Complete MCP inspections equal CLI results on both platforms, with one preview
payload. Source documents, change details, mask hashes and TIFF hashes match
across platforms for the 50 MP workflow; both maximum-size mask/TIFF hashes match.

Windows peak process commit was 89.371 MiB at 50 MP and 108.473 MiB at the
maximum size, below the unchanged 512 MiB workflow target. Unix process memory
remains unavailable. These are independent one-run fidelity/admission checks;
they do not close the repeated scale-v2 latency gates or complete W4.

Final focused feedback passed in 108.3 seconds on Windows and 78.1 seconds on
Linux. The initial missing capability-limit bindings and their failed check are
retained; pending or failed checks receive no acceptance credit.

Frozen source fingerprint:
`316e78125eb046b4ac7883760f8fdc9e59006b14f24c4be49c294a90c58a3136`.
Retained `w4-proxy-segment-acceptance-01/audit.json` SHA-256:
`160071d97751bf9e98a9fbfc2256979c7b51fd8276f1249875c9ae8ab367afc9`.
The audit binds full/focused logs, original sources, executables, independent
oracles, complete response comparisons and both target-size workflows. Later
documentation changes are recorded separately. Remaining operation regions,
larger layered files, repeated scale-v2, Unix memory and the original four
checkpoints stay open; the registry remains 163/167.
