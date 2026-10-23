"""Linux command/server RSS via an isolated, single-threaded supervisor.

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
import select
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


def _supervise(report_path, expected_parent, timeout, argv, control_fd=None):
    _parent_death(expected_parent)
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    if control_fd is not None:
        os.set_inheritable(control_fd, False)
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
                if control_fd is not None:
                    os.close(control_fd)
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
        deadline = None if timeout is None else time.monotonic() + timeout
        stopped = False
        while not os.waitid(os.P_PID, child, os.WEXITED | os.WNOWAIT | os.WNOHANG):
            remaining = .001 if deadline is None else deadline - time.monotonic()
            if remaining <= 0:
                break
            interval = min(.001, remaining)
            if control_fd is None:
                time.sleep(interval)
            elif select.select([control_fd], [], [], interval)[0]:
                if os.read(control_fd, 1) not in (b'K', b''):
                    raise ValueError('Invalid supervisor control byte')
                stopped = True
                break
        else:
            exited = True
        timed_out = not exited and not stopped
        if not exited:
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
        for fd in (error_read, error_write, control_fd):
            if fd is not None:
                os.close(fd)


def _result(report, process, source_hash):
    if process.returncode != 0 or not report.is_file():
        raise RuntimeError(f'Linux memory supervisor failed ({process.returncode}); no valid measurement')
    result = json.loads(report.read_bytes())
    if result.get('schema_version') != 1 or result.get('supervisor_pid') != process.pid:
        raise RuntimeError('Invalid Linux memory supervisor identity')
    if 'launch_error' in result:
        error = result['launch_error']
        raise OSError(error['errno'], error['error'])
    peak = result['peak_resident_bytes']
    resident = dict(available=type(peak) is int and peak > 0, method=METHOD, scope=SCOPE,
                    supervisor_sha256=source_hash,
                    peak_resident_bytes=peak if type(peak) is int and peak > 0 else None)
    if not resident['available']:
        resident['reason'] = 'wait4 returned no positive lifetime RSS'
    result['memory'] = dict(available=False,
        reason='Windows working-set/commit counters unavailable; see resident', resident=resident)
    return result


class Process:
    """Owned streaming process for benchmark MCP; explicitly close after use.

    Only the small Popen surface needed by the benchmark is exposed. A control
    pipe requests termination without destroying the supervisor's wait4 record.
    The pipe works even before the supervisor has finished starting.
    """
    def __init__(self, argv, *, stdin, stdout, stderr, creationflags=0):
        if sys.platform != 'linux' or creationflags or not argv:
            raise ValueError('Expected a Linux command without Windows creation flags')
        script = Path(__file__).resolve()
        self.source_hash = hashlib.sha256(script.read_bytes()).hexdigest()
        self.directory = tempfile.TemporaryDirectory(prefix='inkbolt-mcp-rss-')
        self.report = Path(self.directory.name)/'result.json'
        self.result = None
        self.closed = False
        self.stop_requested = False
        self.control = None
        read_fd = None
        try:
            read_fd, self.control = os.pipe2(os.O_CLOEXEC)
            self.process = subprocess.Popen([sys.executable, '-I', '-S', str(script),
                '--persistent', str(self.report), str(os.getpid()), str(read_fd), *map(os.fspath, argv)],
                stdin=stdin, stdout=stdout, stderr=stderr, pass_fds=(read_fd,))
        except BaseException:
            if self.control is not None:
                os.close(self.control)
            self.control = None
            self.directory.cleanup()
            raise
        finally:
            if read_fd is not None:
                os.close(read_fd)
        self.stdin, self.stdout, self.stderr = self.process.stdin, self.process.stdout, self.process.stderr

    @property
    def returncode(self):
        return self.result['exit_code'] if self.result is not None else None

    def wait(self, timeout=None):
        self.process.wait(timeout=timeout)
        if self.result is None:
            self.result = _result(self.report, self.process, self.source_hash)
        return self.returncode

    def memory(self):
        if self.result is None:
            raise RuntimeError('Wait for the complete server lifetime before reading RSS')
        return self.result['memory']

    def kill(self):
        if not self.closed and not self.stop_requested:
            self.stop_requested = True
            try:
                os.write(self.control, b'K')
            except BrokenPipeError:
                pass  # Already exited; wait still validates its final record.

    def close(self):
        if self.closed:
            return
        try:
            self.kill()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()  # Parent-death signal stops its command.
                self.process.wait(timeout=10)
        finally:
            self.closed = True
            os.close(self.control)
            for pipe in (self.stdin, self.stdout, self.stderr):
                if pipe is not None:
                    pipe.close()
            self.directory.cleanup()


def resident_summary(observations):
    """Summarize one consistent counter contract; incomplete data stays unknown."""
    residents = [(value or {}).get('resident', {}) for value in observations]
    complete = bool(residents) and all(value.get('available') is True and
        value.get('method') == METHOD and value.get('scope') == SCOPE and
        type(value.get('peak_resident_bytes')) is int and value['peak_resident_bytes'] > 0 and
        isinstance(value.get('supervisor_sha256'), str) and len(value['supervisor_sha256']) == 64
        and all(c in '0123456789abcdef' for c in value['supervisor_sha256'])
        for value in residents)
    complete = complete and len({value['supervisor_sha256'] for value in residents}) == 1
    return dict(resident_memory_complete=complete,
        peak_resident_bytes=max(value['peak_resident_bytes'] for value in residents) if complete else None,
        resident_memory_method=METHOD if complete else None,
        resident_memory_scope=SCOPE if complete else None,
        resident_supervisor_sha256=residents[0]['supervisor_sha256'] if complete else None)


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
            result = _result(report, process, source_hash)
            return dict(exit_code=result['exit_code'], seconds=time.perf_counter()-start,
                        timed_out=result['timed_out'], memory=result['memory']), stdout, stderr


if __name__ == '__main__':
    if sys.argv[1] == '--persistent':
        _supervise(sys.argv[2], int(sys.argv[3]), None, sys.argv[5:], control_fd=int(sys.argv[4]))
    else:
        _supervise(sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), sys.argv[4:])
