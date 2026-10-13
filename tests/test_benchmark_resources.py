"""B15 exact resource repair, preserved history and relocated capture controls."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_cli import EXE,ROOT
sys.path.insert(0,str(ROOT/'tools'))
from agent_benchmark import run_task
from benchmark_resources import fixture,solve,judge,PROMPT,expected_picture,cache_name,BLUE,GREEN,BROKEN,expected_diagnostics,reported_diagnostics
from benchmark_baseline_resources import judge_resources
from benchmark_driver import run_external_task,workspace_files
from benchmark_runtime import Trial,TaskFailure
from benchmark_tasks import CHECKS
from benchmark_resources_client import author
from test_benchmark_driver import driver,fake_tools
from test_images_cli import png,canonical


class ResourceBenchmarkTests(unittest.TestCase):
    def prepare(self,root,independent=False):
        case=Trial(EXE,root,'B15',1,'cli',CHECKS['B15']);self.addCleanup(case.close)
        fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));original=case.call
        def call(step,command,**arguments):
            if arguments.get('session_id')=='work':arguments['session_id']='studio-resources'
            if 'request_id' in arguments:arguments['request_id']='owner-'+arguments['request_id']
            return original(step,command,**arguments)
        if independent:case.call=call
        solve(case);case.call=original
        if independent:
            locator=json.loads((case.root/'session.json').read_bytes());locator['creation']='owner-create'
            (case.root/'session.json').write_text(json.dumps(locator),encoding='utf-8')
        return case

    def test_original_fixtures_and_checks_on_cli_and_mcp_with_separate_judge(self):
        for transport in ('cli','mcp'):
            with self.subTest(transport=transport),tempfile.TemporaryDirectory() as directory:
                row=run_task(EXE,Path(directory)/'reference','B15',1,transport)
                self.assertEqual(row['status'],'passed',row)
                self.assertEqual((row['engine_commands'],row['judge_engine_commands']),(11,10))
                self.assertEqual({c['name'] for c in row['checks']},set(CHECKS['B15'])|{'source-preservation'})
                self.assertGreater(row['first_verified_preview_seconds'],0);self.assertTrue(row['judge_separated'])
                self.assertEqual(row['sources'],{
                    'source.json':'01f756ed9743525ec539feb42bb0397d82218cd15e118672c140612894fe15b2',
                    'original-0.png':'4e8a1ab5551f3c15849555e07b0b7b11bd4fa7ed7fb5025aa7c317428c06fe9a',
                    'original-1.png':'3e3f4de7859b333f69ac692e04b6fa7d78ad1cc49105c385e12b5a6b4a65f27b',
                    'broken-assets/'+cache_name(0):'6a247b61b66cea977151ac86e18ede3fc3490038618782910e723242199ab325'})

    def test_independent_request_and_session_ids_do_not_need_solver_results(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'names',True);case.results.clear();case.begin_judging();judge(case)
            row=case.finish();self.assertEqual(row['status'],'passed',row);self.assertIsNone(row['first_verified_preview_seconds'])

    def test_bad_diagnostics_replacements_artwork_reviews_and_history_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'negative');original=case.call;case.results.clear();case.begin_judging()
            names=['editable.json','diagnostics.json','preview.png','bindings.json','review.json','session.json',
                   'repaired-assets/'+cache_name(0),'repaired-assets/'+cache_name(1),'broken-assets/'+cache_name(0)]
            good={name:(case.root/name).read_bytes() for name in names}
            for fault in ('artwork','diagnosis','replacement','pixels','bindings','review','fingerprint','root','history','missing'):
                with self.subTest(fault=fault):
                    for name,data in good.items():(case.root/name).write_bytes(data)
                    missing=case.root/'broken-assets'/cache_name(1)
                    if missing.exists():missing.unlink()
                    case.checks.clear();case.call=lambda step,command,**arguments:original(fault+'-'+step,command,**arguments)
                    if fault=='artwork':
                        value=json.loads(good['editable.json']);value['items'][0]['transform'][4]=1;name='editable.json'
                    elif fault=='diagnosis':
                        value=json.loads(good['diagnostics.json']);value['issues'][0]['code']='ASSET_MISSING';name='diagnostics.json'
                    elif fault=='bindings':value=dict(before='broken-assets',after='other-assets');name='bindings.json'
                    elif fault in ('review','fingerprint'):
                        value=json.loads(good['review.json']);value['proposal']['base_state_sha256' if fault=='review' else 'request_fingerprint']='0'*64;name='review.json'
                    elif fault in ('root','history'):
                        value=json.loads(good['session.json']);name='session.json'
                        if fault=='root':value['workspace_root']=str(case.root.parent/'wrong')
                        else:value['after_revision']+=1
                    else:value=None
                    if value is not None:(case.root/name).write_text(json.dumps(value),encoding='utf-8')
                    if fault=='replacement':(case.root/'repaired-assets'/cache_name(0)).write_bytes(BROKEN)
                    if fault=='pixels':(case.root/'preview.png').write_bytes(png(1,1,bytes(4)))
                    if fault=='missing':missing.write_bytes(good['repaired-assets/'+cache_name(1)])
                    try:judge(case)
                    except TaskFailure:pass
                    expected={'artwork':'unchanged-artwork','bindings':'unchanged-artwork','diagnosis':'located-diagnostics',
                        'replacement':'verified-replacements','pixels':'repaired-pixels','missing':'verified-replacements',
                        'review':'old-bindings-preserved','fingerprint':'old-bindings-preserved','root':'old-bindings-preserved','history':'history-valid'}[fault]
                    self.assertIn(expected,[c['name'] for c in case.checks if c['status']=='fail'],case.checks)

    def test_external_capture_rejudges_without_following_old_absolute_resource_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);configuration=driver()
            row=run_external_task(EXE,root/'live','B15',1,'model',configuration)
            self.assertEqual(row['status'],'passed',row);before=workspace_files(root/'live/workspace')
            (root/'live').rename(root/'moved')
            imported=run_external_task(EXE,root/'import','B15',1,'model',configuration,import_source=root/'moved')
            self.assertEqual(imported['status'],'passed',imported);self.assertFalse(imported['model_trials'])
            self.assertEqual(before,workspace_files(root/'moved/workspace'));self.assertEqual(before,workspace_files(root/'import/workspace'))

    def test_baseline_checks_pinned_decoding_and_fresh_pixels_without_engine_access(self):
        for fault in ('none','decoded','pixels'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as directory:
                resources=[canonical(2,2,bytes(color)*4) for color in (BLUE,GREEN)]
                if fault=='decoded':resources[0]=canonical(2,2,bytes(GREEN)*4)
                picture=bytes(16*8*4) if fault=='pixels' else expected_picture()
                with patch('benchmark_baseline_resources.decode_and_render',return_value=(resources,picture)), \
                     patch('benchmark_driver.ExternalTrial.call',side_effect=AssertionError('Baseline launched Inkbolt')):
                    row=run_external_task(None,Path(directory)/'baseline','B15',1,'baseline',driver('--preview-usage','--resource-float-json'),fake_tools())
                self.assertEqual(row['status'],'passed' if fault=='none' else 'failed',row)
                if fault=='none':
                    self.assertEqual(row['first_verified_preview_seconds'],.5)
                    self.assertEqual({c['name'] for c in row['checks'] if c['status']=='not_applicable'},{'old-bindings-preserved','history-valid'})
                else:self.assertIn('verified-replacements' if fault=='decoded' else 'repaired-pixels',[c['name'] for c in row['checks'] if c['status']=='fail'])

    def test_baseline_admission_and_cache_validation_precede_pinned_process(self):
        with tempfile.TemporaryDirectory() as directory:
            case=Trial(None,Path(directory)/'baseline','B15',1,'cli',CHECKS['B15'],arm='baseline');self.addCleanup(case.close)
            fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));author(case.root,[bytes(BLUE)*4,bytes(GREEN)*4]);case.begin_judging()
            good=(case.root/'editable.json').read_bytes();good_cache=(case.root/'repaired-assets'/cache_name(0)).read_bytes()
            for fault in ('path','artwork','boolean','cache','missing'):
                with self.subTest(fault=fault):
                    case.checks.clear();(case.root/'editable.json').write_bytes(good)
                    (case.root/'repaired-assets'/cache_name(0)).write_bytes(good_cache)
                    missing=case.root/'broken-assets'/cache_name(1)
                    if missing.exists():missing.unlink()
                    source=json.loads(good)
                    if fault=='path':source['assets']['asset-0']['sha256']='../external'
                    elif fault=='artwork':source['items'][0]['content']['width']=9
                    elif fault=='boolean':source['items'][0]['transform'][0]=True
                    elif fault=='cache':(case.root/'repaired-assets'/cache_name(0)).write_bytes(BROKEN)
                    else:missing.write_bytes(b'unrequested repair')
                    (case.root/'editable.json').write_text(json.dumps(source),encoding='utf-8')
                    with patch('benchmark_baseline_resources.decode_and_render',side_effect=AssertionError('Decoder ran before admission')),self.assertRaises(TaskFailure):
                        judge_resources(case,fake_tools())
                    self.assertIn('verified-replacements' if fault in ('cache','missing') else 'unchanged-artwork',
                        [c['name'] for c in case.checks if c['status']=='fail'])

    def test_diagnostic_order_is_not_a_solution_requirement_but_pairs_are_exact(self):
        value=expected_diagnostics();value['issues'].reverse()
        self.assertEqual(reported_diagnostics(json.dumps(value).encode()),expected_diagnostics())
        value['issues'][0]['pointer']='/assets/asset-0'
        self.assertNotEqual(reported_diagnostics(json.dumps(value).encode()),expected_diagnostics())
        value['issues'][0]['extra']='ignored'
        with self.assertRaises(TaskFailure):reported_diagnostics(json.dumps(value).encode())


if __name__=='__main__':unittest.main()
