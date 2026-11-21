# Separate 50 MP photo evaluation

`python tools/agent_benchmark.py --variant photo-50mp-v1` selects a separate,
fixed B10 task. The default twenty-task suite, original 1920 x 1080 photo,
check IDs and 256 MiB criterion remain unchanged. The large variant never
substitutes for original-suite or unchanged 167-checkpoint acceptance.

The original synthetic source is an 8192 x 6144, unsigned RGBA16 TIFF with
straight alpha and encoded-sRGB interpretation. A standalone integer Rust
generator streams the studio scene into the fixture without engine linkage or
a full-frame Python allocation. The task clones an exact 20 x 16 source region
96 pixels right, crossing four native blocks. All other channels must remain
unchanged. Its separate ceiling is 512 MiB peak commit per engine/tool process.
See the [prompt](../tools/benchmark_prompts/B10-photo-50mp-v1.md) and
[driver contract](BENCHMARK_DRIVER.md).

The engine arm retains import and reviewed-proposal results, editable snapshots,
immutable blocks, exact focused PNG, edited and historical native TIFFs, and
verified undo/redo history. Independent row/block expectations check every
sample, block identity, proposal and saved receipt. External judges publish in
a separate owned workspace with verified resource copies. Capture import works
after the original absolute workspace and session paths disappear. The baseline
keeps an editable native TIFF, the same exact samples and preview; engine-only
checks are explicitly inapplicable. Fixtures and outputs use file streams;
metadata and transcript bounds remain separate.

## Five matched Windows trials

On 21 November 2026, Codex CLI 0.164.0 ran the same 50 MP task five times
with Inkbolt and five times with the no-engine baseline. Both arms used the
externally selected `gpt-6.1-sol` model with medium reasoning, the same host,
prompt, TIFF and frozen source. The five Inkbolt runs preceded the baseline
batch. Desktop and remote-service load could vary. The October pilot is separate.

| Outcome or median per attempt | Inkbolt | No-engine baseline |
| --- | ---: | ---: |
| Accepted TIFF, preview and preserved source | 5/5 | 5/5 |
| Complete applicable workflow | 5/5 | 5/5 |
| Native import, immutable blocks, reviewed edit and history (seven checks) | 7/7 in every trial | Outside baseline scope |
| Input + output tokens, cached input counted once | 654,324 | 79,002 |
| Cached input tokens | 585,344 | 44,416 |
| Agent time | 169.6 s | 68.7 s |
| Largest single-process peak commit in the owned client tree | 58.11 MiB | 44.20 MiB |

The baseline agents used the pinned Python environment and Pillow 12.3.0.
Both arms passed the full-image sample and focused-preview comparisons.
Five successes give a 95% Wilson interval of 56.6%–100% for each arm.
Inkbolt used 8.28 times the median input-plus-output tokens. Its assignment
also required a reviewed proposal, immutable blocks and historical deliveries.
Underlying model-call counts, engine-only traffic and time to the first verified
preview remain unmeasured. The memory row includes the client and its tools.

All five Inkbolt agents used the CLI. In three transcripts, printing the
dry-run result exposed over a million characters of output in one shell
step, including hex-encoded native pixels. The task requires the full review
on disk. Its `proposal` field, needed for the commit, occupied just 359–367
bytes in compact JSON. An agent can read that field and the change summary
from the saved review. [Session proposals](SESSION_PROPOSALS.md)

