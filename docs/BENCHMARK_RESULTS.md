# Recorded agent evaluation results

## B02: five matched icon-sheet trials

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
