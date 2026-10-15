# Repairing rejected request fields

When final typed JSON request conversion fails, `INVALID_REQUEST` includes a
working request in `error.details.schema_lookup`. Run it through the CLI or MCP
dispatcher to inspect the relevant command or definition. Unknown commands point
to the schema index. JSON syntax, duplicate keys, workspace preparation and
engine-semantic errors retain their separate contracts.

For a recognized missing required field, `details.reason` is `missing_field` and
`details.field` names the field. For example, `sample.import` with `storage:{}`
and no workspace reports:

```json
{
  "reason": "missing_field",
  "field": "store_root",
  "schema_lookup": {
    "command": "schema.lookup",
    "name": "sample.import",
    "select": "NativeStore"
  },
  "expected": { "type": "string" }
}
```

Supply the field inside its declared object, or use a workspace when the
[workspace contract](AGENT_WORKSPACE.md) provides that default. In this example,
an explicit store root belongs inside `storage`. A workspace already supplies
that default; diagnostics do not change it. A missing history `limit` still needs
an explicit value.

`field` is a schema-confirmed name, not a JSON instance path. When several
reachable types require that name, the query stays at the command. It does not
guess which array element or variant was wrong. `expected` is optional and only
contains unambiguous compact schema fields; the returned lookup is authoritative
for the complete definition. Other decoding failures use `invalid_arguments`
with a working lookup and no invented missing-field diagnosis.

Hints are generated only after typed rejection. They neither accept invalid
inputs nor add defaults, move revisions, reserve request IDs or write files.
The successful inline request path retains its existing typed conversion and
does not build a discovery schema for diagnostics. Caller values and raw decoder
messages are not reflected into the hint. Advisory error objects are bounded to
2 KiB; MCP framing is separate. Discover the limit and scope under
`capabilities.request_diagnostics`.

Regression coverage exercises the observed storage/session/history
cases, CLI/MCP parity, executable queries, ambiguous names, bounded responses,
workspace defaults, successful repairs and retry preservation. Fresh complete
Windows/Linux checks passed for this implementation. The
[model follow-up](BENCHMARK_RESULTS.md#b10b17b19-at-447bbc2-request-guidance-follow-up)
observed individual repairs alongside persistent workflow failures; it does not
establish the broader W5 efficiency requirement.
