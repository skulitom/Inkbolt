"""Release-compatible recovery faults, complete process accounting and cleanup."""
import ctypes
from ctypes import wintypes as w
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_cli import EXE, ROOT
sys.path.insert(0,str(ROOT/'tools'))
from agent_benchmark import run_task
from benchmark_recovery_runtime import RecoveryTrial,process_ids
from benchmark_runtime import TaskFailure
from benchmark_tasks import CHECKS


class RecoveryBenchmarkTests(unittest.TestCase):
    def test_exited_command_identity_survives_until_the_trial_closes(self):
        with tempfile.TemporaryDirectory() as directory:
            trial=RecoveryTrial(EXE,Path(directory)/'case','B19',1,'cli',[])
            try:
                trial.begin('Retain a measured command during an exit-list observation')
                trial.call('catalog','preset.list')
                trial.stop.set();trial.observer.join(timeout=2)
                process=trial.frontend_processes[0]
                self.assertEqual(process.poll(),0)
                self.assertFalse(process._handle.closed)
                def inventory(handle,kind,buffer,length,returned):
                    self.assertEqual(kind,3)
                    header=ctypes.cast(buffer,ctypes.POINTER(w.DWORD));header[0]=header[1]=1
                    ctypes.cast(ctypes.byref(buffer._obj,8),ctypes.POINTER(ctypes.c_size_t))[0]=process.pid
                    return True
                with patch.object(trial.api,'QueryInformationJobObject',side_effect=inventory),patch.object(
                        trial.api,'QueryFullProcessImageNameW',side_effect=AssertionError('Exited caller image queried')):
                    trial.capture_members()
                self.assertEqual(trial.workers,{})
                self.assertEqual(trial.finish()['status'],'passed')
                self.assertTrue(process._handle.closed)
            finally:trial.close()

    def test_incomplete_process_lists_are_requeried_without_waiving_coverage_or_bounds(self):
        def query(rows):
            iterator=iter(rows)
            def call(entries):
                success,error,assigned,pids=next(iterator)
                header=ctypes.cast(entries,ctypes.POINTER(w.DWORD))
                header[0]=assigned;header[1]=len(pids)
                values=ctypes.cast(ctypes.byref(entries,8),ctypes.POINTER(ctypes.c_size_t))
                for index,pid in enumerate(pids):values[index]=pid
                return success,error
            return call
        for first in [(True,0,2,[10]),(True,0,1,[10,20]),(False,234,2,[10])]:
            events=[]
            result=process_ids(query([first,(True,0,2,[10,20])]),lambda kind,**data:events.append((kind,data)))
            self.assertEqual(result,[10,20]);self.assertEqual(len(events),1)
            self.assertEqual(events[0][0],'inventory-retry')
        for rows,message in [([(True,0,257,[])],'bound'),([(False,5,0,[])],'enumerate'),
                             ([(True,0,2,[10])]*4,'complete observation')]:
            with self.subTest(rows=rows),self.assertRaisesRegex(RuntimeError,message):
                process_ids(query(rows),lambda *args,**kw:None)

    def test_active_cancel_crash_restart_and_replay_on_both_transports(self):
        with tempfile.TemporaryDirectory() as directory:
            for transport in ('cli','mcp'):
                with self.subTest(transport=transport):
                    root=Path(directory)/transport
                    row=run_task(EXE,root,'B19',1,transport)
                    self.assertEqual(row['status'],'passed',json.dumps(row,indent=2))
                    self.assertEqual(set(c['name'] for c in row['checks']),set(CHECKS['B19'])|{'source-preservation'})
                    self.assertEqual(row['request_bytes'],sum(p.stat().st_size for p in root.glob('*.request.json')))
                    self.assertEqual(row['response_bytes'],sum(p.stat().st_size for p in root.glob('*.response.json')))
                    self.assertTrue(row['memory_complete']);self.assertGreater(row['peak_commit_bytes'],0)
                    self.assertGreater(row['first_verified_preview_seconds'],0)
                    self.assertEqual(row['process_tree']['active'],0)
                    self.assertEqual(row['process_tree']['total'],row['process_calls']+len(row['background_processes']))
                    self.assertEqual(sum(p['role']=='runner' for p in row['background_processes']),3)
                    evidence=json.loads((root/'recovery-evidence.json').read_bytes())
                    self.assertEqual(sum(e['kind']=='fault-boundary' for e in evidence['events']),2)
                    self.assertEqual(sum(e['kind']=='interrupted-tree-exited' for e in evidence['events']),1)
                    self.assertFalse(row['model_trials']);self.assertIsNone(row['token_usage'])

    def test_foreign_process_and_reused_pid_are_never_fault_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            trial=RecoveryTrial(EXE,Path(directory)/'case','B19',1,'mcp',[])
            trial.begin('Verify exact process ownership')
            outsider=subprocess.Popen([str(EXE)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                      creationflags=subprocess.DETACHED_PROCESS)
            try:
                values=[w.FILETIME() for _ in range(4)]
                self.assertTrue(trial.api.GetProcessTimes(int(outsider._handle),*(ctypes.byref(v) for v in values)))
                created=(values[0].dwHighDateTime<<32)|values[0].dwLowDateTime
                with self.assertRaisesRegex(TaskFailure,'PID was reused'):
                    trial.capture(dict(pid=outsider.pid,created=created+1),'runner')
                with self.assertRaisesRegex(TaskFailure,'outside the owned process tree'):
                    trial.capture(dict(pid=outsider.pid,created=created),'runner')
                self.assertIsNone(outsider.poll())
                trial.call('catalog','preset.list')
                self.assertEqual(trial.finish()['status'],'passed')
                self.assertIsNone(outsider.poll())
            finally:
                trial.close();outsider.kill();outsider.communicate(timeout=5)

    def test_failure_cleanup_stops_only_its_owned_tree_and_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            trial=RecoveryTrial(EXE,Path(directory)/'case','B19',1,'cli',[])
            trial.begin('Force an unfinished owned transport')
            process=trial.spawn([str(EXE)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                row=trial.finish()
                self.assertEqual(row['status'],'failed')
                self.assertIn('leaked',row['error'])
                self.assertEqual(process.wait(timeout=5),125)
                self.assertFalse(row['memory_complete'])
            finally:
                trial.close();process.communicate(timeout=5)


if __name__=='__main__':unittest.main()
