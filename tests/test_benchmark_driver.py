"""External arms retain identity, real artifacts, unknown observations and every failure."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_cli import EXE,ROOT
sys.path.insert(0,str(ROOT/'tools'))
from benchmark_driver import run_external_task,workspace_files,model_run_complete,observations
from benchmark_tasks import TASKS,CHECKS,ARTIFACT_CHECKS,ENGINE_CHECKS
from benchmark_diagram import expected_picture
from benchmark_baseline import svg_diagram
from benchmark_runtime import TaskFailure
from benchmark_fake_driver import SVG
from test_images_cli import png
from synthetic_font import geometric_font
from workload_cases import sha


def driver(*flags):
    script=ROOT/'tests/benchmark_fake_driver.py'
    return dict(schema_version=1,kind='synthetic',client=dict(id='original-test-client',version='1'),
        model=dict(id='synthetic-no-model',settings={}),argv=[sys.executable,str(script),*flags],
        driver_files=[str(script)],timeout_seconds=30)


def fake_tools():
    return dict(resvg=dict(path=sys.executable,version='synthetic-fixture',sha256='test-only'),
                python=dict(path=sys.executable,sha256='test-only'),pillow=dict(version='synthetic-fixture',files_sha256='test-only'))


class BenchmarkDriverTests(unittest.TestCase):
    def test_original_fixture_is_unchanged_and_named_variant_retains_glyph_pixels(self):
        self.assertEqual(sha(geometric_font()),'0bc1bae3dae5c43f7a8eb8500b12ea60f16afd6317501878cbee455b30401b11')
        # Real CLI/MCP B01 pixel tests use the named variant on both platforms.
        self.assertNotEqual(geometric_font(),geometric_font(family='Inkbolt Diagram Fixture'))

    def test_every_original_check_has_exactly_one_classification(self):
        for task,names in CHECKS.items():
            self.assertEqual(set(names),set(ARTIFACT_CHECKS[task])|set(ENGINE_CHECKS[task]))
            self.assertFalse(set(ARTIFACT_CHECKS[task])&set(ENGINE_CHECKS[task]))

    def test_live_model_arm_and_import_use_the_same_judge_without_inventing_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);configuration=driver()
            row=run_external_task(EXE,root/'live','B01',1,'model',configuration)
            self.assertEqual(row['status'],'passed',row)
            self.assertFalse(row['model_trials'])
            self.assertIsNone(row['token_usage']);self.assertIsNone(row['model_calls']);self.assertIsNone(row['engine_commands'])
            self.assertEqual(row['judge_engine_commands'],2)
            before=workspace_files(root/'live/workspace')
            imported=run_external_task(EXE,root/'imported','B01',1,'model',configuration,import_source=root/'live')
            self.assertEqual(imported['status'],'passed',imported)
            self.assertEqual(imported['checks'],row['checks'])
            self.assertEqual(before,workspace_files(root/'live/workspace'))
            self.assertEqual(before,workspace_files(root/'imported/workspace'))
            self.assertTrue(imported['driver']['imported'])

    def test_baseline_runs_without_an_engine_and_marks_engine_checks_not_applicable(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            # The fake driver covers orchestration; real pinned renderer trials
            # are external evidence, not substituted by this controlled oracle.
            with patch('benchmark_baseline.render_svg',return_value=png(128,56,expected_picture())),\
                 patch('benchmark_driver.ExternalTrial.call',side_effect=AssertionError('Baseline launched Inkbolt')):
                row=run_external_task(None,root/'baseline','B01',1,'baseline',driver('--usage'),fake_tools())
            self.assertEqual(row['status'],'passed',row)
            checks={v['name']:v for v in row['checks']}
            self.assertEqual(checks['editable-source']['status'],'not_applicable')
            self.assertEqual(checks['diagram-pixels']['status'],'pass')
            self.assertEqual(row['token_usage'],dict(input_tokens=20,output_tokens=10))
            self.assertFalse(row['model_trials'])
            request=json.loads((root/'baseline/evidence/request.json').read_text())
            self.assertIsNone(request['mcp_config']);self.assertNotIn('engine_executable',request)

    def test_bad_client_data_changed_inputs_wrong_artifacts_and_deadlines_cannot_pass(self):
        for flag in ['--wrong-contract','--changed-prompt','--wrong-image','--invalid-usage','--timeout']:
            with self.subTest(flag=flag),tempfile.TemporaryDirectory() as directory:
                configuration=driver(flag)
                if flag=='--timeout': configuration['timeout_seconds']=.2
                root=Path(directory)/'failed'
                row=run_external_task(EXE,root,'B01',1,'model',configuration)
                self.assertEqual(row['status'],'failed',row)
                self.assertTrue((root/'result.json').is_file())
                self.assertTrue((root/'evidence/request.json').is_file())
                self.assertFalse(row['model_trials'])

    def test_import_checks_transcript_and_workspace_bytes_instead_of_trusting_result_claims(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);configuration=driver()
            run_external_task(EXE,root/'live','B01',1,'model',configuration)
            (root/'live/evidence/transcript.jsonl').write_text('forged transcript',encoding='utf-8')
            row=run_external_task(EXE,root/'forged','B01',1,'model',configuration,import_source=root/'live')
            self.assertEqual(row['status'],'failed')
            self.assertIn('identity mismatch',row['driver_failure'])

    def test_preparation_open_tasks_and_engine_only_baseline_tasks_stay_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch('benchmark_driver.run_owned',side_effect=AssertionError('Preparation launched a client')):
                row=run_external_task(EXE,root/'prepared','B01',1,'model',driver(),prepare=True)
            self.assertEqual(row['status'],'prepared')
            self.assertEqual(run_external_task(EXE,root/'open','B02',1,'model',driver())['status'],'not_implemented')
            for task in ('B17','B18','B19'):
                self.assertEqual(run_external_task(None,root/task,task,1,'baseline',driver(),fake_tools())['status'],'not_applicable')

    def test_synthetic_rows_and_partial_selections_never_complete_the_model_benchmark(self):
        rows=[dict(task=task,repetition=rep,arm='model',model_trials=False,status='passed',
                   driver=dict(kind='synthetic',transcript_sha256='x')) for task in TASKS for rep in range(1,6)]
        self.assertFalse(model_run_complete(rows,TASKS,5,True))
        forged=copy.deepcopy(rows)
        for row in forged: row['model_trials']=True
        self.assertFalse(model_run_complete(forged,TASKS,5,True))
        self.assertFalse(model_run_complete(rows,['B01'],5,True))
        for values in [dict(source='estimated',model_calls=1),dict(source='client_reported',agent_seconds=float('nan'))]:
            with self.assertRaises(TaskFailure): observations(dict(observations=values))

    def test_svg_structure_judge_accepts_arbitrary_ids_and_rejects_external_content(self):
        self.assertEqual(len(svg_diagram(SVG.encode())),2)
        alternate=SVG.replace('<rect x="8" y="8"','<rect id="arbitrary" transform="translate(8,8)" x="0" y="0"')
        self.assertEqual(len(svg_diagram(alternate.encode())),2)
        for bad in [SVG.replace('width="128"','width="999999999"'),SVG.replace('<rect','<image',1),
                    SVG.replace('fill="#145096"','fill="url(file:///external)"'),SVG.replace('AA','AB')]:
            with self.assertRaises((TaskFailure,ValueError)): svg_diagram(bad.encode())


if __name__=='__main__': unittest.main()
