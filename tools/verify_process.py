"""Run one verification command in an owned process tree with a deadline."""
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


MEMORY_SCOPE = 'owned_command_tree_including_launcher'
MEMORY_METHOD = 'windows_job_lifetime_commit_peaks'


def unavailable_memory(reason, method=None):
    return dict(available=False, scope=MEMORY_SCOPE, method=method,
                peak_process_commit_bytes=None, peak_job_commit_bytes=None, reason=reason)


class WindowsJob:
    """The launcher waits for stdin until it belongs to this kill-on-close job."""
    def __init__(self):
        from ctypes import wintypes as w

        class Basic(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                        ('flags', w.DWORD), ('min_working_set', ctypes.c_size_t),
                        ('max_working_set', ctypes.c_size_t), ('active', w.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]

        class Limits(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', ctypes.c_uint64 * 6),
                        ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                        ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]

        self.limits_type = Limits
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        self.api.CreateJobObjectW.restype = w.HANDLE
        self.api.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        self.api.SetInformationJobObject.restype = w.BOOL
        self.api.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.api.AssignProcessToJobObject.restype = w.BOOL
        self.api.CloseHandle.argtypes = [w.HANDLE]
        self.api.CloseHandle.restype = w.BOOL
        self.api.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
        self.api.TerminateJobObject.restype = w.BOOL
        self.api.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p]
        self.api.QueryInformationJobObject.restype = w.BOOL
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Limits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, process):
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def memory(self):
        limits = self.limits_type()
        if not self.api.QueryInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits), None):
            return unavailable_memory('Windows job memory query failed', MEMORY_METHOD)
        if not limits.peak_process or not limits.peak_job:
            return unavailable_memory('Windows job memory peaks were not recorded', MEMORY_METHOD)
        return dict(available=True, scope=MEMORY_SCOPE, method=MEMORY_METHOD,
                    peak_process_commit_bytes=limits.peak_process,
                    peak_job_commit_bytes=limits.peak_job, reason=None)

    def close(self, observe_memory=False):
        memory = unavailable_memory('Owned process cleanup was not observed complete', MEMORY_METHOD)
        if self.handle:
            # Closing a job requests termination but does not wait for every
            # descendant's executable handle to close. Observe the owned job's
            # active count before returning to the caller's file cleanup.
            accounting = (ctypes.c_uint64 * 6)()
            try:
                self.api.TerminateJobObject(self.handle, 125)
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    if not self.api.QueryInformationJobObject(self.handle, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None):
                        break
                    active = ctypes.cast(ctypes.byref(accounting, 40), ctypes.POINTER(ctypes.c_uint32))[0]
                    if active == 0:
                        if observe_memory:
                            # Read lifetime peaks before releasing the job. Its
                            # children may all have exited between observations.
                            memory = self.memory()
                        break
                    time.sleep(.01)
            finally:
                self.api.CloseHandle(self.handle)
                self.handle = None
        return memory if observe_memory else None


def run(argv, root, timeout=None, env=None, observe_memory=False):
    """Return captured output/status; timeout never grants a passing result.

    Close the entire owned tree even on ordinary completion (fixtures must clean
    up their own persistent workers). No process lookup or name-based killing.
    Optional memory covers the whole command tree, including this Python launcher
    and client, through cleanup. It is not an engine-only or resident-set metric.
    """
    started = time.monotonic()
    if timeout is not None and timeout <= 0:
        result = dict(status='deferred', seconds=0, output='', exit_code=None)
        if observe_memory:
            result['memory'] = unavailable_memory('Command was not started')
        return result
    job = WindowsJob() if os.name == 'nt' else None
    memory = unavailable_memory('Owned process tree commit peaks are unavailable on this platform')
    process = None
    with tempfile.TemporaryFile() as output:
        try:
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--child'],
                                       cwd=root, env=env, stdin=subprocess.PIPE, stdout=output,
                                       stderr=subprocess.STDOUT, start_new_session=os.name != 'nt',
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if job:
                job.assign(process)
            process.stdin.write(json.dumps(argv).encode('utf-8'))
            process.stdin.close()
            try:
                code = process.wait(timeout=max(.001, timeout - (time.monotonic() - started)) if timeout is not None else None)
                status = 'passed' if code == 0 else 'failed'
            except subprocess.TimeoutExpired:
                status, code = 'deferred', None
        finally:
            if job:
                memory = job.close(observe_memory=observe_memory)
            elif process:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if process:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                if process.stdin and not process.stdin.closed:
                    process.stdin.close()
        output.seek(0)
        result = dict(status=status, exit_code=code, seconds=time.monotonic() - started,
                      output=output.read().decode('utf-8', 'replace'))
        if observe_memory:
            result['memory'] = memory
        return result


if __name__ == '__main__':
    if sys.argv[1:] != ['--child']:
        raise SystemExit('Internal verification launcher')
    command = json.loads(sys.stdin.buffer.read())
    raise SystemExit(subprocess.call(command))
