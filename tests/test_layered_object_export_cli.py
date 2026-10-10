"""Independent native-source delivery, placement and durable workflow contracts."""
import base64,copy,hashlib,json,tempfile,time,unittest
from pathlib import Path
import layered_fixtures as f
import layered_delivery_reader as reader
import layered_object_fixtures as incoming
import test_layered_cli as core
from test_mcp import Client

POLICY=dict(embedded_objects='native_reconstruction')
PIXELS=bytes([201,31,61,64,20,160,90,255,45,70,195,128,99,55,44,0,21,93,167,255,0,220,70,1])

class LayeredObjectExportTests(unittest.TestCase):
    invoke=core.LayeredTests.invoke
    document=core.LayeredTests.document
    read=core.LayeredTests.read
    pixels=core.LayeredTests.pixels
    def source(self):
        d=self.document(3,2);d['resolution_ppi']=123.456
        d['items']=[dict(id='pixels',name='Editable Δ 🎨',content=dict(type='raster',width=3,height=2,rgba_hex=PIXELS.hex()))]
        return d
    def object(self,source=None,**kw):
        obj=self.invoke(dict(command='object.import',snapshot=json.dumps(source or self.source())))['object']
        obj.update(kw);return obj
    def scene(self,**kw):
        d=self.document(12,10)
        d['items']=[dict(id='placed',name='Editable placement',transform=[1,0,0,1,2,1],content=dict(type='object',object=self.object(**kw)))]
        return d
    def export(self,d,expected=0,format='layered',**kw):
        return self.invoke(dict(command='document.export',document=d,format=format,**dict(dict(layered_options=POLICY),**kw)),expected)
    def load(self,b):return self.read(b,embedded_objects=incoming.POLICY)['document']
    def test_explicit_policy_and_format_validation_are_actionable(self):
        d=self.scene()
        for option in [None,{}]:
            err=self.export(d,1,layered_options=option);self.assertEqual(err['code'],'UNSUPPORTED_LAYERED_SEMANTICS');self.assertIn('native_reconstruction',err['message'])
        for format in ['snapshot','png','svg']:
            self.assertEqual(self.export(d,1,format=format)['code'],'INVALID_REQUEST')
        for options in [dict(embedded_objects='exact'),dict(embedded_objects='native_reconstruction',unknown=True)]:self.export(d,1,layered_options=options)
        plain=self.source();a=self.export(plain);b=self.export(plain,layered_options=None)
        self.assertEqual(a['data'],b['data']);self.assertEqual(a['layered']['embedded_objects'],[])
    def test_both_containers_keep_editable_source_separate_from_cache(self):
        d=self.scene();before=copy.deepcopy(d)
        for format in ['layered','layered_large']:
            artifact=self.export(d,format=format);raw=base64.b64decode(artifact['data'])
            parsed=f.parse(raw);layer=parsed['layers'][0];placement=reader.placement(layer['tags'][b'SoLd']);sources=reader.sources(parsed['global_tags'][b'lnk2'])
            self.assertEqual(len(sources),1);source=sources[0];nested=f.parse(source['data'])
            self.assertEqual(nested['version'],2);self.assertEqual(nested['layers'][0]['rgba'],PIXELS)
            self.assertEqual(nested['layers'][0]['name'],'Editable Δ 🎨');self.assertEqual(source['type'],b'8BPB')
            self.assertEqual(placement['Idnt'],source['id']);self.assertEqual(placement['Trnf'],[2,1,5,1,5,3,2,3])
            self.assertEqual(placement['Sz  ']['fields'],dict(Wdth=3,Hght=2));self.assertAlmostEqual(placement['Rslt'][1],123.456,delta=.5/65536)
            receipt=artifact['layered']['embedded_objects'][0];self.assertEqual(receipt['native_source_sha256'],hashlib.sha256(source['data']).hexdigest())
            self.assertEqual(receipt['source_snapshot_sha256'],d['items'][0]['content']['object']['sha256']);self.assertFalse(receipt['source_changed'])
            self.assertEqual(artifact['layered']['layers'][0]['kind'],'object');self.assertIn('receiving consumer',artifact['losses'][-1])
            self.assertNotEqual(layer['rgba'],PIXELS) # Source retains hidden RGB; cache has rendered transparency.
            reopened=self.load(raw);self.assertEqual(self.pixels(reopened),self.pixels(d))
            child=json.loads(reopened['items'][0]['content']['object']['snapshot']);self.assertEqual(child['items'][0]['content']['rgba_hex'],PIXELS.hex())
            self.assertEqual(self.export(d,format=format)['data'],artifact['data'])
        self.assertEqual(d,before)
    def test_affine_placements_resized_frames_parent_groups_and_controls(self):
        for matrix in [[2,0,0,2,1,1],[-1,0,0,1,6,2],[0,1,-1,0,6,2],[1,.5,.25,1,1.25,2.5]]:
            d=self.scene(width=6,height=4);d['items'][0].update(transform=matrix,opacity=128/255,fill_opacity=192/255,locked=True)
            artifact=self.export(d);raw=base64.b64decode(artifact['data']);p=f.parse(raw);placement=reader.placement(p['layers'][0]['tags'][b'SoLd'])
            a,b,c,e,x,y=matrix;expected=[v for sx,sy in [(0,0),(6,0),(6,4),(0,4)] for v in [a*sx+c*sy+x,b*sx+e*sy+y]]
            self.assertEqual(placement['Trnf'],expected);self.assertEqual(placement['Sz  ']['fields'],dict(Wdth=3,Hght=2))
            self.assertEqual(self.pixels(self.load(raw)),self.pixels(d))
        d=self.scene();d['items'][0]['parent']='folder';d['items'].insert(0,dict(id='folder',name='Parent',transform=[0,1,-1,0,8,1],content=dict(type='group',isolated=True)))
        raw=base64.b64decode(self.export(d)['data']);p=f.parse(raw);self.assertEqual(len(p['layers']),3)
        self.assertEqual(self.pixels(self.load(raw)),self.pixels(d))
    def test_duplicate_sources_have_distinct_native_ids_and_independent_edits(self):
        d=self.scene();duplicate=copy.deepcopy(d['items'][0]);duplicate.update(id='copy',transform=[1,0,0,1,6,3]);d['items'].append(duplicate)
        artifact=self.export(d);raw=base64.b64decode(artifact['data']);p=f.parse(raw);sources=reader.sources(p['global_tags'][b'lnk2'])
        self.assertEqual(len(set(s['id'] for s in sources)),2);self.assertEqual(sources[0]['data'],sources[1]['data'])
        self.assertEqual(len(set(reader.placement(l['tags'][b'SoLd'])['placed'] for l in p['layers'])),2)
        reopened=self.load(raw);self.assertEqual(self.pixels(reopened),self.pixels(d));before=copy.deepcopy(reopened['items'][1])
        source=json.loads(reopened['items'][0]['content']['object']['snapshot']);source['items'][0]['visible']=False
        reopened['items'][0]['content']['object']=self.object(source);self.assertEqual(reopened['items'][1],before)
        self.assertNotEqual(self.pixels(reopened),self.pixels(d))
    def test_linked_and_unlinked_authored_masks_roundtrip_without_cache_baking(self):
        for linked in [True,False]:
            d=self.scene();d['items'][0]['mask']=dict(width=3,height=2,gray_hex='0040ff80c020',linked=linked,transform=[1,0,0,1,0 if linked else 2,0 if linked else 1])
            raw=base64.b64decode(self.export(d)['data']);p=f.parse(raw);self.assertEqual(p['layers'][0]['mask_gray'].hex(),'0040ff80c020')
            source=reader.sources(p['global_tags'][b'lnk2'])[0];self.assertEqual(f.parse(source['data'])['layers'][0]['rgba'],PIXELS)
            reopened=self.load(raw);self.assertEqual(self.pixels(reopened),self.pixels(d));self.assertEqual(reopened['items'][0]['mask']['linked'],linked)
    def test_nested_sources_and_explicit_sampling_losses(self):
        source=self.source()
        for depth in range(1,5):
            obj=self.object(source);source=self.document(3,2);source['items']=[dict(id='nested',content=dict(type='object',object=obj))]
            raw=base64.b64decode(self.export(source)['data']);self.assertEqual(self.pixels(self.load(raw)),self.pixels(source))
        d=self.scene(sampling='bicubic',surface_scale=2);a=self.export(d);receipt=a['layered']['embedded_objects'][0]
        self.assertEqual(receipt['source_sampling'],'bicubic');self.assertEqual(receipt['source_surface_scale'],2)
        self.assertIn('surface-scale',a['losses'][-1]);self.assertEqual(reader.placement(f.parse(base64.b64decode(a['data']))['layers'][0]['tags'][b'SoLd'])['Sz  ']['fields'],dict(Wdth=3,Hght=2))
    def test_unsupported_sources_controls_limits_and_cancellation_fail_before_publication(self):
        for changed in [dict(blend='multiply'),dict(opacity=.5)]:
            d=self.scene();d['items'][0].update(changed);self.assertEqual(self.export(d,1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        source=self.source();source['items'][0]['transform']=[2,0,0,2,0,0]
        d=self.scene();d['items'][0]['content']['object']=self.object(source);self.assertEqual(self.export(d,1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        d=self.scene();d['items'][0]['transform']=[110,0,0,110,0,0];self.assertEqual(self.export(d,1)['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.export(self.scene(),1,control=dict(timeout_ms=0))['code'],'TIMEOUT')
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'failed.psd';r=self.invoke(dict(command='document.preflight',document=d,output=dict(output_root=root,file_name=path.name,format='layered',layered_options=POLICY)))
            self.assertFalse(r['ready']);self.assertFalse(path.exists())
    def test_mcp_session_preflight_job_restart_retry_undo_and_create_only_outputs(self):
        d=self.scene();before=copy.deepcopy(d)
        with tempfile.TemporaryDirectory() as root:
            s=dict(session_root=root,session_id='delivery');output=dict(output_root=root,file_name='editable.psd',format='layered',layered_options=POLICY)
            c=Client();c.initialize()
            try:
                c.success('session.create',**s,request_id='create',document=d)
                prepared=c.success('document.preflight',document=d,output=output);self.assertTrue(prepared['ready']);self.assertFalse((Path(root)/'editable.psd').exists())
                published=c.success('session.publish',**s,expected_revision=0,output=output)
                raw=(Path(root)/'editable.psd').read_bytes();self.assertEqual(published['sha256'],hashlib.sha256(raw).hexdigest())
                self.assertEqual(c.tool('session.publish',**s,expected_revision=0,output=output)['structuredContent']['error']['code'],'OUTPUT_EXISTS')
                edit=dict(request_id='hide',expected_revision=0,action=dict(type='edit',operations=[dict(op='properties',id='placed',visible=False)]))
                c.success('session.apply',**s,**edit)
                c.success('session.apply',**s,request_id='undo',expected_revision=1,action=dict(type='undo'))
                job=dict(job_root=str(Path(root)/'jobs'),request_id='native',document=d,output=dict(output,file_name='background.psd'))
                c.success('job.start',**job)
            finally:c.close()
            c=Client();c.initialize()
            try:
                self.assertTrue(c.success('session.apply',**s,**edit)['replayed']);self.assertTrue(c.success('session.verify',**s)['valid'])
                deadline=time.monotonic()+20
                while True:
                    state=c.success('job.wait',job_root=str(Path(root)/'jobs'),request_id='native',wait_ms=1000)
                    if state['state'] not in ['queued','running']:break
                    self.assertLess(time.monotonic(),deadline)
                self.assertEqual(state['state'],'completed',state);result=c.success('job.result',job_root=str(Path(root)/'jobs'),request_id='native')
                self.assertEqual((Path(root)/'background.psd').read_bytes(),raw);self.assertEqual(result['sha256'],published['sha256'])
                self.assertTrue(c.success('job.start',**job)['replayed'])
                self.assertEqual((Path(root)/'editable.psd').read_bytes(),raw)
            finally:c.close()
        self.assertEqual(d,before)

    def test_nested_metadata_links_and_aggregate_budgets_are_not_silently_converted(self):
        for scope in ['document','item']:
            source=self.source()
            if scope=='document':source['metadata']=dict(title='Retained source note')
            else:source['items'][0]['metadata']=dict(note='Retained item note')
            d=self.scene();d['items'][0]['content']['object']=self.object(source)
            error=self.export(d,1,metadata_policy=dict(mode='strip'))
            self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS');self.assertIn('copy',error['message'])
        d=self.scene(link=dict(key='original.json'));self.assertEqual(self.export(d,1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        d=self.scene();d['items'][0]['transform']=[100,0,0,100,0,0]
        second=copy.deepcopy(d['items'][0]);second['id']='copy';d['items'].append(second)
        self.assertEqual(self.export(d,1)['code'],'RESOURCE_LIMIT') # Two individually bounded caches exceed the document total.
        source=self.source();source.update(width=1024,height=1024)
        d=self.document(1024,1024);d['items']=[dict(id='wide',content=dict(type='object',object=self.object(source,width=3,height=2)))]
        self.assertEqual(self.export(d,1)['code'],'RESOURCE_LIMIT') # Aggregate source plus outer canvases.

if __name__=='__main__':unittest.main()
