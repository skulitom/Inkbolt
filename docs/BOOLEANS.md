# Filled geometry combinations

Exact solver work charges and quadratic root-enclosure precision are listed in
the [limit reference](LIMITS.md). The enclosure policies are also reported in
`capabilities.numerical_limits`; quadratic contact receipts use that same minimum
precision. Enclosure width remains certified by exact rational arithmetic.

See the generated [limit reference](LIMITS.md) for centralized resource ceilings.

`capabilities.booleans.curve_tolerance` and `default_curve_tolerance` report the
accepted range and default from the same constants as validation. The shared
`precision` option selects `auto` (default), `exact` or `tolerance` for both the
read-only command and the atomic edit.

`document.boolean` computes `union`, `intersection`, `difference` or `xor` from 2..16 distinct vector or work-path item `ids` in a supplied `document`. It returns an editable root-coordinate polygonal `geometry` and `fill_rule:nonzero`. An empty region returns `geometry:null` and `empty:true`. This command remains read-only. The `boolean` edit operation computes and adds the result in one atomic edit, with explicit paint and source handling.

Difference means the first operand minus the union of every remaining operand. Intersection requires membership in every operand; xor uses odd membership across operands. Each operand's own nonzero/even-odd rule determines its filled region. Open contours close for this geometric operation. Zero-area spikes and retraced edges contribute no filled region. Item and ancestor transforms place operands in document coordinates; the result is suitable for a root item with identity transform. Results added beneath a transformed parent need an explicit coordinate conversion.

This command combines geometry. Paint, stroke width, visibility, locks, opacity, clips, masks, filters and ancestor appearance do not define its operands. It can inspect locked or hidden source geometry because it does not mutate it. Materializing a result or changing source properties uses the normal edit and lock rules. There is no appearance flattening or live reference to the source items. Results and original operands can coexist in snapshots and sessions; undo of the materializing edit restores the previous document.

## Precision and ellipse conversion

`precision:"auto"` first attempts the existing exact curve certificate, allowing
500,000 charged curve-work units within the unchanged total 2,000,000-unit budget.
On an unresolved curve topology, precision loss, topology error, or a **curve-stage**
resource limit, a positive `curve_tolerance` permits a tolerance fallback. The
receipt reports `certificate:"exact"` or `"tolerance_snap"`, plus the failed stage,
code and attempt work when fallback occurred. Work already spent remains charged.
Input-admission failures and arrangement resource exhaustion do not bypass limits.

`precision:"exact"` preserves the previous strict behavior, including explicit
ellipse-conversion requirements and refusal of uncertified curve deformations.
`precision:"tolerance"` selects approximation directly and requires a positive
tolerance. `auto` with zero tolerance never selects approximation. The tolerance
range remains 0..64 document units and defaults to 0.125.

Automatic and tolerance modes expand each analytic ellipse through the existing
four tangent cubics. `inputs[].primitive_conversion` reports the encoded tangent
coefficient, unit radial deviation, control-construction rounding and an affine
world-space squared error bound. This conversion error is **additional to** curve
flattening, snapping and final rounding. Analytic ellipse contact topology is not
certified by a certificate about its cubic expansion. Source ellipses stay
parametric and unchanged.

For the encoded coefficient `k`, the unit quarter cubic satisfies
`x(t)^2+y(t)^2-1 = u^2*(a+b*u)`, where `u=t*(1-t)`,
`a=9*k*k+6*k-6`, and `b=-2*(3*k-2)^2`. Exact rational evaluation of the endpoint
and interior stationary values bounds radial error (less than 0.000273 in unit
coordinates). The world bound uses the Frobenius norm of the affine radius map
and the actual expanded control rounding. It does not assume an ideal irrational
coefficient or silently round a bound downward.

Tolerance mode reuses exact canonical curve normalization and signed shared
multiplicities, then subdivides with rational de Casteljau arithmetic. The two
interior control differences from the chord's Bernstein controls bound each
input arc's displacement by at most half the requested tolerance. Using rational
arithmetic here strengthens the plan's proposed floating-point flattening step.
Equivalent exact source subdivisions share the same evaluated chords. Bounds
exclude collinear retracing removed by exact filled-winding reduction.

