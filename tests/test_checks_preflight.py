"""Located diagnostics, exact preflight outputs and seeded repairs without collateral edits."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import base64
import copy
import hashlib
import json
from pathlib import Path
import unittest

import test_agent_workspace as workspace
from synthetic_font import geometric_font
from test_images_cli import png
from test_editing_cli import png_pixels
from test_mcp import Client


class CheckPreflightTests(unittest.TestCase):
    setUp=workspace.AgentWorkspaceTests.setUp
    cli=workspace.AgentWorkspaceTests.cli
    save=workspace.AgentWorkspaceTests.save
    ref=workspace.AgentWorkspaceTests.ref

    def document(self,kind='vector',items=None):
        d=self.cli('document.create',id='checks-original',kind=kind,width=32,height=24)
        d['items']=items or []
        return d

    def files(self):
        return {str(p.relative_to(self.root)):(p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest()) for p in self.root.rglob('*') if p.is_file()}

    def font(self,store_root='fonts'):
        source=self.root/'original.ttf';license=self.root/'original-license.txt'
        if not source.exists():source.write_bytes(geometric_font());license.write_text('Original synthetic Inkbolt font fixture.')
        return self.cli('font.import',source_path='original.ttf',license_path='original-license.txt',store_root=store_root)

    def frame(self,width=6,overflow='error',**kw):
        return dict(text='AA',width=width,height=10,wrap=False,overflow=overflow,style=dict(font_id='geometry',size=10,fill=[25,100,200,255]),**kw)

    def text_document(self,width=6,overflow='error'):
        d=self.document(items=[dict(id='label',content=dict(type='text',frame=self.frame(width,overflow))),
                               dict(id='keep',content=dict(type='vector',geometry=dict(shape='rect',x=25,y=15,width=4,height=3),fill=[200,80,30,255]))])
        d['fonts']={'geometry':self.font()}
        return self.cli('document.validate',document=d)

    def check(self,d,**kw):
        return self.cli('document.check',document=d,**kw)

    def preflight(self,d,name='ready.png',format='png',**kw):
        return self.cli('document.preflight',document=d,output=dict(file_name=name,format=format,**kw))

    def test_seeded_overflow_repair_checked_proposal_and_exact_delivery(self):
        d=self.text_document();self.save(d,resources=dict(font_root='fonts'))
        before=self.files();report=self.check(self.ref())
        self.assertEqual(report['status'],'fail');self.assertTrue(report['complete']);self.assertTrue(report['valid_structure'])
        issue=report['issues'][0];self.assertEqual(issue['error']['code'],'TEXT_OVERFLOW')
        self.assertEqual(issue['error']['item_id'],'label');self.assertEqual(issue['location']['pointer'],'/items/0/content')
        self.assertIn('text.inspect',issue['recovery']['commands']);self.assertFalse(issue['recovery']['automatic_fix'])
        failed=self.preflight(self.ref());self.assertFalse(failed['ready']);self.assertEqual(failed['issues'][0]['error']['code'],'TEXT_OVERFLOW')
        self.assertEqual(self.files(),before)
        frame=copy.deepcopy(d['items'][0]['content']['frame']);frame['width']=12
        action=dict(type='edit',operations=[dict(op='text',id='label',frame=frame)])
        proposal=self.cli('session.dry_run',session_id='work',request_id='repair',expected_revision=0,action=action,options=dict(include_document=True,preview=True))
        repaired=proposal['proposed_document']
        self.assertEqual(repaired['items'][1],d['items'][1]);self.assertEqual(repaired['fonts'],d['fonts'])
        self.assertEqual(repaired['items'][0]['content']['frame']['text'],'AA')
        self.assertEqual([i['id'] for i in proposal['difference']['items']],['label'])
        self.assertEqual(self.check(repaired,resources=dict(font_root='fonts'))['status'],'pass')
        prepared=self.cli('document.preflight',document=repaired,resources=dict(font_root='fonts'),output=dict(file_name='repaired.png',format='png'))
        self.assertTrue(prepared['ready']);self.assertFalse(prepared['prepared_output']['created']);self.assertEqual(self.files(),before)
        with closing(Client(('--tools','core'),workspace=self.root)) as c:
            c.initialize();self.assertEqual(c.success('document.check',document=self.ref()),report)
            self.assertEqual(c.tool('run',command='document.preflight',arguments=dict(document=self.ref(),output=dict(file_name='ready.png',format='png')))['structuredContent']['result'],failed)
        committed=self.cli('session.apply_proposal',proposal=proposal['proposal'],action=action)
        self.assertEqual(committed['document'],repaired)
        self.assertEqual(self.check(self.ref(1))['status'],'pass');self.assertEqual(self.check(self.ref())['status'],'fail')
        receipt=self.cli('session.publish',session_id='work',expected_revision=1,output=dict(file_name='repaired.png',format='png'))
        self.assertEqual(receipt,dict(prepared['prepared_output'],created=True,session_id='work',observed_current_revision=1))
        data=(self.root/'repaired.png').read_bytes();self.assertEqual(hashlib.sha256(data).hexdigest(),receipt['sha256'])
        w,h,p,_=png_pixels(data);self.assertEqual((w,h),(32,24))
        for y in range(24):
            for x in range(20,32):
                expected=bytes([200,80,30,255]) if 25<=x<29 and 15<=y<18 else bytes(4)
                self.assertEqual(p[(y*32+x)*4:(y*32+x+1)*4],expected)
        self.assertEqual(self.cli('document.validate',document=self.ref()),d)
        self.cli('session.verify',session_id='work')

    def test_missing_and_corrupt_resources_repair_by_new_verified_store(self):
        d=self.text_document(width=12)
        original=png(1,1,bytes([20,80,160,255]));(self.root/'source.png').write_bytes(original)
        asset=self.cli('asset.import',source_path='source.png',store_root='broken-assets')['asset']
        d['assets']={'paint':asset} # unused resources must still be checked
        blob=next(p for p in (self.root/'broken-assets').iterdir() if p.is_file());blob.write_bytes(b'corrupt fixture')
        self.save(d,resources=dict(asset_root='broken-assets',font_root='missing-fonts'))
        before=self.files();r=self.check(self.ref())
        self.assertEqual(r['status'],'fail');self.assertFalse(r['complete']);self.assertEqual(r['checked']['skipped_layouts'],1)
        self.assertEqual({i['error']['code'] for i in r['issues']},{'ASSET_CORRUPT','FONT_MISSING'})
        self.assertEqual({i['location']['pointer'] for i in r['issues']},{'/assets/paint','/fonts/geometry'})
        self.assertEqual(self.files(),before)
        self.assertEqual(self.cli('asset.import',source_path='source.png',store_root='repaired-assets')['asset'],asset)
        self.font('repaired-fonts')
        action=dict(type='resources',resources=dict(asset_root='repaired-assets',font_root='repaired-fonts'))
        proposal=self.cli('session.dry_run',session_id='work',request_id='resolve',expected_revision=0,action=action,options=dict(include_document=True))
        self.assertEqual(proposal['proposed_document']['items'],d['items']);self.assertEqual(proposal['proposed_document']['assets'],d['assets'])
        self.assertEqual(self.check(proposal['proposed_document'],resources=proposal['proposed_resources'])['status'],'pass')
        self.cli('session.apply_proposal',proposal=proposal['proposal'],action=action)
        self.assertEqual(self.check(self.ref(1))['status'],'pass');self.assertEqual(self.check(self.ref())['status'],'fail')
        self.assertEqual((self.root/'source.png').read_bytes(),original);self.assertEqual(blob.read_bytes(),b'corrupt fixture')

    def test_nested_snapshots_and_instance_overrides_have_original_locations(self):
        child=self.text_document()
        snapshot=json.dumps(child,separators=(',',':'))
        outer=self.document(kind='raster',items=[dict(id='placed',content=dict(type='object',object=dict(snapshot=snapshot,sha256=hashlib.sha256(snapshot.encode()).hexdigest(),width=32,height=24)))])
        before=self.files();r=self.check(outer,resources=dict(font_root='fonts'))
        self.assertEqual(r['checked']['documents'],2);self.assertEqual(r['issues'][0]['location'],dict(retained_document_path=['/items/0/content/object/snapshot'],pointer='/items/0/content'))
        self.assertEqual(outer['items'][0]['content']['object']['snapshot'],snapshot)
        d=self.text_document(width=12);d['items']= [dict(id='source',content=dict(type='component_source')),dict(d['items'][0],parent='source'),dict(id='instance',content=dict(type='instance',instance=dict(source='source',overrides=dict(label=dict(content=dict(type='text',frame=self.frame()))))))]
        r=self.check(d,resources=dict(font_root='fonts'));self.assertEqual(r['checked']['text_frames'],2)
        self.assertEqual(r['issues'][0]['location']['pointer'],'/items/2/content/instance/overrides/label/content');self.assertEqual(r['issues'][0]['error']['item_id'],'instance')
        self.assertEqual(self.files(),before)

    def test_story_tail_policy_warnings_and_explicit_flow_repair(self):
        d=self.text_document(width=12);d['items']=[dict(id='flow',content=dict(type='story_frame',story_id='story',slot_id='slot'))]
        story=dict(paragraphs=[dict(text='AAAAAA',style=self.frame()['style'])],slots=[dict(id='slot',width=12,height=10)],overset='retain');d['stories']={'story':story}
        r=self.check(d,resources=dict(font_root='fonts'));self.assertEqual(r['status'],'warnings');self.assertTrue(r['complete'])
        overset=next(i for i in r['issues'] if i['error']['code']=='STORY_OVERFLOW');self.assertEqual(overset['context']['overset'],dict(paragraph=0,offset=2))
        story['overset']='error';self.assertEqual(self.check(d,resources=dict(font_root='fonts'))['status'],'fail')
        text=story['paragraphs'][0]['text'];story['slots'][0]['height']=30
        self.assertEqual(self.check(d,resources=dict(font_root='fonts'))['status'],'pass');self.assertEqual(story['paragraphs'][0]['text'],text)

    def test_diagnostic_limits_disabled_checks_and_invalid_structure(self):
        d=self.text_document(overflow='visible');item=d['items'][0];d['items']=[dict(item,id=f'label-{i}') for i in range(12)]
        r=self.check(d,resources=dict(font_root='fonts'),options=dict(issue_limit=3))
        self.assertEqual(r['status'],'incomplete');self.assertFalse(r['complete']);self.assertTrue(r['stopped_at_limit']);self.assertEqual(len(r['issues']),3)
        self.assertLess(len(json.dumps(r).encode()),128*1024)
        self.assertEqual(len(self.check(d,resources=dict(font_root='fonts'),options=dict(issue_limit=20))['issues']),12)
        r=self.check(d,options=dict(resources=False,typography=False));self.assertEqual(r['status'],'pass');self.assertEqual(r['checked']['fonts'],0)
        d['width']=0;r=self.check(d);self.assertFalse(r['valid_structure']);self.assertFalse(r['complete']);self.assertIsNone(r['document_sha256']);self.assertEqual(r['checked']['fonts'],0)
        for n in [0,257]:self.check(self.document(),options=dict(issue_limit=n),error='INVALID_REQUEST')

    def test_empty_text_still_validates_requested_font_axes(self):
        d=self.text_document();frame=d['items'][0]['content']['frame'];frame['text']='';frame['style']['font_variations']={'geometry':{'wght':1}}
        r=self.check(d,resources=dict(font_root='fonts'));self.assertEqual(r['status'],'fail')
        issue=r['issues'][0];self.assertEqual(issue['error']['code'],'FONT_AXIS_UNAVAILABLE');self.assertEqual(issue['error']['font_id'],'geometry')
        self.assertIn('font.inspect',issue['recovery']['commands'])

    def test_report_byte_budget_and_shared_nested_layout_budget_are_explicit(self):
        child=self.document();child['fonts']={f'f{i}-'+('x'*125):dict(sha256='a'*64,license_sha256='b'*64,face_index=0,bytes=100) for i in range(8)}
        snapshot=json.dumps(child,separators=(',',':'));obj=dict(snapshot=snapshot,sha256=hashlib.sha256(snapshot.encode()).hexdigest(),width=32,height=24)
        d=self.document(kind='raster',items=[dict(id=f'object-{i}',content=dict(type='object',object=obj)) for i in range(24)])
        r=self.check(d,options=dict(issue_limit=256));self.assertFalse(r['complete']);self.assertTrue(r['stopped_at_limit'])
        self.assertLess(len(r['issues']),192);self.assertLessEqual(len(json.dumps(r,separators=(',',':')).encode()),128*1024)
        child=self.text_document(width=3000);frame=child['items'][0]['content']['frame'];frame['text']='A'*4000;frame['style']['size']=1
        snapshot=json.dumps(child,separators=(',',':'));obj=dict(snapshot=snapshot,sha256=hashlib.sha256(snapshot.encode()).hexdigest(),width=32,height=24)
        d=self.document(kind='raster',items=[dict(id=f'object-{i}',content=dict(type='object',object=obj)) for i in range(3)])
        r=self.check(d,resources=dict(font_root='fonts'));self.assertFalse(r['complete']);self.assertTrue(r['stopped_at_limit'])
        self.assertEqual(r['issues'][-1]['error']['code'],'RESOURCE_LIMIT')

    def test_preflight_matches_all_shared_artifact_receipts_without_writes(self):
        d=self.document(items=[dict(id='shape',content=dict(type='vector',geometry=dict(shape='rect',x=1,y=1,width=8,height=6),fill=[30,80,170,255]))])
        formats=[('png','png'),('svg','svg'),('snapshot','json'),('tiff','tiff'),('bmp','bmp'),('tga','tga'),('pdf','pdf')]
        for format,ext in formats:
            with self.subTest(format=format):
                name=f'proof.{ext}';before=self.files();options=dict(image_options=dict(matte=[255,255,255])) if format=='bmp' else {};r=self.preflight(d,name,format,**options)
                self.assertTrue(r['ready'],r);self.assertFalse(r['prepared_output']['created']);self.assertEqual(self.files(),before)
                receipt=self.cli('document.publish',document=d,output=dict(file_name=name,format=format,**options))
                self.assertEqual(receipt,dict(r['prepared_output'],created=True))
                raw=(self.root/name).read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),receipt['sha256']);self.assertEqual(len(raw),receipt['bytes'])
        before=self.files();r=self.preflight(d,'proof.png');self.assertFalse(r['ready']);self.assertEqual(r['issues'][0]['error']['code'],'OUTPUT_EXISTS');self.assertEqual(self.files(),before)

    def test_preflight_failure_parity_destination_race_and_cancel(self):
        d=self.document()
        for output in [dict(file_name='wrong.txt',format='png'),dict(file_name='new.png',format='png',output_root='missing'),dict(file_name='image.png',format='png',scale=5),dict(file_name='image.jpg',format='jpeg')]:
            before=self.files();pre=self.cli('document.preflight',document=d,output=output);self.assertFalse(pre['ready'])
            error=pre['issues'][0]['error'];actual=self.cli('document.publish',document=d,output=output,error=error['code']);self.assertEqual(actual,error)
            self.assertEqual(self.files(),before)
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:self.preflight(d),range(2)))
        self.assertTrue(all(r['ready'] for r in results));self.assertEqual(results[0],results[1]);self.assertFalse((self.root/'ready.png').exists())
        self.cli('document.publish',document=d,output=dict(file_name='ready.png',format='png'))
        before=self.files();self.assertFalse(self.preflight(d)['ready']);self.assertEqual(self.files(),before)
        for command,args in [('document.check',{}),('document.preflight',dict(output=dict(file_name='cancelled.png',format='png')))]:
            self.cli(command,document=d,control=dict(timeout_ms=0),error='TIMEOUT',**args)
        self.assertEqual(self.files(),before)


if __name__=='__main__':unittest.main()
