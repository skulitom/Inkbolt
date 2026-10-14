"""B18 real stale proposals, independent recovery checks and sealed captures."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_cli import EXE,ROOT
sys.path.insert(0,str(ROOT/'tools'))
from agent_benchmark import run_task
from benchmark_conflict import fixture,prepare,solve,judge,PROMPT,SETUP_FILES,target_action
from benchmark_driver import run_external_task,workspace_files,run_owned
from benchmark_runtime import Trial,TaskFailure
from benchmark_tasks import CHECKS
from test_benchmark_driver import driver,fake_tools
from test_images_cli import png


class ConflictBenchmarkTests(unittest.TestCase):
    def prepare(self,root):
        case=Trial(EXE,root,'B18',1,'cli',CHECKS['B18']);self.addCleanup(case.close)
        fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));prepare(case);solve(case)
        return case

    def test_original_ten_commands_and_five_checks_on_cli_and_mcp(self):
        for transport in ('cli','mcp'):
            with self.subTest(transport=transport),tempfile.TemporaryDirectory() as directory:
                row=run_task(EXE,Path(directory)/'reference','B18',1,transport)
                self.assertEqual(row['status'],'passed',row)
                self.assertEqual((row['engine_commands'],row['judge_engine_commands']),(10,13))
                self.assertEqual({c['name'] for c in row['checks']},set(CHECKS['B18'])|{'source-preservation'})
                self.assertTrue(row['judge_separated']);self.assertGreater(row['first_verified_preview_seconds'],0)
                self.assertEqual(row['sources']['source.json'],'043f59c6e7024a9bd2b6d8be99ccdabbffd32a56cce25657efb9157de32c98d6')

    def test_judge_reproduces_conflict_without_solver_results_or_changing_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'retained');case.results.clear();case.begin_judging()
            case.judge_root=Path(directory)/'judge';case.judge_root.mkdir()
            for name in SETUP_FILES:(case.judge_root/name).write_bytes((case.root/name).read_bytes())
            before=workspace_files(case.root);judge(case)
            row=case.finish();self.assertEqual(row['status'],'passed',row);self.assertIsNone(row['first_verified_preview_seconds'])
            after=workspace_files(case.root)
            self.assertEqual(before,{name:after[name] for name in before})  # Reference judging adds traffic logs.

    def test_wrong_error_request_review_artwork_and_pixels_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'negative');original=case.call;case.results.clear();case.begin_judging()
            names=['rejected.json','review.json','editable.json','preview.png','historical.png',*SETUP_FILES]
            good={name:(case.root/name).read_bytes() for name in names}
            for fault in ('error','request','fingerprint','base','prediction','artwork','pixels','history-pixels',
                          'missing-revision','stale-revision','resolution','review-error','review-nonboolean',
                          'review-extra','review-result','review-missing','review-malformed'):
                with self.subTest(fault=fault):
                    for name,raw in good.items():(case.root/name).write_bytes(raw)
                    case.checks.clear();case.call=lambda step,command,**arguments:original(fault+'-'+step,command,**arguments)
                    case.judge_root=Path(directory)/fault;case.judge_root.mkdir()
                    for name in SETUP_FILES:(case.judge_root/name).write_bytes(good[name])
                    if fault in ('error','request'):
                        value=json.loads(good['rejected.json'])
                        if fault=='error':value['error']['code']='REQUEST_CONFLICT'
                        else:value['request']['proposal']['expected_revision']=1
                        (case.root/'rejected.json').write_text(json.dumps(value),encoding='utf-8')
                    elif fault in ('fingerprint','base','prediction'):
                        value=json.loads(good['review.json'])
                        if fault=='fingerprint':value['proposal']['request_fingerprint']='0'*64
                        elif fault=='base':value['proposal']['base_state_sha256']='0'*64
                        else:value['predicted_receipt']['revision']=3
                        (case.root/'review.json').write_text(json.dumps(value),encoding='utf-8')
                    elif fault in ('artwork','missing-revision','stale-revision','resolution'):
                        value=json.loads(good['editable.json'])
                        if fault=='artwork':value['items'][1]['content']['geometry']['x']=21
                        elif fault=='missing-revision':del value['revision']
                        elif fault=='stale-revision':value['revision']=1
                        else:value['resolution_ppi']=72
                        (case.root/'editable.json').write_text(json.dumps(value),encoding='utf-8')
                    elif fault.startswith('review-'):
                        value=dict(ok=True,result=json.loads(good['review.json']))
                        if fault=='review-error':value=dict(ok=False,error=dict(code='REVISION_CONFLICT'))
                        elif fault=='review-nonboolean':value['ok']=1
                        elif fault=='review-extra':value['extra']=True
                        elif fault=='review-result':value['result']=[]
                        elif fault=='review-missing':del value['result']
                        raw=b'{' if fault=='review-malformed' else json.dumps(value).encode()
                        (case.root/'review.json').write_bytes(raw)
                    else:(case.root/('preview.png' if fault=='pixels' else 'historical.png')).write_bytes(png(1,1,bytes(4)))
                    judge(case)
                    expected=('stale-rejected' if fault in ('error','request') else 'conflict-pixels' if fault=='pixels' else
                        'historical-pixels' if fault=='history-pixels' else 'both-intents-preserved')
                    self.assertIn(expected,[c['name'] for c in case.checks if c['status']=='fail'],case.checks)
                    self.assertEqual({c['name'] for c in case.checks},set(CHECKS['B18']))

    def test_extra_real_commit_cannot_be_hidden_by_correct_deliverables(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'extra')
            case.call('extra','session.apply',session_id='work',request_id='extra',expected_revision=2,action=target_action(),response_mode='compact')
            case.results.clear();case.begin_judging();judge(case)
            self.assertIn('history-valid',[c['name'] for c in case.checks if c['status']=='fail'])
            self.assertIn('both-intents-preserved',[c['name'] for c in case.checks if c['status']=='fail'])

    def test_external_setup_precedes_client_and_import_preserves_original_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);configuration=driver('--preview-usage','--recovery-compact-source','--conflict-review-envelope')
            row=run_external_task(EXE,root/'live','B18',1,'model',configuration)
            self.assertEqual(row['status'],'passed',row);self.assertFalse(row['model_trials'])
            self.assertEqual(row['harness_setup']['engine_commands'],3);self.assertIsNone(row['engine_commands'])
            self.assertEqual(row['first_verified_preview_seconds'],.5)
            saved=json.loads((root/'live/workspace/editable.json').read_bytes())
            self.assertNotIn('resolution_ppi',saved);self.assertEqual(saved['revision'],2)
            review=json.loads((root/'live/workspace/review.json').read_bytes())
            self.assertEqual(set(review),{'ok','result'});self.assertIs(review['ok'],True)
            self.assertEqual(set(row['harness_setup']['files']),set(SETUP_FILES))
            for name in SETUP_FILES:self.assertFalse((root/'live/workspace'/name).exists())
            events=[json.loads(s) for s in (root/'live/evidence/transcript.jsonl').read_text().splitlines()]
            self.assertEqual(len(events),7);self.assertEqual(events[0]['step'],'stale')
            self.assertEqual(json.loads(events[0]['response'])['error']['code'],'REVISION_CONFLICT')
            before=workspace_files(root/'live/workspace');(root/'live').rename(root/'moved')
            with patch('benchmark_conflict.prepare_external',side_effect=AssertionError('Import reinjected writer')):
                imported=run_external_task(EXE,root/'import','B18',1,'model',configuration,import_source=root/'moved')
            self.assertEqual(imported['status'],'passed',imported);self.assertEqual(imported['harness_setup'],row['harness_setup'])
            self.assertEqual(before,workspace_files(root/'moved/workspace'));self.assertEqual(before,workspace_files(root/'import/workspace'))
            path=root/'moved/evidence'/SETUP_FILES[1];path.write_bytes(path.read_bytes()+b'changed')
            failed=run_external_task(EXE,root/'changed','B18',1,'model',configuration,import_source=root/'moved')
            self.assertEqual(failed['status'],'failed');self.assertIn('setup evidence identity mismatch',failed['driver_failure'])

    def test_prepare_only_and_baseline_do_not_launch_client(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch('benchmark_driver.run_owned',side_effect=AssertionError('Preparation launched client')):
                row=run_external_task(EXE,root/'prepared','B18',1,'model',driver(),prepare=True)
            self.assertEqual(row['status'],'prepared');self.assertEqual(row['harness_setup']['engine_commands'],3)
            self.assertTrue((root/'prepared/workspace/stale-request.json').is_file())
            with patch('benchmark_conflict.prepare_external',side_effect=AssertionError('Baseline launched Inkbolt')):
                baseline=run_external_task(None,root/'baseline','B18',1,'baseline',driver(),fake_tools())
            self.assertEqual(baseline['status'],'not_applicable')

    def test_setup_store_or_supplied_request_cannot_change(self):
        for name in (SETUP_FILES[1],'stale-request.json'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as directory:
                case=self.prepare(Path(directory)/'changed');path=case.root/name;path.write_bytes(path.read_bytes()+b' ')
                case.begin_judging()
                with self.assertRaisesRegex(TaskFailure,'identity changed'):judge(case)

    def test_live_client_cannot_change_harness_setup(self):
        def changed(argv,workspace,*args,**kwargs):
            result=run_owned(argv,workspace,*args,**kwargs)
            path=workspace.parent/'evidence'/SETUP_FILES[1];path.write_bytes(path.read_bytes()+b'changed')
            return result
        with tempfile.TemporaryDirectory() as directory,patch('benchmark_driver.run_owned',side_effect=changed):
            row=run_external_task(EXE,Path(directory)/'changed','B18',1,'model',driver())
        self.assertEqual(row['status'],'failed');self.assertIn('setup evidence identity mismatch',row['driver_failure'])


if __name__=='__main__':unittest.main()
