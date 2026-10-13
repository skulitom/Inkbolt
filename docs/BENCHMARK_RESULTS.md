# Recorded agent evaluation results

Three five-pair B02 evaluations are recorded below. The latest CLI-help and
sibling-index guidance preserved 5/5 success in both arms and removed the observed
help/reorder failures. Inkbolt still used **5.44 times** the baseline's median
reported input-plus-output tokens. A separate setup pilot verified explicit MCP
approval; the latest five trials chose CLI execution. Broader task and smaller-model
evidence remain required.

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

## B02 at 8586e82: CLI-help and sibling-index guidance

Five new pairs used commit `8586e82ade30069fb2eabe6e13a112ec549e12a5`, the same
Windows host, Codex CLI 0.160.0, externally selected `gpt-6.1-sol` with medium
reasoning, unchanged B02 prompt/checks, and the same pinned baseline tools as
above. Both arms used the pilot-verified external configuration with explicit
MCP approval. The five Inkbolt runs preceded the five baseline runs; execution
was sequential, not randomized, on the shared host with no concurrent local
engine verification or benchmarks. OS caches could be warm. Candidate identity
remained unchanged, and the comparison found no evidence-matching issues.

| Measurement | Inkbolt arm | No-Inkbolt baseline |
| --- | ---: | ---: |
| Artifact success / retained attempts | 5/5 | 5/5 |
| Complete applicable workflow | 5/5 | 5/5 |
| Native editable-source check | 5/5 | Not applicable |
| 95% Wilson interval for artifact success | 56.6%-100% | 56.6%-100% |
| Median input + output tokens | 313,114 | 57,582 |
| Input + output token range | 274,123-394,769 | 56,782-70,869 |
| Median client execution, seconds | 112.8 | 46.6 |
| Client execution range, seconds | 99.9-129.7 | 40.0-54.6 |
| Median cached input tokens, reported separately | 253,312 | 35,328 |

The 5.44x token ratio still triggers the fixed cost signal. Inkbolt's observed
median was 44.5% below the previous five-run median of 564,296, but the engine
guidance, client approval configuration and execution paths differed across
batches. This small sequential sample does not isolate causes or establish
general performance, equivalence or billing savings. Cached context is included
in input totals and is not added twice. Model-call counts, complete engine
traffic/retries and first verified preview time remain unknown.

All five Inkbolt traces successfully used `--help`, looked up the `reorder`
operation, and avoided the previous sibling-reorder failure. They used 10-13
completed shell items each and no MCP calls. Thus zero approval refusals in this
batch do not measure the server policy's effect; the separate MCP pilot remains
the evidence for that setting. The agents arranged the required flat snapshot
item order explicitly before engine validation/publication. One trial attempted
an invalid global insertion index and repaired it; schema-selector and output-option
errors also remain in the captures. No prompt, judge or insertion/reorder semantics
were changed to improve the scores.

Transcript and generated-script review found only the supplied engine/image
tools, workspace inputs/outputs and owned temporary files. No repository/judge
reads, additional model use or baseline engine access were observed. All ten
attempts remain retained. These observations count client items, not underlying
model or engine calls.

The next work is broader B01/B03 and smaller-model evaluation before further
B02-specific tuning. The insertion-index and schema-discovery gaps remain
recorded, while larger W3c/W4/W5.2+/W6 priorities await evidence across tasks.
The other nineteen tasks, Linux scale evidence and sister-engine comparison
remain open. All four full-suite completion gates remain false; no checkpoint
credit or full W2/W5.2 milestone completion follows from these results.

The complete captures, reports and comparison remain outside the repository
under `w5-cli-guidance-b02-`; reviewed trace counts and final candidate hashes
are retained alongside them. The same configuration hash as the pilot above
applies to both arms.

| Evidence | SHA-256 |
| --- | --- |
| Source candidate | `cd888dde1f5765d78fee3bdac3512f56e9202ffe269608253ae47b3a82d15b27` |
| Inkbolt release executable | `3fc78f0f7eb5d3273ad693e1f2726cb9fc4fe1cb837bb1dc88367daa4ec15959` |
| Inkbolt-arm report | `1c1697dcd26aaccb6e760fe165f2adbb3c8940941e072e9bc1a6ac6f6f7b353b` |
| Baseline-arm report | `96c016d9bea5c7153f23ab74fb9c454f93b2df90056159c401155416f9812e1c` |
| Matched comparison report | `085294024818692b92f53dbc537925f5b583fcf5c6014310c89b99efbe752fbc` |

