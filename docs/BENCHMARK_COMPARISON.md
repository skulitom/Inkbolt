# Matched model and baseline reports

`tools/compare_agent_benchmarks.py` compares two retained external-arm reports.
It writes a new external `report.json` and an aggregate `summary.md`. It never
runs clients, engines or judges, and refuses an existing output directory.
Keep the complete original trial directories beside their reports.

```powershell
python tools/compare_agent_benchmarks.py --model-report C:/Work/model-01/report.json --baseline-report C:/Work/baseline-01/report.json --output-root C:/Work/comparison-01
```

Run the paired arms with the same candidate, client configuration, model/settings,
machine/load conditions, task selection and repetition count. Record conditions
consistently. Each comparable pair must have the same prompt, original fixture
hashes and task control/consumer identities. Captured trials use their original
solve host, not the host performing the later judgment. Candidate changes,
different conditions/settings, missing requests and incompatible evidence remain
visible matching issues; they cannot produce an efficiency or losing-task signal.

The reader checks report and candidate hashes, retained per-trial results,
request contracts, client results, transcript bytes and captured execution
metadata. Baseline tool identities must declare the pinned versions. Client
usage must agree with its retained result. These checks identify evidence; they
do not authenticate model behavior or rerun artifact judges/full workspace hashes.
Preserve trusted raw captures and the independent judge evidence. Rejudge captures
with the original driver protocol when fresh artifact verification is needed.

## Scores and missing evidence

All twenty task IDs remain visible. Every selected repetition stays in its arm's
denominator, including failed, missing, unimplemented and prepared rows. Missing
checks never pass. A passing row with contradictory checks is rejected. A row
whose retained evidence is invalid cannot score artifact/workflow success; its
untrusted measurements become unknown and its engine checks become unverified.
Failed clients stay in the totals even when no valid transcript was produced.

Artifact success requires every unchanged artifact check plus source preservation.
Engine checks are tallied separately. For example, an engine-history failure can
leave all artifact checks passed while failing the complete workflow. Baseline
engine checks are explicitly not applicable; B17-B19 have no baseline counterpart
at all. B20 shares the pinned video consumer, as described in the
[external-driver contract](BENCHMARK_DRIVER.md); it does not give the baseline
Inkbolt history or typed-handoff credit.

Artifact and workflow rates include their counts and two-sided 95% Wilson score
intervals, calculated from the public [NIST interval formula](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm).
These intervals assume independent Bernoulli trials. Equal results in five
trials are a prioritization signal, not evidence of equivalence; this is not a
multiple-task significance test.

## Fixed comparison policy

Policy version 1 declares these task categories before genuine trials:

| Category | Tasks |
| --- | --- |
| Authoring | B01, B02, B05, B06, B07, B12 |
| Input admission | B04 |
| Scale | B03, B10 |
| Pixel editing | B08, B09, B11 |
| Delivery | B13, B14, B20 |
| Repair | B15, B16 |
| Recovery | B17, B18, B19 |

A losing-task signal requires at least five matched repetitions. It records:

- baseline artifact success greater than or equal to model-arm artifact success;
- model-arm median model-call count or input-plus-output tokens at least twice
  the baseline median, and strictly greater.

Cost comparisons use only pairs where both artifacts succeeded, require at least
five such pairs, and require every relevant observation in those pairs. Unknown
usage cannot become zero or establish an advantage. A zero baseline with positive
model cost gets an explicit zero-baseline flag and a null ratio, never infinity.
Cached-input and reasoning-token counts remain separate because adding them to
input/output totals could double count usage. These descriptive thresholds do
not claim statistical significance or cause, and cannot be tuned on a CLI flag.
The report binds the policy, fixed checks and analysis code hashes.

Every metric includes observed/unknown counts, minimum, maximum, mean, median
and sample standard deviation where defined. Distributions retain all attempts
and a separate artifact-success subset. Metrics include invalid calls, retries,
traffic, verified preview time, reported agent time, measured client execution
time, engine round trips and available memory peaks. No agent time is inferred
from engine or client execution time. Engine, consumer and client-tree memory
keep distinct fields and declared scopes. Engine calls are descriptive costs,
not a model-call efficiency ratio: the baseline naturally has no Inkbolt calls.

## Completion and planning

`actual_model_benchmark_complete` is derived from a complete model-arm inventory
with at least five repetitions, unchanged inputs and retained declared-model
client evidence; judge failures still count as completed trials.
`matched_model_baseline_complete` and `decision_ready` additionally require the
complete matching baseline, including explicit B17-B19 exclusions. Report flags
alone cannot establish these values. Synthetic, mixed, partial or invalid runs
cannot become decision-ready. The separate `matched_cutbolt_comparison` gate
remains false: the no-Inkbolt baseline is not a matched sister-product comparison.

