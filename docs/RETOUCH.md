# Region cloning and healing

The atomic `retouch` edit operates on an explicit target and `source_id` in the same document. Both may use `raster`, inline `samples` or immutable-block `stored_samples`; source and target may be the same item. Each operation freezes both input grids before sampling, so overlapping clones never read their own writes. Existing snapshots remain unchanged, and persistent sessions support undo/redo and retries. Stored edits retain exact native patches and create no resource files.

```json
{
  "op": "retouch", "id": "pixels",
  "options": {
    "source_id": "source",
    "source_transform": [1, 0, 0, 1, -12, 0],
    "region": {"x": 20, "y": 14, "width": 12, "height": 10},
    "mode": {"type": "clone"},
    "sampling": "bilinear", "border": "error", "opacity": 1
  }
}
```

Send this in `document.edit` or `session.apply`'s `edit` action with the expected revision. `mode:{"type":"heal"}` enables original boundary-constrained healing. Both modes retain the target representation, native depth (`u8`, `u16`, `f32`), channels and a detailed change receipt. Normalized encoded sRGB is required; profiled or linear HDR inputs reject explicitly. A chromatic result cannot silently enter a gray/alpha target. Save the input snapshot and request to replay different controls; this is not a live effect in the snapshot.

## Coordinates and coverage

`region` is a nonempty integer rectangle entirely inside the target's **native pixel grid**. Optional `gray_hex` has exactly one gray8 byte per region cell, row-major; omitted/null means full coverage. Zero cells are outside the edited domain, including holes and disconnected areas. All positive cells belong to the domain. Their fractional coverage applies at the final replacement, not as a coefficient in the healing equations.

`source_transform` defaults to identity and maps target native pixel centers into the source native grid. It supports the existing finite, nonsingular affine matrix contract, including translation, scale, reflection and shear. Source dimensions, depth and channels may differ from the target. Source scene transforms, visibility, opacity, masks and effects do not change native samples. A source lock permits reading; every target/dependency lock is honored. Ordinary image links, containers and composite sampling remain unsupported. Immutable native-block grids are supported and verified completely, including blocks outside the edit.

`sampling` is `bilinear` (default, premultiplied encoded sRGB) or `nearest` (containing source cell). Source cells are centered at half-integer coordinates. `border` is `error` (default), `transparent` or `clamp`. Error checks every nonzero sampling tap actually needed. Clone needs covered cells; healing also needs adjacent unselected cells for its boundary conditions. A source footprint outside those required cells is irrelevant. Transparent borders supply zero premultiplied RGBA; clamp repeats edge pixels.

`use_selection:true` requires an explicit canvas selection. Each target native center maps through its full world transform, then samples the containing selection cell; outside the canvas gives zero. Region coverage multiplies selection coverage. The selection remains unchanged. `opacity` is 0..1, default1. Replacement strength is region coverage times selection coverage times opacity. A zero-opacity request still validates input fields, IDs and regions, but skips source footprint evaluation and healing.

## Original healing equations

Let S be the frozen, mapped source field and T the frozen target, both normalized **premultiplied encoded sRGB plus alpha**. Let D contain every positive-coverage target cell. Four-connected neighbors are limited to the target image; the exterior of the image contributes no edges. For each channel independently, the unknown correction u satisfies:

```text
(degree(p) + screening) * u(p) - sum(u(q), q in D and adjacent to p)
    = sum(T(q) - S(q), q outside D and adjacent to p)
healed(p) = S(p) + u(p)
```

This is the minimizer of squared correction differences across grid edges, plus `screening * sum(u²)`, with fixed correction T-S on the unselected boundary. It retains the source's local differences while matching surrounding target values. Screening defaults to0 and accepts0..16; larger values pull the correction toward zero, retaining more of the mapped source's absolute color. With zero screening, every connected region must have an unselected in-image boundary. An entirely selected image therefore needs explicit positive screening. Image-edge regions with an interior boundary work without a fabricated exterior color.