Endpoints snap to the nearest point on one dyadic grid, with spacing at most
`tolerance/8` and ties away from zero. The exact line arrangement evaluates the
snapped operands using their individual fill rules. The receipt reports actual
squared flattening and snapping maxima per input, grid spacing and its squared
snapping bound. Very small regions, gaps or contacts can merge, split or disappear;
**this mode does not preserve source topology**.

The usual output planarity, winding, nesting and adjacency checks still apply.
If f64 rounding cannot retain the arrangement, up to three repairs snap the
computed contour vertices to the same grid and evaluate their nonzero self-union.
Every repair's actual squared displacement is reported, and the final rounding
must stay within `tolerance/8`. The total work, 512-edge, 4,096-atom and depth-20
limits remain enforced; an uncertifiable result still fails without partial
geometry. `area_exact` refers to the final rational arrangement before f64 rounding.

These are separate bounds on input flattening, input snapping, output repair and
output rounding. They do **not** bound the movement of intersection vertices or
the final boolean boundary: nearly parallel intersections can amplify small
input displacements. No analytic-ellipse or original-curve topology guarantee is
implied by an exact arrangement of snapped chords.

The default precision is omitted from serialized edit operations, retaining the
historical request identity for saved session retries. Explicit strict or tolerance
operations have their own identities. Existing strict geometry tests specify
`precision:"exact"`; default behavior is tested separately.

## Atomic editing

Submit this operation through `document.edit` or a session edit action:

```json
{"op":"boolean","ids":["outer","opening"],"new_id":"frame","mode":"difference","fill":[35,100,180,255],"sources":"hide","curve_tolerance":0}
```

`new_id` must be valid and unused, even when the result is empty. `fill` is
required. A nonempty result is an ordinary vector item with identity transform,
nonzero fill rule and no stroke, added after existing root siblings. Geometry is
in document coordinates; source appearance and metadata are not copied. The
ordinary item, paint/resource and scene validation rules apply.

`sources` defaults to `keep`, which can read locked sources. `hide` changes only
their visibility; `remove` deletes the selected operands and clears a removed
background assignment. Both mutation policies check source, ancestor and normal
shared-resource dependent locks. Removal that leaves an invalid reference fails
the entire batch. Other changes caused by explicit source handling, such as a
hidden shared component child, follow the ordinary scene rules.

Empty results add no item; the source policy still applies and a successful edit
advances the revision. Change details report `created`, nullable `result_id`,
`sources` and the same numerical certificates, bounds and losses as the read-only
command, without repeating the geometry. It remains in the resulting document.
The operation uses the same selected precision, ellipse conversion and numerical
certificates as the read-only command. Compound-region operands remain explicitly
unsupported.

Normal atomic batches, revision checks, session proposals, retry receipts and
undo/redo apply. A failure in this or a later operation leaves the saved document
and revision unchanged. One accepted batch creates one undo point. Discover the
complete schema and an executable fragment with
`schema.lookup {name:"operation",select:"boolean"}`.

## Exact numerical model

Rectangle fields are interpreted as exact binary rationals, including endpoint sums and affine mapping; their area does not first incur rounded `x+width` arithmetic. Existing polygon/rounded-shape/path expansion supplies other line/cubic control points. Encoded finite coordinates and the engine's composed f64 world matrix are then treated as exact rationals. Matrix composition itself retains the ordinary engine f64 contract.

`curve_tolerance` is a document-space distance in 0..64, default 0.125. After exact coincidence normalization, rational curve intervals recursively split in half. Intervals ending at supported quadratic parameters choose a rational cut strictly within their central half, keeping both children at most three quarters of the original parameter interval. Refinement continues until the difference from each endpoint chord is bounded by the requested tolerance and the topology certificate below succeeds. The maximum squared length of the exact Bernstein control differences must be at most tolerance squared; the convex-hull property proves this distance bound across the entire interval. Quadratic control differences receive a certified rational upper bound. Each operand reports its maximum accepted squared bound as a rational string. Topology can force more subdivision than distance alone requires. A surviving nonstraight cubic with zero tolerance is unsupported. Exactly cancelled signed curve traversals need no approximation. Maximum subdivision depth is 20.

