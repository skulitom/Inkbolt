"""B20 external model/baseline captures and measured local command boundaries."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_cli import EXE,ROOT
sys.path.insert(0,str(ROOT/'tools'))
from benchmark_driver import run_external_task,workspace_files
from benchmark_baseline import tool_identity
from benchmark_handoff_control import HandoffControl
from benchmark_handoff_external import validate_capture
from benchmark_runtime import TaskFailure
from test_benchmark_driver import driver
from workload_cases import sha


class HandoffBoundaryTests(unittest.TestCase):
    def test_preparation_starts_no_engines_and_missing_tools_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with self.assertRaisesRegex(TaskFailure,'explicit --cutbolt'):
                run_external_task(EXE,root/'missing','B20',1,'model',driver())
            # Valid paths suffice for preparation; these substitutes must never run.
            tools={name:EXE.resolve() for name in ('cutbolt','ffmpeg','ffprobe')}
            with patch('benchmark_handoff_external.execute_client',side_effect=AssertionError('Preparation launched a client')):
                if os.name=='nt':
                    result=run_external_task(EXE,root/'prepared','B20',1,'model',driver(),prepare=True,consumer_tools=tools)
                    self.assertEqual(result['status'],'prepared')
                    request=json.loads((root/'prepared/evidence/request.json').read_bytes())
                    self.assertIsNone(request['mcp_config']);self.assertNotIn('engine_executable',request)
                    self.assertIn('consumer_tools',request['contract']);self.assertIn('handoff_bridge',request)
                    self.assertFalse((root/'prepared/evidence/control-channel').exists())
                else:
                    with self.assertRaisesRegex(TaskFailure,'requires Windows'):
                        run_external_task(EXE,root/'unsupported','B20',1,'model',driver(),consumer_tools=tools)

    def test_baseline_cannot_call_inkbolt_and_consumer_paths_cannot_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);case=SimpleNamespace(root=root,arm='baseline',consumer=SimpleNamespace())
            broker=HandoffControl(case,root/'channel')
            with self.assertRaisesRegex(TaskFailure,'unavailable'):
                broker.dispatch(dict(engine='inkbolt',step='bad',command='capabilities',arguments={}))
            with self.assertRaisesRegex(TaskFailure,'escapes'):
                broker.dispatch(dict(engine='consumer',step='escape',command='session.get',arguments=dict(store_root=str(root.parent))))


@unittest.skipUnless(os.name=='nt' and os.environ.get('INKBOLT_B20_TEST_TOOLS') and os.environ.get('INKBOLT_B20_BASELINE_TOOLS'),
    'Requires explicit B20 consumer/baseline tool configurations and Windows process accounting')
class HandoffExternalTests(unittest.TestCase):
    def setUp(self):
        self.tools=json.loads(Path(os.environ['INKBOLT_B20_TEST_TOOLS']).read_text(encoding='utf-8'))
        self.baseline=tool_identity(json.loads(Path(os.environ['INKBOLT_B20_BASELINE_TOOLS']).read_text(encoding='utf-8')))

    def run_trial(self,root,arm='model',flags=(),source=None):
        configuration=driver(*flags);configuration['timeout_seconds']=60
        return run_external_task(EXE if arm=='model' else None,root,'B20',1,arm,configuration,
            self.baseline if arm=='baseline' else None,import_source=source,consumer_tools=self.tools)

    def test_model_bridge_keeps_measured_costs_and_rejudges_a_moved_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);flags=('--handoff-cli','--handoff-names','--probe-error','--preview-usage')
            row=self.run_trial(root/'live',flags=flags)
            self.assertEqual(row['status'],'passed',{k:row.get(k) for k in ('error','driver_failure','checks')})
            self.assertEqual((row['engine_commands'],row['consumer']['commands'],row['total_engine_commands']),(16,22,38))
            self.assertEqual(row['invalid_calls'],1);self.assertTrue(row['memory_complete']);self.assertFalse(row['model_trials'])
            self.assertEqual(row['preview_timing_source'],'harness_observed');self.assertGreater(row['first_verified_preview_seconds'],0)
            self.assertEqual(row['judge_engine_commands'],9);self.assertEqual(row['consumer']['judge_engine_commands'],9)
            before=workspace_files(root/'live/workspace');(root/'live').rename(root/'moved')
            with patch('benchmark_handoff_external.execute_client',side_effect=AssertionError('Import ran the client')):
                imported=self.run_trial(root/'import',flags=flags,source=root/'moved')
            self.assertEqual(imported['status'],'passed',{k:imported.get(k) for k in ('error','driver_failure','checks')})
            self.assertEqual(imported['harness_handoff'],row['harness_handoff'])
            self.assertEqual(imported['first_verified_preview_seconds'],row['first_verified_preview_seconds'])
            self.assertEqual(before,workspace_files(root/'moved/workspace'));self.assertEqual(before,workspace_files(root/'import/workspace'))
            evidence=root/'moved/evidence';path=evidence/'handoff-control.json';original=path.read_bytes()
            value=json.loads(original);bad=copy.deepcopy(row['harness_handoff'])
            value['metrics']['model_trials']=True;bad['metrics']['model_trials']=True
            path.write_text(json.dumps(value),encoding='utf-8');bad['files'][path.name]=sha(path.read_bytes())
            with self.assertRaisesRegex(TaskFailure,'metric fields'):validate_capture(evidence,bad)
            path.write_bytes(original+b' ')
            with self.assertRaisesRegex(TaskFailure,'identity mismatch'):validate_capture(evidence,row['harness_handoff'])

    def test_baseline_artifacts_and_import_never_call_inkbolt(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch('benchmark_handoff_external.Trial.call',side_effect=AssertionError('Baseline called Inkbolt')):
                row=self.run_trial(root/'live','baseline');before=workspace_files(root/'live/workspace')
                self.assertEqual(row['status'],'passed',{k:row.get(k) for k in ('error','driver_failure','checks')})
                (root/'live').rename(root/'moved')
                imported=self.run_trial(root/'import','baseline',source=root/'moved')
            self.assertEqual(imported['status'],'passed',imported.get('driver_failure'))
            self.assertEqual(row['engine_commands'],0);self.assertEqual(row['consumer']['commands'],6)
            self.assertIsNone(row['peak_commit_bytes']);self.assertFalse(row['memory_complete']);self.assertFalse(row['model_trials'])
            self.assertEqual(len([c for c in row['checks'] if c['status']=='not_applicable']),8)
            self.assertEqual(before,workspace_files(root/'moved/workspace'));self.assertEqual(before,workspace_files(root/'import/workspace'))
            self.assertEqual(row['harness_handoff'],imported['harness_handoff'])
            wrong=self.run_trial(root/'wrong','baseline',('--wrong-image',))
            self.assertEqual(wrong['status'],'failed');self.assertIsNone(wrong['driver_failure'])
            self.assertIn('revised-preview',[c['name'] for c in wrong['checks'] if c['status']=='fail'])

    def test_rejected_baseline_engine_and_outside_store_commands_remain_failures(self):
        for arm,flag in (('baseline','--baseline-engine'),('model','--consumer-escape')):
            with self.subTest(arm=arm),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);row=self.run_trial(root/'trial',arm,(flag,))
                self.assertEqual(row['status'],'failed');self.assertIn('controller failed',row['driver_failure'])
                self.assertFalse((root/'projects.sqlite3').exists())


if __name__=='__main__':unittest.main()
