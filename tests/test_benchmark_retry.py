"""B17 real withheld responses, independent replay probes and sealed captures."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_cli import EXE,ROOT
sys.path.insert(0,str(ROOT/'tools'))
from agent_benchmark import run_task
from benchmark_retry import fixture,prepare,solve,judge,PROMPT,edit_request,SETUP_FILES
from benchmark_driver import run_external_task,workspace_files,run_owned
from benchmark_runtime import Trial,TaskFailure
from benchmark_tasks import CHECKS
from test_benchmark_driver import driver,fake_tools
from test_images_cli import png


class RetryBenchmarkTests(unittest.TestCase):
    def prepare(self,root):
        case=Trial(EXE,root,'B17',1,'cli',CHECKS['B17']);self.addCleanup(case.close)
        fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));prepare(case);solve(case)
        return case

    def test_original_nine_commands_and_five_checks_on_cli_and_mcp(self):
        for transport in ('cli','mcp'):
            with self.subTest(transport=transport),tempfile.TemporaryDirectory() as directory:
                row=run_task(EXE,Path(directory)/'reference','B17',1,transport)
                self.assertEqual(row['status'],'passed',row)
                self.assertEqual((row['engine_commands'],row['judge_engine_commands'],row['retries']),(9,12,2))
                self.assertEqual({c['name'] for c in row['checks']},set(CHECKS['B17'])|{'source-preservation'})
                self.assertTrue(row['judge_separated']);self.assertGreater(row['first_verified_preview_seconds'],0)
                lost=next(c for c in row['calls'] if c['step']=='lost')
                self.assertEqual(lost['status'],'response_lost');self.assertIs(lost['response_observed'],False)
                self.assertEqual(row['sources']['source.json'],'043f59c6e7024a9bd2b6d8be99ccdabbffd32a56cce25657efb9157de32c98d6')

    def test_judge_uses_retained_sources_and_receipts_without_solver_results(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'retained');case.results.clear();case.begin_judging();judge(case)
            row=case.finish();self.assertEqual(row['status'],'passed',row);self.assertIsNone(row['first_verified_preview_seconds'])

    def test_wrong_receipts_requests_states_pixels_and_restored_controls_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'negative');original=case.call;case.results.clear();case.begin_judging()
            names=['attempts.json','editable.json','preview.png',SETUP_FILES[0]]
            good={name:(case.root/name).read_bytes() for name in names}
            for fault in ('receipt','retry','request','head','pixels','artwork','injected'):
                with self.subTest(fault=fault):
                    for name,raw in good.items():(case.root/name).write_bytes(raw)
                    case.checks.clear();case.call=lambda step,command,**arguments:original(fault+'-'+step,command,**arguments)
                    case.judge_root=Path(directory)/fault;case.judge_root.mkdir()
                    (case.judge_root/SETUP_FILES[0]).write_bytes(good[SETUP_FILES[0]])
                    if fault in ('receipt','retry','request','head'):
                        value=json.loads(good['attempts.json'])
                        if fault=='receipt':value['recovered']['receipt_summary']['state_sha256']='0'*64
                        elif fault=='retry':value['retry']['result']['replayed']=False
                        elif fault=='request':value['retry']['request']['expected_revision']=1
                        else:value['retry-after-undo']['result']['current_revision']=3
                        (case.root/'attempts.json').write_text(json.dumps(value),encoding='utf-8')
                    elif fault=='pixels':(case.root/'preview.png').write_bytes(png(1,1,bytes(4)))
                    elif fault=='artwork':
                        value=json.loads(good['editable.json']);value['items'][1]['content']['geometry']['x']=21
                        (case.root/'editable.json').write_text(json.dumps(value),encoding='utf-8')
                    else:
                        value=json.loads(good[SETUP_FILES[0]]);value['response']['receipt_summary']['request_id']='different'
                        (case.judge_root/SETUP_FILES[0]).write_text(json.dumps(value),encoding='utf-8')
                    judge(case)
                    expected={'receipt':'original-receipt','retry':'retry-idempotent','request':'retry-idempotent','head':'retry-idempotent',
                        'pixels':'edited-pixels','artwork':'undo-preserved','injected':'original-receipt'}[fault]
                    self.assertIn(expected,[c['name'] for c in case.checks if c['status']=='fail'],case.checks)

    def test_duplicate_real_edit_cannot_be_hidden_by_retained_success_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'duplicate')
            request=edit_request();request.pop('command');request.update(request_id='duplicate',expected_revision=2)
            case.call('duplicate','session.apply',**request);case.results.clear();case.begin_judging();judge(case)
            self.assertIn('history-valid',[c['name'] for c in case.checks if c['status']=='fail'])
            self.assertIn('undo-preserved',[c['name'] for c in case.checks if c['status']=='fail'])

    def test_external_harness_drops_response_before_client_and_import_preserves_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);configuration=driver('--preview-usage')
            row=run_external_task(EXE,root/'live','B17',1,'model',configuration)
            self.assertEqual(row['status'],'passed',row);self.assertFalse(row['model_trials'])
            self.assertEqual(row['harness_setup']['engine_commands'],2);self.assertIsNone(row['engine_commands'])
            self.assertEqual(row['first_verified_preview_seconds'],.5)
            self.assertEqual(set(row['harness_setup']['files']),set(SETUP_FILES));self.assertGreater(row['harness_setup']['response_bytes'],0)
            self.assertFalse((root/'live/workspace'/SETUP_FILES[0]).exists())
            events=[json.loads(s) for s in (root/'live/evidence/transcript.jsonl').read_text().splitlines()]
            self.assertEqual(len(events),7);self.assertFalse(any(e['step']=='lost' for e in events))
            original=json.loads((root/'live/evidence'/SETUP_FILES[0]).read_bytes())
            self.assertIs(original['observed'],False);self.assertIs(original['response']['replayed'],False)
            before=workspace_files(root/'live/workspace');(root/'live').rename(root/'moved')
            with patch('benchmark_retry.prepare_external',side_effect=AssertionError('Import reinjected the edit')):
                imported=run_external_task(EXE,root/'import','B17',1,'model',configuration,import_source=root/'moved')
            self.assertEqual(imported['status'],'passed',imported);self.assertEqual(imported['harness_setup'],row['harness_setup'])
            self.assertEqual(before,workspace_files(root/'moved/workspace'));self.assertEqual(before,workspace_files(root/'import/workspace'))
            evidence=root/'moved/evidence'/SETUP_FILES[0];value=json.loads(evidence.read_bytes());value['observed']=True
            evidence.write_text(json.dumps(value),encoding='utf-8')
            rejected=run_external_task(EXE,root/'changed','B17',1,'model',configuration,import_source=root/'moved')
            self.assertEqual(rejected['status'],'failed');self.assertIn('setup evidence identity mismatch',rejected['driver_failure'])

    def test_preparation_injects_once_without_launching_client_and_baseline_stays_not_applicable(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch('benchmark_driver.run_owned',side_effect=AssertionError('Preparation launched client')):
                row=run_external_task(EXE,root/'prepared','B17',1,'model',driver(),prepare=True)
            self.assertEqual(row['status'],'prepared');self.assertEqual(row['harness_setup']['engine_commands'],2)
            self.assertTrue((root/'prepared/evidence'/SETUP_FILES[0]).is_file())
            with patch('benchmark_retry.prepare_external',side_effect=AssertionError('Baseline launched Inkbolt')):
                baseline=run_external_task(None,root/'baseline','B17',1,'baseline',driver(),fake_tools())
            self.assertEqual(baseline['status'],'not_applicable')

    def test_live_client_cannot_change_harness_evidence_after_setup(self):
        def changed(argv,workspace,*args,**kwargs):
            result=run_owned(argv,workspace,*args,**kwargs)
            path=workspace.parent/'evidence'/SETUP_FILES[0];value=json.loads(path.read_bytes());value['observed']=True
            path.write_text(json.dumps(value),encoding='utf-8')
            return result
        with tempfile.TemporaryDirectory() as directory,patch('benchmark_driver.run_owned',side_effect=changed):
            row=run_external_task(EXE,Path(directory)/'changed','B17',1,'model',driver())
        self.assertEqual(row['status'],'failed');self.assertIn('setup evidence identity mismatch',row['driver_failure'])

    def test_marked_observed_injection_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'observed');case.begin_judging()
            path=case.root/SETUP_FILES[0];value=json.loads(path.read_bytes());value['observed']=True
            path.write_text(json.dumps(value),encoding='utf-8')
            with self.assertRaisesRegex(TaskFailure,'unobserved'):judge(case)


if __name__=='__main__':unittest.main()