## B01/B03 breadth pilots and capture rejudgment

Single-attempt pilots broadened coverage to labelled diagrams (B01) and a
5,000-object edit with saved history (B03). Codex CLI 0.160.0 used externally
configured `gpt-6.1-sol` and `gpt-6-luna`, each with medium reasoning and the
explicit MCP approval option. Each model used the same configuration in its two
arms. No model is built into the harness, engine or acceptance criteria.
The pinned baseline tools and release executable match the preceding B02 batch.
Runs were sequential on the shared Windows development host; OS caches could
be warm. Each model's Inkbolt arm preceded its baseline arm. They were not
randomized, and the two model configurations are separate pilot samples.

| External model | Task | Inkbolt / baseline outcome | Input + output tokens, Inkbolt / baseline | Client seconds, Inkbolt / baseline |
| --- | --- | --- | ---: | ---: |
| gpt-6.1-sol | B01 | Pass / fail | 363,329 / 57,926 | 104.2 / 41.7 |
| gpt-6.1-sol | B03 | Pass / pass | 379,095 / 67,137 | 149.9 / 38.3 |
| gpt-6-luna | B01 | Pass / fail | 698,196 / 64,542 | 133.5 / 23.8 |
| gpt-6-luna | B03 | Pass / pass | 575,269 / 66,564 | 104.2 / 31.8 |

Outcomes above use corrected judges on the original captured bytes. Sol's B01
initially failed because the judge assumed the default font store. Luna's B03
initially failed because the judge assumed the default session store. Neither
prompt prescribes those store names. The corrected judges locate retained
resources inside the capture and still verify exact font/license identities,
editable content, all pixels and, for B03, exact original/current snapshots and
full history integrity. Missing, linked or corrupt font/license copies fail;
missing, linked, ambiguous or corrupt session stores also fail. Regression tests cover nondefault stores and
capture relocation; [verification evidence](DEVELOPMENT_STATUS.md) records the
focused Windows/Linux results. Artifact and engine requirements did not change.

Both B01 baseline failures remain. Sol delivered a `defs/style` font embedding
outside the prompt's bounded editable SVG contract. Luna's text placement
differed from the required frame positions; its renderer invocation also omitted
the supplied font. Neither failure was relaxed or retried. Both B03 baselines
passed shared artifact checks; saved history is explicitly not applicable there.

All eight transcripts and generated command/script bodies were reviewed.
Observed tools and reads stayed within the supplied engine/image tools and
workspace material; no repository/judge reads, additional model calls or baseline
engine access were observed. All Inkbolt trials used CLI execution and no MCP
calls. Shell/schema, relative-path and output-option errors remain in the raw
traces. Rejudgment preserved transcript and workspace hashes, token usage and
original client durations; it did not rerun the models or replace original
reports. Judge execution is separate from client execution.

These are pilots, not five-repetition acceptance or evidence of relative
reliability/efficiency. Input totals include cached context; cached tokens are
reported separately in the raw rows and are not added again. Model-call counts,
complete engine traffic/retries, first verified preview and engine-only memory
remain unknown. Neither comparison has matching issues for B01/B03, but both
retain false minimum-repetition and full-suite completion gates. Complete the
required repetitions and broader task coverage before further priority changes.

Original captures remain under `w2-breadth-*-pilot-01`; new reports are under
`w2-breadth-*-rejudged-02` and `w2-breadth-*-comparison-pilot-02`. The trace review
is retained separately. Sol's original candidate was
`7bac198d1f816e4907c55c1fb54a4f138839313b17efa3abc747d48fa40fa6a5`;
Luna's was `8f25bdc287d0cbc5c87609146bd58f027dc669f4cc12c9139d76a886d3e89041`.
Both used the unchanged release executable identified in the preceding table.

