# External benchmark drivers and captured trials

The W2 external lifecycle currently supports B01. B02-B20 remain visible as
`not_implemented` until their fixtures/prompts/judges are separated; the baseline
reports B17-B19 as `not_applicable` with engine-specific reasons. This is not a
complete model benchmark or evidence that Inkbolt beats the baseline.

## Configure a client

Keep configuration, transcripts, generated workspaces, tools and reports outside
the repository. A version-1 driver configuration has exactly these fields:

```json
{
  "schema_version": 1,
  "kind": "model",
  "client": {"id": "your-client", "version": "the-exact-client-version"},
  "model": {"id": "the-exact-model-id", "settings": {}},
  "argv": ["C:/Tools/client-adapter.exe"],
  "driver_files": ["C:/Tools/client-adapter.exe"],
  "timeout_seconds": 600
}
```

Use your actual executable paths and complete model settings. Include adapter
scripts/configuration files in `driver_files` so their hashes are checked before
and after execution. `argv[0]` must be an absolute executable file; the launcher
appends one argument, the absolute `evidence/request.json` path. It uses an owned
process tree, a fixed workspace and a deadline; there is no shell interpolation.
The client must enforce the request's tool policy. Process cleanup is not a
filesystem or security sandbox. Credentials come only from the inherited
environment, never configuration, settings or transcripts. Console output is
not retained; the adapter must produce its declared credential-free transcript.

Use `kind:"synthetic"` for any fake/scripted driver. Tests refuse to let the
repository's fake client impersonate a model. Its artifacts and usage can test
the lifecycle but never establish actual model-run completion.

```powershell
python tools/agent_benchmark.py --arm model --driver-config C:/Work/client.json --task B01 --repetitions 5 --output-root C:/Work/model-01 --conditions "Actual machine and load conditions"
```

The model arm builds and pins the release executable. Each request names its
workspace, exact prompt, output paths and MCP configuration (`--tools core`),
and supplies the executable for clients that use the CLI. A portable contract
binds task/repetition, arm, prompt, original fixture hashes, model/settings,
client version and executable/tool identities. The transcript and usage must
refer to this contract. `--transport` selects the reference runner's transport;
external-client reports describe the actual adapter protocol as external.

## Pinned baseline

The no-engine arm uses the same prompt and original font. It does not build,
configure or launch Inkbolt. Provide an external JSON file with exactly `resvg`
and `python` absolute executable paths. The tools must be resvg **0.47.0** and a
Python environment containing Pillow **12.3.0**. Tool executable hashes and a
hash of the installed Pillow distribution files are recorded and rechecked.
Preserve downloaded package licenses; see [dependencies](DEPENDENCIES.md).

```powershell
python tools/agent_benchmark.py --arm baseline --driver-config C:/Work/client.json --baseline-tools C:/Work/baseline-tools.json --task B01 --repetitions 5 --output-root C:/Work/baseline-01 --conditions "Same machine and load conditions"
```

The request supplies only baseline tool identities and no Inkbolt MCP server or
executable. The client must disable other engine tools. B01 delivers editable SVG
and a PNG; its bounded source-judge contract is stated in the shared prompt.
The judge renders with system fonts disabled and only the original named font.
Artifact checks apply to both arms. The Inkbolt snapshot check is explicitly
`not_applicable` for the baseline, never omitted or counted as an artifact pass.

## Client result and observations

Write the requested `driver-result.json` and a separate transcript file in the
requested transcript directory. The result has exactly these fields:

```json
{
  "schema_version": 1,
  "contract_sha256": "copy the request's contract_sha256",
  "kind": "model",
  "client": {"id": "your-client", "version": "the-exact-client-version"},
  "model": {"id": "the-exact-model-id", "settings": {}},
  "transcript": "transcript.jsonl",
  "observations": null
}
```

Client/model/kind must match the request. The harness ignores solver verdicts
and runs the independent judge. Missing observations remain null. When the
client provides observed data, replace null with an object containing
`source:"client_reported"` and any available fields:

- `token_usage`: input/output/cached-input/reasoning token counts, using the keys
  `input_tokens`, `output_tokens`, `cached_input_tokens`, `reasoning_tokens`.
- `model_calls`, `engine_commands`, `request_bytes`, `response_bytes`,
  `invalid_calls`, `retries`: nonnegative integer observations.
- `agent_seconds`: observed nonnegative finite duration.
- `first_preview_seconds` and `first_preview_sha256`: a paired observation. Timing
  is accepted only when those PNG bytes pass the independent artifact judge.

Do not estimate unavailable metrics. External client memory and engine round-trip
timing remain unknown in this lifecycle; judge traffic is retained separately.
Reports preserve failures and distributions of available observations, including
token counts. Retained client reports are evidence, not authenticated attestations.

## Preparation and import

`--prepare-only` writes requests and fixtures without launching the client. It
returns `prepared`, never a task pass. For now, use a configured client adapter
to capture a prepared/external-client session in this protocol. Arbitrary older
client transcript formats require an adapter; automatic format detection and a
manual capture-sealing command are not implemented.

`--import-root C:/Work/model-01` rejudges a captured run into a **new** output
directory with the same arm/configuration/settings. Each `01-B01/` entry contains
`workspace/` plus `evidence/driver-result.json`, the transcript and `capture.json`.
Import verifies the prompt/fixture/tool contract, complete captured workspace,
result and transcript hashes before copying. Links and changed evidence reject.
Original captures stay intact; judge logs and renders are outside solver inputs.

The capture records the original host, driver identity, observed execution and
workspace files. Never relabel a synthetic capture as a model run. Exact content
identity cannot independently authenticate how an external transcript was made.

`actual_model_benchmark_complete` is derived from a complete fixed twenty-task,
at-least-five-repetition model-arm run with retained genuine-client evidence and
unchanged inputs. B01-only runs cannot set it. The remaining adapter migrations,
matched comparison/losing-task report and real owner-run trials remain required.
