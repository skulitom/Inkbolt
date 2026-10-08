# Saved channels and image-guided selection

Inkbolt stores reusable scalar regions separately from visible artwork. These original operations use the same Rust library, JSON CLI and MCP tools. They are available in both document kinds. A selection or saved channel never changes a composite until an explicit operation such as `mask_from_selection` uses it.

## Saved scalar channels

Schema-v2 snapshots may contain `channels`, a map from stable IDs to `{name,role,plane}`. The plane is canvas-sized `{width,height,gray_hex}` with one unsigned byte per pixel in row-major order. Names are at most 1,024 UTF-8 bytes and contain no control characters. IDs use the ordinary portable identifier contract. Empty channel maps are omitted; older snapshots and their stored hashes remain unchanged. Schema-v1 cannot contain channels.

Roles are explicit:

- `{"type":"alpha"}` (default) stores a reusable scalar selection. It does not alter document alpha.
- `{"type":"spot","ink_id":"ocean","alternate_srgb":[12,80,170]}` stores named-ink tint coverage: zero is no ink and 255 is full coverage. Ink identity is unique within a document. Its alternate color is an encoded-sRGB preview, without a physical ink, overprint or profile conversion model. Exact ink ID, alternate color and coverage remain in editable snapshots and session history.

`channel_put` takes `id`, `channel` and optional `replace_existing:false`. `channel_remove` takes `id`. `channel_calculate` takes `id`, `name`, optional `role` (alpha), `calculation` and optional `replace_existing:false`. An occupied ID is an error unless replacement is explicit. Replacement replaces the name, role and complete plane; it can intentionally convert a named-ink channel to alpha. References resolve from the candidate state before replacement, so calculating a replacement from its own old values is defined. No implicit channel renaming, merging of ink IDs or conversion occurs.

`channel_load` takes `id` and optional `combine:replace`. It copies the channel into the active selection. `add`, `subtract` and `intersect` use maximum, saturating difference and minimum respectively; these require an existing selection. Loading or combining a spot channel copies its tint bytes without changing its role or the artwork. Saving an absent selection is an error; an explicit empty selection is valid. Channel removal also fails for an unknown ID.

Calculation sources are `{type:selection}`, `{type:channel,id}`, `{type:constant,value}` and `{type:component,component}`. Components are `red`, `green`, `blue`, `alpha` or `luma`, sampled from the current complete scale-one RGBA8 composite. Earlier edits in the same atomic batch are visible. Supply normal image/font resource roots where needed. Zero-alpha composite colors are canonical zero. `luma` is encoded brightness `round((2126R+7152G+722B)/10000)`, not linear-light luminance.

Calculations use integer arithmetic:

| Calculation | Exact byte result |
| --- | --- |
| `copy` with `source` and optional `invert:false` | Source, or `255-source` |
| `combine` with `left`, `right`, `mode`, optional `invert_left:false`, `invert_right:false` | Apply inversions first; then the mode below |
| `add` / `subtract` / `difference` | `min(255,a+b)` / `max(0,a-b)` / `abs(a-b)` |
| `multiply` / `screen` | `round(a*b/255)` / `255-round((255-a)*(255-b)/255)` |
| `minimum` / `maximum` / `average` | `min(a,b)` / `max(a,b)` / `round((a+b)/2)` |

Rounding is nearest with exact halves upward. No hidden floating-point quantization or color-space conversion occurs. When both operands sample the composite, one rendered image is reused.

`document.inspect` reports sorted channel IDs, names, roles, bounds, coverage totals and byte hashes. `document.diff` reports channel metadata changes independently of visible pixel changes. `channel.export` takes `document`, `id` and `display:gray` (default) or `ink`. Gray returns opaque grayscale RGBA8 PNG; ink requires a spot role and returns its alternate RGB with tint as alpha (zero tint is transparent black). The response retains identity and coverage hash and explains that PNG itself does not carry named-ink semantics. Only snapshots retain the full editable channel representation; ordinary artwork PNG/SVG exports exclude this nonprinting state. Standalone artboard exports omit document-sized channels from their temporary view; the source document stays unchanged. There is no color-managed separation or prepress-completion claim.

