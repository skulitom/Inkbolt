# Practical-scale workload measurements

`tools/measure_workloads.py` builds the current locked release binary and runs original workloads in new external directories. It retains every request, response, engine error, output, source hash, independent correctness result and build log. This is a reproducible A5 baseline tool, not the complete B01–B20 agent benchmark or evidence of autonomous model performance. The original engine registry remains unchanged.

```powershell
python tools/measure_workloads.py --output-root C:\Work\Evidence\scale-run-001 --repetitions 5 --conditions "Sequential local run; no concurrent verification; other desktop work not controlled"
```

The parent directory must exist; the output directory must be new and outside the repository. Nothing is overwritten or swept. The driver retains all artifacts, including failed outputs and original fixtures. Use ordinary Python without optimization: the independent readers contain assertions, and `-O` is rejected. `--case` may select named cases for diagnosis; the report lists that selection and never presents a subset as the full suite. One to ten repetitions are allowed; use at least five for a baseline. Exit **0** means all selected workloads passed, **2** means the baseline was recorded with workload failures, and other nonzero exits mean driver/build failure or invalid changed inputs. A failure is never counted as successful merely because it was expected at the current engine limits.

## Versioned workloads

The initial `scale-v1` suite has seven fixed cases. Each repetition uses new workspaces and synchronous CLI processes. Case order rotates deterministically; filesystem/page caches are not flushed, and the tool makes no cold-cache claim.

The call adapter is versioned separately from these fixed fixtures and outcomes. Default `--adapter native-tiled-v1` opts into native block import and tiled PNG/native-TIFF output. The pure `sparse-5000` case retains the existing sparse whole evaluator; the mixed case uses tiled evaluation. `--adapter legacy-v1` reproduces the original inline import and whole-output calls for comparison. Reports record the adapter per run and per case. Both adapters use exactly the same dimensions, original sources, edit region, history checks, final outputs and independent oracles; no failed case is removed. Different adapters measure different call paths and must be identified when comparing results.

| Case | Required outcome and independent oracle |
| --- | --- |
| `native-control` | Import an original 128×128 RGBA16 PNG, save a session, replace a 2×2 region, inspect the old revision, undo, and verify history. An independent TIFF reader checks every native sample before/after editing and undo, including unchanged surrounding pixels and adjacent 16-bit codes. |
| `native-screen` | Exactly the same native editing/history contract at 1920×1080. Import failure remains visible, and unavailable dependent steps are recorded as blocked. |
| `stored-screen` | Import an original RGBA8 pattern and deliver a 1920×1080 PNG. Independent decoding checks every pixel, all alpha classes, dimensions and unchanged input bytes. |
| `social-square` | Deliver a 1080×1080 colored vector field; independently decode and check every output pixel. |
| `sparse-5000` | Deliver 5,000 distinct editable vector cells on a 1024×1024 canvas; arithmetic constructs the expected complete pixel grid, including transparent unused area. |
| `mixed-5001` | The same 5,000 cells plus a placed 64×64 image with transparent, translucent and opaque pixels. This isolates the mixed-scene fallback and independently checks both artwork types. |
| `print-page` | Deliver a 2480×3508 page at 300 ppi as PDF and PNG. An independent PDF reader checks physical boxes, geometry and color; the PNG oracle checks every pixel. A simple RGB page is not complete print/profile/ink acceptance. |

All sources are original synthetic generators. The native pattern varies across the canvas and contains full 16-bit codes; it is not a representative photographic compression benchmark. The mixed case isolates one important boundary and does not stand in for text, effect, clipping or dense-overlap workloads. Failed cases remain in the denominator when the engine changes; expanding this baseline and the separate twenty-task suite remains required.

## What is measured

Each command records wall time from process startup through JSON transfer, execution and exit, exact input/output byte counts, exit status, structured errors, and retries (zero for these scripted calls). Fixture generation, output decoding, correctness comparisons, report work and release compilation are outside engine time. The first independently correct PNG records cumulative engine-call time to that output; cases without a verified PNG retain `null`. This is not model time or a user-observed end-to-end preview latency. Unknown model calls, tokens and agent time remain `null`.

