# Recorded agent evaluation results

Two five-pair B02 evaluations are recorded below. The first-page discovery
change preserved artifact success but did not meet its token-reduction target.
The follow-up also exposed client approval refusals. A separate setup pilot below
verified an explicit external configuration that permits MCP publication.

## B02 at c7d9f30: initial five matched icon-sheet trials

Both arms passed all five B02 artifact trials. Inkbolt's median reported
input-plus-output usage was **8.60 times** the baseline's, and median client
execution took **159.0 seconds versus 49.7 seconds**. This is a task-specific
prioritization signal under the fixed [comparison policy](BENCHMARK_COMPARISON.md),
not full-suite acceptance or a finding of statistical equivalence.

### Conditions and scope

These ten genuine trials used commit
`c7d9f30769d6be3a1aff2ad88c7cb87a21668733` on the same Windows 10.0.26200
x86-64 host with a Ryzen 9 7950X3D and 32 logical CPUs. The source candidate,
prompt, checks, client, model and settings stayed unchanged throughout. The
five Inkbolt trials ran first, followed by the five baseline trials, sequentially
on a shared development host with no concurrent local engine verification or
benchmarks. OS caches could be warm; execution order was not randomized.

The externally configured client was Codex CLI 0.160.0, with model
`gpt-6.1-sol` and `reasoning_effort: medium` in both arms. These names record this
evaluation; Inkbolt and the harness have no model default, allowlist or fallback.
See the [configurable client adapter](BENCHMARK_CODEX.md).