An original sparse diagonal-preconditioned conjugate-gradient solver evaluates the four channels in fixed order. It checks the **true** maximum absolute equation residual before accepting a solution, restarting after drift or every64iterations. `tolerance` defaults to1e-9 and accepts1e-12..1e-4 in normalized premultiplied units; `max_iterations` defaults to2048 and accepts1..4096 **per channel**. Failure returns `RETOUCH_PRECISION` and discards the entire batch. This residual is an equation-quality measurement, not a bound on every final encoded color error or a promise of perceptual reconstruction.

Healing can produce values outside the representable premultiplied color range. Alpha clamps to0..1; each premultiplied RGB channel clamps to0..alpha. The receipt counts affected pixels. This clamping occurs after the measured linear solve. Clone uses its sampled source directly. Both modes then interpolate with the frozen target by final replacement strength and encode straight channels once at the target's native depth. Gray/alpha targets require equal resulting RGB channels before encoding. Untouched bytes, including hidden color, signed zero and float subnormal bits, remain exact. Newly cleared pixels canonicalize to zero channels. No source-over accumulation is implied.

## Measurements, limits and fidelity

The receipt includes normalized settings SHA-256, source/target/result pixel identities, declared identity kinds, source/target sample types, the global processing window and its conservative memory bound, positive-coverage area and bounds, coverage sum, connected components, in-image boundary edges, exterior image faces, total grid perimeter, changed pixels/bounds, clamping count, per-channel iterations/residuals and work. Legacy raster identities keep their original RGBA8 image framing; sample grids use the typed native manifest identity, independent of inline versus stored representation. Bounds are global and end-exclusive. The boundary RMS is the root mean square of all four premultiplied channel differences across positive-domain/unselected edges, before and after editing. It excludes exterior image faces and is null when no boundary edges exist. It describes the seam; a naturally textured seam need not be zero, and lower RMS alone does not prove image quality.

Independent dense pivoted elimination, affine sampling, analytic constant-offset texture recovery, disconnected/hole domains, alpha/gamut fixtures and decoded delivery pixels verify these contracts. Automatic donor selection, patch synthesis, content-sensitive fill/move and guided edge correction are now available through [REPAIR.md](REPAIR.md). General semantic photograph reconstruction is not implied. No external model, application or hardware is required.

Existing storage limits remain: 65,536 aggregate inline pixels, 16,777,216 stored source pixels, 65,536 pixels per local edit, and the stored grid's retained patch count/aggregate pixel and snapshot-byte limits. A maximum-size high-depth patch may need the explicit `large_raster` profile. The solver covers only the requested rectangle plus its actual in-image one-cell boundary, at most 131,072 cells. Each source reader keeps at most 16 raw blocks. Before loading resources, a conservative 128 MiB processing bound includes solver/raw/output buffers, source preparation and complete replacement blocks. Narrow edits can intersect many blocks and reject this bound even with a small selected area; no full-image floating-point buffer or raised processing allowance is implied.

Work remains bounded by67,108,864 cell visits across complete dependency preparation, block loads, topology, sampling, right-hand-side assembly, solver passes and replacement blocks. Fixed-size per-cell arithmetic is not separately counted. Deadlines/cancellation apply throughout and before returning the pure candidate. Limits never silently reduce accuracy or choose a different region. Large or ill-conditioned systems can fail explicitly; sources and session heads remain intact.

`tests/test_native_retouch.py` adds all six depth/channel combinations, exact rational affine sampling and dense rational healing equations, overlapping block-boundary clones, hidden float bits, native selections, pure MCP proposals, retries, undo/redo, backup/recovery, unselected corruption and memory/patch/lock failures. An original two-megapixel texture has independent complete native-output checks for clone/heal edits and historical publication; its separate [workload and budgets](WORKLOAD_MEASUREMENT.md#native-clone-and-heal-edits) retain the original unsupported-edit failure. This does not complete broader native operators or the A5 scale gate.

Run `python examples/retouch_workflow.py --output <new-directory>` for preserved original pixels, a blemished texture, clone/heal requests, measured receipts and lossless PNG/TIFF/snapshot deliveries.
