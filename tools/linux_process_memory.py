"""Linux synchronous command RSS via an isolated, single-threaded supervisor.

Keep this module independent of fixtures: the forked command inherits this small
interpreter's resident image before exec, never the large fixture/oracle image.
wait4 includes that pre-exec footprint and any descendants reaped by the command;
it is not concurrent tree memory, Windows commit, or post-exec-only memory.
"""
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

METHOD = 'linux_wait4_isolated_supervisor_v1'
SCOPE = 'command_lifetime_including_pre_exec_and_reaped_descendant_maximum'


def _parent_death(expected_parent):
    # Linux prctl(2), PR_SET_PDEATHSIG. Check after arming to close the race
    # where the parent disappeared before this process reached prctl.
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                          ctypes.c_ulong, ctypes.c_ulong]
    libc.prctl.restype = ctypes.c_int
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))
    if os.getppid() != expected_parent:
        os._exit(125)


def _supervise(report_path, expected_parent, timeout, argv):
    _parent_death(expected_parent)
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    error_read, error_write = os.pipe2(os.O_CLOEXEC)
    child = None
    exited = False
    reaped = False
    try:
        parent = os.getpid()
        child = os.fork()  # This fresh interpreter has no worker threads.
        if child == 0:
            try:
                os.close(error_read)
                _parent_death(parent)
                # Match Popen's restored SIGPIPE behavior on POSIX.
                for name in ('SIGPIPE', 'SIGXFZ', 'SIGXFSZ'):
                    if hasattr(signal, name):
                        signal.signal(getattr(signal, name), signal.SIG_DFL)
                os.execvpe(argv[0], argv, os.environ)
            except BaseException as error:
                message = dict(errno=getattr(error, 'errno', None),
                               error=f'{type(error).__name__}: {error}')
                os.write(error_write, json.dumps(message).encode()[:4000])
                os._exit(127)
        os.close(error_write)
        error_write = None
        # Observe exit without consuming the child or its resource counters.
        # Even a zombie retains its PID until our one wait4 reaps it. This also
        # works with Python builds that do not expose pidfd_open.
        deadline = time.monotonic() + timeout
        while not os.waitid(os.P_PID, child, os.WEXITED | os.WNOWAIT | os.WNOHANG):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(.001, remaining))
        else:
            exited = True
        timed_out = not exited
        if timed_out:
            os.kill(child, signal.SIGKILL)
            os.waitid(os.P_PID, child, os.WEXITED | os.WNOWAIT)
            exited = True
        waited, status, usage = os.wait4(child, 0)
        reaped = True
        if waited != child:
            raise RuntimeError('wait4 returned an unrelated process')
        error = os.read(error_read, 4096)
        result = dict(schema_version=1, supervisor_pid=parent,
                      exit_code=os.waitstatus_to_exitcode(status), timed_out=timed_out,
                      peak_resident_bytes=int(usage.ru_maxrss) * 1024)
        if error:
            result['launch_error'] = json.loads(error)
        with open(report_path, 'x', encoding='utf-8') as output:
            json.dump(result, output)
    finally:
        if child and not reaped:
            if not exited:
                # SIGCHLD is default and nothing reaps before exited is set.
                # The PID therefore still names this exclusively owned child.
                os.kill(child, signal.SIGKILL)
            try:
                os.wait4(child, 0)
            except ChildProcessError:
                pass
        for fd in (error_read, error_write):
            if fd is not None:
                os.close(fd)


def run(argv, payload, timeout):
    """Return the ordinary workload tuple; never fill Windows counters with RSS."""
    if sys.platform != 'linux':
        raise RuntimeError('The RSS supervisor is Linux-only')
    if not argv or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('A command and positive finite deadline are required')
    script = Path(__file__).resolve()
    source_hash = hashlib.sha256(script.read_bytes()).hexdigest()
    start = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='inkbolt-rss-') as directory:
        report = Path(directory) / 'result.json'
        command = [sys.executable, '-I', '-S', str(script), str(report), str(os.getpid()),
                   str(timeout), *map(os.fspath, argv)]
        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE) as process:
            try:
                stdout, stderr = process.communicate(payload, timeout=timeout + 10)
            except BaseException:
                process.kill()  # Kernel parent-death signal also stops its child.
                process.communicate(timeout=10)
                raise
            if process.returncode != 0 or not report.is_file():
                raise RuntimeError(f'Linux memory supervisor failed ({process.returncode}); '
                                   f'no valid measurement: {stderr[-4096:]!r}')
            result = json.loads(report.read_bytes())
            if result.get('schema_version') != 1 or result.get('supervisor_pid') != process.pid:
                raise RuntimeError('Invalid Linux memory supervisor identity')
            if 'launch_error' in result:
                error = result['launch_error']
                raise OSError(error['errno'], error['error'])
            peak = result['peak_resident_bytes']
            resident = dict(available=type(peak) is int and peak > 0,
                            method=METHOD, scope=SCOPE,
                            supervisor_sha256=source_hash,
                            peak_resident_bytes=peak if type(peak) is int and peak > 0 else None)
            if not resident['available']:
                resident['reason'] = 'wait4 returned no positive lifetime RSS'
            memory = dict(available=False,
                          reason='Windows working-set/commit counters unavailable; see resident',
                          resident=resident)
            return dict(exit_code=result['exit_code'], seconds=time.perf_counter()-start,
                        timed_out=result['timed_out'], memory=memory), stdout, stderr


if __name__ == '__main__':
    _supervise(sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), sys.argv[4:])