| Rejudged evidence | SHA-256 |
| --- | --- |
| Shared tested/judged source candidate | `115d0ecb4e8a4f3110df3936fe8c29db48cc8dd5e8fae9c171f614cd1af2f46b` |
| Sol Inkbolt report | `6b996520eac294d80e9631e722dbcb532aacd3b8e241cf436cc2c9f2ca6a72fa` |
| Sol baseline report | `c4ce824949269a14126824c3c17d8289652784a6cb43682c1bc16f723a3c22b0` |
| Sol comparison | `83dcb595c1332c8d844cfa6b5e90ef1dd31a5fed45556846786cedefcf7bc828` |
| Luna Inkbolt report | `c891df9bfde9e83f21b8b662199547bc6c1baab2c13d32f36fda11dd08f029f1` |
| Luna baseline report | `42866663ce11e65a86288c69291091e76971a2ce484c2f45a957f719f7caeac7` |
| Luna comparison | `b1c8002ea52f7aa66dce5bc3567159f75cb1221d9e7097672e8d604252c3a35f` |
| Sol external configuration | `7210961872baca5a7afc9f8668aa935135d311ad9beb83156563c0e633c0cf02` |
| Luna external configuration | `6b34578c04ebb0bb7597d48820f9e58720a0ecef42fa2b27e2145d40472320c3` |

## B01/B03 at 8bc8982: five matched pairs

Five new repetitions per task and arm used Codex CLI 0.160.0, externally selected
`gpt-6.1-sol` with medium reasoning, and the same explicit MCP approval option.
The engine and pinned baseline tools match the preceding pilots. Model choice
remains external; these names identify this evaluation only. The Inkbolt arm
preceded the baseline on the shared Windows host. No other Inkbolt verification
or benchmark ran concurrently in this chat; other host workloads were
uncontrolled and OS caches could be warm. Task order rotated by repetition.
Neither arm changed its source inputs, and both selected tasks have five matched
pairs with no global or task matching issues.

| Task | Inkbolt / baseline artifact passes | Median input + output tokens | Median client seconds |
| --- | --- | ---: | ---: |
| B01 diagram | 5/5 / 0/5 | 299,232 / 71,327 | 95.9 / 45.7 |
| B03 5,000-object edit | 5/5 / 5/5 | 349,212 / 65,011 | 128.9 / 41.8 |

Medians include all attempts, including B01 baseline failures. B03 triggers the
existing signal: matching shared artifact success and **5.37x** median observed
token use with Inkbolt. Every Inkbolt B03 trial also passed saved-revision and
history checks, which are not applicable to the baseline. Five equal artifact
outcomes do not prove equivalence or isolate the cost of those extra semantics.
The broader decision and full-suite gates remain false.

All five B01 baselines embedded the supplied font in a CSS `style` element,
usually inside `defs`, beyond the judge's supported source subset. They also
included frame metadata attributes outside that subset. Admission stopped the
original judge before pixel checks; the failures were retained without retries.
A separate post-hoc check of the unchanged delivered PNG bytes against the
existing independent pixel oracle passed all five images. It did not re-render
SVG, validate source/font semantics or convert task failures to passes. B01's
font-retention wording and bounded source contract need review before using
these failures as general reliability evidence. There is no successful-pair
token-cost signal for B01 and no demonstrated rendering advantage from this batch.

All twenty transcripts, command bodies and generated scripts were reviewed.
No repository/judge reads, additional engines/models or baseline Inkbolt access
were observed. Two Inkbolt attempts mixed MCP with shell calls: B01 repetition
one used 21 MCP items and B03 repetition five used 27; the other eight used CLI
only. Invalid schema selectors, relative resource paths and publication options
remain in the traces. Shell-item counts do not measure complete engine calls,
errors or retries. Input totals include cached context without adding cached or
reasoning tokens twice. Billing, model-call counts, full engine traffic/retries,
first verified preview and engine-only memory remain unknown.

The next work is broader B04/B05 evidence; the palette judge's unprescribed
default-store assumption now has a focused Windows/WSL correction. B03 reinforces the need to reduce
discovery overhead, while the full task matrix must still guide substantial
W3c/W4/W5.2+/W6 ordering. This batch does not complete W2 or change checkpoints.

External evidence is retained under `w2-breadth-sol-{model,baseline}-five-01`
and `w2-breadth-sol-comparison-five-01`, with separate trace reviews and
`w2-breadth-sol-b01-supplemental-pixels-01.json`.

