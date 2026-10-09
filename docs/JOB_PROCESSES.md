# Contained job processes

The Windows Rust library provides `job_process` as the process-lifetime foundation for durable background exports. The [durable export queue](JOBS.md) now supplies CLI/MCP submission and recovery. Ordinary engine requests keep their existing synchronous behavior. This milestone earns no original engine-checkpoint credit and does not complete readiness gate A4.

## Lifetime and startup contract

The caller captures an `Executable` identity from an absolute regular file. `spawn` checks its exact length and SHA-256 while holding a handle that denies writes and deletion. The command must name that exact path. Executables are bounded at 512 MiB; hashing streams 64 KiB chunks and observes submission cancellation. The held handle remains alive with the runner. This binds executable bytes, not the complete operating system, environment or dynamically loaded libraries.

The supplied command must be a trusted, cooperating child that calls `await_start(stdin)` before job work and exits on error. `spawn` replaces standard streams: stdin carries one startup byte; stdout and stderr go to null. A hidden child first waits on this pipe. The owner assigns it to a private Windows job object before returning a `PendingRunner`. Only `PendingRunner::start` releases the gate. The queue persists the ownership record before that call.

Before assignment, owner death closes the pipe and the cooperating child exits without starting work. After assignment, closing the owner's job handle terminates its contained process, including on an abrupt owner crash. Dropping either runner value stops and reaps its own child. The job admits one active process and no breakaway, so the runner cannot launch an uncontained descendant. Failure to set limits or assign the child aborts startup. Actual supervisor/child tests terminate the supervisor between launch and assignment.

This is containment for trusted engine code, not a filesystem, network or hostile-code sandbox. It cannot control an arbitrary executable that ignores the gate. The public Windows [job limit contract](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information) and [process assignment contract](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject) define the underlying behavior.

## Limits and observations

| Control | Contract |
| --- | --- |
| Lifetime | 1–3,600,000 ms; default 300,000 ms; starts at launch and includes the closed gate |
| Deadline | Dedicated watchdog terminates the owned job even when the caller never polls |
| Committed memory | 64–2,048 MiB; default 512 MiB; enforced by Windows |
| Polling | Nonblocking `poll`, or `wait_slice` bounded to one second |
| Stop | Terminates the owned job without opening a recorded PID for termination |
| Report | Exit code, PID/creation identity, requested stop reason, observed elapsed time and OS peak committed bytes |

`observed_elapsed_ms` runs from launch until the owner first observes exit. It includes startup and may include delay after exit; it is not precise engine runtime. `peak_committed_bytes` measures process commitment, not resident memory. Independent tests attempt an actual 128 MiB commit under 64 MiB and 256 MiB caps and verify rejection/admission and peak. The [extended job information](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information) specifies these measurements. These fixture observations are not the workload benchmarks required by A1/A5.

`stop_requested` records a termination request. It does not establish whether cancellation or deadline expiry preceded successful output publication. The queue reconciles durable publication evidence before reporting a terminal outcome. An already-created output must keep its successful result.

## Ownership and leases

`ProcessIdentity` combines PID and creation time. Read-only `process_state` returns running, not running or unknown. A mismatched creation time treats the old owner as gone even if its PID has been reused; denied/uncertain inspection remains unknown. It never opens a saved PID with termination rights. Creation time follows [GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes).

`FileLease::try_acquire` uses an OS exclusive file lock and returns immediately on contention. Lease files are persistent, empty, regular files; callers must never remove or replace them. The open handle denies deletion. Unrelated contents are rejected and preserved. Process death releases the lock. This is a local trusted-filesystem contract, without a claim about hostile parent-directory replacement or network filesystems. Rust's [file locking API](https://doc.rust-lang.org/std/fs/struct.File.html#method.try_lock) requires Rust 1.89 or later.

## Verification and remaining integration

Rust checks use original synthetic data and owned hidden processes. They cover gate release and rejection, natural exit, cancellation, deadline without polling, dropping pending/running children, supervisor death before/after assignment and during work, descendant rejection, actual memory caps, immutable executable identities, PID/creation mismatches, and lease contention/release. Test instrumentation is compiled only into the Rust test binary. Generated files stay in owned temporary directories; no external application is inspected.

The separate jobs module supplies durable submission, pinned inputs, ownership persistence, progress/status/wait/cancel APIs, startup/shutdown coordination, explicit recovery and publication serialization. This process library alone supplies no queue semantics. Full A4 audit and wider file-writer coverage remain open. Non-Windows spawn/identity entry points explicitly report unsupported; no additional platform acceptance is claimed.
