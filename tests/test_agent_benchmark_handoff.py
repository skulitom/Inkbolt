"""Handoff evidence fails closed; consumer memory includes short-lived children."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_cli import EXE,ROOT
sys.path.insert(0,str(ROOT/'tools'))
from agent_benchmark import run_task
from benchmark_consumer import tree_command,tool_identities
from benchmark_handoff import check_timestamps,consumer_rgba,over_black
from benchmark_runtime import TaskFailure
from verify_process import WindowsJob


class HandoffBenchmarkTests(unittest.TestCase):
    def test_missing_external_tools_remain_a_failed_full_task(self):
        with tempfile.TemporaryDirectory() as directory:
            row=run_task(EXE,Path(directory)/'missing','B20',1,'cli')
            self.assertEqual(row['status'],'failed')
            self.assertIn('explicit --cutbolt',row['error'])
            self.assertTrue(row['missing_checks'])
            self.assertEqual(row['engine_commands'],0)
            self.assertIsNone(row['consumer'])
            self.assertFalse(row['model_trials'])
        with self.assertRaises(TaskFailure):tool_identities(dict(cutbolt=EXE))

    def test_independent_alpha_endpoints_quantization_and_clock_rejections(self):
        raw=bytes([200,80,30,128,10,220,70,255,45,23,88,0,77,33,22,64])
        expected=bytes([199,80,30,128,10,220,70,255,0,0,0,0,76,32,24,64])
        self.assertEqual(consumer_rgba(raw),expected)
        self.assertEqual(over_black(expected),bytes([100,40,15,255,10,220,70,255,0,0,0,255,19,8,6,255]))
        check_timestamps(dict(frames=[dict(best_effort_timestamp_time=str(i/25)) for i in range(10)]),10)
        for value in [dict(frames=[]),dict(frames=[dict(best_effort_timestamp_time='0.05')])]:
            with self.assertRaises(TaskFailure):check_timestamps(value,1)

    def test_kernel_peak_includes_a_short_lived_child_and_timeout_cleans_the_owned_tree(self):
        child="value=bytearray(64*1024*1024);print(len(value))"
        script="import json,sys,subprocess;child=json.load(sys.stdin);result=subprocess.run([sys.executable,'-c',child],check=True,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW);sys.stdout.buffer.write(result.stdout)"
        result,stdout,stderr=tree_command([sys.executable,'-c',script],json.dumps(child).encode(),os.environ.copy(),10)
        self.assertEqual((result['exit_code'],stderr),(0,b''))
        self.assertEqual(stdout.strip(),b'67108864')
        self.assertTrue(result['memory_available'])
        self.assertGreaterEqual(result['processes'],2)
        self.assertEqual(result['active_processes'],0)
        self.assertGreater(result['peak_process_commit_bytes'],64*1024*1024)
        self.assertGreaterEqual(result['peak_tree_commit_bytes'],result['peak_process_commit_bytes'])
        result,_,_=tree_command([sys.executable,'-c',script],json.dumps('import time;time.sleep(60)').encode(),os.environ.copy(),.3)
        self.assertTrue(result['timed_out']);self.assertFalse(result['memory_available'])
        self.assertNotEqual(result['exit_code'],0)

    def test_failed_assignment_kills_the_unassigned_owned_caller(self):
        with patch.object(WindowsJob,'assign',side_effect=RuntimeError('injected assignment failure')):
            result,_,_=tree_command([sys.executable,'-c','import sys;sys.stdin.read()'],b'{}',os.environ.copy(),5)
        self.assertFalse(result['memory_available'])
        self.assertIn('injected assignment failure',result['observation_error'])
        self.assertNotEqual(result['exit_code'],0)


if __name__=='__main__':unittest.main()
