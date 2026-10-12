"""B02 judges read deliveries, preserve task criteria and never grant fake model credit."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_cli import EXE, ROOT
sys.path.insert(0, str(ROOT/'tools'))
from agent_benchmark import run_task
from benchmark_icons import fixture, solve, judge, PROMPT, expected_board
from benchmark_baseline_icons import svg_boards
from benchmark_driver import run_external_task, workspace_files
from benchmark_runtime import Trial, TaskFailure
from benchmark_tasks import CHECKS
from benchmark_fake_driver import ICONS_SVG
from test_benchmark_driver import driver, fake_tools
from test_images_cli import png


class BenchmarkIconTests(unittest.TestCase):
    def prepare(self, root, alternate_session=False):
        trial = Trial(EXE, root, 'B02', 1, 'cli', CHECKS['B02'])
        self.addCleanup(trial.close)
        if alternate_session:
            original = trial.call
            def call(step, command, **arguments):
                if command == 'session.create':
                    arguments.update(session_id='artist-chosen-session', request_id='artist-save')
                return original(step, command, **arguments)
            trial.call = call
        fixture(trial); trial.begin(PROMPT.read_text(encoding='utf-8')); solve(trial)
        return trial

    def test_both_reference_transports_preserve_checks_and_separate_judge_traffic(self):
        for transport in ('cli','mcp'):
            with self.subTest(transport=transport), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)/transport
                row = run_task(EXE, root, 'B02', 1, transport)
                self.assertEqual(row['status'], 'passed', row)
                self.assertEqual({c['name'] for c in row['checks']}, set(CHECKS['B02'])|{'source-preservation'})
                self.assertEqual(row['judge_engine_commands'], 4)
                self.assertTrue(row['judge_separated'])
                self.assertGreater(row['first_verified_preview_seconds'], 0)
                for direction in ('request', 'response'):
                    self.assertEqual(row[direction+'_bytes'] + row['judge_'+direction+'_bytes'],
                                     sum(p.stat().st_size for p in root.glob('*.'+direction+'.json')))

    def test_judge_reads_artifacts_and_allows_independent_document_and_session_names(self):
        with tempfile.TemporaryDirectory() as directory:
            trial = self.prepare(Path(directory)/'delivery', alternate_session=True)
            path = trial.root/'editable.json'; document = json.loads(path.read_bytes())
            document['id'] = 'another-author'
            path.write_text(json.dumps(document), encoding='utf-8')
            trial.results.clear(); trial.begin_judging(); judge(trial)
            row = trial.finish()
            self.assertEqual(row['status'], 'passed', row)
            self.assertIsNone(row['first_verified_preview_seconds'])
            self.assertFalse(row['model_trials'])

    def test_correct_solver_logs_cannot_hide_corrupt_or_missing_deliverables(self):
        for alteration in ('spacing','owner','id','order','canvas','role','pixels','visibility','missing','prompt'):
            with self.subTest(alteration=alteration), tempfile.TemporaryDirectory() as directory:
                trial = self.prepare(Path(directory)/alteration)
                path = trial.root/'editable.json'; document = json.loads(path.read_bytes())
                if alteration == 'spacing': document['items'][2]['transform'][4] = 39
                elif alteration == 'owner': document['items'][1]['parent'] = 'board-1'
                elif alteration == 'id': document['items'][1]['id'] = 'changed-icon'
                elif alteration == 'order': document['items'][1],document['items'][3] = document['items'][3],document['items'][1]
                elif alteration == 'canvas': document['width'] = 111
                elif alteration == 'role': document['items'][0]['content']['frame']['role'] = 'page'
                elif alteration == 'visibility': document['items'][3]['visible'] = False
                elif alteration == 'pixels': (trial.root/'board-1.png').write_bytes(png(32,32,expected_board(0)))
                elif alteration == 'missing': (trial.root/'board-2.png').unlink()
                else: (trial.root/'task.txt').write_text('changed original prompt')
                path.write_text(json.dumps(document), encoding='utf-8')
                trial.begin_judging()
                try: judge(trial)
                except (TaskFailure,ValueError,KeyError) as error: trial.error = str(error)
                self.assertEqual(trial.finish()['status'], 'failed')

    def test_external_model_and_import_rejudge_all_three_boards_with_unknown_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); configuration = driver()
            row = run_external_task(EXE, root/'live', 'B02', 1, 'model', configuration)
            self.assertEqual(row['status'], 'passed', row)
            self.assertEqual(row['judge_engine_commands'], 4)
            self.assertFalse(row['model_trials']); self.assertIsNone(row['model_calls'])
            before = workspace_files(root/'live/workspace')
            imported = run_external_task(EXE, root/'import', 'B02', 1, 'model', configuration, import_source=root/'live')
            self.assertEqual(imported['status'], 'passed', imported)
            self.assertEqual(row['checks'], imported['checks'])
            self.assertEqual(before, workspace_files(root/'live/workspace'))
            self.assertEqual(before, workspace_files(root/'import/workspace'))

    def test_baseline_is_engine_free_and_preview_usage_requires_its_judged_board(self):
        for incorrect in (False,True):
            with self.subTest(incorrect=incorrect), tempfile.TemporaryDirectory() as directory:
                configuration = driver('--preview-usage', *(['--wrong-image'] if incorrect else []))
                with patch('benchmark_baseline_icons.render_board', side_effect=lambda c,t,i,s: png(32,32,expected_board(i))),\
                     patch('benchmark_driver.ExternalTrial.call', side_effect=AssertionError('Baseline launched Inkbolt')):
                    row = run_external_task(None, Path(directory)/'baseline', 'B02', 1, 'baseline', configuration, fake_tools())
                self.assertEqual(row['status'], 'failed' if incorrect else 'passed', row)
                self.assertEqual(row['first_verified_preview_seconds'], None if incorrect else .5)
                self.assertFalse(row['model_trials'])
                self.assertEqual({c['name']:c['status'] for c in row['checks']}['editable-source'], 'not_applicable')

    def test_svg_admission_retains_independent_viewports_and_rejects_wrong_sources(self):
        self.assertEqual(len(svg_boards(ICONS_SVG.encode())), 3)
        shifted = ICONS_SVG.replace('x="12" y="11"', 'transform="translate(12,11)" x="0" y="0"')
        self.assertEqual(len(svg_boards(shifted.encode())), 3)
        for source in [ICONS_SVG.replace('x="40"','x="39"'),
                       ICONS_SVG.replace('id="icon-1"','id="icon-0"'),
                       ICONS_SVG.replace('height="32"','height="999999999"',1),
                       ICONS_SVG.replace('width="8"','width="7"',1),
                       ICONS_SVG.replace('<rect','<image',1),
                       ICONS_SVG.replace('fill="#145096"','fill="url(file:///external)"'),
                       ICONS_SVG.replace('id="board-0"','id="board-0" overflow="visible"'),
                       '<!DOCTYPE svg>'+ICONS_SVG]:
            with self.assertRaises((TaskFailure,ValueError)):
                svg_boards(source.encode())


if __name__ == '__main__': unittest.main()
