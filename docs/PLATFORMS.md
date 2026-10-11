# Platform support and WSL verification

The Linux tier covers the Rust library, JSON CLI, MCP over stdio, vector/raster
editing, sessions and durable publication/history receipts. Its acceptance suite
runs on Ubuntu 22.04 under WSL2, x86-64, with Rust 1.98.1 and Python 3.11.
Windows retains its durable background-job implementation. Linux job commands
return `UNSUPPORTED_PLATFORM` before writing a queue or output;
`capabilities.jobs.supported_here` and `job_process.supported_here` are false.
The Unix file-identity implementation is shared source, but macOS remains
unverified. This does not establish full W1, distribution or scale acceptance.

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
This workflow does not introduce the planned public CI guard or enable CI.

For direct Linux use, configure the normal checkout-local private policy as
described in [research boundaries](RESEARCH.md), then run:

```bash
cargo build --locked
./target/debug/inkbolt examples/create-vector.json
./target/debug/inkbolt mcp --tools core
python3.11 tools/verify.py --only test_cli,test_mcp
```

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
