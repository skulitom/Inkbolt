# Explicit source ink bindings

Native inspection and native PDF preparation accept an optional `ink_bindings`
list. Each entry deliberately interprets a retained source spot as one declared
root destination spot:

```json
{
  "object_path": ["placed", "inner"],
  "source_spot": "source_ink",
  "target_spot": "shared_ink"
}
```

Pass the list in `document.prepress.options` or `pdf_options.prepress` alongside
the required output profile. Every path element is a retained object ID in the
current source document; ordinary parent groups and artboard IDs are not path
elements. Paths contain one to four IDs. Source and target IDs must name direct
spot declarations; process colours and tint declarations are not binding
endpoints. Paints using tint aliases of a bound base spot retain their exact tint
multiplication. At most 1,024 bindings are accepted. Duplicate source paths/spot
pairs are errors, including identical duplicates.

The source snapshot stays unchanged. A binding changes how this print operation
interprets its source ink, using the destination's identity, name and alternate
colour. Different source alternates are allowed because the caller explicitly
selects the destination ink. This is not a colour conversion or an inference
from matching display names. Unbound inks retain their independent identities
under the [native object contract](NATIVE_OBJECTS.md).

Bindings resolve before source composition, filtering and channel-budget checks.
If two source spots target the same destination, their paints address one channel
in their original order. Overprint, knockout, blending and filtering therefore
operate on the shared ink. Adding separately flattened source plates would not
produce the same result. Nested objects preserve their isolated source boundary;
binding an ink does not make the object pass through its parent's backdrop.
Bound named-noise operations use destination identity; unbound noise identity is
unchanged.

Validation checks the original complete source tree before page selection and
never reads a linked external source. Missing paths, non-object path elements,
missing declarations and non-spot endpoints return `INVALID_INK_BINDING`.
Valid hidden, unused or unselected sources may be bound: their per-page receipt
reports `applied: false`. `applied: true` means the route was used by the prepared
ink plan, even if later masks, opacity or zero tint leave no visible amount.

`coverage_sources.ink_bindings` records each original object path, source spot,
source name/alternate, target spot, destination name/alternate and applied state.
Receipts use deterministic path/spot order. Object `spot_mapping` entries for a
bound surface channel identify `target_spot` and set `source_id` to null because
multiple source declarations may share it; the root binding receipt lists those
original declarations. Unbound entries keep their existing source IDs. PDF page
receipts share the same mapping, and colourant names use the destination ID.

Bindings are export/inspection options, not edits to retained documents or
session history. The same bindings can be used after source replacement, undo or
redo; they are validated against that revision. Existing cancellation, resource
limits and create-only publication apply. The 28-spot bound counts effective
channels after binding. Other bounds, including the 32-visible-object limit,
remain unchanged.

`tests/test_native_bindings_cli.py` verifies independent ordered ink equations,
all native blends/overprint policies, nested aliases, all filter families, stable
noise, inverse reconstruction, page selection, malformed requests, limits,
source/PDF identity and durable agent workflows. Bindings cannot cross an explicit HDR view boundary (`INVALID_INK_BINDING`); see [NATIVE_CONTEXTS.md](NATIVE_CONTEXTS.md). The explicit native adjustment policy preserves bound spot amounts; see [NATIVE_ADJUSTMENTS.md](NATIVE_ADJUSTMENTS.md). Registry status governs checkpoint credit.
