"""Original scene-linear radiance, rational composition and Decimal display oracles."""
import base64
import copy
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
import json
from pathlib import Path
import struct
import tempfile
import unittest
import test_editing_cli as editing
import test_samples_cli as samples
import test_sample_conversion_cli as conversion
import test_resampling_cli as resampling
from test_mcp import Client


def layer(values,id='source',channels='rgba',w=None,**kw):
    item=samples.layer(values,'f32',channels,w,id,**kw);item['content']['grid']['encoding']='linear_srgb';return item


def f32(v):return struct.unpack('<f',struct.pack('<f',v))[0]


def encoded(v):
    v=D(v)
    return v*D('12.92') if v<=D('.0031308') else D('1.055')*v**(D(1)/D('2.4'))-D('.055')


def decoded(v):
    v=D(v)
    return v/D('12.92') if v<=D('.04045') else ((v+D('.055'))/D('1.055'))**D('2.4')


class HdrTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    edit=samples.SampleTests.edit
    exported=samples.SampleTests.exported
    def document(self,items,w=None,h=None):
        g=next(i['content']['grid'] for i in items if i['content']['type']=='samples')
        d=self.invoke(dict(command='document.create',id='radiance',kind='raster',width=w or g['width'],height=h or g['height']))
        d['items']=items;d['color_space']='linear_srgb';return self.invoke(dict(command='document.validate',document=d))
    def native(self,d,**kw):return samples.decode(self.exported(d,depth='f32',**kw))[0]
    def measured(self,d,points=None,expected=0):return self.invoke(dict(command='sample.measure',document=d,points=points or [[x,y] for y in range(d['height']) for x in range(d['width'])]),expected)
    def preview(self,d,view=None,expected=0,**kw):return self.invoke(dict(command='document.render',document=d,**({} if view is None else dict(render_options=dict(view=view,**kw)))),expected)
    def convert(self,d,**options):return self.edit(d,[dict(op='sample_convert',id='source',conversion=options)])

    def test_signed_radiance_gray_subnormals_and_large_values_survive_native_delivery(self):
        values=[-16.,-0.,2**-149,2**-126,.5,1.,2.,65536.,2**64]
        for channels in ['rgba','gray_alpha']:
            data=[c for v in values for c in ([v,v,v,1] if channels=='rgba' else [v,1])]
            d=self.document([layer(data,channels=channels)]);source=copy.deepcopy(d)
            for compression in ['none','deflate']:
                self.assertEqual(self.native(d,channels=channels,compression=compression),data)
            self.assertEqual(json.loads(self.invoke(dict(command='document.export',document=d,format='snapshot'))['data']),source)
            measured=self.measured(d);self.assertEqual(measured['minimum'][0],-16);self.assertEqual(measured['maximum'][0],2**64)
            self.assertEqual(measured['negative_color_channels'],3);self.assertEqual(measured['above_white_color_channels'],9)

    def test_seven_linear_blends_match_exact_rational_source_over(self):
        b=list(map(F,[4,-2,1.5,.25]));s=list(map(F,[2,3,-8,.5]))
        for mode in ['normal','multiply','linear_dodge','darken','lighten','difference','subtract']:
            functions={'normal':lambda x,y:y,'multiply':lambda x,y:x*y,'linear_dodge':lambda x,y:x+y,'darken':min,'lighten':max,'difference':lambda x,y:abs(x-y),'subtract':lambda x,y:x-y}
            a=s[3]+b[3]*(1-s[3]);expected=[((1-s[3])*b[c]*b[3]+s[3]*((1-b[3])*s[c]+b[3]*functions[mode](b[c],s[c])))/a for c in range(3)]+[a]
            d=self.document([layer(list(map(float,b)),id='back'),layer(list(map(float,s)),blend=mode)])
            self.assertEqual(self.native(d),[f32(v) for v in expected]);actual=self.measured(d)['samples'][0]['rgba']
            for x,y in zip(actual,expected):self.assertAlmostEqual(x,float(y),places=13)

    def test_encoded_byte_and_sample_sources_decode_before_linear_compositing(self):
        gray=128
        for content in [dict(type='raster',width=1,height=1,rgba_hex='808080ff'),samples.layer([gray]*3+[255],'u8')['content']]:
            d=self.document([layer([4,4,4,.5]),dict(id='encoded',opacity=.25,content=content)])
            with localcontext() as ctx:
                ctx.prec=55;q=decoded(D(gray)/255);a=D('.25')+D('.5')*D('.75');expected=(q*D('.25')+D(4)*D('.5')*D('.75'))/a
            actual=self.measured(d)['samples'][0]['rgba'];self.assertAlmostEqual(actual[0],float(expected),places=13);self.assertEqual(actual[3],float(a))

    def test_bilinear_sampling_preserves_radiance_and_alpha_weighting(self):
        item=layer([16,0,-4,.25,32,16,0,.75],transform=[1,0,0,1,.5,0]);item['content']['grid']['sampling']='bilinear'
        d=self.document([item],w=3);self.assertEqual(self.measured(d,[[1,0]])['samples'][0]['rgba'],[28,12,-1,.5])
        encoded_item=samples.layer([0,0,0,65535,65535,65535,65535,65535],transform=[1,0,0,1,.5,0]);encoded_item['content']['grid']['sampling']='bilinear'
        d=self.document([encoded_item],w=3);self.assertEqual(self.measured(d,[[1,0]])['samples'][0]['rgba'],[.5,.5,.5,1])

    def test_cubic_and_sinc_keep_signed_radiance_against_independent_kernels(self):
        pixels=[[16,-4,2,.25],[2,8,-2,1],[32,0,4,.5],[-8,4,64,.75]]
        for method in ['bicubic','lanczos3']:
            d=self.document([layer([v for p in pixels for v in p])]);d=self.edit(d,[dict(op='canvas',action=dict(type='scale',width=9,height=1,sampling=method))])
            actual=self.native(d);expected=[]
            with localcontext() as ctx:
                ctx.prec=60
                for x in range(9):
                    weights=resampling.weights(method,F(2*x+1,2)*F(4,9),F(4,9),4);weights=[(i,D(v.numerator)/D(v.denominator) if isinstance(v,F) else v) for i,v in weights]
                    alpha=sum(D(pixels[i][3])*v for i,v in weights)
                    colors=[sum(D(pixels[i][c])*D(pixels[i][3])*v for i,v in weights)/alpha if alpha>0 else D(0) for c in range(3)]
                    expected.extend([f32(v) for v in colors]+[f32(max(D(0),min(D(1),alpha)))])
            self.assertEqual(actual,expected)

    def test_reversible_grade_preserves_bytes_and_multiplies_linear_color_only(self):
        d=self.document([layer([-2,8,16,.25])]);before=copy.deepcopy(d)
        changed=self.edit(d,[dict(op='hdr_grade',id='source',grade=dict(exposure=2,gain=[.5,2,1]))])
        self.assertEqual(self.native(changed),[-4,64,64,.25]);self.assertEqual(changed['items'][0]['content'],d['items'][0]['content'])
        delta=self.invoke(dict(command='document.diff',before=d,after=changed));self.assertIn('hdr_grade',delta['items'][0]['fields'])
        restored=self.edit(changed,[dict(op='hdr_grade',id='source',grade=None)]);self.assertEqual(restored['items'],d['items']);self.assertEqual(d,before)

    def test_isolated_group_grade_clipping_and_opacity_retain_hdr(self):
        group=dict(id='group',opacity=.5,hdr_grade=dict(exposure=1),content=dict(type='group',isolated=True))
        child=layer([4,-2,8,.5],parent='group',mask=dict(width=1,height=1,gray_hex='ff'))
        d=self.document([group,child]);self.assertEqual(self.native(d),[8,-4,16,.25])
        d['items'].append(layer([16,4,-8,.5],id='clip',parent='group',clip_to='source'))
        d=self.invoke(dict(command='document.validate',document=d));self.assertEqual(self.native(d),[20,2,0,.25])

    def test_explicit_views_match_decimal_projection_without_changing_sources(self):
        d=self.document([layer([-2,8,16,.5,0,.125,1,1])]);before=copy.deepcopy(d)
        for method in ['clip','reinhard']:
            for stops in [-2,0,3]:
                view=dict(tone_map=method,exposure=stops);actual=bytes.fromhex(self.preview(d,view)['data']);expected=[]
                with localcontext() as ctx:
                    ctx.prec=55
                    for p in [[-2,8,16,.5],[0,.125,1,1]]:
                        for c in p[:3]:
                            v=max(D(0),D(c)*D(2)**stops);v=min(D(1),v) if method=='clip' else v/(1+v);expected.append(int(encoded(v)*255+D('.5')))
                        expected.append(int(D(p[3])*255+D('.5')))
                self.assertEqual(actual,bytes(expected));self.assertEqual(d,before)
        self.assertEqual(self.preview(d,expected=1)['code'],'HDR_VIEW_REQUIRED')
        self.assertEqual(self.exported(d,expected=1)['code'],'HDR_VIEW_REQUIRED')

    def test_view_follows_full_precision_supersample_average(self):
        d=self.document([layer([0,0,0,1,8,8,8,1])],w=1)
        d['items'][0]['transform']=[.5,0,0,1,0,0]
        artifact=self.exported(d,depth='u16',render_options=dict(antialias='supersample2',view=dict(tone_map='reinhard')))
        expected=int(encoded(D(4)/5)*65535+D('.5'));self.assertEqual(samples.decode(artifact)[0],[expected]*3+[65535])
        self.assertEqual(artifact['render_settings']['compositing_space'],'linear_srgb')

    def test_native_float_import_requires_declared_linear_interpretation_and_keeps_source(self):
        raw=conversion.tiff(2,1,[-2,4,8,.5,2**-149,65536,0,1],'f32',endian='>',planar=True,compression=8)
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'original.tif';p.write_bytes(raw)
            args=dict(command='sample.import',source_path=str(p),id='hdr')
            d=self.invoke(dict(args,color_policy='assume_linear_srgb'))['document'];self.assertEqual(d['color_space'],'linear_srgb');self.assertEqual(conversion.values(d),[-2,4,8,.5,2**-149,65536,0,1]);self.assertEqual(p.read_bytes(),raw)
            self.assertEqual(self.invoke(dict(args,color_policy='assume_srgb'),1)['code'],'UNSUPPORTED_SAMPLE_RANGE')
            data=base64.b64decode(self.exported(d,depth='f32')['data']);q=Path(root)/'delivery.tif';q.write_bytes(data)
            imported=self.invoke(dict(args,source_path=str(q),color_policy='assume_linear_srgb'))['document'];self.assertEqual(conversion.values(imported),conversion.values(d))

    def test_encoding_conversion_retains_endpoints_alpha_and_explicit_tone_map(self):
        vals=[c for i in range(256) for c in [i*257,(255-i)*257,i*257,65535]];d=self.document([samples.layer(vals)])
        changed=self.convert(d,depth='f32',channels='rgba',encoding='linear_srgb')
        with localcontext() as ctx:
            ctx.prec=55;expected=[f32(decoded(D(v)/65535)) if i%4!=3 else 1 for i,v in enumerate(vals)]
        self.assertEqual(conversion.values(changed),expected)
        back=self.convert(changed,depth='u16',channels='rgba',encoding='encoded_srgb',view=dict(tone_map='clip'));self.assertEqual(conversion.values(back),vals)
        bad=dict(op='sample_convert',id='source',conversion=dict(depth='u16',channels='rgba',encoding='encoded_srgb'))
        self.assertEqual(self.edit(changed,[bad],expected=1)['code'],'HDR_VIEW_REQUIRED')

    def test_linear_gray_conversion_keeps_out_of_range_and_hidden_color(self):
        d=self.document([layer([-2,8,16,0,4,4,4,1])]);changed=self.convert(d,depth='f32',channels='gray_alpha',gray='linear_luminance')
        expected=f32(F(-2*2126+8*7152+16*722,10000));self.assertEqual(conversion.values(changed),[expected,0,4,1])
        self.assertEqual(self.native(changed,channels='gray_alpha'),[0,0,4,1])
        projected=self.convert(changed,depth='u16',channels='gray_alpha',encoding='encoded_srgb',gray='require_neutral',view=dict(tone_map='clip'))
        self.assertEqual(conversion.values(projected),[65535,0,65535,65535])

    def test_native_replace_float_overflow_and_nonfinite_alpha_are_explicit(self):
        maximum=f32(float.fromhex('0x1.fffffep127'));d=self.document([layer([maximum,-maximum,0,1])])
        changed=self.edit(d,[dict(op='hdr_grade',id='source',grade=dict(exposure=1))]);self.assertEqual(self.exported(changed,depth='f32',expected=1)['code'],'UNSUPPORTED_SAMPLE_RANGE')
        self.assertEqual(self.measured(changed)['maximum'][0],maximum*2)
        self.assertEqual(bytes.fromhex(self.preview(changed,dict(tone_map='reinhard'))['data']),bytes([255,0,0,255]))
        replaced=self.edit(d,[dict(op='sample_replace',id='source',region=dict(x=0,y=0,width=1,height=1),data_hex=samples.packed([-8,32,4,.25],'f32'))]);self.assertEqual(self.native(replaced),[-8,32,4,.25])
        for pixel in [[float('inf'),0,0,1],[float('nan'),0,0,1],[0,0,0,-.1],[0,0,0,1.01]]:
            bad=copy.deepcopy(d);bad['items'][0]['content']['grid']['data_hex']=samples.packed(pixel,'f32');self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'UNSUPPORTED_SAMPLE_RANGE')

    def test_incompatible_semantics_locks_and_working_space_changes_fail_atomically(self):
        d=self.document([layer([4,2,-1,1])]);before=copy.deepcopy(d)
        for mode in ['screen','overlay','hue','color_dodge']:
            bad=copy.deepcopy(d);bad['items'][0]['blend']=mode;self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'UNSUPPORTED_HDR_MODE')
        bad=copy.deepcopy(d);bad['items'].append(dict(id='adjust',content=dict(type='adjustment',adjustment=dict(operators=[dict(type='exposure',stops=1)]))));self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'UNSUPPORTED_HDR_MODE')
        for patch in [dict(kind='vector'),dict(color_space='srgb')]:self.assertEqual(self.invoke(dict(command='document.validate',document=dict(d,**patch)),1)['code'],'UNSUPPORTED_HDR_MODE')
        self.assertEqual(self.edit(d,[dict(op='working_space',color_space='srgb')],expected=1)['code'],'UNSUPPORTED_HDR_MODE')
        bad=copy.deepcopy(d);bad['items'][0]['locked']=True;self.assertIn('LOCK',self.edit(bad,[dict(op='hdr_grade',id='source',grade=dict(exposure=1))],expected=1)['code'])
        ops=[dict(op='properties',id='source',name='pending'),dict(op='hdr_grade',id='source',grade=dict(exposure=33))];self.assertEqual(self.edit(d,ops,expected=1)['operation_index'],1);self.assertEqual(d,before)

    def test_working_space_edit_preserves_encoded_sources_and_transfer_requires_matching_space(self):
        item=samples.layer([32768]*3+[65535]);d=self.document([item]);d['color_space']='srgb';d=self.invoke(dict(command='document.validate',document=d))
        changed=self.edit(d,[dict(op='working_space',color_space='linear_srgb')]);self.assertEqual(changed['items'],d['items'])
        with localcontext() as ctx:ctx.prec=55;expected=float(decoded(D(32768)/65535))
        self.assertAlmostEqual(self.measured(changed)['samples'][0]['rgba'][0],expected,places=14)
        op=dict(op='transfer',transfer=dict(source=changed,ids=['source'],prefix='copy'))
        self.assertEqual(self.edit(d,[op],expected=1)['code'],'UNSUPPORTED_HDR_MODE')
        self.assertEqual(self.edit(changed,[op])['items'][1]['content'],changed['items'][0]['content'])

    def test_artboards_and_integer_delivery_require_explicit_view_and_keep_native_source(self):
        frame=dict(id='board',content=dict(type='frame',frame=dict(role='artboard',width=2,height=1)))
        d=self.document([frame,layer([2,4,8,1,-1,0,16,.5],parent='board')]);before=copy.deepcopy(d)
        native=self.invoke(dict(command='artboard.export',document=d,format='tiff',image_options=dict(depth='f32',compression='none')))
        self.assertEqual(samples.decode(native['artifacts'][0]['artifact'])[0],[2,4,8,1,-1,0,16,.5])
        for format in ['png','jpeg','pdf','svg']:
            r=self.invoke(dict(command='document.export',document=d,format=format),1);self.assertIn(r['code'],['HDR_VIEW_REQUIRED','UNSUPPORTED_HDR_MODE'])
        viewed=self.exported(d,depth='u16',render_options=dict(view=dict(tone_map='clip')));self.assertEqual(samples.decode(viewed)[0],[65535]*4+[0,0,65535,32768]);self.assertEqual(d,before)

    def test_measurement_points_discovery_and_preview_options_are_strict(self):
        d=self.document([layer([2,-1,4,1])]);caps=self.invoke(dict(command='capabilities'));self.assertTrue(caps['sample_precision']['hdr']);self.assertIn('sample.measure',caps['commands'])
        for points in [[[1,0]],[[0,1]],[[0,0]]*257]:self.assertEqual(self.measured(d,points,expected=1)['code'],'INVALID_DOCUMENT')
        self.assertEqual(self.preview(d,dict(tone_map='clip',exposure=33),expected=1)['code'],'INVALID_DOCUMENT')
        d['color_space']='srgb';d['items'][0]['content']['grid']=samples.layer([1,2,3,65535])['content']['grid'];self.assertEqual(self.preview(d,dict(tone_map='clip'),expected=1)['code'],'INVALID_REQUEST')

    def test_encoded_procedural_paints_and_opaque_backgrounds_enter_linear_space(self):
        vector=dict(id='vector',opacity=.5,content=dict(type='fill',width=1,height=1,paint=[128,64,192,255]))
        d=self.document([layer([4,8,-2,1]),vector]);actual=self.measured(d)['samples'][0]['rgba']
        with localcontext() as ctx:
            ctx.prec=55;expected=[float(decoded(D(v)/255)/2+D(b)/2) for v,b in zip([128,64,192],[4,8,-2])]+[1]
        for x,y in zip(actual,expected):self.assertAlmostEqual(x,y,places=14)
        d=self.document([layer([4,8,-2,.5])]);d=self.edit(d,[dict(op='background',id='source',action=dict(type='promote',matte=[128,64,192]))])
        expected=[float(decoded(D(v)/255)/2+D(b)/2) for v,b in zip([128,64,192],[4,8,-2])]+[1]
        for x,y in zip(self.measured(d)['samples'][0]['rgba'],expected):self.assertAlmostEqual(x,y,places=14)

    def test_active_normalized_operators_and_pass_through_grades_reject_explicitly(self):
        d=self.document([layer([4,2,8,1])]);source=copy.deepcopy(d)
        bad=copy.deepcopy(d);bad['items'][0]['filters']=[dict(id='blur',operator=dict(type='gaussian',sigma=1))]
        self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'UNSUPPORTED_HDR_MODE')
        for spec in [dict(type='group',isolated=True,knockout=True),dict(type='group',isolated=False)]:
            group=dict(id='group',hdr_grade=dict(exposure=1),content=spec);bad=copy.deepcopy(d);bad['items']=[group,dict(bad['items'][0],parent='group')]
            self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'UNSUPPORTED_HDR_MODE')
        self.assertEqual(d,source)

    def test_mcp_hdr_grade_history_retry_native_publication_and_readonly_measurement(self):
        c=Client();self.addCleanup(c.close);c.initialize();d=self.document([layer([-2,8,16,.5])])
        with tempfile.TemporaryDirectory() as root:
            args=dict(session_root=root,session_id='hdr');c.success('session.create',**args,request_id='create',document=d)
            action=dict(type='edit',operations=[dict(op='hdr_grade',id='source',grade=dict(exposure=1))])
            edited=c.success('session.apply',**args,request_id='grade',expected_revision=0,action=action)['document'];self.assertEqual(c.success('sample.measure',document=edited,points=[[0,0]])['samples'][0]['rgba'],[-4,16,32,.5])
            output=dict(output_root=root,file_name='hdr.tiff',format='tiff',image_options=dict(depth='f32'))
            c.success('session.publish',**args,expected_revision=1,output=output)
            self.assertEqual(c.success('session.apply',**args,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'],dict(d,revision=2))
            self.assertEqual(c.success('session.apply',**args,request_id='redo',expected_revision=2,action=dict(type='redo'))['document'],dict(edited,revision=3))
            self.assertTrue(c.success('session.apply',**args,request_id='grade',expected_revision=0,action=action)['replayed']);c.success('session.verify',**args)
            imported=c.success('sample.import',source_path=str(Path(root)/'hdr.tiff'),id='delivered',color_policy='assume_linear_srgb')['document'];self.assertEqual(conversion.values(imported),[-4,16,32,.5])


if __name__=='__main__':unittest.main()
