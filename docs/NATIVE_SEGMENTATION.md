# Native region selection

This contract extends `assist.segment` and `assist_mask` to an explicit native
region of an image, including stored RGBA/gray-alpha samples. Fresh full
Windows/Linux acceptance and an independent 50 MP workflow passed within this
contract. It advances W4.6; proxy-then-refine selection, larger graphs and full W4
remain open.

## Region and coordinates

`options.region` contains integer `x`, `y`, `width` and `height` in the item's
cropped native grid. It must be nonempty, contained in that grid and contain at
most 65,536 pixels. Omitting it requests the complete grid under the same graph
bound. Seeds retain their original cropped-native coordinates and must lie inside
the region; they are not interpreted relative to its upper-left corner.

The returned mask is region-sized, zero outside its rectangle, and translated
into the item's local coordinates. Placed images also retain their crop/display
scale. Masks, effects and item opacity are not baked into analysis. Attaching the
mask with `assist_mask` preserves every source byte and uses the existing lock, replacement,
proposal, retry and history rules. No source or storage format is migrated.

For an existing session whose image contains this native region, run with its
workspace selected. Both seeds use the item's cropped native coordinates:

```json
{
  "command": "assist.segment",
  "document": {"session_id": "selection", "revision": 0},
  "id": "pixels",
  "options": {
    "region": {"x": 4095, "y": 3071, "width": 256, "height": 256},
    "foreground": [[4095, 3071]],
    "background": [[4350, 3326]],
    "smoothness": 0
  }
}
```

Zero smoothness classifies each pixel by its seed-color distance. A nonzero
value adds the declared neighbor cost. Apply the same options with `assist_mask`
to retain an editable region mask; inspect it before applying it to source pixels.

## Defined analysis precision

Eight-bit sources keep the existing rounded premultiplied byte features and
integer objective. Sixteen-bit sources use rounded premultiplied 16-bit features:
`round(component * alpha / 65535)`, plus the original alpha. Grayscale repeats its
color feature in the three RGB positions. Hidden color at zero alpha has no effect.

Normalized encoded-sRGB float32 sources use exact binary-rational premultiplication
followed by rounding to 16-bit analysis features. This is declared analysis quantization, with
at most half a 16-bit feature step of rounding error; original float samples stay
unchanged. Visible out-of-range values, linear/profiled encodings and retained
pixel deformations fail explicitly. There is no implicit color conversion.

For 16-bit features, `smoothness` and `edge_scale` are multiplied by `257²` before
the existing exact integer energy is constructed. Unary costs use native feature
differences. Neighbor costs use integer arithmetic with a wide intermediate;
minimum energy, maximum flow and hard seeds must still agree. Ties retain the
smallest foreground set. The certificate concerns this declared objective,
not semantic recognition or fractional alpha matting.

New native/region responses identify the region, feature depth, source format and
identity, quantization, local work and complete-source preparation work. Optional
cost indices are row-major within the region. Existing successful eight-bit
requests without a region retain their complete response contract.

## Bounds and verification

Native readers verify all source dependencies, including blocks outside the
region, under the existing 536,870,912-unit preparation budget. Local reads,
feature construction and graph work share the existing 67,108,864-unit ceiling.
Processing admits a conservative 128 MiB bound for prepared inputs, graph fields
and response construction. The graph bound does not imply a whole-image graph
or remove document, source-storage, mask or publication limits.

Acceptance covers independent exhaustive label/energy checks at both integer
precisions, rational float-feature references, six sample formats and both stored
representations, global seed and mask placement, unchanged original samples,
corruption outside the region, cancellation, memory/work refusals, exact legacy
responses, CLI/MCP proposal/retry/history and fresh full Windows/Linux suites.
The independent 50 MP workflow verifies native region selection, mask application,
history and delivered samples. Its measured scope is recorded below.

Native `assist_mask` changes use `native_selection_summary_v1`: energy and source
identity, analysis metadata and a `mask_summary` containing placement and the
SHA-256 of the region's row-major mask bytes. The full mask remains in the
document. Edit receipts omit mask bytes and per-pixel cost arrays even when
`include_costs` is requested; `cost_arrays_included:false` makes this explicit.
Use `assist.segment` to inspect the full mask and optional costs. This keeps the
maximum region reviewable within the existing session receipt limit without
changing historical eight-bit receipts.

## Verified acceptance

| Platform | Fresh stages | Rust tests | Python executed | Explicit skips | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows | 266 | 306 | 2,775 | 13 | 828.344 |
| Linux / WSL | 266 | 272 | 2,737 | 51 | 509.250 |

All stages ran fresh on matching unchanged inputs, without failed, pending or
reused checks. Seven native-region tests cover six sample formats and inline,
legacy stored and block-stored representations; exhaustive cut/energy and exact
rational float references; crop/transform placement; corrupted dependencies;
refusal, cancellation, source preservation and CLI/MCP history. Maximum-region
session tests also request complete costs while requiring a receipt below 8 KiB.
Ninety-six complete successful eight-bit responses match the previous executable.

The independent 8192x6144 RGBA16 workflow checks every source, edited and TIFF
sample. Its 256x256 region crosses block boundaries and reaches the unchanged
65,536-pixel graph limit. At zero smoothness, every unary/pair cost and mask cell
matches an independent native-integer calculation. Review, commit, identical
retry, mask application, saved originals and all undo/redo states pass on both
platforms. Documents, change receipts, selection masks and TIFF hashes match.
The complete maximum-region MCP response also matches its CLI counterpart on
both platforms.
The saved selection receipt is approximately 2.5 KiB. Windows peak process commit
was 60.730 MiB; Unix memory remains unavailable. These are one-run fidelity
and admission checks, not repeated scale-v2 latency acceptance.

The first target attempt found that full mask bytes duplicated in change details
exceeded the existing session receipt limit. The native summary above fixes that
failure without raising the limit; full inspection and document mask bytes remain
available. Failed focused checks, the target refusal and both deliberately
interrupted initial full runs are retained. Final focused feedback passed in
89.1 seconds on Windows and 56.0 seconds on Linux. Fresh complete acceptance then
ran against the corrected sources.

Frozen source fingerprint:
`f58f53ad7736e69893573a0c00c57a4b36c62c6301290cfb368cd3c5f2cf07e6`.
Retained `w4-native-segment-acceptance-02/audit.json` SHA-256:
`36db7283c7621cd1fa4c4624b6910ca9c3fa07d77402ba7af056563b33762f5e`.
The audit binds the source archive, executables, complete/focused logs, failures,
independent sample oracles and compatibility comparisons. Later documentation
changes are recorded separately. Proxy/refine selection, larger operation regions,
larger layered files, repeated scale-v2 and Unix memory remain open. The unchanged
registry stays 163/167; full W4 and the overall goal remain incomplete.
