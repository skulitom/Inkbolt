# Platform support and WSL verification

The Linux tier covers the Rust library, JSON CLI, MCP over stdio, vector/raster
editing, sessions and durable publication/history receipts. Its acceptance suite
runs on Ubuntu 22.04 under WSL2, x86-64, with Rust 1.98.1 and Python 3.11.
Windows retains its durable background-job implementation. Linux job commands
return `UNSUPPORTED_PLATFORM` before writing a queue or output;
`capabilities.jobs.supported_here` and `job_process.supported_here` are false.
The shared Unix core/receipt tier also passed hosted macOS 15 ARM64 acceptance.
The latest retained hosted Windows/Linux/macOS matrix passed at `171a1c5`,
including the matched benchmark reporter; see below.
This does not establish full W1, distribution, Unix jobs or scale acceptance.

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

The [latest retained matrix at `171a1c5`](https://github.com/skulitom/Inkbolt/actions/runs/38421962898)
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
timing/contention failures. Their correction and hosted confirmation remain
pending; this does not supersede the last complete matrix. See
[retained evidence](DEVELOPMENT_STATUS.md).

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