The CLI returns 0 when at least one task meets the matching/repetition threshold
and the global identities agree, including for synthetic controls. It returns 2
for malformed inputs or when matching is not established. Exit 0 is not a model
acceptance flag. Inspect the report's decision and coverage fields.

Review the failure ledger, transcripts and losing categories using W2's decision
table in [the primary plan](../FIX_PLAN.md). An artifact tie alone does not show
whether a history guarantee is useful. Do not change judges after seeing winners.
Publish the permitted genuine-run aggregate and record the motivating task,
expected improvement and remeasurement/stop condition before expanding a major
W3c/W4/W5.2+/W6 workstream. Never publish private transcripts or grant engine
checkpoint credit for benchmark plumbing.

Use `python tools/verify.py --only test_benchmark_comparison` for focused feedback,
and the equivalent WSL selector for portable coverage. The original fabricated
metadata tests cover complete/incomplete inventories, distinct artifact/workflow
scores, losing thresholds, missing observations, invalid evidence and create-only
outputs. They do not execute a model or establish a real success rate.

## Saved-session recovery with Cutbolt

Inkbolt and Cutbolt each recovered the original creation receipt in five of
five trials on Windows x64 and five of five on Arch Linux under WSL2. The test
created an empty 192 × 108 vector document or 25 fps timeline, withheld the
first response and restarted the MCP server. The client used its original
request ID to retrieve the receipt and retry. Both engines rejected a changed
width with the same ID. Each saved project still had its original dimensions
and exactly one creation at revision zero.