Prioritize keeping full reviews on disk and returning selected fields to the
agent. Test that change with the same prompt, artifact checks and history checks
before claiming lower cost. This comparison covers one large-photo variant.
The retained set is `b10-large-matched-windows-01`. All ten captured transcripts,
prompts and original TIFF hashes were verified. The comparison report SHA-256 is
`cffd9938f08af39342624b3345b05ab29d58ed3fa741963bfca6ef1ca5c88308`.
[Measured source revision](https://github.com/skulitom/Inkbolt/commit/e4529266b79a07b89dd5f5a7f1711da2dd366a16)

## Linux address-space experiment

Run the original 50 MP reference task with a 512 MiB limit on each Inkbolt
process. The MCP transport uses one server through the edit, independent
judge and shutdown. The CLI transport starts a process for each command.
Use a fresh external output directory for each run.

```sh
python3.11 tools/agent_benchmark.py --variant photo-50mp-v1 --transport mcp \
  --linux-address-space-budget --repetitions 1 --output-root "$HOME/b10-mcp-01" \
  --conditions "Local Linux reference run"
```

Use `--transport cli` for the command-line comparison. In this mode a zero
exit status requires the original TIFF, all edit, artifact and history checks,
clean process exits and a verified 512 MiB limit for every engine process.
The row's `linux_address_space_workflow` records that result. The ordinary
peak-commit score remains in the row's `status` and the report's
`peak_commit_workflow_outcome`. The Linux peak resident measurement is
reported in its own field. Model and baseline arms use their original
measurement contract.

After the last judge response and before closing the server's input, the
MCP run also reads the kernel's `VmPeak`. This measures peak virtual address
space through the observed edit and judge work. The enforced limit continues
through shutdown. [Linux process status fields](https://www.kernel.org/doc/html/latest/filesystems/proc.html)

At [the measured revision](https://github.com/skulitom/Inkbolt/commit/e4529266b79a07b89dd5f5a7f1711da2dd366a16),
both transports passed the bounded experiment on WSL2. They completed the same
14 solve and nine judge commands on the original 8192 × 6144 RGBA16 TIFF.

| Transport | Engine processes | Highest lifetime RSS | Peak virtual size before MCP shutdown |
| --- | ---: | ---: | ---: |
| MCP stdio | 1 | 53.83 MiB | 158.49 MiB |
| JSON CLI | 23 | 48.75 MiB | — |

Every process retained both its soft and hard 512 MiB limits through exit.
The original TIFF, preview, edited and historical TIFFs, and both independent
judge deliveries matched the earlier unrestricted Linux and Windows references
byte for byte. Both rows passed all ten artifact, history and source checks.
The eleventh check requires peak commit, which remains unmeasured on Linux.
The retained runs are `b10-reference-limit-mcp-01` and `b10-reference-limit-cli-01`.

## Focused rendering

The first fixed-size diagnostic completed import and repair but its 20 x 16
preview exceeded the unchanged 90-second command deadline. Tiled previews now
compose only intersecting original-grid tiles, retaining the full scene,
viewport, filter neighborhoods, supersampling and resource verification. Only
the focused output is allocated. Full-scene admission/replay limits still apply;
whole evaluation keeps its original behavior. See [focused previews](FOCUSED_PREVIEWS.md).

The retained failed diagnostic and replay used the same source and saved edit.
The debug replay took 15.804 seconds and 13.24 MiB peak commit, with every
preview pixel matching the independent expected value. Optimized CLI previews
took 0.621 seconds on Windows and 0.273 seconds on Linux in the retained first
pair. These are individual observations under recorded concurrent load, not
latency guarantees or regression-gate statistics.

## Retained target-size evidence, 23 October 2026

| Scope | Outcome | Memory observation |
| --- | --- | --- |
| Windows reference CLI | All eleven checks pass; 14 solve and nine judge commands | 36.04 MiB peak process commit |
| Windows persistent reference MCP, final harness | All eleven checks pass; same full source/history checks | 35.80 MiB peak server commit, including judging |
| Linux reference CLI | Every artifact/history/source check passes; commit-budget check fails explicitly | 49.90 MiB peak process RSS; commit unavailable |
| Linux persistent reference MCP, final harness | Same artifact/history results; commit-budget check fails explicitly | 55.16 MiB peak server RSS; commit unavailable |
| Synthetic external controls | Both arms pass, then pass rejudging after physical relocation | Never counted as model trials |

All four reference runs retain the same original TIFF SHA-256:
`ad7b22173189ea6dd25cad6ce3f4e775242e536e6ee000ef0e2fc63f57e6e793`.
Linux RSS is not substituted for commit; Linux therefore has no complete B10
large-variant pass. The full W4 memory/performance gates remain open.

A genuine matched Windows pilot used externally configured Codex CLI 0.160.0,
`gpt-6.1-sol`, medium reasoning, the existing native sandbox and an explicitly
approved supplied MCP server. No model choice is embedded in Inkbolt or the
benchmark defaults. Each arm ran once. Both pass applicable artifact checks;
the engine arm also passes all seven engine checks. The engine client chose a
reviewed clone patch and its own session IDs/root, rather than reproducing the
scripted reference's retouch call. Transcript review found only the supplied
engine, local shell/file work and image checks; the baseline used its pinned
Python/Pillow environment. Client-written memory claims do not decide acceptance.

| Client-observed metric | Inkbolt arm | Baseline arm |
| --- | ---: | ---: |
| Input tokens | 832,256 | 135,590 |
| Cached input tokens, already included above | 766,720 | 118,144 |
| Output tokens | 5,000 | 5,979 |
| Agent seconds, including client/tool work | 205.995 | 168.878 |
| Largest owned-tree process peak commit | 42.13 MiB | 119.96 MiB |

This single matched pair establishes neither equivalence nor efficiency. It
shows substantial token overhead in the engine arm. Engine traffic, retries,
underlying model-call counts and verified-preview timing remain unknown where
the client did not report them. The comparison has no matching/evidence issues,
but the pilot did not meet the five-repetition threshold.

Two initial pilot attempts stopped before contacting a model because the Codex
adapter refused fixtures over 128 MiB. Those failed preparations remain retained.
The adapter now streams fixture hashes and admits only this variant's fixed TIFF
payload plus 1 MiB; ordinary fixture, metadata, sandbox and approval contracts
remain unchanged. An earlier synthetic control also retained a correct workspace
boundary rejection, fixed by isolating judge publication. Failures were not
converted into successful trials or omitted from the record.

Private evidence roots under the retained agent-readiness workspace:
`b10-large-development-01`, `b10-large-target-windows-cli-01`,
`b10-large-target-windows-mcp-02`, `b10-large-controls-01`,
`b10-large-codex-pilot-01` and `b10-large-evaluation-source-01`.
The Linux cache retains `b10-large-target-linux-cli-02` and
`b10-large-target-linux-mcp-02`. Reports bind original fixtures, prompts,
source-file inventories, optimized binaries, commands and captured transcripts.
The genuine-pilot source fingerprint is
`d6a8015138b1ada27f4d0f99035eb4b13bd497df0cf84ccb985efcf188a87e1e`;
its retained source archive SHA-256 is
`e30ec9d29ab4bc22c7ae46d2b2e43254586421dfe41bdaaab8ed559bce781c14`.

## Full milestone acceptance

Fresh full suites completed on 23 October 2026 against the same 991 source files:
273 stages per platform, with no reuse, failures or pending checks. Windows ran
310 Rust tests and 2,818 Python tests, with 24 explicit skips; Linux ran 276 Rust
tests and 2,791 Python tests, with 51 explicit skips. Formatting, locked build,
all-target warning-denying Clippy, every Rust target and every Python module ran.
The accepted source fingerprint is
`44bf74f5a19ebe83b0d7ece4bff05b860f34068590e6cb311917f1f0e4e3a64a`.

The 26 October audit rechecked source archives, logs, target-size results,
retained client workspaces and physically relocated captures. The Windows build
cache had been removed after the original runs. A locked rebuild from the same
source passed seven fresh focused checks in 127.8 seconds; its executable is
retained with that recovery evidence. Historical full-suite and optimized-trial
build hashes remain distinct from the rebuilt executable. No unrelated suite
was repeated solely for a removed build cache.

Evidence is retained under `b10-large-acceptance-01`, with audit SHA-256
`52c75944afc853c0a7b864cb651561d244a65f6691ddfd4a773e109e029e3f04`.
Only this contract's milestone is accepted. Linux commit evidence, repeated
model comparisons, full W4 acceptance and original checkpoint completion remain
open. The registry stays 163/167.
