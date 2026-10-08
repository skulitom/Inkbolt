# Region cloning and healing

The atomic `retouch` edit operates on an inline raster target and an explicit inline `source_id` in the same document. Source and target may be the same item. Each operation freezes both input grids before sampling; overlapping clones never read their own writes. Existing snapshots remain unchanged, and persistent sessions support undo/redo and retries.

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

Send this in `document.edit` or `session.apply`'s `edit` action with the expected revision. `mode:{"type":"heal"}` enables original boundary-constrained healing. Both modes return ordinary editable RGBA8 content and a detailed change receipt. Save the input snapshot and request to replay different controls; this is not a live effect in the snapshot.

## Coordinates and coverage

`region` is a nonempty integer rectangle entirely inside the target's **native pixel grid**. Optional `gray_hex` has exactly one gray8 byte per region cell, row-major; omitted/null means full coverage. Zero cells are outside the edited domain, including holes and disconnected areas. All positive cells belong to the domain. Their fractional coverage applies at the final replacement, not as a coefficient in the healing equations.

`source_transform` defaults to identity and maps target native pixel centers into the source native grid. It supports the existing finite, nonsingular affine matrix contract, including translation, scale, reflection and shear. Source dimensions may differ from the target. Source scene transforms, visibility, opacity, masks and effects do not change native samples. A source lock permits reading; every target/dependency lock is honored. Immutable image links, containers and composite sampling are explicitly unsupported; convert a copy to native pixels first.

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

Healing can produce values outside the representable premultiplied color range. Alpha clamps to0..1; each premultiplied RGB channel clamps to0..alpha. The receipt counts affected pixels. This clamping occurs after the measured linear solve. Clone uses its sampled source directly. Both modes then interpolate with the frozen target by final replacement strength and encode straight RGBA8 once. Untouched bytes, including hidden RGB at zero alpha, remain exact. Newly cleared pixels canonicalize to zero RGBA. No source-over accumulation is implied.

## Measurements, limits and fidelity

The receipt includes normalized settings SHA-256, source/target/result pixel identities, positive-coverage area and bounds, coverage sum, connected components, in-image boundary edges, exterior image faces, total grid perimeter, changed pixels/bounds, clamping count, per-channel iterations/residuals and work. Bounds are end-exclusive. The boundary RMS is the root mean square of all four premultiplied channel differences across positive-domain/unselected edges, before and after editing. It excludes exterior image faces and is null when no boundary edges exist. It describes the seam; a naturally textured seam need not be zero, and lower RMS alone does not prove image quality.

Independent dense pivoted elimination, affine sampling, analytic constant-offset texture recovery, disconnected/hole domains, alpha/gamut fixtures and decoded delivery pixels verify these contracts. Automatic donor selection, patch synthesis, content-sensitive fill/move and guided edge correction are now available through [REPAIR.md](REPAIR.md). General semantic photograph reconstruction is not implied. No external model, application or hardware is required.

Existing inline storage limits still apply, including65,536 aggregate stored pixels. Work is bounded by67,108,864 cell visits across preparation, topology, source sampling, right-hand-side assembly, solver matrix/update/preconditioner passes and output. Fixed-size per-cell arithmetic is not separately counted. Deadlines/cancellation are checked before and between bounded passes, while sampling and before publication. Limits never silently reduce accuracy or choose a different region. Large or ill-conditioned systems can fail explicitly; sources and session heads remain intact.

Run `python examples/retouch_workflow.py --output <new-directory>` for preserved original pixels, a blemished texture, clone/heal requests, measured receipts and lossless PNG/TIFF/snapshot deliveries.
