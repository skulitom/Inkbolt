"""Original byte fixtures, independent layer framing and source-preserving workflows."""
import base64,copy,hashlib,json,tempfile,unittest
from pathlib import Path
import test_editing_cli as editing
from test_profiles_cli import linear_profile,embedded,builtin
from test_mcp import Client
import layered_fixtures as f

class LayeredTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def document(self,w=8,h=6):return self.invoke(dict(command='document.create',id='layered',kind='raster',width=w,height=h))
    def export(self,d,expected=0,**kw):return self.invoke(dict(command='document.export',document=d,format='layered',**kw),expected)
    def read(self,data,expected=0,**kw):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'original.psd';p.write_bytes(data);before=hashlib.sha256(data).hexdigest();r=self.invoke(dict(command='layered.import',source_path=str(p),id='imported',**kw),expected);self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),before);return r
    def pixels(self,d):return self.invoke(dict(command='document.render',document=d))['data']
    def scene(self):
        d=self.document();d['items']=[dict(id='bottom',name='duplicate',content=dict(type='raster',width=8,height=6,rgba_hex='285078ff'*48)),dict(id='top',name='Δ icon 🎨',opacity=128/255,fill_opacity=192/255,transform=[1,0,0,1,-1,2],content=dict(type='raster',width=3,height=2,rgba_hex='c0204080'+'11ee9900'+'70a010ff'+'10203040'+'807060ff'+'9a8b7c55')),dict(id='hidden',name='duplicate',visible=False,locked=True,transform=[1,0,0,1,6,-2],content=dict(type='raster',width=2,height=2,rgba_hex='ff0000ff'*4))];return self.invoke(dict(command='document.validate',document=d))

    def test_export_independent_planes_names_order_profiles_and_exact_pixels(self):
        d=self.scene();before=copy.deepcopy(d);artifact=self.export(d);raw=base64.b64decode(artifact['data']);external=f.parse(raw)
        self.assertEqual([l['name'] for l in external['layers']],['duplicate','Δ icon 🎨','duplicate']);self.assertEqual(external['layers'][2]['bounds'],[-2,6,0,8]);self.assertFalse(external['layers'][2]['visible'])
        for l,item in zip(external['layers'],d['items']):self.assertEqual(l['rgba'].hex(),item['content']['rgba_hex'])
        self.assertEqual(hashlib.sha256(external['resources'][1039]).hexdigest(),artifact['layered']['profile_sha256']);self.assertEqual(external['layers'][1]['opacity'],128)
        reopened=self.read(raw)['document'];self.assertEqual(self.pixels(reopened),self.pixels(d));self.assertEqual([i['name'] for i in reopened['items']],[i['name'] for i in d['items']]);self.assertEqual(d,before);self.assertEqual(self.export(d)['data'],artifact['data'])

    def test_original_raw_rle_zip_and_predictor_inputs_are_identical_and_ignore_cache(self):
        layers=[dict(name='upper',width=3,height=2,xy=(-1,2),rgba=bytes([21,72,193,128])*6,opacity=153),dict(name='lower',width=8,height=6,rgba=bytes([200,100,50,255])*48)]
        outputs=[]
        for compression in range(4):
            raw=f.make(list(reversed(layers)),compression=compression);r=self.read(raw,color_policy='assume_srgb');self.assertFalse(r['merged_cache']['used_for_editable_reconstruction']);d=r['document'];self.assertEqual(d['items'][0]['name'],'lower');self.assertEqual(d['items'][1]['content']['rgba_hex'],layers[0]['rgba'].hex());outputs.append(self.pixels(d))
        self.assertTrue(all(p==outputs[0] for p in outputs));self.assertNotEqual(outputs[0],'00000000'*48)

    def test_repeated_literal_boundaries_odd_rows_hidden_rgb_and_resolution(self):
        for width in [1,2,3,127,128,129,257]:
            d=self.document(width,2);p=bytes([v%256 for i in range(width*2) for v in [i,23 if i%3 else 24,(i*71)%256,0 if i%2 else 255]])
            d['resolution_ppi']=123.456;d['items']=[dict(id='p',content=dict(type='raster',width=width,height=2,rgba_hex=p.hex()))];raw=base64.b64decode(self.export(d)['data']);self.assertEqual(f.parse(raw)['layers'][0]['rgba'],p);d2=self.read(raw)['document'];self.assertEqual(d2['items'][0]['content']['rgba_hex'],p.hex());self.assertAlmostEqual(d2['resolution_ppi'],123.456,delta=.5/65536)

    def test_untagged_profile_conversion_conflicts_and_hash_are_explicit(self):
        layer=dict(name='pixels',width=1,height=1,rgba=[64,128,192,0]);raw=f.make([layer]);self.assertEqual(self.read(raw,1)['code'],'COLOR_POLICY_REQUIRED');self.assertEqual(self.read(raw,1,color_policy='assume_srgb',expected_sha256='0'*64)['code'],'SOURCE_MISMATCH')
        tagged=f.make([layer],profile=linear_profile());self.assertEqual(self.read(tagged,1,color_policy='assume_srgb')['code'],'COLOR_POLICY_REQUIRED');r=self.read(tagged,color_policy='convert_srgb');self.assertEqual(r['interpretation'],'converted_srgb_per_layer');self.assertEqual(r['document']['items'][0]['content']['rgba_hex'][-2:],'00');self.assertNotEqual(r['document']['items'][0]['content']['rgba_hex'],'4080c000');self.assertEqual(r['source_profile_sha256'],hashlib.sha256(linear_profile()).hexdigest())

    def test_unsupported_editable_semantics_fail_before_returning_a_document(self):
        basic=dict(name='pixel',width=1,height=1,rgba=[0,0,0,255])
        for change in [dict(blend=b'mul '),dict(mask=bytes(17)+b'\4\0\0'),dict(clipping=1),dict(extra=f.tag(b'TySh',bytes(10))),dict(extra=f.tag(b'lsct',f.U32(1))),dict(extra=f.tag(b'lspf',f.U32(1))),dict(extra=f.tag(b'knko',b'\1\0\0\0'))]:
            with self.subTest(change=change):self.assertEqual(self.read(f.make([dict(basic,**change)]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        d=self.scene()
        for change in [dict(opacity=.5),dict(transform=[1,0,0,1,.5,0]),dict(mask=dict(width=3,height=2,gray_hex='ff'*6,feather=1)),dict(blend='multiply')]:
            bad=copy.deepcopy(d);bad['items'][1].update(change);self.assertEqual(self.export(bad,1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')

    def test_truncation_lengths_duplicate_ids_and_decompression_overflow_rejected(self):
        basic=dict(name='pixels',width=3,height=2,rgba=[1,2,3,4]*6);raw=f.make([basic],compression=3)
        for cut in [0,1,5,13,25,30,60,len(raw)-1]:self.assertIn(self.read(raw[:cut],1,color_policy='assume_srgb')['code'],['INVALID_LAYERED_FILE','UNSUPPORTED_LAYERED_SEMANTICS'])
        self.assertEqual(self.read(f.make([dict(basic,id=1),dict(basic,id=1)]),1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')
        self.assertEqual(self.read(raw+b'extra',1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')
        bomb=bytearray(raw);bomb[30:34]=f.U32(0xffffffff);self.assertEqual(self.read(bomb,1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')

    def test_publication_import_verification_and_cancellation_preserve_sources(self):
        c=Client();self.addCleanup(c.close);c.initialize();d=self.scene()
        with tempfile.TemporaryDirectory() as root:
            s=dict(session_root=root,session_id='layered');c.success('session.create',**s,request_id='create',document=d)
            output=dict(output_root=root,file_name='scene.psd',format='layered');r=c.success('session.publish',**s,expected_revision=0,output=output);path=Path(root)/'scene.psd';before=path.read_bytes();self.assertEqual(r['sha256'],hashlib.sha256(before).hexdigest())
            result=c.success('layered.import',source_path=str(path),id='reopened',expected_sha256=r['sha256']);self.assertEqual(self.pixels(result['document']),self.pixels(d));self.assertTrue(c.success('session.verify',**s)['valid'])
            self.assertEqual(self.invoke(dict(command='layered.import',source_path=str(path),id='cancelled',control=dict(timeout_ms=0)),1)['code'],'TIMEOUT');self.assertEqual(path.read_bytes(),before)
            self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=output),1)['code'],'OUTPUT_EXISTS')

    def test_independent_plane_compositing_confirms_stack_and_white_matted_cache(self):
        from fractions import Fraction as F
        d=self.scene();d['items']=d['items'][1:];d['items'][1]['visible']=True
        artifact=self.export(d);parsed=f.parse(base64.b64decode(artifact['data']));expected=[]
        for y in range(d['height']):
            for x in range(d['width']):
                color=[F(0)]*3;alpha=F(0)
                for layer in parsed['layers']:
                    top,left,bottom,right=layer['bounds']
                    if not layer['visible'] or not (left<=x<right and top<=y<bottom):continue
                    at=((y-top)*(right-left)+x-left)*4;p=layer['rgba'][at:at+4]
                    a=F(p[3]*layer['opacity']*layer['tags'][b'iOpa'][0],255**3)
                    color=[F(p[c],255)*a+color[c]*(1-a) for c in range(3)];alpha=a+alpha*(1-a)
                expected.extend([round(v/alpha*255) if alpha else 0 for v in color]+[round(alpha*255)])
        actual=bytes.fromhex(self.pixels(d));self.assertTrue(all(abs(a-b)<=1 for a,b in zip(actual,expected)))
        n=d['width']*d['height'];cache=parsed['merged']
        for i in range(n):
            a=actual[4*i+3];self.assertEqual(cache[3*n+i],a)
            for c in range(3):self.assertEqual(cache[c*n+i],(actual[4*i+c]*a+255*(255-a)+127)//255)
        self.assertEqual(artifact['layered']['order'],'bottom_to_top');self.assertEqual(hashlib.sha256(cache).hexdigest(),artifact['layered']['merged_planes_sha256'])

    def test_aligned_layer_records_and_terminated_unicode_names(self):
        for width in [1,2,3,4,5]:
            layer=dict(name='abcd',width=width,height=1,rgba=[10,20,30,255]*width,name_padding=2)
            raw=f.make([layer],compression=1,info_alignment=4);d=self.read(raw,color_policy='assume_srgb')['document'];self.assertEqual(d['items'][0]['content']['rgba_hex'],bytes(layer['rgba']).hex())

    def test_channel_decompression_bombs_incomplete_packets_and_extra_streams_fail(self):
        import zlib
        basic=dict(name='p',width=1,height=1,rgba=[1,2,3,255]);good=f.plane(bytes([30]),1,0)
        bad=[f.U16(0),f.U16(0)+bytes([1,2]),f.U16(1)+f.U16(2)+bytes([255,7]),f.U16(1)+f.U16(1)+bytes([0]),f.U16(1)+f.U16(1)+bytes([128]),f.U16(2)+zlib.compress(bytes(1000000)),f.U16(2)+zlib.compress(b'x')+zlib.compress(b'y'),f.U16(3)+zlib.compress(b'xx'),f.U16(2)+zlib.compress(b'x')[:-1]]
        for plane in bad:
            with self.subTest(plane=plane[:8]):self.assertEqual(self.read(f.make([dict(basic,channel_data=[plane,good,good,good])]),1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')
        # A legal no-op packet neither consumes pixels nor changes the following literal.
        legal=f.U16(1)+f.U16(3)+bytes([128,0,255]);d=self.read(f.make([dict(basic,channel_data=[legal,good,good,good])]),color_policy='assume_srgb')['document'];self.assertEqual(d['items'][0]['content']['rgba_hex'],'1e1e1eff')

    def test_dimension_bounds_modes_unknown_records_and_publication_policies(self):
        basic=dict(name='p',width=1,height=1,rgba=[1,2,3,255]);raw=f.make([basic])
        for offset,value in [(4,f.U16(3)),(22,f.U16(16)),(24,f.U16(4))]:
            b=bytearray(raw);b[offset:offset+2]=value;self.assertEqual(self.read(b,1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for extra in [f.tag(b'shmd',f.U32(1)+b'8BIManim'),f.tag(b'zzzz',b'')]:self.assertEqual(self.read(f.make([dict(basic,extra=extra)]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        self.assertEqual(self.read(f.make([basic],extra_resources=f.resource(2999,b'')),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        self.assertEqual(self.read(f.make([basic],w=30000,h=30000,merged=b''),1,color_policy='assume_srgb')['code'],'RESOURCE_LIMIT')
        d=self.scene();d['items'][1]['transform'][4]=32768;self.assertEqual(self.export(d,1)['code'],'RESOURCE_LIMIT')
        d=self.scene();d['metadata']=dict(title='Private fixture title',private=dict(note='hidden text'))
        self.assertEqual(self.export(d,1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        a=self.export(d,metadata_policy=dict(mode='strip'));self.assertNotIn(b'Private fixture title',base64.b64decode(a['data']));self.assertNotIn(b'hidden text',base64.b64decode(a['data']))
        self.assertEqual(self.export(self.scene(),1,scale=2)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')

    def test_agent_restart_edit_undo_redo_retry_and_native_reopening(self):
        source=f.make([dict(name='original',width=2,height=2,rgba=[20,80,160,255]*4)])
        with tempfile.TemporaryDirectory() as root:
            source_path=Path(root)/'input.psd';source_path.write_bytes(source);session=dict(session_root=root,session_id='roundtrip')
            c=Client();c.initialize()
            try:
                original=c.success('layered.import',source_path=str(source_path),id='native',color_policy='assume_srgb')['document'];c.success('session.create',**session,request_id='create',document=original)
                edit=dict(expected_revision=0,request_id='edit',action=dict(type='edit',operations=[dict(op='properties',id=original['items'][0]['id'],name='edited',visible=False)]));first=c.success('session.apply',**session,**edit)
            finally:c.close()
            c=Client();c.initialize()
            try:
                replay=c.success('session.apply',**session,**edit);self.assertTrue(replay['replayed']);self.assertEqual(replay['receipt'],first['receipt'])
                undo=c.success('session.apply',**session,expected_revision=1,request_id='undo',action=dict(type='undo'))['document'];self.assertEqual(self.pixels(undo),self.pixels(original))
                redo=c.success('session.apply',**session,expected_revision=2,request_id='redo',action=dict(type='redo'))['document'];self.assertFalse(redo['items'][0]['visible'])
                c.success('session.publish',**session,expected_revision=3,output=dict(output_root=root,file_name='edited.psd',format='layered'))
                reopened=c.success('layered.import',source_path=str(Path(root)/'edited.psd'),id='reopened')['document'];self.assertEqual(reopened['items'][0]['name'],'edited');self.assertFalse(reopened['items'][0]['visible']);self.assertEqual(reopened['items'][0]['content'],original['items'][0]['content']);self.assertTrue(c.success('session.verify',**session)['valid'])
                cancel=Path(root)/'cancel';cancel.touch();error=c.tool('layered.import',source_path=str(source_path),id='cancel',color_policy='assume_srgb',control=dict(cancel_file=str(cancel)));self.assertEqual(error['structuredContent']['error']['code'],'CANCELLED')
            finally:c.close()
            self.assertEqual(source_path.read_bytes(),source)

if __name__=='__main__':unittest.main()

