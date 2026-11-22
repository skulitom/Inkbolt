"""B03 compares final artifacts and bound history, independently of solver logs."""
import json
from functools import lru_cache
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_cli import EXE, ROOT
sys.path.insert(0, str(ROOT/'tools'))
from agent_benchmark import run_task
from benchmark_large_layout import fixture, expected_picture
from benchmark_baseline_large_layout import svg_layout
from benchmark_driver import run_external_task, workspace_files
from benchmark_runtime import Trial, TaskFailure
from benchmark_graphics import png_check
from benchmark_tasks import CHECKS
from benchmark_fake_driver import layout_svg
from test_benchmark_driver import driver, fake_tools
from test_images_cli import png


class BenchmarkLargeLayoutTests(unittest.TestCase):
    def setUp(self):
        # Re-judging a capture repeats identical images. Cache only exact raw
        # PNG/dimensions/expected-pixel tuples within this test; changed images
        # still run the independent decoder and every engine render still runs.
        checker = patch('benchmark_large_layout.png_check', lru_cache(maxsize=8)(png_check))
        checker.start()
        self.addCleanup(checker.stop)

    def test_both_reference_transports_separate_judging_and_keep_all_checks(self):
        for transport in ('cli','mcp'):
            with self.subTest(transport=transport), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)/transport
                row = run_task(EXE, root, 'B03', 1, transport)
                self.assertEqual(row['status'], 'passed', row)
                self.assertEqual({c['name'] for c in row['checks']}, set(CHECKS['B03'])|{'source-preservation'})
                self.assertEqual(row['judge_engine_commands'], 7)
                self.assertTrue(row['judge_separated'])
                self.assertGreater(row['first_verified_preview_seconds'], 0)
                for direction in ('request','response'):
                    self.assertEqual(row[direction+'_bytes']+row['judge_'+direction+'_bytes'],
                        sum(p.stat().st_size for p in root.glob('*.'+direction+'.json')))

    def test_external_model_capture_is_rejudged_without_mutating_its_workspace(self):
        for flags in (('--custom-session-store',),):
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); configuration = driver(*flags)
                row = run_external_task(EXE,root/'live','B03',1,'model',configuration)
                self.assertEqual(row['status'],'passed',row)
                self.assertFalse(row['model_trials']); self.assertIsNone(row['model_calls'])
                before = workspace_files(root/'live/workspace')
                imported = run_external_task(EXE,root/'import','B03',1,'model',configuration,import_source=root/'live')
                self.assertEqual(imported['status'],'passed',imported)
                self.assertEqual(row['checks'],imported['checks'])
                self.assertEqual(before,workspace_files(root/'live/workspace'))
                self.assertEqual(before,workspace_files(root/'import/workspace'))

    def test_baseline_never_calls_the_engine_and_checks_preview_identity(self):
        for incorrect in (False,True):
            with self.subTest(incorrect=incorrect), tempfile.TemporaryDirectory() as directory:
                configuration = driver('--preview-usage', *(['--wrong-image'] if incorrect else []))
                with patch('benchmark_baseline_large_layout.render_layout', return_value=png(1000,500,expected_picture())), \
                     patch('benchmark_driver.ExternalTrial.call', side_effect=AssertionError('Baseline launched Inkbolt')):
                    row = run_external_task(None,Path(directory)/'baseline','B03',1,'baseline',configuration,fake_tools())
                self.assertEqual(row['status'],'failed' if incorrect else 'passed',row)
                self.assertEqual(row['first_verified_preview_seconds'],None if incorrect else .5)
                self.assertFalse(row['model_trials'])
                checks = {c['name']:c['status'] for c in row['checks']}
                self.assertEqual(checks['historical-pixels'],'not_applicable')
                self.assertEqual(checks['history-valid'],'not_applicable')

    def test_svg_admission_rejects_changed_controls_and_external_or_unbounded_content(self):
        with tempfile.TemporaryDirectory() as directory:
            trial = Trial(None,Path(directory)/'source','B03',1,'cli',CHECKS['B03'])
            fixture(trial)
            source = layout_svg(json.loads((trial.root/'source.json').read_bytes()))
        self.assertEqual(len(svg_layout(source.encode())),5000)
        self.assertEqual(len(svg_layout(source.replace('translate(1,1)','matrix(1,0,0,1,1,1)').encode())),5000)
        self.assertEqual(len(svg_layout(source.replace('#145096','rgb(20,80,150)').encode())),5000)
        for text in (source.replace('translate(1,1)','translate(1,0)'),
                     source.replace('id="cell-17"','id="cell-18"'),
                     source.replace('width="6"','width="7"',1),
                     source.replace('#145096','#000000',1),
                     source.replace('height="500"','height="999999999"'),
                     source.replace('<rect','<image',1),
                     source.replace('fill="#145096"','fill="url(file:///external)"',1),
                     source.replace('id="cell-17"','id="cell-17" transform="translate(1,1)"'),
                     source.replace('id="cell-17"','id="cell-17" opacity="0.5"'),
                     '<!DOCTYPE svg>'+source):
            with self.assertRaises((TaskFailure,ValueError)):
                svg_layout(text.encode())


if __name__ == '__main__': unittest.main()
