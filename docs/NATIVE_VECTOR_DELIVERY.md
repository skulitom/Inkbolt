# Editable native vector delivery

Use `format:"native_vector"` with `document.export`, ordinary create-only
publication, pinned saved references or background export jobs. For example,
pass this output object to `document.publish` in an existing workspace:

```json
{"file_name":"drawing.vector","format":"native_vector","scale":1}
```

The artifact is original editable text data with a project-owned header, an
empty prolog and explicit layer, path and artboard records. It has no embedded
snapshot or preview substitute. No program is executed and no external resource
is loaded. This is a native editing format, not a general PostScript/EPS export.
`vector.import` accepts the resulting text independently of its file extension.
See [native import](NATIVE_VECTOR_IMPORT.md) for its separate admission rules.

## Admitted document

Delivery requires an encoded-sRGB vector document with explicit, flat, normal,
fully opaque isolated layers. Each layer must contain at least one path.
Visibility and locks remain separate on layers and paths; normal path opacity
is preserved. Empty layers fail because the verified text consumer discards
them. Nested containers and root paths have no implicit restructuring.

Paths have one explicitly closed contour, nonzero winding, an opaque solid
eight-bit RGB fill, no stroke and straight or cubic segments. Rectangles and
polygons expand to editable paths. Layer and object transforms are baked into
point controls without changing the source document. Other primitives retain
different approximation contracts and require explicit conversion beforehand.

Scene artboards are independent views over the same layer tree. Their names,
rectangles and lock fields are retained, with project-generated distinct UUIDs.
They require zero bleed, no guides and no background. Owned-subtree frames are
unsupported. A document without artboards receives one `Canvas` view matching
its logical viewport. Single-artboard publication selectors are unsupported;
deliver the complete native document.

Names must be nonempty printable ASCII. Layer/artboard strings and path-name
identities use their respective encodings. Spaces, literal underscores,
delimiters, backslashes and initial digits retain their distinction. Ambiguous
identity spellings such as a name consisting of ` x41 ` fail explicitly rather
than changing the name. Duplicate path labels are retained independently of
object IDs. Import generates new engine IDs; keep the snapshot for original IDs.

Resources, text, gradients, masks, clipping, effects, filters, nonnormal blends,
fill opacity, process inks/profiles, selections, channels and variant state are
not admitted. Hidden objects receive the same validation as visible ones.
Descriptive metadata requires an explicit `metadata_policy:{"mode":"strip"}`
when it would otherwise be embedded. No metadata envelope is hidden in the file.

## Units and limits

Source pixels map to points by `72 / resolution_ppi`, with the vertical axis
reversed. The receipt reports this matrix, source resolution, counts, data hash,
implicit-artboard status and losses. Reimport uses 72 pixels per inch and an
origin at the artboard union. Compare physical dimensions and placed controls
when source resolution differs; raw pixel dimensions are not equivalent.

Scale must be 1. Every delivered control/corner is bounded to an absolute 16,383
points, and artboard dimensions and their union have the same size budget.
Output is bounded to 16 MiB and passes the reader's syntax, item and per-path
budgets before it can be published. These are admission limits, not a claim
that every large production scene has completed external fidelity testing.
Cancellation and existing publication, retry and history contracts still apply.

## Verification and remaining scope

Original generated fixtures independently inspect emitted controls, physical
transforms, names and UUIDs; compare every pixel of integer artboards; reject
unsupported states; and exercise CLI/MCP, saved references, durable receipts
and background jobs. Controlled native open/save/reopen comparisons preserve
structure and native pixels, with exact engine pixels after reimport at the
same physical resolution. The build identities, original sources and detailed
external comparisons remain private under the research policy.

External antialiasing, color management and opacity quantization can differ.
Matching controls do not establish cross-application pixel equality. Retain
source documents, snapshots and loss receipts. Empty layers, broader geometry,
complex text/effects/links and complete interchange acceptance remain open;
neither original native interchange checkpoint is newly credited by this subset.
