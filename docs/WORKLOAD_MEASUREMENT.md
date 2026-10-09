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

## Identity and acceptance

The report records the source fingerprint, complete candidate-file hashes including fixture/oracle code, Git state, toolchain, optimized Cargo artifact and executable hash. Cargo's actual binary path is used. Inputs are rechecked after measurement; changed source, executable or candidate files invalidate the report. Raw evidence stays externally, and a later commit can be associated only after the exact tested bytes are checked again. Editing implementation, generators or oracles makes earlier evidence stale.

These measurements guide storage, bounded rendering and incremental preparation work. Multi-megapixel native editing, common screen/print sizes, more realistic mixed scenes, retained precision, identity-bound cache invalidation and measured acceptance budgets remain A5 requirements. Do not raise limits alone or award an engine checkpoint for adding this driver. Revalidate the [recovery contracts](RECOVERY_CONTRACTS.md) after relevant storage changes; actual model-driven trials and matched sister-project comparisons remain separate evidence.