| Evidence | SHA-256 |
| --- | --- |
| Shared source candidate | `5de6a49ce7e146936c0f7f9b04960c9200a9ca23744d157bb6c8eda9d68d4812` |
| Inkbolt report | `abf3044104010b5fc36043eb4c5edf1b8df03878da86d55539a86bb76fd920f2` |
| Baseline report | `632a0f5dda0a8de1f951f1d415b94978c546674bf0d8b2010a4a09b835982a85` |
| Matched comparison | `a3ef9a766ea7ecb721f77dbc871ab651ae4ddf9e631b06a7ee751d0e3ea5949d` |

## B04/B05 at dabe447: five matched pairs

Five fresh repetitions per task and arm used the same external Codex CLI
0.160.0 configuration (`gpt-6.1-sol`, medium reasoning, explicit MCP approval
option) as the preceding batch. These are evaluation metadata, not model
defaults. The engine and pinned baseline tools were unchanged. The Inkbolt arm
preceded the baseline on the shared Windows host; task order rotated within
each arm. No other Inkbolt verification or benchmark ran in this chat, other
host workloads were uncontrolled, and OS caches could be warm. Both source
candidates stayed unchanged; both tasks have five matched pairs and no matching
issues. Every attempt and its original transcript remains retained.

| Task | Inkbolt / baseline artifact passes | Median input + output tokens | Median client seconds |
| --- | --- | ---: | ---: |
| B04 SVG import/edit | 5/5 / 5/5 | 206,924 / 57,528 | 71.2 / 56.7 |
| B05 shared palette | 5/5 / 5/5 | 270,958 / 54,973 | 93.8 / 35.6 |

Both tasks trigger the existing cost signal: baseline artifact success matches
Inkbolt, whose median observed token totals are **3.60x** and **4.93x** those of
the baseline, respectively. All Inkbolt-only native-source and palette live-reference/history
checks passed; these are explicitly not applicable in the baseline. Five equal
outcomes do not prove equivalence, and this comparison does not isolate the cost
of those additional guarantees. Cached input is included in input totals, never
added twice. These ratios are not billing or causal performance estimates.

Every B04 baseline retained the original SVG IDs and description. Every Inkbolt
B04 delivery remapped IDs and omitted the description, with exact losses openly
reported and judged. All retained the requested editable path and passed pixel
checks. Every B05 Inkbolt attempt chose a nondefault session directory; the
corrected judge found and verified its original/current snapshots and history.

All twenty traces and generated command/script bodies were reviewed. No
repository/judge reads, extra models/engines or baseline Inkbolt access were
observed. All Inkbolt attempts chose CLI execution; this batch does not measure
MCP approval behavior. Invalid schema selectors, full-schema fallbacks, a JSON
property-order comparison false alarm and a mistaken historical publication
request remain in the traces and usage. Some agents also retained extra local
copies of the task prompt. Complete model-call/engine-call counts, traffic,
retries, first verified preview and engine-only memory remain unknown; completed
shell items are not substituted for these metrics.

This extends the fewer-interactions signal beyond B02/B03 into input admission
and palette authoring. Continue the remaining tasks before making a substantial
W3c/W4/W5.2+/W6 choice from the full decision rule. B06/B07 are next after their
audited resource-location assumptions are corrected and checked. Full-suite,
matched sister-project and readiness gates remain open; checkpoints are unchanged.

Reports/workspaces are retained under `w2-svg-palette-sol-{model,baseline}-five-01`
and `w2-svg-palette-sol-comparison-five-01`, with separate trace review files.

| Evidence | SHA-256 |
| --- | --- |
| Shared source candidate | `cddc5b424cf3f1154733069dc615c302621a8da7311ef21aa32f316460eeca3f` |
| Inkbolt report | `13bc20d7fc032c105037cf4b715a83034380575481372997f0a60b630343ff36` |
| Baseline report | `ef6a6603aac9534468539d097c072aeb79e027faeaf70d1638c8fe2e2fdf9e74` |
| Matched comparison | `006c77ecd151342ec6af21579bc8200b5277fb2cd8e79981fa0fcffad48be9e6` |

## B06/B07 at a7e034e: captured trials rejudged

