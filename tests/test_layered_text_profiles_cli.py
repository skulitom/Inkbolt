"""Authored text paint converts before RGB8 rounding, independently of caches."""
import base64,copy,hashlib,json,struct,unittest
import layered_editable_text_fixtures as p
import layered_fixtures as f
import layered_object_fixtures as objects
import test_layered_editable_text_cli as editable
import test_layered_story_cli as story
from test_profiles_cli import linear_profile,encode_srgb
from test_mcp import Client


class LayeredTextProfileTests(unittest.TestCase):
    invoke=editable.EditableLayeredTextTests.invoke
    setUp=editable.EditableLayeredTextTests.setUp
    add_font=editable.EditableLayeredTextTests.add_font
    bindings=editable.EditableLayeredTextTests.bindings
    args=editable.EditableLayeredTextTests.args
    load=editable.EditableLayeredTextTests.load
    pixels=editable.EditableLayeredTextTests.pixels

    def encoded(self,profile,colors,global_mode=False,version=1,extra_layers=None):
        payload=p.local(styles=[p.style(FillColor=dict(Type=1,Values=[1.0,*c])) for c in colors],
                        lengths=[1,2] if len(colors)==2 else [3])
        layer=p.layer(payload=payload)
        tail=b''
        if global_mode:
            # Global authorship overrides this deliberately unrelated local paint.
            layer=p.layer();g=p.global_data();runs=g['1']['1'][0]['0']['6']['0'];first=copy.deepcopy(runs[0]);runs.clear()
            for i,color in enumerate(colors):
                run=copy.deepcopy(first);run['1']=3 if len(colors)==1 else (1 if i==0 else 2)
                run['0']['0']['6']['53']['0']['1']=[1.0,*color];runs.append(run)
            tail=story.tag(story.entries(g))
        return f.make([layer,*(extra_layers or [])],w=64,h=48,version=version,profile=profile,global_extra=tail)

    def test_local_and_authoritative_global_floating_paint_converts_before_rounding(self):
        colors=[[.003,.123456,.45789],[.001,.21123,.79876]]
        for version in [1,2]:
            for global_mode in [False,True]:
                for gamma in [1,1.8]:
                    profile=linear_profile(gamma);raw=self.encoded(profile,colors,global_mode,version)
                    r=self.load(raw,color_policy='convert_srgb');frame=r['document']['items'][0]['content']['frame']
                    self.assertEqual([(x['start'],x['end']) for x in frame['ranges']],[(1,2)])
                    for style,color in zip([frame['style'],frame['ranges'][0]['style']],colors):
                        expected=[round(255*encode_srgb(c**(round(gamma*256)/256))) for c in color]+[255]
                        self.assertLessEqual(max(abs(a-b) for a,b in zip(style['fill'],expected)),1)
                    if gamma==1:
                        # Early byte rounding would turn .003 into 1/255, producing 13 instead of 10.
                        self.assertEqual(frame['style']['fill'][0],10)
                    receipt=r['text'][0]
                    self.assertEqual(receipt['color_interpretation'],'converted_srgb_before_quantization')
                    self.assertEqual(receipt['color_conversion'],dict(source_profile_sha256=hashlib.sha256(profile).hexdigest(),target='srgb',intent='relative_colorimetric',black_point_compensation=False,gamut_policy='clip_to_srgb',clipping_count_available=False))
                    self.assertEqual(receipt['cached_rgba_sha256'],hashlib.sha256(bytes([9,80,7,255])).hexdigest())
                    self.assertFalse(receipt['cached_pixels_used'])
                    self.assertEqual(r['interpretation'],'converted_srgb_per_layer')

    def test_internal_gamut_clipping_is_not_reported_as_zero_loss(self):
        profile=bytearray(linear_profile())
        # Original matrix profile with a red primary 25% beyond the sRGB red.
        for i in range(struct.unpack_from('>I',profile,128)[0]):
            tag,offset,size=struct.unpack_from('>4sII',profile,132+12*i)
            if tag==b'rXYZ':
                for c in range(3):
                    at=offset+8+c*4;value=struct.unpack_from('>i',profile,at)[0]
                    struct.pack_into('>i',profile,at,round(value*1.25))
        r=self.load(self.encoded(bytes(profile),[[1.0,0.0,0.0]]),color_policy='convert_srgb')
        self.assertEqual(r['document']['items'][0]['content']['frame']['style']['fill'],[255,0,0,255])
        receipt=r['text'][0]['color_conversion']
        self.assertEqual(receipt['gamut_policy'],'clip_to_srgb')
        self.assertFalse(receipt['clipping_count_available']);self.assertNotIn('clipped_components',receipt)

    def test_pixel_paint_agrees_and_delivered_text_is_not_converted_twice(self):
        color=[64/255,128/255,192/255];pixel=dict(name='Matching pixel',width=1,height=1,xy=(60,40),rgba=[64,128,192,255])
        r=self.load(self.encoded(linear_profile(),[color],extra_layers=[pixel]),color_policy='convert_srgb');d=r['document']
        text=next(i for i in d['items'] if i['content']['type']=='text');raster=next(i for i in d['items'] if i['content']['type']=='raster')
        self.assertEqual(bytes(text['content']['frame']['style']['fill']).hex(),raster['content']['rgba_hex'])
        before=self.pixels(d)
        for format in ['layered','layered_large']:
            artifact=self.invoke(dict(command='document.export',document=d,format=format,font_root=str(self.store),
                layered_options=dict(text=dict(reconstruction='native_layout',shape_owner='OriginalGeometry'))))
            reopened=self.load(base64.b64decode(artifact['data']),color_policy='convert_srgb')
            self.assertEqual(self.pixels(reopened['document']),before)
            self.assertEqual(reopened['text'][0]['color_interpretation'],'source_is_srgb')
            self.assertNotIn('color_conversion',reopened['text'][0])
            other=next(i for i in reopened['document']['items'] if i['content']['type']=='text')
            self.assertEqual(other['content']['frame'],text['content']['frame'])
            self.assertEqual(other['transform'],text['transform'])

    def test_nested_text_uses_its_own_profile_once_and_mcp_matches_cli(self):
        nested=self.encoded(linear_profile(),[[.123,.345,.567]],True,2)
        expected=self.load(nested,color_policy='convert_srgb')['document']
        layer=dict(name='Placed text',width=1,height=1,rgba=[0,0,255,255],extra=objects.placement(size=(64,48),matrix=(1,0,0,1,0,0)))
        for version in [1,2]:
            raw=f.make([layer],w=64,h=48,version=version,profile=linear_profile(2),global_extra=objects.global_sources([objects.entry(nested)],version=version))
            r=self.load(raw,color_policy='convert_srgb',embedded_objects=objects.POLICY)
            source=json.loads(r['document']['items'][0]['content']['object']['snapshot'])
            self.assertEqual(source['items'],expected['items']);self.assertEqual(self.pixels(r['document']),self.pixels(expected))
            receipt=r['embedded_sources'][0]['text'][0]['color_conversion']
            self.assertEqual(receipt['source_profile_sha256'],hashlib.sha256(linear_profile()).hexdigest())
            args=self.args(raw);args.update(color_policy='convert_srgb',embedded_objects=objects.POLICY)
            c=Client()
            try:
                c.initialize();self.assertEqual(c.success('layered.import',**{k:v for k,v in args.items() if k!='command'}),r)
                cap=c.success('capabilities')['layered_interchange']['text_import']
                self.assertEqual(cap['profile_conversion'],'explicit_convert_srgb;authored_components_before_rgb8_quantization;source_profile_per_nested_document')
                self.assertNotIn('profile_conversion',cap['unsupported'])
            finally:c.close()

    def test_conversion_preserves_policy_and_semantic_failures_without_document(self):
        raw=self.encoded(linear_profile(),[[.2,.4,.6]])
        self.assertEqual(self.load(raw,1)['code'],'COLOR_POLICY_REQUIRED')
        self.assertEqual(self.load(p.source(),1,color_policy='convert_srgb')['code'],'COLOR_POLICY_REQUIRED')
        for change in [dict(FillColor=dict(Type=1,Values=[.5,.2,.4,.6])),dict(FillColor=dict(Type=1,Values=[1,-.1,.4,.6])),dict(StrokeFlag=True),dict(UnknownControl=0)]:
            payload=p.local(styles=[p.style(**change)]);raw=f.make([p.layer(payload=payload)],w=64,h=48,profile=linear_profile())
            error=self.load(raw,1,color_policy='convert_srgb');self.assertNotIn('document',error)
            self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        layer=p.layer();layer['channel_data']=[b'\x00\x00']*4
        raw=f.make([layer],w=64,h=48,profile=linear_profile())
        self.assertEqual(self.load(raw,1,color_policy='convert_srgb')['code'],'INVALID_LAYERED_FILE')
        raw=self.encoded(linear_profile(),[[.2,.4,.6]])
        self.assertEqual(self.load(raw,1,color_policy='convert_srgb',control=dict(timeout_ms=0))['code'],'TIMEOUT')
        self.assertEqual(self.load(raw,1,color_policy='convert_srgb',expected_sha256='0'*64)['code'],'SOURCE_MISMATCH')


if __name__=='__main__':unittest.main()
