"""Original exact sample, rational composite and public TIFF framing evidence."""
import base64
import copy
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib
import test_editing_cli as editing
import test_resampling_cli as resampling
from test_image_io_cli import tiff_tags
from test_mcp import Client


def packed(values, depth):
    return struct.pack('<'+{'u8':'B','u16':'H','f32':'f'}[depth]*len(values),*values).hex()


def layer(values,depth='u16',channels='rgba',w=None,id='source',**kw):
    n=4 if channels=='rgba' else 2;w=w or len(values)//n
    return dict(id=id,content=dict(type='samples',grid=dict(width=w,height=len(values)//n//w,depth=depth,channels=channels,data_hex=packed(values,depth))),**kw)


def decode(artifact):
    data=base64.b64decode(artifact['data']);tags=tiff_tags(data)
    assert tags.get(284,(1,))==(1,) and tags[338]==(2,) and tags[274]==(1,)
    assert tags.get(317,(1,))==(1,)
    strips=[data[o:o+n] for o,n in zip(tags[273],tags[279])]
    if tags[259] in [(8,),(32946,)]:strips=[zlib.decompress(p) for p in strips]
    else:assert tags[259]==(1,)
    raw=b''.join(strips);bits=tags[258][0];count=tags[277][0]
    assert tags[258]==(bits,)*count
    floating=tags[339]==(3,)*count
    if not floating:assert tags[339]==(1,)*count
    fmt='f' if floating else {8:'B',16:'H'}[bits]
    endian='<' if data[:2]==b'II' else '>'
    return list(struct.unpack(endian+fmt*(len(raw)//(bits//8)),raw)),tags


def q16(v):return int(max(F(0),min(F(1),v))*65535+F(1,2))


class SampleTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def document(self,items,w=None,h=None):
        grid=next(i['content']['grid'] for i in items if i['content']['type']=='samples')
        d=self.invoke(dict(command='document.create',id='sample-fixture',kind='raster',width=w or grid['width'],height=h or grid['height']))
        d['items']=items
        return self.invoke(dict(command='document.validate',document=d))
    def exported(self,d,depth='u16',channels='rgba',compression='none',expected=0,**kw):
        return self.invoke(dict(command='document.export',document=d,format='tiff',image_options=dict(depth=depth,channels=channels,compression=compression),**kw),expected)
    def edit(self,d,ops,expected=0):
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=ops),expected)
        return r if expected else r['document']

    def test_all_six_depth_channel_combinations_keep_native_samples_and_tags(self):
        for depth,maximum in [('u8',255),('u16',65535),('f32',1)]:
            values=([0,1,2,maximum//2,maximum-1,maximum] if depth!='f32' else [0,2**-149,2**-24,.125,.5000000596046448,1])
            for channels in ['rgba','gray_alpha']:
                source=[c for v in values for c in ([v,v,v,maximum] if channels=='rgba' else [v,maximum])]
                d=self.document([layer(source,depth,channels)]);before=copy.deepcopy(d)
                for compression in ['none','deflate']:
                    artifact=self.exported(d,depth,channels,compression);actual,tags=decode(artifact)
                    self.assertEqual(actual,source);self.assertEqual(tags[262],(2 if channels=='rgba' else 1,));self.assertEqual(artifact['settings']['depth'],depth)
                self.assertEqual(d,before)
                self.assertEqual(json.loads(self.invoke(dict(command='document.export',document=d,format='snapshot'))['data']),d)

    def test_adjacent_sixteen_bit_codes_survive_without_byte_plateaus(self):
        values=[c for i in range(4096) for c in (i,65535-i,(i*7919)%65536,65535)]
        d=self.document([layer(values,w=128)])
        actual,_=decode(self.exported(d));self.assertEqual(actual,values)
        self.assertEqual(len(set(actual[::4])),4096)

    def test_transparent_source_color_retained_and_output_zero_alpha_clears_color(self):
        for depth,values in [('u16',[12345,23456,34567,0,12345,23456,34567,1]),('f32',[.125,.25,.5,0,.125,.25,.5,2**-149])]:
            d=self.document([layer(values,depth)]);source=d['items'][0]['content']['grid']['data_hex']
            actual,_=decode(self.exported(d,depth));self.assertEqual(actual,[0]*4+values[4:])
            self.assertEqual(d['items'][0]['content']['grid']['data_hex'],source)
            p=self.invoke(dict(command='document.render',document=d));self.assertEqual(bytes.fromhex(p['data']),bytes(8));self.assertEqual(p['sample_precision']['output_depth'],'u8')

    def test_sixteen_bit_roundtrip_to_float_and_byte_is_one_explicit_output_projection(self):
        vals=[c for i in [0,1,127,128,255,256,257,32767,32768,65534,65535] for c in [i,65535-i,12345,65535]]
        d=self.document([layer(vals)])
        floats,_=decode(self.exported(d,'f32'))
        self.assertEqual(floats,[struct.unpack('<f',struct.pack('<f',v/65535))[0] for v in vals])
        octets,_=decode(self.exported(d,'u8'));self.assertEqual(octets,[int(F(v*255,65535)+F(1,2)) for v in vals])
        self.assertEqual(editing.png_pixels(base64.b64decode(self.invoke(dict(command='document.export',document=d,format='png'))['data']))[2],bytes(octets))

    def test_normal_layer_composition_matches_exact_rational_unrounded_alpha(self):
        a=[12345,45678,34567,11111];b=[53456,2345,22222,45678]
        d=self.document([layer(a,id='back'),layer(b,id='front',opacity=.375)])
        ca=[F(v,65535) for v in a];cb=[F(v,65535) for v in b];sa=cb[3]*F(3,8);alpha=sa+ca[3]*(1-sa)
        expected=[q16((cb[c]*sa+ca[c]*ca[3]*(1-sa))/alpha) for c in range(3)]+[q16(alpha)]
        self.assertEqual(decode(self.exported(d))[0],expected)

    def test_opacity_mask_and_adjustment_keep_sub_byte_channel_values(self):
        vals=[10001,20003,40007,50009]
        item=layer(vals,mask=dict(width=1,height=1,gray_hex='73'))
        adjustment=dict(id='invert',content=dict(type='adjustment',adjustment=dict(operators=[dict(type='invert')])))
        d=self.document([item,adjustment])
        expected=[65535-v for v in vals[:3]]+[q16(F(vals[3],65535)*F(115,255))]
        self.assertEqual(decode(self.exported(d))[0],expected)
        self.assertEqual(d['items'][0]['content']['grid']['data_hex'],packed(vals,'u16'))

    def test_bilinear_and_area_use_premultiplied_high_depth_reconstruction(self):
        a=[12345,30001,50003,20001];b=[50009,40003,10007,50011]
        for sampling,transform,w in [('bilinear',[2,0,0,1,0,0],4),('area',[.5,0,0,1,0,0],1)]:
            item=layer(a+b,transform=transform);item['content']['grid']['sampling']=sampling
            d=self.document([item],w=w);out,_=decode(self.exported(d))
            weights=[F(0),F(1,4),F(3,4),F(1)] if w==4 else [F(1,2)]
            expected=[];ties={}
            for t in weights:
                alpha=F(a[3],65535)*(1-t)+F(b[3],65535)*t
                exact=[(F(a[c]*a[3],65535**2)*(1-t)+F(b[c]*b[3],65535**2)*t)/alpha for c in range(3)]+[alpha]
                for v in exact:
                    if (v*65535).denominator==2:ties[len(expected)]=int(v*65535)
                    expected.append(q16(v))
            for i,(actual,want) in enumerate(zip(out,expected)):self.assertIn(actual,[want,ties.get(i,want)])

    def test_supersampling_keeps_tiny_alpha_and_exact_fractional_coverage(self):
        item=layer([12345,23456,34567,7],transform=[1,0,0,1,.25,0])
        d=self.document([item],w=2)
        out,_=decode(self.exported(d,render_options=dict(antialias='supersample4')))
        self.assertEqual(out,[12345,23456,34567,5,12345,23456,34567,2])

    def test_cubic_and_windowed_sinc_match_high_precision_independent_kernels(self):
        pixels=[[12345,23456,34567,12345],[40001,20003,30007,50009],[123,456,789,65535],[55555,33333,11111,32109]]
        for method in ['bicubic','lanczos3']:
            d=self.document([layer([c for p in pixels for c in p])]);d=self.edit(d,[dict(op='canvas',action=dict(type='scale',width=9,height=1,sampling=method))])
            actual,_=decode(self.exported(d));expected=[]
            with localcontext() as ctx:
                ctx.prec=60
                for x in range(9):
                    weights=resampling.weights(method,F(2*x+1,2)*F(4,9),F(4,9),4)
                    weights=[(i,D(v.numerator)/D(v.denominator) if isinstance(v,F) else v) for i,v in weights]
                    a=sum(D(pixels[i][3])*v for i,v in weights);a=max(D(0),min(D(65535),a))
                    colors=[max(D(0),min(D(65535)*a,sum(D(pixels[i][c]*pixels[i][3])*v for i,v in weights)))/a if a else D(0) for c in range(3)]
                    expected.extend(colors+[a])
            for v,w in zip(actual,expected,strict=True):
                rounded=int(w+D('.5'));self.assertEqual(v,rounded)

    def test_gray_export_requires_neutral_rgb_and_never_silently_converts_color(self):
        d=self.document([layer([10000,10001,10000,65535])])
        self.assertEqual(self.exported(d,channels='gray_alpha',expected=1)['code'],'GRAYSCALE_CONVERSION_REQUIRED')
        d=self.document([layer([12345,23456],channels='gray_alpha')])
        self.assertEqual(decode(self.exported(d))[0],[12345]*3+[23456])
        self.assertEqual(decode(self.exported(d,channels='gray_alpha'))[0],[12345,23456])

    def test_native_rectangular_replacement_preserves_outside_bytes_and_input(self):
        values=list(range(48));item=layer(values,w=4);item['content']['grid']['data_hex']=item['content']['grid']['data_hex'].upper()
        d=self.document([item]);before=copy.deepcopy(d);replacement=[60000+i for i in range(16)]
        op=dict(op='sample_replace',id='source',region=dict(x=1,y=1,width=2,height=2),data_hex=packed(replacement,'u16'))
        edited=self.edit(d,[op]);expected=values[:]
        expected[20:28]=replacement[:8];expected[36:44]=replacement[8:]
        actual=bytes.fromhex(edited['items'][0]['content']['grid']['data_hex'])
        self.assertEqual(list(struct.unpack('<48H',actual)),expected);self.assertEqual(d,before)
        self.assertEqual(edited['items'][0]['content']['grid']['data_hex'][:40],before['items'][0]['content']['grid']['data_hex'][:40])

    def test_invalid_ranges_bytes_depth_channels_dimensions_and_hdr_are_explicit(self):
        d=self.document([layer([.1,.2,.3,1],'f32')])
        for values in [[float('nan'),0,0,1],[float('inf'),0,0,1],[-.1,0,0,1],[2,0,0,1],[0,0,0,1.01]]:
            bad=copy.deepcopy(d);bad['items'][0]['content']['grid']['data_hex']=packed(values,'f32')
            self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'UNSUPPORTED_SAMPLE_RANGE')
        for key,value in [('width',0),('height',32769),('data_hex','00'),('data_hex','zz'*16),('depth','u32'),('channels','cmyk')]:
            bad=copy.deepcopy(d);bad['items'][0]['content']['grid'][key]=value
            self.invoke(dict(command='document.validate',document=bad),1)
        bad=copy.deepcopy(d);bad['kind']='vector';self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'INVALID_DOCUMENT')

    def test_edits_fail_atomically_for_locks_wrong_targets_and_invalid_rectangles(self):
        d=self.document([layer([1,2,3,65535])]);before=copy.deepcopy(d)
        op=dict(op='sample_replace',id='source',region=dict(x=0,y=0,width=1,height=1),data_hex=packed([4,5,6,65535],'u16'))
        for region in [dict(x=1,y=0,width=1,height=1),dict(x=0,y=0,width=0,height=1),dict(x=4294967295,y=0,width=1,height=1)]:
            result=self.edit(d,[dict(op='properties',id='source',name='pending'),dict(op,region=region)],1);self.assertEqual(result['operation_index'],1)
        locked=copy.deepcopy(d);locked['items'][0]['locked']=True
        self.assertIn('LOCK',self.edit(locked,[op],1)['code'])
        self.assertEqual(d,before)
        rgba8=copy.deepcopy(d);rgba8['items'][0]['content']=dict(type='raster',width=1,height=1,rgba_hex='010203ff')
        self.assertEqual(self.edit(rgba8,[op],1)['code'],'INVALID_OPERATION')

    def test_high_depth_pdf_brush_mask_bake_and_wrong_options_are_rejected(self):
        d=self.document([layer([1,2,3,65535],mask=dict(width=1,height=1,gray_hex='ff'))])
        self.assertEqual(self.invoke(dict(command='document.export',document=d,format='pdf'),1)['code'],'UNSUPPORTED')
        for fmt in ['png','jpeg','snapshot']:
            self.assertEqual(self.invoke(dict(command='document.export',document=d,format=fmt,image_options=dict(depth='u16')),1)['code'],'INVALID_REQUEST')
        self.assertEqual(self.edit(d,[dict(op='mask_apply',id='source')],1)['code'],'UNSUPPORTED')
        stroke=dict(points=[dict(point=[.5,.5])],diameter=1,mode=dict(type='paint',color=[20,40,60,255]))
        self.assertEqual(self.edit(d,[dict(op='brush_stroke',id='source',stroke=stroke)],1)['code'],'INVALID_OPERATION')
        d['output_profile']=dict(type='builtin',name='srgb')
        self.assertEqual(self.exported(d,expected=1)['code'],'UNSUPPORTED')

    def test_box_filter_retains_small_impulses_and_alpha_with_rational_convolution(self):
        values=[c for v in [0,10001,0,30005,0] for c in [v,v,v,65535]]
        item=layer(values,filters=[dict(id='blur',operator=dict(type='box',radius=1),border='clamp')]);d=self.document([item])
        actual,_=decode(self.exported(d,channels='gray_alpha'))
        expected=[]
        for i in range(5):
            v=sum(values[4*max(0,min(4,j))] for j in range(i-1,i+2))
            expected.extend([q16(F(v,3*65535)),65535])
        self.assertEqual(actual,expected)

    def test_artboard_tiff_depth_density_and_metadata_share_export_contract(self):
        frame=dict(id='board',content=dict(type='frame',frame=dict(role='artboard',width=2,height=1)))
        source=layer([12345,45678,23456,56789],channels='gray_alpha',parent='board')
        d=self.document([frame,source]);d['metadata']=dict(title='Original precision fixture',private=dict(secret='omit'))
        result=self.invoke(dict(command='artboard.export',document=d,format='tiff',scale=2,image_options=dict(depth='u16',channels='gray_alpha',compression='deflate')))
        a=result['artifacts'][0]['artifact'];values,tags=decode(a)
        self.assertEqual(values,[12345,45678]*2+[23456,56789]*2+[12345,45678]*2+[23456,56789]*2)
        self.assertEqual(tags[282],(192000,1000));self.assertEqual(tags[283],(192000,1000))
        description=bytes(tags[270]).decode();self.assertIn('Original precision fixture',description);self.assertNotIn('omit',description)
        self.assertEqual(a['settings']['depth'],'u16');self.assertEqual(d['metadata']['private'],dict(secret='omit'))

    def test_storage_and_render_limits_include_typed_grids_and_hidden_layers(self):
        d=self.document([layer([1,2,3,65535])]);grid=d['items'][0]['content']['grid']
        grid.update(width=32768,height=3)
        self.assertEqual(self.invoke(dict(command='document.validate',document=d),1)['code'],'RESOURCE_LIMIT')
        d=self.document([layer([1,2,3,65535])]);d.update(width=2048,height=1024)
        self.assertEqual(self.exported(d,expected=1)['code'],'RESOURCE_LIMIT')
        d=self.document([layer([1,2,3,65535])]);d['items'][0]['visible']=False;d['items'][0]['content']['grid']['data_hex']='ff'
        self.assertEqual(self.invoke(dict(command='document.validate',document=d),1)['code'],'INVALID_DOCUMENT')

    def test_sample_query_bounds_and_anchored_resize_preserve_grid(self):
        d=self.document([layer([12345,23456,34567,45678],transform=[1,0,0,1,2,3])],w=6,h=7)
        query=self.invoke(dict(command='document.query',document=d,query=dict(types=['samples'])))
        self.assertEqual(query['items'][0]['id'],'source');self.assertEqual(query['items'][0]['geometry_bounds'],[2,3,3,4])
        resized=self.edit(d,[dict(op='canvas',action=dict(type='scale',width=12,height=14,sampling='bilinear'))])
        self.assertEqual(resized['items'][0]['content']['grid']['data_hex'],d['items'][0]['content']['grid']['data_hex'])
        self.assertEqual(resized['items'][0]['content']['grid']['sampling'],'bilinear')

    def test_mcp_history_retry_undo_and_create_only_depth_publication(self):
        c=Client();self.addCleanup(c.close);c.initialize();d=self.document([layer([12345,23456,34567,45678])])
        with tempfile.TemporaryDirectory() as root:
            args=dict(session_root=root,session_id='samples')
            c.success('session.create',**args,request_id='create',document=d)
            action=dict(type='edit',operations=[dict(op='sample_replace',id='source',region=dict(x=0,y=0,width=1,height=1),data_hex=packed([20001,30003,40005,50007],'u16'))])
            edited=c.success('session.apply',**args,expected_revision=0,request_id='replace',action=action)['document']
            undo=c.success('session.apply',**args,expected_revision=1,request_id='undo',action=dict(type='undo'))['document'];self.assertEqual(undo,dict(d,revision=2))
            redo=c.success('session.apply',**args,expected_revision=2,request_id='redo',action=dict(type='redo'))['document'];self.assertEqual(redo,dict(edited,revision=3))
            replay=c.success('session.apply',**args,expected_revision=0,request_id='replace',action=action);self.assertEqual(replay['document'],edited)
            output=dict(output_root=root,file_name='samples.tiff',format='tiff',image_options=dict(depth='u16',compression='none'))
            receipt=c.success('session.publish',**args,expected_revision=3,output=output)
            self.assertEqual(receipt['settings']['depth'],'u16');self.assertEqual(receipt['sample_precision']['output_depth'],'u16')
            original=(Path(root)/'samples.tiff').read_bytes();self.assertEqual(decode(dict(data=base64.b64encode(original)))[0],[20001,30003,40005,50007])
            self.assertTrue(c.tool('session.publish',**args,expected_revision=3,output=output)['isError']);self.assertEqual((Path(root)/'samples.tiff').read_bytes(),original)
            self.assertEqual(c.success('session.read',**args)['document'],redo);c.success('session.verify',**args)

    def test_capabilities_describe_complete_supported_path_and_pending_boundaries(self):
        caps=self.invoke(dict(command='capabilities'))['sample_precision']
        self.assertEqual(caps['depths'],['u8','u16','f32']);self.assertTrue(caps['hdr']);self.assertTrue(caps['high_depth_import']);self.assertFalse(caps['import']['profiles']);self.assertEqual(caps['conversion']['operation'],'sample_convert');self.assertFalse(caps['native_brush_and_mask_bake']);self.assertEqual(caps['tiff']['gray_policy'],'exact_neutral_rgb_required')


if __name__=='__main__':unittest.main()
