"""B13 exact straight alpha, private metadata and actual duplicate refusal."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_cli import EXE,ROOT
sys.path.insert(0,str(ROOT/'tools'))
from benchmark_reference_checks import reference_task
from benchmark_baseline_screen import screen_shape
from benchmark_driver import run_external_task,workspace_files
from benchmark_runtime import TaskFailure
from benchmark_screen_client import SVG
from test_benchmark_driver import driver,fake_tools
from test_images_cli import png
from workload_cases import sha


class ScreenBenchmarkTests(unittest.TestCase):
    @reference_task('B13')
    def test_original_outcomes_on_cli_and_mcp_with_separate_judge_calls(self, row):
        self.assertEqual((row['engine_commands'],row['judge_engine_commands']),(6,6))
        probes=[call for call in row['calls'] if 'judge_workspace' in call]
        self.assertEqual(len(probes),3)
        self.assertTrue(all(call['phase']=='judge' and call['transport']=='cli' for call in probes))

    def test_external_capture_can_be_rejudged_without_writing_into_solver_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);configuration=driver()
            row=run_external_task(EXE,root/'live','B13',1,'model',configuration)
            self.assertEqual(row['status'],'passed',row);before=workspace_files(root/'live/workspace')
            (root/'live').rename(root/'capture')
            imported=run_external_task(EXE,root/'import','B13',1,'model',configuration,import_source=root/'capture')
            self.assertEqual(imported['status'],'passed',imported);self.assertFalse(imported['model_trials'])
            self.assertEqual(before,workspace_files(root/'capture/workspace'));self.assertEqual(before,workspace_files(root/'import/workspace'))

    def test_baseline_checks_fresh_pixels_and_actual_protected_bytes_without_engine_access(self):
        for fault in ('none','pixels','collision','overwritten','boolean'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as directory:
                def rendered(case,tools,shape,raw):
                    probe=dict(collision=False if fault=='collision' else 1 if fault=='boolean' else True,before=sha(raw),after=sha(raw))
                    return (png(1,1,bytes(4)) if fault=='pixels' else raw),probe,(b'overwritten' if fault=='overwritten' else raw)
                with patch('benchmark_baseline_screen.render_and_probe',side_effect=rendered), \
                     patch('benchmark_driver.ExternalTrial.call',side_effect=AssertionError('Baseline launched Inkbolt')):
                    row=run_external_task(None,Path(directory)/'baseline','B13',1,'baseline',driver('--preview-usage'),fake_tools())
                self.assertEqual(row['status'],'passed' if fault=='none' else 'failed',row)
                self.assertEqual(row['first_verified_preview_seconds'],None if fault=='pixels' else .5)
                self.assertEqual(next(c for c in row['checks'] if c['name']=='editable-source')['status'],'not_applicable')

    def test_bounded_svg_rejects_changed_paint_metadata_paths_and_dimensions(self):
        good=screen_shape(SVG.encode());self.assertEqual(good['color'],[20,80,150,128])
        self.assertEqual(screen_shape(SVG.replace('width="1920"','width="1920.0"').encode()),good)
        for changed in (SVG.replace('width="1920"','width="999999"'),SVG.replace('0.5019607843137255','1'),
                        SVG.replace('#145096','#0a284b'),SVG.replace('original private source note','lost'),
                        SVG.replace('<rect ','<rect href="../external" '),'< !DOCTYPE svg>'.replace('< !','<!')+SVG):
            with self.subTest(changed=changed),self.assertRaises((TaskFailure,ValueError)):screen_shape(changed.encode())

if __name__=='__main__':unittest.main()
