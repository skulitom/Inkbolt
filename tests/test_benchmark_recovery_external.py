"""B19 external bridge, retained process evidence and immutable capture import."""
import json
import copy
import hashlib
from contextlib import chdir
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_cli import EXE,ROOT
from platform_support import require_capability
sys.path.insert(0,str(ROOT/'tools'))
from benchmark_driver import run_external_task,workspace_files
from benchmark_runtime import TaskFailure
from test_benchmark_driver import driver,fake_tools
from benchmark_recovery_external import validate_capture


class RecoveryPlatformTests(unittest.TestCase):
    def test_baseline_is_not_applicable_and_preparation_never_starts_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch('benchmark_recovery_external.execute_client',side_effect=AssertionError('Preparation started processes')):
                baseline=run_external_task(None,root/'baseline','B19',1,'baseline',driver(),fake_tools())
                self.assertEqual(baseline['status'],'not_applicable')
                if os.name=='nt':
                    with chdir(root):prepared=run_external_task(EXE,Path('prepared'),'B19',1,'model',driver(),prepare=True)
                    self.assertEqual(prepared['status'],'prepared')
                    request=json.loads((root/'prepared/evidence/request.json').read_bytes())
                    self.assertIsNone(request['mcp_config']);self.assertNotIn('engine_executable',request)
                    self.assertIn('recovery_bridge',request);self.assertIn('control_files',request['contract'])
                    self.assertTrue(Path(request['recovery_bridge'][-1]).is_absolute())
                    self.assertFalse((root/'prepared/evidence/control-channel').exists())
                else:
                    with self.assertRaisesRegex(TaskFailure,'Unix jobs are unsupported'):
                        run_external_task(EXE,root/'unsupported','B19',1,'model',driver())


class RecoveryExternalTests(unittest.TestCase):
    def setUp(self):require_capability(self,'jobs')

    def test_real_cli_bridge_retains_costs_and_import_rejudges_without_faults_or_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);configuration=driver('--recovery-cli','--preview-usage','--recovery-full','--probe-error',
                '--custom-session-store','--custom-asset-store','--recovery-compact-source');configuration['timeout_seconds']=60
            row=run_external_task(EXE,root/'live','B19',1,'model',configuration)
            self.assertEqual(row['status'],'passed',{k:row.get(k) for k in ('status','error','driver_failure','checks')})
            self.assertFalse(row['model_trials']);self.assertGreaterEqual(row['engine_commands'],23)
            self.assertEqual(row['judge_engine_commands'],12);self.assertEqual(row['retries'],3)
            self.assertEqual(row['invalid_calls'],1)
            self.assertEqual(row['expected_errors'],3);self.assertGreater(row['first_verified_preview_seconds'],0)
            self.assertEqual(row['preview_timing_source'],'harness_observed')
            self.assertTrue(row['memory_complete']);self.assertGreater(row['peak_commit_bytes'],0)
            workspace=root/'live/workspace';snapshot=json.loads((workspace/'editable.json').read_bytes())
            self.assertEqual(snapshot['revision'],1);self.assertNotIn('resolution_ppi',snapshot)
            self.assertTrue((workspace/'chosen sessions').is_dir());self.assertTrue((workspace/'chosen resources/images').is_dir())
            self.assertFalse((workspace/'.inkbolt/sessions').exists());self.assertFalse((workspace/'.inkbolt/assets').exists())
            control=row['harness_recovery'];self.assertEqual(control['metrics']['engine_commands'],row['engine_commands'])
            before=workspace_files(root/'live/workspace');(root/'live').rename(root/'moved')
            with patch('benchmark_recovery_external.execute_client',side_effect=AssertionError('Import injected a fault')):
                imported=run_external_task(EXE,root/'import','B19',1,'model',configuration,import_source=root/'moved')
            self.assertEqual(imported['status'],'passed',{k:imported.get(k) for k in ('status','error','driver_failure','checks')})
            self.assertEqual(imported['harness_recovery'],control)
            self.assertEqual(imported['first_verified_preview_seconds'],row['first_verified_preview_seconds'])
            self.assertEqual(before,workspace_files(root/'moved/workspace'));self.assertEqual(before,workspace_files(root/'import/workspace'))
            for name in ('recovery-observations.json','recovery-evidence.json','recovery-control.json'):
                self.assertFalse((root/'moved/workspace'/name).exists())
            evidence=root/'moved/evidence'
            path=evidence/'recovery-control.json';good=path.read_bytes();proof=json.loads(good);bad=copy.deepcopy(control)
            proof['metrics']['model_trials']=True;bad['metrics']['model_trials']=True
            path.write_text(json.dumps(proof),encoding='utf-8');bad['files'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(TaskFailure,'metric fields'):validate_capture(evidence,bad)
            path.write_bytes(good)
            path=evidence/'recovery-observations.json';path.write_bytes(path.read_bytes()+b' ')
            with self.assertRaisesRegex(TaskFailure,'identity mismatch'):validate_capture(evidence,control)
            failed=run_external_task(EXE,root/'changed','B19',1,'model',configuration,import_source=root/'moved')
            self.assertEqual(failed['status'],'failed');self.assertIn('identity mismatch',failed['driver_failure'])

    def test_failed_client_and_invalid_fault_control_close_only_the_owned_runtime(self):
        for flag in ('--hold-and-stop','--bad-control'):
            with self.subTest(flag=flag),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);configuration=driver(flag);configuration['timeout_seconds']=60
                row=run_external_task(EXE,root/'failed','B19',1,'model',configuration)
                self.assertEqual(row['status'],'failed');self.assertIsNotNone(row['driver_failure'])
                proof=json.loads((root/'failed/evidence/recovery-evidence.json').read_bytes())
                self.assertEqual(proof['accounting']['active'],0);self.assertIsNone(proof['observer_error'])
                lease=root/'failed/workspace/.inkbolt/jobs/worker.lock'
                if lease.exists():
                    import msvcrt
                    with lease.open('a+b') as stream:
                        stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                        stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)

    def test_successful_driver_cannot_award_a_wrong_artifact_a_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            configuration=driver('--wrong-image');configuration['timeout_seconds']=60
            row=run_external_task(EXE,Path(directory)/'wrong','B19',1,'model',configuration)
            self.assertEqual(row['status'],'failed');self.assertIsNone(row['driver_failure'])
            self.assertIn('review-pixels',[c['name'] for c in row['checks'] if c['status']=='fail'])


if __name__=='__main__':unittest.main()
