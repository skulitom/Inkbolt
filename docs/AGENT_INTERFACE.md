# Agent interface v0.1

One UTF-8 JSON request per invocation, at most 1 MiB. Pass a file path or write to stdin. `capabilities` and `schema` are argument shorthands. Stdout contains only the JSON envelope. Bad syntax and unsupported fields return `INVALID_REQUEST`; invalid document invariants return `INVALID_DOCUMENT`; read errors return `IO_ERROR`; excessive input returns `REQUEST_TOO_LARGE`.

| Command | Request fields besides command | Result |
| --- | --- | --- |
| capabilities | none | Implemented commands, limits, explicit unavailable features |
| schema | none | JSON Schema for the request union |
| document.create | id, kind, width, height | Empty document snapshot |
| document.validate | document | The valid document snapshot |

`kind` is `vector` or `raster`. Dimensions are integers in pixels, 1 through 32768 each. IDs are 1 through 128 ASCII letters, digits, dots, hyphens or underscores. Snapshots declare `schema_version: 1` and `color_space: "srgb"`. This color field records intent only; there is no pixel storage or color conversion yet. Snapshots have no content objects or layer arrays in this version.

```json
{"command":"document.create","id":"poster-01","kind":"vector","width":1200,"height":1600}
```

```json
{"command":"document.validate","document":{"schema_version":1,"id":"poster-01","kind":"vector","width":1200,"height":1600,"color_space":"srgb"}}
```

The JSON Schema describes request shape; runtime validation also enforces version, identifier and dimension invariants. There are no mutations, stored state, retry receipts, undo operations, rendering or file imports yet. Do not infer support from the roadmap. In-process callers use `inkbolt::execute` and `inkbolt::validate`.
