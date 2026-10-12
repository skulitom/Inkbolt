"""B05 judges delivered swatch references, pixels and bound session history."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_cli import EXE, ROOT
sys.path.insert(0,str(ROOT/'tools'))
from agent_benchmark import run_task
from benchmark_palette import fixture, solve, judge, PROMPT, expected_picture, swatch
from benchmark_baseline_palette import svg_palette
from benchmark_driver import run_external_task, workspace_files
from benchmark_runtime import Trial, TaskFailure
from benchmark_graphics import ORANGE
from benchmark_tasks import CHECKS
from benchmark_fake_driver import palette_svg
from test_benchmark_driver import driver, fake_tools
from test_images_cli import png


class BenchmarkPaletteTests(unittest.TestCase):
    def prepare(self, root, alternate_session=False):
        trial = Trial(EXE,root,'B05',1,'cli',CHECKS['B05'])
        self.addCleanup(trial.close)
        if alternate_session:
            call = trial.call
            def renamed(step, command, **arguments):
                if arguments.get('session_id') == 'work': arguments['session_id'] = 'artist-palette'
                return call('artist-'+step,command,**arguments)
            trial.call = renamed
        fixture(trial); trial.begin(PROMPT.read_text(encoding='utf-8')); solve(trial)
        return trial

    def test_reference_transports_separate_judging_and_keep_all_checks(self):
        for transport in ('cli','mcp'):
            with self.subTest(transport=transport), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)/transport
                row = run_task(EXE,root,'B05',1,transport)
                self.assertEqual(row['status'],'passed',row)
                self.assertEqual({c['name'] for c in row['checks']},set(CHECKS['B05'])|{'source-preservation'})
                self.assertTrue(row['judge_separated'])
                self.assertEqual(row['judge_engine_commands'],7)
                self.assertEqual(row['engine_commands'],7)
                self.assertGreater(row['first_verified_preview_seconds'],0)
                for direction in ('request','response'):
                    self.assertEqual(row[direction+'_bytes']+row['judge_'+direction+'_bytes'],
                        sum(p.stat().st_size for p in root.glob('*.'+direction+'.json')))

    def test_judge_reads_deliveries_and_author_chosen_session_without_solver_results(self):
        with tempfile.TemporaryDirectory() as directory:
            trial = self.prepare(Path(directory)/'independent',True)
            trial.results.clear(); trial.begin_judging(); judge(trial)
            row = trial.finish()
            self.assertEqual(row['status'],'passed',row)
            self.assertIsNone(row['first_verified_preview_seconds'])
            self.assertEqual(json.loads((trial.root/'session.json').read_bytes())['session_id'],'artist-palette')

    def test_correct_solver_logs_cannot_hide_broken_links_collateral_edits_or_false_history(self):
        for alteration in ('flattened','one-link','unrelated','swatch-name','geometry','order','canvas','metadata',
                           'preview','historical','revision','other-session','newer-head','missing','source','prompt'):
            with self.subTest(alteration=alteration), tempfile.TemporaryDirectory() as directory:
                trial = self.prepare(Path(directory)/alteration)
                path = trial.root/'editable.json'; actual = json.loads(path.read_bytes())
                if alteration == 'flattened':
                    for item in actual['items'][:2]: item['content']['fill'] = ORANGE
                elif alteration == 'one-link': actual['items'][0]['content']['fill'] = ORANGE
                elif alteration == 'unrelated': actual['items'][2]['content']['fill'] = ORANGE
                elif alteration == 'swatch-name': actual['swatches']['shared']['name'] = 'Renamed'
                elif alteration == 'geometry': actual['items'][0]['content']['geometry']['x'] = 3
                elif alteration == 'order': actual['items'][0],actual['items'][1] = actual['items'][1],actual['items'][0]
                elif alteration == 'canvas': actual['width'] = 33
                elif alteration == 'metadata': actual['metadata'] = {'title':'Unrequested'}
                elif alteration == 'preview': (trial.root/'preview.png').write_bytes(png(32,16,expected_picture(False)))
                elif alteration == 'historical': (trial.root/'historical.png').write_bytes(png(32,16,expected_picture()))
                elif alteration in ('revision','other-session'):
                    locator = json.loads((trial.root/'session.json').read_bytes())
                    if alteration == 'revision': locator['original_revision'] = True
                    else:
                        # A valid history with identical pixels still needs to
                        # contain the original fixture and delivered snapshot.
                        other = json.loads((trial.root/'source.json').read_bytes())
                        other['metadata'] = {'title':'Different source'}
                        trial.call('other-save','session.create',session_id='other',request_id='save',document=other,response_mode='compact')
                        trial.call('other-edit','session.apply',session_id='other',request_id='edit',expected_revision=0,
                            action=dict(type='edit',operations=[dict(op='swatch',id='shared',swatch=swatch(ORANGE))]),response_mode='compact')
                        locator['session_id'] = 'other'
                    (trial.root/'session.json').write_text(json.dumps(locator),encoding='utf-8')
                elif alteration == 'newer-head':
                    trial.call('later-edit','session.apply',session_id='work',request_id='later',expected_revision=1,
                        action=dict(type='edit',operations=[dict(op='transform',id='first',matrix=[1,0,0,1,1,0],space='world')]),response_mode='compact')
                elif alteration == 'missing': (trial.root/'historical.png').unlink()
                elif alteration == 'source': (trial.root/'source.json').write_bytes(b'{}')
                elif alteration == 'prompt': (trial.root/'task.txt').write_text('changed',encoding='utf-8')
                path.write_text(json.dumps(actual),encoding='utf-8')
                trial.begin_judging()
                try: judge(trial)
                except (TaskFailure,ValueError,KeyError) as error: trial.error = str(error)
                self.assertEqual(trial.finish()['status'],'failed',alteration)

    def test_external_capture_is_rejudged_after_relocation_without_mutating_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); configuration = driver()
            row = run_external_task(EXE,root/'live','B05',1,'model',configuration)
            self.assertEqual(row['status'],'passed',row)
            self.assertFalse(row['model_trials']); self.assertIsNone(row['model_calls'])
            before = workspace_files(root/'live/workspace')
            imported = run_external_task(EXE,root/'import','B05',1,'model',configuration,import_source=root/'live')
            self.assertEqual(imported['status'],'passed',imported)
            self.assertEqual(row['checks'],imported['checks'])
            self.assertEqual(before,workspace_files(root/'live/workspace'))
            self.assertEqual(before,workspace_files(root/'import/workspace'))

    def test_baseline_never_calls_engine_and_checks_both_fresh_render_and_delivered_preview(self):
        for incorrect in ('none','delivery','fresh-render'):
            with self.subTest(incorrect=incorrect), tempfile.TemporaryDirectory() as directory:
                configuration = driver('--preview-usage',*(['--wrong-image'] if incorrect == 'delivery' else []))
                with patch('benchmark_baseline_palette.render_palette',return_value=png(32,16,expected_picture(incorrect != 'fresh-render'))), \
                     patch('benchmark_driver.ExternalTrial.call',side_effect=AssertionError('Baseline launched Inkbolt')):
                    row = run_external_task(None,Path(directory)/'baseline','B05',1,'baseline',configuration,fake_tools())
                self.assertEqual(row['status'],'passed' if incorrect == 'none' else 'failed',row)
                self.assertEqual(row['first_verified_preview_seconds'],.5 if incorrect == 'none' else None)
                self.assertFalse(row['model_trials'])
                checks = {c['name']:c['status'] for c in row['checks']}
                for name in ('live-dependencies','historical-pixels','history-valid'):
                    self.assertEqual(checks[name],'not_applicable')

    def test_svg_admission_preserves_unrelated_paint_geometry_and_bounded_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            trial = Trial(None,Path(directory)/'source','B05',1,'cli',CHECKS['B05'])
            self.addCleanup(trial.close)
            fixture(trial)
            source = palette_svg(json.loads((trial.root/'source.json').read_bytes()))
        self.assertEqual(len(svg_palette(source.encode())),3)
        self.assertEqual(len(svg_palette(source.replace('#dc5a1e','rgb(220,90,30)').replace('#1e9646','rgb(30,150,70)').encode())),3)
        self.assertEqual(len(svg_palette(source.replace('id="first"','id="first" transform="matrix(1,0,0,1,0,0)"').encode())),3)
        for text in (source.replace('x="2"','x="3"'),source.replace('id="first"','id="second"'),
                     source.replace('#dc5a1e','#145096',1),source.replace('#1e9646','#dc5a1e'),
                     source.replace('width="32"','width="999999999"'),source.replace('<rect','<image',1),
                     source.replace('#dc5a1e','url(file:///external)',1),source.replace('id="first"','id="first" opacity="0.5"'),
                     source.replace('id="first"','id="first" transform="translate(1,0)"'),
                     source.replace('</svg>','<style>rect{fill:black}</style></svg>'), '<!DOCTYPE svg>'+source,
                     source+' '*(64*1024)):
            with self.assertRaises((TaskFailure,ValueError)):
                svg_palette(text.encode())


if __name__ == '__main__': unittest.main()