On Windows, the driver queries the still-owned process handle after exit. [`GetProcessMemoryInfo`](https://learn.microsoft.com/en-us/windows/win32/api/psapi/nf-psapi-getprocessmemoryinfo) supplies lifetime peak working-set bytes and peak committed bytes through [`PROCESS_MEMORY_COUNTERS`](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters). These are OS high-water marks, not periodic samples or heap allocations. Whole-case memory is the maximum of its sequential command peaks. The driver/oracles are excluded; these cases do not launch background job children. A missing backend or API failure is explicit unavailable data, never zero. Other platforms do not yet have verified memory measurement support.

`tests/test_workload_measurement.py` verifies this distinction with an owned process that allocates and frees 32 MiB before exit, compared with a separate no-allocation process. It also exercises actual native edit/history fidelity, failure/blocked-step accounting, incorrect oracles, changed sources, malformed envelopes, owned timeout cleanup and create-only evidence paths. Small harness checks run in ordinary verification; the full release benchmark is a separate sequential run.

Aggregates report all attempts, successes, failures, variance, bytes and observed memory. Successful-task timing/memory distributions exclude failed cases; fast resource-limit rejections cannot improve a success budget. No current latency/memory threshold is inferred from an unsuccessful workload. Record actual machine load and repeatability conditions; this tool does not isolate the computer from other desktop work.

## Measured regression budgets

`tools/workload_gates.py` creates versioned local budgets from a complete successful `scale-v1`, `wide-native-v1`, `native-layout-v1`, `native-filter-v1`, `native-shadow-v1`, `native-retouch-v1` or `native-brush-v1` report. The first requires all seven fixed cases; each additional suite requires its separate original native workload. All require at least five repetitions of every case, every original command and correctness check, unchanged inputs, an optimized binary, and complete positive Windows memory observations. It recomputes metrics from command records; aggregate success claims cannot hide a failed, missing, duplicate, timed-out or retried attempt.

```powershell
python tools/workload_gates.py create --baseline C:\Work\Evidence\baseline\report.json --output C:\Work\Evidence\scale-gate.json --reason "Five complete successful runs under the recorded conditions"
python tools/measure_workloads.py --output-root C:\Work\Evidence\candidate --conditions "Sequential local run; no concurrent verification; other desktop work not controlled"
python tools/workload_gates.py check --gate C:\Work\Evidence\scale-gate.json --report C:\Work\Evidence\candidate\report.json --output C:\Work\Evidence\comparison.json
```

The `scale-regression-v1` policy allows each case a median command-time sum of at most **1.5 times** its baseline median, a slowest-trial sum of at most **2 times** the baseline maximum, and maximum process peak committed memory of at most **1.5 times** the baseline peak. Time budgets round upward to milliseconds and memory budgets to MiB. Every output must still pass its independent correctness oracle. These fixed margins allow ordinary local timing variance; they are engineering regression budgets, not perceptual response targets or a statistical significance claim. First-preview time, response bytes and working-set peaks remain separately observed in the workload report.

The gate pins the adapter, exact bytes of the fixture/measurement driver and its local helper import closure, machine/OS/Python identity, compiler and baseline report/source/executable identities. Engine revisions may change; changed workload oracles, adapters, machines or compilers require explicit review and a new baseline. Missing/incomparable data is `ineligible`, never a pass. A fresh result is bound to both report and gate hashes, and the baseline report itself cannot count as a new regression measurement. Outputs are create-only and external. The tool does not authenticate reports or prevent deliberate fabrication; retain the original trusted raw evidence, conditions and previous failed comparisons. It never automatically loosens budgets or substitutes faster failures.

Each gate covers exactly one versioned suite, including its fixed case names. A wide report cannot replace the seven-workload suite or use its budgets, and the reverse also rejects. Each additional native gate pins its own driver and fixture generator together with the shared measurement module and complete helper closure. Its seven calls and six independent correctness/history/source checks must all be present; the checker never infers them from a success summary. Broader production compositions, streaming native operations, actual model trials and matched sister-project results remain separate A5/A1 requirements. Small synthetic record-validation tests belong to the normal quick suite; full release measurements stay separate and sequential so concurrent test load does not distort engine timings.

## Identity and acceptance

The report records the source fingerprint, complete candidate-file hashes including fixture/oracle code, Git state, toolchain, optimized Cargo artifact and executable hash. Cargo's actual binary path is used. Inputs are rechecked after measurement; changed source, executable or candidate files invalidate the report. Raw evidence stays externally, and a later commit can be associated only after the exact tested bytes are checked again. Editing implementation, generators or oracles makes earlier evidence stale.

Windows architecture is observed through [`GetNativeSystemInfo` and its public `SYSTEM_INFO` structure](https://learn.microsoft.com/windows/win32/api/sysinfoapi/ns-sysinfoapi-system_info); CPU model/vendor/identifier come from the local hardware registry. Optional environment variables are insufficient, and older reports with missing machine/processor fields remain ineligible for machine-bound budgets. The driver captures identity before and after execution; a change invalidates the run. An unavailable hardware read is explicit missing evidence. No computer name, device serial, user identity or network lookup is collected.

These measurements guide storage, bounded rendering and incremental preparation work. Multi-megapixel native editing, common screen/print sizes, more realistic mixed scenes, retained precision, identity-bound cache invalidation and measured acceptance budgets remain A5 requirements. Do not raise limits alone or award an engine checkpoint for adding this driver. Revalidate the [recovery contracts](RECOVERY_CONTRACTS.md) after relevant storage changes; actual model-driven trials and matched sister-project comparisons remain separate evidence.

## Additional wide native composition

`python tools/measure_wide_native.py --output-root C:\Work\Evidence\wide-001 --conditions "Sequential local run; no concurrent verification"` runs the separate `wide-native-v1` baseline five times. It imports an original 2560x1440 RGBA16 source, adds 128 clipped annotations inside a translated isolated group, saves a session, publishes the initial image, edits a 2x2 native region, publishes the edit and historical revision, and verifies history and source bytes. An independent arithmetic oracle checks every channel of each native TIFF, including unchanged surrounding pixels and annotations.

This case was added after a real decode-work-limit failure in the wider composition. It supplements the unchanged seven-case `scale-v1` suite; it neither replaces a failed task nor inherits that suite's performance budgets. Its report retains every attempt, source/executable/candidate identities, before/after machine identity, per-command metrics and correctness failures. Successful timing/memory summaries exclude failed attempts without removing them from the denominator. Use at least five repetitions, new external output directories and sequential measurement. Create its own reviewed budget with the same `workload_gates.py create` command, supplying the wide report and a new gate path; check a later full wide run against that gate. The measurement driver does not itself evaluate budgets. Broader production cases remain required; this is not the complete A5 or model-driven benchmark.

## Native image with 5,000 mixed annotations

`python tools/measure_native_layout.py --output-root C:\Work\Evidence\layout-001 --conditions "Sequential local run; no concurrent verification"` measures `native-layout-v1`. Its fixed `mixed-native-5000` case uses the explicit `large_raster` profile and the original scene described in [large raster layouts](LARGE_RASTER.md). It retains a 2560x1440 RGBA16 base, 2,500 vector and 2,500 raster annotations, clips and a translated isolated group. One atomic revision applies a native patch and moves an annotation of each kind; all channels of initial, revised and historical output have independent arithmetic oracles.

This suite has its own five-or-more-repetition baseline and gate. It cannot replace or borrow budgets from any other suite. The shared additional-workload driver retains the same failure accounting, source/build/machine identity, original raw artifacts and create-only external directories; sharing mechanics does not merge fixture identities. The original standard-profile admission failure remains evidence of the limitation that motivated the explicit profile. These regular clipped annotations do not represent every dense, text, effect or photographic workload.

## Native neighborhood filters

`python tools/measure_native_filter.py --output-root C:/Work/Evidence/filter-001 --conditions "Sequential local run; no concurrent verification"` measures `native-filter-v1`. The `native-box-blur` case retains a 1920x1080 RGBA16 image with an editable one-pixel box filter and clamp borders. An independent integer 3x3 convolution checks every native output channel before and after a four-block-boundary patch and in the historical revision. Import, saved revisions, filter controls and original bytes remain intact.

The original release imported and saved this same initial source/filter combination but rejected tiled publication. Its failure remains recorded. The new workload has separate content-bound baseline and repeat-run budgets; it cannot replace any other suite. This original opaque image exercises full native depth and discontinuities, while smaller rational-alpha, stacked-filter, mask, border and shortened-codec-band fixtures cover additional semantics. It does not establish broad photographic quality, all filter families or complete practical-scale acceptance.

## Translucent native image with retained shadow

`python tools/measure_native_shadow.py --output-root C:/Work/Evidence/shadow-001 --conditions "Sequential local run; no concurrent verification"` measures `native-shadow-v1`. Its `native-shadow-history` case imports an original 1920x1080 translucent RGBA16 image with an editable unblurred shadow offset by two pixels horizontally and one vertically. A 2x2 patch changes both color and alpha across four source blocks. Independent integer source-over arithmetic checks every initial, revised and historical channel; only exact rational half-code results allow the two adjacent rounding outcomes. There is no blanket one-code tolerance. History order and source preservation are also required.

The prior release imported, saved and edited this scene but rejected all three publications as unsupported. Those failures remain evidence; the exact-half oracle clarification occurred before successful acceptance and is retained in the verification record. This suite pins its own complete harness and has a separate five-repetition baseline and repeat-run gate. It neither replaces an older suite nor establishes broad production effects or complete A5 acceptance.

## Native clone and heal edits

`python tools/measure_native_retouch.py --output-root C:/Work/Evidence/retouch-001 --conditions "Sequential local run; no concurrent verification"` measures `native-retouch-v1`. Its original 1920x1080 RGBA16 texture includes a small blemish crossing four source blocks. One atomic revision clones a separate region and heals the blemish from a frozen donor whose texture differs by a known constant color offset. The exact boundary solution restores the arithmetic texture. Every native channel of initial, revised and historical TIFF output is checked independently; source bytes and history order must also remain intact.

The previous release imported, saved and published this source but rejected the clone/heal edit, leaving revised output blocked and historical output unchanged. That failure remains recorded. This suite has its own complete pinned fixture/helper closure, five-repetition baseline and separate repeat-run gate. It does not replace another suite or establish broad photographic reconstruction, all native operators or complete A5 acceptance.

## Native pixel-brush edits

`python tools/measure_native_brush.py --output-root C:/Work/Evidence/brush-001 --conditions "Sequential local run; no concurrent verification"` measures `native-brush-v1`. The original 1920x1080 RGBA16 texture receives paint, erase, smudge and mixer strokes in one atomic revision. A native-grid texture restricts deposition to a fully covered 8x8 region crossing four source blocks. An independent exact rational oracle computes source-over, frozen transport, reservoir pickup, stroke opacity and native quantization for every operation; expected values avoid half-code ties. Every initial, revised and historical TIFF channel is exact, and source bytes and history order must remain intact. Independent fractional-edge fixtures cover numeric tip integration separately.

The prior release imported and published this image but rejected the first brush operation without changing history. That failure remains recorded. This suite pins its complete fixture/helper closure and uses its own five-repetition baseline and repeat-run gate. Existing retouch/rendering budgets remain separate and unchanged. Scripted correctness and measured engine time are not model trials or complete A5 acceptance.