## Image-guided selection

`selection_sample` takes `method` and optional `combine:replace`. Other combination modes follow the same selection set algebra. All methods sample the current complete scale-one RGBA8 composite in document pixel coordinates; they do not sample hidden layers or change visible pixels. `components:rgba` is the default; `rgb` deliberately ignores alpha. Distance is the maximum absolute difference among the selected byte components. Transparent composite colors are zero, so RGB-only selection can include transparent black deliberately.

| Method | Fields and behavior |
| --- | --- |
| `color_range` | 1..32 RGBA `colors`, `tolerance` byte, optional `feather` byte (0). Use distance to the nearest target. |
| `connected` | 1..32 integer canvas `seeds` as `[x,y]`, `tolerance`, optional `feather` (0), `connectivity:four` (default) or `eight`. Sample the fixed seed colors once. Compute candidate coverage relative to the nearest seed color, then retain only nonzero candidates reachable from any seed. |
| `edge` | Integer `radius` 0..8, `tolerance`, optional `black:0` and `white:255`, with black strictly below white. Requires an active selection. Use image-gated triangular averaging followed by coverage levels as specified below. |

For color range and connectivity, distance `d <= tolerance` gives 255. Beyond tolerance, feather zero gives zero. Otherwise coverage is `round(255*clamp((tolerance+feather-d)/feather,0,1))`. The sum of tolerance and feather uses a wider integer, so it never wraps. Multiple seed colors form one union of acceptable colors; all seeds share it. Connectivity includes candidates with positive coverage, with no gradual drift of the reference color as traversal advances. Four connectivity uses orthogonal neighbors; eight includes diagonals. These are explicit color-based regions, not semantic object recognition.

Edge refinement visits the square neighborhood around each center, clipped to the canvas. Keep only neighbors whose image distance from the center is at most tolerance. Weight each by `(radius+1-abs(dx))*(radius+1-abs(dy))`. The center always qualifies. With weighted coverage sum S and weight sum W, produce `clamp(round(255*(S-black*W)/((white-black)*W)),0,255)`, using exact integers and just one final rounding. Out-of-canvas neighbors are absent; a constant selection remains constant at the boundary when levels are neutral. Radius zero with neutral levels is identity. Tolerance zero smooths only identical image colors; 255 allows all neighbors. Levels can suppress small defects after smoothing. Smoothing alone can spread uncertainty and is not guaranteed to reduce total error on arbitrary images.

Independent quality checks use original known regions: every output byte matches rational reference arithmetic, fixed-seed connectivity cannot drift along a ramp, diagonal contact follows the chosen topology, identical-color regions preserve coverage at canvas edges, local defects are reduced, and the specified smoothing-plus-levels configuration reduces total error without bleeding across a high-contrast image boundary. There is no learned segmentation, natural-image quality guarantee or foreground-color decontamination claim.

## Bounds and recovery

There are at most 16 saved channels and 262,144 aggregate saved scalar samples, separate from the 262,144 selection pixels and 65,536 inline artwork/mask samples. The 768 KiB document and 1 MiB request limits also apply. Every plane matches the canvas; channels are fixed in document coordinates and do not follow an item's transform.

Selection analysis preflights 67,108,864 work units: `pixels*targets*4` for color range, `pixels*(seeds*4+8)` for connectivity, and `pixels*(2*radius+1)^2*4` for edge refinement. Rendering has its own existing limits. Invalid seeds, missing channels/selections/resources, malformed planes, duplicate ink IDs or exhausted budgets fail explicitly. The whole edit batch rolls back on failure. Durable session undo/redo restores plane bytes and role identity together, including after process reopening. Source artwork and immutable assets remain intact.

See [selection geometry and masks](SELECTIONS.md) and run `python examples/channel_workflow.py C:/absolute/new-directory` for an original region-isolation workflow with saved channels, ink previews, editable masks and recovery.
