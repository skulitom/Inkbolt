"""B09 judges exact local repair, unchanged pixels/state and bound history."""
import copy
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
from benchmark_retouch import fixture, solve, judge, PROMPT, original_pixels, repaired_pixels
from benchmark_baseline_retouch import manifest, admitted_manifest, decode_pixels
from benchmark_driver import run_external_task, workspace_files
from benchmark_runtime import Trial, TaskFailure
from benchmark_tasks import CHECKS
from test_benchmark_driver import driver, fake_tools
from test_images_cli import png
from workload_cases import save_json


class BenchmarkRetouchTests(unittest.TestCase):
    def prepare(self, root, independent=False):
        trial = Trial(EXE,root,'B09',1,'cli',CHECKS['B09'])
        self.addCleanup(trial.close)
        if independent:
            call = trial.call
            def authored(step, command, **arguments):
                if arguments.get('session_id') == 'work': arguments['session_id'] = 'artist-retouch'
                if command == 'session.apply':
                    for row in range(2):
                        part = copy.deepcopy(arguments); part['request_id'] = 'row-'+str(row); part['expected_revision'] = row
                        region = part['action']['operations'][0]['options']['region']; region['y'] = 10+row; region['height'] = 1
                        result = call('artist-'+step+'-'+str(row),command,**part)
                    return result
                return call('artist-'+step,command,**arguments)
            trial.call = authored
        fixture(trial); trial.begin(PROMPT.read_text(encoding='utf-8')); solve(trial)
        return trial

    def test_reference_transports_preserve_fixture_and_separate_solver_from_judge(self):
        for transport in ('cli','mcp'):
            with self.subTest(transport=transport), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)/transport; row = run_task(EXE,root,'B09',1,transport)
                self.assertEqual(row['status'],'passed',row)
                self.assertEqual({c['name'] for c in row['checks']},set(CHECKS['B09'])|{'source-preservation'})
                self.assertEqual(row['engine_commands'],6); self.assertEqual(row['judge_engine_commands'],7)
                self.assertTrue(row['judge_separated']); self.assertGreater(row['first_verified_preview_seconds'],0)
                for direction in ('request','response'):
                    self.assertEqual(row[direction+'_bytes']+row['judge_'+direction+'_bytes'],
                        sum(p.stat().st_size for p in root.glob('*.'+direction+'.json')))
                self.assertEqual(row['sources']['source.json'],'200dda427495dfe414221be21d9db65ce8ab8091bd0ecac3cf34b7f397292558')
                original,correct = original_pixels(),repaired_pixels()
                changed = [i for i in range(256) if original[i*4:i*4+4] != correct[i*4:i*4+4]]
                self.assertEqual(changed,[170,171,186,187])

    def test_judge_accepts_independent_session_and_two_edits_without_solver_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            trial = self.prepare(Path(directory)/'independent',True)
            trial.results.clear(); trial.begin_judging(); judge(trial)
            row = trial.finish(); self.assertEqual(row['status'],'passed',row)
            self.assertIsNone(row['first_verified_preview_seconds'])
            self.assertEqual(json.loads((trial.root/'session.json').read_bytes()),
                dict(session_id='artist-retouch',original_revision=0,current_revision=2))

    def test_solver_logs_cannot_hide_wrong_patch_unrelated_changes_or_false_history(self):
        for alteration in ('defect','outside','alpha','position','canvas','metadata','preview','historical',
                           'revision','other-session','newer-head','missing','source','prompt'):
            with self.subTest(alteration=alteration), tempfile.TemporaryDirectory() as directory:
                trial = self.prepare(Path(directory)/alteration)
                actual = json.loads((trial.root/'editable.json').read_bytes()); item = actual['items'][0]
                if alteration in ('defect','outside','alpha'):
                    data = bytearray.fromhex(item['content']['rgba_hex'])
                    if alteration == 'defect': data[170*4:170*4+4] = bytes([255,0,255,255])
                    elif alteration == 'outside': data[0] ^= 1
                    else: data[170*4+3] = 254
                    item['content']['rgba_hex'] = data.hex()
                elif alteration == 'position': item['transform'][4] = 1
                elif alteration == 'canvas': actual['width'] = 17
                elif alteration == 'metadata': actual['metadata'] = {'title':'Unrequested'}
                elif alteration == 'preview': (trial.root/'preview.png').write_bytes(png(16,16,original_pixels()))
                elif alteration == 'historical': (trial.root/'historical.png').write_bytes(png(16,16,repaired_pixels()))
                elif alteration in ('revision','other-session'):
                    locator = json.loads((trial.root/'session.json').read_bytes())
                    if alteration == 'revision': locator['original_revision'] = False
                    else:
                        other = json.loads((trial.root/'source.json').read_bytes()); other['metadata'] = {'title':'Different source'}
                        trial.call('other-save','session.create',session_id='other',request_id='save',document=other,response_mode='compact')
                        trial.call('other-edit','session.apply',session_id='other',request_id='edit',expected_revision=0,
                            action=dict(type='edit',operations=[dict(op='retouch',id='pixels',options=dict(source_id='pixels',
                                region=dict(x=10,y=10,width=2,height=2),source_transform=[1,0,0,1,-8,-8],sampling='nearest',mode=dict(type='clone')))]),response_mode='compact')
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

    def test_external_capture_rejudges_relocated_artifacts_and_keeps_usage_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); configuration = driver()
            row = run_external_task(EXE,root/'live','B09',1,'model',configuration)
            self.assertEqual(row['status'],'passed',row); self.assertFalse(row['model_trials']); self.assertIsNone(row['model_calls'])
            before = workspace_files(root/'live/workspace')
            imported = run_external_task(EXE,root/'import','B09',1,'model',configuration,import_source=root/'live')
            self.assertEqual(imported['status'],'passed',imported); self.assertEqual(row['checks'],imported['checks'])
            self.assertEqual(before,workspace_files(root/'live/workspace')); self.assertEqual(before,workspace_files(root/'import/workspace'))

    def test_baseline_checks_editable_pixels_and_preview_without_engine_access(self):
        for incorrect in ('none','delivery','pixels'):
            with self.subTest(incorrect=incorrect), tempfile.TemporaryDirectory() as directory:
                configuration = driver('--preview-usage',*(['--wrong-image'] if incorrect == 'delivery' else []))
                decoded = original_pixels() if incorrect == 'pixels' else repaired_pixels()
                with patch('benchmark_baseline_retouch.decode_pixels',return_value=decoded), \
                     patch('benchmark_driver.ExternalTrial.call',side_effect=AssertionError('Baseline launched Inkbolt')):
                    row = run_external_task(None,Path(directory)/'baseline','B09',1,'baseline',configuration,fake_tools())
                self.assertEqual(row['status'],'passed' if incorrect == 'none' else 'failed',row)
                self.assertEqual(row['first_verified_preview_seconds'],.5 if incorrect == 'none' else None)
                self.assertFalse(row['model_trials'])
                checks = {c['name']:c['status'] for c in row['checks']}
                for name in ('historical-pixels','history-valid'): self.assertEqual(checks[name],'not_applicable')

    def test_baseline_manifest_rejects_wrong_identity_transform_or_external_components(self):
        for alteration in ('none','bool-transform','id','resource','dimensions','extra','missing','oversized'):
            with self.subTest(alteration=alteration), tempfile.TemporaryDirectory() as directory:
                trial = Trial(None,Path(directory)/'baseline','B09',1,'cli',CHECKS['B09'],arm='baseline')
                self.addCleanup(trial.close); fixture(trial); value = manifest()
                (trial.root/'pixels.png').write_bytes(png(16,16,repaired_pixels()))
                if alteration == 'bool-transform': value['transform'][4] = False
                elif alteration == 'id': value['id'] = 'other'
                elif alteration == 'resource': value['image'] = '../external.png'
                elif alteration == 'dimensions': value['width'] = 17
                elif alteration == 'extra': value['mask'] = 'unrequested.png'
                elif alteration == 'missing': (trial.root/'pixels.png').unlink()
                elif alteration == 'oversized': (trial.root/'pixels.png').write_bytes(b' '*(64*1024+1))
                save_json(trial.root/'editable.json',value)
                if alteration == 'none': self.assertEqual(admitted_manifest(trial),manifest())
                else:
                    with self.assertRaises(TaskFailure): admitted_manifest(trial)

    def test_pinned_decoder_validates_result_shape_and_sample_count(self):
        with tempfile.TemporaryDirectory() as directory:
            case = SimpleNamespace(root=Path(directory)); payload = dict(pixels=repaired_pixels().hex())
            with patch('benchmark_baseline_retouch.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(payload).encode())) as launch:
                self.assertEqual(decode_pixels(case,fake_tools()),repaired_pixels())
                self.assertEqual(launch.call_args.args[0][:2],[sys.executable,'-I']); self.assertEqual(launch.call_args.kwargs['timeout'],30)
            for code,value in ((1,payload),(0,{}),(0,dict(pixels='00')),(0,dict(pixels='bad'))):
                with patch('benchmark_baseline_retouch.subprocess.run',return_value=SimpleNamespace(returncode=code,stdout=json.dumps(value).encode())):
                    with self.assertRaises((TaskFailure,ValueError)): decode_pixels(case,fake_tools())


if __name__ == '__main__': unittest.main()
