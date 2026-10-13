"""B11 judges retained composition and assets, independently of solver logs and IDs."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_cli import EXE,ROOT
sys.path.insert(0,str(ROOT/'tools'))
from agent_benchmark import run_task
from benchmark_mixed import fixture,solve,judge,PROMPT,initial_document,original_pixels,mask_samples,mixed_pixels
from benchmark_baseline_mixed import manifest,admitted_manifest,decode_and_compose
from benchmark_driver import run_external_task,workspace_files
from benchmark_runtime import Trial,TaskFailure
from benchmark_tasks import CHECKS
from test_benchmark_driver import driver,fake_tools
from test_images_cli import png
from workload_cases import save_json


class MixedBenchmarkTests(unittest.TestCase):
    def prepare(self,root,independent=False):
        case=Trial(EXE,root,'B11',1,'cli',CHECKS['B11']);self.addCleanup(case.close)
        fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'))
        if not independent:solve(case);return case
        original=case.call
        def authored(step,command,**arguments):
            if arguments.get('session_id')=='work':arguments['session_id']='artist-session'
            if command=='session.apply_proposal':
                middle=copy.deepcopy(arguments['action']);middle['operations'][0]['effects'][0]['operator']['offset']=[5,2]
                original('artist-intermediate','session.apply',session_id='artist-session',request_id='first',expected_revision=0,
                         action=middle,response_mode='compact')
                review=original('artist-final-review','session.dry_run',session_id='artist-session',request_id='second',expected_revision=1,
                                action=arguments['action'])
                arguments['proposal']=review['proposal']
            return original('artist-'+step,command,**arguments)
        case.call=authored
        names=dict(document='canvas',image='background',group='masked',art='green',unrelated='orange',asset='source',effect='shade')
        with patch('benchmark_mixed.initial_document',side_effect=lambda asset:initial_document(asset,names)):
            solve(case)
        return case

    def test_reference_transports_keep_original_fixture_and_separate_judge_traffic(self):
        for transport in ('cli','mcp'):
            with self.subTest(transport=transport),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)/transport;row=run_task(EXE,root,'B11',1,transport)
                self.assertEqual(row['status'],'passed',row)
                self.assertEqual({c['name'] for c in row['checks']},set(CHECKS['B11'])|{'source-preservation'})
                self.assertEqual((row['engine_commands'],row['judge_engine_commands']),(9,7))
                self.assertTrue(row['judge_separated']);self.assertGreater(row['first_verified_preview_seconds'],0)
                self.assertEqual(row['sources']['original.png'],'d3b13b878b717a8b41f391753b0bd6f372116f0797d261c0e8acf296165fe208')
                for direction in ('request','response'):
                    self.assertEqual(row[direction+'_bytes']+row['judge_'+direction+'_bytes'],sum(p.stat().st_size for p in root.glob('*.'+direction+'.json')))

    def test_independent_ids_and_two_edits_pass_without_solver_results(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'independent',True);case.results.clear();case.begin_judging();judge(case)
            row=case.finish();self.assertEqual(row['status'],'passed',row)
            self.assertIsNone(row['first_verified_preview_seconds'])
            self.assertEqual(json.loads((case.root/'session.json').read_bytes()),
                             dict(session_id='artist-session',original_revision=0,current_revision=2))

    def test_changed_controls_assets_deliveries_and_history_cannot_hide_behind_solver_logs(self):
        for fault in ('group-opacity','isolation','mask','mask-link','fill-opacity','shadow','sigma','unrelated',
                      'resource','preview','historical','before','revision','newer-head','asset-bytes','missing'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as directory:
                case=self.prepare(Path(directory)/fault);path=case.root/'editable.json';actual=json.loads(path.read_bytes())
                group,art=actual['items'][1:3]
                if fault=='group-opacity':group['opacity']=1
                elif fault=='isolation':group['content']['isolated']=False
                elif fault=='mask':group['mask']['gray_hex']='ff'*768
                elif fault=='mask-link':group['mask']['linked']=False
                elif fault=='fill-opacity':art['fill_opacity']=1
                elif fault=='shadow':art['effects'][0]['color'][3]=127
                elif fault=='sigma':art['effects'][0]['operator']['sigma']=1
                elif fault=='unrelated':actual['items'][3]['transform'][4]=1
                elif fault=='resource':actual['assets']['photo']['provenance']['source_sha256']='0'*64
                elif fault in ('preview','historical'):(case.root/(fault+'.png')).write_bytes(png(32,24,original_pixels()))
                elif fault=='before':
                    old=json.loads((case.root/'before.json').read_bytes());old['width']=33
                    (case.root/'before.json').write_text(json.dumps(old),encoding='utf-8')
                elif fault=='revision':actual['revision']=0
                elif fault=='newer-head':case.call('later','session.apply',session_id='work',request_id='later',expected_revision=1,
                    action=dict(type='edit',operations=[dict(op='properties',id='unrelated',name='Later')]),response_mode='compact')
                elif fault=='asset-bytes':
                    asset=next((case.root/'.inkbolt/assets').glob('*.rgba8'));data=bytearray(asset.read_bytes());data[-1]^=1;asset.write_bytes(data)
                elif fault=='missing':(case.root/'historical.png').unlink()
                path.write_text(json.dumps(actual),encoding='utf-8');case.begin_judging()
                try:judge(case)
                except (TaskFailure,ValueError,KeyError) as error:case.error=str(error)
                self.assertEqual(case.finish()['status'],'failed',fault)

    def test_external_capture_rejudges_after_original_resource_roots_move(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);configuration=driver('--custom-session-store','--custom-asset-store')
            row=run_external_task(EXE,root/'live','B11',1,'model',configuration)
            self.assertEqual(row['status'],'passed',row);self.assertFalse(row['model_trials']);self.assertIsNone(row['model_calls'])
            self.assertFalse((root/'live/workspace/.inkbolt/assets').exists());self.assertFalse((root/'live/workspace/.inkbolt/sessions').exists())
            before=workspace_files(root/'live/workspace');(root/'live').rename(root/'capture')
            imported=run_external_task(EXE,root/'import','B11',1,'model',configuration,import_source=root/'capture')
            self.assertEqual(imported['status'],'passed',imported);self.assertEqual(imported['checks'],row['checks'])
            self.assertEqual(before,workspace_files(root/'capture/workspace'));self.assertEqual(before,workspace_files(root/'import/workspace'))

    def test_missing_or_corrupt_custom_image_store_is_not_repaired_by_judging(self):
        for fault in ('--missing-asset-copy','--corrupt-asset-copy'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as directory:
                row=run_external_task(EXE,Path(directory)/'failed','B11',1,'model',
                    driver('--custom-session-store','--custom-asset-store',fault))
                self.assertEqual(row['status'],'failed',row)
                self.assertIn('resource-identity',[c['name'] for c in row['checks'] if c['status']=='fail'])

    def test_baseline_verifies_retained_layers_and_fresh_composition_without_engine_access(self):
        good=dict(pixels=original_pixels(),mask=mask_samples(),rendered=mixed_pixels(original_pixels(),(5,-1)))
        for fault in ('none','pixels','mask','rendered','delivery'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as directory:
                decoded=dict(good)
                if fault in decoded:decoded[fault]=bytes(len(decoded[fault]))
                configuration=driver('--preview-usage',*(['--wrong-image'] if fault=='delivery' else []))
                with patch('benchmark_baseline_mixed.decode_and_compose',return_value=decoded), \
                     patch('benchmark_driver.ExternalTrial.call',side_effect=AssertionError('Baseline launched Inkbolt')):
                    row=run_external_task(None,Path(directory)/'baseline','B11',1,'baseline',configuration,fake_tools())
                self.assertEqual(row['status'],'passed' if fault=='none' else 'failed',row)
                self.assertFalse(row['model_trials'])
                for name in ('historical-pixels','history-valid'):
                    self.assertEqual(next(c for c in row['checks'] if c['name']==name)['status'],'not_applicable')
                self.assertEqual(row['first_verified_preview_seconds'],None if fault in ('rendered','delivery') else .5)

    def test_manifest_rejects_external_paths_boolean_numbers_and_changed_controls(self):
        for fault in ('none','image','mask','bool','alpha','isolation','extra','oversized'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as directory:
                case=Trial(None,Path(directory)/'case','B11',1,'cli',CHECKS['B11'],arm='baseline');fixture(case)
                value=manifest(case.sources['original.png']);(case.root/'mask.png').write_bytes(png(32,24,bytes([128,128,128,255])*768))
                if fault=='image':value['image']['file']='../source.png'
                elif fault=='mask':value['group']['mask']['file']='../mask.png'
                elif fault=='bool':value['art']['shadow']['sigma']=False
                elif fault=='alpha':value['art']['fill'][3]=255
                elif fault=='isolation':value['group']['isolated']=1
                elif fault=='extra':value['group']['blend']='multiply'
                elif fault=='oversized':(case.root/'mask.png').write_bytes(bytes(64*1024+1))
                save_json(case.root/'editable.json',value)
                if fault=='none':self.assertEqual(admitted_manifest(case),value)
                else:
                    with self.assertRaises(TaskFailure):admitted_manifest(case)

    def test_pinned_composition_validates_response_shape_and_sample_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            case=SimpleNamespace(root=Path(directory));good=dict(pixels=original_pixels().hex(),mask=mask_samples().hex(),rendered=mixed_pixels(original_pixels(),(5,-1)).hex())
            with patch('benchmark_baseline_mixed.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(good).encode())) as launch:
                self.assertEqual(decode_and_compose(case,fake_tools())['mask'],mask_samples())
                self.assertEqual(launch.call_args.args[0][:2],[sys.executable,'-I'])
            for code,value in ((1,good),(0,{}),(0,dict(good,mask='00')),(0,dict(good,rendered='bad'))):
                with patch('benchmark_baseline_mixed.subprocess.run',return_value=SimpleNamespace(returncode=code,stdout=json.dumps(value).encode())):
                    with self.assertRaises((TaskFailure,ValueError)):decode_and_compose(case,fake_tools())


if __name__=='__main__':unittest.main()
