"""Release-compatible recovery faults, complete process accounting and cleanup."""
import ctypes
import copy
from contextlib import closing
from ctypes import wintypes as w
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_cli import EXE, ROOT
from platform_support import require_capability
sys.path.insert(0,str(ROOT/'tools'))
from agent_benchmark import run_task
from benchmark_recovery_runtime import RecoveryTrial,process_ids
from benchmark_runtime import TaskFailure
from benchmark_recovery import fixture,solve,durable_inputs,judge_retained,terminal,PROMPT
from benchmark_tasks import CHECKS
from workload_cases import sha


class RecoveryBenchmarkTests(unittest.TestCase):
    def setUp(self):
        require_capability(self, "jobs")

    def test_busy_wait_retries_the_same_observation_and_counts_both_responses(self):
        with tempfile.TemporaryDirectory() as directory:
            for transport in ('cli','mcp'):
                with self.subTest(transport=transport):
                    case=RecoveryTrial(EXE,Path(directory)/transport,'B19',1,transport,[])
                    try:
                        case.begin('Observe a cancelled job while its queue is briefly locked')
                        doc=case.call('create','document.create',id='sample',kind='vector',width=8,height=8)
                        with case.blocked_queue():
                            case.call('start','job.start',request_id='sample',document=doc,
                                      output=dict(file_name='sample.png',format='png'))
                            case.call('cancel','job.cancel',request_id='sample')
                        with closing(sqlite3.connect(case.ledger)) as writer:
                            writer.execute('BEGIN EXCLUSIVE')
                            def wait(step,request_id,retry_of):
                                try:
                                    return case.call(step,'job.wait',request_id=request_id,wait_ms=1000,
                                                     retry_of=retry_of,allow_busy_wait=True)
                                finally:
                                    writer.rollback()
                            self.assertEqual(terminal(wait,'sample','cancelled')['state'],'cancelled')
                        busy,observed=case.calls[-2:]
                        self.assertEqual((busy['status'],busy['engine_error']['code']),('expected_error','JOB_BUSY'))
                        self.assertEqual((observed['status'],observed['retry_of']),('success',busy['step']))
                        self.assertEqual(busy['request_sha256'],observed['request_sha256'])
                        self.assertTrue(all(r['response_bytes']>0 for r in (busy,observed)))
                        self.assertEqual(case.finish()['retries'],1)
                        self.assertFalse((case.root/'sample.png').exists())
                    finally:
                        case.close()

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
                    self.assertTrue(row['judge_separated']);self.assertEqual(row['judge_engine_commands'],12)
                    self.assertEqual(row['request_bytes']+row['judge_request_bytes'],sum(p.stat().st_size for p in root.glob('*.request.json')))
                    self.assertEqual(row['response_bytes']+row['judge_response_bytes'],sum(p.stat().st_size for p in root.glob('*.response.json')))
                    self.assertTrue(row['memory_complete']);self.assertGreater(row['peak_commit_bytes'],0)
                    self.assertGreater(row['first_verified_preview_seconds'],0)
                    self.assertEqual(row['process_tree']['active'],0)
                    self.assertEqual(row['process_tree']['total'],row['process_calls']+len(row['background_processes'])+
                        (row['judge_engine_commands'] if transport=='cli' else 0))
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

    def test_retained_judge_accepts_defaults_but_rejects_changed_source_and_stores(self):
        with tempfile.TemporaryDirectory() as directory:
            case=RecoveryTrial(EXE,Path(directory)/'case','B19',1,'cli',CHECKS['B19'])
            try:
                fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));solve(case);case.begin_judging()
                inputs=durable_inputs(case);path=case.root/'editable.json';original=path.read_bytes()
                for fault in ('none','missing-revision','stale-revision','resolution','artwork','resource-binding'):
                    with self.subTest(fault=fault):
                        value=json.loads(original);del value['resolution_ppi']
                        if fault=='missing-revision':del value['revision']
                        elif fault=='stale-revision':value['revision']=0
                        elif fault=='resolution':value['resolution_ppi']=72
                        elif fault=='artwork':value['items'][0]['transform'][4]=1
                        path.write_text(json.dumps(value),encoding='utf-8')
                        changed=copy.deepcopy(inputs)
                        changed['final']=case.call('reopen-'+fault,'document.validate',document=dict(file_path='editable.json',sha256=sha(path.read_bytes())))
                        if fault=='resource-binding':changed['current']['resources']['asset_root']='different resources'
                        case.checks.clear();judge_retained(case,**changed)
                        failures=[c['name'] for c in case.checks if c['status']=='fail']
                        if fault=='none':self.assertEqual(failures,[])
                        else:self.assertIn('history-valid' if fault=='resource-binding' else 'revision-resource-pinning',failures)
                path.write_bytes(original)
                session=case.root/'.inkbolt/sessions'/(sha(b'work')+'.sqlite3');session_bytes=session.read_bytes()
                asset=next((case.root/'.inkbolt/assets').glob('*.rgba8'));asset_bytes=asset.read_bytes()
                duplicate=case.root/'duplicate';duplicate.mkdir();call=case.call
                for fault in ('missing-session','ambiguous-session','corrupt-session','missing-image','corrupt-image'):
                    with self.subTest(fault=fault):
                        case.call=lambda step,command,**arguments:call(fault+'-'+step,command,**arguments)
                        if fault=='missing-session':session.unlink()
                        elif fault=='ambiguous-session':(duplicate/session.name).write_bytes(session_bytes)
                        elif fault=='corrupt-session':session.write_bytes(b'not a session database')
                        elif fault=='missing-image':asset.unlink()
                        else:asset.write_bytes(b'not the pinned image samples')
                        try:
                            with self.assertRaises(TaskFailure):durable_inputs(case)
                        finally:
                            session.write_bytes(session_bytes);asset.write_bytes(asset_bytes)
                            (duplicate/session.name).unlink(missing_ok=True)
            finally:case.close()

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
