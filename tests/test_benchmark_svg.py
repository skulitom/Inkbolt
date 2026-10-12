"""B04 rejudges SVG, snapshot and actual loss disclosure without solver state."""
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
from benchmark_svg import fixture, solve, judge, PROMPT, SOURCE, DESCRIPTION, svg_artifact, declared_losses, expected_picture
from benchmark_driver import run_external_task, workspace_files
from benchmark_runtime import Trial, TaskFailure
from benchmark_tasks import CHECKS
from test_benchmark_driver import driver, fake_tools
from test_images_cli import png
from workload_cases import sha

REVISED = SOURCE.decode().replace('<path ', '<path transform="translate(4,-1)" ')


class BenchmarkSvgTests(unittest.TestCase):
    def prepare(self, root, independent_names=False):
        trial=Trial(EXE,root,'B04',1,'cli',CHECKS['B04'])
        self.addCleanup(trial.close)
        if independent_names:
            call=trial.call
            def renamed(step, command, **arguments):
                if command=='svg.import': arguments['id']='artist-import'
                if arguments.get('session_id')=='work': arguments['session_id']='artist-session'
                return call('artist-'+step,command,**arguments)
            trial.call=renamed
        fixture(trial);trial.begin(PROMPT.read_text(encoding='utf-8'));solve(trial)
        return trial

    def test_reference_transports_keep_checks_and_separate_all_judge_traffic(self):
        for transport in ('cli','mcp'):
            with self.subTest(transport=transport), tempfile.TemporaryDirectory() as directory:
                root=Path(directory)/transport
                row=run_task(EXE,root,'B04',1,transport)
                self.assertEqual(row['status'],'passed',row)
                self.assertEqual({c['name'] for c in row['checks']},set(CHECKS['B04'])|{'source-preservation'})
                self.assertTrue(row['judge_separated'])
                self.assertEqual(row['judge_engine_commands'],5)
                self.assertEqual(row['engine_commands'],6)
                self.assertGreater(row['first_verified_preview_seconds'],0)
                for direction in ('request','response'):
                    self.assertEqual(row[direction+'_bytes']+row['judge_'+direction+'_bytes'],
                        sum(p.stat().st_size for p in root.glob('*.'+direction+'.json')))

    def test_independent_names_and_restored_svg_description_are_judged_from_files(self):
        with tempfile.TemporaryDirectory() as directory:
            trial=self.prepare(Path(directory)/'independent',True)
            path=trial.root/'revised.svg';svg=path.read_text()
            svg=svg.replace('color-interpolation="sRGB">','color-interpolation="sRGB"><desc>'+DESCRIPTION+'</desc>')
            path.write_text(svg,encoding='utf-8')
            report=json.loads((trial.root/'import-report.json').read_bytes())
            report['losses'].remove('description_omitted')
            (trial.root/'import-report.json').write_text(json.dumps(report),encoding='utf-8')
            trial.results.clear();trial.begin_judging();judge(trial)
            row=trial.finish()
            self.assertEqual(row['status'],'passed',row)
            self.assertIsNone(row['first_verified_preview_seconds'])

    def test_good_solver_logs_cannot_hide_altered_files_or_dishonest_receipts(self):
        for alteration in ('mapping','source-hash','losses','receipt-loss','receipt-source','receipt-definitions',
                           'controls','parent','svg-path','svg-paint','svg-transform','svg-layer','png','missing','source','prompt'):
            with self.subTest(alteration=alteration), tempfile.TemporaryDirectory() as directory:
                trial=self.prepare(Path(directory)/alteration)
                report=json.loads((trial.root/'import-report.json').read_bytes())
                receipt=json.loads((trial.root/'import-receipt.json').read_bytes())
                document=json.loads((trial.root/'editable.json').read_bytes())
                svg=(trial.root/'revised.svg').read_text()
                if alteration=='mapping': report['mapping']['block']=report['mapping']['layer']
                elif alteration=='source-hash': report['source_sha256']='0'*64
                elif alteration=='losses': report['losses']=[]
                elif alteration=='receipt-loss': receipt['losses']=[]
                elif alteration=='receipt-source': receipt['source']['sha256']='0'*64
                elif alteration=='receipt-definitions': receipt['definitions']=[{}]
                elif alteration=='controls': document['items'][-1]['content']['geometry']['commands'][0]['to'][0]=3
                elif alteration=='parent': document['items'][-1]['parent']=document['items'][0]['id']
                elif alteration=='svg-path': svg=svg.replace('L 10 3','L 11 3')
                elif alteration=='svg-paint': svg=svg.replace('#145096','#000000')
                elif alteration=='svg-transform': svg=svg.replace('1 4 -1','1 5 -1')
                elif alteration=='svg-layer': svg=svg.replace('id="svg-1"','id="missing-layer"')
                elif alteration=='png': (trial.root/'preview.png').write_bytes(png(32,24,b'\0'*(32*24*4)))
                elif alteration=='source': (trial.root/'original.svg').write_bytes(SOURCE+b' ')
                elif alteration=='prompt': (trial.root/'task.txt').write_text('changed task')
                for name,value in (('import-report.json',report),('import-receipt.json',receipt),('editable.json',document)):
                    (trial.root/name).write_text(json.dumps(value),encoding='utf-8')
                (trial.root/'revised.svg').write_text(svg,encoding='utf-8')
                if alteration=='missing': (trial.root/'import-receipt.json').unlink()
                trial.begin_judging()
                try: judge(trial)
                except (TaskFailure,ValueError,KeyError) as error: trial.error=str(error)
                self.assertEqual(trial.finish()['status'],'failed',alteration)

    def test_external_client_capture_is_rejudged_with_unknown_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);configuration=driver()
            row=run_external_task(EXE,root/'live','B04',1,'model',configuration)
            self.assertEqual(row['status'],'passed',row)
            self.assertFalse(row['model_trials']);self.assertIsNone(row['model_calls'])
            before=workspace_files(root/'live/workspace')
            imported=run_external_task(EXE,root/'import','B04',1,'model',configuration,import_source=root/'live')
            self.assertEqual(imported['status'],'passed',imported)
            self.assertEqual(row['checks'],imported['checks'])
            self.assertEqual(before,workspace_files(root/'live/workspace'))
            self.assertEqual(before,workspace_files(root/'import/workspace'))

    def test_baseline_is_engine_free_and_cannot_claim_a_bad_preview(self):
        for incorrect in (False,True):
            with self.subTest(incorrect=incorrect), tempfile.TemporaryDirectory() as directory:
                configuration=driver('--preview-usage', *(['--wrong-image'] if incorrect else []))
                with patch('benchmark_baseline_svg.render_artwork',return_value=png(32,24,expected_picture())), \
                     patch('benchmark_driver.ExternalTrial.call',side_effect=AssertionError('Baseline launched Inkbolt')):
                    row=run_external_task(None,Path(directory)/'baseline','B04',1,'baseline',configuration,fake_tools())
                self.assertEqual(row['status'],'failed' if incorrect else 'passed',row)
                self.assertEqual(row['first_verified_preview_seconds'],None if incorrect else .5)
                self.assertFalse(row['model_trials'])
                self.assertEqual({c['name']:c['status'] for c in row['checks']}['editable-source'],'not_applicable')

    def test_loss_report_must_match_actual_id_and_description_preservation(self):
        case=SimpleNamespace(sources={'original.svg':sha(SOURCE)})
        for remapped in (False,True):
            for omitted in (False,True):
                text=REVISED;mapping={'layer':'layer','block':'block'};losses=[]
                if remapped:
                    text=text.replace('id="layer"','id="renamed-layer"').replace('id="block"','id="renamed-block"')
                    mapping={'layer':'renamed-layer','block':'renamed-block'};losses.append('source_ids_remapped')
                if omitted:
                    text=text.replace('<desc>'+DESCRIPTION+'</desc>','');losses.append('description_omitted')
                artifact=svg_artifact(text.encode(),mapping)
                report=dict(source_sha256=sha(SOURCE),mapping=mapping,losses=losses)
                declared_losses(case,report,artifact)
                for wrong in (['invented'],losses+['source_ids_remapped'],losses+['description_omitted']):
                    with self.assertRaises(TaskFailure): declared_losses(case,dict(report,losses=wrong),artifact)

    def test_svg_admission_rejects_other_controls_resources_layers_and_viewports(self):
        mapping={'layer':'layer','block':'block'}
        self.assertTrue(svg_artifact(REVISED.encode(),mapping)['description_preserved'])
        self.assertTrue(svg_artifact(REVISED.replace('M2 3 H10 V9 H2 Z','M2 3 L10 3 L10 9 L2 9 Z').encode(),mapping))
        for text in (REVISED.replace('H10','H11'), REVISED.replace(' Z',''),
                     REVISED.replace('translate(4,-1)','translate(5,-1)'),
                     REVISED.replace('translate(3,2)','translate(4,2)'),
                     REVISED.replace('width="32"','width="10000000"'),
                     REVISED.replace('id="block"','id="layer"'),
                     REVISED.replace('<path','<image'),
                     REVISED.replace('#145096','url(file:///external)'),
                     REVISED.replace('</g>','</g><g id="extra"/>'),
                     REVISED.replace('<path','<path opacity="0.5"'),
                     '<!DOCTYPE svg>'+REVISED):
            with self.assertRaises((TaskFailure,ValueError)):
                svg_artifact(text.encode(),mapping)


if __name__=='__main__': unittest.main()
