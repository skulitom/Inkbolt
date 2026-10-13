"""B06 artifact/history checks must not trust solver state or report claims."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from test_cli import EXE, ROOT
sys.path.insert(0,str(ROOT/'tools'))
from agent_benchmark import run_task
from benchmark_flow import fixture, solve, judge, PROMPT, expected_picture, expected_lines, repaired, read_report
from benchmark_baseline_flow import svg_flow, judge_flow, same_json
from benchmark_driver import run_external_task, workspace_files
from benchmark_runtime import Trial, TaskFailure
from benchmark_tasks import CHECKS
from benchmark_fake_driver import flow_svg
from test_benchmark_driver import driver, fake_tools
from test_images_cli import png
from workload_cases import save_json


class BenchmarkFlowTests(unittest.TestCase):
    def prepare(self, root, alternate_session=False):
        trial = Trial(EXE,root,'B06',1,'cli',CHECKS['B06'])
        self.addCleanup(trial.close)
        if alternate_session:
            call = trial.call
            def renamed(step, command, **arguments):
                if arguments.get('session_id') == 'work': arguments['session_id'] = 'artist-flow'
                return call('artist-'+step,command,**arguments)
            trial.call = renamed
        fixture(trial); trial.begin(PROMPT.read_text(encoding='utf-8')); solve(trial)
        return trial

    def test_reference_transports_keep_all_checks_and_separate_judge_traffic(self):
        for transport in ('cli','mcp'):
            with self.subTest(transport=transport), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)/transport
                row = run_task(EXE,root,'B06',1,transport)
                self.assertEqual(row['status'],'passed',row)
                self.assertEqual({c['name'] for c in row['checks']},set(CHECKS['B06'])|{'source-preservation'})
                self.assertEqual(row['engine_commands'],10)
                self.assertEqual(row['judge_engine_commands'],9)
                self.assertTrue(row['judge_separated'])
                self.assertGreater(row['first_verified_preview_seconds'],0)
                for direction in ('request','response'):
                    self.assertEqual(row[direction+'_bytes']+row['judge_'+direction+'_bytes'],
                        sum(p.stat().st_size for p in root.glob('*.'+direction+'.json')))

    def test_judge_uses_authors_session_and_deliveries_without_solver_results(self):
        with tempfile.TemporaryDirectory() as directory:
            trial = self.prepare(Path(directory)/'independent',True)
            trial.results.clear(); trial.begin_judging(); judge(trial)
            row = trial.finish()
            self.assertEqual(row['status'],'passed',row)
            self.assertIsNone(row['first_verified_preview_seconds'])
            self.assertEqual(json.loads((trial.root/'session.json').read_bytes())['session_id'],'artist-flow')

    def test_correct_solver_logs_cannot_hide_false_reports_collateral_edits_or_history(self):
        for alteration in ('diagnosis','interval','final-overflow','bool-offset','text','first-slot','second-slot',
                           'unrelated','font','metadata','preview','revision','other-session','newer-head','missing','source','license','prompt'):
            with self.subTest(alteration=alteration), tempfile.TemporaryDirectory() as directory:
                trial = self.prepare(Path(directory)/alteration)
                report = json.loads((trial.root/'flow-report.json').read_bytes())
                actual = json.loads((trial.root/'editable.json').read_bytes())
                if alteration == 'diagnosis': report['original_overset']['offset'] = 9
                elif alteration == 'interval': report['lines'][-1]['start'] = 8
                elif alteration == 'final-overflow': report['final_overset'] = dict(paragraph=0,offset=8)
                elif alteration == 'bool-offset': report['lines'][0]['paragraph'] = False
                elif alteration == 'text': actual['stories']['article']['paragraphs'][0]['text'] = 'A'*10
                elif alteration == 'first-slot': actual['stories']['article']['slots'][0]['width'] = 25
                elif alteration == 'second-slot': actual['stories']['article']['slots'][1]['gutter'] = 6
                elif alteration == 'unrelated': actual['items'][2]['content']['fill'] = [0,0,0,255]
                elif alteration == 'font': actual['fonts']['face']['license_sha256'] = '0'*64
                elif alteration == 'metadata': actual['metadata'] = {'title':'Unrequested'}
                elif alteration == 'preview': (trial.root/'preview.png').write_bytes(png(96,48,b'\0'*(96*48*4)))
                elif alteration in ('revision','other-session'):
                    locator = json.loads((trial.root/'session.json').read_bytes())
                    if alteration == 'revision': locator['original_revision'] = True
                    else:
                        other = json.loads((trial.root/'source.json').read_bytes()); other['metadata'] = {'title':'Different original'}
                        trial.call('other-save','session.create',session_id='other',request_id='save',document=other,response_mode='compact')
                        trial.call('other-edit','session.apply',session_id='other',request_id='edit',expected_revision=0,
                            action=dict(type='edit',operations=[dict(op='story',id='article',story=repaired(other)['stories']['article'])]),response_mode='compact')
                        locator['session_id'] = 'other'
                    (trial.root/'session.json').write_text(json.dumps(locator),encoding='utf-8')
                elif alteration == 'newer-head':
                    trial.call('later-edit','session.apply',session_id='work',request_id='later',expected_revision=1,
                        action=dict(type='edit',operations=[dict(op='transform',id='unrelated',matrix=[1,0,0,1,1,0],space='world')]),response_mode='compact')
                elif alteration == 'source': (trial.root/'source.json').write_bytes(b'{}')
                elif alteration == 'license': (trial.root/'font-license.txt').write_bytes(b'changed')
                elif alteration == 'prompt': (trial.root/'task.txt').write_text('changed',encoding='utf-8')
                (trial.root/'editable.json').write_text(json.dumps(actual),encoding='utf-8')
                (trial.root/'flow-report.json').write_text(json.dumps(report),encoding='utf-8')
                if alteration == 'missing': (trial.root/'flow-report.json').unlink()
                trial.begin_judging()
                try: judge(trial)
                except (TaskFailure,ValueError,KeyError) as error: trial.error = str(error)
                self.assertEqual(trial.finish()['status'],'failed',alteration)

    def test_external_capture_rejudges_relocated_saved_fonts_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); configuration = driver('--custom-font-store','--custom-session-store')
            row = run_external_task(EXE,root/'live','B06',1,'model',configuration)
            self.assertEqual(row['status'],'passed',row)
            self.assertFalse(row['model_trials']); self.assertIsNone(row['model_calls'])
            self.assertFalse((root/'live/workspace/.inkbolt/sessions').exists())
            self.assertFalse((root/'live/workspace/.inkbolt/fonts').exists())
            before = workspace_files(root/'live/workspace')
            imported = run_external_task(EXE,root/'import','B06',1,'model',configuration,import_source=root/'live')
            self.assertEqual(imported['status'],'passed',imported)
            self.assertEqual(row['checks'],imported['checks'])
            self.assertEqual(before,workspace_files(root/'live/workspace'))
            self.assertEqual(before,workspace_files(root/'import/workspace'))

    def test_retained_font_or_license_cannot_be_replaced_by_original_input(self):
        for flag in ('--corrupt-font-copy','--missing-font-license'):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as directory:
                row = run_external_task(EXE,Path(directory)/'broken','B06',1,'model',
                    driver('--custom-font-store','--custom-session-store',flag))
                self.assertEqual(row['status'],'failed',row)
                self.assertIn('Missing intact workspace font store',row['error'])

    def test_baseline_has_no_engine_and_verifies_delivered_and_fresh_pixels(self):
        for incorrect in ('none','delivery','fresh-render'):
            with self.subTest(incorrect=incorrect), tempfile.TemporaryDirectory() as directory:
                configuration = driver('--preview-usage',*(['--wrong-image'] if incorrect == 'delivery' else []))
                rendered = png(96,48,expected_picture() if incorrect != 'fresh-render' else b'\0'*(96*48*4))
                with patch('benchmark_baseline_flow.render_flow',return_value=rendered), \
                     patch('benchmark_driver.ExternalTrial.call',side_effect=AssertionError('Baseline launched Inkbolt')):
                    row = run_external_task(None,Path(directory)/'baseline','B06',1,'baseline',configuration,fake_tools())
                self.assertEqual(row['status'],'passed' if incorrect == 'none' else 'failed',row)
                self.assertEqual(row['first_verified_preview_seconds'],.5 if incorrect == 'none' else None)
                self.assertFalse(row['model_trials'])
                for check in row['checks']:
                    if check['name'] in ('historical-flow','history-valid'): self.assertEqual(check['status'],'not_applicable')

    def test_baseline_retained_layout_and_report_are_independently_checked(self):
        for alteration in ('none','diagnosis','interval','text','first-slot','columns','unrelated','font','bool-coordinate'):
            with self.subTest(alteration=alteration), tempfile.TemporaryDirectory() as directory:
                trial = Trial(None,Path(directory)/'baseline','B06',1,'cli',CHECKS['B06'],arm='baseline')
                self.addCleanup(trial.close); fixture(trial)
                trial.begin(PROMPT.read_text(encoding='utf-8'))
                source = json.loads((trial.root/'source.json').read_bytes()); layout = repaired(source)
                report = dict(original_overset=dict(paragraph=0,offset=8),final_overset=None,lines=expected_lines())
                if alteration == 'diagnosis': report['original_overset']['offset'] = 12
                elif alteration == 'interval': report['lines'][2]['end'] = 8
                elif alteration == 'text': layout['stories']['article']['paragraphs'][0]['text'] = 'A'*10
                elif alteration == 'first-slot': layout['stories']['article']['slots'][0]['width'] = 25
                elif alteration == 'columns': layout['stories']['article']['slots'][1]['columns'] = 1
                elif alteration == 'unrelated': layout['items'][2]['content']['fill'] = [0,0,0,255]
                elif alteration == 'font': layout['fonts']['face']['sha256'] = '0'*64
                elif alteration == 'bool-coordinate': layout['items'][0]['transform'][4] = False
                save_json(trial.root/'layout.json',layout); save_json(trial.root/'flow-report.json',report)
                (trial.root/'editable.svg').write_text(flow_svg(source),encoding='utf-8')
                (trial.root/'preview.png').write_bytes(png(96,48,expected_picture()))
                trial.begin_judging()
                with patch('benchmark_baseline_flow.render_flow',return_value=png(96,48,expected_picture())):
                    judge_flow(trial,fake_tools())
                self.assertEqual(any(c['status'] == 'fail' for c in trial.checks),alteration != 'none',trial.checks)
        self.assertTrue(same_json({'n':24.0,'flag':True},{'n':24,'flag':True}))
        self.assertFalse(same_json({'n':False},{'n':0}))

    def test_svg_admission_binds_text_intervals_frames_font_and_unrelated_artwork(self):
        with tempfile.TemporaryDirectory() as directory:
            trial = Trial(None,Path(directory)/'fixture','B06',1,'cli',CHECKS['B06'])
            self.addCleanup(trial.close); fixture(trial)
            source = flow_svg(json.loads((trial.root/'source.json').read_bytes()))
        self.assertEqual(svg_flow(source.encode()),expected_lines())
        self.assertEqual(svg_flow(source.replace('#145096','rgb(20,80,150)').replace('#1e9646','rgb(30,150,70)').encode()),expected_lines())
        for text in (source.replace('data-start="4"','data-start="2"'),source.replace('data-start="0"','data-start="false"'),
                     source.replace('>AA<','>A<',1),source.replace('width="56"','width="55"'),
                     source.replace('x="32"','x="31"',1),source.replace('y="16"','y="17"',1),
                     source.replace('font-size="20"','font-size="19"'),source.replace('Inkbolt Flow Fixture','Different Font'),
                     source.replace('#1e9646','#145096'),source.replace('width="96"','width="999999999"'),
                     source.replace('#145096','url(file:///external)',1),source.replace('<text ','<path ',1),
                     source.replace('</svg>','<style>text{fill:black}</style></svg>',1),'<!DOCTYPE svg>'+source,
                     source+' '*(64*1024)):
            with self.assertRaises((TaskFailure,ValueError,ET.ParseError)):
                svg_flow(text.encode())


if __name__ == '__main__': unittest.main()