Noncollinear quadratic and cubic polynomials have an exact canonical parameterization. For `P(t)`, the evaluator forms `P(a+b*u)`: first it translates the parameter to remove one component of the next-to-leading coefficient; then it scales using a nonzero first derivative coefficient, or a second/third coefficient ratio at a stationary point. Under any nonzero affine parameter change, these rational coefficients are identical. Equality uses complete exact coefficient vectors, never distance or epsilon snapping. A collinear cubic reduces to its signed endpoint interval: any forward/backward retracing cancels exactly in filled winding. That reduction preserves filled regions, not a stroked centerline or zero-area traces. Its discarded excursions are not represented by the reported noncollinear chord-deviation bound.

Each canonical polynomial collects signed endpoint events per operand. Internal knots with zero net event disappear, including exact subdivisions, reversed traversal and cancellation. Intervals with constant per-operand multiplicity share one certified polygonal boundary. This makes noncollinear subdivisions within the same operand invariant when their encoded coefficients are exactly equivalent, and aligns exactly coincident portions across operands. Splitting into different operand IDs can change multiplicity-event intervals and is not the same invariant. Changes caused by rounded control points or rounded world-matrix composition remain real differences in this exact input model.

The `curves` summary reports source cubic count, canonical group count, collinear cubic count, removed parameter knots and shared curve runs. Its `topology` entry identifies the completed certificate and reports evaluated arc counts, subdivisions, separated pairs, shared-coordinate pairs and transverse crossings. `algebraic_contacts` reports the root method, distinct discovered contact points and parameter splits; `aligned_splits` counts additional interval alignment. Completely straight or cancelled inputs use `exact_polygon_winding`.

In exact mode, analytic ellipses require explicit `path/convert` first. Automatic and tolerance modes perform the separately reported conversion. Their existing quarter-cubic conversion has its own disclosed error, separate from boolean flattening. The command does not silently include that error in the requested tolerance. Parametric rounded shapes already use their documented cubic outline.

The evaluator splits all flattened edges at exact rational intersections. Collinear overlaps split at their endpoints and accumulate signed per-operand multiplicity. A rational sample in each atomic edge's adjacent face determines winding; signed multiplicity supplies the opposite face's winding. Only edges separating included and excluded faces remain. Exact angular ordering joins them into deterministic closed boundaries with the included face on the left. Contour signs identify outer boundaries and holes, including disconnected and point-touching regions. Redundant collinear vertices are removed only when they are not shared junctions. No epsilon snapping or randomized ordering is used.

The result includes exact rational area before output rounding, a floating convenience area, positive/negative contour counts, source revision, input and boundary edge counts, tolerance evidence, coordinate semantics, work units and explicit losses. Rational vertices round to f64 for the ordinary editable path model. Distinct-vertex identity, planarity, cyclic adjacency, signed winding and contour nesting are checked after rounding. Unrepresentable topology fails with `PRECISION_LOSS`. The exact maximum squared rounding displacement is reported separately; `area_exact` describes the rational arrangement, so rounded path area can differ by the reported coordinate rounding.

## Exact curve topology certificate

Successful strictly certified curved results carry `exact_simultaneous_curve_to_chord_homotopy`. This certifies a continuous simultaneous deformation of the noncollinear input arcs to their chords while preserving the filled boundary arrangement, after exact signed coincidence and collinear-winding reductions. In `exact` mode a failed certificate remains an explicit error. `auto` may use the declared tolerance fallback described above.

Before chord evaluation, original rational polynomial arithmetic locates supported exact contacts. The greatest common divisor of the two coordinate differences finds endpoint preimages; a curve/line cross-product polynomial finds contacts with a straight segment. Curves sharing a nonconstant linear projected coordinate can be compared through an exact affine parameter substitution. For other curve pairs, a fraction-free Sylvester determinant eliminates the second parameter. Roots of that resultant are only candidates: the original two coordinate equations must agree exactly at parameters inside both source intervals. No approximate root or resultant alone establishes a contact.

Linear roots and quadratic roots with rational square discriminant are evaluated directly. Higher-degree polynomials first lose repeated factors through their derivative gcd. Exact Bernstein sign variations bound roots in recursively halved intervals; continued-fraction convergents of interval midpoints supply rational candidates, checked by exact substitution. The rational-root denominator bound can end a search early. Discovery stops at 96 bisections per branch, independently of geometric subdivision depth. It does not assert that every rational or algebraic root has been found: unresolved contacts still need the subsequent topology certificate or fail explicitly. The summary sets `all_algebraic_contacts_located:false`.

