"""B07 reference transports, captured workspaces and baseline runs."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from test_cli import EXE, ROOT
sys.path.insert(0,str(ROOT/'tools'))

from benchmark_reference_checks import reference_task
from benchmark_typography import (
    fixture,
    PROMPT,
    TYPOGRAPHY,
    expected_picture,
    authored_geometry,
    shaping_report,
)
from benchmark_baseline_typography import svg_typography, judge_typography
from benchmark_driver import run_external_task, workspace_files
from benchmark_runtime import Trial, TaskFailure
from benchmark_tasks import CHECKS
from benchmark_fake_driver import typography_svg
from test_benchmark_driver import driver, fake_tools
from test_images_cli import png
from workload_cases import save_json


class BenchmarkTypographyTests(unittest.TestCase):
    @reference_task('B07')
    def test_both_reference_transports_separate_judging_and_preserve_check_inventory(self, row):
        self.assertEqual(row['engine_commands'],9)
        self.assertEqual(row['judge_engine_commands'],9)

    def test_external_capture_rejudges_fonts_snapshot_and_shaping_after_relocation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); configuration = driver('--custom-font-store','--custom-session-store')
            row = run_external_task(EXE,root/'live','B07',1,'model',configuration)
            self.assertEqual(row['status'],'passed',row)
            self.assertFalse(row['model_trials']); self.assertIsNone(row['model_calls'])
            self.assertFalse((root/'live/workspace/.inkbolt/sessions').exists())
            self.assertFalse((root/'live/workspace/.inkbolt/fonts').exists())
            before = workspace_files(root/'live/workspace')
            imported = run_external_task(EXE,root/'import','B07',1,'model',configuration,import_source=root/'live')
            self.assertEqual(imported['status'],'passed',imported)
            self.assertEqual(row['checks'],imported['checks'])
            self.assertEqual(before,workspace_files(root/'live/workspace'))
            self.assertEqual(before,workspace_files(root/'import/workspace'))

    def test_retained_font_or_license_cannot_be_replaced_by_original_input(self):
        for flag in ('--corrupt-font-copy','--missing-font-license'):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as directory:
                row = run_external_task(EXE,Path(directory)/'broken','B07',1,'model',
                    driver('--custom-font-store','--custom-session-store',flag))
                self.assertEqual(row['status'],'failed',row)
                self.assertIn('Missing intact workspace font store',row['error'])

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
