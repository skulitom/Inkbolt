"""B07 font fixtures, editable text and delivered glyphs."""
import json
from functools import lru_cache
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_cli import EXE, ROOT
sys.path.insert(0,str(ROOT/'tools'))

from benchmark_typography import fixture, solve, judge, PROMPT, named_font, typography_document
from benchmark_runtime import Trial, TaskFailure
from benchmark_graphics import png_check
from benchmark_tasks import CHECKS
from test_images_cli import png
from synthetic_bidi_font import bidi_font
from synthetic_variable_font import tables
from workload_cases import sha


class TypographyJudgeTests(unittest.TestCase):
    def prepare(self, root, independent_names=False, first_baseline=None):
        trial = Trial(EXE,root,'B07',1,'cli',CHECKS['B07'])
        self.addCleanup(trial.close)
        if independent_names or first_baseline is not None:
            call = trial.call
            def authored(step, command, **arguments):
                if independent_names:
                    if arguments.get('session_id') == 'work': arguments['session_id'] = 'artist-type'
                    if command == 'session.create':
                        doc = typography_document('artist-sheet','artist-font',arguments['document']['fonts']['face'])
                        doc['metadata'] = {'title':'Multilingual study'}
                        for i,item in enumerate(doc['items']):
                            item.update(id=f'artist-{i}',name=f'Study row {i}',metadata={'title':f'Row {i}'})
                        arguments['document'] = doc
                    if command == 'text.inspect' and arguments['id'].startswith('row-'):
                        arguments['id'] = arguments['id'].replace('row-','artist-')
                if command == 'session.create' and first_baseline is not None:
                    for item in arguments['document']['items']:
                        item['content']['frame']['first_baseline'] = dict(first_baseline)
                return call('authored-'+step,command,**arguments)
            trial.call = authored
        fixture(trial); trial.begin(PROMPT.read_text(encoding='utf-8')); solve(trial)
        return trial

    def test_named_font_changes_only_name_records_and_keeps_original_fixture_identity(self):
        original = bidi_font()
        self.assertEqual(sha(original),'61e6b5aca4ce38f9094b657a912c56ea6b03b6ee070a9d45a6c9ebebaaf2d574')
        old,new = tables(original),tables(named_font())
        self.assertEqual(set(new)-set(old),{b'name'})
        self.assertEqual({k:v for k,v in new.items() if k != b'name'},old)

    def test_judge_uses_deliveries_and_arbitrary_author_ids_without_solver_results(self):
        with tempfile.TemporaryDirectory() as directory:
            trial = self.prepare(Path(directory)/'independent',True)
            trial.results.clear(); trial.begin_judging(); judge(trial)
            row = trial.finish()
            self.assertEqual(row['status'],'passed',row)
            self.assertIsNone(row['first_verified_preview_seconds'])

    def test_explicit_baseline_placement_keeps_independent_glyph_and_pixel_oracles(self):
        for metric,minimum,valid in (('fixed',200,True),('ascent',0,True),('fixed',199,False)):
            with self.subTest(metric=metric,minimum=minimum), tempfile.TemporaryDirectory() as directory:
                trial = self.prepare(Path(directory)/'baseline',first_baseline=dict(metric=metric,minimum=minimum))
                trial.results.clear(); trial.begin_judging(); judge(trial)
                row = trial.finish(); checks = {check['name']:check['status'] for check in row['checks']}
                self.assertEqual(row['status'],'passed' if valid else 'failed',row)
                self.assertEqual(checks['editable-text-and-font'],'pass')
                self.assertEqual(checks['history-valid'],'pass')
                for name in ('glyph-cluster-order','typography-pixels'):
                    self.assertEqual(checks[name],'pass' if valid else 'fail',row)

    def test_solver_logs_cannot_hide_false_clusters_changed_source_or_unrelated_history(self):
        # Reuse only exact raw PNG/dimensions/expected-byte tuples inside this
        # mutation test. Every candidate still reopens and renders through the
        # real engine; altered PNGs always decode independently.
        with tempfile.TemporaryDirectory() as directory, \
             patch('benchmark_typography.png_check',lru_cache(maxsize=8)(png_check)):
            trial = self.prepare(Path(directory)/'delivery')
            originals = {name:(trial.root/name).read_bytes() for name in
                ('editable.json','shaping.json','preview.png','session.json','texts.json','font-license.txt','task.txt')}
            call,check = trial.call,trial.check
            solve_calls = list(trial.calls)
            trial.call = lambda step,command,**kw: call(alteration+'-'+step,command,**kw)
            def reject_early(name, oracle, **kw):
                if not check(name,oracle,**kw): raise TaskFailure('Independent check rejected '+name)
            trial.check = reject_early; trial.begin_judging()
            for alteration in ('glyph','cluster','origin','advance','bool-offset','units','logical-report','text','position',
                               'wrap','fill','font','visibility','preview','revision','other-session','missing','source','license','prompt','none','newer-head'):
                with self.subTest(alteration=alteration):
                    for name,raw in originals.items(): (trial.root/name).write_bytes(raw)
                    trial.checks.clear(); trial.error = None
                    trial.calls = list(solve_calls); trial.check = reject_early
                    trial.result_path = trial.root/(alteration+'-result.json')
                    actual = json.loads(originals['editable.json']); report = json.loads(originals['shaping.json'])
                    if alteration == 'glyph': report['rows'][1]['glyphs'][2][0] = 9
                    elif alteration == 'cluster': report['rows'][2]['glyphs'][3][1] = 3
                    elif alteration == 'origin': report['rows'][0]['glyphs'][0][3][0] = 1
                    elif alteration == 'advance': report['rows'][0]['glyphs'][0][4] = 121
                    elif alteration == 'bool-offset': report['rows'][0]['glyphs'][0][1] = False
                    elif alteration == 'units': report['indices'] = 'utf8_bytes'
                    elif alteration == 'logical-report': report['rows'][2]['text'] = 'normalized'
                    elif alteration == 'text': actual['items'][1]['content']['frame']['text'] = 'A'
                    elif alteration == 'position': actual['items'][2]['transform'][5] = 481
                    elif alteration == 'wrap': actual['items'][0]['content']['frame']['wrap'] = True
                    elif alteration == 'fill': actual['items'][0]['content']['frame']['style']['fill'] = [0,0,0,255]
                    elif alteration == 'font': actual['fonts']['face']['license_sha256'] = '0'*64
                    elif alteration == 'visibility': actual['items'][0]['visible'] = False
                    elif alteration == 'preview': (trial.root/'preview.png').write_bytes(png(1,1,b'\0'*4))
                    elif alteration in ('revision','other-session'):
                        locator = json.loads(originals['session.json'])
                        if alteration == 'revision': locator['current_revision'] = False
                        else:
                            other = json.loads(originals['editable.json']); other['metadata'] = {'title':'Different document'}
                            trial.call('other-save','session.create',session_id='other',request_id='save',document=other,response_mode='compact')
                            locator['session_id'] = 'other'
                        (trial.root/'session.json').write_text(json.dumps(locator),encoding='utf-8')
                    elif alteration == 'source': (trial.root/'texts.json').write_bytes(b'[]')
                    elif alteration == 'license': (trial.root/'font-license.txt').write_bytes(b'changed')
                    elif alteration == 'prompt': (trial.root/'task.txt').write_text('changed',encoding='utf-8')
                    elif alteration == 'newer-head':
                        trial.call('later-edit','session.apply',session_id='work',request_id='later',expected_revision=0,
                            action=dict(type='edit',operations=[dict(op='transform',id='row-0',matrix=[1,0,0,1,1,0],space='world')]),response_mode='compact')
                    (trial.root/'editable.json').write_text(json.dumps(actual),encoding='utf-8')
                    (trial.root/'shaping.json').write_text(json.dumps(report),encoding='utf-8')
                    if alteration == 'missing': (trial.root/'shaping.json').unlink()
                    try: judge(trial)
                    except (TaskFailure,ValueError,KeyError) as error: trial.error = str(error)
                    trial.check = check
                    self.assertEqual(trial.finish()['status'],'passed' if alteration == 'none' else 'failed',alteration)


if __name__ == '__main__': unittest.main()
