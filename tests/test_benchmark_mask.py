"""B08 artifact checks reject destructive masking and unbound saved history."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_cli import EXE, ROOT
sys.path.insert(0,str(ROOT/'tools'))
from agent_benchmark import run_task
from benchmark_mask import fixture, solve, judge, PROMPT, original_pixels, selected_pixels, expected_picture
from benchmark_baseline_mask import manifest, admitted_manifest, decode_and_compose
from benchmark_driver import run_external_task, workspace_files
from benchmark_runtime import Trial, TaskFailure
from benchmark_tasks import CHECKS
from test_benchmark_driver import driver, fake_tools
from test_images_cli import png
from workload_cases import save_json


def decoded():
    return dict(pixels=original_pixels(),mask=selected_pixels(),selection=selected_pixels(),rendered=expected_picture())


class BenchmarkMaskTests(unittest.TestCase):
    def prepare(self, root, independent=False):
        trial = Trial(EXE,root,'B08',1,'cli',CHECKS['B08'])
        self.addCleanup(trial.close)
        if independent:
            call = trial.call
            def authored(step, command, **arguments):
                if arguments.get('session_id') == 'work': arguments['session_id'] = 'artist-mask'
                if command == 'session.apply':
                    arguments['action']['operations'][1] = dict(op='mask',id='pixels',mask=dict(
                        width=16,height=16,gray_hex=selected_pixels().hex(),linked=True,clip=True))
                return call('artist-'+step,command,**arguments)
            trial.call = authored
        fixture(trial); trial.begin(PROMPT.read_text(encoding='utf-8')); solve(trial)
        return trial

    def test_reference_transports_separate_judging_and_keep_original_check_inventory(self):
        for transport in ('cli','mcp'):
            with self.subTest(transport=transport), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)/transport
                row = run_task(EXE,root,'B08',1,transport)
                self.assertEqual(row['status'],'passed',row)
                self.assertEqual({c['name'] for c in row['checks']},set(CHECKS['B08'])|{'source-preservation'})
                self.assertEqual(row['engine_commands'],6); self.assertEqual(row['judge_engine_commands'],7)
                self.assertTrue(row['judge_separated']); self.assertGreater(row['first_verified_preview_seconds'],0)
                for direction in ('request','response'):
                    self.assertEqual(row[direction+'_bytes']+row['judge_'+direction+'_bytes'],
                        sum(p.stat().st_size for p in root.glob('*.'+direction+'.json')))
                self.assertEqual(selected_pixels().count(255),56)
                self.assertEqual(row['sources']['source.json'],'0ef39aeb334a308f979cfa0dc5edc757f9b55b1deb0ff3421e5f8eb14a690b0b')

    def test_judge_accepts_authors_session_and_equivalent_full_canvas_mask_without_solver_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            trial = self.prepare(Path(directory)/'independent',True)
            actual = json.loads((trial.root/'editable.json').read_bytes())
            self.assertEqual((actual['items'][0]['mask']['width'],actual['items'][0]['mask']['height']),(16,16))
            trial.results.clear(); trial.begin_judging(); judge(trial)
            row = trial.finish()
            self.assertEqual(row['status'],'passed',row); self.assertIsNone(row['first_verified_preview_seconds'])
            self.assertEqual(json.loads((trial.root/'session.json').read_bytes())['session_id'],'artist-mask')

    def test_good_solver_logs_cannot_hide_erased_pixels_mask_changes_or_false_history(self):
        for alteration in ('erased-outside','unlinked','selection','mask','mask-position','layer-position','canvas','metadata',
                           'preview','historical','revision','other-session','newer-head','missing','source','prompt'):
            with self.subTest(alteration=alteration), tempfile.TemporaryDirectory() as directory:
                trial = self.prepare(Path(directory)/alteration)
                actual = json.loads((trial.root/'editable.json').read_bytes()); item = actual['items'][0]
                if alteration == 'erased-outside': item['content']['rgba_hex'] = '00000000'+item['content']['rgba_hex'][8:]
                elif alteration == 'unlinked': item['mask']['linked'] = False
                elif alteration == 'selection': actual['selection']['gray_hex'] = 'ff'+actual['selection']['gray_hex'][2:]
                elif alteration == 'mask': item['mask']['gray_hex'] = '00'+item['mask']['gray_hex'][2:]
                elif alteration == 'mask-position': item['mask']['transform'][4] += 1
                elif alteration == 'layer-position': item['transform'][4] += 1
                elif alteration == 'canvas': actual['width'] = 17
                elif alteration == 'metadata': actual['metadata'] = {'title':'Unrequested'}
                elif alteration == 'preview': (trial.root/'preview.png').write_bytes(png(16,16,original_pixels()))
                elif alteration == 'historical': (trial.root/'historical.png').write_bytes(png(16,16,expected_picture()))
                elif alteration in ('revision','other-session'):
                    locator = json.loads((trial.root/'session.json').read_bytes())
                    if alteration == 'revision': locator['original_revision'] = True
                    else:
                        other = json.loads((trial.root/'source.json').read_bytes()); other['metadata'] = {'title':'Different source'}
                        trial.call('other-save','session.create',session_id='other',request_id='save',document=other,response_mode='compact')
                        trial.call('other-edit','session.apply',session_id='other',request_id='edit',expected_revision=0,
                            action=dict(type='edit',operations=[dict(op='selection_shape',boundary=dict(shape='polygon',
                                points=[[4,3],[12,3],[12,7],[8,7],[8,13],[4,13]])),dict(op='mask_from_selection',id='pixels',linked=True)]),
                            response_mode='compact')
                        locator['session_id'] = 'other'
                    (trial.root/'session.json').write_text(json.dumps(locator),encoding='utf-8')
                elif alteration == 'newer-head':
                    trial.call('later-edit','session.apply',session_id='work',request_id='later',expected_revision=1,
                        action=dict(type='edit',operations=[dict(op='transform',id='pixels',matrix=[1,0,0,1,1,0],space='world')]),response_mode='compact')
                elif alteration == 'missing': (trial.root/'historical.png').unlink()
                elif alteration == 'source': (trial.root/'source.json').write_bytes(b'{}')
                elif alteration == 'prompt': (trial.root/'task.txt').write_text('changed',encoding='utf-8')
                (trial.root/'editable.json').write_text(json.dumps(actual),encoding='utf-8')
                trial.begin_judging()
                try: judge(trial)
                except (TaskFailure,ValueError,KeyError) as error: trial.error = str(error)
                self.assertEqual(trial.finish()['status'],'failed',alteration)

    def test_external_capture_is_independently_rejudged_after_relocation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); configuration = driver()
            row = run_external_task(EXE,root/'live','B08',1,'model',configuration)
            self.assertEqual(row['status'],'passed',row)
            self.assertFalse(row['model_trials']); self.assertIsNone(row['model_calls'])
            before = workspace_files(root/'live/workspace')
            imported = run_external_task(EXE,root/'import','B08',1,'model',configuration,import_source=root/'live')
            self.assertEqual(imported['status'],'passed',imported); self.assertEqual(row['checks'],imported['checks'])
            self.assertEqual(before,workspace_files(root/'live/workspace')); self.assertEqual(before,workspace_files(root/'import/workspace'))

    def test_baseline_never_launches_engine_and_checks_components_and_both_outputs(self):
        for incorrect in ('none','delivery','pixels','mask','selection','rendered'):
            with self.subTest(incorrect=incorrect), tempfile.TemporaryDirectory() as directory:
                configuration = driver('--preview-usage',*(['--wrong-image'] if incorrect == 'delivery' else []))
                result = decoded()
                if incorrect in result: result[incorrect] = bytes(len(result[incorrect]))
                with patch('benchmark_baseline_mask.decode_and_compose',return_value=result), \
                     patch('benchmark_driver.ExternalTrial.call',side_effect=AssertionError('Baseline launched Inkbolt')):
                    row = run_external_task(None,Path(directory)/'baseline','B08',1,'baseline',configuration,fake_tools())
                self.assertEqual(row['status'],'passed' if incorrect == 'none' else 'failed',row)
                self.assertEqual(row['first_verified_preview_seconds'],None if incorrect in ('delivery','rendered') else .5)
                self.assertFalse(row['model_trials'])
                checks = {c['name']:c['status'] for c in row['checks']}
                for name in ('historical-pixels','history-valid'): self.assertEqual(checks[name],'not_applicable')

    def test_baseline_manifest_rejects_unlinked_external_or_missing_components(self):
        for alteration in ('none','unlinked','bool-transform','layer-id','resource','dimensions','extra','missing','oversized'):
            with self.subTest(alteration=alteration), tempfile.TemporaryDirectory() as directory:
                trial = Trial(None,Path(directory)/'baseline','B08',1,'cli',CHECKS['B08'],arm='baseline')
                self.addCleanup(trial.close); fixture(trial); value = manifest()
                for name in ('pixels.png','mask.png','selection.png'): (trial.root/name).write_bytes(png(16,16,original_pixels()))
                if alteration == 'unlinked': value['linked'] = False
                elif alteration == 'bool-transform': value['transform'][4] = False
                elif alteration == 'layer-id': value['id'] = 'other'
                elif alteration == 'resource': value['image'] = '../external.png'
                elif alteration == 'dimensions': value['width'] = 17
                elif alteration == 'extra': value['other'] = 'unrequested'
                elif alteration == 'missing': (trial.root/'mask.png').unlink()
                elif alteration == 'oversized': (trial.root/'mask.png').write_bytes(b' '*(64*1024+1))
                save_json(trial.root/'editable.json',value)
                if alteration == 'none': self.assertEqual(admitted_manifest(trial),manifest())
                else:
                    with self.assertRaises(TaskFailure): admitted_manifest(trial)

    def test_pinned_decoder_result_contract_rejects_failures_wrong_keys_and_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            case = SimpleNamespace(root=Path(directory))
            payload = {key:value.hex() for key,value in decoded().items()}
            with patch('benchmark_baseline_mask.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(payload).encode())) as launch:
                self.assertEqual(decode_and_compose(case,fake_tools()),decoded())
                self.assertEqual(launch.call_args.args[0][:2],[sys.executable,'-I'])
                self.assertEqual(launch.call_args.kwargs['timeout'],30)
            for code,value in ((1,payload),(0,{}),(0,dict(payload,mask='00')),(0,dict(payload,pixels='bad'))):
                with patch('benchmark_baseline_mask.subprocess.run',return_value=SimpleNamespace(returncode=code,stdout=json.dumps(value).encode())):
                    with self.assertRaises((TaskFailure,ValueError)): decode_and_compose(case,fake_tools())


if __name__ == '__main__': unittest.main()
