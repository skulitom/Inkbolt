# Recorded agent evaluation results

The latest [request-guidance follow-up](#b10b17b19-at-447bbc2-request-guidance-follow-up)
passes 3/5 photograph workflows versus 5/5 baseline, 4/5 lost-response workflows,
and 4/5 interrupted-job workflows. It retains every failure and establishes no
general efficiency gain from the new diagnostics. Earlier batches below remain
separate; no prompt versions or attempts are pooled.

Five-pair evaluations now cover B01-B16, with separate smaller-model pilots.
Five additional native attempts each cover B17/B18; those recovery tasks have no
applicable baseline. Both pass 5/5 artifact checks, but two B17 receipt-format
failures leave its complete workflow at 3/5. B18 passes its full workflow 5/5.
Eleven tasks matched baseline artifact success with higher median token use.
Photo repair and mixed composition each passed 3/5 with Inkbolt versus 5/5 with
the baseline. Layout variants passed 5/5 in both arms at 9.17x median token use
with Inkbolt after tested judge corrections. Resource repair passed 5/5 in both
arms at 4.83x tokens; version-2 text repair passed 5/5 in both at 4.47x.
After PDF-judge corrections, print artifacts pass 5/5 with
Inkbolt and 4/5 with the baseline. Two Inkbolt receipt-selection failures leave
its complete workflow at 3/5; this small sample establishes no reliability advantage.
The evidence below preserves failures, judge corrections and exact build
identities. Five B19 attempts failed the protocol gate; four nevertheless passed
all nine independent artifact/recovery checks. B20's first five-pair batch passed
0/5 native workflows versus 5/5 baseline workflows; native artifact judging
stopped at prerequisites, leaving its quality unjudged. B19 accepted-trial
coverage, B20 source-preservation failures, further smaller-model trials and the separate
sister-project comparison remain open. These batches are not full-suite acceptance.

The later [B19/B20 guidance pilots](#b19b20-at-1d5b960-guidance-pilots-and-observation-corrections)
pass the protocol gates. B19 still fails exact retained-record checks; B20 passes
both arms after tested judge corrections. These single attempts stay separate
from the earlier five-trial batches.

The [separate follow-up at f61d952](#b19b20-at-f61d952-recovery-pilot-and-five-pair-handoff-follow-up)
passes 3/5 complete B20 native workflows versus 5/5 baseline after one further
judge correction, at 3.79x median tokens. Its B19 pilot passes all independent
checks but fails the protocol gate. Prior attempts and original scores remain
retained; no batches or prompt versions are pooled.

The later B03/B16 discovery follow-up passes 5/5 per task in both arms, while
Inkbolt still uses 4.62x/5.20x baseline median tokens. Its before/after signal is
mixed; see the [follow-up](#b03b16-at-d34851e-nested-discovery-follow-up).

A preliminary B16 batch exposed a default-field judge bug and underspecified
recipe types. Its retained failures and correction are recorded below, separately
from the completed matched prompt-version-2 batch.

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

## B10/B13 at 7a07f07: five matched pairs with retained-capture corrections

Five genuine repetitions per task and arm used the same external Codex CLI
0.160.0 configuration (`gpt-6.1-sol`, medium reasoning, explicit MCP approval).
The model is evaluation metadata only. Inkbolt ran before the baseline on the
shared Windows host, rotating task order by repetition. No other Inkbolt checks
or benchmarks were scheduled by this chat during those solves; other workloads
were uncontrolled and OS caches could be warm. Both arms retained the same
source candidate, release executable and pinned baseline tools.

| Task | Inkbolt / baseline artifact passes | Median input + output tokens, all attempts | Median client seconds, all attempts |
| --- | --- | ---: | ---: |
| B10 native photograph repair | 3/5 / 5/5 | 606,589 / 75,674 | 144.9 / 83.2 |
| B13 transparent screen artwork | 5/5 / 5/5 | 313,210 / 41,717 | 101.7 / 35.6 |

Complete applicable workflow counts match artifact counts. B13 triggers the
existing cost signal at **7.51x** median input-plus-output tokens. B10 has only
three jointly successful pairs, so the fixed policy does not produce a cost
ratio; the all-attempt medians above retain failures. Five attempts give wide
95% Wilson intervals: 23.1%-88.2% for 3/5 and 56.6%-100% for 5/5. They do not
establish general reliability or statistical equivalence.

The original judge rejected every baseline B10 TIFF at an embedded ICC profile
stored with TIFF UNDEFINED byte type 7. Its byte reader now preserves that field
for both byte orders. Fresh judging verifies every 16-bit channel and pinned
Pillow reopening. Original B13 Inkbolt repetition one had the exact private
note in `metadata.note`; the judge had demanded `metadata.private.note`, which
the prompt never prescribed. It now admits placement within the engine's
metadata schema while requiring the exact note value and all original source,
pixel, color and create-only publication checks. Regression controls cover
changed/missing notes, geometry, alpha, private delivery records, file identity,
overwrite protection and native low-bit corruption.

All twenty unchanged captures were rejudged after focused Windows/WSL checks.
The five baseline photo failures and one screen-source failure now pass; the
other outcomes are unchanged. Original reports remain alongside the new reports.
Full workspace hashes, transcripts, client results, token/time observations and
captured process-memory evidence match their originals. No model was rerun and
no attempt was added or discarded.

B10 Inkbolt repetitions two and five still fail. Their commands omitted the
workspace option, then interpreted the resulting import error as requiring an
explicit store. They departed from the prompt's `storage:{}` contract and used
`native-tiles`. Immutable-store checks fail and fresh rendering cannot find the
tiles at the required default root. Missing downstream checks remain failures;
the delivered TIFFs from those attempts do not receive independent pixel credit.
The three successful attempts pass exact native samples, immutable tiles,
proposal/history checks and the 256 MiB per-process bound. That bound uses
captured peaks across owned client/tool processes; it is not exact engine-only
memory. The baseline passes its applicable sample, preview and memory checks;
Inkbolt history guarantees remain explicitly inapplicable there. This is a
2.07 MP fixture, not the larger W4 workload gate.

All completed command/MCP events and retained generated helper bodies were
reviewed. No prohibited repository/judge reads, extra model/engine use or
baseline Inkbolt access were observed. File-change events omit patch bodies,
so earlier overwritten helper versions are not fully retained. No image-view
tool was observed; numerical validation does not prove visual review. Only
B13 Inkbolt repetition one used MCP alongside shell calls; the other nine used
CLI only. Every Inkbolt photo attempt first tried an unsupported repair operation
before finding native retouch. Invalid schema selectors and workspace/path
errors remain in the recorded usage. Client-written error summaries are not
substituted for captured command responses.

Prioritize actionable workspace errors and clearer native-operation discovery,
then remeasure their effect with the same task contracts. Continue B11/B12 and
the remaining coverage before the full plan decision gate. Token totals already
include cached input and are not billing estimates. Full model/engine call
counts, traffic/retries, first verified preview and engine-only memory remain
unknown. Extra native-source/history obligations and mixed transports prevent
a causal attribution of the cost difference. No checkpoint credit changes.

Evidence is retained under `w2-photo-screen-sol-{model,baseline}-five-01` and
the corresponding `rejudged-01` directories, with original/rejudged comparison
reports. `w2-photo-screen-capture-rejudge-integrity-01.json` and separate trace
reviews retain the identity and review checks.

| Evidence | SHA-256 |
| --- | --- |
| Original source candidate | `a6fbc0f46e6e4875b1e93a67864df5246d7b3fa34732e061eb4ff1c06e42aaa5` |
| Tested rejudging candidate | `2d7fa5e3eddaa00f616189c548d16d0c7d0e4d974687861c6fdf232e27c4ebeb` |
| Release executable | `3fc78f0f7eb5d3273ad693e1f2726cb9fc4fe1cb837bb1dc88367daa4ec15959` |
| Original Inkbolt report | `2c882673d3e268effddb16b57adf4bb8b11b276ab5b043c4769a065a6380715c` |
| Original baseline report | `ea9feb88f29fa5abed557eb5142c57d84e2351c0e461fbbbeaae183f1214d4f4` |
| Original comparison | `44a342ab7214ed60e4c5a1d77254fe0e980578321592e1fbbc5f0228f45f2556` |
| Rejudged Inkbolt report | `54ebcd79653411ec490cb90be67f8b8d913e47c2676de70f6f41c8c535590ad1` |
| Rejudged baseline report | `6f5468d57866598014ac6fc07435b956ad6e2bfe7075abdd0cde8135df56b770` |
| Rejudged comparison | `b5ae766dcb21748c2dc38ac87ab359c8a001a66e1ea6a8601922563a1eba7b98` |

## B11/B12 at 30c4ebd: mixed composition and layout variants

Five genuine repetitions per task and arm used the same external Codex CLI
0.160.0 configuration (`gpt-6.1-sol`, medium reasoning, explicit MCP approval).
These are evaluation settings, not product or harness defaults. Inkbolt ran
before the baseline on the shared Windows host, rotating task order between
repetitions. Sources and tools stayed fixed through both arms. No other local
Inkbolt verification or benchmarks ran during those solves; other host workloads
were uncontrolled and OS caches could be warm. The baseline retained pinned
resvg 0.47.0 and Pillow 12.3.0 in the external Python 3.11 environment.

| Task | Inkbolt / baseline artifact passes | Median input + output tokens, all attempts | Median client seconds, all attempts |
| --- | --- | ---: | ---: |
| B11 mixed masked composition | 3/5 / 5/5 | 395,699 / 72,214 | 114.8 / 46.8 |
| B12 shared layout variants | 5/5 / 5/5 | 566,966 / 61,799 | 128.8 / 46.0 |

Complete applicable workflow counts match artifact counts. B12 triggers the
fixed cost signal at **9.17x** median input-plus-output tokens. B11 has only
three jointly successful pairs, so the fixed policy does not publish a cost
ratio; all-attempt medians retain its failures. Five trials give wide 95% Wilson
intervals: 23.1%-88.2% for 3/5 and 56.6%-100% for 5/5. These small 32 by 24
composition and three-artboard fixtures do not establish production scale,
general reliability, statistical equivalence or the cause of the token gap.

The original B12 judge stopped three Inkbolt attempts at a fixed array-position
assumption. Native `add` operations produced a different cross-parent item
interleaving while preserving the requested hierarchy and sibling order.
A synthetic client reproduced the same failure before the correction. The
judge now locates roles by content and parent and compares all fields plus each
parent's ordered children. It still rejects changed parents, sibling order,
binding targets, resources, properties, receipts and saved history. One attempt
also used the exact names from the prompt's artboard table as display labels.
Those labels and default empty labels are accepted; unrelated labels fail.
The prompt and its fixed IDs, geometry and other defaults are unchanged.

All twenty original captures were rejudged after focused Windows and WSL
verification. The three B12 errors now pass every artifact and engine check;
all other outcomes remain unchanged. Original reports, full workspace hashes,
transcripts, client results, token/time observations and captured process-memory
evidence match the originals. No model attempt was rerun, added or discarded.
The separate synthetic before/after capture also passes unchanged and receives
no model credit.

B11 Inkbolt repetitions one and three still fail: both added `locked:true` to
the original image although the prompt requires default remaining properties.
That is the sole difference between each saved original and the independent
template. Current pixels and original resource identity pass, while complete
composition and saved-state/history checks fail. The judge correction does not
waive those lock changes. Inkbolt's saved-revision and typed-binding guarantees
remain engine-only requirements, inapplicable to the baseline.

All completed direct command/MCP events and available generated script bodies
were reviewed. All ten Inkbolt attempts used CLI only. No prohibited access was
observed, but file-change events omit patch bodies; some intermediate versions
are unavailable. B11 repetition four removed its helper after further edits,
so its final nested helper behavior cannot be fully attested. No image-view tool
was observed; clients' claims of visual review are not independently verified.
Repeated schema lookups, invalid selectors and relative-path imports without a
workspace remain in the usage. Token totals include cached input and are not
billing estimates. Full model/engine call counts, traffic/retries, first verified
preview and engine-only memory remain unknown. Captured client-tree memory is
separate evidence, not an engine memory measurement.

The results reinforce workspace guidance and operation discovery as priorities.
Continue B14-B20 and the separate sister-project comparison before the full W2
decision gate. No engine checkpoint or complete readiness gate gains credit.
Evidence remains under `w2-mixed-variants-sol-{model,baseline}-five-01` and the
corresponding `rejudged-01` directories. The original and rejudged comparisons,
`w2-mixed-variants-capture-rejudge-integrity-01.json`, arm reviews and retained
script bodies preserve the outcome and review boundaries.

| Evidence | SHA-256 |
| --- | --- |
| Original source candidate | `278a9c1f7ace6247504ea3e29f2b9b0f19d6db071a2c57051aa9e7c1485636a1` |
| Tested rejudging candidate | `04f6923675698f2f3451127b137c259988fef43962209db01cf5adeb52e05f46` |
| Release executable | `3fc78f0f7eb5d3273ad693e1f2726cb9fc4fe1cb837bb1dc88367daa4ec15959` |
| Original Inkbolt report | `efda116a63ec37d1c305f1e9d835979320b1a9345385cf2467f20fe4f8b5b9e9` |
| Original baseline report | `2687b06b3d2def5c871464e0ccf0c8447f24c1b313f2198b5469a1efa4a1a536` |
| Original comparison | `aebceb45d795b2a3979926c0536e68f5ebc632113d5c113ee0cfac7a3c377526` |
| Rejudged Inkbolt report | `b6b886736298b1756630d6dfc07243454af49f78f66390d37a44672323737c9c` |
| Rejudged baseline report | `57380085b0485a31a0c24596ff1756c05f8cb798aa7e9fd47f5194a71f0e3123` |
| Rejudged comparison | `8f76b4837778e02596cf4703fc793b04c4fcb9b200f06f66a7a4cc3dffdfbd9f` |

## B14/B15 at 7d31cf9: print delivery and resource repair

Five attempts per task and arm used the same external Codex CLI 0.160.0,
`gpt-6.1-sol` medium configuration, explicit MCP approval mode, shared Windows
host and pinned baseline tools as the preceding batches. The Inkbolt arm ran
first, then the baseline; task order rotated per repetition. The repository and
engine stayed unchanged throughout, with no concurrent local verification or
benchmarks from this chat. Other host workloads were uncontrolled and caches
could be warm. Model names describe this evaluation only, not product defaults.

| Task | Inkbolt / baseline artifact passes | Complete workflow passes | Median input + output tokens, all attempts | Median client seconds, all attempts |
| --- | --- | --- | ---: | ---: |
| B14 physical print | 5/5 / 4/5 | 3/5 / 4/5 | 531,200 / 97,120 | 114.0 / 97.0 |
| B15 resource repair | 5/5 / 5/5 | 5/5 / 5/5 | 274,948 / 56,972 | 89.8 / 44.2 |

The initial B14 judge rejected every baseline PDF at the rendering-intent
operator `ri`. Public-specification review exposed other unprescribed encoding
restrictions: direct-only page/spot color-space arrays, a fixed first corner and
traversal direction, and page-group flags that are equivalent for the exact
standalone page's two opaque, disjoint rectangles. Tested corrections now admit
those representations, while preserving scoped rendering intent, cumulative
graphics state, exact profiles, geometry, native inks and conversion settings.
The original prompt and all check IDs/classes remain unchanged.

Four unchanged baseline captures now pass every artifact check. Repetition one
still fails native-ink delivery because both paints omit `UseBlackPtComp OFF`.
The prompt requires compensation off; absence leaves the choice to the PDF
processor, as explained in the [PDF Association application note](https://pdfa.org/resource/pdf-2-0-application-note-001-black-point-compensation/).
Its physical boxes, profiles, exact preview, source preservation and declared
losses pass. No delivery was edited and no model was rerun. B14 has four jointly
successful artifact pairs, below the fixed five-pair cost threshold; its cost
ratio remains unavailable. Five trials cannot establish a reliability advantage.

B15 triggers the fixed cost signal at **4.83x** median input-plus-output tokens.
Its five paired artifact successes give a wide 95% Wilson interval of
56.6%-100% in either arm. The small synthetic repair fixture does not establish
general reliability, production-scale recovery or a cause for the cost gap.
All attempts remain in the distributions; cached input is already included and
the ratio is not a billing estimate.

The original judge stopped B14 outputs stored in valid subfolders or carrying
unprescribed swatch display names. B15 repetitions three and four retained the
complete successful CLI response around their dry-run result. Tested corrections
now admit those choices, retaining all native controls, source/profile identities,
preview pixels, review proposals and history requirements. Additional print-loss
disclosures are accepted only when every required limitation remains present.
Native receipt binding is checked under the existing engine-only history check;
the common artifact check remains independent. No check ID or class was removed.

B14 Inkbolt repetitions two and five still select snapshot publication receipts
in session.json. Correct PDF receipts also exist, but the judge must verify the
delivered request ID, not silently choose another. Their artifacts and saved
history otherwise pass; the complete workflow remains failed. This identifies
receipt selection and clearer delivery guidance as follow-up work, not corrupt
PDFs or broken session history.

After focused Windows/WSL checks, all twenty original captures were imported into
new judge directories. Original reports and every original workspace, transcript,
client result and capture identity were checked, as were imported workspace bytes,
usage, execution times and captured memory. No model attempt was rerun or removed.
Evidence is under `w2-print-resources-sol-{model,baseline}-five-01`, corresponding
`rejudged-03` roots and `w2-print-resources-capture-rejudge-integrity-03.json`.
The first correction and intermediate PDF-reader reports remain retained as
`rejudged-01` and `rejudged-02`; their report identities are also unchanged.

All completed direct commands and MCP arguments were reviewed. File-change helper
bodies omitted from event logs were read and archived; inline creation/edit
commands remain available for deleted helpers. No direct prohibited access was
observed. This is not authenticated isolation or complete nested-process evidence.
Inkbolt B14 repetition two used MCP schema tools; the other Inkbolt trials used
CLI commands. No image-view tool call was observed, so numerical pixel checks do
not establish visual review. Full model/engine call counts, traffic/retries,
first verified preview time and engine-only memory remain unknown. Observed
client-tree memory has a separate scope.

These results reinforce operation discovery and workspace guidance priorities.
Finish B17-B20 and review the remaining B01/B07 caveats before the full W2 decision
gate. The separate sister-project comparison and B10 Linux memory evidence remain
open. No engine checkpoint or complete readiness gate gains credit.

| Evidence | SHA-256 |
| --- | --- |
| Original source candidate | `4e36bcaf30056c01e2343a1596caf796204cc775a4e8c4f319bd33b22efb3a89` |
| First tested rejudging candidate | `3e8a23d1dadbe3b1e77f128afd83516fda6e7a0055bd89a48efb259d6daacb6d` |
| Final tested rejudging candidate | `94a18f910c738e3f2ff1f3949ecf081046a459506ec137a432eb6a3bb4a95024` |
| Release executable | `3fc78f0f7eb5d3273ad693e1f2726cb9fc4fe1cb837bb1dc88367daa4ec15959` |
| Original Inkbolt report | `6b4ad8e0bae50d8e05f57dcc3fcf578002256db8b5caca420c9045671b1f0f0c` |
| Original baseline report | `b0e084662a8b05395495bee8ec447e8862dbc4c20ac2211330835b24e48cb600` |
| Original comparison | `04b595810e96b7c82cc45feca8a40005383c887616378c43c0b52caac3726288` |
| Final rejudged Inkbolt report | `983965514e72661f02a05d6634088a7d0b49b214fb8de813a02719e8e120b77f` |
| Final rejudged baseline report | `5790ddd9509286d35d314ebd78a251a37afd3a44dc39892393ff0c3ddb7b0342` |
| Final rejudged comparison | `1f2be28adb7fa535d53842fc171a2b4d846ec7d22515998d671e242acdfe8655` |

## B16 at 3c52ce4: preliminary text-repair trials

Five attempts per arm used Codex CLI 0.160.0 with externally selected
`gpt-6.1-sol`, medium effort, and the same pinned baseline tools as the preceding
batches. Inkbolt ran first, then the baseline on the shared Windows host. Inputs
and the engine stayed unchanged, with no concurrent local engine verification
or benchmarks from this chat. Other host workloads were uncontrolled and caches
could be warm. Model selection is evaluation configuration only.

| Measurement, prompt version 1 | Inkbolt | Baseline |
| --- | ---: | ---: |
| Retained attempts | 5 | 5 |
| Original complete passes | 0/5 | 0/5 |
| Complete passes after default-field correction | 1/5 | 0/5 |
| Median input + output tokens, all attempts | 481,327 | 129,382 |
| Median client execution, seconds, all attempts | 114.6 | 94.3 |

The first four Inkbolt attempts saved hand-written repaired recipes without a
revision field. Reopening them yields revision 0, so they do not deliver the
committed revision-1 source. Those failures remain. Attempt five saved revision
1 correctly but omitted ordinary default fields. Its independently reopened
before/after documents already matched the complete expected states; the judge
incorrectly required the raw JSON to include every serialized default. Comparing
the reopened values corrects that restriction while preserving exact controls,
revision, fonts, pixels, proposals and durable history. Tested negatives still
reject missing/stale revisions, altered resolution and changed artwork.

The baseline recipes used alternative font containers, tagged paint objects,
string wrap controls or base64 font data in the byte-length field. The judge
rejects those forms, but the version-1 prompt did not fully specify their JSON
types. These results therefore do not establish a reliability advantage for
either arm. Prompt version 2 states the types and native snapshot revisions
explicitly, without changing fixtures, check IDs/classes or required outcomes.
The matched version-2 batch below uses that contract in both arms and is not
pooled with these preliminary attempts.

A separate post-hoc diagnostic found all ten review/final PNG pairs exact at
every pixel. That does not waive failed editable-source checks or turn checks
skipped after source refusal into passes. No successful matched pair supports a
cost ratio. All attempts remain in the token/time distributions; cached input is
already included, and client time includes tool work. Full model/engine call
counts, traffic, retries, first verified preview time and engine-only memory
remain unknown. Client-tree memory has a separate observed scope.

All completed direct command bodies, including inline helper creation/edits,
were reviewed. No direct prohibited access or image-view call was observed;
this is not authenticated isolation, nested-process attestation or visual review.
All ten original captures, reports, workspace files, transcripts, usage, times
and memory observations remained unchanged during rejudging. Evidence is under
`w2-repair-sol-{model,baseline}-five-01` and corresponding `rejudged-01` roots,
with `w2-repair-capture-rejudge-integrity-01.json` and arm-review records.
This advances benchmark preparation and snapshot-delivery guidance; no engine
checkpoint or complete readiness gate gains credit.

| Evidence | SHA-256 |
| --- | --- |
| Original source candidate | `429238a8bdc98f74a71f985cadc0e8f6fd2bd8545e2208b28f398034280e5885` |
| Tested default-field judge | `b145613796e741388e7ca9599db61ae8d67957247010e5d5bb8400e2ec2aa2a5` |
| Release executable | `3fc78f0f7eb5d3273ad693e1f2726cb9fc4fe1cb837bb1dc88367daa4ec15959` |
| Original Inkbolt report | `ed11b72ff22cab8c2fbf5d866833e2996964dae9948331d22eb1fc55209c8f61` |
| Original baseline report | `52ff8cbd110e454da73acecb647e65ee510bebc0b6b755c38e9a7b950483fa13` |
| Original comparison | `9997c4a7d37625eb84064a7cfc0696fcfb199ef18746ba0b46a280d36d17812a` |
| Rejudged Inkbolt report | `f823f698f2749a6e1a189bbe3da6d3919d8947947b7e376222144c739bc84367` |
| Rejudged baseline report | `da500971d4d94e13b97dd3873aba7654e47da66ce52728e2dc3593b1434e0618` |
| Rejudged comparison | `b76ede6bd8f1ede6cf5852e84c80413fe4b8e630f576e66e3e42afdac8100fa8` |

## B16 at a048690: explicit version-2 repair contract

Both arms passed all five artifact trials under prompt version 2. All five
Inkbolt trials also passed the proposal, saved-revision and durable-publication
history checks. The baseline's engine-specific history check remains not
applicable. No B16 judge correction or prompt change was needed for this batch.

| Measurement, five attempts per arm | Inkbolt | Baseline |
| --- | ---: | ---: |
| Artifact passes | 5/5 | 5/5 |
| Median input + output tokens | 584,833 | 130,703 |
| Median client execution, seconds | 112.9 | 82.4 |

Median token use was **4.47x** the baseline's. Cached input is already included
in input tokens; this is not a billing-cost ratio. Five equal outcomes do not
prove reliability equivalence: the 95% Wilson interval is approximately
0.566-1.000 for each arm, assuming independent trials. Under the fixed policy,
this task supplies another signal to reduce interface cost. Completed traces
show repeated schema/definition searches, full-schema fallbacks and workspace
path corrections. These observations motivate changes, but do not isolate how
much of the cost any single change would remove. Remeasure after implementation.

Commit `a048690fa443dfb57a986d1a4d5dc38b8bc740fc` and prompt
`f3cf3d806e477b57d847130050c063be0636ed53d207cfe756ec78d9ef0abd85`
stayed fixed. Both arms used externally configured Codex CLI 0.160.0 with
`gpt-6.1-sol`, medium effort. Baseline tools remained resvg 0.47.0 and Pillow
12.3.0. Model selection is evaluation configuration only. Inkbolt ran first,
then the baseline, on the same shared Windows host without concurrent local
engine verification or benchmarks from this chat. Other host workloads were
uncontrolled, caches could be warm, and order was not randomized.

All completed direct commands, inline helpers and retained scripts created by
file-change calls were reviewed. No direct prohibited access or image-view call
was observed. This is not authenticated isolation, complete nested-process
attestation or visual review. Numeric pixel checks and independent artifact
judging remain distinct from seeing the image. Full model/engine call counts,
traffic, retries, first verified preview time and engine-only memory remain
unknown; observed client-tree memory has a separate scope.

The 487 retained files under `w2-repair-v2-sol-{model,baseline,comparison}-five-01`
have a complete hash inventory in `w2-repair-v2-complete-hashes-01.json`;
arm-review records retain trace and helper identities. Version-1 failures remain
separate. B17-B20, further smaller-model trials, complete metric coverage and
the sister-project comparison remain open. No engine checkpoint or complete
readiness gate gains credit.

| Evidence | SHA-256 |
| --- | --- |
| Source candidate | `17387bb11cd57c5a0624516de999355a698858c8bd0e657b60063a0583d33af5` |
| Release executable | `3fc78f0f7eb5d3273ad693e1f2726cb9fc4fe1cb837bb1dc88367daa4ec15959` |
| Inkbolt report | `5678475448a41cc96e7cbb6d3c00fb6873b536cda15906fcb66032006b4bf35e` |
| Baseline report | `b340d8340f9c0312a2d57d12794f59523f4d3e0c2abc39e6a223fa67798322da` |
| Comparison | `6772c4e6ceb20b8341d1c48f21588214b121965e2756db87b4be32e20a7b5cd9` |

## B17/B18 at cae530a: receipt and concurrent-edit recovery

Five genuine attempts per task exercised recovery from a withheld editing
response and recovery from another writer's intervening change. Both tasks
passed all artifact checks. B17 passed its complete workflow in three attempts;
B18 passed all five. Their no-engine baselines remain explicitly not applicable,
so these results establish no comparative advantage or full-suite acceptance.

| Measurement, five attempts per task | B17 lost response | B18 concurrent edit |
| --- | ---: | ---: |
| Artifact passes | 5/5 | 5/5 |
| Complete workflow passes | 3/5 | 5/5 |
| Median input + output tokens | 269,176 | 249,608 |
| Median client execution, seconds | 94.6 | 125.0 |

B17 attempts 1 and 3 put the CLI's `ok`/`result` envelope where
[the prompt](../tools/benchmark_prompts/B17.md) explicitly requires the compact
result itself. Their `original-receipt` and `retry-idempotent` checks failed with
`KeyError: document_ref`. Edited pixels, restored source, undo preservation and
history checks passed. These remain failed deliveries; the receipt contract was
not relaxed and neither attempt was replaced. B18 preserved the other writer's
edit and passed stale-request rejection, proposal, source, pixel and history
checks in every attempt.

All ten attempts remain in the totals, including the two failures. Cached input
is included in input tokens and is not added again. Client execution includes
startup and tool work. Full model/engine call counts, traffic, retries, time to
first verified preview and engine-only memory remain unknown. Observed
client-tree memory is retained under its separate scope. Five trials cannot
establish general reliability; even 5/5 has a 95% Wilson interval of approximately
0.566-1.000, assuming independent trials.

Commit `cae530a9986cbb056616d7cf7ed6a0e311529ab1`, both version-1 prompts,
the executable and source candidate stayed unchanged. The external configuration
selected Codex CLI 0.160.0, `gpt-6.1-sol`, medium effort. These settings describe
this evaluation only. Tasks ran sequentially, rotating order by repetition, on
the shared Windows host. This chat ran no other local engine verification or
benchmarks during measurement; other host workloads were uncontrolled and
caches could be warm.

Every completed direct command and inline helper was reviewed. No prohibited
direct access or image-view tool call was observed. Some solver-authored
transcripts reconstruct earlier responses; the retained driver event traces
are separate evidence, and reconstructed text is not authenticated telemetry.
This review does not establish isolation, complete nested-process attestation
or visual inspection. Independent artifact judging remains separate.

The comparison retained all ten not-applicable baseline rows and both native
failures, with no global matching issues. Its exit 2 correctly reports the lack
of applicable baseline pairs. The external batch wrapper incorrectly expected
exit 0 and exited 1 after writing all reports; no trial was restarted. The
wrapper error and original reports are retained.

The 746 files under `w2-retry-conflict-sol-{model,baseline,comparison}-five-01`
have a complete hash inventory in `w2-retry-conflict-complete-hashes-01.json`.
`w2-retry-conflict-model-arm-review-01.json` records trace and helper identities;
`w2-retry-conflict-summary-01.json` retains task statistics and batch outcomes.
Repeated workspace/path corrections and discovery searches, together with the
receipt-format failures, reinforce the existing priority for actionable errors,
focused discovery and snapshot/receipt delivery guidance. Remeasure after changes.
B19/B20, broader metric coverage, smaller-model trials and the separate
sister-project comparison remain open. No engine checkpoint gains credit.

| Evidence | SHA-256 |
| --- | --- |
| Source candidate | `3f199ad5c1f30cf1d6ccc7569d586a897fa248d6e62acee9887d88d98c12c064` |
| Release executable | `3fc78f0f7eb5d3273ad693e1f2726cb9fc4fe1cb837bb1dc88367daa4ec15959` |
| B17 prompt | `f575638fd7aeda0c5faaee06affa8eec1297b006aa0824e5edffc373d57be4e6` |
| B18 prompt | `5b604b46bd953456eddb22e87e08751ba41a3c0d9e8dca39bf02fb7cf99049ef` |
| Native report | `55914818081c13dd82605ba6cd508768584f6889f3c712e4d28f539cb6ac8cb7` |
| Not-applicable baseline report | `5c5730689621b479cb069c522068a68087fb3f2d28ff2aaf162411216d05bf1c` |
| Comparison | `64d1e1f895aa6684bb0046909ba962a1b529b3af9e1c5e1827494ee749b9db3d` |

## B19 at 2cf3869: retained evaluation setup failures

All five genuine attempts failed before issuing an engine command. Each trace
records a `PermissionError` when the supplied bridge tried to create its first
control-channel request outside the client's writable workspace. Harness lifetime
accounting confirms zero engine processes and no leaked processes for every
attempt. These are evaluation setup failures, not evidence of job-recovery
reliability. The five baseline rows remain not applicable.

The source stayed fixed at `2cf3869d2a6ab98de6fb497851339d4ca93973ca`, candidate
`e71211286f39516068bfe297560e87cf41b3fbde7dc53bd4faa2a31ae03fb7b1`, using
version-3 prompt `ed2b7ba79fa7a76daff271f792c19153f1570d1793ceaf8ba8616c493c483886`.
External settings remained Codex CLI 0.160.0, `gpt-6.1-sol`, medium effort.
All completed direct commands were reviewed; no prohibited direct access or
image-view call was observed. This is not authenticated isolation. All 65 files
under `w2-job-recovery-sol-{model,baseline,comparison}-five-01` are hashed in
`w2-job-recovery-setup-failure-hashes-01.json`; the companion review records trace
identities and zero-process observations. None of these attempts was replaced.

The adapter now grants the exact validated control-channel folder through
`--add-dir`, while retaining the client's sandbox and excluding the enclosing
evidence directory. A genuine pilot must verify that correction before another
batch; source changes and later results remain separate from this failed setup.

| Evidence | SHA-256 |
| --- | --- |
| Native report | `55cc71a4105c22d9b5481b6c080ee5a54924a31281f1cc75f4f3ceda8bc96dc7` |
| Not-applicable baseline report | `8cd835415e481c562daaa3aca811121085e0ca332327bc7ea5af7da7496a085f` |
| Comparison | `821948612b33097741d4cf5f9ae75de371b23b476038865e0a64bd915483080a` |

## B19 at 5079c5a: bridge pilot and publication observation gap

The genuine pilot confirmed that the narrow directory grant lets the client
reach the engine. It delivered the requested files and passed the independent
preview/recovered-pixel, cancellation, interrupted-state, revision/resource,
history and source-preservation checks. The complete trial still failed.

During discovery, the client put `command` inside bridge arguments as well as
at message level. This malformed message triggered a controller protocol error;
later successful operations do not erase it. Separately, the client validly used
`session.publish` for the required overwrite refusal. The controller recognized
only `document.publish`, leaving the final output checkpoint absent and failing
the publication/no-partial-final checks. A synthetic run reproduced that missing
checkpoint without the malformed request.

The controller now observes either valid publish command and explicitly rejects
reserved nested fields before engine execution. The pilot remains failed; no
checkpoint is invented afterward, and its capture is not used as passing workflow
evidence. A new batch uses the corrected controller and retains this pilot
separately. Native and baseline task criteria are unchanged.

The pilot used commit `5079c5a4fe0f24387571556fd275c0503f8a0119`, candidate
`d1166a0fd05568e97e663c30068be00e0e8da323ff4a8ae52cc5b37b09a214f3`, the unchanged
version-3 prompt and the previous external client/model settings. Inputs stayed
unchanged. Its report SHA-256 is
`96ef4d6130fbfe6138f06df5f3811ab675d52d93c4dc02b186c55c2a610dde3c`.
All 254 files under `w2-job-recovery-bridge-pilot-01` are hashed in
`w2-job-recovery-bridge-pilot-hashes-01.json`. The companion review records all
39 completed items and the two retained helper files. No prohibited direct access
or image-view tool was observed; numeric pixel checks are not visual inspection,
and direct traces/final helper hashes do not authenticate every nested operation
or intermediate helper version.

## B19 at 30ecf5b: five recovery attempts with protocol failures

All five genuine client attempts remain failed overall. The first four passed
all nine independent artifact, recovery and source-preservation checks. The fifth
saved its preview and editable source but never admitted a cancellation job;
only source preservation was scored, with eight checks missing. This is 0/5
complete workflows, not a recovery reliability claim or completed model batch.

Attempts 1, 3 and 4 supplied a reserved nested `command` field while discovering
schemas. Attempt 2 first used an inline snapshot without its resource binding,
then attached an unsupported retry annotation to a fault control. Attempt 5
repeatedly supplied an extra `resources` field and varied the cancellation
destination; it finally requested the queue gate before successful cancellation.
The broad destination error did not identify that extra field. Later successful
commands cannot erase a controller protocol failure. No criterion was relaxed.

The controller rejected each attempt before accepting its driver evidence, so
the reports retain `model_trials:false` and unknown accepted usage, timing,
engine-count and memory aggregates. Genuine client execution and directly judged
artifacts are retained separately; unvalidated client-result files are not
promoted into accepted metrics. Harness process accounting records 44, 45, 57,
65 and 13 owned processes respectively, all exited with no observer error.

The five baseline rows are not applicable. The comparator reports no matching
issues but is not decision-ready; its expected exit 2 is preserved. Runs used
commit `30ecf5b2442902db23364c5f0a2ea4cd6ed85ec4`, the unchanged version-3 prompt,
and the same external Codex CLI 0.160.0 / `gpt-6.1-sol` medium configuration.
Inputs stayed fixed. Trials ran sequentially on the shared Windows host with no
concurrent local engine verification or benchmarks; caches could be warm.

All completed direct commands and retained helper files were reviewed. No
prohibited direct access or image-view call was observed; numeric pixel checks
are not visual review. Trial 3 manually reconstructed its returned-value file;
this remains distinct from harness observations. Final helper hashes and direct
traces do not attest every intermediate version or nested operation.
The 1,305 files under `w2-job-recovery-sol-{model,baseline,comparison}-five-02`
are hashed in `w2-job-recovery-complete-hashes-02.json`, with companion arm review
and summary files. Earlier setup and pilot failures remain separate.

Prioritize actionable discovery errors, saved-reference and snapshot guidance,
and precise bridge argument errors before remeasuring this workflow. B20,
accepted metric coverage and full W2 acceptance remain open. No engine
checkpoint receives additional credit.

| Evidence | SHA-256 |
| --- | --- |
| Source candidate | `3c9e4d73ed167cee08e03993b213e576e894af8aed1e75caad46bfdf4f6ddd08` |
| Release executable | `3fc78f0f7eb5d3273ad693e1f2726cb9fc4fe1cb837bb1dc88367daa4ec15959` |
| B19 prompt | `ed2b7ba79fa7a76daff271f792c19153f1570d1793ceaf8ba8616c493c483886` |
| Native report | `835a4c4dd806dbeb6c27700005af0e1575656208b34249d256fedfba45ea1543` |
| Not-applicable baseline report | `fc319d392ced4b6694d67eb04ce43bf936591e8e239f4776b25bb328a5aa9f47` |
| Comparison | `35ff00fe37146565b910be7e73b21bc45a47bfbad124bb0204986c9d93be8a4d` |

## B20 at fe7786d: linked-graphic delivery prerequisite failures

The first genuine five-pair B20 batch passed **0/5 complete native workflows**
and **5/5 baseline workflows**. Native artifact quality remains unjudged: only
source preservation was scored, with fifteen checks missing per native attempt.
The baseline passed its seven task artifact checks plus source preservation;
its eight engine-specific checks are not applicable. This is a workflow failure
signal, not a finding that native rendered pixels failed comparison.

All five native attempts used `session_id:"linked-graphic"` instead of the
required `"work"`; the prompt assigns `linked-graphic` to the document ID.
Attempts 2-5 passed driver-evidence validation but failed the judge's session-store
prerequisite. Attempt 1 also requested consumer `media.inspect`, outside the
bridge allowlist, causing a fatal protocol failure. The prompt instructs use of
public discovery but does not disclose that exact allowlist. Preserve this setup
limitation and failure; a later prompt/control clarification needs a separately
versioned run. Neither the allowed commands nor the session-ID requirement was
waived afterward.

Trace review also found nondefault item names in attempts 1-4 and a stale-error
envelope instead of the requested error object in attempt 5. These observations
receive no independent artifact/history score because earlier prerequisites
stopped judging. Delivered files and client assertions cannot supply that credit.

| Observation | Native arm | No-Inkbolt baseline |
| --- | ---: | ---: |
| Retained attempts | 5 | 5 |
| Complete applicable workflow | 0/5 | 5/5 |
| Attempts with accepted driver metrics | 4 failed attempts | 5 successful attempts |
| Median input + output tokens in that accepted subset | 1,029,586.5 | 326,203 |
| Median client execution, seconds | 237.3 | 138.5 |
| Median total engine commands | 54.5 | 19 |

Native total command counts include Inkbolt and the consumer; baseline counts
include only the consumer. The baseline authored graphics with pinned Pillow
and used the same consumer to render the required videos. Native work includes
additional revision/history guarantees. These are observations of different
outcomes and applicable scopes, not cost per successful native workflow.
Input totals include cached context and are not billing estimates. Attempt 1's
unaccepted client-result metrics stay excluded; native time to first independently
verified preview is unknown. Reports retain traffic, retries and the distinct
engine, consumer-tree and client-tree memory scopes.

Both arms used commit `fe7786d1eaad316e5986edf0b804cac228481ebd`, unchanged
version-2 prompt, Codex CLI 0.160.0 and the same external `gpt-6.1-sol` medium
configuration. Model choice remains external evaluation metadata. All five native
attempts ran before the five baseline attempts, sequentially on the shared
Windows host with no concurrent local engine verification or benchmarks. Inputs
stayed unchanged; order was not randomized and caches could be warm.

All completed direct commands and final retained helpers were reviewed. No
prohibited direct engine/evidence access or image-view tool was observed.
Numeric pixel/hash assertions are not visual review, and these traces do not
authenticate every intermediate helper version or nested operation. Consumer
lifetime accounting observed 525 native-arm and 353 baseline-arm processes,
including inherited encoders/probes, all exited with memory observation available.
Those counts exclude other engine/client trees and are not command counts.

All 3,019 files under `w2-linked-animation-sol-{model,baseline,comparison}-five-01`
are hashed in `w2-linked-animation-complete-hashes-01.json`; companion review and
summary records bind the ten traces and retained helpers. The comparator reports
no matching issues and categorizes B20 as a losing task by workflow completion.
Its full-suite `decision_ready`, `matched_model_baseline_complete` and
`actual_model_benchmark_complete` gates remain false. B19/B20 guidance repairs
and the trace-motivated B03/B16 discovery remeasurement remain separate next steps.
No engine-checkpoint credit changes.

| Evidence | SHA-256 |
| --- | --- |
| Source candidate | `3514eda7f794db9083a3a300e11ef126d155162d118541b561103eceb2b37433` |
| Inkbolt release executable | `3fc78f0f7eb5d3273ad693e1f2726cb9fc4fe1cb837bb1dc88367daa4ec15959` |
| B20 prompt | `ca5e7d5b97f0e8fecb605c203fea6e195066f9b5cf8183972f77d830eeae62a8` |
| Consumer executable | `3d9aa4644525c84108b9ec276605595e3d115b6d1fc8d4523b7a48a934f5f536` |
| Native report | `d51c73faba3bba6ea0a8be4f802c4dcafa9ca2a45d1ed3e70c94226bf8d40f40` |
| Baseline report | `f5e84eb6ae82f2b4604f8f8ceac3ca6618ac553c0dd9d0c1fb59af4c6988badf` |
| Comparison | `71b23175cc57ef35d5cd30cd5ce9e9f986fadb5ba92d4fa9f8290b45b64f17cd` |

## B03/B16 at d34851e: nested discovery follow-up

All twenty attempts passed: five per task in each arm, including every applicable
artifact and workflow check. The native arm also passed its separate history and
revision checks. Five successes give a 95% Wilson interval of 56.6%-100%; this
small sample does not establish equivalence or a reliability advantage.

| Task | Native / baseline passes | Native median tokens | Baseline median tokens | Token ratio | Native / baseline median seconds |
| --- | --- | ---: | ---: | ---: | ---: |
| B03: 5,000-object layout | 5/5 / 5/5 | 300,182 | 65,030 | 4.62x | 111.2 / 43.0 |
| B16: text overflow repair | 5/5 / 5/5 | 574,154 | 110,396 | 5.20x | 160.9 / 105.6 |

B03 token ranges were 244,561-322,369 native and 62,799-70,794 baseline; B16
ranges were 471,075-635,301 and 96,052-154,251. Input totals include cached
context; cached and reasoning tokens are not added again. These are not billing
ratios. Client time includes startup, authoring and tool work, not just engine
execution. Complete engine/model call counts, traffic, retries, first independently
verified preview and engine-only memory remain unknown. Client-tree memory is a
separate observation. Both tasks remain losing tasks under the fixed token policy.

### Comparison with the earlier native batches

The earlier B03 and version-2 B16 batches used the same prompts, client, model and
settings. Both already passed 5/5. They ran on different revisions and at different
times, so this is an observational comparison, not randomized causal attribution.

| Task | Earlier / current median tokens | Change | Earlier / current median seconds | Change |
| --- | ---: | ---: | ---: | ---: |
| B03 | 349,212 / 300,182 | -14.0% | 128.9 / 111.2 | -13.7% |
| B16 | 584,833 / 574,154 | -1.8% | 112.9 / 160.9 | +42.5% |

The visible error inventory finds fewer schema-error occurrences: B03 shell
outputs fall from six to three, plus two earlier MCP errors and none currently;
B16 shell outputs fall from two to zero. These count distinct error codes per
completed output event with a complete JSON envelope. Repeated reads can repeat
errors, truncated outputs are excluded, and the transport mix differs. They are
not complete engine-call or retry counts. All ten current native attempts use
CLI; one earlier B03 attempt mixed CLI and MCP. Full-schema and broad capability
requests remain, alongside path and request-field mistakes.

Retain the working nested selector contract, but stop broadening discovery under
the recorded stop condition. The mixed time/token signal and missing call metrics
do not justify a general efficiency claim. Address demonstrated request-field,
path and snapshot/reference friction separately. B19/B20 prompt and controller
guidance are separate versioned follow-ups; none of their previous failures changes.

### Conditions and retained evidence

Both current arms used `d34851ef5ec8f43acf4457826c6fa407f5d36189`, unchanged B03
version 1 and B16 version 2 prompts, Codex CLI 0.160.0 and the same externally
configured `gpt-6.1-sol` medium settings. Model names remain evaluation metadata,
with no engine or harness default. The current driver's only change from the
earlier driver grants a bridge directory for B19/B20; neither of these tasks gets
that bridge. Baseline tools remain pinned resvg 0.47.0 and Pillow 12.3.0.

Native attempts ran before baseline attempts, sequentially on the shared Windows
host, with rotating task order. This chat ran no concurrent local engine checks
or benchmarks. Other host workloads were uncontrolled and caches could be warm.
Both reports confirm unchanged inputs. Every completed direct command and final
retained Python helper was reviewed; no prohibited repository/judge reads, other
engine or additional model access was observed. No image-view tool was observed.
Numeric pixel/font/hash checks do not establish visual review or authenticate
every intermediate helper version and nested operation.

All 715 raw files under the external
`w5-nested-discovery-sol-{model,baseline,comparison}-five-01` roots are hashed in
`w5-nested-discovery-complete-hashes-01.json`. Earlier per-trial inventories were
rechecked unchanged. Companion review and summary records retain all twenty
attempts. The comparator finds no matching issues; `actual_model_benchmark_complete`,
`matched_model_baseline_complete`, `decision_ready` and `matched_cutbolt_comparison`
remain false. No checkpoint credit changes.

| Evidence | SHA-256 |
| --- | --- |
| Source candidate | `4626af3ad8a6023683a54d9cf441d3dd83c81b93d547b429979675da91027081` |
| Release executable | `c4e06dff137c3c710b9837f0d02900b0b5243f732092ca4d0706cb7791b9f281` |
| B03 prompt | `3e72bb258a2b271bf6722bd290bc8c2e481b31c905c0dd9e085d86fbab9c4c3d` |
| B16 prompt | `f3cf3d806e477b57d847130050c063be0636ed53d207cfe756ec78d9ef0abd85` |
| Native report | `589aa15b08e57691db94879d42bcb81ebfccaaf179b6a24ee625a8d9521614d1` |
| Baseline report | `f3172498f91405b221d34422f101db2412826e499cc628e3cd25cb635c8cf8d7` |
| Comparison report | `4caa8a2bef19610db1b9d287164c00ee91333e2d4236c799c229e4ad13951cae` |
| Raw evidence inventory | `2306d4b69eef8c6814d8b0a6fcb48a8335382a8984513daafed2fe23a5fbc842` |

## B19/B20 at 1d5b960: guidance pilots and observation corrections

One native B19 and one B20 attempt per arm used prompt versions 4 and 3,
respectively, with the same external Codex CLI 0.160.0 / gpt-6.1-sol medium
configuration as the preceding trials. Model selection remains external
evaluation metadata. Source and executable identities stayed unchanged.
All three runs have accepted model evidence and no driver failure; B19's
baseline remains not applicable.

B19 passed five checks, including all four artifact/source checks, and failed
four engine checks. The agent manually wrote `attempts.json`; fifteen fields
across seven retained objects differ from actual bridge replies, all process
creation integers. For example, `134364244084953616` became
`134364244084953620`. The raw command outputs retain the exact integer.
The evidence locates the mismatch at the saved objects but does not establish
which hidden client/model step introduced rounding. Keep the failure; exact
process identities cannot be relaxed. Next measure programmatic preservation of
returned objects without manual reconstruction. The run used 1,586,239 total
tokens, 31 engine commands and 237.93 seconds, with a verified preview at 97.52s.

B20 originally failed both arms because of judge defects. The native agent read
the current consumer head immediately after relinking; its actual response was
revision 2, but role lookup demanded an explicit revision argument. The baseline
retained unchanged `inspection.json` files inside both deliveries; the judge
mistook the extra files for changed required files. The corrected judge binds
head reads to the observed revision and pre-undo order. Both arms still require
every mandatory file, and now check every additional observed file for unchanged
bytes as well. Wrong revisions, late reads, missing or altered files still fail.

Rejudging copied, unchanged captures passes all sixteen native checks and eight
baseline artifact/source checks; eight baseline engine checks remain not
applicable. No agent reran, no output was repaired, and original failures remain
retained. Solve metrics and controller captures match the originals exactly:

| B20 arm | Total tokens | Agent seconds | Combined engine commands | Verified preview time |
| --- | ---: | ---: | ---: | --- |
| Inkbolt | 978,624 | 184.50 | 57 | Unknown |
| Baseline | 287,125 | 131.43 | 19 | Unknown |

This one-pair artifact tie at 3.41x tokens is a pilot, not repeated acceptance or
evidence of a reliability advantage. It does not replace or pool with the older
five-pair prompt. All 98 completed trace items and fourteen retained Python
helpers were reviewed. No prohibited repository/judge reads or additional engine
or model access was observed; numeric image checks do not establish visual review.

The original 957 files are retained under `w2-bridge-guidance-`; the 329 rejudge
files are under `w2-handoff-observation-rejudge-`. Both source inventories were
checked unchanged. Focused regression/lifecycle/verifier checks passed on Windows
in 66.1s (40 Python tests) and WSL in 18.3s (30 executed, ten explicit Windows
process skips), with seven fresh stages each and no failures or pending checks.
This does not establish full W2, current full-suite acceptance or checkpoint credit.

| Evidence | SHA-256 |
| --- | --- |
| Original source candidate | `d8f5ce14e0a3c7d81a2d6f1d9db7e7f37314ffa8cd4ea8f4d33329a61068f3c9` |
| Release executable | `c4e06dff137c3c710b9837f0d02900b0b5243f732092ca4d0706cb7791b9f281` |
| Original complete review | `7f15837ce015378732f2313a09e699d7e6aeb8ea35996f7795c2c2be48b9731c` |
| Rejudge review and inventory | `1c9fa7a6ae595b7bebb52faa511cfb802627cde3337dbbcf7d5657ce0cc67753` |
| Native rejudge report | `c458908a0be842bf22f6dad19e848796287e7f68185d05297e39c0aa4d68ba85` |
| Baseline rejudge report | `9c80c63efc3f145df69cefead42210f6d8ada8fd6af74b07d68f86e0526f757b` |
| Focused verification inputs | `e35f8374bc7040c22a69e77b14ecc0753413a94f2d29622b223b0d8e6223fa92` |

## B19/B20 at f61d952: recovery pilot and five-pair handoff follow-up

B20's prompt-3 follow-up passes **3/5 native workflows versus 5/5 baseline**
after a tested judge correction. Original full-workflow scores were 1/5 and 5/5;
artifact success was already 3/5 and 5/5. Repetitions 2 and 3 attempted a different
stale mutation, as the prompt permits, but the original judge additionally
required the relink's operation list. The corrected check requires a nonempty
mutation of revision 1 in the same saved project/store and the actual recorded
`REVISION_CONFLICT`. Exact retry still repeats the entire relink request and
returns its saved receipt. Undo, restored snapshots and history checks remain.

All ten captures were imported and rejudged without launching a client or
repairing artifacts. Original solve metrics and all 4,171 original evidence files
were checked unchanged. The new reports retain the two remaining native failures:
attempts 4 and 5 changed `/variants/base/1/value` from `true` to `false` in the
required source base. This violates exact source/history preservation. Both runs
retain all twelve observed delivery files unchanged; the reported immutable-file
failure cascades from an earlier source assertion preventing complete inventory
collection. It is not evidence that delivered files were overwritten.

### Outcomes and costs

Both arms retain eight artifact/source checks. Eight additional native engine
checks remain not applicable in the baseline. Every attempt, including failures,
is included in the following distributions; no earlier pilot or prompt is pooled.

| Measurement | Inkbolt arm | No-Inkbolt baseline |
| --- | ---: | ---: |
| Artifact and complete applicable workflow success | 3/5 | 5/5 |
| 95% Wilson interval for artifact success | 23.1%-88.2% | 56.6%-100% |
| Median input + output tokens | 1,065,545 | 280,910 |
| Token range | 768,825-1,664,926 | 237,737-357,983 |
| Median client execution, seconds | 209.790 | 115.934 |
| Client execution range, seconds | 185.140-263.562 | 100.889-120.825 |
| Median combined bridge engine commands | 60 | 19 |
| Median bridge request / response bytes | 43,922 / 588,125 | 7,426 / 111,580 |
| Median combined bridge retries | 1 | 0 |
| Median Inkbolt process peak commit, bytes | 11,239,424 | Not applicable |
| Median consumer job-tree peak commit, bytes | 110,239,744 | 110,579,712 |
| First verified preview, median seconds | 140.779 (4/5 observed) | Unknown |

Native median token use is 3.79x baseline; median client time is 1.81x. Cached
and reasoning tokens are not added again, and token ratios are not billing
ratios. Time includes client startup and tool work. Native attempts 1, 2 and 5
also invoked the configured encoder/probe directly for read-only media checks;
these are included in client time but outside bridge command/traffic accounting.
Memory scopes are distinct, underlying model-call counts remain unknown, and
first useful preview remains unknown in every attempt. Five trials establish
neither statistical equivalence nor a general reliability or efficiency claim.

The separate B19 prompt-5 pilot programmatically preserved returned objects and
passed all nine independent artifact/recovery checks. It nevertheless failed the
protocol gate: a schema lookup put `command` inside `arguments`, where that field
is reserved for the message envelope; the lookup expects `name`. The retained
error is `Command and step belong at message level, not in arguments`. Later
successful calls cannot erase it. `model_trials` remains false and accepted solve
metrics remain unavailable. No larger B19 batch followed; its baseline is not
applicable.

### Conditions, review and next work

The eleven original attempts used frozen commit
`f61d952f7733ca80eaf75ca377ce5a96d8e14043`, B19 prompt 5, B20 prompt 3 and the
same externally configured Codex CLI 0.160.0 / `gpt-6.1-sol` medium settings
with a 600-second per-trial limit. Model selection remains evaluation metadata,
with no engine or harness default. The baseline used pinned resvg 0.47.0,
Pillow 12.3.0 and Python 3.11; both B20 arms shared the pinned video consumer.
The recovery pilot ran first, then five native and five baseline B20 attempts.
The shared Windows host had no concurrent engine verification from this chat;
other host work was uncontrolled, caches could be warm and order was not randomized.

Completed direct commands and available helper bodies were reviewed. Native
attempt 1 deleted five helpers and baseline attempt 3 deleted `build_delivery.py`;
their bodies are absent from the capture, so nested behavior cannot be fully
audited. Native attempt 4 deleted nineteen helpers, but their inline constructions
were retained and reviewed. No repository/judge reads or additional model use
were observed in available commands/helpers. No image-view event was observed;
numeric pixel/hash checks are not visual review. Capture hashes neither
authenticate hidden behavior nor establish a filesystem security sandbox.

The fixed comparison policy flags B20 as losing on artifact success. Keep its
source-preservation and overhead findings open, along with B19 protocol usability.
Proceed to W3a.3 embedded SVG styling under the existing input-admission priority,
without claiming CSS caused these failures. Further prompt tuning is not the next
substantial stream. Full-suite, matched-baseline and separate sister-project
comparison gates remain false; engine checkpoint credit is unchanged.

Focused checks passed in 54.7s on Windows (39 executed, three optional baseline
skips) and 18.3s on WSL (31 executed, eleven Windows-process skips). A separate
Windows run with both real tool configurations passed all six external lifecycle
tests without skips in 53.2s, covering the previously skipped baseline checks.
All stages were fresh with no failures or pending checks. The real consumer test
verifies a different stale mutation while retaining undo/history/exact-retry checks.
These are focused harness checks, not fresh full-engine acceptance.

Original evidence is retained under `w2-recovery-record-pilot-01` and
`w2-handoff-followup-{model,baseline,comparison}-five-01`; the complete review
inventory binds all 4,171 files. Rejudging uses separate
`w2-handoff-stale-rejudge-{model,baseline,comparison}-01` roots, with 1,529 files
in its review inventory. Both sets remain available externally.

| Evidence | SHA-256 |
| --- | --- |
| Original source candidate | `185dbec33e8f9de49afe1679023742011bae4e6b31c66028d20f5fee49e87bbc` |
| Release executable | `c4e06dff137c3c710b9837f0d02900b0b5243f732092ca4d0706cb7791b9f281` |
| B19 prompt 5 | `7752a6b12ca4748875418f211a375c42b123b8f222907b1a915712928ef64892` |
| B20 prompt 3 | `debb75263f2202141f93412d3aeb44206cc2af26f6fe82f22f7995fe72b52e9e` |
| Consumer executable | `3d9aa4644525c84108b9ec276605595e3d115b6d1fc8d4523b7a48a934f5f536` |
| B19 pilot report | `9c61c42bd96d6926a32263a6760d667b356c7839a2ccbe7e0ce0f64c167d7626` |
| Original native report | `ab22c222f75f4b559748e4f28ae3bafb64f285e81df1b5ffbda65ff8f7612594` |
| Original baseline report | `5406a06be71ed622e367204199f94187ba046ef0cd85f61d6b2ba5919a781f08` |
| Original comparison | `93ea37b5c4022c8fa6b84065319635f842b43fca20591dac4eb6802613c4ee44` |
| Original complete review | `5c1ff14395744ede1a8493bd4cd10ee90650879b079d7ee939c35b8868e6f792` |
| Rejudge candidate / focused verification inputs | `f2f7d412de0c52a035f48c6b70dabade35af153d5dd3dfc0240b930733d24014` |
| Rejudged native report | `088cfed0e9e06b84f051725556631d967253a3324e186b8ad8528bf13cc8fffa` |
| Rejudged baseline report | `cc5cea6a47832dfdeebe1325cd02855aa19da9eeb91d1b5ab5a042e29eff8e40` |
| Rejudged comparison | `85b6f4ebf72aa7eed18dbc6a1bac159f6f360b8114f794f1e8911f5f822a0cea` |
| Rejudge integrity report | `03041604a8a915ebce3136e20247e4371e9af06db2b9efa692a9f05a3c90c8d4` |
| Rejudge review inventory | `be67b2bd3a303df954c6d8d654b40ee80b65f295dd3e72346ea6e8092ece160e` |

## B10/B17/B19 at 447bbc2: request-guidance follow-up

Five native attempts per task and five B10 baseline attempts used unchanged
prompts (B10/B17 version 1, B19 version 5) and the same external Codex CLI 0.160.0
configuration, `gpt-6.1-sol` with medium reasoning. These are evaluation settings,
with no engine or harness model default. The native task order rotated over five
repetitions, followed by the baseline batch. The shared Windows host had no
concurrent local engine checks from this chat; other work was uncontrolled and
caches could be warm. Both arms report unchanged source and tool identities.

| Task | Accepted artifact passes | Complete workflow passes | Median input + output tokens | Median client seconds |
| --- | ---: | ---: | ---: | ---: |
| B10 native photograph repair | 3/5 | 3/5 | 580,184 | 128.3 |
| B10 no-engine baseline | 5/5 | 5/5 | 75,230 | 63.7 |
| B17 lost response | 5/5 | 4/5 | 194,428 | 76.4 |
| B19 interrupted output | 4/5 | 4/5 | 569,666.5 (4 observed) | 119.7 (4 observed) |

B17/B19 have no applicable baseline. They were omitted from the baseline
selection, so the comparison preserves that selection issue and does not form
pairs for them. B10 has five matched pairs and no identity issues. Its fixed
comparison policy flags lower artifact success; only three pairs succeeded in
both arms, so no token/call cost ratio is awarded. All-attempt medians include
failures where usage is observed. The 95% Wilson intervals are 23.1%-88.2% for
3/5, 37.6%-96.4% for 4/5 and 56.6%-100% for 5/5; these small samples do not prove
equivalence or general reliability.

### Failures and observed repairs

B10 attempts 2 and 4 received the new missing-`store_root` guidance, then chose
a custom `tiles` store instead of restoring workspace defaults. The required
immutable-base/root contract fails; the independent renderer cannot find pinned
tiles at the required root. Downstream sample, preview, history and memory
checks remain missing. Model-written sample checks do not supply that credit.
Attempt 5 also encountered missing-field guidance and restored the workspace
option successfully. B10 remains 3/5, the same count as its earlier five-attempt
batch. This 2.07 MP task does not establish the larger W4 workload target.

All five B17 attempts encountered missing-`session_root` guidance and subsequently
restored the workspace option. Every independent artifact check passes. Attempt
4 saves CLI envelopes where the prompt requires compact result objects; two
receipt/retry checks therefore fail. The earlier workflow count was 3/5 and its
median tokens/time were 269,176/94.6 seconds. Current counts and medians are
descriptive: intervening engine changes and five attempts do not isolate the
effect of diagnostics.

B19 attempt 1 passes all nine independent checks but violates the controller's
required operation order before the corrected recovery sequence. It remains a
failed protocol/model trial, receives no accepted artifact credit and has unknown
accepted usage. Attempts 2-5 pass the complete workflow. Attempt 5 repairs a
missing `name` in `schema.lookup` with a subsequent `name:"session.create"`
query. The earlier prompt-5 run was one failed pilot, so it cannot serve as a
five-attempt before/after control.

The four accepted B19 attempts have median 30 observed engine commands, 2.5
invalid calls, three retries, 3,636.5 request bytes, 342,539 response bytes and
61.6 seconds to a verified preview. These measurements exclude judge work.
Their median maximum individual engine-process commit is 84,566,016 bytes;
it is not a concurrent sum or client-tree total. B10/B17 engine calls, traffic,
retries, preview timing and engine-only memory remain unknown. All ten B10
client/tool trees have captured process peaks below 256 MiB; the two failed
native workflows still receive no completed memory-check credit. Underlying
model-call counts remain unknown for every attempt.

### Evidence and decision

The comparison reader validated retained requests, client results and transcript
identities without changing a judge or rerunning a model. Manual review covered
reported failures and missing-field repair sequences; a separate inventory
records all completed event types and retained helper hashes. This is not a
complete audit of every helper version or authenticated hidden behavior.
No image-view event appears in the native event inventory; numerical checks do
not establish visual review. Source preservation and independent artifact
checks retain their original criteria.

Retain the bounded missing-field contract and stop expanding this diagnostic
approach on the present evidence. It repairs individual requests, but the batch
does not establish the W5 acceptance requirement of fewer tokens and calls per
successful task without correctness loss. Storage-context and receipt-format
workflow failures, missing metrics, the full twenty-task run and the separate
sister-project comparison remain open. No original engine checkpoint gains credit.

The complete external inventory binds 2,897 files across both arms, their
comparison, the recorded evaluation plan, process exits and review. Every listed
file hash was reread. Source commit `447bbc2e632936f23567552375ec922856e84314`
also passed fresh complete Windows/Linux implementation acceptance before these
trials; that acceptance is separate from model usability.

| Evidence | SHA-256 |
| --- | --- |
| Source candidate | `29c47929d8119c4d984e58664644374390f6ad95d916c83d2981d8fb4800b0af` |
| Release executable | `2b5a6275cb502d4fd31797d990a5b05e409dd3a5f33736356223fe615bac9ad2` |
| Native report | `cc35b8ae41d13128e9967d483dff758f22cd2c90b420c539e6474d0f9c1f6d3d` |
| Baseline report | `5286cf6527ccfb7d4311c23ef19a4000942e9dff39d99df41a7b5c217f402e83` |
| Comparison | `477c6ab2d5113ee6187db773a18b58ab1409a2d1f9e48404b57a5e8ff87fb0a6` |
| Review of failures/repairs | `f7d2155bd39665c8fb3c5ae023dd2c7161cceb00afee0db8300f3df169118470` |
| Complete file inventory | `8cd4ca7dfda26d227f02944d7f847b1df2e5aea005dfc69ad19087966e17e7ce` |
| Windows/Linux implementation audit | `a9935f43fa7275af45c539081a34af28b04714ecd7963de2fc3b67db3ab17e71` |
