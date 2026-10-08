"""Original export and comparison fixtures with independent file/pixel checks."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from test_sessions_cli import invoke
from test_editing_cli import png_pixels


class PublishDiffTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def call(self,command,expected=None,**kw):
        result=invoke(dict(command=command,**kw))
        if expected:
            self.assertFalse(result['ok'],result);self.assertEqual(result['error']['code'],expected,result)
            return result['error']
        self.assertTrue(result['ok'],result);return result['result']

    def document(self,kind='vector'):
        d=self.call('document.create',id='original',kind=kind,width=8,height=6)
        content=dict(type='vector',geometry=dict(shape='rect',x=1,y=1,width=3,height=2),fill=[19,83,211,255]) if kind=='vector' else dict(type='raster',width=8,height=6,rgba_hex='1353d3ff'*48)
        return self.call('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=dict(id='shape',content=content))])['document']

    def output(self,name='result.png',fmt='png',**kw):
        return dict(output_root=str(self.root),file_name=name,format=fmt,**kw)

    def test_exact_artifact_bytes_hashes_and_every_existing_destination_is_preserved(self):
        for kind in ['vector','raster']:
            d=self.document(kind)
            for fmt in (['png','svg','snapshot'] if kind=='vector' else ['png','snapshot']):
                name=kind+'.'+('json' if fmt=='snapshot' else fmt)
                artifact=self.call('document.export',document=d,format=fmt)
                expected=base64.b64decode(artifact['data']) if artifact['encoding']=='base64' else artifact['data'].encode()
                receipt=self.call('document.publish',document=d,output=self.output(name,fmt))
                path=self.root/name
                self.assertEqual(path.read_bytes(),expected)
                self.assertEqual(receipt['sha256'],hashlib.sha256(expected).hexdigest())
                self.assertEqual(receipt['bytes'],len(expected))
                self.assertEqual(receipt['revision'],d['revision'])
                self.call('document.publish',document=d,output=self.output(name,fmt),expected='OUTPUT_EXISTS')
                self.assertEqual(path.read_bytes(),expected)
                if fmt=='png':self.assertEqual(png_pixels(expected)[:2],(8,6))
            source=self.root/(kind+'-source.json');source.write_text(json.dumps(d))
            source_bytes=source.read_bytes()
            alias=self.root/(kind+'-alias.json');os.link(source,alias)
            for p in (source,alias):
                self.call('document.publish',document=d,output=self.output(p.name,'snapshot'),expected='OUTPUT_EXISTS')
                self.assertEqual(p.read_bytes(),source_bytes)
        self.assertFalse(list(self.root.glob('.inkbolt-output-*')))

    def test_invalid_names_controls_render_failure_and_concurrent_publish_are_atomic(self):
        d=self.document()
        for name in ['../escape.png','C:stream.png','CON.png','lpt1.png','trailing.png.','bad.svg','.inkbolt-output-2.png']:
            self.call('document.publish',document=d,output=self.output(name),expected='INVALID_REQUEST')
        self.call('document.publish',document=d,output=self.output(),control=dict(timeout_ms=0),expected='TIMEOUT')
        marker=self.root/'cancel';marker.write_bytes(b'cancel')
        self.call('document.publish',document=d,output=self.output(),control=dict(cancel_file=str(marker)),expected='CANCELLED')
        broken=copy.deepcopy(d);broken['items'][0]['blend']='multiply'
        self.call('document.publish',document=broken,output=self.output('no.svg','svg'),expected='UNSUPPORTED')
        self.assertEqual(set(p.name for p in self.root.iterdir()),{'cancel'})
        request=dict(command='document.publish',document=d,output=self.output())
        with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(invoke,[request]*6))
        self.assertEqual(sum(r['ok'] for r in results),1,results)
        self.assertTrue(all(r['ok'] or r['error']['code']=='OUTPUT_EXISTS' for r in results),results)
        self.assertEqual(png_pixels((self.root/'result.png').read_bytes())[:2],(8,6))
        self.assertFalse(list(self.root.glob('.inkbolt-output-*')))

    def test_artboard_publication_preserves_source_and_includes_bleed(self):
        d=self.document();d=self.call('document.edit',document=d,expected_revision=1,operations=[dict(op='add',item=dict(id='board',transform=[1,0,0,1,100,100],content=dict(type='frame',frame=dict(role='artboard',width=4,height=3,background=[3,5,7,255],bleed=dict(left=1,right=2,top=3,bottom=4)))))])['document']
        frozen=copy.deepcopy(d)
        receipt=self.call('document.publish',document=d,output=self.output(artboard_id='board',include_bleed=True))
        w,h,px,_=png_pixels((self.root/'result.png').read_bytes())
        self.assertEqual((w,h),(7,10));self.assertEqual(px,bytes([3,5,7,255])*70)
        self.assertEqual(receipt['artboard_id'],'board');self.assertEqual(d,frozen)

    def test_structural_derived_changes_and_exact_rendered_pixel_delta(self):
        before=self.document()
        after=self.call('document.edit',document=before,expected_revision=1,operations=[dict(op='group',ids=['shape'],new_id='group'),dict(op='transform',id='group',matrix=[1,0,0,1,3,2])])['document']
        diff=self.call('document.diff',before=before,after=after,compare_pixels=True)
        by_id={i['id']:i for i in diff['items']}
        self.assertEqual(by_id['group']['change'],'added')
        shape=by_id['shape'];self.assertIn('parent',shape['fields']);self.assertIn('derived.world_transform',shape['fields'])
        self.assertEqual(shape['before']['geometry_bounds'],[1,1,4,3]);self.assertEqual(shape['after']['geometry_bounds'],[4,3,7,5])
        self.assertEqual(diff['rendered_pixels'],dict(bounds=[1,1,7,5],changed_pixels=12,maximum_channel_delta=255))
        # A later ancestor transform reports a derived child change despite unchanged local item bytes.
        moved=self.call('document.edit',document=after,expected_revision=2,operations=[dict(op='transform',id='group',matrix=[1,0,0,1,2,1])])['document']
        delta=self.call('document.diff',before=after,after=moved)
        child=next(i for i in delta['items'] if i['id']=='shape')
        self.assertEqual(child['before']['sha256'],child['after']['sha256'])
        self.assertIn('derived.geometry_bounds',child['fields'])
        identical=self.call('document.diff',before=before,after=dict(before,revision=99),compare_pixels=True)
        self.assertFalse(identical['changed']);self.assertEqual(identical['items'],[]);self.assertEqual(identical['rendered_pixels']['changed_pixels'],0)

    def test_stored_pixel_deltas_removal_resources_and_incompatible_canvases(self):
        before=self.document('raster')
        after=self.call('document.edit',document=before,expected_revision=1,operations=[dict(op='pixel_fill',id='shape',rect=dict(x=2,y=1,width=4,height=3),color=[1,2,3,255])])['document']
        diff=self.call('document.diff',before=before,after=after,compare_pixels=True)
        self.assertEqual(diff['items'][0]['fields'],['content.rgba_hex'])
        expected=dict(bounds=[2,1,6,4],changed_pixels=12,maximum_channel_delta=208)
        self.assertEqual(diff['items'][0]['stored_pixels'],expected);self.assertEqual(diff['rendered_pixels'],expected)
        removed=dict(after,items=[])
        self.assertEqual(self.call('document.diff',before=after,after=removed)['items'][0]['change'],'removed')
        changed_root=self.call('document.diff',before=before,after=before,before_resources=dict(asset_root=str(self.root/'a')),after_resources=dict(asset_root=str(self.root/'b')))
        self.assertTrue(changed_root['changed']);self.assertTrue(changed_root['resource_bindings_changed'])
        resized=dict(before,width=9)
        self.assertEqual(self.call('document.diff',before=before,after=resized)['metadata'][0],dict(field='width',before=8,after=9))
        self.call('document.diff',before=before,after=resized,compare_pixels=True,expected='UNSUPPORTED')
        self.call('document.diff',before=before,after=dict(before,id='other'),expected='INVALID_REQUEST')

    def test_session_revision_exports_diffs_and_conflicts_preserve_history(self):
        d=self.document();s=dict(session_root=str(self.root/'sessions'),session_id='example')
        self.call('session.create',**s,request_id='create',document=d)
        self.call('session.apply',**s,request_id='hide',expected_revision=0,action=dict(type='edit',operations=[dict(op='properties',id='shape',visible=False)]))
        diff=self.call('session.diff',**s,from_revision=0,to_revision=1,compare_pixels=True)
        self.assertEqual(diff['rendered_pixels']['changed_pixels'],6)
        self.call('session.publish',**s,expected_revision=0,output=self.output(),expected='REVISION_CONFLICT')
        self.assertFalse((self.root/'result.png').exists())
        receipt=self.call('session.publish',**s,expected_revision=1,output=self.output())
        self.assertEqual(receipt['observed_current_revision'],1)
        self.assertEqual(png_pixels((self.root/'result.png').read_bytes())[2],bytes(8*6*4))
        self.call('session.apply',**s,request_id='undo',expected_revision=1,action=dict(type='undo'))
        self.assertFalse(self.call('session.diff',**s,from_revision=0,to_revision=2,compare_pixels=True)['changed'])
        self.call('session.diff',**s,from_revision=0,to_revision=3,expected='REVISION_NOT_FOUND')
        self.assertEqual(self.call('session.verify',**s)['requests'],3)


if __name__=='__main__':unittest.main()