Five new repetitions per task and arm used the same external Codex CLI 0.160.0
configuration (`gpt-6.1-sol`, medium reasoning, explicit MCP approval option).
These identify the evaluation only; the engine and harness have no model default.
The unchanged release executable and pinned baseline tools match the preceding
batch. Inkbolt ran before the baseline on the shared Windows host, with task
order rotated by repetition. This chat scheduled no concurrent Inkbolt checks
or benchmarks; other host workloads were uncontrolled and OS caches could be
warm. Both original and rejudged source candidates stayed unchanged. Both tasks
have five matched pairs with no global or task matching issues.

| Task | Inkbolt / baseline artifact passes | Median input + output tokens | Median client seconds |
| --- | --- | ---: | ---: |
| B06 linked text flow | 5/5 / 5/5 | 337,131 / 76,580 | 113.8 / 53.5 |
| B07 multilingual typography | 5/5 / 0/5 | 405,058 / 218,798 | 111.8 / 148.3 |

B06 triggers the existing cost signal: matching shared artifact success at
**4.40x** median observed token use with Inkbolt. Its saved historical-flow and
history checks also passed; those engine-only checks do not apply to the baseline.
Five equal outcomes do not prove equivalence or isolate the cost of those extra
guarantees. Medians include failed attempts. B07 has no successful-pair cost
signal because its baseline mapping checks failed.

Every B07 image passed the delivered and independent fresh-render pixel checks
in both arms. All five Inkbolt attempts originally failed only the engine's
snapshot judge: the model explicitly selected a fixed baseline of 200, while
the reference omitted that setting and obtained the same position from ascent.
Prompt version 1 prescribes positions, not a storage representation. A focused
Windows/WSL correction admits explicit controls while keeping independent
glyph/cluster positions and pixel checks; a one-pixel shift still fails. Rejudging
the existing captures changed only those five snapshot checks. All ten Inkbolt
attempts now pass their complete workflows. The original failures remain in
their original reports; no model was rerun and no attempt was added or discarded.

All five baseline B07 failures remain. Each mapping lists a Hebrew base glyph
before its zero-advance mark within the shared scalar interval [2,4); the fixed
oracle lists the mark first. The entries, glyph IDs, source intervals, origins
and advances otherwise match. Review this within-cluster ordering convention
before drawing general reliability conclusions. The results show no rendering
advantage for either arm on this sheet.

All twenty transcripts and generated command/script bodies were reviewed. No
repository/judge reads, extra engines/models or baseline Inkbolt access were
observed. B07 Inkbolt repetitions two and four used 37 and 40 MCP items plus
five and three shell items respectively; the other eight used CLI only. Invalid
schema selectors, relative paths, image-option errors, JSON comparison false
alarms and Windows text-encoding errors remain in the traces and usage. This
batch does not isolate MCP's effect. Cached input is already included in input
totals. Billing, model-call counts, full engine calls/traffic/retries, first
verified preview and engine-only memory remain unknown.

Original captures/reports remain under `w2-text-sol-{model,baseline}-five-01` and
`w2-text-sol-comparison-five-01`; the new reports are under the corresponding
`rejudged-02` directories. `w2-text-capture-rejudge-integrity-01.json` verifies
all twenty original and imported workspaces, transcripts, driver results,
observed usage and client durations stayed identical. Separate trace reviews
and baseline-placement/mapping audits are retained. B08/B09 are next after
their store assumptions are checked. Full-suite, sister-project and readiness
gates remain open, with no engine checkpoint changes.

| Evidence | SHA-256 |
| --- | --- |
| Original source candidate | `bc2aac5d628d8cd3cbd5740789bda9eeb1972957a2545e7868ef461721e5d517` |
| Tested rejudging candidate | `095c7c0e1371266b168279206e01f563212f81bd44ae0f6148b2b831e593fb0f` |
| Original Inkbolt report | `3092be7bb880fe670812636786866a5b8599598876a3759d99bb139d7dfc75a9` |
| Original baseline report | `a8ff136b19a61ac2e49df022b700d148c7efa3b1006a48a3555d567f6e8576d2` |
| Original comparison | `f5a5f6943b71d9ebec479a8f5fde1d19945aeccdd9731bf4df94211f11db66d1` |
| Rejudged Inkbolt report | `8765717495fc03ba6b78949d88f24197a3b8d66d5f9dcdb577dab9bda026762c` |
| Rejudged baseline report | `4a8ac2ee3a44e629e6ef69830ea13488328099b6fc964c08372deb02662e5aeb` |
| Rejudged comparison | `d5bab3caad15ad9fe76db30dfe414a3723a8bdc57f5097dbf557c9725ec89043` |

