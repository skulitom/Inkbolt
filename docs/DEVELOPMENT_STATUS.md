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

## W1: verified preparation, hosted evidence pending

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
The complete hosted matrix on the latest revision has not passed. Local
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
guidance now includes this focused check. The latest complete hosted matrix is
still required; those failed runs are not counted as passes.

The [hosted `fbc7fea` run](https://github.com/skulitom/Inkbolt/actions/runs/38197982149)
passed all 221 fresh stages on Ubuntu and macOS in 1137.3 and 2258.2 seconds,
including the corrected dependency-boundary expectation. No stage failed,
remained pending or was reused. Windows finished with 220 passed stages and one
failed Rust stage in 3569.9 seconds. All 2,330 Python tests passed with one explicit
skip, but the idle-exit fixture's second job terminated with `JOB_BUSY`; 142 Rust
library tests passed and one failed, preventing the remaining Rust targets from
running. Serial execution alone did not fix this failure. Its cause must be fixed
without relaxing the required successful job outcome. The newer benchmark adapter
commits have focused local evidence, not full hosted acceptance.

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

B09-B20 external adapters, broader baseline judges, arbitrary legacy transcript
adapters, matched comparison reporting and genuine model trials remain open;
full W2 milestone acceptance remains open. SVG arcs/rounded rectangles and the SVG insertion operation are independent
bounded increments. W2 evidence will sequence the substantial work using the
plan's decision rule; accepted outcomes remain required.

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