The comparison used the native archives from the [Inkbolt 0.84.0 candidate at
`63a78d2`](https://github.com/skulitom/Inkbolt/actions/runs/44848096043) and
[Cutbolt 0.4.0 at `e668c16`](https://github.com/skulitom/Cutbolt/releases/tag/v0.4.0).
The table counts actual JSON-RPC response bytes including framing and every
catalog page. The values matched across the two systems.

| Startup option | Tools | Pages | First page, bytes | Complete catalog, bytes |
| --- | ---: | ---: | ---: | ---: |
| Inkbolt, plain `mcp` | 96 | 12 | 355,139 | 4,119,315 |
| Inkbolt, `--tools core` | 22 | 3 | 26,013 | 86,185 |
| Inkbolt, `--tools essentials` | 10 | 2 | 18,880 | 24,487 |
| Cutbolt, plain `mcp` or `--tools core` | 18 | 1 | 21,198 | 21,198 |

The README's `--tools essentials` setting brings Inkbolt's first page below
Cutbolt's, while its full catalog takes 3,289 more bytes. The six recovery
calls used the core dispatcher and default response format in both engines.
Inkbolt returned 8,343 bytes on Windows and 7,287 on Arch, including the saved
document and workspace resource paths. Cutbolt returned 3,551 bytes on both.
Discovery and handshakes are counted separately in the raw report.

On Ubuntu 22.04 under WSL2, Inkbolt also passed all five trials. The published
Cutbolt binary required glibc 2.39 and could not start on that installation.
Those five startup failures remain in the Ubuntu report. Arch supplied glibc
2.39 and ran the same two Linux executable hashes.

To repeat the comparison, extract both native binaries and supply a new output
directory outside the checkout. The runner alternates the starting engine,
records both server lifetimes and retains the individual request and response
bytes, errors and platform-specific memory observations.

```sh
python tools/compare_session_recovery.py --inkbolt /path/to/inkbolt --cutbolt /path/to/cutbolt --output /path/to/new-results
```

These are scripted calls with known commands. Actual model discovery, creative
workflows and the broader sister-project comparison remain open. The archived
reports have the following SHA-256 digests.

| Environment | Report SHA-256 |
| --- | --- |
| Windows x64 | `b852565c09ecaffc7cc57c4aec735baf4fbf7c9f72943690f43a130081b14245` |
| Arch Linux, WSL2 | `343e48509c5d2baa32a4f24be0a520e714cc5e12f00926d31b2c784bf6a66852` |
| Ubuntu 22.04, WSL2 | `d7160da54582eeb077bc8e94b69b44e4b20dfe5be63ea8f0bf34ee0d619a83e1` |

## Move a placed still and review the original

Inkbolt 0.84.0 and Cutbolt 0.4.0 each passed five of five scripted trials on
Windows x64 and five of five on Arch Linux under WSL2. Both received the same
two PNGs. Each placed a 6 × 4 badge with transparent pixels at (3, 5) on a
32 × 24 patterned background, moved it to (17, 12), then reopened the saved
original revision. All 60 delivered PNG previews matched the independently
calculated RGBA values at every pixel. Both input files retained their hashes.

Inkbolt imported the images, created a document and changed the badge's
transform. Cutbolt compiled a one-frame scene at each position and changed
the clip in a saved timeline. Both clients addressed saved revisions directly.
Cutbolt read the two editable scene files by workspace reference. The judge
also verified that the recipes and compiled media retained their hashes.

| Host and CLI | Calls | Request bytes | Response bytes | First verified preview, seconds | All three previews, seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows · Inkbolt | 7 | 1,543 | 8,882 | 0.160 | 0.262 |
| Windows · Cutbolt | 8 | 2,096 | 5,145 | 0.628 | 1.381 |
| Arch Linux · Inkbolt | 7 | 1,543 | 8,490 | 0.216 | 0.376 |
| Arch Linux · Cutbolt | 8 | 2,096 | 5,145 | 0.476 | 1.041 |

Values are medians of five local trials per row. Each call starts a new CLI
process. Elapsed time includes client file writes, compilation and recording
the replies. The judge decodes the delivered PNGs after timing ends and
matches each one to the bytes observed during the trial. Inkbolt returned its
PNGs in the replies. Cutbolt wrote its PNGs to disk, and the client wrote
1,964 bytes of scene JSON outside the requests. The three PNG files totaled
719 bytes for Inkbolt and 575 for Cutbolt. This workflow measures a scripted
edit with known commands. Model discovery and interaction cost remain open.

To repeat, use the native releases identified in the
[session comparison](#saved-session-recovery-with-cutbolt), supply local FFmpeg
and ffprobe executables, and choose a new output directory outside the checkout.
The runner alternates the first engine and retains the traffic, artworks,
revisions, tool hashes and per-call process memory. Windows counters cover the
CLI process. Linux `wait4` records a high-water mark that includes the pre-exec
footprint and the maximum of reaped descendants.

```sh
python tools/compare_placed_still.py --inkbolt /path/to/inkbolt --cutbolt /path/to/cutbolt --ffmpeg /path/to/ffmpeg --ffprobe /path/to/ffprobe --output /path/to/new-results
```

| Evidence | SHA-256 |
| --- | --- |
| Windows report | `507cd3a8a6042781ce302b317bc49a923ff48ebca3d2638f254092e287012e1a` |
| Arch Linux report | `8070cc8b483e674a9107f9c0e449187f185b60ba02b5044038d2ca2235a50814` |
| Decoded original and historical RGBA bytes | `e69f5b8ece217991a76f9312975fae53150c65b6e9023d4f29c4c80de6da1977` |
| Decoded moved RGBA bytes | `7179693f9b0916765c92815ce94d4e626a5fa2844be7bf7b9549141ec767a255` |

### Run the placement task with a model

The model starts with the two image files, the requested positions and preview
filenames, and a launcher for one native engine. It discovers the commands,
saves two revisions in the same session and draws the earlier revision again
after the move. Both arms use the same task, driver configuration and deadline.
The engine name in the launch instructions changes between arms. Supply the
model and reasoning settings in the [external driver configuration](BENCHMARK_DRIVER.md).

```sh
python tools/run_placed_still_models.py --driver-config /path/to/driver.json --inkbolt /path/to/inkbolt --cutbolt /path/to/cutbolt --ffmpeg /path/to/ffmpeg --ffprobe /path/to/ffprobe --output /path/to/new-capture
python tools/judge_placed_still_models.py --capture /path/to/new-capture --inkbolt /path/to/inkbolt --cutbolt /path/to/cutbolt --ffmpeg /path/to/ffmpeg --ffprobe /path/to/ffprobe --output /path/to/new-judgment.json
```

Collection alternates the starting engine in five sequential pairs by default.
The recorder runs inside the client's workspace and retains native CLI
arguments, JSON inputs, stdout, stderr and exit status. Repetition counts a
second identical parsed JSON request or an identical invocation with the same
non-JSON input. A repeated read of an unchanged schema counts here. Failed
commands and unfinished calls have separate fields. CLI stdout is the full
native reply. For the Codex driver the judge also counts completed shell
commands, the output returned in those events and client-reported tokens.
One shell command can issue several native calls or trim their output.

The judge checks the captured file hashes and compares each delivered PNG
against the pixel oracle. It then uses the pinned engine to reopen the
declared original revision, the moved revision and the current session head.
A passing delivery must keep the two input files intact. The first-preview
measurement requires a matching filename and SHA-256 at a completed client
event. The report also records when the CLI trace shows a successful render of
the original saved revision after the move with bytes matching `historical.png`.
Rejudging a capture uses a new output file and does not call the model.