[B02's original synthetic task](../tools/benchmark_prompts/B02.md) asks for three
aligned rectangular icons, three independent artboard exports, prescribed exact
pixels and editable source. It measures a small structured authoring workflow,
not artistic quality. The baseline used pinned resvg 0.47.0 and Pillow 12.3.0
through an external Python 3.11 environment. Its editable delivery was SVG;
the Inkbolt arm also had to provide a valid native snapshot. Independent judges
checked the delivered files. No prompt or judge changed between these arms.

### Outcomes

| Measurement | Inkbolt arm | No-Inkbolt baseline |
| --- | ---: | ---: |
| Retained attempts | 5 | 5 |
| Artifact success | 5/5 | 5/5 |
| Complete applicable workflow | 5/5 | 5/5 |
| Native editable-source check | 5/5 | Not applicable |
| 95% Wilson interval for artifact success | 56.6%-100% | 56.6%-100% |
| Median input + output tokens | 487,207 | 56,624 |
| Input + output token range | 374,064-568,364 | 43,367-71,575 |
| Median client execution, seconds | 159.0 | 49.7 |
| Client execution range, seconds | 132.0-169.5 | 45.2-52.6 |
| Median cached input tokens, reported separately | 428,544 | 39,424 |

All ten attempts remain in the denominators. Token and execution-time observations
exist for every attempt. Input totals include cached context; cached-input and
reasoning counts are not added again. The token ratio is **not a billing ratio**.
Client execution includes startup and tool work; it is not engine-only latency.
Underlying model-call counts, complete engine-call/traffic counts, retries and
time to first verified preview remain unknown. Client-tree memory was observed
separately and does not establish engine-only memory performance.

The fixed policy flags both the artifact-success tie and the greater-than-2x
token ratio. Five trials give a wide success interval and cannot establish
equivalence, general model performance or a cause for the difference. Earlier
one-pair pilots, including the smaller-model failure, remain separate retained
evidence and are excluded from these five-pair aggregates.

### What changes next

The recorded commands show all five Inkbolt trials using CLI discovery, with
5-10 shell events containing schema lookups per trial and an unsuccessful CLI
help attempt in each. Those events are not underlying model-call counts. A
separate probe of the same executable confirms that neither `inkbolt_schema_lookup`
nor `inkbolt_run` appears on the first eight-tool compact MCP page. This suggests
an entry-point discovery problem; it does not prove that the client ignored
pagination or that pagination caused the token difference. Baseline commands
used the supplied image tools. Transcript review found no repository/judge reads,
other model use or prohibited engine use in these ten trials.

Prioritize a bounded W5.2 change that makes schema lookup and the general command
dispatcher visible on the first compact page. Preserve the catalog byte ceiling,
complete tool inventory and execution semantics. Then repeat five matched B02
trials per arm with the same client/model/settings and unchanged task/checks.
The expected benefit is fewer discovery workarounds and lower context usage,
while retaining 5/5 artifact and applicable workflow success. If discovery and
usage do not improve, reassess this hypothesis before expanding that workstream.

The other nineteen task IDs, further smaller-model trials and matched sister-engine
comparisons remain open. `actual_model_benchmark_complete`,
`matched_model_baseline_complete`, `decision_ready` and
`matched_cutbolt_comparison` are all false. No engine checkpoint credit changes.

### Evidence identities

Raw transcripts, original workspaces, per-trial results and full aggregate reports
remain external. These SHA-256 identities bind the published summary to them:

| Evidence | SHA-256 |
| --- | --- |
| Source candidate | `abdfa023c342ea73d4cd9c0b39e2806e54ba5624099559dfcdd3045b5fdcf413` |
| Inkbolt release executable | `cb5bc72591bf60ada097a698dc2835bbd70ca54ae12a9b09a4f109c153d453af` |
| Shared B02 prompt | `0911714f1c4f869bdf33ebebd9eb7d207e9ceea7c11a88046a7e18ddfbe6f67e` |
| Fixed comparison policy | `17355cd7d79018d710679efbaae7a91964b701a34be601c6eca4cceab2d2212c` |
| Inkbolt-arm report | `8cea5964bc2190d285695ea00240c0afe9994517fadab10fecf99054fbc1f20d` |
| Baseline-arm report | `1628ac44fc37b36d33f06e62c4257192d624aa5a15fa4c2b65d6d2ee6b4195de` |
| Matched comparison report | `2005145ec9ff99fab67619fa2408ebe1aaf5a77ccc78d48d7c0e00f2f4980a29` |
| First-page runtime probe | `1f08a9ebcfd082a1d748a5869747d8017bad827c1306f06a4467b7c1e7425849` |

## B02 at 9909329: first-page discovery follow-up

Commit `9909329f034b5458d984a96be4309445b2cac6a4` exposes schema lookup and
the general dispatcher on the first compact page. Five new genuine trials per
arm used the same external client/model/settings, prompt, judges and pinned
baseline tools as the initial evaluation. Both arms used the unchanged candidate
below, on the same host, sequentially with Inkbolt first and baseline second.
There were no concurrent local engine tests or benchmarks; OS caches could be
warm. The two evaluations were separate runs, not randomized paired observations
of the old and new engine revisions.

| Measurement | Inkbolt arm | No-Inkbolt baseline |
| --- | ---: | ---: |
| Retained attempts | 5 | 5 |
| Artifact success | 5/5 | 5/5 |
| Complete applicable workflow | 5/5 | 5/5 |
| Native editable-source check | 5/5 | Not applicable |
| 95% Wilson interval for artifact success | 56.6%-100% | 56.6%-100% |
| Median input + output tokens | 564,296 | 41,249 |
| Input + output token range | 420,520-636,076 | 40,913-56,432 |
| Median client execution, seconds | 123.0 | 42.4 |
| Client execution range, seconds | 97.3-135.9 | 38.1-49.4 |

Every attempt passed, with observed usage and execution time. The fixed policy
again flags the artifact tie and excessive token usage: **13.68x** the baseline
median. Inkbolt's token median increased from 487,207 to 564,296. Its execution
median decreased from 159.0 to 123.0 seconds, but this small sequential sample
does not isolate the cause or establish a general speed improvement. The same
unknown metrics and billing/memory limitations stated above apply. Full-suite,
matched-baseline and sister-comparison completion gates remain false.

All five Inkbolt trials now used MCP, with 15-21 recorded MCP call items each,
and all still used the CLI. Every trial received an invalid-operation response
after attempting a document-wide item index in the sibling-stack reorder
operation. In addition, every trial's dispatcher publication attempt was refused
by the evaluation client because tool approval was required while its unattended
approval policy was `never`: nine such refusals across five trials. These are
client refusals before engine execution, not nine failed engine publications.
Recorded MCP items are not underlying model-call counts or a complete count of
engine calls across both transports. Transcript review found only the supplied
engine/image tools and task/workspace reads, with no repository/judge reads.

The first-page change made the entry points usable for discovery, but the
predeclared token target was not met. Keep the result and stop broader interface
expansion pending a focused check of the evaluation client's explicit approval
configuration for the supplied local engine. Verify that configuration in one
pilot before another five-pair run; keep model/settings external, both arms
matched, sandboxing enabled and engine tool-effect annotations truthful. The
documented [client configuration interface](https://learn.chatgpt.com/docs/config-file/config-reference)
provides server/tool approval settings. The item-ordering errors are a separate
candidate for focused guidance after the client setup is verified.

These additional SHA-256 identities bind the follow-up evidence; its raw
captures remain separate from the initial runs:

| Evidence | SHA-256 |
| --- | --- |
| Source candidate | `5e57d183bcaa3a6d16856980590db43643f60374cf361b3190e6981b3b628edb` |
| Inkbolt release executable | `40a3c7f88ef8aa50d96a468494173287ffa864bddb5705fccc4ab9485f17562f` |
| Inkbolt-arm report | `c432074c3e97dce7fc01cf61440ad7c7b4a78a035c2b9e125901673231f13406` |
| Baseline-arm report | `2438ddeb8d7b16f87f277b0260d8c5f62119c742b104aa05d2350d346a98a6c5` |
| Matched comparison report | `ab880b37dad6e63835ec9ff5d561d90658547c6b2a4665a6d3c7c35dabd62b4f` |

## B02 client approval configuration pilot

One subsequent genuine trial used the same client/model/settings and unchanged
B02 prompt/checks, with the externally selected `--mcp-approval-mode approve`
option described in the [driver contract](BENCHMARK_CODEX.md). The engine binary
was unchanged from the first-page experiment. This pilot passed all artifact and
native-source checks, including source preservation. Its transcript records four
successful `inkbolt_run` publication calls for the snapshot and three PNGs, with
zero client approval refusals. Shell commands inspected local files/pixels and
attempted CLI discovery; they did not publish the outputs. The sibling-stack
reorder error still occurred.

The client reported 436,301 input tokens and 2,073 output tokens, with 360,320
cached input tokens tracked separately, and 103.6 seconds of agent execution.
This is one setup pilot without a paired baseline, not an efficiency comparison
or part of either five-pair aggregate. The shell sandbox, prompt, model/settings
and engine effect annotations were preserved; the external config and exact
client argument array record the server policy. Future matched trials must use
the same external config in both arms. All full-suite completion gates remain open.

| Evidence | SHA-256 |
| --- | --- |
| Tested/pilot source candidate | `bdffa598686967936c79c57e1297068e31f04422e72c757cd7b455e9d4877aa6` |
| Pilot report | `d0975df5a530a5045d94fadf793c9849c11a75edd1682ecbd2d054976c7fdafb` |
| Client transcript | `e3daf8ac7812efe4e3cb0300a62ee05c1a114f4fa42726f016fc76fed47f27d3` |
| External client configuration | `7210961872baca5a7afc9f8668aa935135d311ad9beb83156563c0e633c0cf02` |
