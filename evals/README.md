# Plugin evals

Cases for `claude plugin eval`, with every Inkbolt tool answered by the mock in `mocks/inkbolt/`. The mock's
`_tools.json` is v0.82.0's real `tools/list` with `--tools core`.

Each run starts in an empty folder, while the mock describes the project's files. So keep Claude's own file tools
out of the runs:

```text
claude plugin eval . --no-publish --disallow-tools Glob Grep Read
```

`app-icon`, `recolor-logo` and `readme-diagram` should use Inkbolt. `trim-video-not-graphics` should not.
