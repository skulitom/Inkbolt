# Essentials catalog: matched evaluation at 81e8830

The smaller catalog preserved correctness in this evaluation, but its token
results were mixed. Across five attempts per task, `essentials` used **12.8%
fewer median input-plus-output tokens for B03 layout editing** and **13.3% more
for B16 text repair** than `core`. Both catalog modes and the no-engine baseline
passed every applicable check. This does not establish a general efficiency gain
or complete W5 acceptance.

## Setup and retained scope

The 26 October 2026 evaluation used source commit
`81e883070cbec67dab40cd76b5fcd7845d5a25e2` on the same Windows x86-64 desktop.
The externally configured client was Codex CLI 0.160.0, model `gpt-6.1-sol`,
with `reasoning_effort: medium`. These identify this evaluation; the engine has
no required model and the driver has no model default or fallback.

The plan, source archive, settings and tool identities were recorded before
execution. A one-attempt pilot covered both tasks in both arms. All four pilot
attempts passed and remain separate from the repeated batches. The repeated
batches ran sequentially: ten `essentials` engine attempts, ten no-engine
attempts, then ten `core` engine attempts. Task order rotated within each batch.
The only configuration difference between the engine batches was the explicit
catalog value. Their source, executable, client, settings, task prompts and
fixture identities match. No prompt, judge or setting changed after outcomes.

This was a shared interactive host, with no concurrent Inkbolt verification or
second benchmark client. Other host activity was not isolated, caches could be
warm, and batch order was not randomized. The no-engine baseline used pinned
resvg 0.47.0 and Pillow 12.3.0 with its external Python environment.

[B03](../tools/benchmark_prompts/B03.md) moves one of 5,000 editable rectangles
and checks every output pixel; Inkbolt also has to retain the original revision
and verify history. [B16](../tools/benchmark_prompts/B16.md) diagnoses text
overflow, changes only the frame width and delivers the exact repaired image.
Inkbolt additionally has to retain its reviewed proposal, committed revisions
and durable publication receipt. Baseline engine-only checks are not applicable.

## Results

Tokens are observed input plus output, including cached input once. Cached-input
and reasoning counts are not added again. These are not billing ratios. Seconds
are median measured client execution, including startup and tool work.

| Task | Configuration | Artifact passes | Applicable workflow passes | Median tokens | Token range | Median seconds |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| B03 | Essentials | 5/5 | 5/5 | 296,450 | 242,181-329,322 | 74.75 |
| B03 | Core | 5/5 | 5/5 | 339,972 | 252,799-411,416 | 80.80 |
| B03 | No-engine baseline | 5/5 | 5/5 | 69,288 | 63,129-82,101 | 37.48 |
| B16 | Essentials | 5/5 | 5/5 | 588,300 | 456,983-677,439 | 120.36 |
| B16 | Core | 5/5 | 5/5 | 519,217 | 475,298-585,892 | 113.30 |
| B16 | No-engine baseline | 5/5 | 5/5 | 129,553 | 98,332-167,609 | 74.19 |

Each 5/5 success rate has a 95% Wilson interval of approximately 56.6%-100%,
under the independent-trial assumption. The small samples do not prove
equivalence, a causal catalog effect or performance on other tasks/models.

The unchanged [comparison policy](BENCHMARK_COMPARISON.md) accepts the matched
essentials/baseline pairs without identity issues. Essentials uses **4.28x**
baseline median tokens on B03 and **4.54x** on B16. Both retain the policy's
losing-task signal for shared artifacts and token cost. The core/essentials
contrast is a separate descriptive comparison with the catalog difference
explicitly audited; it is not a second matched-baseline report.

All 34 attempts, including the four pilots, retain their transcripts, results
and captured workspaces. Every retained workspace still matches its captured
inventory. Recovered command failures remain in the transcripts; no attempt was
discarded. Independent judges reopen artifacts and history instead of trusting
the agent's success message.

## What the traces establish

All twenty repeated engine attempts chose the CLI; their transcripts contain
**zero MCP tool-call events**, despite the selected MCP server configuration.
The captured client events do not expose the complete initial model context.
These results therefore do not isolate MCP transport or catalog exposure.
Underlying model-call counts, complete engine-call/traffic counts and time to
first verified preview remain unknown. Client-process memory is retained with
its own scope and does not establish engine-only memory performance.

Repeated command-line schema and capability queries remain visible in text
repair. Some attempts searched large capability reports for font/workspace
defaults. One high-token core layout attempt printed the entire one-line source
file. These observations identify further investigation targets; they do not
attribute a particular number of tokens to any one query.

Keep the optional ten-tool catalog and its verified byte budget. Pause further
schema deferral: this batch does not demonstrate a consistent task-efficiency
benefit. The next bounded W5 investigation should target CLI examples and
focused access to the font/workspace information actually requested in B16.
Record that hypothesis before implementation, rerun the affected matched task,
and stop expansion if correctness drops or additional lookups erase the benefit.
The subsequent [focused-example evaluation](BENCHMARK_CLI_EXAMPLES.md) completes
that bounded B16 follow-up and records its remaining overhead separately.
An MCP-specific evaluation needs a separately declared transport setup; these
trials must not be relabeled. Full-suite model acceptance, missing metrics,
smaller-model follow-ups and the sister-project comparison remain open.

## Evidence identities

The 991-file source archive matches candidate fingerprint
`4284bb09f25c3d8e2703b00dd9df108fce38eab6fc14e20b2a049b21c839504a`.
The retained optimized Windows executable is
`99217c10b0af47e515b4cd2d76adad169c7f819409ca4b1eec6a2e3f1885bc32`.
The evaluation plan SHA-256 is
`9b34e71a1f02127a5e2360dc0d3ad6118c1a9518a4ab395bd3e8abf802881201`.

| Retained report | SHA-256 |
| --- | --- |
| Essentials engine | `8badbca659e6695a064b7c40ea57a59b39b465e00344fd4cf4823e0c75129f88` |
| No-engine baseline | `aa2e07d2b18c80335bbe5c26d5d25c132b2e55371da79a71dac4e16361818418` |
| Core engine | `5eb520554eece7400429e968933e1b7d5137be130a046603db9456710158e182` |
| Essentials/baseline comparison | `1a769d1d5692336a7f5fc1b51cf96f58b864557ca24b447647f9a66bae9a083f` |
| Source, configuration and capture audit | `367d5f10280bf71f35297927e1b559a6c1cfed4c9fda753b2ab0b94c06a315f2` |

Hashes establish retained identity, not authenticated model behavior. The two
selected tasks leave `actual_model_benchmark_complete` and `decision_ready`
false. No original engine checkpoint or whole-goal completion is awarded.
