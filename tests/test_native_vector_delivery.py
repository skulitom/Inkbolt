"""Original editable delivery: independent controls, pixels, framing and safe publication."""
import copy
import base64
import hashlib
import re
import uuid
from contextlib import closing
import unittest

import native_vector_fixture as fixture
import test_native_vector_import as native
import test_agent_workspace as workspace
import test_jobs as jobs
from test_mcp import Client
from platform_support import requires_capability
from test_editing_cli import png_pixels


class NativeVectorDelivery(unittest.TestCase):
    setUp = native.NativeVectorImport.setUp
    invoke = native.NativeVectorImport.invoke
    read = native.NativeVectorImport.read
    pixels = native.NativeVectorImport.pixels
    exports = native.NativeVectorImport.exports
    edit = native.NativeVectorImport.edit
    cli = workspace.AgentWorkspaceTests.cli
    ledger = jobs.JobTests.ledger
    stop_owned = jobs.JobTests.stop_owned
    finish = jobs.JobTests.finish
    idle = jobs.JobTests.idle

    def document(self, **kw):
        return self.read(fixture.source(data=fixture.artwork(**kw)))['document']

    def export(self, document, expected=0, **kw):
        before = copy.deepcopy(document)
        result = self.invoke(dict(command='document.export',document=document,
                                  format='native_vector',**kw),expected)
        self.assertEqual(document,before)
        return result

    def test_original_layer_path_artboard_acceptance_exact_pixels_and_editable_reopen(self):
        # Fixed original acceptance geometry: two named layers, one artboard,
        # blue full-page path and an opaque red rectangular patch.
        d=dict(schema_version=2,id='basic-reference',kind='vector',width=128,height=96,
               resolution_ppi=72,color_space='srgb',items=[
            dict(id='page',name='Artboard 1',content=dict(type='frame',frame=dict(role='artboard',scope='scene',width=128,height=96))),
            dict(id='base',name='base',content=dict(type='group',role='layer')),
            dict(id='base-fill',name='base-fill',parent='base',content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=128,height=96),fill=[0,0,255,255])),
            dict(id='top',name='top',content=dict(type='group',role='layer')),
            dict(id='patch',name='patch',parent='top',content=dict(type='vector',geometry=dict(shape='rect',x=8,y=8,width=32,height=24),fill=[255,0,0,255]))])
        before=copy.deepcopy(d)
        output=dict(output_root=str(self.root),file_name='basic.vector',format='native_vector')
        receipt=self.invoke(dict(command='document.publish',document=d,output=output))
        data=(self.root/'basic.vector').read_bytes()
        out=self.read(data)['document']
        self.assertEqual(receipt['sha256'],hashlib.sha256(data).hexdigest())
        self.assertEqual([i['name'] for i in out['items']],['Artboard 1','base','base-fill','top','patch'])
        self.assertEqual(out['items'][-1]['parent'],out['items'][-2]['id'])
        self.assertEqual(out['items'][-1]['content']['geometry']['commands'],[
            dict(verb='move',to=[8,-8]),dict(verb='line',to=[40,-8]),
            dict(verb='line',to=[40,-32]),dict(verb='line',to=[8,-32]),dict(verb='close')])
        expected=bytes(channel for y in range(96) for x in range(128)
                       for channel in ([255,0,0,255] if 8<=x<40 and 8<=y<32 else [0,0,255,255]))
        for document in [d,out]:
            image=self.exports(document)['artifacts'][0]['artifact']
            self.assertEqual(png_pixels(base64.b64decode(image['data']))[:3],(128,96,expected))
        edited=self.edit(out,[dict(op='properties',id=out['items'][-1]['id'],visible=False)])
        image=self.exports(edited)['artifacts'][0]['artifact']
        self.assertEqual(png_pixels(base64.b64decode(image['data']))[:3],(128,96,bytes([0,0,255,255])*128*96))
        self.assertEqual(d,before)
        self.assertEqual((self.root/'basic.vector').read_bytes(),data)

    def test_independent_encoded_geometry_and_exact_integer_board_pixels(self):
        d = self.document()
        result = self.export(d)
        data = result['data'].encode('ascii')
        self.assertTrue(data.startswith(b'%!PS-Inkbolt-1.0\n'))
        self.assertIn(b'%%BeginProlog\n%%EndProlog',data)
        self.assertNotIn(b'%PDF',data)
        self.assertNotIn(b'schema_version',data)
        self.assertIn(b'2 -2 m\n8 -2 L\n8 -6 L\n2 -6 L\n2 -2 L\nf',data)
        self.assertIn(b'%_0 0 /RealPointRelToROrigin (PositionPoint1) ,',data)
        self.assertIn(b'%_24 -8 /RealPointRelToROrigin (PositionPoint2) ,',data)
        identities = re.findall(rb'\(([0-9a-f-]+)\) /String \(ArtboardUUID\)',data)
        self.assertEqual(len(set(identities)),2)
        for value in identities:
            self.assertEqual(uuid.UUID(value.decode()).version,8)
        self.assertEqual(result['native_vector']['sha256'],hashlib.sha256(data).hexdigest())
        self.assertEqual(result['native_vector']['counts'],dict(artboards=2,layers=2,paths=3))
        imported = self.read(data)
        self.assertEqual(imported['source']['transport'],'editable_text')
        self.assertIsNone(imported['source']['container_version'])
        self.pixels(imported['document'])
        self.assertEqual(self.export(d)['data'],result['data'])

    def test_cubic_controls_flags_and_opacity_survive_delivery(self):
        for kw in [dict(curve=True,locked=True,board_locked=True),dict(visible=False),
                   dict(layer_visible=False),dict(layer_locked=True),dict(opacity=.5)]:
            with self.subTest(kw=kw):
                d = self.document(**kw)
                native = self.export(d)['data'].encode()
                if kw.get('curve'):
                    self.assertIn(b'4 -1 6 -1 8 -2 C',native)
                out = self.read(native)['document']
                original = {i['name']:i for i in d['items']}
                for item in out['items']:
                    for field,default in [('visible',True),('locked',False),('opacity',1)]:
                        self.assertEqual(item.get(field,default),original[item['name']].get(field,default))
                if not kw.get('curve'):
                    self.pixels(out,visible=kw.get('visible',True) and kw.get('layer_visible',True),opacity=kw.get('opacity',1))

    def test_physical_units_affine_placement_and_fractional_controls(self):
        d = self.document(curve=True)
        d['resolution_ppi'] = 144
        path = next(i for i in d['items'] if i['name']=='overlay')
        path['transform'] = [1,.25,.5,1,.125,-.25]
        result = self.export(d)
        self.assertEqual(result['native_vector']['document_to_native'],[.5,0,0,-.5,0,0])
        # Independent composition: local x'=x+.5*y+.125, y'=.25*x+y-.25;
        # parent x''=x'+4,y''=12-y'; delivery x=x''/2,y=-y''/2.
        self.assertIn('3.5625 -1.375 m',result['data'])
        self.assertIn('4.8125 -0.625 5.8125 -0.375 6.5625 -0.625 C',result['data'])
        out = self.read(result['data'].encode())['document']
        self.assertEqual(out['resolution_ppi'],72)
        self.assertEqual(out['vector_canvas']['size_px'],[12,4])

    def test_rectangles_polygons_empty_layer_refusal_and_implicit_canvas(self):
        d = self.document()
        d['items'] = [i for i in d['items'] if i['content']['type']!='frame']
        p = next(i for i in d['items'] if i['name']=='underlay')
        p['content']['geometry'] = dict(shape='rect',x=-4,y=4,width=12,height=8)
        p = next(i for i in d['items'] if i['name']=='detail-fill')
        p['content']['geometry'] = dict(shape='polygon',points=[[14,9],[18,9],[18,6],[14,6]])
        d['items'].append(dict(id='empty',name='Empty (layer) \\',content=dict(type='group',role='layer')))
        self.assertEqual(self.export(d,1)['code'],'UNSUPPORTED')
        d['items'].pop()
        next(i for i in d['items'] if i['name']=='Top')['name']='Top (layer) \\'
        result = self.export(d)
        self.assertTrue(result['native_vector']['implicit_canvas_artboard'])
        out = self.read(result['data'].encode())['document']
        self.assertEqual([i['name'] for i in out['items'] if i['content']['type']=='group'],['Base','Top (layer) \\'])
        self.assertEqual(out['vector_canvas']['size_px'],[24,8])

    def test_unsupported_appearance_geometry_names_and_state_fail_explicitly(self):
        d = self.document()
        for key,value in [('blend','multiply'),('fill_opacity',.5),('name',''),('name','caf\u00e9')]:
            changed=copy.deepcopy(d); changed['items'][-1][key]=value
            self.assertEqual(self.export(changed,1)['code'],'UNSUPPORTED')
        for mutate in [lambda p:p['content'].update(fill=[1,2,3,128]),
                       lambda p:p['content'].update(fill_rule='even_odd'),
                       lambda p:p.update(parent=None),
                       lambda p:p['content'].update(geometry=dict(shape='ellipse',cx=0,cy=0,rx=1,ry=1)),
                       lambda p:p['content']['geometry']['commands'].pop()]:
            changed=copy.deepcopy(d); mutate(changed['items'][-1])
            self.assertEqual(self.export(changed,1)['code'],'UNSUPPORTED')
        for key,value in [('color_space','linear_srgb'),('kind','raster')]:
            changed=copy.deepcopy(d); changed[key]=value
            self.assertIn(self.export(changed,1)['code'],['UNSUPPORTED','INVALID_DOCUMENT','INVALID_CANVAS'])
        self.assertEqual(self.export(d,1,scale=2)['code'],'UNSUPPORTED')
        changed=copy.deepcopy(d); changed['items'][-1]['transform']=[1,0,0,1,20000,0]
        self.assertEqual(self.export(changed,1)['code'],'RESOURCE_LIMIT')

    def test_metadata_requires_explicit_strip_and_is_not_hidden_in_delivery(self):
        d=self.document(); d['metadata']=dict(title='secret-title')
        d['items'][-1]['metadata']=dict(note='secret-note')
        self.assertEqual(self.export(d,1)['code'],'UNSUPPORTED')
        result=self.export(d,metadata_policy=dict(mode='strip'))
        self.assertNotIn('secret',result['data'])
        self.assertEqual(d['metadata']['title'],'secret-title')

    def test_native_identity_name_encoding_is_distinct_from_layer_display_strings(self):
        pairs=[('alpha beta','alpha_beta'),('alpha_beta','alpha_x5F_beta'),('1 starts','_x31__starts'),
               ('a:b/c&d<e>','a:b_x2F_c_x26_d_x3C_e_x3E_'),('literal_x41_tail','literal_x5F_x41_x5F_tail'),
               ('curve (one) \\ name','curve__x28_one_x29___x5C__name')]
        for name,encoded in pairs:
            d=self.document();d['items'][-1]['name']=name
            result=self.export(d)
            self.assertIn(f'({encoded}) ; (AI10_ArtUID)',result['data'])
            out=self.read(result['data'].encode())['document']
            self.assertEqual(out['items'][-1]['name'],name)
        d=self.document();d['items'][-1]['name']=' x41 '
        self.assertEqual(self.export(d,1)['code'],'UNSUPPORTED')
        for value in [b'_x20_',b'_xE9_',b'_x20AC_']:
            self.assertEqual(self.read(fixture.artwork().replace(b'(overlay)',b'('+value+b')'),1)['code'],'UNSUPPORTED')
        data=fixture.artwork().replace(b'(Base) Ln',b'(Base\\(Layer\\)\\040Name) Ln\n%_/ArtDictionary : /XMLUID : (distinct-data-identity) ; (AI10_ArtUID) , ;')
        out=self.read(data)['document']
        self.assertEqual(next(i['name'] for i in out['items'] if i['id']=='layer-0'),'Base(Layer) Name')

    def test_typed_document_scope_uuid_and_raw_version_failures(self):
        data=fixture.artwork()
        for old,new in [(b'%AI9_BeginDocumentData',b'%AI9_BeginOtherData'),
                         (b'/Recorded ,',b'/Other ,'),(b'%%AI8_CreatorVersion: 30.0.0',b'%%AI8_CreatorVersion: 29.0.0'),
                         (b'%AI5_FileFormat 14.0',b'%AI5_FileFormat 15.0')]:
            self.assertIn(old,data)
            self.read(data.replace(old,new),1)
        ids=re.findall(rb'\(([0-9a-f-]+)\) /String \(ArtboardUUID\)',data)
        for broken in [data.replace(ids[0],b'bad-id'),data.replace(ids[1],ids[0]),
                       data.replace(b'%AI9_EndDocumentData',b'%AI9_EndDocumentData\n%AI9_EndDocumentData')]:
            self.assertEqual(self.read(broken,1)['code'],'INVALID_VECTOR_SOURCE')

    def test_single_native_block_without_count_and_ambiguous_extra_block(self):
        for compressed in [False,True]:
            objects=fixture.objects(compressed=compressed)
            objects[5]=objects[5].replace(b'/NumBlock 1',b'')
            self.pixels(self.read(fixture.pdf(objects))['document'])
            objects[5]=objects[5].replace(b'/AIPrivateData1',b'/AIPrivateData2 7 0 R /AIPrivateData1')
            self.assertEqual(self.read(fixture.pdf(objects),1)['code'],'UNSUPPORTED')

    def test_create_only_publication_and_mcp_agree_without_source_edits(self):
        d=self.document()
        args=dict(command='document.publish',document=d,output=dict(output_root=str(self.root),file_name='delivery.vector',format='native_vector'))
        result=self.invoke(args)
        data=(self.root/'delivery.vector').read_bytes()
        self.assertEqual(result['sha256'],hashlib.sha256(data).hexdigest())
        self.assertEqual(data,self.export(d)['data'].encode())
        self.assertEqual(self.invoke(args,1)['code'],'OUTPUT_EXISTS')
        self.assertEqual((self.root/'delivery.vector').read_bytes(),data)
        with closing(Client(('--tools','core'),workspace=self.root)) as client:
            client.initialize()
            r=client.tool('run',command='document.export',arguments=dict(document=d,format='native_vector'))
            self.assertFalse(r['isError'],r)
            self.assertEqual(r['structuredContent']['result']['data'],data.decode())
            cap=client.tool('run',command='capabilities',arguments={})['structuredContent']['result']
            self.assertIn('native_vector',cap['publication']['formats'])
            self.assertIn('native_vector_editable_subset',cap['supported']['exports'])
            self.assertNotIn('native_vector_editable_subset',cap['supported']['raster'])
        args['output'].update(file_name='one.vector',artboard_id='board-0')
        self.assertEqual(self.invoke(args,1)['code'],'UNSUPPORTED')
        self.assertFalse((self.root/'one.vector').exists())

    def test_saved_revision_receipt_recovery_preserves_bytes_without_job(self):
        self.delivery_workflow(False)

    @requires_capability('jobs')
    def test_saved_revision_receipt_recovery_and_background_job_preserve_bytes(self):
        self.delivery_workflow(True)

    def delivery_workflow(self, with_job):
        if with_job: self.addCleanup(self.stop_owned)
        d=self.document()
        self.cli('session.create',session_id='work',request_id='create',document=d)
        original=dict(session_id='work',revision=0)
        args=dict(document=original,output=dict(file_name='saved.vector',format='native_vector'),receipt=dict(request_id='saved'))
        published=self.cli('document.publish',**args)
        before=(self.root/'saved.vector').read_bytes()
        edit=self.cli('session.apply',session_id='work',request_id='hide',expected_revision=0,
                      action=dict(type='edit',operations=[dict(op='properties',id='path-2',visible=False)]))
        self.assertEqual(edit['document']['revision'],1)
        self.assertTrue(self.cli('document.publish',**args)['publication']['replayed'])
        self.assertEqual(self.cli('publication.receipt',request_id='saved')['result']['sha256'],published['sha256'])
        self.assertEqual((self.root/'saved.vector').read_bytes(),before)
        if with_job:
            job=dict(request_id='native-job',document=original,output=dict(file_name='background.vector',format='native_vector'))
            self.cli('job.start',**job)
            self.finish('native-job'); self.idle()
            self.assertEqual((self.root/'background.vector').read_bytes(),before)
            self.assertTrue(self.cli('job.start',**job)['replayed'])
            self.assertEqual(self.cli('job.result',request_id='native-job')['sha256'],published['sha256'])


if __name__=='__main__': unittest.main()
