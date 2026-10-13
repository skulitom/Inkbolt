"""B14 retained native print evidence, independent clients and corrupt deliveries."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_cli import EXE,ROOT
sys.path.insert(0,str(ROOT/'tools'))
from agent_benchmark import run_task
from benchmark_print import fixture,solve,judge,PROMPT,source_document,expected_picture,retained_print_file,print_files
from benchmark_baseline_print import manifest,judge_print,page_geometry
from benchmark_driver import run_external_task,workspace_files
from benchmark_runtime import Trial,TaskFailure
from benchmark_tasks import CHECKS
from benchmark_print_client import author,pdf_bytes
from test_benchmark_driver import driver,fake_tools
from test_images_cli import png
from pdf_reader import Pdf
from workload_cases import sha


class PrintBenchmarkTests(unittest.TestCase):
    def prepare(self,root,independent=False,custom=False):
        case=Trial(EXE,root,'B14',1,'cli',CHECKS['B14']);self.addCleanup(case.close)
        fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'))
        original=case.call
        def call(step,command,**arguments):
            if independent:
                if command=='preset.create':arguments['id']='studio-page'
                if arguments.get('session_id')=='work':arguments['session_id']='studio-session'
            if custom:
                if command.startswith('session.'):arguments['session_root']='chosen sessions'
                document=arguments.get('document')
                if isinstance(document,dict) and 'session_id' in document:
                    arguments['document']=dict(document,session_root='chosen sessions')
                if 'receipt' in arguments:arguments['receipt']['receipt_root']='chosen receipts'
            return original(step,command,**arguments)
        if independent or custom:case.call=call
        if independent:
            with patch('benchmark_print.source_document',side_effect=lambda preset,rgb,cmyk:source_document(preset,rgb,cmyk,
                dict(board='sheet',process='process-ink',items=['left','right']))):solve(case)
        else:solve(case)
        case.call=original
        return case

    def test_original_outcomes_on_cli_and_mcp_with_separated_solver(self):
        for transport in ('cli','mcp'):
            with self.subTest(transport=transport),tempfile.TemporaryDirectory() as directory:
                row=run_task(EXE,Path(directory)/'reference','B14',1,transport)
                self.assertEqual(row['status'],'passed',row)
                self.assertEqual((row['engine_commands'],row['judge_engine_commands']),(7,9))
                self.assertEqual({c['name'] for c in row['checks']},set(CHECKS['B14'])|{'source-preservation'})
                self.assertTrue(row['judge_separated']);self.assertGreater(row['first_verified_preview_seconds'],0)
                self.assertEqual(row['sources'],{'original-rgb.icc':'ae8f979d6718a08dd8b9526c965263444caa8b7e1b7c0f8a12ebba9c76365c98',
                    'original-cmyk.icc':'5ba4f5f0eb525b7dbc622b4aa51c27cc32676648a581a4f2a5fe4949d4375a58'})

    def test_independent_names_and_source_pass_without_solver_result_access(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'names',True);case.results.clear();case.begin_judging();judge(case)
            row=case.finish();self.assertEqual(row['status'],'passed',row);self.assertIsNone(row['first_verified_preview_seconds'])

    def test_changed_source_delivery_pixels_and_declared_losses_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);case=self.prepare(root/'model',custom=True);original_call=case.call
            files={name:(case.root/name).read_bytes() for name in ('editable.json','preview.png','print.pdf','delivery.json')}
            case.results.clear();case.begin_judging()
            for fault in ('geometry','profile','ink','pixels','pdf','losses','missing-loss'):
                with self.subTest(fault=fault):
                    for name,data in files.items():(case.root/name).write_bytes(data)
                    case.judge_root=root/fault;case.judge_root.mkdir();case.checks.clear()
                    case.call=lambda step,command,**arguments:original_call(fault+'-'+step,command,**arguments)
                    if fault in ('geometry','profile','ink'):
                        value=json.loads(files['editable.json'])
                        if fault=='geometry':value['items'][1]['content']['geometry']['width']=101
                        elif fault=='profile':value['output_profile']={'type':'builtin','name':'srgb'}
                        else:value['swatches']['process']['definition']['color']['components'][0]=.5
                        (case.root/'editable.json').write_text(json.dumps(value),encoding='utf-8')
                    elif fault=='pixels':(case.root/'preview.png').write_bytes(png(1,1,bytes(4)))
                    elif fault=='pdf':
                        raw=files['print.pdf'];changed=raw.replace(b'23 39 m',b'24 39 m');self.assertNotEqual(raw,changed)
                        (case.root/'print.pdf').write_bytes(changed)
                        value=json.loads(files['delivery.json']);value['sha256']=sha(changed)
                        (case.root/'delivery.json').write_text(json.dumps(value),encoding='utf-8')
                    else:
                        value=json.loads(files['delivery.json'])
                        if fault=='missing-loss':value['losses'].pop(0)
                        else:value['losses']=[]
                        (case.root/'delivery.json').write_text(json.dumps(value),encoding='utf-8')
                    try:judge(case)
                    except TaskFailure:pass
                    expected='editable-print-source' if fault in ('geometry','profile','ink') else 'print-preview' if fault=='pixels' else 'declared-losses'
                    self.assertIn(expected,[c['name'] for c in case.checks if c['status']=='fail'],case.checks)

    def test_external_capture_rejudges_after_original_workspace_moves(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);configuration=driver('--custom-session-store','--custom-receipt-store',
                '--print-labels','--print-delivery-folder','--print-extra-losses','--preview-usage')
            row=run_external_task(EXE,root/'live','B14',1,'model',configuration)
            self.assertEqual(row['status'],'passed',row);before=workspace_files(root/'live/workspace')
            self.assertEqual(row['first_verified_preview_seconds'],.5)
            self.assertFalse((root/'live/workspace/print.pdf').exists())
            snapshot=json.loads((root/'live/workspace/print output/editable.json').read_bytes())
            self.assertEqual({key:value['name'] for key,value in snapshot['swatches'].items()},
                {'process':'Chosen process label','spot':'Chosen spot label'})
            self.assertFalse((root/'live/workspace/.inkbolt/sessions').exists())
            self.assertFalse((root/'live/workspace/.inkbolt/publications').exists())
            self.assertEqual(len(list((root/'live/workspace/chosen sessions').glob('*.sqlite3'))),1)
            self.assertEqual(len(list((root/'live/workspace/chosen receipts').rglob('publications.sqlite3'))),1)
            (root/'live').rename(root/'moved')
            imported=run_external_task(EXE,root/'import','B14',1,'model',configuration,import_source=root/'moved')
            self.assertEqual(imported['status'],'passed',imported);self.assertFalse(imported['model_trials'])
            self.assertEqual(imported['first_verified_preview_seconds'],.5)
            self.assertEqual(before,workspace_files(root/'moved/workspace'));self.assertEqual(before,workspace_files(root/'import/workspace'))

    def test_custom_history_and_receipt_stores_must_be_unique_and_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);case=self.prepare(root/'model',custom=True);original=case.call
            paths=[next((case.root/name).glob('*.sqlite3')) for name in ('chosen sessions','chosen receipts')]
            originals={path:path.read_bytes() for path in paths};case.results.clear();case.begin_judging()
            for index,path in enumerate(paths):
                for fault in ('missing','ambiguous','corrupt'):
                    with self.subTest(store=path.parent.name,fault=fault):
                        label=f'{index}-{fault}';case.judge_root=root/label;case.judge_root.mkdir();case.checks.clear()
                        case.call=lambda step,command,**arguments:original(label+'-'+step,command,**arguments)
                        duplicate=case.root/'duplicate'/path.name
                        if fault=='missing':path.unlink()
                        elif fault=='ambiguous':
                            duplicate.parent.mkdir(exist_ok=True);duplicate.write_bytes(originals[path])
                        else:path.write_bytes(b'corrupt retained store')
                        with self.assertRaises(TaskFailure):judge(case)
                        self.assertTrue(all(c['status']=='pass' for c in case.checks),case.checks)
                        self.assertIn('native-inks',[c['name'] for c in case.checks])
                        path.write_bytes(originals[path])
                        if duplicate.exists():duplicate.unlink()

    def test_baseline_never_launches_engine_and_keeps_engine_checks_not_applicable(self):
        with tempfile.TemporaryDirectory() as directory,patch('benchmark_baseline_print.render_preview',return_value=expected_picture()) as render, \
             patch('benchmark_driver.ExternalTrial.call',side_effect=AssertionError('Baseline launched Inkbolt')):
            row=run_external_task(None,Path(directory)/'baseline','B14',1,'baseline',driver('--preview-usage','--print-delivery-folder'),fake_tools())
            self.assertEqual(row['status'],'passed',row);self.assertEqual(row['first_verified_preview_seconds'],.5)
            self.assertEqual({c['name'] for c in row['checks'] if c['status']=='not_applicable'}, {'editable-print-source','history-valid'})
            self.assertEqual(render.call_args.args[2],'print output/editable.json')

    def test_print_file_lookup_accepts_separate_folders_but_rejects_ambiguous_deliveries(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();case=SimpleNamespace(root=root)
            expected={name:f'folder {i}/{name}' for i,name in enumerate(('editable.json','preview.png','print.pdf','delivery.json'))}
            for name,path in expected.items():
                file=root/path;file.parent.mkdir();file.write_text(name,encoding='utf-8')
            self.assertEqual(print_files(case),expected);self.assertEqual(case.preview_paths,{'preview.png':expected['preview.png']})
            (root/'print.pdf').write_bytes(b'duplicate')
            with self.assertRaisesRegex(TaskFailure,'ambiguous'):print_files(case)
            (root/'print.pdf').unlink();(root/expected['print.pdf']).unlink()
            with self.assertRaisesRegex(TaskFailure,'Missing'):print_files(case)

    def test_print_file_lookup_rejects_linked_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory).resolve();root=base/'capture';root.mkdir();external=base/'external.pdf';external.write_bytes(b'external')
            try:(root/'print.pdf').symlink_to(external)
            except OSError as error:self.skipTest('Host cannot create fixture symlinks: '+str(error))
            with self.assertRaisesRegex(TaskFailure,'linked'):retained_print_file(SimpleNamespace(root=root),'print.pdf')

    def test_wrong_nested_preview_has_no_verified_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            row=run_external_task(EXE,Path(directory)/'bad-preview','B14',1,'model',
                driver('--print-labels','--print-delivery-folder','--preview-usage','--wrong-image'))
            self.assertEqual(row['status'],'failed',row);self.assertIsNone(row['first_verified_preview_seconds'])
            self.assertIn('print-preview',[c['name'] for c in row['checks'] if c['status']=='fail'])

    def test_snapshot_receipt_cannot_stand_in_for_print_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'wrong-receipt',custom=True)
            path=case.root/'session.json';locator=json.loads(path.read_bytes())
            case.call('publish-other-source','document.publish',
                document=dict(session_root='chosen sessions',session_id=locator['session_id'],revision=locator['revision']),
                output=dict(file_name='other-snapshot.json',format='snapshot'),
                receipt=dict(receipt_root='chosen receipts',request_id='wrong-pdf-receipt'))
            locator['publication']='wrong-pdf-receipt';path.write_text(json.dumps(locator),encoding='utf-8')
            case.results.clear();case.begin_judging();judge(case)
            self.assertEqual([c['name'] for c in case.checks if c['status']=='fail'],['history-valid'])
            self.assertIn({'name':'declared-losses','status':'pass','check_class':'artifact'},case.checks)

    def test_baseline_pdf_mutations_cannot_hide_behind_a_correct_preview_or_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            case=Trial(None,Path(directory)/'baseline','B14',1,'cli',CHECKS['B14'],arm='baseline');self.addCleanup(case.close)
            fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));scene=author(case.root)
            (case.root/'preview.png').write_bytes(png(240,130,expected_picture()));case.begin_judging()
            rgb=(case.root/'original-rgb.icc').read_bytes();cmyk=(case.root/'original-cmyk.icc').read_bytes()
            for fault,expected in [('none',None),('boxes','physical-boxes'),('ink','native-inks'),('geometry','native-inks'),
                                   ('profile','profile-identities'),('channels','profile-identities'),('function','native-inks'),('pixels','print-preview')]:
                with self.subTest(fault=fault):
                    value=copy.deepcopy(scene);case.checks.clear()
                    if fault=='boxes':value['paper_mm'][0]=211
                    if fault=='ink':value['items'][0]['components'][0]=.5
                    if fault=='geometry':value['items'][1]['bounds'][0]+=1
                    raw=pdf_bytes(value,rgb if fault!='profile' else rgb.replace(b'Inkb',b'Test'),cmyk)
                    if fault=='channels':raw=raw.replace(b'/N 4',b'/N 3')
                    if fault=='function':raw=raw.replace(b'/FunctionType 2',b'/FunctionType 3')
                    (case.root/'print.pdf').write_bytes(raw)
                    (case.root/'delivery.json').write_text(json.dumps(dict(file='print.pdf',sha256=sha(raw),losses=[
                        'PDF does not carry the editable document model; this is not a print proof.'])),encoding='utf-8')
                    with patch('benchmark_baseline_print.render_preview',return_value=bytes(240*130*4) if fault=='pixels' else expected_picture()):
                        judge_print(case,fake_tools())
                    failed=[c['name'] for c in case.checks if c['status']=='fail']
                    if expected:self.assertIn(expected,failed)
                    else:self.assertEqual(failed,[])

    def test_recipe_admission_precedes_profile_decoder_and_rejects_paths_boolean_numbers(self):
        with tempfile.TemporaryDirectory() as directory:
            case=Trial(None,Path(directory)/'bounded','B14',1,'cli',CHECKS['B14']);self.addCleanup(case.close);fixture(case)
            good=author(case.root);(case.root/'preview.png').write_bytes(png(240,130,expected_picture()))
            for fault in ('path','boolean','profile','bleed'):
                with self.subTest(fault=fault):
                    value=copy.deepcopy(good)
                    if fault=='path':value['ink_profile']['file']='../external.icc'
                    elif fault=='boolean':value['items'][1]['tint']=True
                    elif fault=='profile':value['page_profile']['sha256']='0'*64
                    else:value['bleed_px']=[9,12,6,4]
                    (case.root/'editable.json').write_text(json.dumps(value),encoding='utf-8')
                    with patch('benchmark_baseline_print.render_preview',side_effect=AssertionError('Admission must run first')),self.assertRaises(TaskFailure):
                        judge_print(case,fake_tools())

    def test_pdf_geometry_checks_transform_opacity_and_unsupported_clipping(self):
        with tempfile.TemporaryDirectory() as directory:
            case=Trial(None,Path(directory)/'geometry','B14',1,'cli',CHECKS['B14']);self.addCleanup(case.close);fixture(case)
            scene=manifest(case.sources)
            raw=pdf_bytes(scene,(case.root/'original-rgb.icc').read_bytes(),(case.root/'original-cmyk.icc').read_bytes())
            page_geometry(Pdf(raw))
            for old,new in ((b'1 0 0 -1 0',b'2 0 0 -1 0'),(b'/ca 1',b'/ca 0'),
                            (b'/UseBlackPtComp /OFF',b'/UseBlackPtComp /DEF'),(b'\nh\nf\n',b'\nh\nW\n')):
                changed=raw.replace(old,new);self.assertNotEqual(changed,raw)
                with self.subTest(old=old),self.assertRaises(TaskFailure):page_geometry(Pdf(changed))
            for key,value in [('Rotate',90),('CropBox',[0,0,1,1]),('Annots',[])]:
                pdf=Pdf(raw);pdf.pages[0][key]=value
                with self.subTest(key=key),self.assertRaises(TaskFailure):page_geometry(pdf)
            pdf=Pdf(raw);pdf.get(pdf.pages[0]['Resources']['ExtGState']['Paint'])['TR']='Identity'
            with self.assertRaises(TaskFailure):page_geometry(pdf)


if __name__=='__main__':unittest.main()
