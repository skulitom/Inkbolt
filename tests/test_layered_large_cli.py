"""Large-container framing, independent plane decoding and durable publication."""
import base64,hashlib,tempfile,unittest
from pathlib import Path
import layered_fixtures as f
import test_layered_cli as core
import test_layered_metadata_cli as metadata
from test_mcp import Client

class LargeLayeredTests(unittest.TestCase):
    invoke=core.LayeredTests.invoke
    read=core.LayeredTests.read
    pixels=core.LayeredTests.pixels
    scene=core.LayeredTests.scene
    document=core.LayeredTests.document
    def export(self,d,expected=0,**kw):return self.invoke(dict(command='document.export',document=d,format='layered_large',**kw),expected)
    def source(self,**kw):return f.make([dict(name='original Δ 🎨',width=3,height=2,rgba=[20,80,140,0,200,40,70,1,30,20,10,127]*2)],version=2,**kw)
    def test_wide_fields_preserve_original_pixels_and_standard_export_compatibility(self):
        d=self.scene();a=self.export(d);b=base64.b64decode(a['data']);external=f.parse(b);self.assertEqual(external['version'],2);self.assertEqual(a['layered']['version'],2)
        for l,i in zip(external['layers'],d['items']):self.assertEqual(l['rgba'].hex(),i['content']['rgba_hex']);self.assertEqual(l['name'],i['name']);self.assertEqual(l['visible'],i['visible'])
        reopened=self.read(b);self.assertEqual(reopened['file_version'],2);self.assertEqual(reopened['format'],'layered_rgb_v2');self.assertEqual(self.pixels(reopened['document']),self.pixels(d))
        standard=self.invoke(dict(command='document.export',document=d,format='layered'));old=f.parse(base64.b64decode(standard['data']));self.assertEqual(old['version'],1);self.assertEqual(old['merged'],external['merged'])
        self.assertEqual([l['rgba'] for l in old['layers']],[l['rgba'] for l in external['layers']])
    def test_all_four_plane_compressions_use_correct_row_counts_and_preserve_hidden_rgb(self):
        for compression in range(4):
            b=self.source(compression=compression);d=self.read(b,color_policy='assume_srgb')['document'];self.assertEqual(d['items'][0]['content']['rgba_hex'],bytes([20,80,140,0,200,40,70,1,30,20,10,127]*2).hex())
            self.assertEqual(f.parse(b)['layers'][0]['rgba'].hex(),d['items'][0]['content']['rgba_hex'])
        good=f.plane(bytes([255])*6,3,0,2)
        for plane in [f.U16(1)+f.U32(2**32-1)*2,f.U16(1)+f.U32(0)*2,f.U16(1)+f.U16(4)*2+b'\2abc'*2]:
            layer=dict(name='bad',width=3,height=2,rgba=[1,2,3,255]*6,channel_data=[plane,good,good,good]);self.assertEqual(self.read(f.make([layer],version=2),1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')
    def test_large_native_canvases_exceed_standard_axis_limit_without_pixel_or_resolution_loss(self):
        for w,h in [(30001,1),(1,30001),(32768,1),(1,32768)]:
            d=self.document(w,h);data=bytes(v for i in range(w*h) for v in [i%256,(i*7)%256,91,[0,1,64,255][i%4]])
            d['items']=[dict(id='strip',name='original wide strip',content=dict(type='raster',width=w,height=h,rgba_hex=data.hex()))];d['resolution_ppi']=240
            self.assertEqual(self.invoke(dict(command='document.export',document=d,format='layered'),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
            a=self.export(d);b=base64.b64decode(a['data']);external=f.parse(b);self.assertEqual((external['width'],external['height']),(w,h));self.assertEqual(external['layers'][0]['rgba'],data)
            reopened=self.read(b)['document'];self.assertEqual(reopened['items'][0]['content']['rgba_hex'],data.hex());self.assertEqual(reopened['resolution_ppi'],240);self.assertEqual(self.pixels(reopened),self.pixels(d))
        # Full format axes larger than current engine bounds remain explicit, uncredited work.
        for w,h in [(32769,1),(1,300000)]:
            self.assertEqual(self.read(f.make([dict(name='p',width=1,height=1,rgba=[1,2,3,255])],w=w,h=h,version=2,merged=b''),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
    def test_unsigned_64bit_lengths_are_bounded_before_take_or_allocation(self):
        source=self.source();r=f.Reader(source);r.take(26);r.section();r.section();outer=r.at;info=outer+8;first_channel_length=info+8+2+16+2+2
        for at in [outer,info,first_channel_length]:
            for n in [2**32,2**63,2**64-1,32*1024*1024+1]:
                data=bytearray(source);data[at:at+8]=f.U64(n);self.assertEqual(self.read(data,1,color_policy='assume_srgb')['code'],'RESOURCE_LIMIT')
            data=bytearray(source);data[at:at+8]=f.U64(len(source));self.assertEqual(self.read(data,1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')
        for n in range(1,len(source),13):self.assertIn(self.read(source[:n],1,color_policy='assume_srgb')['code'],['INVALID_LAYERED_FILE','RESOURCE_LIMIT','UNSUPPORTED_LAYERED_SEMANTICS'])
    def test_large_tag_lengths_are_key_specific_and_unknown_semantics_still_fail(self):
        overlay=f.U16(0)+f.U16(1111)*4+f.U16(40)
        for sig in [b'8BIM',b'8B64']:
            tagged=sig+b'FMsk'+f.large_section(overlay)
            r=self.read(self.source(global_extra=tagged),color_policy='assume_srgb');self.assertIn('global:FMsk',r['omitted_nonappearance_records'])
        for key in [b'LMsk',b'Lr16',b'Lr32',b'Layr',b'Mt16',b'Mt32',b'Mtrn',b'Alph',b'lnk2',b'FEid',b'FXid',b'PxSD']:
            self.assertEqual(self.read(self.source(global_extra=b'8BIM'+key+f.large_section(b'')),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        globals=metadata.global_tag(b'OCIO',metadata.ocio())+metadata.global_tag(b'GenI',metadata.generation())
        self.assertEqual(self.read(self.source(global_extra=globals),color_policy='assume_srgb')['file_version'],2)
        self.assertEqual(self.read(self.source(global_extra=b'8B64'+globals[4:]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        backend=metadata.backend();tag=b'8B64cinf'+f.large_section(backend)+bytes(-len(backend)%4)
        self.assertIn('global:cinf',self.read(self.source(global_extra=tag),color_policy='assume_srgb')['omitted_nonappearance_records'])
        self.assertEqual(self.read(self.source(global_extra=b'8BIMFMsk'+f.U64(2**64-1)),1,color_policy='assume_srgb')['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.read(self.source(global_extra=f.tag(b'FMsk',overlay)),1,color_policy='assume_srgb')['code'],'RESOURCE_LIMIT')
    def test_native_publication_sessions_and_mcp_discover_large_format_without_new_transport(self):
        d=self.scene()
        with tempfile.TemporaryDirectory() as root:
            c=Client();c.initialize();s=dict(session_root=root,session_id='large')
            try:
                cap=c.success('capabilities');self.assertEqual(cap['layered_interchange']['large_export_format'],'layered_large');self.assertEqual(cap['layered_interchange']['additional_file_versions'],[2]);self.assertEqual(cap['layered_interchange']['extended_status'],'partial_uncredited');self.assertIn('layered_large',cap['publication']['formats'])
                c.success('session.create',**s,request_id='create',document=d)
                r=c.success('session.publish',**s,expected_revision=0,output=dict(output_root=root,file_name='original.psb',format='layered_large'))
                p=Path(root)/'original.psb';before=p.read_bytes();self.assertEqual(hashlib.sha256(before).hexdigest(),r['sha256'])
                opened=c.success('layered.import',source_path=str(p),id='large',expected_sha256=r['sha256']);self.assertEqual(opened['file_version'],2);self.assertEqual(self.pixels(opened['document']),self.pixels(d));self.assertTrue(c.success('session.verify',**s)['valid'])
                failure=c.tool('session.publish',**s,expected_revision=0,output=dict(output_root=root,file_name='original.psb',format='layered_large'));self.assertEqual(failure['structuredContent']['error']['code'],'OUTPUT_EXISTS')
                self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=dict(output_root=root,file_name='wrong.psd',format='layered_large')),1)['code'],'INVALID_REQUEST')
                self.assertEqual(self.invoke(dict(command='layered.import',source_path=str(p),id='cancelled',control=dict(timeout_ms=0)),1)['code'],'TIMEOUT');self.assertEqual(p.read_bytes(),before)
            finally:c.close()

if __name__=='__main__':unittest.main()
