# Fast development feedback

The routine target is **2-3 minutes after implementing a change**. Run focused checks while working and reserve complete acceptance for milestones. This separation follows the sister project's quick/thorough workflow; it does not add automatic publishing or background jobs.

| Need | Command |
| --- | --- |
| Default change-aware check | `python tools/verify.py` |
| Selected Python modules | `python tools/verify.py --only test_session_proposals,test_session_backups` |
| Selected Rust tests | `python tools/verify.py --rust sample_store::tests` |
| Both targeted boundaries | Combine `--only` and `--rust` |
| Fix unresolved failures | `python tools/verify.py --last-failed` |
| Explain current selection | `python tools/verify.py --list` |
| Force a focused rerun | Add `--force` to a quick command |
| Complete milestone acceptance | `python tools/verify.py --thorough` |
| Staged publication check | `python tools/check_repo.py --staged` |

After changing `docs/features.json`, run `python tools/update_report.py` before
verification. The dedicated `test_implementation_registry` module checks the
compiled registry, evidence references and generated report together.
Its source inventory also binds cached results to the evidence-test files, so
renamed or removed test functions cannot leave a stale registry pass.

Do not separately repeat formatting, Clippy, build and full Rust tests after the verifier has already covered them on unchanged inputs. It owns those stages. Use targeted checks after a small correction; rerun broad checks only for new relevant changes, failures or unresolved concerns. Do not run thorough acceptance for each intermediate edit.

## Budget, execution and results

Quick mode has a **180-second total check budget**, including Cargo stages. `--budget SECONDS` explicitly changes it. When the budget ends, owned running process trees stop and checks remain pending. Shutdown, source-identity checks and report writing add a small amount of bookkeeping after the deadline. A fresh build or a broad engine change can require more work than one quick window; this is reported, never silently waived. Rerun to resume already completed stages, narrow the selection for immediate feedback, or use thorough acceptance at the milestone.

The default schedules all checks without an identical valid pass. Up to four isolated workers run concurrently, including the Rust test stage; long checks start early using saved durations. `--jobs 1` is serial and the explicit maximum is eight. Failed and directly edited fixtures receive priority. The CLI is copied to an owned run directory so Python fixtures do not lock the developer's executable. Rust tests use Cargo's ordinary target directory. Changes to the original executable during a run invalidate acceptance. The owned CLI copy is removed after the run; if Windows retains a file lock, the report records its retained path without discarding completed test results.

On Windows, a waiting launcher joins an owned kill-on-close Job Object before it can start the command. The job contains its descendants, including persistent fixture workers; closing it stops only that tree on timeout or completion. POSIX uses an owned process group. The process-tree guarantees have Windows tests; this does not establish whole-engine support for additional platforms.

| Exit | Meaning |
| --- | --- |
| 0 | Every selected check passed or reused an identical pass |
| 1 | A check/harness failed or inputs changed during execution |
| 2 | Checks remain pending because of the quick budget/prerequisites |

Invalid arguments also use the standard argument-parser exit 2 with an explicit diagnostic. A successful `--only`/`--rust` run proves only its listed scope. A quick run, even when every check is covered, is development feedback and does not award engine points or claim current full acceptance. No-match Rust filters and missing/incorrect Python test counts fail instead of reporting green.

`--thorough` always runs the complete suite, including formatting, locked build, all-target Clippy with warnings denied, Rust tests, every discovered Python module and the candidate material guard. It ignores cached passes and has no quick deadline. Selection/cache/budget overrides cannot be combined with it. It does not replace the separate release workload, model-driven benchmark, recovery or platform evidence required for the claims being made.

## Exact-input reuse

Local state and logs live under the checkout's Git directory in `inkbolt-verify/`; they are not published. A per-checkout OS lock prevents overlapping verifiers. Reports contain per-stage commands, timings, test counts, statuses, log paths, source/environment/executable fingerprints and explicit outside-scope and pending lists. `--report EXTERNAL_PATH` also retains a report externally. Only a successful unchanged thorough run sets `complete_suite: true`; no progress/feature registry is updated automatically.

Pass reuse binds to raw candidate bytes, local Python import closures and referenced fixture files, verifier implementation, toolchain versions, Python/platform identity, the environment digest, checkout path and the executable hash for CLI tests. Environment values are hashed, not written to reports. Added/deleted files participate in invalidation. Literal file-based imports bind the referenced local module; glob patterns bind matching candidate files across every directory. Unresolved dynamic imports/patterns, complete repository enumeration and unparseable Python conservatively depend on the entire candidate. Unclassified non-Markdown inputs invalidate engine checks. A failure invalidates the old pass; a later timeout cannot hide an unresolved failure. Changes observed between initial and final identities discard the run's reusable results.

Every Rust source change conservatively invalidates the full Rust stage and all Python engine checks. There is no claim that an unmeasured function-level impact map can prove other fixtures irrelevant. For a small engine edit use the relevant `--rust` and `--only` selectors, then complete broad acceptance at the milestone. Python/helper-only edits automatically invalidate dependent modules through their transitive imports. Ordinary unrelated Markdown edits keep engine passes, except for fixtures that read those files or enumerate the repository. `--force` is available when investigating external conditions the fingerprint cannot observe.

Keep shared test helpers separate from repository-wide checks. The generated
report check lives outside the commonly imported PNG/CLI helper module. Shared
workloads, native-sample oracles and process accounting live in
`tools/workload_cases.py`; complete candidate inventory and release orchestration
remain in `tools/measure_workloads.py`. Helper consumers therefore do not inherit
the measurement driver's repository inventory dependency. Driver entry points
remain compatible and still bind release evidence to the complete candidate.

Generated-workspace file comparisons use `tests/external_workspace.py`, which
rejects the checkout, its descendants and ancestors, and files resolving into
the checkout. It does not traverse directory links. This keeps temporary output
inventories distinct from source-file dependencies without changing the verifier's
conservative import, wildcard or unknown-input rules. Tests that actually inspect
the repository or record its complete identity still rerun when those inputs
change. A regression check exercises these boundaries against the real checkout,
including shared-helper edits and universal Rust-change invalidation.

The candidate material guard always runs and is never cached. The staged guard reads actual indexed blobs in bounded Git batches, preserving path/type/size/encoding/private-content and forced-ignore checks. It does not substitute working-copy bytes, waive the private policy or bypass the commit hook.
