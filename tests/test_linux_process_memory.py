"""Independent Linux lifetime-RSS, transport and owned-process cleanup checks."""
import os
import copy
import errno
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

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

    def stream(self, script):
        process = memory.Process([sys.executable, '-c', script], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(process.close)
        return process

    def test_streaming_lifetime_covers_multiple_exchanges_and_freed_peak(self):
        process = self.stream('import sys\nfor line in sys.stdin:\n'
            ' if line.strip()=="allocate":\n  a=bytearray(64*1024*1024)\n  del a\n'
            ' print("ack:"+line.strip(),flush=True)\n')
        directory = Path(process.directory.name)
        with self.assertRaises(RuntimeError):
            process.memory()
        for line in (b'first', b'allocate', b'last'):
            process.stdin.write(line+b'\n');process.stdin.flush()
            self.assertEqual(process.stdout.readline(), b'ack:'+line+b'\n')
        process.stdin.close()
        self.assertEqual(process.wait(timeout=5), 0)
        self.assertFalse(process.result['timed_out'])
        self.assertGreater(self.peak(dict(memory=process.memory())), 60*1024*1024)
        self.assertEqual(process.stderr.read(), b'')
        observed = copy.deepcopy(process.memory())
        self.assertEqual(process.wait(timeout=1), 0)
        process.close();process.close()
        self.assertFalse(directory.exists())
        self.assertEqual(process.memory(), observed)

    def test_stream_stop_before_startup_still_reaps_and_records_memory(self):
        for _ in range(3):
            process = self.stream('import time; time.sleep(30)')
            process.kill();process.kill()
            self.assertEqual(process.wait(timeout=5), -signal.SIGKILL)
            self.assertFalse(process.result['timed_out'])
            self.peak(dict(memory=process.memory()))
            process.close()

    def test_stream_failed_exec_and_lost_supervisor_are_not_successful_measurements(self):
        process = memory.Process(['/inkbolt-nonexistent-stream'], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(process.close)
        with self.assertRaises(FileNotFoundError):
            process.wait(timeout=5)
        with self.assertRaises(RuntimeError):
            process.memory()
        process.close()
        self.assertFalse(Path(process.directory.name).exists())
        process = self.stream('import os,time; print(os.getpid(),flush=True); time.sleep(30)')
        pid = int(process.stdout.readline())
        process.process.kill()
        with self.assertRaises(RuntimeError):
            process.wait(timeout=5)
        self.assertEqual(process.stdout.read(), b'')
        with self.assertRaises(RuntimeError):
            process.memory()
        deadline = time.monotonic()+2
        while time.monotonic() < deadline:
            try:
                if '\nState:\tZ' in Path(f'/proc/{pid}/status').read_text():
                    break
            except FileNotFoundError:
                break
            time.sleep(.01)
        else:
            self.fail('Owned command survived a failed supervisor')

    def test_stream_constructor_failure_releases_private_directory_and_descriptors(self):
        make_directory = tempfile.TemporaryDirectory
        with make_directory() as root:
            def owned_directory(**kwargs):
                return make_directory(dir=root, **kwargs)
            before = len(list(Path('/proc/self/fd').iterdir()))
            for target in ('os.pipe2', 'subprocess.Popen'):
                with patch('linux_process_memory.tempfile.TemporaryDirectory', side_effect=owned_directory), \
                     patch('linux_process_memory.'+target, side_effect=OSError(errno.EMFILE, 'fixture fd exhaustion')):
                    with self.assertRaises(OSError):
                        memory.Process([sys.executable], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.assertEqual(list(Path(root).iterdir()), [])
                self.assertEqual(len(list(Path('/proc/self/fd').iterdir())), before)


class ResidentSummaryTests(unittest.TestCase):
    def test_complete_consistent_lifetimes_use_maximum_without_windows_counters(self):
        counter = dict(available=True, method=memory.METHOD, scope=memory.SCOPE,
                       supervisor_sha256='a'*64, peak_resident_bytes=100)
        observations = [dict(available=False, resident=counter),
                        dict(available=False, resident=dict(counter, peak_resident_bytes=300))]
        summary = memory.resident_summary(observations)
        self.assertTrue(summary['resident_memory_complete'])
        self.assertEqual(summary['peak_resident_bytes'], 300)
        self.assertNotIn('peak_commit_bytes', summary)

    def test_missing_invalid_or_mixed_measurement_contracts_remain_unknown(self):
        counter = dict(available=True, method=memory.METHOD, scope=memory.SCOPE,
                       supervisor_sha256='a'*64, peak_resident_bytes=100)
        for field, value in [('available', False), ('available', 1), ('method', 'sampled'),
                             ('scope', 'tree_sum'), ('supervisor_sha256', 'b'*64),
                             ('supervisor_sha256', 'z'*64), ('peak_resident_bytes', 0),
                             ('peak_resident_bytes', True), ('peak_resident_bytes', -1)]:
            with self.subTest(field=field, value=value):
                summary = memory.resident_summary([dict(resident=counter), dict(resident=dict(counter, **{field:value}))])
                self.assertFalse(summary['resident_memory_complete'])
                self.assertIsNone(summary['peak_resident_bytes'])
        for observations in ([], [None], [dict(resident=counter), {}]):
            self.assertFalse(memory.resident_summary(observations)['resident_memory_complete'])


if __name__ == '__main__':
    unittest.main()
