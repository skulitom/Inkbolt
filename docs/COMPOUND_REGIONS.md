# Editable compound regions

Agents can combine filled curves while retaining every source control point.
`work_path_combine` makes an independent nonprinting work path from 2..16 distinct
work-path or vector-item IDs. The `mode` is `union`, `intersection`, `difference`
or `xor`. Difference subtracts the union of the remaining operands from the first;
intersection requires every operand; xor includes odd membership.

```json
{"op":"work_path_combine","ids":["outline","opening"],"new_id":"region","mode":"difference"}
```

The result is a root item with identity transform. It stores source geometry,
each source's fill rule and its current composed world transform. These are
independent copies: later source edits or deletion do not change the combination.
Original source items remain intact, including names, visibility and locks.
Reading a hidden or locked source is allowed. Paint, stroke, opacity, masks and
ancestor effects do not define its region.

Stored geometry uses `shape:"compound"`, `mode` and `operands`; each operand has
`geometry`, `fill_rule` and `transform`. Another compound region can be an operand.
Individual paths use nonzero or even-odd winding and implicit contour closure.
The compound's outer fill rule must be nonzero because each leaf defines its own
winding before boolean membership; another outer rule is rejected explicitly.

## Editing and inspection

`path_component` edits one retained leaf. `component` is its zero-based index path
through nested operands, scoped to the current document revision. All ordinary
path actions apply, including explicit primitive conversion, handles, anchors,
split, reverse, join and certified simplification. Local coordinates belong to
the leaf; world coordinates include every operand and item/ancestor transform.
Other components and original sources remain unchanged.

```json
{"op":"path_component","id":"region","component":[0],"action":{"type":"handles","command_index":1,"control1":[12,8],"space":"world"}}
```

For a copied vector mask, set `clip:true` and address the target item's clip.
An empty address can edit an ordinary leaf clip. A compound node requires a leaf
address. Invalid indices, attempts to descend through a leaf and inherited locks
fail without committing any batch changes. `work_path` can replace the entire
tree explicitly, allowing agents to reorder operands or change modes/rules.

`document.query` accepts `shapes:["compound"]`. With `include_anchors`, path leaves
return ordinary anchor/handle coordinates plus their `component` address.
Primitive leaves first require explicit conversion to path commands.
Compound geometry bounds enclose all operand geometry; they are conservative
source bounds, not tight filled-result bounds. Even an empty intersection can
therefore have nonempty geometry bounds. Discovery/alignment use these bounds.

## Selections, vector masks and delivery

`selection_path` evaluates the whole region before accumulating pixel coverage.
It preserves the existing copied-selection and add/subtract/intersect contracts.
This geometric combination differs from combining already-rounded grayscale
masks: two disjoint half-pixel regions form one full pixel under union.

`clip_from_path` copies the full region into an independently editable vector
mask, preserving its world placement. Curves and operations remain stored;
each render evaluates them at the requested scale. Moving the target moves its
mask, and a separate pixel mask still multiplies its coverage. Disabling a vector
mask retains all editing state. Source files, snapshots and session undo/redo
preserve the original path and mask structures.

PNG/JPEG/TIFF delivery uses the shared renderer. Compound regions themselves are
nonprinting. Painted compound vector artwork, implicit polygonal flattening and
direct SVG/PDF delivery of active compound clips are unsupported and fail before
publication. An explicit existing appearance bake can produce raster artwork
where supported; retain the editable snapshot. `document.boolean` retains its
separate certified flattened-geometry contract and does not accept compound trees.
Its remaining general algebraic-contact requirement is unchanged.

## Numerical and resource contract

The shared evaluator uses binary64 scanline crossings, splitting cubics at their
vertical extrema. It finds each monotone crossing with at most 56 bisection steps,
computes per-leaf winding, and evaluates the boolean tree between ordered crossings.
Horizontal overlaps are integrated over 256 midpoint subrows and rounded once to
grayscale8. Without antialiasing, pixel centres and half-open crossing intervals
define binary coverage. Compounds never combine rounded leaf masks.

This is bounded numerical coverage, not a certificate for a flattened topology or
exact pixel area. Features between subrows can disappear. Coincident crossings
retain floating-point precision. Source control points are never flattened or
replaced during evaluation. Ellipse primitives use the existing four-quarter-cubic
region interpretation. These limits also apply to rendered compound clips;
ordinary noncompound display clips retain their existing backend contract.

Each compound tree allows eight nested operations, 64 leaves, 2..16 operands per
operation and the existing 4,096-command document budget, including copied clips.
Component matrices and their compositions obey ordinary coordinate/transform
validation. Region selections and compound clip buffers allow 262,144 pixels.
Evaluation retains the 67,108,864-work-unit cap, now charging boolean predicates
alongside crossings, sorting and output intervals. Oversized requests fail before
publishing results. No new package, listener, model or external resource is used.

Independent checks use vertical area integrals, analytic self-intersecting lobes,
irrational curve crossings, inverse affine coordinates and exact rectangle overlap.
They cover all four operations, winding, nested trees, independent mask copies,
component edits, snapshots, locks, cancellation and saved agent history.
`python examples/compound_region_workflow.py --output NEW_DIRECTORY` produces
five original editable examples, PNGs, snapshots and source-preserving receipts.
