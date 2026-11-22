"""B12 editable variant state, resources and delivered artwork."""
import copy
from contextlib import closing, ExitStack
import json
from pathlib import Path
import shutil
import struct
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_cli import EXE, ROOT
sys.path.insert(0,str(ROOT/'tools'))

from benchmark_variants import (
    fixture,
    solve,
    judge,
    PROMPT,
    initial_document,
    FONT_FAMILY,
    hierarchical_state,
)
from benchmark_runtime import Trial,TaskFailure
from benchmark_tasks import CHECKS
from synthetic_font import geometric_font
from test_images_cli import png
from workload_cases import sha


class VariantJudgeTests(unittest.TestCase):
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

    def test_independent_ids_and_extra_edit_pass_without_solver_results(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'independent',True);case.results.clear();case.begin_judging();judge(case)
            row=case.finish();self.assertEqual(row['status'],'passed',row);self.assertIsNone(row['first_verified_preview_seconds'])
            locator=json.loads((case.root/'session.json').read_bytes())
            self.assertEqual(locator['session_id'],'family-session');self.assertEqual(locator['revisions']['restored'],6)

    @staticmethod
    def damage(case, fault):
        name='base.json' if fault in ('binding','binding-target','inheritance') else 'restored.json' if fault=='restored' else 'source-square.json'
        path=case.root/name;data=json.loads(path.read_bytes())
        if fault=='binding':data['variants']['definition']['bindings'][0]['key']='other'
        elif fault=='binding-target':data['variants']['definition']['bindings'][0]['item_id']='image'
        elif fault=='inheritance':data['variants']['definition']['datasets']['square'].pop('parent')
        elif fault=='restored':data['items'][1]['content']['frame']['style']['size']=21
        elif fault=='board':data['items'][5]['content']['frame']['width']=33
        elif fault in ('image','font'):
            if fault == 'image':
                p = next((case.root / '.inkbolt/assets').glob('*.rgba8'))
            else:
                p = next((case.root / '.inkbolt/fonts').glob('*.font'))
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
        path.write_text(json.dumps(data),encoding='utf-8')

    def test_damaged_controls_resources_deliveries_receipts_and_head_reject(self):
        faults = {
            'intact': None,
            'binding': 'Expected exactly the label, place and image binding keys',
            'binding-target': 'INVALID_VARIANT',
            'inheritance': 'The complete base layout or variant definition changed',
            'restored': 'The complete base was not restored',
            'board': 'Selection changed bindings or unrelated shared state: square',
            'image': 'Missing intact workspace image store',
            'font': 'Missing intact workspace font store',
            'preview': 'Delivered image dimensions changed',
            'output-hash': 'Earlier output differs from its completed publication receipt: wide',
            'receipt': 'Earlier output differs from its completed publication receipt: wide',
            'receipt-bytes': 'PUBLICATION_CORRUPT',
            'old-state': 'revisions must be in increasing order',
            'new-head': 'History must bind every selected snapshot and the restored current head',
            'missing': 'Missing or external deliverable: tall.png',
        }
        with tempfile.TemporaryDirectory() as directory:
            solved = self.prepare(Path(directory) / 'work')
            template = solved.root.rename(Path(directory) / 'template')
            for fault, reason in faults.items():
                with self.subTest(fault=fault), ExitStack() as cleanup:
                    # Receipts bind the original absolute path. Restore there for each judge.
                    shutil.copytree(template, solved.root)
                    cleanup.callback(shutil.rmtree, solved.root)
                    case = copy.deepcopy(solved)
                    if reason is not None:
                        self.damage(case, fault)
                    case.begin_judging()
                    try:judge(case)
                    except (TaskFailure,ValueError,KeyError) as error:case.error=str(error)
                    row = case.finish()
                    if reason is None:
                        self.assertEqual(row['status'], 'passed', row)
                    else:
                        self.assertEqual(row['status'], 'failed', row)
                        errors = [row['error'] or '']
                        errors.extend(c['error'] for c in row['checks'] if c['status'] == 'fail')
                        self.assertTrue(any(reason in message for message in errors), errors)

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


if __name__=='__main__':unittest.main()
