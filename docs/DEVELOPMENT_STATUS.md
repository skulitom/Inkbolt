# Development status and milestone evidence

[FIX_PLAN.md](../FIX_PLAN.md) is the primary plan. Its short status table records
current priorities. Update these milestone summaries in place; use Git history
for individual changes. Completed infrastructure does not establish whole-goal
or additional engine-checkpoint completion.

## W0: closed

**Complete, 11 October 2026.** The central catalog at that milestone contained 773 documented
resource, admission, numerical and work-accounting constants. Shared raster/tile
policies derive from common definitions; independent policies retain their own
names even when values coincide. Existing module paths remain compatible and
no ceiling increased. Discovery and diagnostics use the enforced values, with
676 direct numeric capability bindings, derived/semantic checks and seven
legacy descriptive bindings. The six specifically listed boundary-fixture
modules now read advertised limits; 75 contract documents link to the generated
[limit reference](LIMITS.md).

The source audit covered named definitions, comparisons, bounded loops, batch
extents, work charges and diagnostic/discovery strings. Remaining literals
represent format widths/versions, channel and geometric cardinalities,
mathematical definitions, actual operation counts or synthetic test data.
They are not adjustable resource ceilings.

Fresh acceptance at `53518fd` passed all 213 stages on both platforms:
Windows ran 208 Rust and 2,278 Python tests in 1006.1 seconds;
Linux ran 176 Rust and 2,244 Python tests in 494.5 seconds,
with 34 explicit platform skips. No checks failed, remained pending or reused
older results. The final focused change took 108.5 seconds on Windows and
87.3 seconds on Linux. See [platform evidence](PLATFORMS.md) and the
[development loop](DEVELOPMENT_LOOP.md). W0 completion does not complete
W1, any additional engine checkpoint, the scale targets or the overall goal.

## W1: core platform tier and hosted matrix verified; Unix jobs open

