"""B12 independent state, resource, viewport and durable publication checks."""
import copy
from contextlib import closing
import json
from pathlib import Path
import struct
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_cli import EXE,ROOT
sys.path.insert(0,str(ROOT/'tools'))
from agent_benchmark import run_task
from benchmark_variants import fixture,solve,judge,PROMPT,initial_document,FONT_FAMILY,BOARDS,expected_picture,hierarchical_state
from benchmark_baseline_variants import svg_layout,manifest,judge_variants
from benchmark_driver import run_external_task,workspace_files
from benchmark_runtime import Trial,TaskFailure
from benchmark_tasks import CHECKS
from benchmark_variants_client import author
from synthetic_font import geometric_font
from test_benchmark_driver import driver,fake_tools
from test_images_cli import png
from workload_cases import sha


class VariantBenchmarkTests(unittest.TestCase):
    def prepare(self,root,independent=False):
        case=Trial(EXE,root,'B12',1,'cli',CHECKS['B12']);self.addCleanup(case.close)
        fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'))
        if not independent:solve(case);return case
        original=case.call
        def authored(step,command,**arguments):
            if arguments.get('session_id')=='work':arguments['session_id']='family-session'
            if step=='select-square':
                result=original('artist-extra','session.apply',session_id='family-session',request_id='extra',expected_revision=arguments['expected_revision'],
                    action=dict(type='edit',operations=[dict(op='variant_select',dataset='wide')]),response_mode='compact')
                arguments['expected_revision']=result['document_ref']['revision']
            return original('artist-'+step,command,**arguments)
        case.call=authored
        names=dict(document='family',shared='component',title='label',image='photo',face='typeface',
                   green='leaf',orange='sunset',copies=['first','second','third'])
        with patch('benchmark_variants.initial_document',side_effect=lambda font,assets:initial_document(font,assets,names)):solve(case)
        return case

    def baseline(self,root):
        case=Trial(None,root,'B12',1,'cli',CHECKS['B12'],arm='baseline');self.addCleanup(case.close)
        fixture(case);author(root);(root/'editable.svg').write_bytes((root/'base.svg').read_bytes())
        identities={}
        for name,w,h,_,_ in BOARDS:
            raw=png(w,h,expected_picture(name));(root/(name+'.png')).write_bytes(raw);identities[name]=sha(raw)
        (root/'outputs.json').write_text(json.dumps(identities),encoding='utf-8')
        return case

    def test_original_fixtures_and_named_font_keep_every_non_naming_table(self):
        def tables(raw):
            count=struct.unpack_from('>H',raw,4)[0];values={}
            for at in range(12,12+16*count,16):
                tag,_,offset,length=struct.unpack_from('>4sIII',raw,at);data=raw[offset:offset+length]
                if tag==b'head':data=data[:8]+bytes(4)+data[12:]
                values[tag]=data
            return values
        original=geometric_font();named=geometric_font(family=FONT_FAMILY)
        self.assertEqual(sha(original),'0bc1bae3dae5c43f7a8eb8500b12ea60f16afd6317501878cbee455b30401b11')
        before,after=tables(original),tables(named);self.assertEqual(set(after)-set(before),{b'name'})
        self.assertEqual(before,{k:v for k,v in after.items() if k!=b'name'})

    def test_reference_transports_keep_original_outcomes_and_separate_judge_traffic(self):
        for transport in ('cli','mcp'):
            with self.subTest(transport=transport),tempfile.TemporaryDirectory() as directory:
                row=run_task(EXE,Path(directory)/'reference','B12',1,transport)
                self.assertEqual(row['status'],'passed',row);self.assertEqual((row['engine_commands'],row['judge_engine_commands']),(18,18))
                self.assertEqual({c['name'] for c in row['checks']},set(CHECKS['B12'])|{'source-preservation'})
                self.assertEqual(row['sources']['green.png'],'3e3f4de7859b333f69ac692e04b6fa7d78ad1cc49105c385e12b5a6b4a65f27b')
                self.assertEqual(row['sources']['orange.png'],'ecc09c674ec0eba98d3890f5e0eb393ba07fa46e4df3a4f0d524451f81db176e')
                self.assertTrue(row['judge_separated']);self.assertGreater(row['first_verified_preview_seconds'],0)

    def test_independent_ids_and_extra_edit_pass_without_solver_results(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'independent',True);case.results.clear();case.begin_judging();judge(case)
            row=case.finish();self.assertEqual(row['status'],'passed',row);self.assertIsNone(row['first_verified_preview_seconds'])
            locator=json.loads((case.root/'session.json').read_bytes())
            self.assertEqual(locator['session_id'],'family-session');self.assertEqual(locator['revisions']['restored'],6)

    def test_damaged_controls_resources_deliveries_receipts_and_head_reject(self):
        for fault in ('binding','binding-target','inheritance','restored','board','image','font','preview','output-hash','receipt','receipt-bytes','old-state','new-head','missing'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as directory:
                case=self.prepare(Path(directory)/fault)
                name='base.json' if fault in ('binding','binding-target','inheritance') else 'restored.json' if fault=='restored' else 'source-square.json'
                path=case.root/name;data=json.loads(path.read_bytes())
                if fault=='binding':data['variants']['definition']['bindings'][0]['key']='other'
                elif fault=='binding-target':data['variants']['definition']['bindings'][0]['item_id']='image'
                elif fault=='inheritance':data['variants']['definition']['datasets']['square'].pop('parent')
                elif fault=='restored':data['items'][1]['content']['frame']['style']['size']=21
                elif fault=='board':data['items'][5]['content']['frame']['width']=33
                elif fault in ('image','font'):
                    p=next((case.root/('.inkbolt/assets' if fault=='image' else '.inkbolt/fonts')).glob('*.rgba8' if fault=='image' else '*.font'))
                    raw=bytearray(p.read_bytes());raw[-1]^=1;p.write_bytes(raw)
                elif fault=='preview':(case.root/'square.png').write_bytes(png(1,1,bytes(4)))
                elif fault=='output-hash':
                    p=case.root/'outputs.json';value=json.loads(p.read_bytes());value['wide']='0'*64;p.write_text(json.dumps(value),encoding='utf-8')
                elif fault=='receipt-bytes':
                    with closing(sqlite3.connect(case.root/'.inkbolt/publications/publications.sqlite3')) as db:
                        db.execute("UPDATE publications SET sha256=?",('0'*64,));db.commit()
                elif fault in ('receipt','old-state'):
                    p=case.root/'session.json';value=json.loads(p.read_bytes())
                    if fault=='receipt':value['publications']['wide']=value['publications']['square']
                    else:value['revisions']['wide']=1
                    p.write_text(json.dumps(value),encoding='utf-8')
                elif fault=='new-head':case.call('later','session.apply',session_id='work',request_id='later',expected_revision=5,
                    action=dict(type='edit',operations=[dict(op='variant_select',dataset='wide')]),response_mode='compact')
                elif fault=='missing':(case.root/'tall.png').unlink()
                path.write_text(json.dumps(data),encoding='utf-8');case.begin_judging()
                try:judge(case)
                except (TaskFailure,ValueError,KeyError) as error:case.error=str(error)
                self.assertEqual(case.finish()['status'],'failed',fault)

    def test_external_capture_rejudges_moved_workspaces_without_modifying_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);configuration=driver('--custom-session-store','--custom-font-store','--custom-asset-store','--custom-receipt-store','--variant-binding-order','--variant-add-items','--variant-board-labels')
            row=run_external_task(EXE,root/'live','B12',1,'model',configuration)
            self.assertEqual(row['status'],'passed',row);before=workspace_files(root/'live/workspace')
            for name in ('sessions','fonts','assets','publications'):self.assertFalse((root/'live/workspace/.inkbolt'/name).exists())
            self.assertEqual(len(list((root/'live/workspace/chosen receipts').rglob('publications.sqlite3'))),3)
            base=json.loads((root/'live/workspace/base.json').read_bytes())
            self.assertEqual([b['key'] for b in base['variants']['definition']['bindings']],['image','place','label'])
            self.assertEqual([item['id'] for item in base['items'][:4]],['shared','wide','square','tall'])
            self.assertEqual({item['id']:item['name'] for item in base['items'] if item['id'] in ('wide','square','tall')},
                             dict(wide='wide',square='square',tall='tall'))
            self.assertEqual([item['id'] for item in base['items'] if item.get('parent')=='shared'],['title','image'])
            (root/'live').rename(root/'capture')
            imported=run_external_task(EXE,root/'import','B12',1,'model',configuration,import_source=root/'capture')
            self.assertEqual(imported['status'],'passed',imported);self.assertFalse(imported['model_trials'])
            self.assertEqual(before,workspace_files(root/'capture/workspace'));self.assertEqual(before,workspace_files(root/'import/workspace'))

    def test_native_authored_tree_rejects_changed_siblings_parents_and_properties(self):
        for fault in ('--variant-child-order','--variant-root-order','--variant-reparent','--variant-extra-property','--variant-wrong-board-label'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as directory:
                row=run_external_task(EXE,Path(directory)/'failed','B12',1,'model',driver('--variant-add-items',fault))
                self.assertTrue((Path(directory)/'failed/workspace/session.json').is_file(),row)
                self.assertEqual(row['status'],'failed',row)
                if fault=='--variant-reparent':self.assertIn('Expected exactly one image',row['error'])
                else:self.assertIn('base-preserved',[c['name'] for c in row['checks'] if c['status']=='fail'])

    def test_hierarchy_comparison_retains_every_property_and_sibling_order(self):
        value=dict(id='layout',items=[dict(id='a'),dict(id='child',parent='a',opacity=1),dict(id='b')])
        interleaved=copy.deepcopy(value);interleaved['items']=[interleaved['items'][i] for i in (0,2,1)]
        self.assertEqual(hierarchical_state(value),hierarchical_state(interleaved))
        self.assertEqual([item['id'] for item in interleaved['items']],['a','b','child'])
        for fault in ('roots','parent','property','missing','extra'):
            changed=copy.deepcopy(interleaved)
            if fault=='roots':changed['items'][0:2]=reversed(changed['items'][0:2])
            elif fault=='parent':changed['items'][2]['parent']='b'
            elif fault=='property':changed['items'][2]['opacity']=0.5
            elif fault=='missing':changed['items'].pop()
            else:changed['items'].append(dict(id='extra'))
            self.assertNotEqual(hierarchical_state(value),hierarchical_state(changed),fault)
        duplicate=copy.deepcopy(value);duplicate['items'].append(dict(id='child'))
        with self.assertRaises(TaskFailure):hierarchical_state(duplicate)

    def test_custom_stores_require_intact_original_images_font_and_license(self):
        for fault in ('--missing-asset-copy','--corrupt-font-copy','--missing-font-license'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as directory:
                row=run_external_task(EXE,Path(directory)/'failed','B12',1,'model',driver(
                    '--custom-session-store','--custom-font-store','--custom-asset-store','--custom-receipt-store',fault))
                self.assertEqual(row['status'],'failed',row)
                self.assertIn('base-preserved',[c['name'] for c in row['checks'] if c['status']=='fail'])

    def test_baseline_uses_fresh_viewports_and_never_launches_engine(self):
        for fault in ('none','render','delivery'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as directory:
                def rendered(case,tools,name,root):
                    _,w,h,_,_=next(b for b in BOARDS if b[0]==name)
                    return png(w,h,bytes(w*h*4) if fault=='render' else expected_picture(name))
                with patch('benchmark_baseline_variants.render_variant',side_effect=rendered), \
                     patch('benchmark_driver.ExternalTrial.call',side_effect=AssertionError('Baseline launched engine')):
                    row=run_external_task(None,Path(directory)/'baseline','B12',1,'baseline',
                        driver('--preview-usage',*(['--wrong-image'] if fault=='delivery' else [])),fake_tools())
                self.assertEqual(row['status'],'passed' if fault=='none' else 'failed',row)
                self.assertEqual(row['first_verified_preview_seconds'],.5 if fault=='none' else None)
                self.assertEqual([c['name'] for c in row['checks'] if c['status']=='not_applicable'],['variant-bindings','history-valid'])

    def test_baseline_admission_rejects_unsafe_or_changed_svg_before_rendering(self):
        for fault in ('canvas','path','font','text','shared','extra','doctype'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as directory:
                case=self.baseline(Path(directory)/'baseline');path=case.root/'square.svg';raw=path.read_text()
                if fault=='canvas':raw=raw.replace('width="96"','width="960000"',1)
                elif fault=='path':raw=raw.replace('data:image/png;base64,','https://example.invalid/',1)
                elif fault=='font':raw=raw.replace(FONT_FAMILY,'Other Font')
                elif fault=='text':raw=raw.replace('>AA<','>AAA<')
                elif fault=='shared':raw=raw.replace('xlink:href="#shared"','xlink:href="#another"')
                elif fault=='extra':raw=raw.replace('<defs>','<defs onclick="run()">')
                else:raw='<!DOCTYPE svg>'+raw
                path.write_text(raw,encoding='utf-8')
                with patch('benchmark_baseline_variants.render_variant',side_effect=AssertionError('Unadmitted SVG reached renderer')) as render:
                    with self.assertRaises((TaskFailure,ValueError)):judge_variants(case,fake_tools())
                    render.assert_not_called()

    def test_baseline_retained_base_rows_and_output_hashes_are_checked_separately(self):
        for fault in ('restore','rows','hashes'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as directory:
                case=self.baseline(Path(directory)/'baseline')
                if fault=='restore':(case.root/'editable.svg').write_bytes((case.root/'base.svg').read_bytes()+b'\n')
                elif fault=='rows':
                    data=manifest();data['datasets']['square'].pop('parent');(case.root/'variants.json').write_text(json.dumps(data),encoding='utf-8')
                else:(case.root/'outputs.json').write_text('{}',encoding='utf-8')
                with patch('benchmark_baseline_variants.render_variant',side_effect=lambda case,tools,name,root: (case.root/(name+'.png')).read_bytes()):
                    judge_variants(case,fake_tools())
                failed=[c['name'] for c in case.checks if c['status']=='fail']
                self.assertEqual(failed,['outputs-preserved' if fault=='hashes' else 'base-preserved'])


if __name__=='__main__':unittest.main()
