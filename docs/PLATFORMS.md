# Platform support and WSL verification

The Linux tier covers the Rust library, JSON CLI, MCP over stdio, vector/raster
editing, sessions and durable publication/history receipts. Its acceptance suite
runs on Ubuntu 22.04 under WSL2, x86-64, with Rust 1.98.1 and Python 3.11.
Windows retains its durable background-job implementation. Linux job commands
return `UNSUPPORTED_PLATFORM` before writing a queue or output;
`capabilities.jobs.supported_here` and `job_process.supported_here` are false.
The shared Unix core/receipt tier also passed hosted macOS 15 ARM64 acceptance.
The latest retained successful hosted Windows/Linux/macOS matrix is `d4692ea`,
through SVG images, spans, omissions and request guidance. This predates native
block migration, store admission and [private source snapshots](STREAMING_SAMPLE_IMPORT.md),
whose later evidence is Windows/WSL.
The subsequent [private source/pixel staging acceptance](DEVELOPMENT_STATUS.md#w42-private-source-and-pixel-staging-scale-admission-open)
passed all 256 stages fresh on Windows/WSL with matching unchanged inputs.
Windows ran 251 Rust and 2,698 Python tests, with 13 explicit skips, in 926.750
seconds; Linux ran 217 Rust and 2,660 Python tests, with 51 skips, in 630.942
seconds. No check failed, remained pending or reused results. Its source identity
is `68585115b760b7fe6bf7d398c5b121b55822fa02c469608a45114cb49a19b4fd`;
the retained audit is `76f46808a0a35528afd2ef231cb623fb198bb753abc8ae9f49082fc99ec05d7d`.
This does not extend hosted macOS evidence beyond the run recorded below.

Earlier failures and their focused follow-up remain recorded.
This does not establish full W1, distribution, Unix jobs or scale acceptance.

The [latest complete run](https://github.com/skulitom/Inkbolt/actions/runs/38791299542)
passed 255 fresh stages on each platform with matching unchanged inputs, no
failed, pending or reused checks, and successful minimum-compiler checks.

| Hosted platform | Rust tests | Python executed | Explicit skips | Seconds |
| --- | ---: | ---: | ---: | ---: |
| Windows 2025 | 217 | 2,691 | 9 | 4312.810 |
| Ubuntu 24.04 | 183 | 2,649 | 51 | 1441.953 |
| macOS 15 ARM64 | 183 | 2,649 | 51 | 2808.881 |

Reports, all 765 stage logs, run metadata and the 898-entry source archive are
retained under `w1-public-ci-d4692ea`. The archive matches every report's source
fingerprint `70bc66827b5ca35a8b6a79aff9f4287ced7f148033af53297bd608d32f641e45`.
The 770-file audit has SHA-256
`d6f70d11bb38970a204a06da83100f57ed1ce52a3480588a936ec2808977d1e2`.
Explicit platform/configuration skips remain recorded. This extends the hosted
core/receipt tier through request guidance; it does not verify the later native
block storage work on macOS or eliminate intermittent timing failures. Hosted
public structural checks leave the private policy unevaluated; mandatory local
candidate/staged checks and the commit hook remain separate.

The [earlier nested-SVG run](https://github.com/skulitom/Inkbolt/actions/runs/38738326742)
passed 249 fresh stages on every platform, with matching unchanged inputs and
no failed, pending or reused checks. The minimum-compiler checks also passed.

| Hosted platform | Rust tests | Python executed | Explicit skips | Seconds |
| --- | ---: | ---: | ---: | ---: |
| Windows 2025 | 216 | 2,609 | 9 | 4209.1 |
| Ubuntu 24.04 | 182 | 2,567 | 51 | 1437.8 |
| macOS 15 ARM64 | 182 | 2,567 | 51 | 2781.8 |

Reports, all 747 stage logs and run metadata are retained under
`w1-public-ci-c9a5532`, source fingerprint
`9c483a0e27deafb324ae14c68401dd8ea4e67f506774292e706a470d16d600db`.
The 751-file audit is
`d7ca02bbcc239e07bf954a467e2ee2d3b1dadb676dc15f9a029c9d6a78bee3f0`.
Hosted checks use the public structural guard and report private policy as
unevaluated; mandatory local candidate/staged guards remain separate. This
run extends macOS evidence through nested SVG and predates image admission.

The [earlier `10c3505` run](https://github.com/skulitom/Inkbolt/actions/runs/38704401571)
passed 243 fresh stages on every platform, with unchanged inputs and no failed,
pending or reused checks. Windows ran 215 Rust and 2526 Python tests, with eight
explicit skips, in 3702.5 seconds. Linux/macOS each ran 181 Rust and 2484 Python
tests, with 50 skips, in 1418.1/2633.1 seconds. Reports and logs are retained under
`w1-public-ci-10c3505`, candidate
`fa44b6a32da94c89844854edbc5f4d1a94b77c1cb8cde913567256abb6f04362`;
the 732-file audit is
`7c9c3a4e7f5d005e0511a1fd3c3dc1366b0fcaf0e3a3c400a04937bdc4506579`.
This is a successful run after the Windows changes, not proof that intermittent
timing failures cannot recur. Subsequent benchmark-judge edits have separate
focused Windows/WSL evidence. The preceding `1d5b960` full matrix remains retained
under `w1-public-ci-1d5b960`; these hosted runs predate the embedded SVG CSS work.

The later embedded-style milestone passed fresh local Windows/WSL acceptance:
244 stages per platform, with no failures, pending checks or reuse. Windows ran
216 Rust and 2,543 Python tests with four explicit skips; Linux ran 182 Rust and
2,496 Python tests with 51 explicit skips. Both runs verified unchanged, matching
inputs. See [the CSS acceptance record](DEVELOPMENT_STATUS.md#w3a3-complete-within-the-embedded-style-contract)
for the candidate identity, skip boundaries, timings and retained evidence. This
does not extend Linux background-job support. The later hosted run above
establishes macOS evidence through nested SVG.

The subsequent [reusable-SVG milestone](DEVELOPMENT_STATUS.md#w3a4-complete-within-the-reusable-svg-contract)
passed all 248 fresh local stages on each platform at `3eaf500`, with matching
unchanged source inputs. Windows executed 216 Rust and 2,590 Python tests with
12 explicit skips; Linux executed 182 Rust and 2,551 Python tests with 51 skips.
No reusable-SVG test was skipped. The linked acceptance record retains exact
inputs, logs and skip boundaries; Unix jobs and the separate configured
handoff/model gates remain open. Later hosted macOS evidence is recorded above.

The [nested-SVG milestone](DEVELOPMENT_STATUS.md#w3a5-complete-within-the-nested-viewport-contract)
subsequently passed all 249 fresh stages per platform at `c9a5532`, again on
matching unchanged inputs. Windows executed 216 Rust and 2,606 Python tests with
12 explicit skips; Linux executed 182 Rust and 2,567 Python tests with 51 skips.
No nested-SVG test was skipped. The linked record retains the source archive,
all 498 logs and requirement review. The hosted matrix above subsequently
passed this revision on all three platforms; Unix jobs and separately configured
handoff/model gates remain open.

The [SVG image milestone](DEVELOPMENT_STATUS.md#w3a6-complete-within-the-image-contract)
passed all 250 fresh local stages per platform on matching unchanged inputs.
Windows executed 216 Rust and 2,621 Python tests with 13 explicit skips in 730.4
seconds; Linux executed 182 Rust and 2,583 Python tests with 51 skips in 467.2
seconds. All sixteen image tests ran on Linux; Windows skipped the image
symlink fixture because host privilege was unavailable. The linked record
retains the source archive, full logs, requirement review and skip boundaries.
This does not establish macOS image verification or Unix background-job support.

The [SVG span-range milestone](DEVELOPMENT_STATUS.md#w3a7-complete-within-the-span-range-contract)
subsequently passed all 252 fresh local stages per platform on matching unchanged
inputs. Windows executed 216 Rust and 2,649 Python tests with 13 explicit skips
in 760.5 seconds; Linux executed 182 Rust and 2,611 Python tests with 51 skips in
446.8 seconds. All sixteen span tests and twelve native positioning tests ran on
both platforms. The linked record retains all 504 logs, the source archive and
requirement review. This establishes the documented text-range contract on
Windows/Linux, with no new macOS or Unix background-job claim.

The [explicit SVG omission milestone](DEVELOPMENT_STATUS.md#w3a8-complete-within-the-explicit-omission-contract)
passed all 254 fresh local stages per platform on matching unchanged inputs at
`dace8dd`. Windows executed 217 Rust and 2,680 Python tests with 13 explicit skips
in 943.9 seconds; Linux executed 183 Rust and 2,642 Python tests with 51 skips in
591.7 seconds. All 26 omission and five historical SVG request-identity tests ran
on both platforms. The linked record retains source, full logs, requirements and
skip boundaries. No additional macOS or Unix background-job support is claimed.

The [missing-field guidance implementation](DEVELOPMENT_STATUS.md#w57-missing-field-guidance-implementation-verified-efficiency-unproven)
at `447bbc2` passed all 255 fresh local stages per platform on matching unchanged
inputs. Windows executed 217 Rust and 2,687 Python tests with 13 explicit skips;
Linux executed 183 Rust and 2,649 Python tests with 51 skips. All five new
request-guidance tests ran on both. The linked record retains all 510 logs,
source and skip boundaries. Model-efficiency acceptance and Unix jobs remain open.

`rust-toolchain.toml` pins the verified development compiler, rustfmt and Clippy
to Rust 1.98.1. `Cargo.toml` declares Rust 1.89 as the minimum: the locked
`moxcms` dependency requires it, as does the standard file-locking API. Separate
`cargo +1.89.0 check --locked --offline --all-targets` runs passed on Windows and
Linux against the unchanged engine sources and lockfile. These are compiler
compatibility checks, not additional runtime or macOS acceptance.

Fresh W0 acceptance on 11 October 2026 tested engine commit `53518fd`
on both platforms. Every verification stage ran afresh, including formatting,
the locked build, all-target Clippy with warnings denied, Rust tests and all
208 Python modules. There were no failures, pending checks or reused passes.

| Platform | Stages passed | Rust tests | Python tests executed | Explicit skips | Duration |
| --- | ---: | ---: | ---: | ---: | ---: |
| Ubuntu 22.04 / WSL2 x86-64 | 213 | 176 | 2,244 | 34 | 494.5 s |
| Windows | 213 | 208 | 2,278 | 0 | 1006.1 s |

The 34 Linux skips comprise 28 job-dependent tests and six Windows memory/host
measurement tests. Linux uses Rust/Cargo 1.98.1, Python 3.11.13 and a native ELF
executable. WSL evidence does not establish macOS, other Linux distributions,
Unix background jobs or the full scale/distribution goals.

The final focused W0 change passed in 87.3 seconds on Linux and 108.5 seconds
on Windows, with no skips. Thorough acceptance is a separate milestone gate;
routine changes retain the three-minute budget and identical-pass reuse.
An earlier Linux full run caught the benchmark manifests' missing shared-limit
helper; all workload suites now pin `tests/advertised_limits.py` through their
common manifest, while historical budgets remain unchanged.

The initial simultaneous full runs retained one Linux print-render timeout at
the existing 20-second fixture deadline. The isolated module rerun passed
unchanged in 64.8 seconds, followed by the fresh full Linux pass
above. Run full Windows and Linux acceptance consecutively on a shared host to
avoid competing with these bounded render fixtures; quick focused runs retain
their ordinary selectors and budget. No timeout or acceptance criterion changed.

Use native Linux storage for sources, builds and generated fixtures. The WSL
runner snapshots current candidate bytes, including uncommitted changes, into
an owned checkout under `~/.cache/inkbolt/wsl/`. It keeps Cargo and test caches
separate from Windows and refuses to overwrite local edits in that mirror.
Generated tests use the Linux temporary filesystem. This tests the Linux binary,
filesystem, SQLite, path handling and process groups, not a Windows executable
launched through WSL interoperability. WSL does not prove all Linux distributions
or mounted/network filesystem behavior.
The check process removes WSL's per-launch Windows interoperability socket from
its actual environment. This keeps native-only checks reproducibly cacheable
without weakening the verifier's environment fingerprint.

From the Windows checkout, with an existing WSL Ubuntu distribution, Rust/Cargo,
a C compiler, Git and Python 3.11 installed:

```powershell
python tools/verify_wsl.py --only test_platform_support,test_publication_receipts
python tools/verify_wsl.py --last-failed
python tools/verify_wsl.py
python tools/verify_wsl.py --thorough
```

`--distribution NAME` and `--python NAME` select another installed distribution
or Python executable. All remaining options pass to `tools/verify.py`;
`--report C:\external\linux-report.json` translates the Windows report path.
Quick checks retain the 180-second verification budget, exact-input pass reuse,
explicit pending status and focused selectors. First-time setup/downloads are
separate from normal feedback. Synchronization and source checks add overhead.
The runner verifies that the Windows source and private policy stayed unchanged
through the Linux run. Do not edit the candidate during acceptance checks.

The normal private repository guard runs on Windows before snapshotting and
again inside Linux. Its Git-private policy is copied only into the owned mirror's
Git metadata, along with a local guard hook. No research directory, Windows build
output or arbitrary ignored files are copied. The mirror makes no commits or
pushes. Logs and cache state stay under its `.git/inkbolt-verify/` directory.
The development mirror always requires that private guard and rejects `--public`.
It does not enable CI.

For a direct public Linux clone, run:

```bash
cargo build --locked
./target/debug/inkbolt examples/create-vector.json
./target/debug/inkbolt mcp --tools core
python3.11 tools/verify.py --public --only test_cli,test_mcp
```

The explicit public mode performs structural checks and reports
`private_policy:"not_evaluated"`; it does not satisfy the private commit hook.
Development checkouts retain the normal policy described in
[research boundaries](RESEARCH.md) and use verification without `--public`.
Public mode never activates automatically. Fresh public-clone Windows/Linux
acceptance is recorded in [development status](DEVELOPMENT_STATUS.md). CI is
enabled on main for Windows, Linux and macOS. After the directory-alias fixes,
[hosted Linux and macOS](https://github.com/skulitom/Inkbolt/actions/runs/38186420025)
each passed all 216 fresh stages. Windows still reported an expected `JOB_BUSY`
response mishandled by a polling test and a concurrent print-render timeout.
That poll now uses the existing bounded busy-retry helper; Windows and macOS
verification run serially without relaxing any deadline or image oracle. A
complete hosted matrix subsequently passed at
[`5dfb699`](https://github.com/skulitom/Inkbolt/actions/runs/38207200768), including
the production publication-lock retry. All three platforms ran 227 fresh stages
with no failures, pending checks or reused passes. Windows ran 212 Rust tests
and 2,376 Python tests with one explicit skip in 3672.1 seconds. Linux and macOS
each ran 178 Rust tests and 2,341 Python tests with 36 explicit skips, in 1039.2
and 2241.3 seconds respectively. The shared candidate fingerprint was
`4e52a6f0ff99f44c8ac28876ba466d6c444fb08a8a7b177f834e4cb4aec6dfcf`.
These full milestone runs do not replace the 180-second routine feedback budget.

The later `3ac68d6` macOS run exposed a collision between timestamp-named test
directories. Fixture allocation now uses an atomic sequence and exclusive
creation. Concurrent repeated-clock and complete session-retry checks pass on
Windows/Linux. The [complete `20ac313` hosted run](https://github.com/skulitom/Inkbolt/actions/runs/38377988007)
now passes all 230 fresh stages on Windows, Linux and macOS, confirming the fixture
fix. Windows ran 213 Rust and 2396 Python tests with one explicit skip; Linux and
macOS each ran 179 Rust and 2362 Python tests with 35 explicit skips. Production
session behavior and existing assertions are unchanged. See the exact candidate,
timings and retained evidence in [development status](DEVELOPMENT_STATUS.md).

The [earlier matrix at `171a1c5`](https://github.com/skulitom/Inkbolt/actions/runs/38421962898)
passed all 241 fresh stages on every platform, with unchanged inputs and no
failures, pending checks or reused passes. Windows ran 213 Rust and 2473 Python
tests with seven skips in 4488.8 seconds. Linux and macOS each ran 179 Rust and
2432 Python tests with 48 skips, in 1274.1 and 2698.0 seconds respectively.
Reports and logs are retained externally under `w1-public-ci-171a1c5`; the shared
candidate fingerprint is
`19205e33567634035ef3531377ad668baf9eb3947c4a405510777024507f714c`.
This revision predates the Codex adapter and first-page discovery change; their
focused checks do not establish full-suite acceptance at the latest revision.

The subsequent [run at `9909329`](https://github.com/skulitom/Inkbolt/actions/runs/38431558895)
passed all 242 fresh Linux stages (179 Rust and 2446 Python tests, 48 skips,
1257.3 seconds). macOS failed an evaluation-test fixture that compared aliased
temporary paths with resolved paths. The fixture now matches the real harness's
resolved-path contract; a Linux alias reproduction failed before the correction
and all 13 checks passed afterward. Focused Windows/WSL checks also passed.
Windows exposed the same short-path fixture mismatch, plus two separate job-test
timing/contention failures. The fixtures now allow cold startup before testing
actual deadline stops and retry only documented busy responses while preserving
the snapshot assertions. Focused Windows checks passed in 140.6 seconds; WSL
passed the platform boundary with explicit job skips in 7.0 seconds. The complete
`8bc8982` matrix below subsequently confirmed those job-fixture changes. See
[retained evidence](DEVELOPMENT_STATUS.md).

The [matrix at `a1a0339`](https://github.com/skulitom/Inkbolt/actions/runs/38440855374)
subsequently passed all 242 fresh stages on Windows, Linux and macOS, including
the evaluation path-alias correction. Windows ran 213 Rust and 2490 Python tests
with seven skips in 2651.7 seconds; Linux and macOS each ran 179 Rust and 2449
Python tests with 48 skips, in 1443.1 and 3034.6 seconds respectively. All inputs
were unchanged, with no failed, pending or reused stages. Reports/logs are
retained under `w1-public-ci-a1a0339`, candidate
`f985ad1ec589c62a2a342d58356d64d24095e61314e2a66a42d11afb4811d2db`.
This earlier complete matrix predates the later B01/B03 store-judge
and Windows job-fixture changes, whose focused checks remain separately scoped.

The [complete `8bc8982` matrix](https://github.com/skulitom/Inkbolt/actions/runs/38446529203)
passed all 242 fresh stages on every platform. Windows ran 213 Rust and 2492
Python tests with seven explicit skips in 4448.6 seconds. Linux and macOS each
ran 179 Rust and 2451 Python tests with 48 skips, in 1421.4 and 2161.0 seconds
respectively. All inputs stayed unchanged; no checks failed, remained pending
or reused older passes. Reports/logs are retained under `w1-public-ci-8bc8982`
in the corresponding platform directories, with shared candidate
`72ed74353fa11496d6b06b678dbf5708d87f54ee4778da875a7d23eae566b63f`.
This confirms the B01/B03 store judges and Windows job-fixture timing/busy-retry
corrections. It predates the later B05-B07 judge corrections, whose focused
Windows/WSL checks do not establish a newer complete matrix.

The [retained complete matrix at `7a07f07`](https://github.com/skulitom/Inkbolt/actions/runs/38468108741)
passed all 242 fresh stages on every platform. Windows ran 213 Rust and 2495
Python tests, with seven explicit skips, in 2950.1 seconds. Linux and macOS each
ran 179 Rust and 2454 Python tests, with 48 skips, in 1426.3 and 3026.1 seconds
respectively. Inputs were unchanged, with no failed, pending or reused stages. Reports/logs are
retained under `w1-public-ci-7a07f07`, with report and log hashes in
`complete-matrix-audit-01.json`, candidate
`6e3153244579fd3e0dcdebd7c42185b3787d71854664171b9f71b239364ae3a3`.
These passes predate the later B10/B13 delivery-judge, B11/B12 store/hierarchy
and B14/B15 store corrections. Those changes have focused Windows/WSL checks,
not a newer complete matrix. The hierarchy correction executed 56 Windows Python tests in
80.3 seconds and 53 Linux tests in 53.1 seconds, with three explicit Linux
platform skips and unchanged Cargo checks reused. No selected check failed or
remained pending; this is focused feedback, not complete milestone acceptance.
The subsequent B14/B15 store correction executed 45 Windows tests with one
symlink skip in 39.5 seconds and 43 WSL tests with three platform skips in
31.2 seconds. Cargo checks were reused and no selected check failed or remained
pending. Both reports under `w2-print-resources-store-` bind candidate
`a144f4c829b0b3c4dbf801fc9974551a3e7f73e5468e1912c8b4e85d59edb9e5`.

The B14/B15 delivery-label/folder and review-envelope correction executed 57
Windows tests with one symlink skip in 56.5 seconds and 55 WSL tests with three
platform skips in 47.6 seconds. Cargo checks were reused; no selected check
failed or remained pending. Both `w2-print-label-folder-` reports bind candidate
`3e8a23d1dadbe3b1e77f128afd83516fda6e7a0055bd89a48efb259d6daacb6d`.
These remain focused checks, not a new full platform milestone.

The subsequent B14 PDF-grammar correction executed 42 Windows tests with one
symlink skip in 59.3 seconds and 40 WSL tests with three platform skips in 42.5
seconds. Five unchanged test-reader consumer modules and Cargo checks reused
identical passes; no selected check failed or remained pending. Final reports
under `w2-print-pdf-grammar-` bind candidate
`94a18f910c738e3f2ff1f3949ecf081046a459506ec137a432eb6a3bb4a95024`.

The B16 repair-judge contract correction executed 46 Windows tests with one
symlink skip in 41.4 seconds and 44 WSL tests with three platform skips in 19.1
seconds. Unchanged Cargo checks were reused; no selected check failed or remained
pending. Both `w2-repair-contract-` reports bind tested fingerprint
`7a6e5b7f40cfdb7e130f3cb9db2c457c3891545401e739a28ce191baf07e5564`.
This is focused benchmark coverage, not a new full platform milestone.

B16's normalized-default correction executed 37 Windows tests in 33.5 seconds
and 34 WSL tests with three platform skips in 17.8 seconds; tested fingerprint
`b145613796e741388e7ca9599db61ae8d67957247010e5d5bb8400e2ec2aa2a5`.
After clarifying prompt version 2, all 11 repair tests passed on each platform
in 36.0/16.6 seconds, fingerprint
`42c67a9be4f9ceaf7654843253c9fd8f96e1811d9ca7b9ead35cf13990989910`.
Unchanged Cargo passes were reused, with no failed/pending checks or input
changes. Evidence is under `w2-repair-defaults-` and `w2-repair-prompt-v2-`;
neither focused run establishes full-suite acceptance.

B17/B18's reopened-default and review-envelope judge corrections executed 42
Windows tests in 32.7 seconds and 39 WSL tests with three platform skips in
19.2 seconds. Cargo passes were reused, inputs stayed unchanged and no selected
check failed or remained pending. The `w2-retry-conflict-contract-` reports bind
tested fingerprint
`f17fe2bed1e4e25d82dd2f7314a3962f2a736fa245e1c432ed0a8e29135a31f1`.
This is focused benchmark coverage, not a new platform milestone.

The [latest retained full matrix at `30c4ebd`](https://github.com/skulitom/Inkbolt/actions/runs/38476034163)
passed all 243 fresh stages per platform. Windows ran 213 Rust and 2502 Python
tests, with seven skips, in 4584.9 seconds. Linux/macOS each ran 179 Rust and
2461 Python tests, with 48 skips, in 1490.2/2715.8 seconds. Inputs stayed
unchanged, with no failed, pending or reused checks. Reports/logs and their hashes
are retained under `w1-public-ci-30c4ebd`, candidate
`811f2460a6ddb536965a2b822971fe8f6fbf0d3c9094c14e7bf4625ae337e81d`.
This covers the B10/B13 delivery and B11/B12 store corrections; it predates
the later hierarchy and B14/B15 judge changes and is not current-HEAD acceptance.

The [later `30ecf5b` run](https://github.com/skulitom/Inkbolt/actions/runs/38497212073)
passed Linux/macOS and failed two Windows stages: a test polling race and a
job-submission timeout. The polling fix and optimized development hashing have
focused Windows/Linux verification, with exact byte/hash assertions and existing
deadlines retained. Linux/macOS subsequently each passed all 243 fresh stages at
[`d34851e`](https://github.com/skulitom/Inkbolt/actions/runs/38504495500): 181 Rust,
2,482 Python tests and 50 explicit skips in 1317.3/2910.0 seconds. This predates the hash
profile change and does not prove current full-matrix acceptance or resolution of
the hosted Windows timeout. See [the diagnosis and focused evidence](DEVELOPMENT_STATUS.md#windows-polling-and-development-hash-cost).

The [Unix MCP configuration](../examples/mcp-config.unix.json) assumes `inkbolt`
is on the client's PATH; otherwise replace it with the absolute Linux executable
path. The [Windows configuration](../examples/mcp-config.windows.json) uses an
absolute installation path.

Receipt tests run on both platforms, including writer termination, cancellation,
history preservation and rejection of unrelated identical files. Job fixtures
consult engine capabilities at runtime and retain explicit skip reasons.
Windows-specific process-memory benchmarks are also explicitly skipped on Linux;
missing peak-commit measurements never become passing scale evidence. The verifier
reports Python tests executed and skipped separately. Full discovery and all
portable modules remain mandatory; skip counts do not imply feature passes.

See [publication receipts](PUBLICATION_RECEIPTS.md),
[recovery scope](RECOVERY_CONTRACTS.md) and the
[development loop](DEVELOPMENT_LOOP.md).