Each cubic also receives an exact self-contact check. Dividing its coordinate differences by the trivial parameter difference gives two equations in the sum and product of the two parameters; verified distinct rational solutions become a shared node. A gcd of the coordinate derivatives finds rational stationary points, including cusps. The report distinguishes these `self_contact_points` and `stationary_points` within the distinct discovered points. Ordinary closed endpoints do not count as additional internal self contacts.

When the node's quadratic has irrational roots, its shared world point is still rational. The evaluator checks that identity exactly, groups actual preimages across source arcs, and splits matching rational preimages on other curves or lines. A lone branch without another preimage or contacting item receives no unnecessary algebraic cuts. The separate `quadratic_contacts` summary reports distinct junctions, irrational parameter splits and the initial algebraic arc count. For example, the node visited at `1/2 +/- sqrt(1/8)` can now meet another shape's rational corner without losing either lobe.

These intervals retain exact controls of the form `a+b*sqrt(d)`; they are never replaced by rounded source curves. Monotonicity, control-hull separation, shared-coordinate ordering and transverse predicates use exact signs, including comparisons across two different real quadratic fields. A mixed expression is grouped as `X+Y*sqrt(e)` over the first field; only after checking the signs of `X` and `Y` may comparison of their squares decide its sign. Rational control approximations merely suggest separating directions, each checked again against the exact controls. Every emitted chord endpoint remains rational, preserving the existing exact arrangement and checked output-rounding stages.

Squared chord-deviation bounds use outward rational square-root intervals with at least 128 fractional bits, increased by 16 per geometric depth. Coarse dyadic subdivision candidates are accepted only after exact comparisons place them inside the central half. Neither approximation decides topology. Source control points, documents and media remain unchanged.

Each discovered rational contact becomes a fixed shared endpoint before deformation. Overlapping arcs with a common linear or supported quadratic projected coordinate also align their interval endpoints after refinement. Quadratic matches require complete coefficient equality after an exact affine parameter change; source projection directions survive later refinement and affine placement. This preserves exact coordinate pairing even when the two curves needed different distance subdivisions. All added cuts retain source geometry and signed multiplicities; they are internal evaluation data, not snapshot edits. The same geometric depth, edge and exact-work limits bound this preparation.

Every curved arc must have a nonzero endpoint chord and nonnegative derivative-control projections onto it. This proves strict monotonicity through the arc interior and throughout the deformation, preventing a single arc from folding or collapsing. Straight segments split at their intersections and at curved endpoints that lie on them. Pairwise checks then establish one of these cases:

- Separating control-hull planes prove the two deforming arcs are disjoint or touch only at a fixed shared endpoint. At a touching plane, the reachable face of the entire monotone curve-to-chord family is bounded by its endpoints on that plane; unused control points on the plane do not create a false contact.
- An identical strictly monotone projected coordinate, together with a fixed sign of the perpendicular coordinate difference and a nonzero endpoint difference, proves two arcs remain ordered. This also handles close translated curves whose control hulls overlap.
- For a transverse pair, all derivative-control cross products must have one sign with at least one nonzero value. Both endpoints of each arc must lie outside the other's complete control hull. The difference map then has a nonzero Jacobian in the parameter-square interior and keeps its boundary away from zero throughout the deformation. Its boundary degree equals that of the two endpoint chords, proving exactly zero or one interior intersection for every intermediate shape.

Each curved arc may participate in at most one transverse crossing after refinement. Alongside the pairwise separation and fixed-endpoint checks, this prevents crossings from changing their order or becoming triple contacts during deformation. Uncertain arcs subdivide and all checks repeat. Small loops, holes and disconnected regions cannot disappear merely because their size is below the requested distance tolerance. Output f64 rounding receives the separate arrangement checks described above.

The distance tolerance bounds individual input arcs. It does not bound movement of intersection vertices or the final boolean boundary: nearly parallel intersections can move farther than either input arc's displacement. The certificate concerns filled geometry in the exact encoded world-coordinate model, not renderer coverage, stroke appearance or source metadata. Raster coverage retains the documented f32 backend limits, so very small retained geometry can still disappear in a raster preview.

