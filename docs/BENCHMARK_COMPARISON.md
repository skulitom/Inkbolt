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
