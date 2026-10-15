# Editable SVG import

The numeric ranges in `capabilities.svg_import.validation_limits` share the
engine's canvas, stroke and text definitions. SVG source units and the fixed CSS
96-ppi conversion remain unchanged.

See the generated [limit reference](LIMITS.md) for centralized resource ceilings.

Negative and fractional coordinate fidelity, normalization tolerance and consumer-preview boundaries are documented in [COORDINATE_PRECISION.md](COORDINATE_PRECISION.md).

`svg.import` accepts an explicit local file or inline UTF-8 text and returns a new vector document, a source-byte SHA-256 receipt, an element-to-item mapping, normalization losses and an `approximations` array (empty when no arcs/corners were normalized). It writes no files. Local image references require an explicit source root; remote resources are refused. The same command is available through the Rust library, JSON CLI and MCP stdio.

```json
{"command":"svg.import","id":"diagram","source":{"kind":"file","source_path":"C:/Graphics/input.svg"}}
```

For inline input, use `source: {"kind":"text","text":"<svg ...>...</svg>"}`. The [original example](../examples/import-svg.json) creates an editable diagram from text. Persist the returned `document` with `session.create`; use the returned `mapping[].item_id` with ordinary query, edit, diff, export and undo operations. Imports create revision zero. They do not merge into an existing document or create a session automatically.

## Explicit omission reports

Strict failure remains the default (`unsupported:"error"`). An explicit
`unsupported:"omit_and_report"` on `svg.import` or `add_svg` enables a bounded
recovery pass. The Rust library exposes the same option through
`svg_import::Options` and `import_with_options_controlled`; existing import
functions keep their strict behavior.

```json
{"command":"svg.import","id":"partial","unsupported":"omit_and_report","source":{"kind":"text","text":"<svg width=\"32\" height=\"24\"><foreignObject/><rect width=\"8\" height=\"8\"/></svg>"}}
```

Only `SVG_UNSUPPORTED` errors located at removable source elements are eligible.
The importer removes the whole element and its descendants, then retries on a
private candidate. An unsupported attribute removes its owning element; an
unsupported embedded stylesheet removes the entire `style` element. Inline
styles belong to their element. A failure specific to a `use` placement removes
that placement. References to IDs removed by these omissions cause their owning
elements to be omitted with a dependency reason. Truly missing references still
fail. Removed text or styles can change the remaining layout and appearance;
this is explicitly degraded import, not a fidelity guarantee.

The result includes `unsupported:"omit_and_report"` and `omissions`, even if the
array is empty. Each row records `source_id`, `element`, `reason`, `code`, original
UTF-8 `byte_offset` and exclusive `byte_end`, one-based `line` and `column`, and
the number of descendant elements covered by the removal. `cause` retains the
located diagnostic and any omitted dependency ID. If a later removal covers
earlier removals, their reports move into its `covered_omissions` array. Top-level
rows are in source order and do not overlap. Byte locations in ordinary mappings,
definition receipts, approximations, reuse paths and subsequent errors also refer
to the original source. Insertion reports use the caller's fragment coordinates,
excluding its generated root. Source hashes always identify the original bytes.

Malformed XML, empty/duplicate IDs and excessive nesting are checked on the
complete source before omission. DTDs, processing instructions, root-level or
unlocated unsupported semantics, invalid-value errors, missing fonts/resources,
resource budgets and cancellation still fail without returning a partial document.
Nesting is checked before XML parsing, including the insertion probe. Discarded
subtrees do not otherwise receive an independent validation of every semantic
value. Unsupported CSS syntax classified as `SVG_UNSUPPORTED` is eligible for
whole-owner omission; XML well-formedness is always required.

