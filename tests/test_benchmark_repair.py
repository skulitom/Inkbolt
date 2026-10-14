"""B16 independent overflow, collateral changes, delivery and capture controls."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_cli import EXE,ROOT
sys.path.insert(0,str(ROOT/'tools'))
from agent_benchmark import run_task
from benchmark_repair import fixture,solve,judge,PROMPT,initial_document,original_font,FONT_FAMILY,expected_picture
from benchmark_baseline_repair import judge_repair,measured_width
from benchmark_driver import run_external_task,workspace_files
from benchmark_runtime import Trial,TaskFailure
from benchmark_tasks import CHECKS
from benchmark_repair_client import author,publish
from synthetic_font import geometric_font
from test_benchmark_driver import driver,fake_tools
from test_images_cli import png
from workload_cases import sha


class RepairBenchmarkTests(unittest.TestCase):
    def prepare(self,root,independent=False,custom=False):
        case=Trial(EXE,root,'B16',1,'cli',CHECKS['B16']);self.addCleanup(case.close)
        fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));original=case.call
        def call(step,command,**arguments):
            if independent:
                if arguments.get('session_id')=='work':arguments['session_id']='studio-repair'
                if 'request_id' in arguments:arguments['request_id']='owner-'+arguments['request_id']
                if command=='session.publish':arguments['receipt']['request_id']='owner-delivery'
            if custom:
                if command.startswith('session.'):arguments['session_root']='chosen sessions'
                document=arguments.get('document')
                if isinstance(document,dict) and 'session_id' in document:document['session_root']='chosen sessions'
                if 'receipt' in arguments:arguments['receipt']['receipt_root']='chosen receipts'
            return original(step,command,**arguments)
        if independent or custom:case.call=call
        if independent:
            with patch('benchmark_repair.initial_document',side_effect=lambda font:initial_document(font,
                dict(document='poster',label='headline',other='decoration',face='typeface'))):solve(case)
            locator=json.loads((case.root/'session.json').read_bytes());locator.update(creation='owner-create',publication='owner-delivery')
            (case.root/'session.json').write_text(json.dumps(locator),encoding='utf-8')
        else:solve(case)
        case.call=original;return case

    def test_original_fixtures_and_named_companion_preserve_all_non_naming_tables(self):
        def tables(raw):
            result={}
            for at in range(12,12+16*struct.unpack_from('>H',raw,4)[0],16):
                tag,_,offset,length=struct.unpack_from('>4sIII',raw,at);value=raw[offset:offset+length]
                if tag==b'head':value=value[:8]+bytes(4)+value[12:]
                result[tag]=value
            return result
        original=geometric_font();before=tables(original);after=tables(geometric_font(family=FONT_FAMILY))
        self.assertEqual(set(after)-set(before),{b'name'});self.assertEqual(before,{k:v for k,v in after.items() if k!=b'name'})
        self.assertEqual(measured_width(original),24)
        self.assertEqual(sha(original),'0bc1bae3dae5c43f7a8eb8500b12ea60f16afd6317501878cbee455b30401b11')

    def test_original_checks_on_cli_and_mcp_with_separate_judge(self):
        for transport in ('cli','mcp'):
            with self.subTest(transport=transport),tempfile.TemporaryDirectory() as directory:
                row=run_task(EXE,Path(directory)/'reference','B16',1,transport)
                self.assertEqual(row['status'],'passed',row)
                self.assertEqual((row['engine_commands'],row['judge_engine_commands']),(11,12))
                self.assertEqual({c['name'] for c in row['checks']},set(CHECKS['B16'])|{'source-preservation'})
                self.assertGreater(row['first_verified_preview_seconds'],0);self.assertTrue(row['judge_separated'])
                self.assertEqual(row['sources']['font-license.txt'],'38b2ad535b9f5a4778264eddc05f1c8286131dd1079d5cfd7cde6d00c6c85ed6')

    def test_independent_ids_and_requests_do_not_need_solver_results(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'names',True);case.results.clear();case.begin_judging();judge(case)
            row=case.finish();self.assertEqual(row['status'],'passed',row);self.assertIsNone(row['first_verified_preview_seconds'])

    def test_omitted_defaults_preserve_source_semantics_but_repaired_revision_must_match(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'defaults');original=case.call;case.results.clear();case.begin_judging()
            before=initial_document(original_font(case))
            (case.root/'before.json').write_text(json.dumps(before),encoding='utf-8')
            for fault in ('none','missing-revision','stale-revision','changed-resolution','changed-artwork'):
                with self.subTest(fault=fault):
                    after=initial_document(original_font(case));after['revision']=1
                    after['items'][0]['content']['frame']['width']=24
                    if fault=='missing-revision':del after['revision']
                    elif fault=='stale-revision':after['revision']=0
                    elif fault=='changed-resolution':after['resolution_ppi']=72
                    elif fault=='changed-artwork':after['items'][1]['content']['geometry']['x']=31
                    (case.root/'editable.json').write_text(json.dumps(after),encoding='utf-8');case.checks.clear()
                    case.call=lambda step,command,**arguments:original(fault+'-'+step,command,**arguments)
                    if fault=='none':
                        judge(case);self.assertTrue(all(c['status']=='pass' for c in case.checks),case.checks)
                    else:
                        with self.assertRaises(TaskFailure):judge(case)
                        self.assertIn('no-collateral-edits',[c['name'] for c in case.checks if c['status']=='fail'])

    def test_changed_sources_diagnosis_review_pixels_delivery_and_history_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'negative');original=case.call;case.results.clear();case.begin_judging()
            names=['before.json','editable.json','diagnostics.json','review.png','review.json','delivery.json','repaired.png']
            good={name:(case.root/name).read_bytes() for name in names}
            for fault in ('initial','artwork','font','diagnosis','review','pixels','delivery','fingerprint','history','review-image'):
                with self.subTest(fault=fault):
                    for name,data in good.items():(case.root/name).write_bytes(data)
                    case.checks.clear();case.call=lambda step,command,**arguments:original(fault+'-'+step,command,**arguments)
                    value=None
                    if fault in ('initial','artwork','font'):
                        name='before.json' if fault=='initial' else 'editable.json';value=json.loads(good[name])
                        if fault=='initial':value['items'][0]['content']['frame']['width']=24
                        elif fault=='artwork':value['items'][1]['content']['geometry']['x']=31
                        else:value['fonts']['face']['sha256']='0'*64
                    elif fault=='diagnosis':name='diagnostics.json';value=json.loads(good[name]);value['suggested_width']=12
                    elif fault=='delivery':name='delivery.json';value=json.loads(good[name]);value['preflight_sha256']='0'*64
                    elif fault=='review-image':
                        name='review.json';value=json.loads(good[name]);value['preview']['data']=''
                    elif fault in ('fingerprint','history'):
                        name='review.json';value=json.loads(good[name]);value['proposal']['request_fingerprint' if fault=='fingerprint' else 'base_state_sha256']='0'*64
                    else:(case.root/('review.png' if fault=='review' else 'repaired.png')).write_bytes(png(1,1,bytes(4)))
                    if value is not None:(case.root/name).write_text(json.dumps(value),encoding='utf-8')
                    try:judge(case)
                    except TaskFailure:pass
                    expected={'initial':'no-collateral-edits','artwork':'no-collateral-edits','font':'no-collateral-edits',
                        'diagnosis':'seeded-diagnosis','review':'repair-pixels','pixels':'preflight-delivery','delivery':'preflight-delivery',
                        'fingerprint':'history-valid','history':'history-valid','review-image':'history-valid'}[fault]
                    self.assertIn(expected,[c['name'] for c in case.checks if c['status']=='fail'],case.checks)

    def test_capture_rejudges_with_local_fonts_after_original_root_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);configuration=driver('--custom-session-store','--custom-receipt-store','--repair-review-envelope')
            row=run_external_task(EXE,root/'live','B16',1,'model',configuration)
            self.assertEqual(row['status'],'passed',row);before=workspace_files(root/'live/workspace')
            self.assertFalse((root/'live/workspace/.inkbolt/sessions').exists())
            self.assertFalse((root/'live/workspace/.inkbolt/publications').exists())
            self.assertTrue((root/'live/workspace/.inkbolt/fonts').is_dir())
            self.assertTrue(json.loads((root/'live/workspace/review.json').read_bytes())['ok'])
            (root/'live').rename(root/'moved')
            imported=run_external_task(EXE,root/'import','B16',1,'model',configuration,import_source=root/'moved')
            self.assertEqual(imported['status'],'passed',imported);self.assertFalse(imported['model_trials'])
            self.assertEqual(before,workspace_files(root/'moved/workspace'));self.assertEqual(before,workspace_files(root/'import/workspace'))

    def test_stores_must_be_unique_and_intact_and_default_font_store_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'model',custom=True);original=case.call;case.results.clear();case.begin_judging()
            paths=[next((case.root/name).glob('*.sqlite3')) for name in ('chosen sessions','chosen receipts')]
            fonts=list((case.root/'.inkbolt/fonts').glob('*.font'))+list((case.root/'.inkbolt/fonts').glob('*.license'))
            self.assertEqual(len(fonts),2)
            for index,path in enumerate(paths+fonts):
                raw=path.read_bytes()
                for fault in (('missing','ambiguous','corrupt') if path in paths else ('missing','corrupt')):
                    with self.subTest(store=path.name,fault=fault):
                        label=f'{index}-{fault}';case.checks.clear()
                        case.call=lambda step,command,**arguments:original(label+'-'+step,command,**arguments)
                        duplicate=case.root/'duplicate'/path.name
                        if fault=='missing':path.unlink()
                        elif fault=='ambiguous':
                            duplicate.parent.mkdir(exist_ok=True);duplicate.write_bytes(raw)
                        else:path.write_bytes(b'corrupt retained resource')
                        with self.assertRaises(TaskFailure):judge(case)
                        if path in fonts:
                            self.assertIn('no-collateral-edits',[c['name'] for c in case.checks if c['status']=='fail'])
                        else:
                            self.assertEqual({c['name'] for c in case.checks if c['status']=='pass'},set(CHECKS['B16'])-{'history-valid'})
                        path.write_bytes(raw)
                        if duplicate.exists():duplicate.unlink()

    def test_review_envelope_and_publication_binding_remain_required_history(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'model');original=case.call;case.results.clear();case.begin_judging()
            path=case.root/'review.json';raw=path.read_bytes()
            for fault in ('error','boolean','extra','result','proposal','publication'):
                with self.subTest(fault=fault):
                    value=dict(ok=True,result=json.loads(raw));case.checks.clear()
                    if fault=='error':value['ok']=False
                    elif fault=='boolean':value['ok']=1
                    elif fault=='extra':value['other']='unrequested'
                    elif fault=='result':value['result']=[]
                    elif fault=='proposal':value['result']['proposal']['result_state_sha256']='0'*64
                    path.write_text(json.dumps(value),encoding='utf-8')
                    def call(step,command,**arguments):
                        result=original(fault+'-'+step,command,**arguments)
                        if fault=='publication' and command=='publication.receipt':result['result']['format']='snapshot'
                        return result
                    case.call=call;judge(case)
                    self.assertEqual([c['name'] for c in case.checks if c['status']=='fail'],['history-valid'],case.checks)

    def test_baseline_requires_fresh_rasterized_pixels_and_prepared_identity_without_engine(self):
        for fault in ('none','alternate','pixels','encoding'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as directory:
                raw=png(48,32,expected_picture()) if fault!='pixels' else png(1,1,bytes(4))
                if fault=='alternate':raw=png(48,32,expected_picture(),extra=((b'tEXt',b'Comment\0Original alternate encoding'),))
                if fault=='encoding':raw+=b'different encoding'
                with patch('benchmark_baseline_repair.render_repair',return_value=raw), \
                     patch('benchmark_driver.ExternalTrial.call',side_effect=AssertionError('Baseline launched Inkbolt')):
                    row=run_external_task(None,Path(directory)/'baseline','B16',1,'baseline',driver('--preview-usage'),fake_tools())
                self.assertEqual(row['status'],'passed' if fault in ('none','alternate') else 'failed',row)
                if fault in ('none','alternate'):
                    self.assertEqual(row['first_verified_preview_seconds'],.5)
                    self.assertEqual({c['name'] for c in row['checks'] if c['status']=='not_applicable'},{'history-valid'})
                    if fault=='alternate':self.assertNotEqual(raw,(Path(directory)/'baseline/workspace/repaired.png').read_bytes())
                else:self.assertIn('repair-pixels',[c['name'] for c in row['checks'] if c['status']=='fail'])

    def test_baseline_delivery_requires_both_exact_hashes_boolean_readiness_and_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            case=Trial(None,Path(directory)/'baseline','B16',1,'cli',CHECKS['B16'],arm='baseline');self.addCleanup(case.close)
            fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));author(case.root)
            raw=png(48,32,expected_picture());publish(case.root,raw);case.begin_judging()
            original=json.loads((case.root/'delivery.json').read_bytes())
            for fault in ('sha256','preflight_sha256','ready','pixels'):
                with self.subTest(fault=fault):
                    value=dict(original);case.checks.clear();(case.root/'repaired.png').write_bytes(raw)
                    if fault in ('sha256','preflight_sha256'):value[fault]='0'*64
                    elif fault=='ready':value['ready']=1
                    else:
                        wrong=png(48,32,bytes(48*32*4));(case.root/'repaired.png').write_bytes(wrong)
                        value['sha256']=value['preflight_sha256']=sha(wrong)
                    (case.root/'delivery.json').write_text(json.dumps(value),encoding='utf-8')
                    with patch('benchmark_baseline_repair.render_repair',return_value=raw):judge_repair(case,fake_tools())
                    self.assertEqual([c['name'] for c in case.checks if c['status']=='fail'],['preflight-delivery'],case.checks)

    def test_baseline_source_admission_precedes_rasterizer_and_accepts_equal_numbers(self):
        with tempfile.TemporaryDirectory() as directory:
            case=Trial(None,Path(directory)/'baseline','B16',1,'cli',CHECKS['B16'],arm='baseline');self.addCleanup(case.close)
            fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));author(case.root);publish(case.root,png(48,32,expected_picture()));case.begin_judging()
            good={name:(case.root/name).read_bytes() for name in ('before.json','editable.json','before.svg','editable.svg')}
            for fault in ('initial','policy','boolean','font','external','placement','extra'):
                with self.subTest(fault=fault):
                    for name,raw in good.items():(case.root/name).write_bytes(raw)
                    case.checks.clear()
                    if fault in ('initial','policy','boolean','font'):
                        name='before.json' if fault=='initial' else 'editable.json';value=json.loads(good[name])
                        if fault=='initial':value['items'][0]['content']['frame']['width']=24
                        elif fault=='policy':value['items'][0]['content']['frame']['wrap']=True
                        elif fault=='boolean':value['fonts']['face']['face_index']=False
                        else:value['fonts']['face']['sha256']='../external'
                        (case.root/name).write_text(json.dumps(value),encoding='utf-8')
                    else:
                        value=good['editable.svg'].decode()
                        if fault=='external':value=value.replace('<text ','<text href="file:///outside" ')
                        elif fault=='placement':value=value.replace('y="16"','y="17"')
                        else:value=value.replace('</svg>','<script>changed</script></svg>',1)
                        (case.root/'editable.svg').write_text(value,encoding='utf-8')
                    with patch('benchmark_baseline_repair.render_repair',side_effect=AssertionError('Renderer ran before admission')),self.assertRaises(TaskFailure):
                        judge_repair(case,fake_tools())
                    self.assertIn('no-collateral-edits',[c['name'] for c in case.checks if c['status']=='fail'])
            for name,raw in good.items():(case.root/name).write_bytes(raw)
            value=json.loads(good['editable.json']);value['width']=48.0;value['items'][0]['content']['frame']['width']=24.0
            (case.root/'editable.json').write_text(json.dumps(value),encoding='utf-8');case.checks.clear()
            with patch('benchmark_baseline_repair.render_repair',return_value=png(48,32,expected_picture())):judge_repair(case,fake_tools())
            self.assertFalse(any(c['status']=='fail' for c in case.checks),case.checks)


if __name__=='__main__':unittest.main()
