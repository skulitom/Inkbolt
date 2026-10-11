# Editable native vector import

`vector.import` reads one local native vector source without modifying it. The
returned `document` contains editable geometry, flat layers and shared scene
artboards. Import requires a deliberate color interpretation:

```json
{"command":"vector.import","id":"drawing","source_path":"drawing.vector","color_policy":"encoded_srgb"}
```

The source's extension is immaterial. Workspace-relative paths, cancellation and
the ordinary `standard` or explicit `large_vector` resource profile apply.
Import returns a snapshot; use `session.create` to start durable editing.
The receipt identifies source and decoded bytes, source-to-document coordinates,
generated object IDs, names, counts and explicit losses. It writes no files.

Editable text requires declared creator major 30 and file format 14.0.
The alternative admitted container has a classic PDF cross-reference table and one reachable
editable data container, with container version 12, roundtrip version 24 and
creator version 30. Numbered blocks are joined in numeric order; an absent count
admits only the single first block, with undeclared extra blocks rejected. Uncompressed
data and one Zstandard frame are supported; selected PDF block streams can be
unfiltered or Flate encoded. Compression completion, checksums when present,
declared sizes, object boundaries, reference cycles and metadata agreement are
checked. Preview pages are never interpreted as editable artwork. Their count
can differ from the native artboard count.

The geometry subset comprises named flat layers and closed, filled paths with
straight or cubic segments. Source controls remain in native point coordinates.
A shared layer transform converts the vertical axis and translates the artboard
union to the document origin at 72 pixels per inch. Artboards remain independent
scene views over the same editable objects. Visibility, locking and normal
opacity are retained separately. Literal ASCII labels support escaped delimiters
and octal bytes. Path-name identities decode their distinct space and ASCII
escape spelling; a layer's separate data identity never replaces its display
label. Unmapped wide escapes fail. Artboards belong to the recorded document
dictionary and require distinct UUIDs with valid syntax. RGB values must resolve to eight-bit channels; fractional values
are rejected rather than rounded away.

`encoded_srgb` declares the caller's interpretation of RGB numbers. Source
profiles and application color-management settings are not imported. Unused
setup resources, display settings and export preferences stay in the source;
this data interpreter executes no programs and loads no external resources.
Unknown artwork operators and object properties fail explicitly. Matching
geometry does not establish identical external curve antialiasing or opacity
quantization. Keep the original source and the returned loss report.

Nested layers, groups, open/stroked/compound paths, text, linked or embedded
images, gradients, effects, clipping, nondefault blending/winding, nonzero bleed,
nondefault artboard display colors, non-ASCII labels and scaled canvases are not
yet admitted. Other creator/container versions, incremental/encrypted PDF,
cross-reference streams, external block streams and filter parameters also fail.
Limits are 16 MiB each for source and decoded data, 256 native blocks, 4,096 PDF
objects, 32 pages/artboards and bounded syntax depth and token counts. Existing
document, per-path, snapshot and rendering budgets remain independent.

Original generated fixtures check direct editable controls, every pixel of
integer rectangles, two shared views, compression/framing failures, source
preservation, saved retry/undo and create-only delivery. Controlled external
source comparisons are retained privately under the research policy.

[Native delivery](NATIVE_VECTOR_DELIVERY.md) writes an admitted editable-text
subset through the ordinary export/publication path. The original basic
layer/path/artboard requirement is [independently verified](NATIVE_VECTOR_ACCEPTANCE.md).
Extended native interoperability remains in progress. Existing snapshot, SVG,
PDF and image delivery use their own published contracts.

The original PDF data reader follows the public
[PDF specification archive](https://pdfa.org/resource/pdf-specification-archive/).
Zstandard framing follows [RFC 8878](https://www.rfc-editor.org/rfc/rfc8878.html),
using the pinned external decoder described in [dependencies](DEPENDENCIES.md).