At most 256 private attempts and 128 MiB of cumulative filtered source bytes are
allowed, separately from the existing source, XML, scene and per-attempt work
limits. Insertion keeps ordinary atomic batch, proposal, retry and history
semantics. The original file is never rewritten and these passes publish no
resource files. [Focused Windows/Linux verification](DEVELOPMENT_STATUS.md#w3a8-omission-policy-implemented-milestone-open)
passed for this increment. The remaining unsupported-owner audit, cumulative-work
boundary evidence and fresh full W3a.8 milestone acceptance remain open.

## Insert into an existing document

Use the atomic `add_svg` operation in `document.edit`, session edit actions or
the Rust `edit::Operation::AddSvg`. See the [runnable schema example](../examples/add-svg.json).

```json
{"op":"add_svg","svg":"<g><rect width=\"20\" height=\"12\" rx=\"2\" fill=\"#2468ac\"/></g>","parent":"layer","prefix":"badge"}
```

Only `svg` is required. It accepts a complete SVG document or a fragment with
one or more elements. Fragments inherit a synthetic SVG root whose viewport is
the destination's logical canvas size; the root adds no clip. Complete documents
retain their own viewport and viewBox; an outer group preserves viewport clipping
independently of any original root clip. Nested SVG viewports have the mapping and clipping contract below.
Coordinates are local to the optional destination `parent`; its transform applies
after imported SVG transforms. Insertion appends artwork to that container.
Nonprinting mask sources remain top-level resource containers.

The operation imports editable geometry, paints, groups, images and supported text using
the same interpretation and losses described below. It preserves the destination's
canvas, profile, metadata and unrelated items. Imported item metadata is retained;
source document metadata is excluded with a loss receipt. Paints use the
destination's compositing rules, just like ordinary `add` operations. Existing
content restrictions still apply: standard raster documents accept vectors only
inside mask sources; the large raster profile supports ordinary vector artwork.
HDR display output still requires an explicit view.

Optional `font_bindings` select fonts already pinned in the destination:
`[{"family":"Geometry","font_id":"existing-font","weight":400,"style":"normal"}]`.
Weight and style default to 400 and normal. The usual `font_root` or session/workspace
font resource binding resolves bytes. Used text faces are hash/license checked by
the importer; insertion reuses their IDs and does not duplicate font descriptors.
Missing families, unavailable/corrupt resources and unsupported text fail explicitly.

`changes[].id` is the inserted root; `changes[].details` returns `root_id`, `prefix`,
`item_ids`, `font_ids`, `asset_ids`, the source `mapping`, `definitions`, `approximations`, `reuse` and
`losses`. The source receipt hashes the exact supplied UTF-8 bytes and records its
kind. Source offsets refer to those bytes; a synthetic fragment root has
`byte_offset:null` and `synthetic:true`. The default prefix is the first available
`svg-N`; explicit prefixes must satisfy the existing transfer prefix limit.
Generated IDs are deterministic for an unchanged destination and source, and
collisions fail. Use the returned source-to-item mapping for later edits. A caller
can preview IDs with a session dry run before applying its checked proposal.

The raw SVG ceiling derives from `MAX_REQUEST_BYTES` (16 MiB), reported at
`capabilities.svg_import.insertion.source_bytes`. CLI/MCP requests must also fit
the whole JSON request ceiling, including escaping and the document/other fields.
The synthetic fragment wrapper does not consume the raw SVG allowance. Existing
XML node, nesting, item, geometry and destination budgets remain enforced; a
complete SVG's viewport wrapper consumes one item. The separate `svg.import`
source ceilings remain unchanged. Unsupported input fails the whole edit batch;
there is no omission mode. Revision checks, locks, dry runs, retry receipts,
undo and redo use the ordinary atomic edit/session contracts.

## Placed images

W3a.6 has [fresh full Windows/Linux acceptance](DEVELOPMENT_STATUS.md#w3a6-complete-within-the-image-contract)
within this image contract. [Text spans](#editable-span-ranges) have separate
acceptance below; opt-in omission reports remain open.

`image` admits PNG and JPEG as editable placed images, using the shared
[image decoder and color rules](IMAGE_IO.md). Supply a `data:image/png` or
`data:image/jpeg` URI with base64 or percent-encoded bytes, or a relative local
path under `images.source_root`. `href` and legacy `xlink:href` are accepted;
conflicting values fail. Local paths may contain percent-encoded UTF-8 but
cannot contain absolute paths, empty/dot/parent segments, backslashes, query
strings or fragments. The resolved regular file must remain inside the explicit
root, including after symbolic-link resolution. Remote URLs are refused.

Both `svg.import` and `add_svg` accept the same optional `images` object:

```json
{"images":{"source_root":"C:/Graphics/assets","color_policy":"assume_srgb","sampling":"bilinear"}}
```

The root is absolute without a workspace; with a workspace it may be relative
and must resolve within that workspace. It is never inferred from the SVG path,
current directory or workspace. Omit it for data URIs. The default color policy
is `assume_srgb`, recorded in the loss receipt and source provenance. Tagged sRGB
retains its interpretation; RGB ICC input requires explicit `convert_srgb`.
`require_srgb` remains available. Metadata and source density are retained in
the original encoded bytes, not promoted into document metadata or sizing.

Each distinct source becomes an `encoded` image asset containing the immutable
PNG/JPEG bytes, original-byte hash, normalized RGBA8 hash and interpretation.
Rendering and `asset.verify` recheck both identities. Imports, failed batches
and session dry runs create no asset-store files; accepted snapshots no longer
depend on the source file. Identical source bytes share one resource. Ordinary
revision checks, proposal matching, retries and undo/redo apply to insertion.
Changing local image bytes between a dry run and application invalidates the
proposal. Once committed, an identical retry uses its retained receipt.

`x`/`y` default to zero. Absolute units and percentages use the enclosing user
viewport. Omitted or `auto` dimensions use intrinsic pixel size; a single supplied
dimension derives the other from the intrinsic ratio. Explicit two-axis sizing
uses `preserveAspectRatio`: all nine alignments, `meet`, `slice`, or `none`.
Overflow defaults to `hidden`; `visible` retains artwork outside the positioning
rectangle. Transforms, opacity, visibility, geometric clips and supported masks
apply through an outer editable group. Object-bounding-box effects use the whole
positioning rectangle, including letterboxing. Zero-size images retain a hidden
intrinsic-sized child under a nonpainting group. Hidden and unused image sources
are still validated, including finite coordinates after percentage resolution.
Images may be local `use` targets and share compatible
native components.

Sampling defaults to bilinear; `images.sampling` accepts the existing native
samplers. The inherited `image-rendering` property accepts `auto` (use that
option) and `pixelated` (nearest), through attributes, embedded CSS and inline
style. The latter is a declared approximation at noninteger scales: Inkbolt
does not reproduce the two-stage reconstruction described by
[CSS Images](https://www.w3.org/TR/css-images-3/#the-image-rendering).
Other values fail explicitly. PNG rendering remains authoritative for engine
sampling. [SVG image sizing](https://www.w3.org/TR/SVG2/embedded.html#ImageElement)
is the public basis for placement and positioning-rectangle bounds.

Mapping rows add `asset_id`, `image_item_id`, `image_size`, and either
`viewport_item_id` or `empty_image`. Insertion remaps resource and item IDs into
the destination; reuse receipts identify shared editable components.
The existing SVG source, whole-request, snapshot-byte, asset-count and aggregate
16,777,216 decoded-pixel limits remain enforced. Encoded sources consume base64
snapshot bytes, not the raw-inline-pixel allowance. The old 65,536 raw-inline-pixel
limit is unchanged; this does not establish the larger W4 workload target.
SVG sources inside `image`, animations, CSS geometry/object-fit and image artwork
inside mask sources remain unsupported. Masks applied to image owners are supported.

## Supported interpretation

The root must be `svg`, with the SVG namespace or no namespace consistently throughout. Explicit width and height must resolve within 0.000001..32768 logical pixels at 96 pixels/inch. Fractional dimensions retain a [logical vector canvas](VECTOR_CANVAS.md) with a ceiling-sized preview grid. User units, px, in, cm, mm, pt and pc are supported. Percentage and font-relative canvas sizes fail. Geometry remains fractional f64. A positive `viewBox` becomes the root group's affine transform, with the nine min/mid/max alignments, meet/slice or none; default is xMidYMid meet. PNG rendering clips at the canvas viewport. Root transforms compose outside the viewBox mapping. Nested SVG viewports have the mapping and clipping contract below.

Nested `svg` establishes an outer viewport group and an inner content group.
`x`/`y` default to zero; `width`/`height` default to `100%`, including `auto`.
Absolute units and percentages resolve against the enclosing user viewport;
a parent's `viewBox` supplies that percentage basis when present. The element's
transform applies outside its position. The inner `viewBox` uses the same nine
alignments and `meet`/`slice`/`none` rules as the root. A valid
`preserveAspectRatio` without `viewBox` has no geometric effect; an optional
`meet` or `slice` after `none` is accepted and ignored.

The viewport clips by default. Presentation attributes, embedded styles and
inline styles can choose `overflow:hidden` or `overflow:visible`; other overflow
values fail. Opacity, explicit clips and masks apply once to the mapped content.
Descendants resolve percentage text positions, references, gradients and masks
in the new user coordinates; following siblings recover the enclosing viewport.
Nested viewports also work inside symbols, reusable groups and mask artwork.
A local `use` can reference an `svg` and override its dimensions, retaining the
existing compatible component sharing and declared context-variant rules.

Zero width or height produces a nonpainting empty group with a declared loss of
unexpanded content; its descendants and references still undergo template
validation. It does not hide siblings. Negative dimensions and nonpositive
`viewBox` dimensions fail. Generated groups count against the existing item and
hierarchy budgets. Mappings retain original source locations, `viewport_size`
and `viewport_item_id`, or `empty_viewport:true` for empty groups. Insertions
remap these item IDs along with component placements.

An omitted nested `version` uses the root's text/mask interpretation. Explicit
`1.0`, `1.1` or `2.0` is accepted only within that same legacy-versus-2.0
interpretation; changing it inside a document fails explicitly. Root canvas,
shape percentage lengths, CSS geometry properties, nested metadata and other
unsupported semantics retain their existing boundaries. These rules follow the
public [SVG coordinate model](https://www.w3.org/TR/SVG/coords.html) and
[viewport overflow rules](https://www.w3.org/TR/SVG/render.html).
The nested viewport milestone has [fresh full Windows/Linux acceptance](DEVELOPMENT_STATUS.md#w3a5-complete-within-the-nested-viewport-contract).
Later SVG admission tasks remain open.

Supported elements are groups, positive-size rectangles with optional rounded corners, ellipses, circles, lines, polygons, polylines and paths. Path commands M/L/H/V/C/S/Q/T/A/Z support absolute/relative coordinates, repeated parameter groups, implicit lines after moveto, smooth-handle reflection and finite exponent notation. Quadratics convert to cubics mathematically exactly up to f64 roundoff. A drawing command after close starts a new contour at the closed contour's start. Empty/non-drawable contours and repeated close commands fail under the current path model. Transform lists support matrix, translate, scale, rotate with an optional center, and skewX/skewY. Singular/out-of-range transforms fail under the shared document limits.

Elliptical arcs follow the public [SVG endpoint-to-center and radius-correction
rules](https://www.w3.org/TR/SVG/implnote.html#ArcImplementationNotes). Negative
radii use their absolute values; insufficient radii grow proportionally to
connect the endpoints. A zero radius draws a line, and identical endpoints add
no segment. These commands reset smooth cubic/quadratic reflection. Flags must
be single `0` or `1` characters; compact adjacent flags and coordinates are
accepted. Corrected radii are bounded by the shared 32,768 local-unit coordinate
ceiling. Nonfinite or numerically unreconstructable geometry fails explicitly.

Nondegenerate arcs become tangent cubics spanning at most 90 degrees each,
subdivided until the maximum radial error bound is at most **0.001 source-element
local units**. The bound excludes binary64 roundoff and renderer sampling. It
applies before element, ancestor, viewport and object-box transforms: for an
affine linear part `L`, document-space error is bounded by the reported local
error times the largest singular value of `L`. It is not a fixed pixel error.
For clip definitions, all resolved clip/object-box transforms also apply.
Expanded commands consume the existing per-path and aggregate geometry budgets;
the importer never drops a segment to fit a budget.

Each imported occurrence using arcs has a receipt entry, including clip-definition
and mask-source elements. Reused occurrences can repeat the original source location. Entries carry `source_id`, `element`, XML `byte_offset`,
`method`, `coordinate_space`, `binary64_roundoff_included:false`, and `arcs` with
`arc_commands`, `cubic_segments`, `zero_radius_lines`, `coincident_endpoints`, and
`max_radial_error_local`. The last field is the maximum bound for that element,
not the sum of its segments. Degenerate-only entries have zero approximation
error. Entries are ordered by source offset; unused clip definitions can also
appear because their geometry is validated during import.

The original error derivation uses `h=tan(abs(segment_angle)/4)`. A unit-circle
tangent cubic's squared radial excess is
`16*h^6/(1+h*h)^2 * t*t*(1-t)^2*(2*t-1)^2`. The last polynomial is bounded by
`1/108`, and `sqrt(1+x)-1 <= x/2`. Multiplying the resulting distance bound by
`max(rx,ry)` bounds elliptical radial projection distance. The implementation
also adds the maximum endpoint reconstruction adjustment, preserves supplied
endpoints exactly and rejects adjustments exceeding the tolerance. This is a
geometric approximation bound, not an interval-arithmetic floating-point proof.

Rounded rectangles follow the [SVG radius defaulting and clamping
rules](https://www.w3.org/TR/SVG2/shapes.html#RectElement) for the supported length
subset. Omitted or `auto` radii copy the other radius before each axis is clamped
to half its corresponding rectangle extent. Both automatic, or either zero,
produce square corners. Negative radii fail; percentages and CSS geometry
properties remain unsupported. Equal and unequal radii both expand to ordinary
editable paths using the same arc contract and receipt. Original corner
parameters are not retained. Snapshots retain the emitted cubics exactly; SVG
export emits cubics and reimport does not approximate them a second time.

Presentation attributes, embedded CSS and inline `style` resolve before document
validation. Fill/stroke, their opacity, fill rule, color, width, cap, join, miter
limit and visibility inherit. `currentColor` follows the descendant's computed
color. Explicit `inherit` is accepted on these inherited properties. Fill defaults
to black, stroke to none. Colors support three/six-digit hex, comma-separated
integer or percentage rgb(), the sixteen basic color names and transparent.
Unsupported paint servers, CSS variables, `!important`, other color syntaxes and
out-of-range component values fail. Gradient definitions accept sRGB or linearRGB
interpolation; ordinary artwork/group compositing remains sRGB.

Embedded `<style>` text/CDATA is collected before artwork, so later blocks apply
to earlier elements. Supported selectors are case-sensitive type, universal `*`,
class, ID, simple compounds such as `rect.icon#mark`, and comma-separated lists.
Repeated selector components contribute to specificity; repeated tokens in an
element's `class` attribute do not. ID/class/type specificity is compared in that
order, then later rules/declarations win. Presentation attributes precede every
stylesheet rule, including `*`; inline declarations take precedence over all
rules, with the last repeated declaration winning. Inheritance happens after
each element's cascade. The same path serves `svg.import` and atomic `add_svg`.

Styles apply to admitted artwork, groups, text, gradients, stops, clips and masks.
They resolve to editable properties; classes and stylesheet syntax are reported
as losses. Comments between CSS tokens are supported without inventing descendant
selectors or joining distinct identifiers. Numeric lexemes retain binary64 parsing.
Mask shorthand resets participate in declaration order and specificity.

At-rules, media/alternate stylesheets, external CSS, escapes, combinators,
attribute/pseudo selectors and unimplemented properties fail explicitly, including
unmatched rules and overwritten declarations. Errors identify the source element's
byte offset and line/column; CSS parse failures also give an offset into its decoded
CSS text. Style elements accept optional `id` and `type="text/css"` only.
Insertion locations refer to the caller's original fragment or complete SVG;
errors on a generated root are explicitly synthetic with no source position.
CSS-wide keywords other than `inherit` remain unsupported; `inherit` is recognized
without regard to ASCII case. Quoted font-family names retain their literal meaning.
The strict importer does not silently discard invalid declarations as a browser
may. Existing value/property restrictions still apply; relative font-size range
checks use the actual inherited size when the declaration applies.

CSS shares the source byte/node limits and has separate ceilings of 4,096 rules
(and 4,096 alternatives per rule),
64 components per selector, 65,536 declarations and 4,194,304 matching work units
(selector components/name bytes and applied declarations). Cancellation is checked
during collection, parsing and matching. These bounds appear in `capabilities.svg_import.css`.
This implements the [SVG style model](https://www.w3.org/TR/SVG2/styling.html)
and [selector specificity](https://www.w3.org/TR/selectors-3/#specificity) within
the stated subset using the external [CSS tokenizer](https://docs.rs/cssparser/0.38.0/cssparser/).

Groups retain ordered children and apply their own opacity once after compositing the children. Display none suppresses a subtree. Visibility hidden/collapse inherits to artwork but can be overridden by a visible descendant. Fill/stroke opacity is distinct from object/group opacity. Solid color components, gradient stops and paint alpha quantize to RGBA8; object/group opacity retains f64 precision. A zero stroke width removes the stroke. Other stroke limits match the engine. There is no automatic color-profile conversion.

The root is an editable group. Each imported drawable/container receives a deterministic `svg-N` ID in page preorder. Mask source subtrees follow page items, in definition byte-offset order; definitions discovered inside sources join that bounded queue. The receipt maps original IDs (including IDs outside the engine's syntax) and original byte offsets to these new IDs; duplicate or empty source IDs fail. A plain `title` becomes the item name, including decoded XML character references; without a title the source ID supplies the name. Plain `desc` text is omitted with a loss entry. Source formatting, comments, style inheritance expressions, original units, shorthand and semantic source IDs are not persisted in the snapshot. Retain the original source and receipt when those are needed.

## Local reusable shapes (W3a.4 in progress)

`use` accepts a literal local `href="#id"` or `xlink:href="#id"` targeting a
supported shape, group, text element, symbol, nested `svg` or another `use`. Forward references and
graphics stored inside `defs` are admitted. The placement and style rules follow
the public [SVG reuse specification](https://www.w3.org/TR/SVG2/struct.html#UseElement).
Source declarations and the embedded stylesheet are evaluated
with styles inherited from each placement. Compatible resolved occurrences become
native components with placement overrides. The original source's ancestors do
not supply the copy's inherited color or other styles. Source transforms remain
inside the placement's transform and x/y translation. Percentage x/y values use
the current viewport. Width/height are validated but do not scale ordinary shapes.

Each copied mapping retains its original source offset and an `instance_path`
of enclosing placements, including their item IDs and source offsets. `add_svg`
remaps both the ordinary mapping and these paths to destination IDs and original
fragment coordinates. Imported item metadata applies to every matching copy.
Cycles, missing targets, conflicting href forms, external/encoded references,
expanded item/hierarchy overflow and unsupported child content fail the import.
The existing reference-depth limit also applies to unused definitions. Unused
artwork templates are checked for supported syntax, geometry, styles and resources.
Text templates bind fonts when painted. Relative font-size range checks use the
actual placement context; definition-time validation checks their syntax without
substituting an unrelated parent size.

Targets may contain local gradients, clips and masks, including nested definitions.
Each reuse tree resolves local resource IDs before searching enclosing reuse trees
and then the original document. A fill, stroke or explicit inherited mask URL
keeps the tree where its value was declared; it is not rebound at each descendant.
Resource styles inherit through the cloned definition's ancestors and placement.
Gradient template stops still inherit from the final derived gradient. Delayed
mask preparation restores that same scope, occurrence path and inherited style,
including explicitly bound fonts; viewport-specific sources retain their existing
coordinate contract. These rules follow the public [fragment URL scope rules](https://drafts.csswg.org/css-values-4/#local-urls)
and [SVG reuse inheritance](https://www.w3.org/TR/SVG2/struct.html#UseStyleInheritance).

Original source IDs and byte offsets remain unchanged. Definition and mapping
rows in a cloned tree add a numeric `resource_scope` and `instance_path`; scope
numbers are local to this import receipt, with absent scope denoting the original
document. Mask definitions also identify their editable source item. Native
sharing and insertion remap occurrence item IDs without changing source locations.
Each original and cloned gradient, clip or mask consumes the existing 64-definition
budget. Duplicate preparation of a resource in the same scope does not reset it.
Masks in different reuse scopes retain independent editable sources, even when
their initial pixels agree. Component variants report that boundary explicitly.
Resource inheritance is resolved at import and is not a live CSS relationship.

Targets containing metadata still fail explicitly;
placements can refer to existing gradient, clip and mask definitions outside the
copied subtree. The reusable-shape milestone has [fresh Windows/Linux acceptance](DEVELOPMENT_STATUS.md#w3a4-complete-within-the-reusable-svg-contract).
Other SVG admission items remain open. Ordinary `use` inside clip-path geometry remains
unsupported by that narrower definition parser.

### Shared editing and placement identity

After validating the expanded source and binding its paints, clips and masks,
import groups compatible occurrences into [native components](COMPONENTS.md).
Geometry remains in one editable source. Different resolved vector paint/stroke,
visibility, opacity, blend and transform values use native overrides. Nested
instances can retain local override maps while continuing to share their geometry.
Visible originals and referenced children inside other copied groups participate
in sharing, including overlapping group/child targets.

Text/content, clip, mask or other context differences that cannot be expressed by
these overrides produce separate component variants. This partition and its loss
of editing linkage are reported. Imported styles are resolved values: changing
an original CSS expression or an ancestor colour is not live CSS recomputation.
Edit mapped source geometry/text for shared changes; use native instance overrides
or `instance_unlink` for a local change. Existing locks and history apply to
shared dependencies. SVG export expands native components and reports its own
loss of source sharing; snapshots retain them.

Repeated mapping rows may now share an `item_id`. Their original offsets and XML
`instance_path` remain distinct. `component_path` lists the native instance/source
pairs from outermost to innermost; the row's `instance_item_id` and
`component_source_id` identify the innermost pair. These are stored editing IDs,
not temporary render IDs. An original direct placement can have a component path
without an XML use path. The `reuse` receipt lists each placement's host, source
location, component identities or explicit expansion reason. Insertion remaps
all these IDs and offsets into the destination.

The original expanded input must fit the importer limits before conversion.
Component definitions, nested references, stored/evaluated items and hierarchy
retain their existing native budgets. When sharing cannot fit, the valid expanded
groups are retained with a reason; no limit is raised and no failed source
validation is waived. Raster insertion also retains groups because native
components are vector-only. If components exceed the existing destination's
budget, insertion retries once with expanded groups on the untouched candidate.
Ordinary destination validation still decides whether that result fits.

### Symbol viewports

`symbol` definitions do not paint directly. An instantiated symbol has a separate
editable viewport group for its rectangular clip and placement, and an inner group
for its viewBox transform and appearance. Its own display declaration does not
suppress the direct instance; the host `use` still controls display. Unreferenced
nested symbols remain definitions.

Dimensions accept absolute units, percentages and `auto`. Explicit non-auto
width/height on `use` override the corresponding symbol dimensions; remaining
auto dimensions use the enclosing user viewport. The symbol's x/y and transform
apply inside the host placement. Positive-size viewBox mapping supports the nine
alignments, meet, slice and none. Numeric/percentage `refX`/`refY` and their axis
keywords anchor a point in the mapped content; omitted anchors retain viewport-edge
placement. Overflow defaults to hidden, with explicit hidden/visible supported
on symbols. These rules follow the public
[symbol contract](https://www.w3.org/TR/SVG2/struct.html#SymbolElement) and
[coordinate rules](https://www.w3.org/TR/SVG2/coords.html#Units).

Mappings include `viewport_item_id` and `viewport_size`; atomic insertion remaps
the extra item identity. A zero dimension becomes a nonpainting empty group with
an `empty_viewport` receipt and explicit loss of unexpanded content. Invalid and
unsupported source syntax still fails. CSS geometry properties and additional
overflow modes remain unsupported; nested `svg` follows the viewport contract above.

Percentage coordinates in admitted text, placements, paints and masks use the
current symbol's viewBox dimensions, or its viewport dimensions without a viewBox.
Returning from the symbol restores the enclosing coordinate basis. Mask sources
used in different viewport contexts have independent editable variants, with an
explicit sharing-loss receipt; placements in the same context share one source.
Variant mappings include `resource_item_id` and `resource_viewport`. Original
definition offsets remain unchanged, and repeated preparation does not collect
nested source definitions again.

## Gradients and clipping definitions

`defs`, `linearGradient`, `radialGradient`, `stop` and `clipPath` are now supported. Definitions can occur before or after artwork, directly in a drawing container or inside defs; each definition requires a unique source ID. Literal local `url(#id)` references may use quotes around the fragment. External URLs, fallback paint syntax, encoded/escaped fragments, missing/wrong-type references and cycles fail the whole import. A separate `definitions` receipt records definition IDs/types and byte offsets. Gradient and clip definitions do not become document items. Mask definitions become nonprinting editable source containers, described below.

Linear and centered radial gradients support fill and stroke, pad/repeat/reflect, gradientTransform, stop alpha and sRGB/linearRGB color interpolation. Default units are objectBoundingBox; userSpaceOnUse is explicit. Object coordinates use the unclipped geometric bounding box, excluding stroke width. The box transform composes outside gradientTransform. Gradient percentages use unit-box dimensions for objectBoundingBox; user-space percentages use the referencing user viewport (viewBox dimensions, or viewport dimensions when viewBox is absent). Radial percentage radius uses the normalized diagonal. Gradient geometry coordinates accept the existing absolute units at 96 ppi. Degenerate object boxes fail explicitly instead of losing a paint.

Local href or xlink:href templates inherit unspecified gradient attributes and stops when the derived gradient has no stops. Derived stops replace the inherited list. Gradient presentation properties, including interpolation and color, inherit from the XML ancestors rather than the href target or the referencing artwork. Reused stop elements retain their declarations and recompute inherited properties in the final gradient's context, following the SVG 2 template-child model; explicit stop properties override that context. This also defines deterministic behavior where SVG 1.1 left template-child styling unspecified. Stop color and opacity default to black and one; they inherit only with explicit inherit. Offsets accept numbers/percentages, clamp to 0..1, then rise to at least the previous offset; repeated offsets retain their discontinuity. Empty gradients paint nothing, single-stop gradients become solid, and coincident linear endpoints or zero radial radius use the final stop. Stop alpha and fill/stroke opacity normalize to RGBA8 with disclosed quantization. Focus coordinates must resolve to the radial center for nonconstant paints.

A clip definition currently contains zero or one supported geometry element, including a compound path with holes. The child's inherited clip-rule controls its interior independently of fill-rule. Fill, stroke and opacity do not affect clip geometry; display none and hidden visibility suppress the child. Empty/hidden clips mask all artwork. Both clipPathUnits modes are supported (default userSpaceOnUse); the object box, clip definition transform and child transform compose in that order. Referencing group transforms apply afterward. Ancestor and descendant clip references intersect through the existing group hierarchy. Definition and clip geometry lengths use absolute/user units; percentage geometry attributes remain unsupported.

Group object boxes include visible and visibility-hidden geometry, excluding display-none descendants, strokes and clipping effects. Curves use their analytic extrema rather than their control hull. Clipping never changes the reported artwork geometry bounds. Local copies remain editable with ordinary vector and clip operations, persist in sessions/snapshots, and export to SVG with supported appearance. Shared template/reference relationships and bounding-box dependence are resolved into independent item-local copies; changing an imported shape later does not automatically resize its copied paint/clip. This normalization is reported as a loss. Keep the source to retain those relationships.

## Editable text and font bindings

Plain `text` elements become editable text frames; nested `tspan` adds retained style ranges and character positions. Supply `font_bindings` on `svg.import`: an array of `{family, font_id, font, weight?, style?}`, where `font` is the complete descriptor returned by `font.import`. Supply the same explicit `font_root` used for that font store. The family is a caller-declared alias for the pinned face; it is not an assertion about a name table. Weight defaults to 400 and accepts 100..900 in steps of 100; style defaults to normal and also accepts italic or oblique. There is no synthetic weight/slant, installed-font lookup or automatic glyph fallback. Only referenced fonts are loaded and retained in the returned document; their bytes and licenses verify before import succeeds. Missing or corrupt resources fail on visibility-hidden text because it still participates in layout. Display-none spans contribute no characters and need no layout font; their declarations and paint references still validate.

`font-family` accepts an ordered list of unescaped quoted names or simple unquoted names. Selection uses the first explicitly bound family with an exact weight/style match, with ASCII case-insensitive family matching. A selected face missing a character fails instead of searching further. At most eight bindings are allowed; duplicate family/weight/style selectors and conflicting descriptors for one font ID fail. Multiple aliases may share one font ID and identical descriptor. An absent matching binding reports `SVG_FONT_NOT_BOUND`; store failures use the existing font diagnostics. Font paths and XML family expressions are not stored in snapshots.

Family, size, weight, style and text-anchor inherit from ancestors and accept explicit inherit. Initial values are serif, 16 user units, normal weight/style and start alignment. Font size supports the existing absolute units, em and percentages relative to the parent's computed size. Plain text without coordinate lists accepts one x/y/dx/dy coordinate each; absolute units, em relative to its size, and percentages relative to the current user viewport are supported. Coordinate lists use the span layout described below. Character rotations and textLength remain unsupported. Position is the alphabetic baseline, then the element and ancestor transforms apply. Start/middle/end use shaped advance, independently of glyph ink bounds. The initial frame width is that advance (minimum 0.001); alignment remains editable inside that frame, so subsequent text edits keep the selected anchor. Off-frame glyph ink remains visible. Source baseline attributes normalize into the item transform; later font/size edits follow the engine's ordinary frame contract.

The text remains Unicode with the existing native shaping and missing-glyph rules. This importer currently requires horizontal left-to-right layout, nonzero fill rule, an alphabetic baseline, no visible stroke and normal/zero letter spacing. textPath and other unsupported text child elements, bidi, text decorations and broader typography fail explicitly. Plain title/desc retain their existing metadata behavior.

SVG 1.x and an omitted version use legacy xml:space handling: default removes line breaks, replaces tabs with spaces, trims and collapses spaces; preserve converts line breaks/tabs to spaces while retaining all spaces. Explicit version 2.0 defaults to replacing line breaks with spaces before collapse. Inherited `white-space:normal` uses that latter behavior; `white-space:pre` preserves spaces but rejects line breaks and tabs because multiline layout and tab stops are not represented. Explicit CSS white-space takes precedence over xml:space. Comments and character references resolve before normalization. These rules are recorded as normalization losses; original XML bytes remain unchanged.

Solid and gradient fills, fill/object/group opacity and geometric clips work on text. Paint and user-space clip coordinates are translated into the new frame's coordinates exactly once. Object-bounding-box effects use full glyph advance cells and scaled font ascent/descent, including space cells, rather than visible ink. Ancestor object boxes include these cells. Ordinary document queries still report the text frame, and text.inspect reports glyph ink. Empty text has no object box and fails nonconstant object-box effects requiring one. Gradient/clip copies retain their existing import-time normalization contract.

Glyphs paint in order as separate paths, including translucent overlaps; item opacity applies once to the assembled text. PNG and snapshots retain text in their source document. SVG export and text_outline produce one path per visible glyph with explicit loss of text editability. This can reach the normal expanded item, geometry or rendering-work limits sooner than merged contours; unsupported expansion fails without partial output. Retain the editable snapshot and pinned font store.

The [text import example](../examples/svg_text_workflow.py) creates an original labeled SVG, imports it, edits its label in a persistent session, exports snapshots/PNG/outlined SVG, compares pixels and verifies exact undo. It requires explicit source font/license paths and a new output directory.

## Editable span ranges

Nested `tspan` and coordinate lists on `text` use one editable frame with
[native character positioning](TEXT_POSITIONING.md). Each DOM text node retains
an initial style range, so ligatures do not cross markup boundaries. Font family,
size, weight/style binding, solid/gradient fill, fill opacity, anchor, visibility
and whitespace use the ordinary embedded CSS cascade and inherited values.
Unbound or missing fonts still fail; descendant spans may supply the only used
font binding without requiring an unused parent family to be bound.

`x`, `y`, `dx` and `dy` accept comma/whitespace-separated length lists bounded by
the existing character ceiling. Absolute units, `em` and percentages resolve in
the declaring element's font and current user viewport. Lists address retained
Unicode scalars across descendants after whitespace normalization and removal of
`display:none` content. Descendant entries override the corresponding ancestor
entry; a shorter child list leaves remaining ancestor entries in effect. Absolute
x/y starts an anchored chunk; relative shifts accumulate and affect following
tail text. Native glyph clusters, coordinate bounds and range-edit rules apply.

Whitespace is normalized across text-node boundaries, preserving the existing
legacy-versus-2.0 rules. Hidden text retains its advances; visibility may be
restored by a descendant. Display-none content is removed from the text and list
addressing, but its syntax and references are still validated. Every span maps
to the owning `item_id` and a half-open `text_range` in Unicode scalars, with its
original byte offset and reuse context. Those ranges describe the imported
revision and do not track later edits. Span XML names, nesting and descriptions
are not retained as document items.

The frame is rebased around its font-cell bounds. All span object-box gradients
use the entire text's font-cell box, per the public
[SVG text paint rules](https://www.w3.org/TR/SVG2/text.html#ObjectBoundingBoxUnitsTextObjects).
Parent text opacity, clips and masks apply to the assembled text. Local reuse,
cloned gradient scopes, mask-source text and atomic SVG insertion share this path.
SVG export remains outlined, with its existing editability loss receipt.

Span transforms, nontrivial span opacity, span clips/masks and isolation still
fail explicitly because they require separate compositing owners. Rotation,
textLength, textPath, unsupported writing modes and differing styles or absolute
positions inside a grapheme also fail. Identically styled text split inside a
grapheme shares one native range to preserve combining behavior. These boundaries
are not silently converted to per-glyph opacity or outlines. W3a.7 has
[fresh full Windows/Linux acceptance](DEVELOPMENT_STATUS.md#w3a7-complete-within-the-span-range-contract)
within this contract, following the plan's requirement for spans representable
by native text ranges.

## Editable mask definitions

`mask` definitions now become top-level nonprinting `mask_source` resources containing ordinary editable shapes, groups and explicitly font-bound single-line text. Source gradients, geometric clips, nested transforms, visibility and opacity retain their established contracts. Forward references and definitions inside mask content are supported. Each definition requires a source ID, and its receipt includes the generated source item ID. Referencing items share that source; editing one source shape changes all owners. Both used and unused source content is validated, including fonts and unsupported elements.

The `mask` presentation attribute or CSS property accepts one literal local `url(#id)` or `none`. Missing, external and wrong-type references fail the complete import. A mask defaults to luminance; `mask-type:alpha` selects alpha interpretation, and the CSS `mask-mode` property supports alpha, luminance and match-source overrides on owners. These properties do not inherit automatically; explicit inherit is supported. CSS mask shorthand resets mask-mode in declaration order and participates in specificity. Mask-mode is a CSS property here, not a recognized XML presentation attribute. Multiple mask layers and other shorthand components fail explicitly.

Style inherits into mask content from its XML ancestors, independently of the referencing artwork. Ancestor transforms, clips, opacity and display are not part of the detached source. The mask element's own opacity and display have no effect; visibility still inherits to painted children and can be overridden there. Mask-type does not inherit unless requested. Source compositing and luminance use encoded sRGB, with the [native f64 mask contract](ARTWORK_MASKS.md) and no grayscale8 intermediate. Explicit linearRGB mask compositing is rejected; declared gradient color interpolation still works.

`maskUnits` controls the rectangular region and defaults to objectBoundingBox. `maskContentUnits` separately controls source artwork and defaults to userSpaceOnUse. Both also accept the other unit mode. Object coordinates use the same unclipped geometry or text font-cell box as other effects, excluding stroke and display-none descendants. A required degenerate box fails explicitly. User coordinates use the referencing element's coordinate system before its transform. Text user coordinates rebase into the editable frame exactly once. Region/content coordinate maps persist independently in the reference; the source keeps its editable coordinates.

Region x/y/width/height accept unitless values and percentages; user-space regions additionally accept the existing absolute units at 96 ppi. Object-box percentages equal their fractional values. User-space region percentages use the referencing user viewport. Changing content units adds a transform and does not establish a new viewport: percentages inside source content, including user-space gradients and text positions, retain the referencing user-viewport basis under the public coordinate rules. Geometry percentage attributes remain unsupported, as for ordinary shapes.

For omitted version and SVG 1.x, absent region coordinates default to -10%/-10%/120%/120%; negative dimensions fail, including on unused masks, and zero dimensions hide the owner. For explicit version 2.0, CSS Masking's region rules apply: when every region attribute is absent, `clip_region:false` retains an unbounded mask field. If any is present, missing attributes use the defaults; zero or negative dimensions hide the owner. This choice is explicit in the document contract, not inferred from a renderer. An unbounded reference exports with version 2.0 and no region attributes. Ordinary finite regions export explicit coordinates and a transformed clip.

Object-box dependence resolves at import time. Later geometry changes do not automatically resize those reference transforms. Shared source edits, linked/unlinked reference edits, disabling, locks, semantic diffs, artboard extraction and durable undo use [the native artwork mask contracts](ARTWORK_MASKS.md). SVG export preserves supported appearance through independent vector source copies and reports losses of shared identity, linkage, unused/disabled state and text editability. Original SVG files are never overwritten.

Opacity masks inside a mask source, mask-definition transforms, images, filters and linear-RGB source compositing remain unsupported; recursive or cyclic source effects therefore fail explicitly before rendering. Nested masks on ordinary parent/child artwork are supported. Source resources share the 256-item, geometry, text and font limits; definitions share the 64-definition limit, and active references obey native coverage, rendering and export-copy budgets.

## Explicit boundaries

Unknown elements/attributes and unsupported content fail the entire import, including content inside hidden groups. There is no partial success or silent element skipping. Image sources beyond the PNG/JPEG contract above, filters, animations, scripts and external stylesheets are not yet supported. Multi-child clip unions, nested clip references and off-center radial focus also remain unsupported. Export currently supports more SVG semantics than import; an exported file containing such features fails on import. Support is bounded by the declared element/property contracts; unsupported semantics return an error.

Standard input is at most 256 KiB and 4096 XML nodes. Explicit `resource_profile: "large_vector"` admits 8 MiB, 65536 XML nodes, 8192 items and 131072 aggregate commands within an 8 MiB snapshot; see [LARGE_VECTOR.md](LARGE_VECTOR.md). XML DTD declarations/markers and processing instructions are rejected; no entity resolver is installed. UTF-8 is required (an optional UTF-8 BOM is retained in the source hash). Local files are opened read-only, checked for regular-file semantics and read with a hard byte cap. Each numeric sequence is bounded to 32768 tokens, each transform list to 64 functions, definitions to 64 and gradient reference chains to 16, and all imported geometry participates in profile-specific limits (standard: 256 items including the root, 16 ancestor levels, 4096 aggregate path commands, coordinate/transform bounds and a 768 KiB snapshot). Rendering retains its separate work/pixel budgets. Cancellation is checked during node traversal and document validation; blocking filesystem reads are not forcefully interrupted.

Failures use `SVG_INVALID` for syntax, `SVG_UNSUPPORTED` for unrepresented SVG semantics, `SVG_IO` for source access and the shared resource/document errors for engine limits. No result document is returned on failure.

## Provenance and verification

The mapping, number/path parser, style handling and coordinate math are original implementations using the public [SVG path specification](https://www.w3.org/TR/SVG11/paths.html), [coordinate specification](https://www.w3.org/TR/SVG2/coords.html), [painting specification](https://www.w3.org/TR/SVG11/painting.html), [gradients and template children](https://www.w3.org/TR/SVG2/pservers.html), [clipping and legacy masks](https://www.w3.org/TR/SVG11/masking.html), [CSS mask interpretation and regions](https://www.w3.org/TR/css-masking-1/), [legacy text and whitespace](https://www.w3.org/TR/SVG11/text.html), [current text rules](https://www.w3.org/TR/SVG2/text.html) and the externally licensed [roxmltree 0.21.1 parser API](https://docs.rs/roxmltree/0.21.1/roxmltree/). No specification sample code or application implementation is copied.

Independent Python tests parse exported XML, solve polynomial extrema, decode PNG bytes, compare exact rectangle pixels and curve extent/area, and verify original-document round trips at multiple scales. Additional checks cover transforms, units, inheritance, group/paint opacity, winding, source hashes and unchanged file bytes, persistent edits/undo/retry through MCP, malformed input and resource boundaries. Full acceptance evidence is recorded in [the implementation report](IMPLEMENTATION.md).

Gradient/clip tests independently evaluate interpolated pixels, linear-light transfer, radial distance, rational alpha, viewBox/object coordinates, exact clipped regions, template resolution and polynomial curve bounds. Export/reimport, copied-reference independence, persistent edits/undo and explicit unresolved-feature failures are exercised. Mask tests additionally verify independent region/content coordinates, rational alpha and luminance, fractional pixel area, analytic curved interiors, sharing and lock protection, definition inheritance, explicitly bound text, versioned region defaults, persistence and scaled export/reimport. Unsupported text layouts and recursive source masks remain explicit errors.

The [shared-mask example](../examples/svg_mask_workflow.py) imports two labeled diagram panels using gradients, a clip and one shared editable mask; it publishes before/after snapshots, PNG and SVG, records a pixel diff and verifies exact undo. Supply explicit font/license paths and a new output directory.

## Stroke patterns

`stroke-dasharray` and `stroke-dashoffset` now resolve through presentation inheritance and inline style into editable local dash controls. Lists use comma/whitespace-separated numbers or supported absolute lengths; `none` clears the pattern. Percentages, relative units, malformed lists and out-of-range values fail, even on unused styles. See [STROKES.md](STROKES.md).
