"""B07 rejudges logical source, glyph declarations, pixels and saved snapshots."""
import json
from functools import lru_cache
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from test_cli import EXE, ROOT
sys.path.insert(0,str(ROOT/'tools'))
from agent_benchmark import run_task
from benchmark_typography import (fixture, solve, judge, PROMPT, TYPOGRAPHY, named_font,
    expected_picture, authored_geometry, shaping_report, typography_document)
from benchmark_baseline_typography import svg_typography, judge_typography
from benchmark_driver import run_external_task, workspace_files
from benchmark_runtime import Trial, TaskFailure
from benchmark_graphics import png_check
from benchmark_tasks import CHECKS
from benchmark_fake_driver import typography_svg
from test_benchmark_driver import driver, fake_tools
from test_images_cli import png
from synthetic_bidi_font import bidi_font
from synthetic_variable_font import tables
from workload_cases import sha, save_json


class BenchmarkTypographyTests(unittest.TestCase):
    def prepare(self, root, independent_names=False):
        trial = Trial(EXE,root,'B07',1,'cli',CHECKS['B07'])
        self.addCleanup(trial.close)
        if independent_names:
            call = trial.call
            def renamed(step, command, **arguments):
                if arguments.get('session_id') == 'work': arguments['session_id'] = 'artist-type'
                if command == 'session.create':
                    doc = typography_document('artist-sheet','artist-font',arguments['document']['fonts']['face'])
                    doc['metadata'] = {'title':'Multilingual study'}
                    for i,item in enumerate(doc['items']):
                        item.update(id=f'artist-{i}',name=f'Study row {i}',metadata={'title':f'Row {i}'})
                    arguments['document'] = doc
                if command == 'text.inspect' and arguments['id'].startswith('row-'):
                    arguments['id'] = arguments['id'].replace('row-','artist-')
                return call('artist-'+step,command,**arguments)
            trial.call = renamed
        fixture(trial); trial.begin(PROMPT.read_text(encoding='utf-8')); solve(trial)
        return trial

    def test_named_font_changes_only_name_records_and_keeps_original_fixture_identity(self):
        original = bidi_font()
        self.assertEqual(sha(original),'61e6b5aca4ce38f9094b657a912c56ea6b03b6ee070a9d45a6c9ebebaaf2d574')
        old,new = tables(original),tables(named_font())
        self.assertEqual(set(new)-set(old),{b'name'})
        self.assertEqual({k:v for k,v in new.items() if k != b'name'},old)

    def test_both_reference_transports_separate_judging_and_preserve_check_inventory(self):
        for transport in ('cli','mcp'):
            with self.subTest(transport=transport), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)/transport
                row = run_task(EXE,root,'B07',1,transport)
                self.assertEqual(row['status'],'passed',row)
                self.assertEqual({c['name'] for c in row['checks']},set(CHECKS['B07'])|{'source-preservation'})
                self.assertEqual(row['engine_commands'],9); self.assertEqual(row['judge_engine_commands'],9)
                self.assertTrue(row['judge_separated']); self.assertGreater(row['first_verified_preview_seconds'],0)
                for direction in ('request','response'):
                    self.assertEqual(row[direction+'_bytes']+row['judge_'+direction+'_bytes'],
                        sum(p.stat().st_size for p in root.glob('*.'+direction+'.json')))

    def test_judge_uses_deliveries_and_arbitrary_author_ids_without_solver_results(self):
        with tempfile.TemporaryDirectory() as directory:
            trial = self.prepare(Path(directory)/'independent',True)
            trial.results.clear(); trial.begin_judging(); judge(trial)
            row = trial.finish()
            self.assertEqual(row['status'],'passed',row)
            self.assertIsNone(row['first_verified_preview_seconds'])

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

    def test_external_capture_rejudges_fonts_snapshot_and_shaping_after_relocation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); configuration = driver()
            row = run_external_task(EXE,root/'live','B07',1,'model',configuration)
            self.assertEqual(row['status'],'passed',row)
            self.assertFalse(row['model_trials']); self.assertIsNone(row['model_calls'])
            before = workspace_files(root/'live/workspace')
            imported = run_external_task(EXE,root/'import','B07',1,'model',configuration,import_source=root/'live')
            self.assertEqual(imported['status'],'passed',imported)
            self.assertEqual(row['checks'],imported['checks'])
            self.assertEqual(before,workspace_files(root/'live/workspace'))
            self.assertEqual(before,workspace_files(root/'import/workspace'))

    def test_baseline_does_not_launch_engine_and_checks_both_rendered_and_delivered_pixels(self):
        for incorrect in ('none','delivery','fresh-render'):
            with self.subTest(incorrect=incorrect), tempfile.TemporaryDirectory() as directory:
                configuration = driver('--preview-usage',*(['--wrong-image'] if incorrect == 'delivery' else []))
                raw = png(1,1,b'\0'*4) if incorrect == 'fresh-render' else png(1000,960,expected_picture())
                with patch('benchmark_baseline_typography.render_typography',return_value=raw), \
                     patch('benchmark_driver.ExternalTrial.call',side_effect=AssertionError('Baseline launched Inkbolt')):
                    row = run_external_task(None,Path(directory)/'baseline','B07',1,'baseline',configuration,fake_tools())
                self.assertEqual(row['status'],'passed' if incorrect == 'none' else 'failed',row)
                self.assertEqual(row['first_verified_preview_seconds'],.5 if incorrect == 'none' else None)
                checks = {c['name']:c['status'] for c in row['checks']}
                self.assertEqual(checks['glyph-cluster-order'],'fail' if incorrect == 'fresh-render' else 'pass')
                for name in ('editable-text-and-font','history-valid'): self.assertEqual(checks[name],'not_applicable')

    def test_baseline_rejects_invented_mapping_even_with_correct_svg_and_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            trial = Trial(None,Path(directory)/'baseline','B07',1,'cli',CHECKS['B07'],arm='baseline')
            self.addCleanup(trial.close); fixture(trial); trial.begin(PROMPT.read_text(encoding='utf-8'))
            report = shaping_report(authored_geometry()[0]); report['rows'][2]['glyphs'][3][2] = 3
            save_json(trial.root/'shaping.json',report)
            (trial.root/'editable.svg').write_text(typography_svg([text for text,_ in TYPOGRAPHY]),encoding='utf-8')
            raw = png(1000,960,expected_picture()); (trial.root/'preview.png').write_bytes(raw)
            trial.begin_judging()
            with patch('benchmark_baseline_typography.render_typography',return_value=raw): judge_typography(trial,fake_tools())
            checks = {c['name']:c['status'] for c in trial.checks}
            self.assertEqual(checks['glyph-cluster-order'],'fail'); self.assertEqual(checks['typography-pixels'],'pass')

    def test_svg_admission_keeps_logical_text_and_rejects_font_resource_and_layout_changes(self):
        source = typography_svg([text for text,_ in TYPOGRAPHY])
        self.assertEqual(len(svg_typography(source.encode())),4)
        self.assertEqual(len(svg_typography(source.replace('#145096','rgb(20,80,150)').encode())),4)
        # Plain runs are admissible too; actual renderer pixels decide whether
        # their shaping succeeds. Do not hide a renderer difference in admission.
        self.assertEqual(len(svg_typography(typography_svg([text for text,_ in TYPOGRAPHY],False).encode())),4)
        for text in (source.replace('Inkbolt Typography Fixture','Other Font'),source.replace('font-size="200"','font-size="201"'),
                     source.replace('y="440"','y="441"'),source.replace('x="260"','x="1001"'),
                     source.replace(TYPOGRAPHY[0][0],'different logical source'),source.replace('#145096','url(file:///external)'),
                     source.replace('<text ','<path ',1),source.replace('<tspan ','<image ',1),
                     source.replace('</svg>','<style>text{fill:black}</style></svg>'), '<!DOCTYPE svg>'+source,
                     source.replace('width="1000"','width="999999999"'),source+' '*(64*1024)):
            with self.assertRaises((TaskFailure,ValueError,ET.ParseError)): svg_typography(text.encode())


if __name__ == '__main__': unittest.main()
