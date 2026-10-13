# Local Codex evaluation driver

`tools/benchmark_codex_driver.py` connects an installed Codex CLI to the
[external benchmark lifecycle](BENCHMARK_DRIVER.md). It is evaluation tooling;
Inkbolt itself has no model dependency. All model IDs and reasoning settings
come from external per-run configuration. There is no default model, model list
or automatic fallback. Use exactly the same configuration for both arms.

An external driver configuration uses the existing version-1 contract:

```json
{
  "schema_version": 1,
  "kind": "model",
  "client": {"id": "codex-cli", "version": "your-installed-version"},
  "model": {"id": "your-evaluation-model", "settings": {"reasoning_effort": "medium"}},
  "argv": ["C:/Tools/python.exe", "C:/Work/Inkbolt/tools/benchmark_codex_driver.py", "--client-executable", "C:/Tools/codex.exe"],
  "driver_files": ["C:/Work/Inkbolt/tools/benchmark_codex_driver.py", "C:/Tools/codex.exe"],
  "timeout_seconds": 600
}
```

Replace every path and the client/model values. Use the actual executable rather
than a shell wrapper. The harness hashes the launcher and declared driver files;
the adapter additionally checks the client's reported version. It accepts exactly
`reasoning_effort` in model settings and refuses unknown settings rather than
silently ignoring them. Supported values depend on the chosen model/client.
An unavailable model or client failure remains a failed attempt.

The adapter uses the client's existing sign-in without reading or copying
credentials. It starts a fresh ephemeral execution with user configuration and
host skill discovery excluded, workspace writes allowed, and approvals disabled
for this unattended evaluation. It does not bypass the client's sandbox or
managed policy. Apps, plugins, browser/computer tools, image generation,
delegation, memory, goals and skill search are disabled for the child execution.
Web search is disabled. Project instruction loading is bounded to zero bytes so
the run receives the task and tools instead of unrelated development instructions.
The only configured MCP server is the supplied, required Inkbolt core server in
the model arm. Bridge tasks receive their harness-owned bridge instead. The
baseline receives the pinned image tools and no Inkbolt executable/server.
On Windows, the child explicitly selects the provisioned `elevated` native
sandbox, since ignoring user configuration also removes that selection. Missing
sandbox setup remains an environment failure; this adapter does not provision
accounts, change host settings or fall back to unsandboxed execution.

These controls define the evaluation environment; they are not a proof that an
arbitrary model obeyed every instruction or that shell reads are isolated from
the whole host. Review transcripts for tool-policy violations before making
comparative claims. Always launch this adapter through `agent_benchmark.py` so
the existing process-tree containment and timeout cover all client children.

The external `codex-events.jsonl` retains the exact submitted prompt, argument
array and request identity, followed by raw client JSON events. Ordinary stderr
is discarded. A successful client must exit zero and emit exactly one completed
turn without a failure/error event. Its final message never supplies a verdict;
the independent artifact judge still decides success.

Input, output, cached-input and reasoning tokens are retained only when the
completion event reports them. Missing usage stays unknown. A completed agent
turn is not an underlying model-call count: model calls, engine traffic, retries
and preview timing stay unknown unless separately observed by the harness.
Wall duration is observed; it includes client startup and tool work. Failed runs
retain their emitted transcript but never receive a successful driver result.

The interface follows the public [non-interactive client contract](https://learn.chatgpt.com/docs/non-interactive-mode)
and [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
Actual evaluations require a compatible installed CLI and model access; synthetic
unit events only test adaptation and cannot establish model performance.
