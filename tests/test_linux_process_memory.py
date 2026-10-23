"""Independent Linux lifetime-RSS, transport and owned-process cleanup checks."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import linux_process_memory as memory


@unittest.skipUnless(sys.platform == 'linux', 'Linux wait4 backend')
class LinuxProcessMemoryTests(unittest.TestCase):
    def run_python(self, script, payload=b'', timeout=10):
        return memory.run([sys.executable, '-c', script], payload, timeout)

    def peak(self, result):
        counters = result['memory']
        self.assertFalse(counters['available'])  # Never manufacture Windows commit.
        self.assertNotIn('peak_commit_bytes', counters)
        resident = counters['resident']
        self.assertTrue(resident['available'], resident)
        self.assertEqual(resident['method'], memory.METHOD)
        self.assertEqual(resident['scope'], memory.SCOPE)
        self.assertEqual(len(resident['supervisor_sha256']), 64)
        self.assertGreater(resident['peak_resident_bytes'], 0)
        return resident['peak_resident_bytes']

    def test_freed_allocation_peak_survives_exit_without_parent_or_previous_peak(self):
        fixture = bytearray(128 * 1024 * 1024)
        base, _, _ = self.run_python('print("base")')
        full, stdout, stderr = self.run_python('a=bytearray(64*1024*1024); del a; print("ok")')
        later, _, _ = self.run_python('print("later")')
        self.assertEqual((full['exit_code'], stdout, stderr), (0, b'ok\n', b''))
        self.assertGreater(self.peak(full), self.peak(base) + 48*1024*1024)
        self.assertLess(self.peak(base), len(fixture) // 2)
        self.assertLess(self.peak(later), self.peak(full) - 48*1024*1024)

    def test_unrelated_child_is_not_reaped_or_charged(self):
        with subprocess.Popen([sys.executable, '-c',
                               'import time; a=bytearray(96*1024*1024); print("ready",flush=True); time.sleep(20)'],
                              stdout=subprocess.PIPE) as unrelated:
            try:
                self.assertEqual(unrelated.stdout.readline(), b'ready\n')
                result, _, _ = self.run_python('pass')
                self.assertLess(self.peak(result), 48*1024*1024)
                self.assertIsNone(unrelated.poll())
            finally:
                unrelated.kill()
                unrelated.wait(timeout=5)

    def test_reaped_descendant_peak_is_declared_not_tree_sum(self):
        result, _, _ = self.run_python(
            'import subprocess,sys; subprocess.run([sys.executable,"-c","a=bytearray(64*1024*1024)"])')
        self.assertGreater(self.peak(result), 60*1024*1024)

    def test_input_output_and_error_pipe_pressure_remain_exact(self):
        payload = bytes(range(256)) * 2048
        script = ('import sys; sys.stderr.buffer.write(b"e"*262144); sys.stderr.flush(); '
                  'sys.stdout.buffer.write(b"o"*262144); sys.stdout.flush(); '
                  'sys.stdout.buffer.write(sys.stdin.buffer.read())')
        result, stdout, stderr = self.run_python(script, payload)
        self.assertEqual(result['exit_code'], 0)
        self.assertFalse(result['timed_out'])
        self.assertEqual(stdout, b'o'*262144 + payload)
        self.assertEqual(stderr, b'e'*262144)
        self.peak(result)

    def test_nonzero_signal_and_failed_exec_are_distinct(self):
        result, _, _ = self.run_python('raise SystemExit(127)')
        self.assertEqual(result['exit_code'], 127)
        self.assertFalse(result['timed_out'])
        result, _, _ = self.run_python('import os,signal; os.kill(os.getpid(), signal.SIGTERM)')
        self.assertEqual(result['exit_code'], -signal.SIGTERM)
        with self.assertRaises(FileNotFoundError):
            memory.run(['/inkbolt-nonexistent-command'], b'', 2)
        for _ in range(5):
            with self.assertRaises(PermissionError):
                memory.run(['/'], b'', 2)

    def test_timeout_reaps_child_and_preserves_enclosing_process_group(self):
        result, stdout, _ = self.run_python(
            'import os,time; print(os.getpid(),os.getpgrp(),flush=True); time.sleep(20)', timeout=.3)
        pid, group = map(int, stdout.split())
        self.assertEqual(group, os.getpgrp())
        self.assertTrue(result['timed_out'])
        self.assertEqual(result['exit_code'], -signal.SIGKILL)
        self.assertLess(result['seconds'], 5)
        self.assertFalse(Path(f'/proc/{pid}').exists())
        self.peak(result)

    def test_killed_supervisor_does_not_leave_running_command(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'result.json'
            command = [sys.executable, '-I', '-S', str(Path(memory.__file__).resolve()),
                       str(report), str(os.getpid()), '20', sys.executable, '-c',
                       'import os,time; print(os.getpid(),flush=True); time.sleep(20)']
            with subprocess.Popen(command, stdout=subprocess.PIPE) as supervisor:
                pid = int(supervisor.stdout.readline())
                supervisor.kill()
                supervisor.wait(timeout=5)
                self.assertEqual(supervisor.stdout.read(), b'')
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    try:
                        status = Path(f'/proc/{pid}/status').read_text()
                    except FileNotFoundError:
                        break
                    if '\nState:\tZ' in status:
                        break  # Dead; init owns reaping after supervisor death.
                    time.sleep(.01)
                else:
                    self.fail('Owned command survived its supervisor')
            self.assertFalse(report.exists())


if __name__ == '__main__':
    unittest.main()