The latest retained [hosted matrix at `d4692ea`](https://github.com/skulitom/Inkbolt/actions/runs/38791299542)
passed all 255 fresh stages on Windows, Ubuntu and macOS, including SVG images,
span ranges, omissions and request guidance.
All three minimum-compiler checks also passed. Reports and logs are retained in
`w1-public-ci-d4692ea`; see [platform evidence](PLATFORMS.md) for exact counts,
timings and the audit identity. This hosted run predates native block migration and
does not replace the mandatory local private publication guard.

Linux tier 1 covers core/library/CLI/MCP, sessions and durable publication/history
receipts on Ubuntu 22.04 under WSL2, using native Linux storage. Background jobs
remain Windows-only. The private WSL mirror retains the required local guard.
Rust 1.89 passed locked all-target compiler checks on Windows and Linux;
`rust-toolchain.toml` pins development to Rust 1.98.1 with rustfmt and Clippy.

The separate public structural guard reports `private_policy:"not_evaluated"`.
It never replaces the default/staged private guard or installed hook; real
commit tests prove missing policies still fail closed after a public pass.

Fresh public clones without private policy or hooks completed every stage with
`--public --thorough --jobs 2`, consecutively on the shared host. No stages were
reused, failed or pending. This is milestone evidence, not the routine time budget.

| Platform | Stages | Rust tests | Python executed | Explicit skips | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows | 213 | 208 | 2,284 | 0 | 1820.3 |
| Linux | 213 | 176 | 2,250 | 34 | 920.3 |

The 34 Linux skips retain the declared job-dependent and Windows measurement
exclusions. Candidate source fingerprint:
`de0c14a2ebd6033868458ec9c8e7ada91887ca4df732acdcfc34446139bfeb22`.
The engine and locked dependencies remain those checked before the subsequent
planning/workflow-only revision; that revision receives focused verification.

The active three-platform CI workflow uses pinned actions, read-only repository
permissions, explicit public verification and the minimum-compiler check. It
retains verification reports/logs. Running main checks survive later pushes;
obsolete pull-request runs can be cancelled. The default concurrency queue still
keeps only the latest pending run. Dependency/build caches do not contain verifier
state or waive any test. The exact workflow path is the only newly admitted YAML
path; private content checks remain mandatory locally.

The owner approved activation, the exact workflow-path rule and Cargo cache on
11 October 2026. The first hosted run failed Python setup on Windows/macOS:
the initial 3.11.13 pin has only Linux hosted distributions. CI now pins 3.13.16,
whose official setup manifest includes all three runner platforms/architectures;
Python 3.11 remains the supported minimum and the locally verified version.
The full hosted matrix subsequently passed at `5dfb699`, as recorded below. Local
verification does not replace those hosted results. See
[platform coverage](PLATFORMS.md).

The Linux job in [the first hosted run](https://github.com/skulitom/Inkbolt/actions/runs/38182183426)
passed all 213 fresh stages, including 2,250 Python tests with 34 explicit skips,
in 902.9 seconds. The overall run failed because of Windows/macOS Python setup.
The [corrected run](https://github.com/skulitom/Inkbolt/actions/runs/38182478787)
passed setup and the minimum-compiler check on all three platforms. Linux passed;
Windows and macOS failed their full checks. The test inventory now preserves the
caller's path spelling after validating resolved locations, fixing Windows short
names and Unix aliases. Unix SQLite opens now resolve only the existing parent
directory; final database-file symlinks remain rejected. The regression reproduced
on Linux before the fix. Library, CLI/MCP and backup/recovery/migration/continuation
checks cover aliases, immutable sources, retries and rejected database links.

Focused Windows verification passed in 108.2 seconds after the first 180-second
window left Rust compilation pending. Linux checks took 114.8 seconds and caught
a test-client configuration mistake; correcting that fixture and rerunning only
the failure passed in 8.0 seconds. The engine fix did not change between those
Linux runs. Workflow syntax validation also passed.
The final selected checks, including verifier dependency-boundary tests, passed
in 38.2 seconds on Windows and 23.6 seconds on Linux with identical-pass reuse;
neither selected set had failed or pending checks.

The [12 October hosted run at `1e8ac2d`](https://github.com/skulitom/Inkbolt/actions/runs/38186420025)
passed all 216 fresh stages on Ubuntu and macOS. Both executed 177 Rust tests
and 2,265 Python tests with 34 explicit platform skips; durations were 1006.8
and 2137.4 seconds respectively. This establishes the bounded macOS core/receipt
tier at that revision. Windows retained two failures: the idle-exit job test
unwrapped a documented retryable `JOB_BUSY`, and a print-render fixture exceeded
its existing 20-second deadline while another stage ran. The polling test now
uses its existing 30-second terminal-state helper, retrying only `JOB_BUSY` and
still requiring successful completion. Windows CI now uses one stage worker,
as in the passing macOS run. No production job behavior, render deadline or
pixel acceptance changed. Focused Windows verification of the job tests and
repository guard passed in 111.5 seconds, including formatting, build and
all-target Clippy, with no failed or pending checks. Workflow validation also
passed. The [follow-up at `c500414`](https://github.com/skulitom/Inkbolt/actions/runs/38190979581)
passed on Ubuntu/macOS and passed every Windows Python module, including the
render fixtures: 2,308 tests executed and one explicit skip. Windows still failed
two Rust job tests: the short-deadline fixture did not reach its startup checkpoint,
and the enqueue-during-idle-exit fixture returned a failed second job. A single
stage worker does not serialize Rust's own test harness; Windows CI now also
sets `RUST_TEST_THREADS=1`. Failure assertions retain the returned job details.
The deadlines and production behavior are unchanged. A complete latest-revision
hosted matrix remains pending. Local serial checks passed for the deadline test
in 32.5 seconds and the idle-exit test in 21.1 seconds, including their verification
overhead. Workflow validation and all 13 repository-guard tests passed. An earlier
attempt to run all nine serial job fixtures reached the 180-second quick budget;
it remains pending, not a full-suite pass. CI's thorough run keeps all fixtures.

The [hosted `43f839e` run](https://github.com/skulitom/Inkbolt/actions/runs/38194879684)
finished all three platforms with one failed stage each: a test of the verifier's
dependency boundaries omitted the new icon benchmark from its expected consumer
list. Both the icon and large-layout lifecycle tests are now listed explicitly;
the assertion remains strict. All 22 verifier tests passed locally on Windows
and Linux in 30.2 and 15.3 seconds, including verification overhead. New-module
guidance now includes this focused check. A subsequent complete hosted matrix
is recorded below; those failed runs are not counted as passes.

The [hosted `fbc7fea` run](https://github.com/skulitom/Inkbolt/actions/runs/38197982149)
passed all 221 fresh stages on Ubuntu and macOS in 1137.3 and 2258.2 seconds,
including the corrected dependency-boundary expectation. No stage failed,
remained pending or was reused. Windows finished with 220 passed stages and one
failed Rust stage in 3569.9 seconds. All 2,330 Python tests passed with one explicit
skip, but the idle-exit fixture's second job terminated with `JOB_BUSY`; 142 Rust
library tests passed and one failed, preventing the remaining Rust targets from
running. Serial execution alone did not fix this failure. Ubuntu and macOS
subsequently passed all 225 fresh stages at `790716d` in 696.4 and 2086.6 seconds,
respectively, each with 2,325 Python tests executed and 34 explicit skips. That
run's Windows job was still running when this evidence was recorded; it predates
the contention fix below.

A controlled delayed-writer regression reproduced a prepared job failing with
`JOB_BUSY` after the short SQLite wait, while its original lifetime still had
time remaining. Before the first publication link, the worker now retries only
the rolled-back publication-permit acquisition, checking the existing job control
and retaining the original attempt and prepared bytes. No encoding, link or
whole job is retried; other errors, external request waits and completed-output
recovery retain their existing behavior. Discovery and the job contract describe
this distinction. The full hosted run at `5dfb699` subsequently passed with this fix.

Focused Windows verification passed all 12 Rust job tests and 26 Python
job/publication tests. The first 46.2-second window completed build, formatting,
Clippy and nine receipt tests, leaving the two longer groups pending. The resumed
125.1-second check reused those identical passes and finished all selected checks
without failures or pending work. Tests cover exact prepared bytes, a single
attempt, simultaneous observers, cancellation before publication, and an unchanged
runner deadline while the writer remains locked. Linux passed 13 Rust
publication tests and nine Python receipt tests in 64.2 seconds, with 17 explicit
Windows-job skips; Linux job execution is still unsupported. The final reports
both recorded unchanged inputs and source fingerprint:
`27cb2d55db3886278b5470828865eaf38d4fdcb22d71c2d162f3a246ad3abf8d`.
The failing before-fix log and final reports are retained externally under
`w1-job-contention-`. These are focused correctness checks, not complete milestone
acceptance or isolated performance measurements.

The [full hosted matrix at `5dfb699`](https://github.com/skulitom/Inkbolt/actions/runs/38207200768)
then passed all 227 stages on Windows, Linux and macOS. Each stage ran freshly;
none failed, remained pending or reused a previous result. Windows ran 212 Rust
and 2,376 Python tests with one explicit skip in 3672.1 seconds. Linux and macOS
each ran 178 Rust and 2,341 Python tests with 36 explicit skips, in 1039.2 and
2241.3 seconds. All three reports confirmed unchanged inputs and fingerprint
`4e52a6f0ff99f44c8ac28876ba466d6c444fb08a8a7b177f834e4cb4aec6dfcf`.
Reports and logs are retained externally under `w1-public-ci-5dfb699-`. This
establishes the declared platform tier at that revision, including the contention
fix; Unix jobs, distribution and overall W1 completion remain separate work.

The [later hosted run at `3ac68d6`](https://github.com/skulitom/Inkbolt/actions/runs/38371259325)
found a macOS test-fixture race: parallel session-retry tests could receive the
same clock value and attempt to create the same temporary directory. The owned
fixture now combines time with an atomic sequence, retains exclusive creation
and retries only name collisions. A deterministic test allocates 16 concurrent
roots with the same supplied clock value. It passed with formatting, locked build
and all-target Clippy in 32.4 seconds on Windows and 11.1 seconds on Linux. The
complete session-retry integration target also passed on both platforms (three
Windows tests, four Linux tests). Session behavior, deadlines and assertions are
unchanged. The [hosted `20ac313` run](https://github.com/skulitom/Inkbolt/actions/runs/38377988007)
now passes on all three platforms with 230 fresh stages each, no failures,
pending checks or reused passes. Windows ran 213 Rust tests and 2396 Python tests
with one explicit skip in 3937.6 seconds. Linux and macOS each ran 179 Rust tests
and 2362 Python tests with 35 explicit skips, in 1310.1 and 2630.3 seconds
respectively. All three reports confirm unchanged candidate fingerprint:
`60af4fdb58926c196becb6e3cd039cad6a405602a5b7bba58f067252373a9da8`.
This confirms the fixture fix and declared platform tier at `20ac313`, not later
unverified commits or Unix jobs. Reports/logs are retained externally under
`w1-public-ci-20ac313`; local evidence remains under `w1-retry-roots-`.

The later [hosted `48929e8` run](https://github.com/skulitom/Inkbolt/actions/runs/38385966170)
passed Windows and Linux, and macOS completed its full verification step
successfully. Its evidence-upload step failed with GitHub endpoint DNS error
`ENOTFOUND`; that job/run remains failed. The subsequent
[hosted `699b136` run](https://github.com/skulitom/Inkbolt/actions/runs/38391594759)
passed all 234 fresh stages on Windows, Linux and macOS, with all reports and
logs retained under `w1-public-ci-699b136`. Windows ran 213 Rust and 2426 Python
tests with one skip in 4130.6 seconds; Linux/macOS each ran 179 Rust and 2392
Python tests with 35 skips, in 1124.4/3135.2 seconds. Every report confirms
complete-suite coverage, unchanged inputs and no failed, pending or reused
checks. Their common candidate fingerprint is
`30fdfae481ac1757a86019d6ce9cd56a40fbaf00f62073da46fab021b3873c42`.
The subsequent [hosted `d0719a1` run](https://github.com/skulitom/Inkbolt/actions/runs/38402258810)
passed all 237 fresh stages on every platform. Windows ran 213 Rust and 2447
Python tests with one skip in 4320.2 seconds; Linux/macOS each ran 179 Rust and
2409 Python tests with 39 skips, in 1251.5/2901.0 seconds. All three retained
reports confirm complete-suite coverage, unchanged inputs and no failed,
pending or reused checks. Reports and logs are under `w1-public-ci-d0719a1`;
their common candidate fingerprint is
`0d80abe1ec91235c63bd1f5aa48f92908d0ecfad59af0caf52aabe8bfab17919`.
The newer [hosted `171a1c5` run](https://github.com/skulitom/Inkbolt/actions/runs/38421962898)
passed all 241 fresh stages on each platform. Windows ran 213 Rust and 2473
Python tests with seven skips in 4488.8 seconds; Linux/macOS each ran 179 Rust
and 2432 Python tests with 48 skips, in 1274.1/2698.0 seconds. All three reports
confirm complete-suite coverage, unchanged inputs and no failed, pending or
reused checks. Reports and logs are retained under `w1-public-ci-171a1c5`, with
shared candidate fingerprint
`19205e33567634035ef3531377ad668baf9eb3947c4a405510777024507f714c`.
This earlier fully retained platform milestone predates the Codex
adapter and first-page discovery change and does not establish Unix job support.

The later [hosted `9909329` run](https://github.com/skulitom/Inkbolt/actions/runs/38431558895)
passed all 242 fresh Linux stages: 179 Rust and 2446 Python tests, with 48 explicit
skips, in 1257.3 seconds. Its macOS job failed only the Codex evaluation-adapter
test module. Windows subsequently failed that same path-alias fixture, one Rust
job deadline fixture and one Python concurrent job-list fixture. Reports
and logs are retained under `w1-public-ci-9909329`, with common candidate
`0860d87bb953c6fbc54cb48a93d46cde6809b1c7387c9c26b156c7534d893c45`.
The fixture used an unresolved temporary root while the adapter and real harness
use resolved paths. macOS's `/var` alias exposed two path assertions and one MCP
configuration mismatch. An aliased Linux temporary root reproduced all three.
The fixture now resolves its root, matching the actual harness without changing
adapter validation or engine behavior. All 13 adapter checks then passed under
the same alias condition, plus ordinary Windows/WSL checks in 13.5/5.6 seconds;
unchanged formatting/build/Clippy checks reused their prior passes. No selected
checks failed or remained pending. Reports and the before/after reproduction are
under `w2-codex-path-alias-`; tested candidate:
`871a566e7752ad5f828b8e92ce4f42178e14450f83b3009b683ae08832bf11f9`.
Windows' short temporary name exposed the same fixture mismatch. The two job
failures are separate: a 1.5-second deadline expired before the fixture reached
its publication checkpoint, and a snapshot test treated documented retryable
`JOB_BUSY` as an unexpected result. The deadline fixture now gives its cold
processes ten seconds to reach their checkpoints. Both attempts still block
until the actual request deadline; the test still requires timeout before
publication, committed output after publication, and no cancellation by an
observer. The snapshot fixture retries only `JOB_BUSY` within a fixed 20-second
observation bound. It still requires ten successful four-row pages, one complete
generation per page, and concurrent progress across generations.

Production deadlines, locking and job semantics are unchanged. Focused Windows
verification passed all 17 job tests plus the Rust deadline test in 140.6 seconds,
including fresh format/build/Clippy. WSL passed the two platform-boundary tests
and explicitly skipped the 17 unsupported job tests in 7.0 seconds, also with
fresh format/build/Clippy. Neither run had failures, pending checks or reused
passes. Reports and candidate hashes are retained under `w1-job-fixture-timing-`;
their common candidate is
`dc8895207d7ee4e8787c9255c9635d515ed76b77d52e28bf9e16267df0df6a5b`.
The [hosted matrix at `a1a0339`](https://github.com/skulitom/Inkbolt/actions/runs/38440855374)
has since passed all 242 fresh stages on each platform: Windows ran 213 Rust
and 2490 Python tests with seven skips in 2651.7 seconds; Linux and macOS each
ran 179 Rust and 2449 Python tests with 48 skips, in 1443.1/3034.6 seconds.
All inputs stayed unchanged, with no failed, pending or reused stages. Retained
reports/logs are under `w1-public-ci-a1a0339`, candidate
`f985ad1ec589c62a2a342d58356d64d24095e61314e2a66a42d11afb4811d2db`.
This confirms the path-alias correction. The later complete `8bc8982` matrix
also confirms the B01/B03 store judges and Windows job-fixture changes: all 242
fresh stages passed on every platform. Windows ran 213 Rust and 2492 Python
tests, with seven skips, in 4448.6 seconds. Linux/macOS each ran 179 Rust and
2451 Python tests, with 48 skips, in 1421.4/2161.0 seconds. Inputs stayed
unchanged; no stages failed, remained pending or reused passes. These reports
predate the later B05-B07 judge corrections. See
[the retained platform evidence](PLATFORMS.md).

The retained [complete matrix at `7a07f07`](https://github.com/skulitom/Inkbolt/actions/runs/38468108741)
passed 242 fresh stages on every platform. Windows ran 213 Rust and 2495 Python
tests with seven explicit skips in 2950.1 seconds; Linux/macOS each ran 179 Rust
and 2454 Python tests with 48 skips, in 1426.3/3026.1 seconds. All reports confirm
unchanged inputs, complete-suite coverage and no failed, pending or reused
checks. Report and log hashes are retained under `w1-public-ci-7a07f07`, candidate
`6e3153244579fd3e0dcdebd7c42185b3787d71854664171b9f71b239364ae3a3`.
Later B10/B13 delivery and B11/B12 store/hierarchy judge corrections retain their
focused Windows/WSL evidence; these hosted results do not cover those later edits.

The latest retained [complete matrix at `30c4ebd`](https://github.com/skulitom/Inkbolt/actions/runs/38476034163)
passed 243 fresh stages on every platform. Windows ran 213 Rust and 2502 Python
tests with seven skips in 4584.9 seconds. Linux/macOS each ran 179 Rust and 2461
Python tests with 48 skips, in 1490.2/2715.8 seconds. All inputs stayed unchanged;
no check failed, remained pending or reused a pass. Reports and all stage-log
hashes are retained under `w1-public-ci-30c4ebd`, candidate
`811f2460a6ddb536965a2b822971fe8f6fbf0d3c9094c14e7bf4625ae337e81d`.
This includes the B10/B13 delivery and B11/B12 store corrections, but predates
the later hierarchy and print/review judge changes. It is not current-HEAD acceptance.

### Windows polling and development hash cost

The [later `30ecf5b` matrix](https://github.com/skulitom/Inkbolt/actions/runs/38497212073)
passed Linux/macOS but failed Windows. The queue-capacity Rust test unwrapped
`JOB_BUSY` while observing the supervisor's final transaction; the five-format
Python export test exceeded its 20-second `job.start` deadline. These failures
remain retained under `w1-public-ci-30ecf5b`. A local unchanged-source rerun passed
the Rust test in 47.9 seconds and the Python case in 17.94 seconds, so the hosted
failures did not reproduce locally.

The Rust observer now retries only `JOB_BUSY` within its existing 30-second
bound and still requires the supervisor owner to clear. Other errors fail.
The Python loop labels each format with a subtest, retaining the same deadline,
exact synchronous/background bytes, hashes and loss-receipt assertions.

Development/test builds now optimize only the pinned SHA-256 dependency, matching
the sister project's build setting. Worker verification still reads/hashes the
complete executable; no content check or production job behavior was removed.
Two sequential local probes of the same five-format assertions passed. Median
`job.start` time fell from 3.385 to 0.340 seconds; the complete case took 17.94
then 2.72 seconds. Other host activity and caches were uncontrolled. This is a
local development measurement, not release performance or proof of the hosted
timeout's cause. Release settings and dependencies remain unchanged.

Windows focused verification took a 94.6-second first window for formatting,
locked build, all-target Clippy and nine receipt tests. Old duration estimates
deferred the two job groups before launch. The 89.8-second continuation reused
those passes and ran all 12 Rust job tests and 17 Python job tests; none failed,
remained pending or skipped. Linux passed fresh formatting/build/Clippy and all
11 receipt/platform Python tests in 76.4 seconds, without reuse or skips.
Both reports record unchanged inputs and fingerprint
`d9c7fa4261528d732494eb9ab0782ab01db8f4a6e93d5e27e2412b34975cdab0`.
The timing reports, Windows stage logs and tested source identities are retained
under `w1-job-ci-` and `w1-job-admission-`. Final status-only documentation follows
these checks; implementation/test inputs remain unchanged.

Separately, [hosted Linux/macOS at `d34851e`](https://github.com/skulitom/Inkbolt/actions/runs/38504495500)
each passed all 243 fresh stages: 181 Rust tests, 2,482 Python tests and 50 explicit
skips, in 1317.3/2910.0 seconds respectively. Retained report/log inventories are under
`w1-public-ci-d34851e`, fingerprint
`6d11ebd28b4136acec415096fa37b220092cfe6a2092484ed3f9d9bee6447bf7`.
That predates the development-profile change. The later complete hosted matrix
at `1d5b960` passes all 243 fresh stages on all three platforms, including the
Windows job tests after the polling/profile changes. Its 732 retained files,
exact counts, skips and identities are recorded in [platform evidence](PLATFORMS.md).
One successful run does not prove intermittent timing failures eliminated;
Unix jobs remain open.

## W2 and the next behavior increments

B01 separates fixtures, its versioned prompt, reference solving and an independent
artifact judge. Its [external driver lifecycle](BENCHMARK_DRIVER.md) supports
model and no-engine arms, bounded client execution, retained transcripts, observed
usage and rejudging captured workspaces. Unknown usage remains null. Explicit
artifact/engine check classes cover the unchanged twenty-task inventory. The
baseline uses externally pinned resvg 0.47.0 and Pillow 12.3.0 with the original
named font; source checks and independently calculated pixels judge both arms.

Seven affected modules passed focused Windows checks in 125.4 seconds; the final
driver-path correction passed in 26.8 seconds. Linux passed the seven modules in
60.1 seconds, executing 44 tests with eight explicit platform skips. These runs
use identical-pass reuse for unaffected stages, with no failures or pending checks.
Five synthetic-client B01 trials passed with the real pinned baseline tools on
each platform; all five retained Windows trials also passed independent rejudging.
Synthetic runs never count as model evidence. No actual model was invoked.

B02 now separates its creation fixture, versioned prompt, reference solver and
delivered-artifact judge. It preserves the original stable IDs, board order,
ownership, spacing, editable icons and all five check IDs, while enforcing the
canvas/board dimensions already stated by the original task. The engine judge
reopens the delivered snapshot and renders each board independently. The baseline
admits three editable SVG viewports, renders each separately with pinned resvg,
and compares both rendered and delivered PNGs against the same authored pixels.
Judge traffic remains separate; preview timing must identify a judged image.

The final Windows quick verifier ran 25 tests in 108.2 seconds, reusing unchanged
Cargo checks with no failed or pending stages. A native WSL snapshot ran the 19
focused harness tests in 18.4 seconds against the already built `e9c493e` engine;
this invocation does not claim a fresh Linux build. The isolated and primary
checkouts differed only by CRLF/LF in unchanged files, verified byte-by-byte after
newline normalization. Five synthetic-client B02 trials passed with the real
pinned tools on each platform, and all five final Windows captures passed
rejudging. Both baseline reports bind candidate fingerprint
`c9bcd4e3d0283a89220305bc121c9a9515ad4b399e3ea500916ff86bb09c2d7f`
and prompt hash `0911714f1c4f869bdf33ebebd9eb7d207e9ceea7c11a88046a7e18ddfbe6f67e`.
An initial fresh Linux mirror lacked a Git revision; that setup failure was
retained before importing its existing source commit, and no trial was counted
from the failed setup. These are correctness checks under shared host load,
not isolated performance measurements or actual model evidence.

B03 separates the original 5,000-object fixture, prompt, reference solver and
delivery/history judge. It checks every normalized document field for collateral
changes, both PNGs against independent geometry, and the supplied session's
original, delivered and current revisions. Rejudging uses the exact saved,
resource-free historical snapshot without retaining obsolete absolute resource
roots. The baseline preserves the same JSON input, delivers 5,000 editable SVG
rectangles and admits their IDs, order, local controls, paints and transforms
before pinned rendering. Its two engine-only history checks remain explicitly
not applicable; the original check IDs and classifications are unchanged.

Six focused B03 tests passed on Windows in 157.8 seconds. Linux ran B03 and the
existing three harness modules, 25 tests, in 123.4 seconds. Both bind fingerprint
`23aee426077905aff645ae3fc8e7aeb8acb3429efa3bdd51ec0313855fd3c73d`.
The Windows regression selection ran 25 tests in 94.9 seconds; Linux's reference
workflow module ran six tests in 66.2 seconds. No selected check failed, remained
pending or skipped. An initial over-budget B03 attempt remains recorded as
pending; shared synthetic setup and identical-image oracle reuse reduced the
final focused run below the 180-second budget without removing fault cases.

Five synthetic-client B03 trials passed with real pinned baseline tools on each
platform, and all five Windows captures passed rejudging with unchanged inputs.
The baseline reports bind candidate
`c0c37081f247dbdffd8942a68f22c71f8b1c2628811c344e7da1e152ddfdb0f2`
(including the subsequent dependency-expectation correction) and prompt
`3e72bb258a2b271bf6722bd290bc8c2e481b31c905c0dd9e085d86fbab9c4c3d`.
These are correctness checks on a shared host; no actual model, isolated
performance measurement or complete W2 acceptance is claimed.

B04 now separates its original SVG fixture, prompt, solve and judge. Both arms
must retain the layer/path controls and requested world translation, deliver SVG
and PNG, and bind truthful ID/description loss reporting to the original source
hash. The SVG is independently admitted for structure, controls, transforms and
paint before rendering. Inkbolt also delivers its complete import receipt and
snapshot; the judge repeats the import and freshly renders both the snapshot and
delivered SVG. A restored description is accepted when accurately reported.
The unchanged four check IDs and classifications remain; only the snapshot check
is not applicable to the no-engine baseline.

The seven B04 tests and 22 verifier tests passed on Windows in 44.6 seconds;
15 existing driver/reference regression tests passed in 105.3 seconds. Linux
ran all 44 selected tests in 77.0 seconds. No selected check failed, remained
pending or skipped. The final Windows regression and Linux reports bind candidate
`e47723b0dc0843eb32f05d3941968f48b224b26592d8560d886c1b8b91280793`.
Five synthetic-client B04 trials passed with real pinned tools on each platform,
and all five Windows captures passed independent rejudging. Baseline reports
bind that same candidate and prompt
`f70a0836d0c92dd84fc42b515aa83d9f5f778cd71f5941141dc89bcd2580c239`.
Inputs remained unchanged. These establish harness correctness under shared host
conditions, not actual model performance or complete W2 acceptance.

B05 now separates the original shared-palette fixture, prompt, solve and judge.
The delivered snapshot must retain both live swatch references and all unrelated
state; only the shared color and revision may change. The judge checks fresh
current/original renders and binds saved history to the exact source, delivery
and current session revision. A flattened but visually correct delivery fails.
Both arms receive the same JSON fixture. The baseline admits three editable SVG
rectangles before pinned rendering and applies the same final pixel oracle;
the original three engine-only checks remain explicitly not applicable.

The six B05 tests and 22 verifier tests passed on Windows in 33.3 seconds;
15 driver/reference regression tests passed in 92.2 seconds. Linux ran all 43
selected tests in 62.5 seconds. No selected check failed, remained pending or
skipped. The final Windows regression and Linux reports bind candidate
`34ba84585cfad079e15bfa0a3b2947db39361d80085e9900d92ad14bb4058f67`.
Five synthetic-client B05 trials passed with real pinned tools on each platform,
and all five Windows captures passed independent rejudging. Baseline reports
bind that same candidate and prompt
`e0f58005689872cb1b5f59ad9ce7e2f39385e5bbd9bb9672b6544d892e842792`.
Inputs remained unchanged. These are correctness checks on a shared host, not
actual model trials, isolated performance measurements or full W2 acceptance.

B06 now separates the original linked-flow scenario into a common JSON fixture,
versioned prompt, solve and independent judge. The original font's optional
family-name table supports the pinned baseline while retaining its authored
outlines, advances and line geometry. Both arms must preserve logical source,
diagnose the four unplaced characters and repair only the second slot. The
baseline retains editable layout JSON plus SVG text with explicit source
intervals; every report, frame, substring and final pixel is independently
checked. Inkbolt's saved history must contain the exact source and final
snapshot, with a matching head. Captured font stores rejudge after relocation.
All six original check IDs and classifications remain; the two history checks
are explicitly not applicable to the baseline.

The seven B06 tests passed on Windows in 33.8 seconds; 37 driver/reference and
verifier regression tests passed in 89.8 seconds. Linux ran all 44 selected
tests in 64.2 seconds. The final checks had no failures, pending checks or skips,
and all three reports bind candidate
`027267a1f7c2a03757cf0e28eff31f63159524d6394ff1610c7f1c116ee96efb`.
Five synthetic-client trials passed with real pinned baseline tools on each
platform, and all five Windows captures passed independent rejudging. Those
reports bind the same candidate and prompt
`6f23a71634bade88c8df5affe549eafc4572b961a877629166c9fa26656502df`.
Inputs remained unchanged. These establish harness correctness on a shared
host, not genuine model trials, isolated performance or full W2 acceptance.

B07 now separates the four multilingual strings, prompt, solve and independent
judge. Original font name records enable baseline discovery without changing
any outline, metric or shaping table; the original unnamed fixture keeps its
exact identity. Both arms deliver logical source-to-glyph mappings, checked
against authored glyph IDs, intervals, origins and advances. Inkbolt's judge
also checks fresh text inspection and binds its reopened snapshot to current
history. Harmless author IDs, labels and descriptive metadata are accepted;
visible formatting, editable source and geometry remain independently checked.
The baseline preserves logical Unicode SVG text and bounded editable spans.
Its mapping is a delivered artifact, not a claim of observed renderer internals.
All four original check IDs/classes and the exact pixel oracle remain unchanged.

The final eight typography checks passed in 76.5 seconds on Windows and 58.9
seconds on Linux, with no failures, pending checks or skips. Both reports bind
candidate `cb8d0988d59b29186df8b55f396afb411e96f6532774870e6a1b7220145bdd53`.
Before the final metadata allowance, 37 harness/verifier regression tests passed
on Windows in 104.3 seconds and all 45 selected tests passed on Linux in 76.6
seconds; these earlier reports separately bind
`ba0ea7471421a6ae983028457c31a01c717557e6380751548116f23218295a30`.
Five synthetic-client trials with pinned baseline tools passed on each platform,
and all five Windows captures passed independent rejudging, on the final candidate
and prompt `c4ea9d8f8462f9bd8b388c3a4cb540ad79d8e3e5208755e7e16b5c916ab74864`.
Inputs remained unchanged. A separate negative control retained correct logical
text and declared glyphs but used unpositioned SVG runs: the pinned renderer's
fourth row differed, and both glyph/pixel checks failed. Explicitly positioned
editable spans passed without changing the oracle. These are shared-host harness
checks, not actual model trials, isolated performance or full W2 acceptance.

B08 separates the original 16-by-16 raster fixture, L-shaped selection, prompt,
solver and independent judge. Both arms retain all 256 original RGBA samples,
the exact 56-pixel selection, a linked mask and an independently checked preview.
The engine judge reopens the delivery, compares the original layer and unchanged
document properties, renders current and historical snapshots, and binds them to
the saved history head. Equivalent mask storage extents are accepted. The baseline
retains a bounded layer manifest and separate pixel, mask and selection PNGs;
pinned Pillow independently decodes and composes them without launching Inkbolt.
The original five check IDs and classifications remain unchanged; the baseline's
two engine-history checks are explicitly not applicable.

The seven B08 tests plus driver, reference and verifier checks passed all 44
selected tests on Windows in 103.1 seconds and Linux in 76.9 seconds. No selected
check failed or remained pending, and both reports recorded unchanged inputs.
Unaffected engine stages reused identical passes. These shared-host checks verify
correctness, not isolated performance. Candidate fingerprint:
`ee16930b0e74e24180adee53faa7813e23e5b841537e10512ff0560579914c83`.
Five synthetic baseline trials passed on each platform with real pinned Pillow,
and all five Windows captures passed independent rejudging on that same candidate.
Prompt SHA-256:
`0ce267330297e3ae595d5410f8388a10901b951059d4755f9abcbebc56b54ab0`.
An additional real-Pillow control accepted the correct bundle and rejected six
damaged variants, including an erased sample outside the visible mask, changed
coverage, a transparent or non-gray mask, and changed dimensions. Reports are
retained externally under the `w2-b08-` evidence prefix. No actual model was run.

B09 separates the unchanged local raster-defect fixture, prompt, solver and
independent judge. Its original source identity remains
`200dda427495dfe414221be21d9db65ce8ab8091bd0ecac3cf34b7f397292558`.
The engine judge checks all 256 RGBA samples, only the four requested pixel
changes, unchanged document properties, fresh current/original images and exact
saved-history/head binding. An independent session using two row edits passes
without solver records. The baseline retains an editable pixel PNG and layer
manifest; pinned Pillow independently decodes the layer, and the delivered
preview must also match the numerical oracle. The original four check IDs and
classes remain unchanged; saved-revision/history checks are not applicable to
the baseline.

All 44 selected B09, driver, reference and verifier tests passed on Windows in
96.5 seconds and Linux in 68.0 seconds. No selected checks failed or remained
pending; unaffected engine stages reused identical passes. Both final reports
recorded unchanged inputs and candidate fingerprint:
`7f08f1928faa9bc463815b817d7038d05e0ec1e3ff90c17b00fa205a52698c3a`.
Five synthetic baseline trials per platform and five Windows capture rechecks
passed with real pinned Pillow on that candidate. Prompt SHA-256:
`26be1006ce7ec12ae2c1c9c30e057b0151a0f7852a1dd85a3099039a929d1753`.
Additional decoder controls accepted correct RGB and RGBA layers and rejected
seven faulty variants: an unrepaired defect, changed unrelated pixel, changed
alpha, dimensions, grayscale mode, a disguised JPEG and an animated PNG. All
retained previews were correct, so those negatives exercise independent layer
checks. Evidence is retained externally under `w2-b09-`, with the limited decoder
controls in `w2-b09-pillow-controls-02`. These are shared-host correctness checks;
no actual model or isolated performance result is claimed.

The external harness now retains a separate owned-command-tree commit-memory
observation on Windows, including short-lived descendants and cleanup. It does
not relabel client/launcher memory as engine-only usage. Failed/timeout clients
retain their observations; malformed imported measurements and client-supplied
memory claims reject. Older captures and Linux commit measurements remain
explicitly unavailable. This is a prerequisite for B10's fixed memory budget,
not completion of that adapter or a new platform memory claim.

Focused checks ran 45 tests on Windows in 54.7 seconds and 36 on Linux in
19.4 seconds, with nine explicit Windows-only skips on Linux. Shared process-runner,
recovery and consumer tests were included. No selected stage failed or remained
pending; the Windows formatting/build/Clippy stages reused identical passes.
Both reports recorded unchanged candidate fingerprint
`ba0005828193351303103009758c2816ef86554f7b5888e258951c7833a1dda8`.
Evidence is retained externally under `w2-external-memory-final-`; these are
shared-host correctness checks, not isolated performance or full W2 acceptance.

B10 now separates the unchanged photograph fixture, shared prompt, reference
solver and independent delivered-evidence judge. Its original PNG identity remains
`f779277bae78c973c8cb229b014bc4771fe25de47879d868c220f792077d9958`.
The judge reconstructs all 135 native block identities from the original channels,
checks the exact patch and reviewed state, binds original/edit/undo/redo snapshots
to durable receipts and the final head, and checks delivered and freshly exported
TIFF samples. Publication hashes and the focused PNG also remain required.
An independently named session and captured workspace relocated away from its old
absolute resource roots pass. Damaged deliverables cannot hide behind retained
correct responses. The baseline's separately authored byte-processing client
preserves native depth, with pinned Pillow used for preview and independent TIFF
admission. All ten original check IDs/classes and the 256 MiB budget are retained.

Final focused checks passed 41 tests on Windows in 96.7 seconds and 39 on Linux
in 82.3 seconds, with two explicit Windows-counter skips on Linux. Linux now runs
the full CLI/MCP photograph and external capture checks, asserting that only its
unavailable commit-memory budget fails. No selected verification stage failed or
remained pending; unchanged engine formatting/build/Clippy results were reused.
Both final reports recorded unchanged inputs and candidate fingerprint:
`9673684f785c911ec01b34b5633dfb994e1d170ed909ed6300e2646c5c3c1a14`.

Five synthetic baseline trials with the real pinned tools passed on Windows,
and all five captured runs passed rejudging with their original memory evidence.
All five Linux trials passed native samples, focused preview and source preservation;
their overall result remains failed solely because commit-memory evidence is
unavailable. No Linux B10 budget pass is claimed. Real-tool controls accepted the
correct TIFF and rejected eight malformed/changed variants, including a single
native low-bit change, depth, sample meaning, alpha, orientation and dimensions.
The tests, trials and controls share the candidate above. Prompt SHA-256:
`da84a8022674bdf878bcd5b3dc61b67e21b4278a9261e6d8d373817ee55f4677`.
Evidence is retained externally under `w2-b10-`; these are shared-host correctness
results with synthetic clients, not genuine model trials, isolated performance
comparisons or full W2 acceptance.

B11 now separates the original mixed-composition fixture, shared prompt,
reference solver and independent delivered-evidence judge. Original PNG identity:
`d3b13b878b717a8b41f391753b0bd6f372116f0797d261c0e8acf296165fe208`.
The judge checks the complete original/final compositions, canonical image bytes,
saved revisions and final head. Both fresh and delivered current/historical pixels
face the unchanged exact rational oracle. Independently chosen IDs, multiple edits
and captured workspaces moved away from their old resource roots pass; altered
controls, assets, deliveries and history fail. The baseline retains a bounded
editable manifest and separate mask; pinned Pillow decoding and fresh numerical
composition preserve intermediate precision. All five original check IDs/classes
remain fixed; the two engine-only checks are explicitly not applicable there.

Focused verification passed 48 tests on Windows in 112.5 seconds and 46 on Linux
in 80.1 seconds, with two explicit Windows-counter skips on Linux. No selected
stage failed or remained pending; unchanged engine formatting/build/Clippy results
were reused. Both reports and the baseline runs recorded unchanged candidate:
`1aac58e2b6e9c336d06f9a46d8076e369ed15e67e0dd28145d3d2c6295b0717b`.
Five synthetic trials with real pinned tools passed on each platform; all five
Windows captures also passed rejudging. Separate real-tool controls accepted L,
RGB and RGBA grayscale masks and rejected eight malformed or altered inputs,
including changed source pixels behind an unchanged correct preview. Prompt hash:
`53bd963c20d0ebdeb266cec2d77237eef00564dda26720612c7cdebbff3b142c`.
Evidence remains external under `w2-b11-`. These are shared-host correctness
results, not genuine model trials, performance comparisons or full W2 acceptance.

B12 separates the original layout-variant fixture, shared prompt, reference solve
and independent judge. The four original font/license/image files remain unchanged;
a named rendering companion supplies SVG font selection while preserving every
glyph/metric table. The reference still uses 18 solve commands. Its separate judge
checks all five snapshots, the restored current head, complete typed definitions
and inheritance, pinned resource bytes, and earlier PNGs against completed durable
publication receipts. All three delivered and freshly rendered boards face the
unchanged pixel oracle. Arbitrary non-artboard IDs, extra edit steps and relocated
captures pass; incorrect controls, resources, outputs, receipt bindings and history
fail. The baseline retains shared editable SVG instances, dataset values and the
restored base. The seven original check IDs/classes remain fixed, with its two
engine-only checks explicitly not applicable.

The separated reference metric now recognizes a successful PNG publication only
when both hash and byte count match the independently checked image. Judge calls,
lost/missing responses and wrong media/identities cannot invent preview timing.
Focused verification passed 50 tests on Windows in 108.4 seconds and 48 on Linux
in 77.3 seconds, with two explicit Windows-counter skips. No selected stage failed
or remained pending; unchanged engine formatting/build/Clippy results were reused.
Both reports and the final trials retained unchanged candidate fingerprint:
`4d1113cfdd2aebe4eb3ca8815f13323a21fec015f43e2c8d02b7e5875d4bf9af`.
Five real-tool synthetic baseline trials passed on each platform; all five Windows
captures passed rejudging. The client renders full sheets and crops boards with
pinned imaging tools; the judge independently renders each viewport. Prompt hash:
`1355cb1b113d313f2ccc62db1923350b002e5acbdd863e5faf3d82509c404894`.
Evidence remains external under `w2-b12-`. These are shared-host correctness
results, not genuine model trials, performance comparisons or full W2 acceptance.

B13 separates the transparent-screen prompt, six-command reference solve and
independent judge. All four original checks remain fixed. Both delivered and
freshly rendered PNGs must preserve exact straight-alpha pixels and a single
valid sRGB declaration while stripping private/descriptive metadata. The editable
source retains its private note. Fresh publication and duplicate-output probes
use owned judge directories, including when rechecking relocated captures;
captured files remain unchanged. These separate CLI probes are explicitly counted
as judge traffic and excluded from persistent MCP server memory measurements.
The baseline retains admitted editable SVG and a content-bound create-only recipe;
pinned Pillow independently renders and probes a protected copy. Its engine-only
snapshot check is explicitly not applicable. This demonstrates reproducible
publication behavior, not authenticated historical client actions.

Focused verification passed 50 tests on Windows in 129.7 seconds and 48 on Linux
in 109.7 seconds, with two explicit Windows-counter skips. No selected stage failed
or remained pending; unchanged engine formatting/build/Clippy results were reused.
Both reports and final trials retained unchanged candidate fingerprint:
`9ea5084f4a6f17917d978b90ae9e884bb55b4fca48dca30ddc472dc12be61fa5`.
Five real-tool synthetic baseline trials passed on each platform; all five Windows
captures passed rejudging. Controls reject altered geometry, alpha, private notes,
delivered pixels, color metadata, manifest identities and protected output bytes.
Prompt hash: `eef3d91c9764e67b5071b1cfa73eda4621c852f3df63ad5de48339b4681390db`.
Evidence remains external under `w2-b13-`. These are shared-host correctness
results, not genuine model trials, performance comparisons or full W2 acceptance.

B14 separates the original two ICC fixtures, shared print prompt, seven-command
reference solve and independent nine-command judge. All seven original check
IDs/classes remain fixed. The judge checks full editable controls, saved history,
fresh preview/PDF/preflight and the completed original publication receipt;
independent IDs and relocated captures pass without consulting solver results.
Both original profile hashes are unchanged. The baseline retains a bounded
editable print recipe and authors native PDF using ordinary Python. Pinned Pillow
independently derives its ICC display preview. A bounded PDF reader checks exact
physical boxes, embedded bytes/channel declarations, native process/spot operands
and functions, painted geometry, transforms and compositing state. Source/history
checks are explicitly not applicable there. Incorrect profiles, inks, geometry,
preview pixels, limitations and unsupported PDF controls fail.

Focused verification passed 50 tests on Windows in 137.2 seconds and 48 on Linux
in 106.0 seconds, with two explicit Windows-counter skips. No selected stage failed
or remained pending; unchanged engine formatting/build/Clippy results were reused.
Both final reports and trials retained unchanged candidate fingerprint:
`8818ab4cd2d7ddbe2139b9781798f9ccd208d2a70a1403c2d7a876e798476f22`.
Five real-tool synthetic baseline trials passed on each platform; all five Windows
captures passed rejudging. Prompt hash:
`29b6d9cda5c6e5c789a65da1d1fcdc89196a144b339bedd5e750a27c594afb74`.
Evidence remains external under `w2-b14-`. These are shared-host correctness
results, not press calibration, genuine model trials, performance comparisons or
full W2 acceptance. The new bounded reader is not a general PDF rasterizer.

B15 separates the original missing/corrupt resource fixture, shared prompt,
eleven-command solve and independent ten-command judge. All four fixture hashes
and six check IDs/classes remain unchanged. The judge checks complete artwork,
correct code/location pairs, exact replacement bytes, fresh/delivered pixels and
the original missing/corrupt cache. Creation/repair receipts, current saved state,
retained proposal state hashes and resource-action fingerprint must agree.
Independent session/request IDs and relocated captures pass without accessing
solver results or stale absolute roots. Captured files remain unchanged.

The baseline retains the editable source and a separate resource-binding recipe.
Pinned Pillow independently decodes the original PNGs and composes the repaired
cache. Changed artwork/descriptors, malformed replacements, repaired old cache,
incorrect diagnostics, pixels, review hashes or historical bindings fail. Numeric
equivalents such as 8 and 8.0 are accepted; boolean replacements are rejected.
Only its two Inkbolt history checks are explicitly not applicable.

Focused verification passed 49 tests on Windows in 122.9 seconds and 47 on Linux
in 94.6 seconds, with two explicit Windows-counter skips. No selected stage failed
or remained pending; unchanged engine formatting/build/Clippy results were reused.
Both final reports and trials retained unchanged candidate fingerprint:
`41106fbd0735235e7ef9d86c61bc363b130abf9d17916c147f8826b013b076bc`.
Five real-tool synthetic baseline trials passed on each platform; all five Windows
captures passed rejudging. A separate pinned-tool numeric-equivalence control also
passed. Prompt hash:
`a0249e33438b2c65d8ec70fba2d9f6e644e754f1bded98f290c0cdb9fcb30c5f`.
Evidence remains external under `w2-b15-`. These are shared-host correctness
results, not authenticated client-review history, genuine model trials,
performance comparisons or full W2 acceptance.

B16 separates the original overflowing text fixture, shared prompt, eleven-command
solve and independent twelve-command judge. The original font/license hashes and
all five check IDs/classes remain unchanged. A rendering companion adds a family
name while preserving all non-naming font tables apart from the checksum. The
judge checks complete original/repaired controls, actual font/license bytes,
fresh diagnosis/preflight/preview, retained proposal fingerprints and durable
creation/repair/publication receipts. Only frame width changes from 12 to 24;
text, font, overflow policy and unrelated artwork remain exact. Independent IDs
and relocated captures pass without solver results or stale resource-root access.
Changed sources, reports, review/delivery pixels, fingerprints and histories fail.

The baseline retains bounded before/after recipes and editable SVG text. It reads
the original font advances, rejects unsupported or changed controls before
rendering, and uses pinned resvg plus Python/Pillow to prepare and publish the
repaired image. Both arms check the four original artifact outcomes, including
exact prepared/delivered byte identities. Only Inkbolt history is not applicable.

Focused verification passed 49 tests on Windows in 129.5 seconds and 47 on Linux
in 106.1 seconds, with two explicit Windows-counter skips. No selected stage failed
or remained pending; unchanged engine formatting/build/Clippy results were reused.
Both final reports and trials retained unchanged candidate fingerprint:
`4e3bc53e5f6e23766b25c9ef5e6db405f4e589ed16238f76d43c6da041196896`.
Five real-tool synthetic baseline trials passed on each platform; all five Windows
captures passed rejudging. Prompt hash:
`895b9e155ab4b7e14c33a768ed81af333f695073a21671aa30fa0ee172f77366`.
Evidence remains external under `w2-b16-`. These are shared-host correctness
results, not authenticated client-review history, genuine model trials,
performance comparisons or full W2 acceptance.

B17 separates the unchanged two-object fixture, recovery prompt, solve and
independent receipt/history judge. The reference retains its nine commands;
external clients start after two harness commands create the session and withhold
the move response. Setup costs and response identity are retained separately from
client metrics, checked after execution and preserved on import without reinjection.
The judge reopens original/edit/undo sources and durable receipts, checks fresh
pixels, and repeats the historical retry on a private copy of the captured store.
Captured files stay unchanged; altered requests, receipts, extra revisions,
artwork and setup evidence fail. All five checks remain fixed. The no-engine
baseline remains explicitly not applicable to this engine-specific task.

The combined Windows check found a real cancellation-cleanup race in the existing
external-client timeout fixture. A nested-job control reproduced locked working
folders in 20 of 20 immediate removals despite zero active job processes. Waiting
on handles to owned members eliminated those 20 failures. The helper now pins and
rechecks job membership, waits within the existing three-second cleanup bound,
and closes its handles. The regression performs eight immediate removals without
retry or grace sleeps. Query/wait failures leave memory evidence unavailable.
The original failed run remains retained; its unchanged driver-only recheck also
passed, but that transient pass was not substituted for the fix and regression.

Final focused verification passed 51 tests on Windows in 140.1 seconds and 48 on
Linux in 92.3 seconds, with three explicit Windows-only skips. All selected stages,
including formatting, locked build and all-target Clippy, ran afresh and passed.
The nine Windows recovery/handoff consumer tests also passed in 54.7 seconds,
with unchanged build checks reused. No selected stages failed or remained pending.
Final reports and trials retained unchanged candidate fingerprint:
`932c66671c2b49513384032fb6e30cd9d2ca29a26e6a3a3b6509dfdbec29d162`.
Five external synthetic recovery trials passed on each platform; all five Windows
captures passed rejudging. Prompt hash:
`f575638fd7aeda0c5faaee06affa8eec1297b006aa0824e5edffc373d57be4e6`.
Evidence remains external under `w2-b17-`. Linux release-build setup took 162.3
seconds separately from the 92.3-second routine checks. These are shared-host
correctness results, not authenticated client behavior, genuine model trials,
performance comparisons or full W2 acceptance.

B18 separates the unchanged two-object fixture, conflict prompt, solve and
independent judge. Three harness commands create the session, review the target
move and commit the other writer's move. The client starts with a real stale
proposal at revision 1; the reference retains ten commands including setup.
Bounded pre-client database evidence and the supplied request are pinned before
client execution and preserved on import. The judge reopens all three states and
durable receipts, binds the replacement's action fingerprint and state hashes,
checks current/historical pixels and reproduces the stale rejection on a private
copy of the pre-client store. The rejected request must leave revision 1 unchanged.
Wrong requests/errors/proposals, lost edits, changed controls, extra commits and
altered setup fail. Captured files remain unchanged. All five checks and the
engine-specific no-engine exclusion remain fixed.

Windows passed 59 selected tests in 121.5 seconds; Linux passed 56 in 87.3 seconds
with three explicit Windows-only skips. Formatting, locked build and all-target
Clippy reused identical passing inputs; all selected Python modules ran afresh.
No selected stage failed or remained pending. The broader Windows candidate
differs from the final candidate only by a removed trailing blank line in the
shared graphics helper; all eight conflict tests passed again in 32.4 seconds
after that whitespace cleanup. Linux and the repeated conflict trials used final
candidate fingerprint:
`78e088272ae4468811f7b6b57b60f38fb56d95e291d9137cfda4177e410cb0f6`.
Five external synthetic trials passed on each platform and all five Windows
captures passed rejudging, with identical candidate/prompt hashes and unchanged
inputs. Prompt hash:
`5b604b46bd953456eddb22e87e08751ba41a3c0d9e8dca39bf02fb7cf99049ef`.
Evidence remains external under `w2-b18-`. Initial failed development checks are
retained: the judge was corrected to respect captured resource-path boundaries,
and the reference immutability test now distinguishes new traffic logs from
changed input/delivery files. These are shared-host correctness results, not
authenticated client behavior, genuine model trials, performance comparisons or
full W2 milestone acceptance. No engine behavior or checkpoint credit changed.

B19 now separates its unchanged original texture fixture, recovery prompt,
controlled reference solve and independent judge. The solve retains actual
attempts and ends before judging. The harness freezes fault/process/output
observations, including a direct checksummed-ledger read at the interrupted
inspection checkpoint. The judge reopens original/current documents, session/job
receipts and the publication ledger, renders fresh focused/full previews and
checks exact pixels, editable controls, attempt counts, absence before resume,
physical publication identity, overwrite refusal and source/history preservation.
All eight original checks remain fixed. Twelve judge calls are separated from
solve costs; container accounting still includes every command and background
process. The external controller and captured-trial integration are now implemented
and have the focused evidence below; full W2 acceptance remains open.

Nine Windows recovery tests passed in 113.7 seconds, including both transports,
cache-independent rejudging, real extra revisions and eleven retained-artifact
fault cases. Seventeen shared benchmark tests also passed; the corrected
dependency-boundary assertion passed all 26 verifier tests in 34.6 seconds.
Initial failed reports remain retained: terminal comparison now permits the
worker's final memory report to arrive after publication, inspection captures
the ledger directly instead of depending on periodic polling, and test cleanup
closes the owned runtime before removing its temporary directory. The standalone
judge test does not depend on report documents, avoiding needless rendering
reruns after documentation-only changes. Runtime and judge bytes match the final
candidate; only contract documentation and that test-only assertion differ across
the focused/integration Windows reports.

Linux passed 41 tests in 86.5 seconds with eleven explicit platform skips. Eight
are job/containment checks and three are Windows verification checks; this is not
Unix job support. Unchanged formatting, locked build and all-target Clippy inputs
reused passing results. No selected checks remain unresolved. Five CLI and five
MCP release references passed with 23 solve calls, 12 judge calls, complete owned
process observations and zero active processes at close in every trial. Final
Linux/reference candidate fingerprint:
`b3b6614d59af9c4e3f907d08caad28ccb09580be5ed2a6ffdcad96c73a289024`.
Prompt hash:
`fcffddcfddd04036491c8960c36317ce360fe2b124843b7476f29fce47bc1673`.
Evidence remains external under `w2-b19-judge-`, with the original interleaved
control under `w2-b19-reference-before-01`. These shared-host correctness
references are not model trials, performance comparisons or full W2 acceptance.
No engine behavior, supported platform tier or checkpoint credit changed.

B19's external lifecycle now uses a bounded local bridge with three harness-owned
fault controls. The client chooses ordinary import/edit/review/job/retry commands;
the harness owns the engine process tree, observes real cancellation/interruption
and releases its queue gate on client failure. Preparation starts no processes.
Complete traffic, preview timing, process peaks and fault/output observations stay
outside the solver workspace and are bound into the capture. Rejudging opens the
captured durable state without reinjecting faults. All eight original checks,
source preservation and complete process observations remain required. Synthetic
clients cannot claim model credit; client/model usage and engine measurements are
reported separately. A repaired engine diagnostic remains a measured call without
changing a correct external task into a failure; live/import scoring agrees.

Focused Windows checks passed 40 tests in 77.4 seconds and 32 shared/reference
tests in 114.3 seconds. Linux ran the same selected modules in 82.2 seconds: 58
tests executed, with eleven explicit job/containment skips and three Windows
verification skips. Formatting, locked build and all-target Clippy reused
unchanged passes; no selected check failed or remained pending. Regressions cover
the real bridge CLI, relative preparation paths, full/compact receipts, repaired
invalid requests, failed clients, invalid fault controls, wrong pixels, moved
captures, changed evidence, metric-schema injection and unchanged source/import
workspaces. Earlier failed feedback is retained; the live/import scoring mismatch
was corrected before these final passes.

Five fresh release external trials and five imported rejudgments passed, each
with 23 observed solve commands, 12 judge commands, three retries, three expected
refusals and complete engine memory observations. Every owned engine tree closed
with zero active processes. Each imported capture preserved the original measured
metrics and preview timing, and all original/imported workspace hashes matched.
The final Windows/Linux/trial candidate fingerprint was
`709cd315e62078687e5472aeac458161e1489aaef47ade27cb0c3edc17160d9d`;
prompt version 2 hash was
`dbe1586ac7e7da36479931fa062caccee90041577e685ea21fd9e55658506eb9`.
Only this status document and the primary plan table changed afterward. Evidence
is retained externally under `w2-b19-external-`. These are shared-host synthetic
correctness checks, not genuine model trials, performance comparisons, Unix job
support, additional checkpoint credit or full-suite milestone acceptance.

B20 now separates its original two-frame RGBA fixture, versioned prompt,
reference solve and independent durable/artifact judge. The solve records actual
reviews, attempts, snapshots and outputs. The harness freezes observed consumer
traffic, process accounting and initial delivery hashes. Judgment reopens both
saved histories and receipts, verifies the exact source edit and explicit relink,
and independently decodes all five movies. No judge command edits or renders the
delivered workspace. Relative, content-bound consumer asset paths prepare for
later capture relocation without rewriting history. All fifteen original checks
remain mandatory; no engine behavior or checkpoint credit changed.

The final focused Windows gate passed 35 tests in 40.7 seconds with the pinned
real consumer/encoder/probe tools. It reran formatting, locked build and
all-target Clippy without reuse. The seven shared benchmark and four external
recovery tests also passed; that earlier 124.5-second run retained a verifier
dependency assertion failure. Narrowing the new test's artifact enumeration
removed an accidental whole-repository dependency, and the final focused gate
passed that assertion. An earlier negative test wrote an unchanged pixel; it now
flips a byte. These failed feedback reports remain retained. The real-tool tests
clear solver caches, preserve delivered files and both databases, reject twelve
altered artifact/observation cases and detect actual extra revisions in both
engines. Their explicit external-tool configuration requires force-refreshing
selected checks; ordinary CI retains explicit skips when those tools are absent.

WSL passed the same selected portable modules in 85.0 seconds, with 35 tests
executed and eleven explicit skips: five B20 Windows/external-consumer tests,
three B19 job checks and three Windows verifier checks. Unchanged Rust checks
reused passing results. No selected check remains unresolved. Five CLI and five
MCP release references passed. Each measured 15 Inkbolt and 21 consumer solve
commands, then nine fresh queries per engine and 20 independent decoder/probe
calls. All consumer process observations were complete, with zero active
processes at close. Consumer judge cost and decoding are excluded from solve
traffic and wall time; the individual Inkbolt and consumer-tree memory scopes
remain separate. These are shared-host correctness references, not performance
comparisons or genuine model trials.

Final Windows/Linux/reference candidate fingerprint:
`270af313bbd4b1509cee2fa28ed7e1ac6f280875548fbbb80890c1e9bc44c215`.
Prompt version 1 hash:
`e889d8bacc7bbd2e90d9947cd3651d71fe8f283d195659609cec791b2fb7ad86`.
Only this status document and the primary plan table changed afterward. Evidence
is external under `w2-b20-judge-`; the original interleaved control is retained
under `w2-b20-reference-before-01` and the pinned tool identities under
`w2-b20-consumer-tools`. External-client, capture/import and no-engine B20 baseline
integration were still open at that reference-separation checkpoint.

B20 now has an external lifecycle and no-Inkbolt baseline. Its local bridge owns
both engines, measures their commands/processes, enforces consumer workspace
paths and freezes delivery hashes after compilation. The prompt binds the exact
task IDs while allowing independent client step labels. Ordinary returned engine
errors can be repaired. Captures bind actual requests/responses, a fixed metric
schema and observed preview bytes/timestamps; imports retain solve measurements
and rejudge moved workspaces without running the client or rewriting history.

The baseline authors editable layer JSON and exact PNG frames with pinned image
tools. Both arms use the same pinned consumer solely to compile/render the
required video. The baseline calls no Inkbolt process, including while judging.
It preserves all seven artifact checks; all eight engine checks are explicitly
not applicable. Pinned Pillow reconstructs the edit, and independent decoders
check every video frame, clock and silent PCM sample. This does not grant typed
handoff or managed-history guarantees to ordinary files.

The final focused Windows gate passed 50 tests in 90.4 seconds, with formatting,
locked build and all-target Clippy rerun. It includes real consumer/image tools,
both moved-capture paths, distinct step labels, repaired engine errors, changed
preview/evidence rejection, baseline isolation and consumer path bounds. Shared
B19 recovery and generic driver tests pass after the capture-hook extension.
WSL passed 45 selected tests in 91.1 seconds, including the shared reference
adapters, with twelve explicit skips: six external-tool B20 cases, three B19 job
cases and three Windows verifier cases. Its unchanged Rust checks reused passes.
No selected check remains failed or pending. The earlier focused Windows run
also passed (41 tests, 57.3 seconds); all reports are retained.

Five fresh synthetic-client runs and five imported rejudgments passed in each
arm. Every source/import workspace retained its captured hashes and measured
solve data. The model path measured 15 Inkbolt plus 21 consumer solve commands,
nine judge queries per engine and 20 decoder/probe calls. The baseline measured
zero Inkbolt commands, six consumer commands and 16 independent decoder/probe
calls. Consumer process observations were complete with zero active processes;
baseline Inkbolt memory remains unavailable. Five fresh CLI and five MCP
references also passed on that same candidate. These shared-host synthetic
controls establish neither a model success rate nor an efficiency advantage.

Final Windows/Linux/reference/external candidate fingerprint:
`0c1686e14bf9d087222e0e92d5bd7bae8a0a91646aca4272e84409bce45a8b46`.
Prompt version 2 hash:
`ca5e7d5b97f0e8fecb605c203fea6e195066f9b5cf8183972f77d830eeae62a8`.
Only status records in this document, PLATFORMS.md and the primary plan changed
afterward. Evidence is external under `w2-b20-external-`; pinned tool identities
remain under `w2-b20-consumer-tools`. No engine behavior or checkpoint changed.

Matched comparison and losing-task reporting now preserve every selected attempt,
separate artifact success from engine guarantees, and keep unavailable usage
unknown. The fixed policy requires five matched repetitions; cost signals require
five jointly successful artifact pairs and complete observations. Reports retain
uncertainty intervals, failed/missing checks and evidence mismatches. Full model,
baseline and sister-product completion remain separate gates. See the
[comparison contract](BENCHMARK_COMPARISON.md).

Eighteen original comparison controls cover matching, evidence changes, missing
and failed attempts, engine-only failures, cost accounting and completion flags.
Final focused Windows verification passed 44 tests in 39.8 seconds; WSL passed
41 tests in 21.7 seconds with three explicit Windows-only verifier skips. Both
had unchanged inputs, no failures and no pending selected stages. Unchanged
format/build/Clippy results were reused; this is not fresh full-suite acceptance.
Final candidate: `e06cb76bb0e4b9d4a1989cede7bedafc774c3206576c2bbf44e1b371d7f04efd`.
Only this status record and the primary plan changed afterward.

The retained five-pair B20 synthetic controls produced identical scores and
measurements from live and imported captures. Both arms passed five artifact
trials; the equality signal is correctly visible, while all model-completion
flags remain false and unknown usage produces no cost signal. Evidence remains
external under `w2-comparison-`. No engine behavior or checkpoint credit changed.

The owner authorized genuine Codex evaluations, including smaller-model trials.
Model selection and settings belong only in external per-run configuration, with
identical settings in each pair; no model is hardcoded into Inkbolt or the harness.
The [local Codex evaluation adapter](BENCHMARK_CODEX.md) now runs a pinned client
with externally selected model/reasoning settings, retains its JSON events and
observed usage, and preserves unknown model-call counts. The client version and
driver binaries are bound to each run. Native Windows sandbox selection is
explicit; the initial pilot without that selection remains a retained failure.
No sandbox bypass, model default or automatic model substitution was added.

Genuine B02 pilots ran with two externally configured models through client
version 0.160.0, one trial per arm. The primary-model pilot passed both arms;
the smaller-model pilot passed the baseline and failed Inkbolt's required snapshot
structure. The first baseline judgments exposed two oracle restrictions absent
from the shared prompt: outer hidden overflow and rectangle fill/stroke opacity
attributes. Admission now preserves those declarations for the unchanged pinned
rendering, exact pixels, geometry and editable-source requirements. Empty source
manifests are also accepted by comparison for creation tasks whose hashed prompt
is their only input. Both corrections have regression controls.

All four original captures were rejudged without modifying their workspace or
capture bytes. The paired comparisons retain original usage and solve times,
including the smaller-model failure, with no evidence-matching issues. Neither
one-pair pilot earns a five-repetition losing-task signal, full-suite completion
or an efficiency claim. Evidence stays external under `w2-codex-`, including
original failures, external configurations and final comparisons.

Final focused Windows verification executed 32 tests in 30.4 seconds; WSL
executed 29 in 17.9 seconds with three explicit Windows-only verifier skips.
The twelve adapter and nineteen comparison controls reused identical passing
inputs in these final reports, as did unchanged format/build/Clippy stages.
There were no failures or pending selected checks. This is focused feedback,
not fresh full-suite acceptance. Final tested/rejudged candidate:
`66f718ea49c6623e53c84d2e2ed9276a4505f4f46c2a0bd60f1205e6eaa395a8`.
Only this status record and the primary plan changed afterward.

Five genuine matched B02 pairs now ran at unchanged commit `c7d9f30`, using the
same externally configured client, model and settings. Both arms passed all five
artifact and applicable workflow checks. Median input-plus-output usage was
487,207 tokens for Inkbolt versus 56,624 for the baseline (8.60x), and measured
client execution was 159.0 versus 49.7 seconds. The [published aggregate](BENCHMARK_RESULTS.md)
records conditions, wide success intervals, unknown metrics and evidence hashes.
All ten original outcomes and transcripts remain external under
`w2-codex-sol-b02-*-five-01`; comparison and first-page probe evidence are retained
beside them. The candidate fingerprint is
`abdfa023c342ea73d4cd9c0b39e2806e54ba5624099559dfcdd3045b5fdcf413`.
No judge changed between these arms, and the earlier pilots remain separate.

This B02 signal promotes a bounded W5.2 discovery change: expose schema lookup
and the general dispatcher on the first compact tool page, preserving inventory,
byte budget and behavior. The recorded CLI discovery workarounds and runtime
page probe motivate a hypothesis, not a proven client-pagination defect.
Remeasure five matched B02 pairs with unchanged client/model/settings and judges;
expect fewer discovery workarounds and lower usage without losing the 5/5
artifact/workflow result. Reassess before expanding if that benefit is absent.

The first-page increment now places schema lookup and the dispatcher before the
remaining alphabetically ordered compact tools. Full discovery keeps its prior
order and cursors. Compact cursors use a new order version, so old continuations
fail explicitly. Independent process checks execute a command using only the
first page, with and without workspace defaults, and verify repeated pages,
complete unique inventory, advertised entry points and rejected stale cursors.
Focused Windows checks passed in 104.6 seconds and WSL checks in 49.0 seconds:
one Rust catalog check and ten Python discovery/protocol tests on each platform,
plus fresh formatting, locked build and all-target Clippy. No selected checks
failed, remained pending or reused prior passes. The measured compact catalog
contains 22 tools over three pages, 71,562 JSON bytes and 71,778 wire bytes.
Reports remain external under `w5-first-page-`; the tested candidate is
`06579314368aa264f13ed5d5a173a91bc0ffe691a22a5a2d09eac942f5edfcc2`.
Only this evidence record and the primary status table changed afterward.
This is focused implementation evidence; full milestone acceptance remains open.

Five new B02 pairs at `9909329` passed both arms with unchanged candidate
`5e57d183bcaa3a6d16856980590db43643f60374cf361b3190e6981b3b628edb`.
Median reported input-plus-output tokens were 564,296 versus baseline 41,249
(13.68x), and client execution was 123.0 versus 42.4 seconds. All five Inkbolt
trials now used MCP but still fell back to CLI publication: the client refused
nine dispatcher calls under its unattended approval setting. Every trial also
hit a sibling-stack reorder index error. These observations do not establish
underlying model-call counts. Original captures, matching reports and trace
counts remain external under `w5-first-page-b02-` and `w5-first-page-trace-counts-01`.
See the [follow-up aggregate](BENCHMARK_RESULTS.md#b02-at-9909329-first-page-discovery-follow-up).
The token-reduction target was not met. Before broader interface work, verify an
explicit client approval configuration for the supplied local engine in one
pilot, then repeat matched trials; retain sandboxing and conservative engine
annotations. Item-ordering guidance remains a separate measured candidate.

The Codex adapter now accepts an explicit external `--mcp-approval-mode`; omission
keeps client defaults and no failure automatically retries with broader access.
The override applies only to the supplied server after its configuration and
executable identity checks. Baseline/bridge arms receive no server or engine
grant. Model/settings, task prompts, shell sandboxing and engine tool annotations
stay unchanged. Thirteen adapter controls plus driver/comparison coverage passed
42 tests on Windows in 18.0 seconds and WSL in 9.7 seconds, with no skips, failures
or pending selected checks. Unchanged format/build/Clippy stages reused prior
passes. Reports remain external under `w2-codex-approval-`; tested candidate:
`bdffa598686967936c79c57e1297068e31f04422e72c757cd7b455e9d4877aa6`.

A genuine B02 pilot on that same candidate passed every artifact and engine
check. It published the snapshot and all three PNGs through MCP with zero client
approval refusals. It retained the sibling-index error and CLI help attempts.
The [pilot evidence](BENCHMARK_RESULTS.md#b02-client-approval-configuration-pilot)
verifies this setup, not five-repetition efficiency or full acceptance. Earlier
results and all failed attempts remain retained.

The next focused increment adds JSON CLI help (`--help` and `-h`) with runnable
request examples, plus operation-schema and error guidance for the final
zero-based sibling index. Reorder semantics remain unchanged: parentage and
sibling order do not prescribe global snapshot storage order. Process tests run
the advertised examples, check workspace validation and lack of input effects,
and repair an invalid global index using the reported sibling scope while
preserving every item. Windows passed 50 Python tests and one focused Rust schema
test in 79.9 seconds; WSL passed 47 Python tests and the same Rust check in 45.5
seconds, with three explicit platform skips. Both also passed fresh formatting,
locked build and all-target Clippy, with no failed, pending or reused selected
checks. Reports remain external under `w5-cli-guidance-`; the unchanged tested
candidate is `a78b00939244a45beeadaf5c68868cc72ea6e465381225bfea3b870c1830d84a`.
Only this record and the primary status table changed before commit `8586e82`.
Full milestone acceptance remains open.

Five matched B02 pairs at `8586e82` passed both arms on unchanged candidate
`cd888dde1f5765d78fee3bdac3512f56e9202ffe269608253ae47b3a82d15b27`.
The external client/model/settings matched, including explicit server approval;
task prompts and judges stayed fixed. Median input-plus-output tokens were
313,114 versus 57,582 (5.44x), with client execution at 112.8 versus 46.6 seconds.
Every Inkbolt trial successfully used CLI help, read the reorder description and
avoided reorder-index failures. All chose CLI execution, so this batch does not
measure the MCP policy's effect. One insertion-index error plus schema/output
mistakes remain retained. The lower observed usage does not isolate causes across
sequential batches, and the baseline still triggers the fixed cost signal.
See the [complete result and evidence identities](BENCHMARK_RESULTS.md#b02-at-8586e82-cli-help-and-sibling-index-guidance).
Broader B01/B03 pilots now cover two externally configured models, with one
attempt per arm/task/model. Both Inkbolt pilots passed both tasks after capture
rejudgment; both baselines passed B03 and failed B01's editable-source contract.
See [the pilot record](BENCHMARK_RESULTS.md#b01b03-breadth-pilots-and-capture-rejudgment).
These small samples do not establish comparative reliability, efficiency or a
new priority signal. Model selection remains entirely external, without defaults
or fallback models in the harness or engine.

The genuine pilots exposed hidden judge assumptions about default font/session
store names. B01 now locates exact retained font/license bytes; B03 locates the
unambiguous canonical session database and passes its explicit root to engine
history checks. Missing/corrupt resources and ambiguous/corrupt history still
fail. Relocation tests preserve captured bytes. Original attempts, transcripts,
usage and initial judge failures remain retained; no model reran for rejudgment.

B01's focused Windows/WSL checks passed in 40.5/18.9 seconds. B03's first Windows
window reached its 180-second bound and remains pending in that retained report.
Avoiding duplicate exact-image decoding within each test and using the custom
store in the existing capture test kept all engine renders and changed-image
checks. Final Windows/WSL checks passed 33/30 Python tests in 158.8/135.0 seconds,
with three explicit Linux skips and no failed or pending selected checks.
Windows ran fresh format/build/Clippy; Linux reused identical prior passes.
Reports are under `w2-b01-font-store-` and `w2-b03-session-store-`; final tested
and rejudged candidate:
`115d0ecb4e8a4f3110df3936fe8c29db48cc8dd5e8fae9c171f614cd1af2f46b`.
Full-suite gates and engine checkpoint criteria remain unchanged.

Five new matched pairs per task at `8bc8982` passed every Inkbolt B01/B03 attempt
and every baseline B03 attempt. B03's median input-plus-output use was
349,212/65,011 tokens (5.37x), triggering the existing cost signal. B01's five
baseline attempts failed SVG admission for embedded font CSS, but a separately
retained post-hoc check found every delivered PNG pixel-correct. Those task
failures remain unchanged; they do not establish a general rendering or
reliability advantage. All twenty traces were reviewed, both source candidates
remained unchanged, and the selected comparisons had no matching issues.
See [the complete scope and evidence](BENCHMARK_RESULTS.md#b01b03-at-8bc8982-five-matched-pairs).

B05 had the same default-session-store assumption: a synthetic custom-store
reproduction passed live swatch/pixel checks but failed `SESSION_NOT_FOUND`.
Its judge now reuses B03's checked retained-store discovery for both revisions
and history verification. The existing capture test uses a nondefault directory,
asserts no default store exists, and verifies relocation without changing either
workspace. Existing collateral-edit, source, false-history and pixel controls
remain unchanged. Focused Windows/WSL checks passed 32/29 Python tests in
37.9/17.7 seconds, with three explicit Linux skips, unchanged Cargo passes
reused and no failed/pending selected checks. Reproduction and reports remain
under `w2-b05-store-before-01` and `w2-b05-session-store-`, tested candidate
`53ff8ce326af86910d2ba5c70c8c641f18075125a3db3294a6cf54ac605a5c0e`.
This fixes judging only; it does not change engine behavior or add model evidence.

Five matched B04/B05 pairs at `dabe447` then passed both arms on both tasks.
Median input-plus-output usage was 206,924/57,528 for SVG editing (3.60x) and
270,958/54,973 for palette editing (4.93x). Both trigger the fixed cost signal;
all palette engine-only live-reference/history checks also passed. All twenty
traces were reviewed; no prohibited tool or repository/judge access was observed.
Both candidates stayed unchanged and selected comparisons had no matching
issues. SVG baselines retained IDs/description while Inkbolt honestly reported
their loss. See [the full scope and identities](BENCHMARK_RESULTS.md#b04b05-at-dabe447-five-matched-pairs).
Before genuine B06/B07 trials, four synthetic reproductions independently
confirmed `FONT_MISSING`/`SESSION_NOT_FOUND` for valid custom stores. Both judges
now reuse the checked retained-font and session-store discovery, including
historical flow inspection. Relocated captures pass without default directories
or workspace changes; corrupted imported fonts and missing retained licenses
fail even when intact original inputs remain. Content, shaping, pixels and
history oracles are unchanged. Focused Windows/WSL checks passed 43/40 Python
tests in 79.9/64.7 seconds, with three explicit Linux skips, unchanged Cargo
passes reused and no failed/pending selected checks. Reproductions and reports
remain under `w2-text-stores-before-01` and `w2-text-stores-`, tested candidate
`46e8c61586fe94fdf7f5e7249bd41530ad1d79115e74c632068a14ac075b1230`.
This correction changes judging only;
model settings remain external and no engine behavior or checkpoint changed.

Five matched B06/B07 pairs at `a7e034e` are now retained and reviewed. Both B06
arms passed all five attempts, with 337,131/76,580 median input-plus-output tokens
(4.40x). All B07 delivered/fresh pixels passed in both arms. Inkbolt's original
B07 failures came solely from the judge prescribing default baseline storage
where the prompt allowed equivalent explicit placement. The corrected judge
retains independent glyph and pixel oracles; fixed/ascent controls pass and a
one-pixel shift fails. The first negative fixture overflowed its frame before
judging; its retained failure led to a renderable upward-shift fixture.
Focused Windows/WSL verification passed 36/33 Python tests in 113.6/82.3 seconds,
with three explicit Linux skips, unchanged Cargo passes reused, and no failed or
pending selected checks. Tested candidate:
`095c7c0e1371266b168279206e01f563212f81bd44ae0f6148b2b831e593fb0f`.

Rejudging the twenty captured attempts changed only the five Inkbolt B07
snapshot checks to passes; original reports, workspaces, transcripts and observed
usage/timing remain intact. Baseline B07 still fails the fixed glyph-list order
within one combining-mark cluster, despite matching entries and geometry.
Review that convention before general reliability claims. B06 reinforces the
interaction-cost signal; B07 has no successful-pair cost signal. See
[the results and evidence identities](BENCHMARK_RESULTS.md#b06b07-at-a7e034e-captured-trials-rejudged).

Before B08/B09 trials, retained synthetic captures reproduced false
`SESSION_NOT_FOUND` errors for valid nondefault session directories. Both judges
now use checked session-store discovery for original/current revision reads and
history verification. The existing independent pixel/state/history assertions
remain unchanged. Both original captures now pass after relocation, with every
workspace byte retained and no default session directory created. These are
synthetic judging checks, not additional model evidence.
Focused Windows/WSL checks passed 40/37 Python tests in 34.7/17.7 seconds, with
three explicit Linux skips, unchanged Cargo passes reused and no failed/pending
selected checks. Before/after captures and reports remain under
`w2-mask-retouch-stores-`, tested candidate
`4f8d4fd1a3e4982a02981b49af8236d8695832d8edd01769f1d4779e05107991`.

Five genuine matched pairs per task at `38f0397` subsequently passed both B08/B09
arms on every attempt. Median input-plus-output usage was 327,734/43,824 for
masking (7.48x) and 354,590/43,008 for retouching (8.24x). Every Inkbolt saved
original/history check also passed; seven attempts used nondefault session
directories. All twenty transcripts and command bodies were reviewed without
observed prohibited access, and both source candidates stayed unchanged.
Repeated schema discovery, rejected PNG options, reversed clone transforms and
JSON text-comparison false alarms remain in the evidence. These small raster
fixtures reinforce the interaction-cost signal; they do not establish scale
performance or isolate the cost of Inkbolt's extra history guarantees. See
[the full comparison and identities](BENCHMARK_RESULTS.md#b08b09-at-38f0397-five-matched-pairs).
B10's synthetic capture also reproduced `SESSION_NOT_FOUND` for a valid custom
session directory. Its judge now uses checked retained-store discovery for all
four receipts and final history verification. The unchanged capture passes with
identical workspace bytes and process-memory evidence; judging still uses nine
engine calls. Native tile identities, every TIFF sample, low-bit corruption
controls, proposal/history checks and the 256 MiB memory requirement are
unchanged. This is synthetic regression evidence, not a new model trial.
Focused Windows/WSL verification passed 32/29 Python tests in 96.5/79.1 seconds,
with three explicit Linux skips, unchanged Cargo checks reused and no failed or
pending selected checks. Linux's unavailable commit-memory measurement still
fails the task's budget check as required by the test. Reports and before/after
captures are retained under `w2-photo-session-`, tested candidate
`3a7ad369fedb0526ab981017649cfec8551d609e2e7f5d33da6c18f8b10781ab`.
B13 has no corresponding judge-store assumption; B17/B18's fixed stores belong
to their harness-seeded fault contracts.

B10/B13 now have five genuine matched pairs per task. After two tested judge
corrections, photo repair passes 3/5 with Inkbolt versus 5/5 with the baseline;
screen delivery passes 5/5 in both arms at 7.51x median reported tokens with
Inkbolt. Two photo attempts still fail the explicit default-storage contract.
All twenty saved captures were rejudged without new model execution, with
unchanged workspace files, transcripts, client results, usage and captured memory.
The original failures remain in their original reports. See
[outcomes, limitations and identities](BENCHMARK_RESULTS.md#b10b13-at-7a07f07-five-matched-pairs-with-retained-capture-corrections).

The TIFF judge now retains UNDEFINED byte fields such as embedded profiles in
either byte order. The screen judge admits author-chosen placement of the exact
source note within the engine metadata schema. Native samples, source geometry,
alpha, privacy, collision and history requirements are unchanged. New controls
cover inline/external TIFF bytes, truncation and missing/changed metadata notes.
The focused Windows selection covers 55 Python tests: 30 executed and 25 reused
from identical passes, in 70.5 seconds. Its fresh screen-module pass took 129.0
seconds. Linux executed 52 with three explicit skips in 129.4 seconds. Cargo
checks were reused; no selected checks failed or remained pending in the final
runs. Earlier fixture failures and an unrelated stale no-match Rust filter
remain in the retained reports. Evidence is under `w2-photo-screen-judge-`, with
tested candidate `2d7fa5e3eddaa00f616189c548d16d0c7d0e4d974687861c6fdf232e27c4ebeb`.
This remains focused judge evidence, not a new engine feature or full acceptance.

B11/B12 synthetic trials reproduced false failures when valid resources,
sessions and publication receipts used custom folders. Their judges now locate
exact original image bytes and pinned font/license files within the capture,
bind saved states to the selected session, and locate each publication request
read-only before engine verification. Separate receipt folders are admitted;
missing/ambiguous IDs and damaged resources still fail. B12 also admits the
three prescribed keyed bindings in a different order, preserving corresponding
saved base values and every target, type, dataset and snapshot requirement.
This ordering correction was reproduced before any genuine B12 trials.

All three retained failing synthetic captures pass after rejudging, with identical
workspace files, transcripts, client results and captured memory. B11/B12 still
use seven/eighteen judge engine calls. Moved-capture tests retain no default
resource/session stores; B12 uses three separate receipt folders. Corrupt and
missing images/fonts/licenses, altered receipt checksums and binding targets
remain rejected. Windows executed 56 Python tests with one explicit symlink
creation skip in 62.2 seconds; WSL executed 54 with three platform skips in
39.1 seconds. Unchanged Cargo checks were reused, with no failed or pending
selected checks in the final runs. The verifier's dependency test was updated
to include the new store-folder snapshot test; earlier failures remain retained.
Reports and before/after captures are under `w2-mixed-variants-stores-` and
`w2-variant-binding-order-before-01`, tested candidate
`0d48913ef6dd4f800b1bcd3f8648ad0a6ee84894d444eca4bbb38f053f707f8b`.
That synthetic preparation awards no model or engine credit.

B11/B12 now have five genuine matched pairs each. Mixed composition passes 3/5
with Inkbolt versus 5/5 with the baseline: two Inkbolt attempts added an unrequested
image lock. Layout variants pass 5/5 in both arms at 9.17x median reported tokens
with Inkbolt. Three original layout judge crashes were reproduced with a
synthetic author using native `add` operations. Judging now finds item roles by
type and parent, preserving exact item fields and sibling order while accepting
different cross-parent interleaving. The exact artboard names from the prompt
table may be display labels or fixed IDs with default empty labels; other labels
remain rejected. Native history must still match each delivered snapshot exactly.

The new regression covers an imported capture with custom resource/session and
receipt roots, different binding order, native item insertion and table labels.
Negative cases retain changed sibling/root order, parents, properties and labels.
Windows executed 56 Python tests in 80.3 seconds; Linux executed 53 with three
explicit platform skips in 53.1 seconds. Cargo checks were reused, with no failed
or pending selected checks. Reports are under `w2-variant-order-`, tested candidate
`04f6923675698f2f3451127b137c259988fef43962209db01cf5adeb52e05f46`.
All twenty genuine captures were rejudged with unchanged workspaces, transcripts,
client results, usage and captured memory. No model was rerun. B11 lock failures
and all baseline outcomes are unchanged; only the three B12 judge errors become
passes. See [results and review limits](BENCHMARK_RESULTS.md#b11b12-at-30c4ebd-mixed-composition-and-layout-variants).

B14/B15 preparation reproduced false failures for valid custom session stores
and a custom B14 publication store. Their judges now locate unique captured
stores by the delivered IDs before native receipt/history verification. Both
original synthetic captures pass rejudging with unchanged files, transcripts,
client results and usage; the judges still use nine/ten engine calls. B15's
explicit broken/repaired resource folders, original absolute binding data and
reviewed resource-only change remain required. Tests reject missing, duplicate
and corrupt stores, altered print artifacts, invalid reviews and historical
resource changes. Windows executed 45 tests with one symlink skip in 39.5 seconds;
WSL executed 43 with three platform skips in 31.2 seconds. Unchanged Cargo checks
were reused; no selected checks failed or remained pending. Evidence is under
`w2-print-resources-store-`, tested candidate
`a144f4c829b0b3c4dbf801fc9974551a3e7f73e5468e1912c8b4e85d59edb9e5`.
This is synthetic judge preparation, without new model or engine credit.

B14/B15 now have five genuine matched attempts per arm at `7d31cf9`. Rejudging
all twenty unchanged captures after tested corrections accepts caller-chosen
swatch labels, contained output subfolders, extra loss disclosures and successful
CLI review envelopes. Exact ink/profile/artwork and historical bindings remain
required. B15 passes 5/5 in both arms at 4.83x median tokens. B14's Inkbolt
artifacts pass 5/5, but two wrong receipt selections still fail the complete
workflow. The original baseline PDFs hit unsupported `ri` and equivalent PDF
encodings. Public-specification review and tested parser corrections now admit
four; the remaining delivery omits the required explicit black-point-compensation
setting. See [the retained outcomes](BENCHMARK_RESULTS.md#b14b15-at-7d31cf9-print-delivery-and-resource-repair).

The correction executed 57 Windows tests with one symlink skip in 56.5 seconds
and 55 WSL tests with three platform skips in 47.6 seconds. Unchanged Cargo
checks were reused; no selected checks failed or remained pending. Reports and
the raw tested-input map are under `w2-print-label-folder-`, candidate
`3e8a23d1dadbe3b1e77f128afd83516fda6e7a0055bd89a48efb259d6daacb6d`.
The original workspaces, reports, transcripts, client results, observations and
captured memory remain unchanged. No model was rerun and no engine credit added.

The PDF correction adds scoped rendering intent, cumulative graphics state,
indirect page/spot color-space references, equivalent rectangle traversals and
page-group flags for this exact opaque, disjoint fixture. Altered profiles,
crossed/changed geometry, overprint, effects and missing/changed conversion
controls still fail. Direct consumers of the shared test reader passed on both
platforms. Final focused runs executed 42 Windows tests with one symlink skip
in 59.3 seconds and 40 WSL tests with three platform skips in 42.5 seconds;
five unchanged consumer modules and Cargo checks reused identical passes.
No selected check failed or remained pending. Reports are under
`w2-print-pdf-grammar-`, final tested candidate
`94a18f910c738e3f2ff1f3949ecf081046a459506ec137a432eb6a3bb4a95024`.
All twenty original captures were rejudged again without changing workspace,
transcript, client-result, usage or memory evidence; intermediate reports remain.

B16's pre-trial audit reproduced four synthetic false failures: caller-selected
session and publication folders, the successful CLI review envelope, and a
different valid PNG encoding from the baseline judge's fresh renderer. Checked
store lookup, strict envelope handling and exact decoded-pixel comparisons now
rejudge all four unchanged captures successfully. Original captured files and
workspace hashes are unchanged; evidence is under `w2-repair-contract-`.
The default font store remains required by the prompt. Missing, ambiguous or
corrupt stores, damaged font/license bytes, invalid reviews, changed publication
bindings, wrong delivery hashes and altered pixels still fail. All original
check IDs/classes remain; native publication binding is checked with history,
separately from artifact delivery.

Focused Windows checks executed 46 tests with one symlink skip in 41.4 seconds;
WSL executed 44 with three platform skips in 19.1 seconds. Both reused unchanged
Cargo checks, with no selected failures or pending checks and unchanged inputs.
Reports and the raw tested-input map use the same external evidence prefix;
tested fingerprint `7a6e5b7f40cfdb7e130f3cb9db2c457c3891545401e739a28ce191baf07e5564`.
This is judge preparation, not new model evidence or engine feature credit.

The first genuine B16 batch at `3c52ce4` retained five attempts per arm. Four
Inkbolt deliveries omitted the repaired revision; the fifth exposed an extra
raw-serialization restriction despite reopening to the exact expected document.
The judge now compares normalized snapshots, keeping wrong revisions and all
collateral changes as failures. Rejudging all ten unchanged captures yields 1/5
complete Inkbolt workflows and 0/5 baseline workflows. Baseline recipe types
were not fully specified in prompt version 1, so the preliminary batch does not
establish comparative reliability. Version 2 explicitly supplies those types
and native snapshot revisions. See [results and provenance](BENCHMARK_RESULTS.md#b16-at-3c52ce4-preliminary-text-repair-trials).

The default-field correction executed 37 Windows tests in 33.5 seconds and
34 WSL tests with three platform skips in 17.8 seconds, fingerprint
`b145613796e741388e7ca9599db61ae8d67957247010e5d5bb8400e2ec2aa2a5`.
The clarified version-2 task then passed all 11 repair tests on each platform,
in 36.0/16.6 seconds, fingerprint
`42c67a9be4f9ceaf7654843253c9fd8f96e1811d9ca7b9ead35cf13990989910`.
All selected checks passed or reused identical Cargo passes, with no pending
checks and unchanged inputs. Reports/raw tested-input maps are under
`w2-repair-defaults-` and `w2-repair-prompt-v2-`. Every original failure remains.
The fresh version-2 batch at `a048690` passed 5/5 in both arms; Inkbolt's full
history checks also passed. Median token use was 584,833 versus 130,703 (4.47x),
and client time was 112.9 versus 82.4 seconds. Its unchanged candidate,
487 retained files and complete direct-trace review are recorded separately in
[the results](BENCHMARK_RESULTS.md#b16-at-a048690-explicit-version-2-repair-contract).
No engine credit changed.

B17/B18 pre-trial checks retained three synthetic false failures: omitted
default resolution in each restored document and B18's successful CLI review
envelope. The judges now compare reopened document semantics and accept that
strict envelope. All three unchanged captures rejudge successfully; explicit
revision 2, exact requests, every source control, receipts and setup hashes
remain required. Negatives cover missing/stale revisions, changed resolution,
malformed/error/nonboolean/extra-field envelopes, altered proposals, duplicate
commits and unrelated artwork. Malformed reviews no longer suppress independent
pixel/history checks. Default session stores remain part of the supplied setup.

Focused Windows checks executed 42 tests in 32.7 seconds; WSL executed 39 tests
with three platform skips in 19.2 seconds. Both reused unchanged Cargo passes,
with no failed/pending checks and unchanged inputs. Evidence, capture integrity
and raw tested-input maps are under `w2-retry-conflict-contract-`, tested
fingerprint `f17fe2bed1e4e25d82dd2f7314a3962f2a736fa245e1c432ed0a8e29135a31f1`.
These are synthetic harness corrections, not model trials or engine credit.

Five genuine attempts each at `cae530a` passed B17/B18 artifact checks 5/5.
Two B17 attempts saved CLI envelopes where the prompt requires compact results,
leaving its complete workflow at 3/5; B18 passed 5/5. Both failures remain, and
neither recovery task has an applicable no-engine baseline. Median tokens were
269,176/249,608 and client times 94.6/125.0 seconds. All direct traces were
reviewed and 746 retained files hashed; the external wrapper's incorrect
expectation of a comparable baseline is recorded with the completed reports.
See [results and provenance](BENCHMARK_RESULTS.md#b17b18-at-cae530a-receipt-and-concurrent-edit-recovery).
This adds model evidence without new engine credit or full W2 acceptance.

B19 pre-trial checks reproduced three synthetic false failures: chosen session
and image-resource folders, and an omitted optional resolution field. The judge
now locates the unique retained session and exact original image samples, and
compares reopened source semantics. All three unchanged captures rejudge
successfully; all 486 original evidence files and workspace contents remain
unchanged. Evidence is under `w2-job-recovery-contract-`, with final rejudging in
`after-02`; the unsuccessful first correction remains retained. Prompt version 3
explicitly fixes the harness-controlled job queue at `.inkbolt/jobs`. It leaves
session/image folders selectable. Process ownership, twelve judge calls, exact
revisions/resources, publication identity and all original checks remain required.

Focused Windows checks executed 42 tests with one symlink skip in 124.7 seconds;
WSL executed 28 with 15 explicit skips in 19.8 seconds. Tested fingerprint:
`fc1452ec2037b9dd5e82e349250b8ad7c54f8144fc1005df59e7d059819b717e`.
A final negative-test state reset reran the judge module: four Windows tests in
103.7 seconds, and one WSL fixture test with three job skips in 6.1 seconds,
fingerprint `d1f2f045f6fe6363b5eec51d7b4dd7b92676e187f8e8e08fa96c5c9b3020c218`.
Reports and raw tested-input maps are under `w2-job-recovery-contract-` and
`w2-job-recovery-judge-`. All selected checks passed or reused unchanged Cargo
passes, with unchanged inputs and no pending checks. Missing/ambiguous/corrupt
stores, changed artwork/resolution/revisions and changed resource bindings still
fail. Synthetic preparation earns no model credit; Linux jobs remain unsupported.

B19's first five genuine attempts at `2cf3869` stopped at a bridge-folder write
denial before any engine process started. All failures and 65 captured files are
retained in [the results](BENCHMARK_RESULTS.md#b19-at-2cf3869-retained-evaluation-setup-failures).
The Codex adapter now grants only the existing, unlinked trial control-channel
folder. Tests reject parent/evidence/workspace grants, other tasks, malformed or
mixed bridge configuration, and linked channels. Ordinary tasks gain no additional
writable folder; B20's baseline still cannot call Inkbolt. Windows executed 40
tests with one symlink skip in 33.7 seconds; WSL executed 38 with three platform
skips in 21.8 seconds. Reports and raw tested-input maps use `w2-bridge-sandbox-`,
fingerprint `5374481b01065399ade94bfcddd9ad82417b34a1cd66182ddbfcd818da7efb9e`.
All selected checks passed or reused unchanged Cargo passes, with unchanged
inputs and no pending checks. Subsequent genuine pilot evidence follows.

The genuine pilot at `5079c5a` confirmed bridge access, but retained a malformed
message failure and exposed an independent missing final checkpoint for valid
`session.publish`. Its pixel, cancellation, interruption, pinning and history
checks passed; the full workflow did not. The failure and all 254 files remain
in [the results](BENCHMARK_RESULTS.md#b19-at-5079c5a-bridge-pilot-and-publication-observation-gap).
A separate synthetic reproduction is retained under `w2-job-session-publish-before-01`.
The controller now records either publish command, with no invented observations
for old captures. Reserved nested command/step fields receive an explicit
protocol error and still fail trials even when the client continues successfully.
Focused checks executed 31 Windows tests in 103.0 seconds and 25 WSL tests with
six platform skips in 19.3 seconds. Reports/raw tested-input maps are under
`w2-job-session-publish-`, fingerprint
`5f66a2d0bdbf67df8bbf549414704101d7feeec38b83cf27dcc55583f813bb9a`.
All selected checks passed or reused unchanged Cargo passes, with unchanged
inputs and no pending checks. The remaining five-attempt run stays separate from
the earlier failed setup and pilot.

Five B19 attempts at `30ecf5b` finished with 0/5 complete workflows. The first four
passed all nine independent artifact/recovery checks, but retained malformed
bridge-message failures. The fifth never admitted cancellation after repeatedly
adding an unsupported control field; only source preservation was scored.
All 224 observed engine processes exited without observer errors. The original
1,305 captured files, direct trace/helper review and missing accepted metrics are
retained in [the results](BENCHMARK_RESULTS.md#b19-at-30ecf5b-five-recovery-attempts-with-protocol-failures).
These failed attempts earn no complete model-trial or engine-checkpoint credit.

B20 pre-trial probes reproduced false failures for a chosen session folder,
an exact successful review envelope and omitted optional source defaults.
All three unchanged synthetic captures now rejudge successfully, preserving all
960 original evidence files, source workspaces and measured solve traffic. The
judge reopens before/after/historical sources and requires explicit revisions;
typed handoff bytes, consumer responses and history remain exact. Judge queries
increase from nine to eleven, with solve/consumer counts and all checks unchanged.
Capture imports ran before the separate bridge identity change; no identity
check was waived. The bridge now explicitly refuses reserved nested fields.

Focused checks executed 38 Windows tests in 74.0 seconds and 28 WSL tests with
ten explicit platform/tool skips in 24.8 seconds. Missing/ambiguous/corrupt
stores, changed revisions/artwork/timing/resolution, malformed reviews and
invalid protocol messages remain failures. All selected checks passed, with
three unchanged Cargo passes reused only on WSL, unchanged inputs and no pending
checks. Reports, raw tested-input identities and synthetic before/after evidence
use the `w2-handoff-contract-` prefix. Tested fingerprint:
`00ffc82411e869b599a5f55f03a1d33002a96ae871d893c2a8fa775f70e69815`.
These are harness corrections and focused checks, not full milestone acceptance.

Five genuine attempts per arm at `fe7786d` completed B20's first matched batch.
The native workflow passed 0/5: one attempt violated an undisclosed consumer
command allowlist; four had accepted driver evidence but failed the required
session-ID prerequisite. All five used a different session ID from the prompt.
Only source preservation was independently scored for native attempts; fifteen
checks per attempt remain missing, so native artifact quality is unjudged.
The baseline passed 5/5, including all seven task artifact checks and source
preservation; its eight engine checks are not applicable. All direct completed
commands and retained helpers were reviewed, and all 3,019 evidence files are
hashed. See [the B20 results](BENCHMARK_RESULTS.md#b20-at-fe7786d-linked-graphic-delivery-prerequisite-failures)
for exact identities, accepted metric scope and retained failures.

The versioned pilots at `1d5b960` use B19 prompt 4 and B20 prompt 3. B19 now states the
existing message/control grammar, shows a valid saved-revision cancellation
request and explains where resource bindings live. B20 publishes the existing
consumer-command allowlist and distinguishes document ID, session ID, folder,
item ID and default display name; it also clarifies the required error object.
These address observed protocol/prerequisite failures without changing any
controller, judge, acceptance criterion or previous score. One genuine B19
native pilot and one B20 pilot per arm completed with the same external settings.
Their protocol gates passed; a successful pilot alone does not establish
five-trial or full-suite acceptance.

The prompt update passed 22 Windows lifecycle/bridge/driver tests in 67.4 seconds,
with real consumer/baseline tool configurations enabled, fresh Cargo checks and
no reused passes, skips or pending checks. WSL passed 16 tests in 11.6 seconds;
six Windows-process tests were explicitly skipped and three unchanged Cargo
passes were reused. Both reports retain unchanged inputs and fingerprint
`4967b90df1520a504e5b38683129960b55ce79e691a696e6d240ab60d21caf93`,
under `w2-bridge-guidance-`. Only status documentation changes after those checks;
the tested prompt hashes are retained separately.

The B19 pilot fails four exact-record checks after manually rounded process
creation identifiers in `attempts.json`; actual bridge output retains exact
integers. Its artifact/source checks pass. B20 passes both arms after correcting
two judge assumptions: current-head reads must bind to observed revision 2 before
undo, and additional delivery diagnostics are allowed only with unchanged bytes.
All required files, history, receipts, pixels and timing checks remain enforced.
Imports preserve the original captures and solve metrics; no client reran.
Regression/lifecycle/verifier checks passed in 66.1s on Windows (40 Python tests)
and 18.3s on WSL (30 executed, ten explicit Windows-process skips), with fresh
Cargo checks and no failed/pending checks or reused passes. Candidate fingerprint:
`e35f8374bc7040c22a69e77b14ecc0753413a94f2d29622b223b0d8e6223fa92`.
See [the pilot evidence](BENCHMARK_RESULTS.md#b19b20-at-1d5b960-guidance-pilots-and-observation-corrections).

B19 prompt 5 now requires direct, programmatic preservation of the returned
objects using an integer-aware parser. The job guide explains the same existing
64-bit process identity contract. This changes guidance only: the bridge, engine,
record types and exact identity checks stay unchanged. Its separate pilot at
`f61d952` passes all nine independent checks with programmatically retained
responses, but fails the protocol gate after a schema request puts `command`
inside `arguments`. Later repair does not erase that failure; no larger recovery
batch followed. Earlier captures remain unchanged.
The guidance update passed sixteen Windows recovery/driver tests in 76.7s,
including fresh format/build/Clippy, with no skips, failures or pending checks.
Report `w2-recovery-record-guidance-windows-01.json` binds fingerprint
`e8844af766df07f82572a73dde6e3eed90d8504da61b9064763de4289fad27e5`;
prompt 5 hashes to `7752a6b12ca4748875418f211a375c42b123b8f222907b1a915712928ef64892`.
The engine and Linux backend are unchanged from the preceding platform checks.

B20 prompt 3 now has a separate five-pair follow-up at `f61d952`. Original full
workflow scores were 1/5 native and 5/5 baseline. Rejudging all ten unchanged
captures after removing an unstated stale-operation equality requirement gives
3/5 native and 5/5 baseline, with eight shared artifact/source checks and eight
native-only engine checks. The stale request still must target the same saved
project at revision 1 and produce an actual conflict; undo, exact retry, receipts
and history remain enforced. Attempts 4 and 5 still fail exact source-base
preservation. No observed delivery file changed; their delivery-inventory failure
cascades from the earlier source assertion. Native median tokens/time were
1,065,545 / 209.8s versus 280,910 / 115.9s for the baseline. No client reran and
all 4,171 original evidence files and solve metrics remain unchanged.

Focused regression/lifecycle/verifier checks passed in 54.7s on Windows
(39 executed, three optional baseline skips) and 18.3s on WSL (31 executed,
eleven explicit Windows-process skips), seven fresh stages each. A separate
53.2s Windows run enabled both real tool configurations and passed all six
external lifecycle tests without skips, including the three baseline checks.
No failed/pending checks or reused passes; verification inputs:
`f2f7d412de0c52a035f48c6b70dabade35af153d5dd3dfc0240b930733d24014`.
See [the follow-up evidence](BENCHMARK_RESULTS.md#b19b20-at-f61d952-recovery-pilot-and-five-pair-handoff-follow-up)
for original/rejudged identities, metric boundaries and trace-review limitations.

Successful B19 recovery trials, reliable B20 source preservation, further smaller-model
trials, arbitrary legacy transcript adapters, B10 Linux commit-memory evidence
and full W2 acceptance remain open. W2 evidence continues to sequence substantial
work using the plan's decision rule; W3a.3 input admission is next, without
claiming that CSS caused these trial failures. No engine checkpoint receives credit.

### Executable nested schema discovery: focused checks and mixed model follow-up

A read-only inventory of 95 completed B01-B19 attempts found 17 distinct JSON
error signatures. Failed selectors appeared 48 times across 15 task IDs,
followed by absolute-path errors (22) and generic request errors (17). These are
visible output occurrences, not authenticated call frequencies: repeated reads,
expected refusals and missing/truncated output prevent that interpretation.

The B03/B16 traces specifically motivate the next W5 increment. A selected
`Action` outline lists `edit`, but the original root-level selector cannot follow
that instruction under `session.apply`. Lowercase property names such as
`document` also fail when the reachable definition is `Document`.

The change adds bounded nested selectors, executable variant selectors
and working recovery queries in errors. It preserves exact existing selectors,
full schemas, the catalog budget and execution validation. Expected improvement:
fewer failed discovery calls and less full-schema output for the same edits.
Remeasure B03/B16 with the same external client configuration and retained
failures. If navigation errors/calls/tokens do not improve without correctness
loss, stop broadening this approach and reassess the trace evidence. Request
field diagnostics, path guidance, B19 recovery and B20 prompt clarity remain
separate follow-ups.

Fresh focused checks passed all eight selected stages on Windows in 123.3 seconds
and WSL in 74.1 seconds: formatting, locked build, all-target Clippy, the guard,
three Rust tests and 23 Python tests across discovery, workspace and MCP. Neither
platform reused passes or had failed, skipped or pending selected tests. Other
checks remain outside this focused scope. Both reports bind to input fingerprint
`750c3b20963b2598de7e51c2556be108676d3144c611653d6bf6381df4569bf0`.

Runtime probes reproduce the old `Action/edit` refusal and verify the new working
route and error suggestions; the direct transform and full operation schemas
remain exactly equal. The measured compact catalog has 22 tools on three pages,
71,593 JSON bytes (71,809 wire bytes), below 96 KiB. The nested transform response
is 693 bytes and its schema equals the 667-byte standalone response's schema.
Reports and probes use the external `w5-discovery-` prefix. Final documentation
updates follow those checks; implementation/test inputs stayed unchanged.
Five new attempts per task and arm at `d34851e` all passed B03/B16. Compared with
the earlier unchanged-prompt native batches, B03 median tokens fell from 349,212
to 300,182 and client time from 128.9 to 111.2 seconds. B16 tokens fell from
584,833 to 574,154, but time rose from 112.9 to 160.9 seconds. The new baseline
still used fewer tokens: native/baseline ratios are 4.62x and 5.20x. These separate
sequential samples do not establish causation, statistical equivalence or billing
cost. Full engine/model call counts and several required metrics remain unknown.

The recorded stop condition therefore holds broad discovery expansion. Keep the
working selector contract, preserve the mixed evidence, and address the separately
observed request/reference problems. All twenty traces and final retained helpers
were reviewed; 715 raw evidence files were hashed and earlier per-trial inventories
rechecked unchanged. See [the follow-up results](BENCHMARK_RESULTS.md#b03b16-at-d34851e-nested-discovery-follow-up).
Full W2/W5, sister-project comparison and engine checkpoint acceptance remain open.

## W3a.1-2: complete within the declared SVG subset

Elliptical path arcs and rounded rectangles now import as ordinary editable
cubics with source-element approximation receipts. Arc handling covers relative
coordinates, rotation, all flag combinations, adjacent flag syntax, proportional
radius correction, zero-radius lines and coincident endpoints. Rectangle radii
default independently, clamp to their respective half-extents and support
unequal elliptical corners. Clip and mask sources use the same conversion.
See [SVG import](SVG_IMPORT.md) for the local error bound, floating-point limits,
losses and remaining unsupported input.

Original analytic ellipse fixtures check each curve against known geometry,
sweep direction and the declared error bound. Checks also cover exact interior
pixels, overflow refusal, SVG/snapshot persistence, MCP, file preservation,
session edits and undo. The first focused 60-test pass took 26.2 seconds on
Windows (reusing its unchanged Cargo checks) and 69.2 seconds on Linux (including
fresh build/Clippy). Related Windows text, coordinate and large-vector
regressions passed in 41.0 seconds. Near-zero and almost-full-circle cases also
pass independent geometry checks. The other W3a items remain open; W3b status
is recorded below. The engine registry is unchanged.

Fresh combined W3a.1-2/W5.1 acceptance on 12 October passed all **218 stages**
on each platform, with no failed, pending or reused checks and unchanged inputs.
Both reports bind candidate fingerprint
`4194d5e095e6e9372d4ed8b2cbb883ea69a598e4375231a993ff0d92762bd088`.

| Platform | Rust tests | Python tests executed | Explicit skips | Duration |
| --- | ---: | ---: | ---: | ---: |
| Windows | 208 | 2,308 | 1 | 1489.2 s |
| Linux / WSL | 177 | 2,275 | 34 | 829.3 s |

These full correctness runs overlapped on the shared host with two workers each;
their durations are not isolated performance measurements. Focused feedback
remains bounded by the ordinary 180-second quick mode. Subsequent changes in this
milestone are documentation of these results only.

## W3a.3: complete within the embedded-style contract

The shared SVG importer now resolves embedded type/class/ID compounds, universal
selectors and selector lists with specificity, source order and inline precedence.
All style blocks are collected before artwork. Definitions, text, masks and
`add_svg` use the same cascade, preserving mask shorthand resets and actual-parent
relative font sizes. Unsupported selectors, declarations and CSS-wide keywords
fail with source locations. Numeric lexemes retain binary64 precision. New rule,
declaration and matching budgets are enforced and exposed; external stylesheets,
at-rules, escapes and `!important` remain unsupported.

This is the next input-admission slice under W2's baseline-cost decision rule;
CSS is not claimed as the cause of the recorded model failures. The acceptance
target is fewer refused ordinary class-styled graphics without changing geometry,
pixels, history or unsupported-semantics policy. Stop at the declared selector
subset; broader CSS, `use`/`symbol` and nested viewports remain separate work.

Focused Windows/WSL checks passed in 101.6/104.1 seconds: 110/107 Python tests,
zero/three explicit skips, and one Rust cancellation test, with 13 fresh stages
each. Font/token edge cases subsequently passed on both platforms. The first
full acceptance run was stopped after a probe found that fragment error offsets
included the generated SVG wrapper. It is not accepted evidence. Located insertion
errors now refer to the original fragment, including Unicode and newline cases;
errors on the generated root have explicit synthetic origin and null positions.

The correction passed 19 Python tests plus the Rust cancellation check on Windows
in 70.9s, with seven fresh stages. The final generated-root budget test passed with
the full ten-test CSS module in 13.4s, reusing three unchanged Cargo stages. Linux
passed 20 Python tests plus the Rust check in 43.2s, with seven fresh stages.
These final checks have no skips, failures or pending checks. Final focused inputs:
`badc87be9130ab39dde5592d478a94cde80b7ef5ebd6559749e39845464599fc`.
Separate locked, offline, all-target checks also passed on the corrected sources
with Rust 1.89.0 on Windows and Linux in 8.5/6.9s, including the pinned CSS parser.
Fresh full acceptance then passed consecutively on Windows and Linux with the
same frozen candidate. Every stage ran fresh, with no failures, pending checks
or outside-scope checks, and both reports confirm unchanged inputs.

| Platform | Fresh stages | Rust tests | Python tests executed | Explicit skips | Duration |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows | 244 | 216 | 2,543 | 4 | 760.0 s |
| Linux / WSL | 244 | 182 | 2,496 | 51 | 435.6 s |

Windows skips were three unavailable symlink fixtures and one Unix-only path
case. Linux skips were 35 job-dependent cases, eight Windows memory/handle/host
cases and eight consumer-tree checks requiring Windows accounting. No CSS test
was skipped. These are correctness runs, not isolated latency or memory results.
The shared input fingerprint is
`91828215f8c411c43c53b7a1b10dc1812bd5a0e6f1efe44988a58db563c2b9a9`.
Evidence lives under `w3a-css-`; acceptance audit 02 retains all 488 stage logs
and verifies the 863-file frozen source inventory. Its SHA-256 is
`3105906c75f81bb18a6e2e97da15c0b539cce35c3da9eeced7f3cdf7cd85b233`.
This completes W3a.3 only. The engine registry remains 163/167; reusable shapes,
nested viewports and the other SVG admission items remain open.

Integration with the incoming packaging commit `9ea83ab` preserved the tested
engine code; Git normalized line endings in seven files. The exact frozen source
archive and comparison are retained with the evidence. Subsequent focused checks
passed 11 fresh stages on each platform: 81 Python tests plus one Rust test on
Windows in 63.6s, and 78 Python tests plus one Rust test with three Windows-only
skips on Linux in 35.5s. These cover the updated guard and SVG integration, not a
new full-suite claim for the combined distribution changes. The packaging suite
passed 18 tests with one non-Windows-only skip when run alone; its earlier run
alongside compilation timed out and remains retained as a failure. No deadline
changed. A separate bundle containing the current development executable passed
standalone discovery of all 22 core tools and document creation. This confirms
integration, not release-build or complete distribution acceptance.

## W3a.4: complete within the reusable SVG contract

**Complete, 15 October 2026, at `3eaf500`.** Local `use` admits supported shapes,
groups, text, symbols and local references within [the declared contract](SVG_IMPORT.md).
Source declarations use placement inheritance. A memoized graph rejects cycles
and excessive reference depth without expanding unused copies; existing item,
hierarchy, geometry and resource limits bound materialization. Symbols keep
viewport placement/clipping separate from viewBox and appearance. Percentage
paints, masks, placements and text use the correct local viewport.

Compatible resolved occurrences become native components with geometry-preserving
placement overrides. Visible originals and overlapping group/child targets share
editable sources too. Other contexts form declared variants; native budgets and
raster destinations retain groups with explicit reasons. Insertion can retry once
from the untouched candidate when components exceed the destination budget.
Source validation runs first. Stored editing identities and original offsets
survive receipt remapping, insertion, retry and history operations.

Cloned gradient, clip and mask definitions receive per-use resource identities.
Local references search enclosing reuse trees before the original document;
inherited URLs keep their declaration context. Delayed masks restore their scope,
occurrence path, pinned font styles and viewport coordinates. The unchanged
64-definition ceiling includes clones. Mask contexts remain independently editable,
and loss of editing linkage across native variants is explicitly reported.

The requirement review maps implementation and independent fixtures to local
reference admission, placement/style correctness, shared editing and fallback,
explicit refusal/limits, resource scopes, atomic insertion/history, capability
reporting and full platform verification. The four dedicated fixture modules
check exact geometry/pixels, fractional text/mask coverage, resized symbols,
overlapping and nested references, source preservation, dependency locks,
resource-budget fallback, malformed/cyclic input, insertion receipts and undo/retry.
Existing SVG, native component, transfer and interface regressions also ran.

Fresh full acceptance ran consecutively on the shared host, with every stage
fresh, no failures, pending/outside-scope checks, reuse or source changes:

| Platform | Stages | Rust tests | Python executed | Explicit skips | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows | 248 | 216 | 2,590 | 12 | 708.7 |
| Linux / WSL | 248 | 182 | 2,551 | 51 | 470.4 |

Windows skips comprise eight separately configured real-tool handoff checks,
three unavailable symlink fixtures and one Unix-only path fixture. Linux skips
retain Windows-only jobs/process accounting and host-measurement exclusions.
No dedicated reusable-SVG test was skipped on either platform. These runs do not
establish new macOS verification, Unix job support or the separate handoff/model gates.

Both reports confirm source fingerprint
`a1d6a3c568ebdac3baabdecc07b3867ad2d750e61d2a8ef82f9f7c03fbcf1374`.
The external `w3a-reuse-acceptance-01` bundle retains both reports, all 496 stage
logs, the eight-part requirement review, an 883-file inventory and frozen source
archive. Audit SHA-256:
`12378ecf48cebe7bbac73bef6081a64fb0641b1f204e4ad1437675b53286236d`.
The preceding focused scope runs took 47.4/57.6 seconds on Windows/Linux; their
separate evidence remains in `w3a-scopes-focused-01`. Earlier component, symbol
and local-reference audits remain retained as well. Full acceptance is a
milestone gate; routine changes keep the 180-second feedback budget.

W3a.6-8 remain open: images, richer text spans and opt-in omission reports.
Nested SVG verification follows below. No additional engine checkpoint or
whole-goal credit is awarded; the unchanged registry remains 163/167.

## W3a.5: complete within the nested viewport contract

Nested SVG viewports retain separate outer placement/clipping and inner
viewBox/appearance coordinates. Absolute, percentage and automatic dimensions,
all nine aspect alignments, meet/slice/none and declared overflow choices use the
[SVG import contract](SVG_IMPORT.md). Nested text, gradients, masks and reuse
resolve against the nearest user viewport; siblings recover the enclosing basis.
Referenced SVGs retain compatible shared geometry and independent viewport clips.
Empty viewports preserve occurrence metadata, validate source templates and do
not hide siblings. Limits and unsupported semantic boundaries remain explicit.

The six-part requirement review covers placement, aspect mapping, clipping and
effects, reuse/editing, explicit boundaries, and source/transaction preservation.
Sixteen new original tests check independent rectangles at two scales, pinned
font coverage, source-file identity, reusable geometry edits, masks, hierarchy
limits, version conflicts and atomic insertion through MCP proposals/retry/undo.
The existing SVG, component, resource, session and interface regressions also ran.

Fresh full acceptance at `c9a5532` ran consecutively on the shared host, with
all stages fresh, matching unchanged inputs, and no failures, pending checks,
reuse or outside-scope checks:

| Platform | Stages | Rust tests | Python executed | Explicit skips | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows | 249 | 216 | 2,606 | 12 | 835.4 |
| Linux / WSL | 249 | 182 | 2,567 | 51 | 453.0 |

Windows skips comprise eight separately configured real-tool handoff checks,
three unavailable symlink fixtures and one Unix-only path fixture. Linux skips
retain the Windows job, process-accounting and host-measurement boundaries,
including the separately configured handoff checks. No dedicated nested-SVG test
was skipped. These runs do not establish new macOS verification, Unix job support
or the separate handoff/model gates.

Both reports bind source fingerprint
`e40e58f80708f7826081f8cf996d38782c6d13352683610788d8fa7fff216772`.
The external `w3a-viewports-acceptance-01` bundle retains both reports, all 498
stage logs, the six-part requirement review, an 884-file inventory and a frozen
candidate archive. Audit SHA-256:
`698f68325b36735ff65d99785fe3d794fac5494f36a1bc7154b640ed1ecd8905`.
Final documentation updates follow this frozen candidate; engine and fixture
inputs remain unchanged.

The preceding focused checks took **41.2/51.3 seconds** on Windows/Linux, retained
under `w3a-viewports-focused-01`. Windows reused six matching passes; Linux ran
all selected stages fresh. The initial Windows fixture failures remain retained,
followed by their correction and the successful focused/full runs. Routine
feedback keeps the 180-second budget; fresh full acceptance is a milestone gate.
W3a.6-8 and the overall goal remain open. No additional engine checkpoint is
awarded; the unchanged registry remains 163/167.

## W3a.6: complete within the image contract

PNG/JPEG data URIs and relative local files under an explicit image source root
become editable placed images. The [contract](SVG_IMPORT.md#placed-images) covers
intrinsic and percentage sizing, aspect mapping, clipping, positioning-rectangle
effects, inherited sampling hints and reusable components. Encoded resources
retain original source bytes and normalized identity without writing an asset
store. The existing snapshot-byte, asset and decoded-pixel ceilings remain in
force; the raw-inline allowance is unchanged. This is not W4 scale acceptance.

Sixteen original image tests cover independent placement pixels at two scales,
PNG/SVG round trips, synthetic JPEG, profile conversion, source/pixel identities,
resource limits, explicit root resolution and symlinks, shared edits, mapped IDs,
dry runs, changed-source proposal rejection, source-free retries and undo/redo.
A failed batch leaves session state and workspace files unchanged. Existing
image, color, SVG, discovery, workspace and verifier regressions also ran.

The six-part requirement review caught a percentage that was finite when parsed
but overflowed against the actual viewport. A zero-size image could then return
a null size receipt. Coordinates now fail with `SVG_INVALID` after nonfinite
resolution, including hidden and nonpainting content. Four regression subcases
cover width, height and position overflow. The first Windows full run was
deliberately stopped before this correction; its retained logs are not acceptance.

Fresh full acceptance then ran consecutively on Windows and Linux. Every stage
ran fresh on matching unchanged inputs, with no failures, pending checks, reuse
or outside-scope checks:

| Platform | Stages | Rust tests | Python executed | Explicit skips | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows | 250 | 216 | 2,621 | 13 | 730.4 |
| Linux / WSL | 250 | 182 | 2,583 | 51 | 467.2 |

Windows skips comprise eight separately configured real-tool handoff checks,
four unavailable symlink fixtures and one Unix-only path fixture. Linux retains
the Windows job, process-accounting, host-measurement and configured handoff
boundaries. All sixteen image tests ran on Linux; Windows skipped only the image
symlink fixture. No new macOS image verification, Unix-job support, scale or
real-model claim follows from these runs.

Both full reports bind source fingerprint
`eeda061b0204db7ab949fc2becfea66456a3cc60aa2db600762a9a8336100c20`:
engine base `502b64c` plus the coordinate fix and its regression cases. The
external `w3a-images-acceptance-01` bundle retains the full and focused reports,
all 500 full-stage and 14 repair-stage logs, the completed six-part review,
an 886-file inventory, a frozen source archive and the interruption record.
Audit SHA-256:
`b00fd042ea9c1d0ef96017d11d36f565962234f3b6252a6a5bce1c4b7a514c05`.
Final documentation updates follow this frozen candidate; engine and test
inputs remain unchanged.

The repair's selected image, viewport and insertion checks took **44.1/29.1
seconds** on Windows/Linux: seven fresh stages each, with 41/42 Python tests
executed and one/zero skips. Earlier focused implementation checks took
31.3/81.0 seconds; their reports and source archive remain in
`w3a-images-focused-01`, audit
`f05f4cd86f6f14eaa99b88d052706595c592e4ef73e09311610e5263c532a7c3`.
Routine feedback retains the 180-second budget. Span acceptance follows below;
W3a.8 opt-in omission reports are next. No engine checkpoint is added; the registry
remains 163/167 and the overall goal remains open.

## W3a.7: complete within the span-range contract

**Complete within the declared native-range contract.** Nested `tspan` retains
editable font/fill ranges and Unicode-scalar absolute/relative positions. The
shared text layout handles anchored chunks, omitted-axis continuation and
relative shifts inside glyph clusters. The importer resolves descendant cascade,
whitespace, coordinate lists, visibility, resource scopes and whole-text gradient
bounds. Source mappings identify the owning item, normalized scalar range and
original byte offset. Atomic insertion remaps those identities and retains
proposal/retry/undo behavior. See the [span contract](SVG_IMPORT.md#editable-span-ranges)
and [native positioning](TEXT_POSITIONING.md).

This implements the primary plan's explicit requirement to use text ranges where
the engine model can represent the source. Span-specific transforms, group
opacity, clipping, masks and isolation need separate compositing owners and
remain located refusals. Rotation, textLength, textPath, unsupported writing
modes, and differing styles or absolute positions inside a grapheme also remain
unsupported. These effects are not silently flattened into fill alpha or outlines.
Identically styled markup within a grapheme shares one range. Source XML nesting
and descriptions are not retained, import-time mappings do not track edits, and
later range edits may merge initial DOM shaping boundaries; the import contract
and loss receipts state those limits. This does not claim all SVG typography.

Sixteen original span tests use synthetic fonts and independent glyph origins,
rectangular pixels at multiple scales, overlap-alpha calculations, source offsets
and scalar ranges. They cover nested styles and sizes, coordinates, anchors,
whitespace, supplementary characters, visibility, gradients, reuse, mask sources,
grapheme boundaries, located failures, resource limits and session insertion.
Twelve positioning tests additionally check edits, snapshots, outlined delivery,
components, failed-batch rollback and history. Related SVG, text, publication,
recovery and all other repository checks ran fresh in both full suites:

| Platform | Fresh stages | Rust tests | Python executed | Explicit skips | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows | 252 | 216 | 2,649 | 13 | 760.5 |
| Linux / WSL | 252 | 182 | 2,611 | 51 | 446.8 |

There were no failures, pending checks, reused passes or stages outside scope.
All sixteen span tests and twelve positioning tests ran on both platforms.
Windows skipped four unavailable symlink fixtures, one Unix directory-alias
fixture and eight separately configured handoff/consumer checks. Linux's 51 skips
retain Windows jobs/process accounting and separately configured handoff gates;
they are not Linux feature passes. The final focused span check took 13.7 seconds,
reusing only unchanged formatting/build/Clippy results; routine feedback retains
the 180-second budget.

Both full reports bind matching, unchanged source fingerprint
`d14a5e1d8eba2c1da09f5204a125a3115fe1cb806256f050ffa55ab5de28f9f9`.
The external `w3a-spans-acceptance-01` bundle retains all 504 stage logs, both
reports, the focused follow-up, a requirement review and an 891-file source
inventory/archive. Its 512-file audit has SHA-256
`cbc0ab207e902f6e39af05ea70aa160cd69968444b7797b8a07ac1e2900cd89f`.
These status updates leave tested engine and fixture inputs unchanged. Earlier
focused evidence and corrected failures remain in `w3a-positioning-focused-01`
and `w3a-spans-focused-01` rather than being replaced by the milestone record.

W3a.8 opt-in omission reports are next. Unix jobs, macOS verification of this
increment, distribution, actual-model/scale evidence and the overall goal remain
separate. No engine checkpoint is awarded; the registry remains 163/167.

## W3a.8: complete within the explicit omission contract

The explicit `unsupported:"omit_and_report"` policy now shares import and atomic
insertion. Fresh private strict attempts discard reported source subtrees and
dependents of their removed IDs. Original byte ranges, line/column positions,
source hashes and nested receipts survive filtering and fragment wrapping.
Strict import remains the default. See the [omission contract](SVG_IMPORT.md#explicit-omission-reports).

The first focused run exposed a deep-XML process stack overflow before the
post-parse nesting guard, ambiguous malformed-length classification and missing
capability-limit bindings. These are corrected. Original XML depth is checked
lexically before parsing (including the insertion probe), and literal numbers
are validated before unknown length units become eligible for omission.
Imported Python test classes were also replaced with module aliases to avoid
unintentionally repeating unrelated suites.

Matching unchanged inputs passed all eleven selected stages fresh on Windows
and Linux: formatting, locked build, all-target Clippy with warnings denied,
the typed insertion byte-ceiling test, six Python modules and the private guard.
Windows executed 85 Python tests with no skips in 80.8 seconds; Linux executed
82 with three explicit Windows verifier/process-accounting skips in 121.9
seconds. All 18 omission fixtures ran on both platforms, including exact pixels,
Unicode locations, source immutability, dependency removal, strict/fatal failures,
MCP parity, proposal/retry receipts, undo/redo and failed-batch rollback.

The 894-file candidate is
`c4a9af521061ae92e604625e37a3c37cd1e5410484950869e2ec1879d5923ac0`.
The frozen source archive/inventory, three reports (including the failed first
run) and all 33 stage logs are retained in `w3a-omissions-focused-01`; its
38-file evidence index has audit SHA-256
`2f019070708826157a756ad115858c3fc3fa88d6df8bf5555b499a9444f64922`.
Source archive entries and every indexed hash were independently reread.
Only status Markdown and one fixture's trailing whitespace changed after that
capture; engine bytes and fixture syntax trees remain identical.

Subsequent late-resource work retains the source node and outermost placement
through gradient resolution, paints, clips and masks. Positions are calculated
only on error. Unsupported child descriptions, stops and image children retain
their own owners; malformed mask literals and conflicting gradient references
remain fatal. A retained-source review covers structural/global validation,
styles, ordinary artwork, text, definitions, reuse and late resource application.
Root/global failures still refuse a document, and errors outside
`SVG_UNSUPPORTED` never become omissions.

The follow-up Windows selection passed all eleven stages fresh in 76.5 seconds:
88 Python tests executed, one explicit unavailable-symlink skip, and the new
Rust cumulative-work boundary test. All 26 omission fixtures ran. The boundary
test checks inputs immediately below/above the total byte ceiling, counts the
successful attempt and proves an excess attempt never reaches the strict
importer. The preceding failed run exposed a test search that matched
`linearGradient` while looking for `line`; its corrected source-location
assertion passes. Reports are retained as `w3a-omissions-windows-03/04`.

The subsequent full Windows run passed all 253 stages fresh on unchanged inputs
in 926.9 seconds, with 217 Rust tests, 2675 Python tests executed and 13 explicit
skips. During its requirement review, an additional upgrade check exposed an
older strict SVG action fingerprint mismatch. That suite pass therefore does
not close the milestone. The pre-fix report/source are retained separately in
`w3a-omissions-acceptance-01`.

Historical action fixtures independently reconstruct both original SVG request
encodings and their SQLite checksums. They reproduce rejected retries/proposals
before the fix. Compatibility now accepts only those historical formats with
default newly introduced fields; current identities, saved rows, changed-action
rejection and proposal content checks remain intact. The first corrected
Windows selection passed all nine stages fresh in 79.7 seconds. After the
capability/documentation follow-up, matching focused Windows/Linux runs passed
all eight stages fresh in 84.6/120.1 seconds: 35 Python and 21 Rust tests per
platform, without skips. Routine feedback stayed within 180 seconds.

Fresh full acceptance then passed all 254 stages per platform on matching,
unchanged inputs, with no failures, pending checks or reused passes:

| Platform | Rust tests | Python executed | Explicit skips | Seconds |
| --- | ---: | ---: | ---: | ---: |
| Windows | 217 | 2,680 | 13 | 943.9 |
| Linux / WSL2 | 183 | 2,642 | 51 | 591.7 |

All 26 omission tests, five historical-identity tests, sixteen span tests and
ten insertion tests ran on both platforms. Both full Rust runs exercised the
cumulative-source-work boundary. Windows skips cover four unavailable symlink
fixtures, eight separately configured consumer/baseline checks and one Unix-only
path case. Linux skips retain explicit Windows-job/process/measurement and
external-consumer boundaries. They do not establish Unix job support or waive
the separate configured handoff/model gates.

The 895-file candidate is
`ebcbe526696cbcac0fff2007ce3b3eb73de0c932ec026a83ebb46305151487f2`,
implementation commit `dace8dd`. The frozen source archive/inventory, requirement
review, historical declarations, failed reproduction logs, two final focused
reports, two full reports and all 524 stage logs are retained in
`w3a-omissions-acceptance-02`. Its 535-file evidence index has audit SHA-256
`d8fc1f58f746122e492f063d48c50ddc78dad627efac619cef785eac967c9d16`.
Every source archive entry and indexed evidence hash was independently reread.
Only final status Markdown follows this capture; implementation and test bytes
remain identical.

This completes W3a task 8 and D3 within the explicit omission contract. Root/global
failures remain fatal; degraded import can change appearance and is never silent.
No new macOS, complete SVG, engine-checkpoint or overall-goal claim is made. The
registry remains 163/167.

### W5.7 missing-field guidance: implementation verified; efficiency unproven

The retained 95-attempt error inventory includes 17 visible generic request-error
occurrences across B10, B17, B18 and B19. These are output occurrences, not
authenticated call counts, and include repeated observations. Three minimal
read-only reproductions on the accepted candidate retain the same generic error:
B10's empty native storage object, B17's receipt lookup without a session root,
and B19's history lookup without a limit. Current working schema queries and
their source trace identities are retained in
`w5-request-guidance-reproductions-01.json`.

The bounded implementation names the missing field and supplies a working
focused lookup for these cases, while preserving execution validation, workspace
defaults and retry identity. Diagnostics are bounded and do not echo caller
values. This targets fewer repair/discovery interactions;
broader catalogs, wrappers and unrelated format/storage work are not part of
this increment. Reproduce each failure before changing behavior, then remeasure
the affected tasks with the same externally configured client/model/settings
and at least five retained attempts per applicable arm. B17/B19 remain engine-only.
If request repair does not improve without correctness loss, stop expanding this
approach. Unknown usage/call metrics stay unknown and cannot establish an
efficiency gain. The completed follow-up below applies that recorded decision.

The [request guidance contract](REQUEST_DIAGNOSTICS.md) confirms missing names
against generated typed schemas and supplies an executable lookup. It does not
guess an instance path; ambiguous owners retain command-level guidance. The
successful inline path does not clone the request or generate a discovery schema.
The first focused run exposed missing hints for schemas without definitions and
a limit-catalog import mismatch; both failures and their repairs are retained.

Retry verification also exposed a historical no-match Rust selector that remained
in the failed-check queue after fresh complete Rust passes. The verifier now
records such older failures as `superseded` only after a fresh unchanged full
Rust pass. Original failures/logs remain available, and supersession never counts
as a passing filtered test. Explicit current filters still require their own
passing test evidence. See the [verification contract](DEVELOPMENT_LOOP.md).

Focused Windows and WSL/Linux runs passed all ten selected stages fresh in 44.0
and 72.4 seconds respectively. Windows ran 217 Rust and 57 Python tests without
skips; Linux ran 183 Rust and 54 Python tests with three explicit Windows-only
verifier skips. All five request-guidance tests ran on both platforms, covering
CLI/MCP agreement, executable queries, repairs, workspace defaults, retry
preservation, ambiguous names and bounded output. Three retained read-only
probes now return working guidance in 322, 305 and 308 stdout bytes. These are
response measurements, not model-efficiency results.

Both passing runs bind the same 898-file source fingerprint
`57735de41b681322b80f0b6bba43e70bbbec9e207c3ec382358da26e70dbbd70`.
The private `w5-request-diagnostics-focused-01` bundle retains all four reports,
36 stage logs, before-implementation evidence, repair probes and a source
archive. Its 44 evidence-file hashes and every archived source entry were reread;
the audit SHA-256 is
`99743d797e796455a219a59f91ef0a4d3067a729d798555a21f6db90aaa7bf90`.
Only plan/status Markdown changed after that focused capture.

Fresh full Windows/Linux acceptance at `447bbc2` passed all 255 stages on each
platform with matching unchanged inputs and no failures, pending checks or reuse.
Windows ran 217 Rust and 2,687 Python tests, with 13 explicit skips, in 759.0
seconds. Linux ran 183 Rust and 2,649 Python tests, with 51 skips, in 444.5 seconds.
All five request-guidance tests ran on both. Windows skips cover unavailable
symlink privileges, one Unix-only path check and separately configured handoff
tools; Linux retains its declared Windows-process/job and optional-tool skips.
The 898-file candidate is
`29c47929d8119c4d984e58664644374390f6ad95d916c83d2981d8fb4800b0af`.
The private `w5-request-diagnostics-acceptance-01` bundle retains source, all 510
stage logs, both reports and the requirement review. All 516 evidence-file hashes
and every archived source entry were reread; the audit is
`a9935f43fa7275af45c539081a34af28b04714ecd7963de2fc3b67db3ab17e71`.
Its implementation acceptance is true; full W5 completion remains false.

The [fixed follow-up trials](BENCHMARK_RESULTS.md#b10b17b19-at-447bbc2-request-guidance-follow-up)
then ran five attempts each for B10/B17/B19 and five B10 baseline attempts on that
same source. B10 passes 3/5 workflows versus 5/5 baseline; B17 passes 4/5 and B19
passes 4/5. Missing-field repairs are observed, but storage-context and receipt
format failures remain. No general efficiency gain is established. Retain this
bounded implementation and stop expanding the diagnostic approach on current
evidence. The broader W5 acceptance, full twenty-task evaluation, other readiness
gates and original checkpoint criteria remain unchanged.

### W4.1: native block editing and store admission

The separate accepted D7 target requires a 50 MP RGBA16 edit/history workflow
within 512 MiB. Legacy stored layers retain at most 256 overlays and 65,536
aggregate patched pixels over their lifetime, so continuing normal edits can
exhaust the document even when each edit is small. B10 remains a 2.07 MP workflow
failure and does not establish a capacity failure or justify raising ceilings.

The [W4.1 migration contract](NATIVE_COPY_ON_WRITE.md) now specifies explicit
layer migration, old-history preservation, pure review, durable manifest
projection and block publication before the document transaction. The first
library increment adds versioned candidate transfer with caller-required byte
budgets, exact typed-block validation and explicit external dependencies.
It does not change document storage modes or remove either lifetime cap.

Focused checks used `--rust sample_store::tests` plus
`test_resource_limits,test_stored_samples`. Windows passed 21 Rust and 17 Python
tests in 80.531 seconds, reusing unchanged formatting/build/Clippy passes from
the immediately preceding 34.860-second fix check. Linux passed 18 Rust and 15
Python tests in 104.556 seconds, with all seven selected stages fresh and two
explicit Python skips for unsupported jobs. All seven new transfer tests ran on
both platforms. Both final reports have unchanged inputs and fingerprint
`ac14050aeafa6333200460658fc9e699842c40e79707a65fe2ef59f03ce04b2f`.
Neither run had failed or pending selected checks; 249 stages were outside scope.
The initial constant-assertion Clippy failure and its corrected rerun are retained.

External evidence `w4-candidate-transfer-focused-01/audit.json` has SHA-256
`72a7000fa8af72c6be3d3d491ca35a17daa4795f7ee117a5027316b507e85b44`.
Its 28 evidence files and 901 archived source entries were reread against their
hashes. The archive identifies the final focused-check candidate; it does not
claim to capture the earlier failed source. This is implementation feedback,
not full W4.1 or scale acceptance. The 260-edit transport test exercises only
pure library candidates; it does not establish committed document/history edits.

The explicit-migration increment implements `sample_storage_migrate`, version-2
native layers, pure shared pending buffers and manifest-only document/session
commits. Focused checks cover 260 snapshot edits, all six native depth/channel
layouts, brush/retouch routing, pure proposals, exact receipts, interrupted block
publication and transaction commits, cancellation, concurrent writers and
independent pending/transport budgets. A full-history test continues beyond the
unchanged session capacity, checks every retained native state, restores a backup
and replays the original receipt. All eight new Python tests ran on both
platforms, including every encoded-sRGB depth/channel layout. Candidate-transfer
tests separately cover all admitted encodings. At that milestone, profile/HDR
document-migration cases and default adoption remained required, and imports
still defaulted to legacy storage. These checks do not establish the larger
workload memory target or complete W4.1.

Fresh full Windows and Linux suites passed all 256 stages per platform with no
reuse, failures, pending checks or outside-scope stages. Windows ran 229 Rust and
2,695 Python tests in 940.562 seconds; Linux ran 195 Rust and 2,657 Python tests in
532.308 seconds. Windows explicitly skipped 13 Python tests (eight external-tool
handoff cases, four unavailable symlink fixtures and one Unix-only path case).
Linux explicitly skipped 51 Python tests for unsupported jobs, Windows process
accounting/handle checks and external-tool handoff configurations. None of the new
block-edit tests were skipped. The runs overlapped on the same host and are
correctness evidence, not comparable performance measurements. Focused feedback
for the final history test took 25.235 seconds, including 15.062 seconds for all
eight Python tests; earlier focused platform runs completed within 180 seconds.

Both full reports have unchanged input fingerprint
`ebe22f4abcac7d3ef9e539c954ffd6e671f1df973c5916723f0b929a890b47ce`.
External evidence `w4-block-mode-acceptance-01/audit.json` has SHA-256
`638b9d34f8e111fa023df7c5ad397f8355f35c497a68c1afe31c23c20b42f3ef`.
Its 591 evidence files and 904 archived source entries were reread against their
hashes. Earlier implementation failures and corrected focused reports are
retained; the source archive identifies the final full-suite candidate, not the
earlier failed candidates. Subsequent status-document edits do not alter the
tested engine or fixtures.

Default-import adoption is now verified: new stored imports select version 2,
while an explicit version-1 option retains legacy output and receipt shapes.
Independent block bytes cover profile/HDR migration, built-in/embedded profiles,
signed zero, subnormal/negative float values and default imports beyond both old
edit caps. All ten block-edit Python tests ran on both platforms. B10 storage
judge v2 independently admits both representations with unchanged pixel, source,
history and memory criteria; damaged staged bytes/manifests fail. Scripted CLI/MCP
workflows and an explicit legacy CLI workflow pass their applicable checks.
Linux's unavailable commit-memory check remains explicit; no new model-trial or
efficiency claim follows from these scripted runs.

Fresh default-adoption full suites passed all 256 stages per platform with no
reuse, failures, pending checks or outside-scope stages. Windows ran 229 Rust and
2,697 Python tests in 811.969 seconds; Linux ran 195 Rust and 2,659 Python tests in
495.575 seconds. The same 13 Windows and 51 Linux skip categories described above
remain explicit; none of the new tests were skipped. Runs overlapped on the same
host, so timings are correctness-run durations, not a platform performance
comparison. Focused Windows feedback took 146.078 seconds and exposed a wrong
MCP entry point in the new fixture. The corrected test passed in 35.766 seconds;
Linux's full focused selection passed in 114.174 seconds. All remain inside the
180-second implementation budget.

Both final full reports bind unchanged input fingerprint
`c77aa72b1af695d730c77007af86d973c7799bf0686403da714edeffd3d3c080`.
External `w4-default-block-acceptance-01/audit.json` has SHA-256
`0e01ad42eaf9e57baa8313c7457ed834158b059a6dc7ecf39a3a3122c9b15b83`.
Its 555 evidence files and 904 archived source entries were reread against their
hashes. The initial failed fixture report is retained; the source archive binds
the final candidate. Only status documentation changes after full acceptance.

Aggregate store admission is now verified within its
[declared contract](NATIVE_COPY_ON_WRITE.md#aggregate-store-admission). An OS lock
serializes growth against 16 GiB of native bytes and 65,536 root entries. Exact
boundary tests charge unique missing blocks, interrupted stages and the temporary
hard-link alias, preserving old blocks. Fully deduplicated publication bypasses
capacity and lock waits. Cancellation, killed owners, cleanup failure and a
rejected session edit preserve the applicable publication/history boundaries.
Original receipts replay even after resources disappear.

Final full suites passed all 256 stages fresh per platform with no failures,
pending checks, reuse or outside-scope stages. Windows ran 238 Rust and 2,697
Python tests in 765.562 seconds; Linux ran 204 Rust and 2,659 Python tests in
469.958 seconds. The 13 Windows and 51 Linux Python skips retain the categories
above; every applicable new storage test ran. The Unix symlink and Windows
file-sharing cleanup fixtures run on their respective platforms.
Concurrent runs are correctness evidence, not a platform performance comparison.

Focused feedback took 82.0 seconds on Windows and 59.3 seconds on Linux after
correcting two Windows assertions that read an exclusively locked file. The
first Windows full run found two existing job-fixture commits failing on SQLite
contention. Those fixtures now retry their original transaction within the same
fixture wait bound; job deadlines and cancellation/output/attempt assertions are
unchanged. The targeted correction passed in 53.2 seconds, then both complete
suites passed. Earlier failures remain retained. Rust 1.89 also passed the
Windows locked all-target check. Separate public CLI checks observed the actual
busy error at 30.016 seconds on Windows and 30.006 on Linux, followed by exact
successful publication after releasing the lock, with unchanged source bytes.

The final full reports share unchanged input fingerprint
`f0f1e817db34bcb3c743cc5b0e55f1f58f49adb1c6c45a3e8a9721ffb7d1beb5`.
External `w4-store-admission-acceptance-02/audit.json` has SHA-256
`5f126f7406cf1da5b9e4633cc60759394c9ffcf88f93c78b600ca2a3a37b408e`.
Its 1,104 evidence files and 906 archived source entries were reread against their
hashes, including the earlier failed candidate and public CLI evidence bound to
the full-suite executables. Subsequent edits update status documentation only.

The W4.2 follow-up below stages encoded input and prepared pixels privately,
retaining only one source TIFF chunk at a time. Preserve old snapshots,
exact history/retries, pure review proposals and immutable base blocks. Use
targeted feedback within 180 seconds and full acceptance at storage milestones;
do not lift unrelated pixel/work budgets as a substitute for measured behavior.

Stop and revise the storage design if exact history or create-only publication
cannot survive failures, or measured memory/state growth violates the declared
budget. This first storage increment does not satisfy the complete 50 MP gate:
streaming import/export, native operations and the new independent `scale-v2`
cases remain required under W4. No accepted workstream or checkpoint is removed.

### W4.2: private source and pixel staging; scale admission open

The [bounded importer](STREAMING_SAMPLE_IMPORT.md) stages encoded input and native
pixels privately, then validates and publishes one canonical block at a time.
Native extent admission now allows 256 MiB on disk while codec output/intermediate
allocations retain independent 64 MiB bounds. Encoded source remains 32 MiB;
aggregate private staging is 288 MiB. Native TIFF padded tile work is separately
bounded at 256 MiB. Inline limits, the 16,777,216-pixel canvas ceiling, persistent
store admission and output limits are unchanged. No resident frame receives the
disk allowance; source-defined TIFF chunks above the codec bound still fail.

Ordinary PNG retains a native row, Adam7 adds one coverage bit per pixel, and TIFF
retains one source chunk and row segments. Exact samples, typed identities,
source hashes, metadata, cancellation, private-file cleanup, immutable publication,
deduplication and history retain their contracts. Public pure candidates still
keep their existing in-memory representation.

Fresh full acceptance passed all 257 stages per platform on matching unchanged
inputs, with no failures, pending checks, reuse or excluded stages:

| Platform | Rust tests | Python executed | Explicit skips | Seconds |
| --- | ---: | ---: | ---: | ---: |
| Windows | 251 | 2,701 | 13 | 974.579 |
| Linux / WSL | 217 | 2,663 | 51 | 639.447 |

Both suites used four workers and overlapped; their timings are correctness
evidence, not performance comparisons. Windows focused checks passed in 130.8
seconds. The first Linux focused run took 78.3 seconds and exposed one fixture
still expecting rejection at the old image-byte ceiling. It now tests the
unchanged canvas-pixel ceiling; the focused repair passed in 8.1 seconds. The
initial failure and later passing reports/logs remain retained.

An isolated Windows development-build diagnostic used original compressed images,
with every block unique and every native byte/manifest checked independently.
All twelve candidate imports passed (three repetitions for each case below);
the prior implementation rejected each of the four cases at its old extent bound.

| Input | Native disk extent MiB | Median peak commit MiB | Median seconds |
| --- | ---: | ---: | ---: |
| 4096x3072 RGBA16 ordinary PNG | 96 | 1.895 | 7.681 |
| 4096x3072 RGBA16 Adam7 PNG | 96 | 3.105 | 9.055 |
| 4096x3072 RGBA16 tiled TIFF | 96 | 1.969 | 10.379 |
| 4096x4096 binary32 RGBA tiled TIFF | 256 | 2.617 | 25.135 |

These are Windows lifetime process counters on synthetic, highly compressible
inputs. They establish import admission and retained-memory behavior, not
release performance, arbitrary codec layouts, a whole-process memory guarantee,
or the 50 MP edit/export gate. The separate full-frame TIFF fixture proves that
an oversized codec chunk is refused without publishing resources.

Both complete reports and the diagnostic bind source fingerprint
`12301b29830071c0de69a2874a64f84222e681e40a8fee13c43cda1f996f9207`. External
`w4-native-capacity-acceptance-01/audit.json` has SHA-256
`71cd458bc11e39ea1d2d9367121265a84beed77744aa5187c3feca6596ca28d1`.
The audit rereads all retained source/evidence hashes; its measurement index binds
the original native stores without duplicating them. Earlier source/pixel staging
acceptance remains retained under `w4-source-staging-acceptance-01` and
`w4-pixel-staging-acceptance-01`, including the paired 48-import diagnostic and
their original failed attempts. Subsequent changes update acceptance docs only.

Native JPEG, coordinated 8192-square canvases and encoded-input/output limits,
streaming output, the complete 50 MP workflow and independent `scale-v2`
acceptance remain open. No original checkpoint receives additional credit.

## W3b: complete within the insertion contract

`add_svg` is an atomic edit accepting fragments and complete SVG documents. It
uses the existing importer, returns deterministic collision-checked item IDs,
retains approximation/loss receipts and reuses pinned destination fonts. Parent
coordinates, full-document viewport clipping, destination compositing and
metadata exclusions are explicit in the [contract](SVG_IMPORT.md#insert-into-an-existing-document).
Existing locks, destination restrictions and resource ceilings remain enforced.

Ten new Python tests cover independently calculated pixels, transformed parents,
clipping and masks, font bytes, unchanged unrelated state, profiles/HDR, metadata,
source offsets, schema/example execution, failures and session dry-run/apply,
retry, rollback, undo/redo and reopening. A typed Rust test checks the exact
request-derived source-byte boundary for fragments and complete documents.

Focused Windows verification passed in 74.6 seconds: one Rust test and 91 Python
tests ran; ten insertion tests reused their identical 13.6-second passing check.
Linux/WSL ran all 101 selected Python tests and the Rust boundary test in 122.1
seconds, including fresh build and all-target Clippy. No failures, pending checks
or platform skips occurred. Both selected runs bind source fingerprint
`55028d2675b9e20fea00e1a306979586eb3dfac1080343f744b4e10a261296cc`.
Fresh Windows acceptance at `e9c493e` passed all 219 stages, with no reuse,
failures or pending checks: 209 Rust tests and 2,318 Python tests executed, with
one explicit skip, in 1506.7 seconds. Its source fingerprint is
`c7bf604f97349decfa51d8d9f0aa26454268d305c107591442c488e4fb39419b`.
The same byte-matched Linux snapshot passed all 219 fresh stages in 920.3 seconds:
178 Rust tests and 2,285 Python tests executed, with 34 explicit platform skips
and no reuse, failures or pending checks. Both reports confirm unchanged inputs.
The full runs were consecutive; focused B02 checks shared the host during the
Linux run, so these durations are correctness evidence, not isolated performance
measurements. Subsequent B02 harness work does not change that frozen candidate
or engine.
No engine checkpoint or whole-goal credit is added by this implementation increment.

## W5.1: complete within the declared response contract

All MCP formats now send supported PNG payloads once using the existing payload
references. Default JSON and Markdown retain textual metadata envelopes;
overflow PNGs remain once in structured content. The explicit `structured`
format uses the existing preview summary presentation for any result. Clients
reconstruct the same CLI artifacts; engine execution and source documents stay
unchanged. See [the transport contract](AGENT_INSPECTION.md), including the required
update for clients that previously read default MCP PNG `data` directly.

Actual JSON-RPC line measurements on original fixtures:

| Fixture / mode | Before (bytes) | After (bytes) | Evidence |
| --- | ---: | ---: | --- |
| 128x128 seeded PNG, default JSON | 226,597 | 76,129 | 66.4% smaller; one payload instead of three |
| Same PNG, Markdown | 226,696 | 76,288 | One payload instead of three |
| Same PNG, preview | 76,016 | 76,016 | Existing summary presentation preserved |
| Editable snapshot, default JSON | 263,097 | 263,097 | Default non-PNG text compatibility preserved |
| Same snapshot, structured | Unsupported | 131,758 | 49.9% smaller than default JSON |

Windows and Linux produced identical post-change wire sizes. The measurement
tool checks exact reconstruction and retains source/executable identities;
it does not establish model success, token counts or latency/memory budgets.
Windows focused checks passed in 125.8 seconds, affected workflows in 75.2
seconds and benchmark adapters in 158.5 seconds. The Linux build consumed most
of its first 180-second window; five pending checks completed in a 37.4-second
resume using identical passes. Broader Linux workflows and benchmark adapters
passed in 60.9 seconds, with one explicit Windows-job recovery skip. No selected
checks remain failed or pending. The fresh combined full acceptance recorded
above closes W5.1. Broader W5 interface changes, real model trials and the
unchanged engine-checkpoint criteria remain separate work.

## Earlier scale baseline

The tiled radial/twist milestone landed on `main` as `f9ea22a` on 11 October.
Capabilities report both operators as supported under bounded source paths;
wrapped borders remain unsupported. Its fresh thorough run passed all 210 checks
(200 Rust and 2,210 Python tests), and ten release workload trials passed exact
native-channel/history checks and a separate speed/memory comparison. Focused
development feedback took 115.4 seconds. This is an A5 increment, with no registry
checkpoint or whole-goal completion credit. Inspect
`git status` before editing to preserve any concurrent work.

## Archived W0 requirements (closed)

**Original problem (before implementation).** Scattered ceilings made W4
error-prone.

- **One value, five separate constants.** 16,777,216 is defined independently in
  `src/sample_store.rs` (`MAX_PIXELS`), `src/render/tiled.rs` (`MAX_PIXELS`),
  `src/render/coverage_cache.rs`, `src/assets.rs` (`MAX_ASSET_PIXELS`) and
  `src/sequences.rs:14`.
- **Duplicated tile edge.** The tile edge of 128 is defined twice and the two are
  not linked.
- **Literals in capabilities.** `capabilities` repeats limits as literals at
  `src/lib.rs` ~1478 (`65536`, `33554432`, `67108864`), ~1576 (`30000`/`32768`),
  ~1662 (`262144`) and ~1673-1698 (`1_048_576`, `16_777_216`, `minimum_items:128`).
  `src/jobs.rs:29` has its own.
- **Literals elsewhere.** `src/layered.rs:116` has a bare `30000`. The spatial
  index threshold `128` is a literal at `src/render/prepared.rs` ~95. Error
  messages hard-code numbers (`model.rs` ~543/608/937, `geometry.rs:146`,
  `retouch.rs:297`, `pixel_brush.rs:565`, `assistance/segment.rs:44,148`,
  `sample_import.rs:127`).
- **Tests.** Tests hard-code limits (`test_tiled_render.py:127`,
  `test_stored_samples.py:259`, `test_large_raster.py:51,62,77`,
  `test_native_brush.py:98-99`, `test_large_vector_cli.py:178`,
  `test_native_retouch.py:223,259`).

**Tasks**

1. Create `src/limits.rs` holding every resource ceiling as a named, documented
   constant. Include the document/profile limits in `model.rs:8-19`, render
   limits, the native store, decoders, sessions (`sessions.rs:26-32`), requests
   (`lib.rs:114`, `mcp.rs:20-21`), jobs, work budgets and caches. Re-export them
   or replace the module-local constants. Derive related values from each other
   (for example `MAX_TILES = MAX_PIXELS / TILE_EDGE^2`).
2. Make `capabilities` read only from these constants. Remove every literal.
3. Format error messages from the constants.
4. Add a test asserting that each limit `capabilities` reports equals its
   constant. Change the tests listed above to read limits from `capabilities`
   instead of literals.
5. Add a generated `docs/LIMITS.md` table, or a section in an existing doc, as
   the single human-readable limit reference. Link to it from the ~50 docs that
   repeat numbers, and over time replace their numbers with the link.

**Acceptance.** No limit numeric literal remains outside `limits.rs` (verify by
grep). Behavior is unchanged: the quick verify passes, and `--thorough` passes at
the end of W0.

## Initial platform findings (historical)

**Original findings (before implementation).** Only Windows had evidence. The
initial audit identified these gaps; the linked status records subsequent work:

- **Receipts.** `src/publications/file_identity.rs:55-61` is a non-Windows stub,
  so any `receipt:{...}` publish, backup, recover or migrate fails off Windows.
- **Durable jobs.** These are stubs off Windows: `src/jobs.rs` ~62-67, 377-412,
  518-578 and `src/job_process.rs` ~266-288. They use raw `kernel32` externs in
  `src/job_process/windows.rs:52-78`. `ProcessIdentity.created` is a Windows
  FILETIME.
- **Clippy.** It likely fails off Windows with `-D warnings` on now-unused items:
  `jobs.rs` `receipt` ~253, `bound_control` ~259, `complete` ~236, the `runtime`
  variable ~425 and the `reconcile` parameter ~414, plus
  `job_process::release_start` ~30.
- **Python test discovery.** `tests/test_jobs.py:8` imports `msvcrt` at module
  level and uses `WinDLL`, which breaks discovery for the whole Python suite.
  The receipt, job and recovery benchmark tests have no platform skips.
- **Measurement and benchmark tools.**
  - `tools/workload_cases.py:4` imports `ctypes.wintypes` at module level.
  - `tools/measurement_host.py` uses `WinDLL`/`winreg`. `workload_gates.py`
    ~117/152 then hard-fails off Windows.
  - B19/B20 adapters `require(os.name=='nt')`.
- **Guard.** `tools/check_repo.py:27` hard-requires the private policy, and
  `tools/verify.py` ~240-248 stops at the guard, so a fresh clone or CI cannot
  run anything.
- **No CI.** There is no CI, no `rust-version` and no toolchain pin.
- **Windows-only docs.** `examples/mcp-config.json` hard-codes
  `C:/Tools/Inkbolt/inkbolt.exe`, and the README examples are PowerShell-only.
