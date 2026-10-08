# Knockout groups

Set `content.knockout:true` on a group or named layer in either document kind.
It is independent of `isolated`. The `group` edit accepts the same boolean;
`group_options` requires `isolated` and optionally changes `knockout`. Omitting
that edit field preserves the current value. Snapshot defaults omit false.
Inspection exposes `group:{isolated,knockout,role}`, and diffs name
`content.knockout`. Atomic edits, duplication and durable history retain it.

Ordinary children blend with preceding siblings. Knockout children blend with
the backdrop at group entry, replacing earlier siblings within their own
footprints. An isolated group's entry backdrop is transparent. A pass-through
group uses the surrounding composite. This general group concept is described
in the historical [W3C compositing draft, section 8.3](https://www.w3.org/TR/2013/WD-compositing-1-20130625/#knockoutgroups).
Inkbolt's footprint rules and implementation below are its own explicit
contract; this is not a claim of draft, document-format or application parity.

## Footprint and opacity

The footprint is a scalar field distinct from the final alpha. A leaf begins
with its evaluated intrinsic alpha after filters: paint alpha and geometry
coverage for vectors/text/fills, or reconstructed alpha for placed pixels.
Thus a fully transparent paint/pixel contributes no footprint. Use item opacity
or fill, rather than intrinsic paint alpha, to fade color while retaining the
complete knockout footprint. Hidden items contribute neither color nor shape.
A visible, zero-opacity item still replaces earlier siblings in a knockout
group; within its footprint it reveals the group's initial backdrop.

Containers retain the union of child footprints, `f + (1-f)*next`, including
visible children whose item opacity is zero. Frame backgrounds contribute
their evaluated alpha. Children are each one element at their parent's level;
subgroups are never flattened. Filters on isolated containers evaluate the
retained footprint as an alpha-only buffer using the same filter settings.
Styles decorate that footprint with fill fixed at one; actual content fill
remains independent. The resulting footprint is raised to at least the actual
decorated alpha, since alpha-dependent filters/styles need not be monotone.

Grid masks, artwork masks, geometric clips and frame clips attenuate both
shape and alpha; item opacity only attenuates alpha. Dissolve applies its same
saved local-cell threshold to each field separately, preserving `alpha <=
shape`. Clipped layer members alter their base's color; the assembled base
keeps its own footprint. Bound adjustments retain alpha. Pass-through group
opacity interpolates its complete child-modified backdrop exactly once, while
its masks also attenuate the retained child footprint. Existing restrictions
on pass-through blend, fill, filters and styles still apply.

## Pixel equations

Let `D` be the current premultiplied composite, `B` the saved initial backdrop,
`f` the incoming footprint, `a` its final alpha and `Cs` its straight color.
Let `b` be backdrop alpha and `Cb` its straight color, zero when `b=0`.
Each of the 26 color modes supplies `M(Cb,Cs)`:

```text
P = (1-f)*D.rgb + (f-a)*B.rgb + a*((1-b)*Cs + b*M(Cb,Cs))
A = (1-f)*D.a   + (f-a)*b     + a
```

Equivalently, keep the current result outside the footprint and, inside it,
place the source with conditional alpha `a/f` over the saved backdrop. No
division by footprint is needed in the engine. Nested pass-through groups
retain that same initial backdrop, compute a candidate composite and replace
the parent result within their aggregate footprint. The initial backdrop is
never added twice. Group blending, opacity and masks apply once at the outer
boundary. f64 premultiplied channels persist until the existing final straight
RGBA8 encoding; numerical residuals are projected to `0 <= rgb <= alpha <= 1`.

## Limits and explicit failures

The presence of any knockout group enables retained shape fields for the
document, including hidden content in resource preflight. Additional work is
`output_pixels * sum(24 + filter_work + effect_work)` and must not exceed
67,108,864. Shape storage reserves `3*(maximum_ancestor_depth+1)+3` full RGBA
buffer slots in addition to existing compositing, mask and effect reservations,
within the same 4,194,304 buffer-pixel budget. This conservative reservation
covers retained initial backdrops, scalar shapes and temporary evaluation.
Artboard range preflight includes the additional work for every selected view.
Documents without knockout allocate no retained shape fields.

SVG export rejects stored knockout, including hidden groups, because the
current exporter cannot preserve it. Snapshot and PNG export remain available.
Ungroup rejects a knockout group or a group directly inside a knockout parent:
removing either boundary can change the footprint and overlap result. Other
existing appearance-preservation checks still apply.

Knockout inside a mask source and unbound backdrop adjustments inside a knockout
subtree are explicitly unsupported. Use ordinary mask-source artwork and bind
adjustments to drawable bases. No implicit flattening, silent approximation or
native-format compatibility is claimed. These restrictions do not remove the
broader interchange or appearance requirements from the full feature registry.

Run `examples/knockout_workflow.py --output <new-directory>` for original editable
layered, isolated-knockout, pass-through-knockout and zero-opacity-cutout variants.
Independent rational tests condition on footprint coverage and check every blend
family, nested group choices, masks, fractional edges, filters, styles, dissolve,
strict errors, budgets and durable MCP history.