## Remaining curved-path work

Rational repeated contacts include general cubic pairs with different nonlinear parameterizations, quadratic-projection tangencies, non-dyadic nodes and cusps. Quadratic-parameter nodes now retain their rational world junctions. Exact contact discovery still does not guarantee that the subsequent simultaneous deformation can be certified, and general non-rational fixed world junctions remain unsupported by exact certification. Automatic mode can instead use the declared tolerance model.

For example, take `A(s)=(s,s^2)` and `B(u)=(u+h,u^2+2*u*h)`, with `h=u^2-1/8`. The identity `B_y-B_x^2=-h^2` gives two tangencies at irrational world x coordinates. A supported exact detector verifies a repeated quadratic resultant factor, both source parameters, the common point and parallel nonzero derivatives before promptly returning `CURVE_TOPOLOGY_UNRESOLVED`. It does not mistake an unverified resultant root for a real contact. This original fixture now also passes the independent tolerance-mode membership checks. Other strict unresolved arrangements still refine or fail at their declared limits. The full advanced boolean checkpoint therefore stays **in progress and uncredited**.

## Bounds and agent workflow

Inputs allow at most 512 aggregate source edges (cubics plus nonzero lines, including implicit closure), 512 evaluated topology arcs and aggregate nonzero emitted edges, an arrangement of at most 4,096 atomic edges and 2,000,000 charged exact-work units. The source limit applies before merging equivalent curve pieces. The ordinary document/input/output coordinate and path-command limits apply, along with the subdivision depth. Unrecoverable work/size limits return `RESOURCE_LIMIT`; exact mode refuses unresolved topology at maximum depth with `CURVE_TOPOLOGY_UNRESOLVED`. Automatic mode may recover eligible curve-stage failures through its declared fallback. Failed operations return no partial geometry. Work charges curve normalization, subdivision, exact topology predicates and multiplicity expansion, edge-pair intersection checks, face sampling/winding, traversal and output topology checks.

Contact polynomial arithmetic additionally allows degree at most 18 during elimination products, 4,096 bits per coefficient numerator or denominator, and 512 retained quadratic projection directions. These are bounded discovery resources, not expanded document limits. Exceeding them refuses exact evaluation with `RESOURCE_LIMIT`; automatic mode may select the tolerance fallback. Strict curve certificates remain mandatory in exact mode; tolerance mode reports its separate snapped model. Output-rounding checks remain mandatory in both.

Retained quadratic discriminants, parameters and control coefficients also have a 4,096-bit numerator/denominator limit. Dyadic parameter-cut search allows at most 4,096 fractional bits, using 32 extra root-bound bits when needed to suggest a candidate. Exact field operations and predicates consume the existing work budget; the source, evaluated-arc and geometric-depth limits remain unchanged.

Use the atomic `boolean` operation to combine and materialize in one request. For
read-only inspection, `document.boolean` still returns geometry and numerical
evidence without changing the document. Clients that materialize that response
manually must preserve its revision, handle `geometry:null` explicitly and choose
paint/source edits themselves.

`python examples/boolean_workflow.py C:/absolute/new-directory` constructs an original frame icon, subtracts a rectangular opening and notch, adds the editable result while retaining hidden source rectangles, publishes snapshots/PNG/SVG, and reverses that edit through durable session undo. Independent checks verify analytic area, every output pixel, contour structure and unchanged source geometry.

Ellipse admission and precision selection have [fresh Windows/Linux acceptance](DEVELOPMENT_STATUS.md#ellipse-and-precision-acceptance):
all 276 stages per platform, independent area/membership checks for twenty original
combinations, repeated cross-platform results, strict refusals and durable history.
The original frame-icon example still uses one combination/materialization request
instead of two. Broader model efficiency, retained curve output and the advanced
curved-geometry checkpoint remain separate, open requirements.

For routine precision changes, use focused feedback:

```text
python tools/verify.py --only test_boolean_precision_cli,test_boolean_curves_cli,test_boolean_edit_cli,test_resource_limits
```

Add `test_boolean_ellipses_cli` when changing ellipse admission or its bound, and
use the appropriate `--rust` filter for internal arithmetic. Complete milestone
acceptance uses fresh `--thorough` runs on Windows and Linux.