## B08/B09 at 38f0397: five matched pairs

Five fresh repetitions per task and arm used the same external Codex CLI 0.160.0
configuration (`gpt-6.1-sol`, medium reasoning, explicit MCP approval option).
The model name identifies this evaluation only; no engine or harness default
was introduced. The release executable and pinned baseline tools were unchanged.
Inkbolt ran before the baseline on the shared Windows host, rotating task order
by repetition. This chat ran no other Inkbolt checks or benchmarks concurrently;
other host workloads were uncontrolled and OS caches could be warm. Both source
candidates stayed unchanged, and both tasks have five matched pairs with no
global or task matching issues.

| Task | Inkbolt / baseline artifact passes | Median input + output tokens | Median client seconds |
| --- | --- | ---: | ---: |
| B08 foreground mask | 5/5 / 5/5 | 327,734 / 43,824 | 93.7 / 32.3 |
| B09 local retouch | 5/5 / 5/5 | 354,590 / 43,008 | 102.0 / 29.2 |

Both tasks trigger the existing cost signal: matching shared artifact success
at **7.48x** and **8.24x** median observed token use with Inkbolt. All Inkbolt
saved-original and history checks also passed; those engine-only checks are not
applicable to the baseline. Seven Inkbolt attempts chose nondefault session
directories, and the corrected judges verified their exact original/current
states. Five equal outcomes do not prove equivalence or isolate the cost of
the extra history guarantees. These exact 16 by 16 fixtures measure basic
workflow use, not production-scale raster latency or memory.

All twenty transcripts, command bodies and MCP arguments were reviewed. No
repository/judge reads, extra engines/models or baseline Inkbolt access were
observed. Four Inkbolt attempts mixed MCP and shell calls: B08 repetitions one
and two used MCP for discovery, while B09 repetitions three and five also used
it for editing and publication. The other six used CLI only. The baseline used
the pinned Python/Pillow environment and ordinary local file inspection. Its
mask deliveries retained the original layer and separate selection/mask images;
its retouch deliveries retained the exact repaired editable pixel layer.

Invalid nested-schema selectors, full-schema fallbacks, rejected PNG options,
reversed clone transforms, and JSON text comparisons that mistook serialization
differences for state changes remain in the transcripts and usage. No attempt
was retried or discarded by the harness. Cached input is included in input totals,
never added twice; these ratios are not billing estimates. Complete model/engine
call counts, engine traffic/retries, first verified preview and engine-only
memory remain unknown. Event counts are not substituted for those measurements,
and this batch does not isolate MCP's effect.

The results extend the interaction-cost signal to these raster workflows.
Continue B10 and the remaining task coverage before the full plan decision gate;
the native photograph's exact precision and memory requirements remain distinct.
Full-suite, sister-project and readiness gates remain open, with no engine
checkpoint changes. Reports/workspaces remain under
`w2-mask-retouch-sol-{model,baseline}-five-01` and
`w2-mask-retouch-sol-comparison-five-01`. Separate trace reviews and
`w2-mask-retouch-sol-evidence-audit-01.json` retain the identity checks.

| Evidence | SHA-256 |
| --- | --- |
| Shared source candidate | `89c7856f7aada09c66da34a5e96d31ebe5f4b9a1671083cdd67a8b452c5dd36c` |
| Release executable | `3fc78f0f7eb5d3273ad693e1f2726cb9fc4fe1cb837bb1dc88367daa4ec15959` |
| Inkbolt report | `41bda628113e00aecf37e101fa2b883e73191d9fd4895956a8f135fab5f2d5fa` |
| Baseline report | `f22b7f737b7cb8c79f2411c41c4f1926b411a14830946cbe94f3faffec150717` |
| Matched comparison | `f3228271c9a41526e899a4937495cb26fda9aec1d87853e2cc505e493a2251bf` |
