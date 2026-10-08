"""Independent areas, premultiplied integrals, convolution and delivery checks."""
import base64
import copy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import test_editing_cli as editing
import test_coordinate_precision_cli as coordinates
import test_effects_coverage_cli as effects
import test_profiles_cli as profiles
import test_boards_cli as boards
import test_artwork_masks_cli as masks
import test_instances_cli as instances
from test_mcp import Client


def rect(id='art',x=0,y=0,w=4,h=4,color=None,**kw):
    return dict(id=id,content=dict(type='vector',geometry=dict(shape='rect',x=x,y=y,width=w,height=h),fill=color or [30,100,210,255]),**kw)
def byte(v):return int(v*255+F(1,2))
def crop(raw,w,x,y,cw,ch):return b''.join(raw[((y+j)*w+x)*4:((y+j)*w+x+cw)*4] for j in range(ch))
def rgba(p):return list(zip(*[iter(p)]*4))


class RenderQualityTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    edit=coordinates.CoordinatePrecisionTests.edit
    def document(self,items=None,w=16,h=12,kind='vector'):
        d=self.invoke(dict(command='document.create',id='render-quality',kind=kind,width=w,height=h))
        return self.edit(d,[dict(op='add',item=i) for i in items]) if items else d
    def preview(self,d,scale=1,options=None,expected=0,**kw):
        q=dict(command='document.render',document=d,scale=scale,**kw)
        if options is not None:q['render_options']=options
        r=self.invoke(q,expected)
        return r if expected else (r,bytes.fromhex(r['data']))
    def export(self,d,format='png',scale=1,options=None,expected=0,**kw):
        q=dict(command='document.export',document=d,format=format,scale=scale,**kw)
        if options is not None:q['render_options']=options
        return self.invoke(q,expected)

    def test_default_preview_export_and_explicit_coverage_preserve_existing_pixels(self):
        d=self.document([rect(x=.125,y=.75,w=8.625,h=6.875)])
        for scale in [1,2,4]:
            a,p=self.preview(d,scale);b,q=self.preview(d,scale,{})
            self.assertEqual(p,q);self.assertNotIn('render_settings',a)
            self.assertEqual(b['render_settings']['antialias'],'coverage')
            self.assertEqual(editing.png_pixels(base64.b64decode(self.export(d,scale=scale)['data']))[2],p)
            self.assertEqual(self.export(d,scale=scale)['data'],self.export(d,scale=scale,options={})['data'])

    def test_none_has_binary_geometric_coverage_at_pixel_centers(self):
        d=self.document([rect(x=1.2,y=2.7,w=7.4,h=5.4)])
        for scale in [1,2,4]:
            r,p=self.preview(d,scale,dict(antialias='none'))
            for y in range(r['height']):
                for x in range(r['width']):
                    inside=1.2<(x+.5)/scale<8.6 and 2.7<(y+.5)/scale<8.1
                    self.assertEqual(p[(y*r['width']+x)*4:(y*r['width']+x+1)*4],bytes([30,100,210,255] if inside else [0]*4))

    def test_supersampling_corrects_fractional_rectangle_fixture_area(self):
        d=self.document([coordinates.vector(coordinates.rectangle(),transform=[1,0,0,1,9.25,7.125])],24,20)
        for scale in [1,2,4]:
            r,p=self.preview(d,scale,dict(antialias='supersample4'));maximum=0
            for y in range(r['height']):
                for x in range(r['width']):
                    overlap=lambda a,b,c:max(F(0),min(b,c+1)-max(a,c))
                    a=overlap(F(49,8)*scale,F(63,4)*scale,x)*overlap(F(19,4)*scale,F(101,8)*scale,y)
                    maximum=max(maximum,abs(p[(y*r['width']+x)*4+3]-byte(a)))
            self.assertLessEqual(maximum,1)

    def test_averaging_occurs_before_rgba_rounding_and_preserves_low_alpha_color(self):
        # Two half-pixel opaque/translucent patches: analytic premultiplied integral.
        for alpha in [1,7,64,128,254,255]:
            d=self.document([rect('red',w=.5,h=1,color=[255,0,0,alpha]),rect('blue',x=.5,w=.5,h=1,color=[0,0,255,255])],1,1)
            for aa in ['supersample2','supersample4']:
                for space in ['encoded_srgb','linear_srgb']:
                    _,p=self.preview(d,options=dict(antialias=aa,averaging_space=space))
                    colors=[F(alpha,alpha+255),F(0),F(255,alpha+255)]
                    if space=='linear_srgb':colors=[profiles.encode_srgb(float(v)) for v in colors]
                    expected=[byte(v) for v in colors]+[byte(F(alpha+255,510))]
                    self.assertEqual(list(p),expected)

    def test_gradient_sampling_integrates_colors_and_alpha_over_sample_grid(self):
        d=self.document([rect(w=1,h=1)],1,1)
        d['items'][0]['content']['fill']=dict(type='linear',start=[0,0],end=[1,0],stops=[dict(offset=0,color=[0,80,250,1]),dict(offset=1,color=[240,160,10,255])])
        # Stop interpolation is straight encoded sRGB; integrate associated samples.
        for n in [2,4]:
            points=[F(2*x+1,2*n) for x in range(n)]
            samples=[([240*t,80+80*t,250-240*t],1+254*t) for t in points]
            total=sum(a for _,a in samples)
            expected=[int(sum(c[k]*a for c,a in samples)/total+F(1,2)) for k in range(3)]+[int(total/n+F(1,2))]
            _,p=self.preview(d,options=dict(antialias='supersample'+str(n)))
            self.assertEqual(list(p),expected)

    def test_none_applies_to_clips_frames_images_and_artwork_regions(self):
        items=[rect(w=12,h=8,clip=dict(geometry=dict(shape='rect',x=1.2,y=1.2,width=5.6,height=4.6)))]
        d=self.document(items);_,p=self.preview(d,options=dict(antialias='none'))
        self.assertEqual(set(p[3::4]),{0,255})
        d=self.document([effects.layer('pixels',[[70,90,130,255]]*4,2,transform=[1.3,.2,.1,1.4,2.2,1.2])],kind='raster')
        _,p=self.preview(d,options=dict(antialias='none'));self.assertEqual(set(p[3::4]),{0,255})
        frame=self.board('frame',5,4,x=1.2,y=1.2,role='frame',background=[30,100,210,255])
        d=self.document([frame]);_,p=self.preview(d,options=dict(antialias='none'))
        self.assertEqual(set(p[3::4]),{0,255})

    def test_supersampled_triangle_agrees_with_exact_polygon_pixel_intersections(self):
        points=[(F(5,8),F(3,4)),(F(71,8),F(13,8)),(F(25,8),F(67,8))]
        commands=[dict(verb='move' if i==0 else 'line',to=[float(v) for v in p]) for i,p in enumerate(points)]+[dict(verb='close')]
        d=self.document([dict(id='triangle',content=dict(type='vector',geometry=dict(shape='path',commands=commands),fill=[30,100,210,255]))],10,10)
        def area(poly,x,y):
            for axis,edge,sign in [(0,x,1),(0,x+1,-1),(1,y,1),(1,y+1,-1)]:
                result=[]
                for a,b in zip(poly,poly[1:]+poly[:1]):
                    inside=lambda p:(p[axis]-edge)*sign>=0
                    if inside(a):result.append(a)
                    if inside(a)!=inside(b):
                        t=(F(edge)-a[axis])/(b[axis]-a[axis]);result.append(tuple(a[k]+t*(b[k]-a[k]) for k in [0,1]))
                poly=result
            return abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(poly,poly[1:]+poly[:1])))/2
        for scale in [1,2,4]:
            r,p=self.preview(d,scale,dict(antialias='supersample4'))
            polygon=[tuple(v*scale for v in q) for q in points]
            errors=[abs(p[(y*r['width']+x)*4+3]-byte(area(polygon,x,y))) for y in range(r['height']) for x in range(r['width'])]
            self.assertLessEqual(max(errors),3)

    def test_supersampled_ellipse_matches_independent_vertical_slice_integrals(self):
        import math
        cx,cy,rx,ry=7.125,5.625,3.75,2.25
        d=self.document([dict(id='ellipse',content=dict(type='vector',geometry=dict(shape='ellipse',cx=cx,cy=cy,rx=rx,ry=ry),fill=[30,100,210,255]))],14,12)
        r,p=self.preview(d,options=dict(antialias='supersample4'));errors=[]
        for y in range(12):
            for x in range(14):
                # 4096 independent midpoint slices bound integration noise well
                # below a byte; the declared ellipse is a backend cubic outline.
                area=0.
                for k in range(4096):
                    xx=x+(k+.5)/4096;v=1-((xx-cx)/rx)**2
                    if v>0:
                        h=ry*math.sqrt(v);area+=max(0,min(y+1,cy+h)-max(y,cy-h))/4096
                errors.append(abs(p[(y*14+x)*4+3]-int(area*255+.5)))
        self.assertLessEqual(max(errors),3)

    def test_font_outlines_share_antialias_and_padding_without_source_changes(self):
        import test_text_cli as text
        fixture=text.TextCliTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        for kind in ['vector','raster']:
            d=fixture.document(kind,text='AB');d['items'][0]['transform']=[1,0,0,1,.125,.375]
            before=copy.deepcopy(d)
            for aa in ['none','coverage','supersample2','supersample4']:
                kw=dict(font_root=str(fixture.store));options=dict(antialias=aa)
                r,p=self.preview(d,options=options,**kw)
                self.assertEqual(p,self.preview(d,options=dict(options,padding=3),**kw)[1])
                if aa=='none':self.assertEqual(set(p[3::4]),{0,255})
                if kind=='vector':
                    outlined=fixture.edit(d,[dict(op='text_outline',id='label')])
                    self.assertEqual(p,self.preview(outlined,options=options,**kw)[1])
            self.assertEqual(d,before)

    def test_gaussian_effect_padding_matches_independent_full_convolution(self):
        e=effects.effect('shadow','shadow',[200,40,10,173],sigma=.75,offset=[2.5,1.25])
        d=self.document([rect(x=-1,y=1,w=2,h=2,color=[30,100,210,128],effects=[e])],6,5)
        _,p=self.preview(d,options=dict(padding=4))
        source=[effects.premul([30,100,210,128] if 3<=x<5 and 5<=y<7 else [0]*4) for y in range(13) for x in range(14)]
        reference=effects.decorated(source,14,13,[e]);raw=bytes(v for q in reference for v in [int(max(F(0),min(F(255),v))+F(1,2)) for v in effects.blending.encoded(q)])
        self.assertEqual(p,crop(raw,14,4,4,6,5))
        d=self.document([masks.source(),rect('mask',x=.2,y=.2,w=4.6,h=3.6,parent='source'),rect(artwork_mask=dict(source='source',region=[.2,.2,4.6,3.6],clip_region=True))])
        _,p=self.preview(d,options=dict(antialias='none'));self.assertEqual(set(p[3::4]),{0,255})

    def test_padding_recovers_off_canvas_shadow_and_optionally_retains_outer_pixels(self):
        d=self.document([rect(x=-2,y=2,w=2,h=3,effects=[effects.effect('shadow','shadow',[200,40,10,255],sigma=0,offset=[3,0])])],8,8)
        original=copy.deepcopy(d)
        self.assertFalse(any(self.preview(d)[1]))
        for aa in ['none','coverage','supersample2','supersample4']:
            for scale in [1,2]:
                r,p=self.preview(d,scale,dict(antialias=aa,padding=4))
                outer,q=self.preview(d,scale,dict(antialias=aa,padding=4,crop_to_canvas=False))
                self.assertEqual(crop(q,outer['width'],4*scale,4*scale,8*scale,8*scale),p)
                for y in range(8*scale):
                    for x in range(8*scale):
                        c=[200,40,10,255] if 1<=x/scale<3 and 2<=y/scale<5 else [0]*4
                        self.assertEqual(list(p[(y*8*scale+x)*4:(y*8*scale+x+1)*4]),c)
                self.assertEqual(outer['render_settings']['origin'],[-4,-4])
        self.assertEqual(d,original)

    def test_padding_filtered_outside_source_matches_independent_box_convolution(self):
        d=self.document([rect(x=-1,y=2,w=2,h=2,color=[160,40,100,128],filters=[dict(id='blur',operator=dict(type='box',radius=1))])],6,6)
        r,p=self.preview(d,options=dict(padding=3));self.assertEqual((r['width'],r['height']),(6,6))
        for y in range(6):
            for x in range(6):
                n=sum(-1<=x+i<1 and 2<=y+j<4 for i in [-1,0,1] for j in [-1,0,1]);a=byte(F(n*128,9*255))
                self.assertEqual(list(p[(y*6+x)*4:(y*6+x+1)*4]),[160,40,100,a] if a else [0]*4)

    def test_padding_preserves_unlinked_masks_and_component_definition_coordinates(self):
        d=instances.InstanceTests.document(self)
        # Independent expected shift invariance for shared source instances.
        for aa in ['none','coverage','supersample4']:
            self.assertEqual(self.preview(d,options=dict(antialias=aa))[1],self.preview(d,options=dict(antialias=aa,padding=3))[1])
        for linked in [False,True]:
            mask=dict(width=4,height=3,gray_hex='ff0080ff'*3,linked=linked,transform=[1,0,0,1,2,1])
            d=self.document([rect(x=1,y=1,w=8,h=6,mask=mask,transform=[1,0,0,1,1,1])])
            self.assertEqual(self.preview(d)[1],self.preview(d,options=dict(padding=4))[1])

    def test_padding_preserves_artwork_definition_and_unlinked_reference_placement(self):
        for linked in [False,True]:
            d=self.document([masks.source(),rect('mask',x=1,y=1,w=3,h=3,parent='source'),rect(w=12,h=8,artwork_mask=masks.mask(linked=linked,transform=[1,0,0,1,2,1]))])
            for aa in ['coverage','supersample4']:
                self.assertEqual(self.preview(d,options=dict(antialias=aa))[1],self.preview(d,options=dict(antialias=aa,padding=3))[1])

    def test_rendering_locked_sources_is_read_only_and_snapshot_identical(self):
        d=self.document([effects.layer('art',[[30,100,210,128]]*16,4,locked=True,transform=[1,0,0,1,.25,.25])],kind='raster')
        d['selection']=dict(width=16,height=12,gray_hex='80'*192)
        source=json.dumps(d,sort_keys=True)
        for options in [dict(padding=4),dict(antialias='supersample4',padding=2,crop_to_canvas=False)]:
            self.preview(d,options=options);self.export(d,options=options)
        self.assertEqual(json.dumps(d,sort_keys=True),source)
        self.assertEqual(json.loads(self.export(d,'snapshot')['data']),self.invoke(dict(command='document.validate',document=d)))

    def test_tiff_compressions_and_jpeg_quality_density_repeatable_at_selected_resolution(self):
        d=self.document([rect(x=.25,y=.25,w=6.5,h=4.5)],8,6);d['resolution_ppi']=123.5
        import test_image_io_cli as images
        for scale in [1,3,4]:
            opts=dict(antialias='supersample4',padding=1,crop_to_canvas=False)
            r,p=self.preview(d,scale,opts)
            for compression in ['none','lzw','deflate']:
                a=self.export(d,'tiff',scale,opts,image_options=dict(compression=compression));self.assertEqual(a,self.export(d,'tiff',scale,opts,image_options=dict(compression=compression)))
                tags=images.tiff_tags(base64.b64decode(a['data']));self.assertEqual(tags[256],(r['width'],));self.assertEqual(tags[257],(r['height'],))
                self.assertEqual(a['settings']['resolution_ppi'],123.5*scale)
            for quality in [1,75,100]:
                for chroma in ['full','half']:
                    io=dict(quality=quality,chroma=chroma,matte=[245,245,245])
                    a=self.export(d,'jpeg',scale,opts,image_options=io)
                    self.assertEqual(a,self.export(d,'jpeg',scale,opts,image_options=io));self.assertEqual(a['width'],r['width'])
                    self.assertEqual(a['settings']['quality'],quality)
            self.assertEqual(self.export(d,'jpeg',scale,opts,expected=1)['code'],'ALPHA_POLICY_REQUIRED')

    def test_profile_conversion_follows_supersample_average_and_embeds_exact_bytes(self):
        d=self.document([rect('left',w=.5,h=1,color=[255,0,0,255]),rect('right',x=.5,w=.5,h=1,color=[0,0,255,255])],1,1)
        profile=profiles.linear_profile();d['output_profile']=profiles.embedded(profile)
        for space in ['encoded_srgb','linear_srgb']:
            opts=dict(antialias='supersample4',averaging_space=space)
            a=self.export(d,options=opts);data=base64.b64decode(a['data']);self.assertEqual(profiles.png_profile(data),profile)
            pixel=editing.png_pixels(data)[2];expected=round((profiles.decode_srgb(128/255) if space=='encoded_srgb' else profiles.decode_srgb(188/255))*255)
            for channel in [0,2]:self.assertLessEqual(abs(pixel[channel]-expected),1)
            self.assertEqual(pixel[3],255)
            for fmt,reader in [('tiff',profiles.tiff_profile),('jpeg',profiles.jpeg_profile)]:
                self.assertEqual(reader(base64.b64decode(self.export(d,fmt,options=opts)['data'])),profile)

    def test_artboard_order_bleed_sampling_receipts_and_whole_range_failures(self):
        d=boards.BoardCliTests.fixture(self);before=copy.deepcopy(d)
        opts=dict(antialias='supersample4',padding=2,crop_to_canvas=False)
        for fmt in ['png','tiff','jpeg']:
            kw=dict(image_options=dict(matte=[255]*3)) if fmt=='jpeg' else {}
            q=dict(command='artboard.export',document=d,format=fmt,scale=2,include_bleed=True,selection=dict(type='ids',ids=['tall','wide']),render_options=opts,**kw)
            a=self.invoke(q);self.assertEqual(a,self.invoke(q));self.assertEqual([e['id'] for e in a['artifacts']],['tall','wide'])
            for entry,dimensions in zip(a['artifacts'],[(14,20),(24,22)]):
                self.assertEqual((entry['artifact']['width'],entry['artifact']['height']),dimensions)
                self.assertEqual(entry['artifact']['render_settings']['internal_scale'],8)
        self.assertEqual(d,before)
        q['scale']=4;q['render_options']['padding']=256
        e=self.invoke(q,1);self.assertEqual(e['code'],'RESOURCE_LIMIT');self.assertEqual(e['artboard_id'],'tall')

    board=boards.BoardCliTests.board
    rectangle=boards.BoardCliTests.rectangle

    def test_publication_metadata_dimensions_hashes_and_create_only_sources(self):
        d=self.document([rect(x=.25,y=.5,w=5.5,h=4.25)]);d['metadata']=dict(description='Original quality fixture')
        opts=dict(antialias='supersample4',padding=2,crop_to_canvas=False)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source.json';source.write_text(json.dumps(d));original=source.read_bytes()
            output=dict(output_root=temp,file_name='quality.png',format='png',scale=2,render_options=opts)
            r=self.invoke(dict(command='document.publish',document=d,output=output));raw=(root/'quality.png').read_bytes()
            self.assertEqual(r['render_settings']['origin'],[-2,-2]);self.assertEqual(r['sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual(source.read_bytes(),original)
            chunks=editing.png_pixels(raw)[3];packet=json.loads(chunks[b'iTXt'].split(b'\0',5)[-1]);delivery=packet['delivery']
            self.assertEqual([delivery['width'],delivery['height']],[40,32]);self.assertEqual(delivery['render_settings']['origin'],[-2,-2])
            self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=output),1)['code'],'OUTPUT_EXISTS')
            self.assertEqual((root/'quality.png').read_bytes(),raw);self.assertEqual(sorted(p.name for p in root.iterdir()),['quality.png','source.json'])

    def test_options_validation_unsupported_formats_and_resource_budgets(self):
        d=self.document()
        for opts in [dict(padding=257),dict(padding=-1),dict(antialias='magic'),dict(extra=1),dict(averaging_space='linear_srgb')]:
            self.preview(d,options=opts,expected=1)
        for fmt in ['svg','snapshot','pdf']:
            self.assertEqual(self.export(d,fmt,options={},expected=1)['code'],'INVALID_REQUEST')
        self.assertEqual(self.preview(d,scale=5,expected=1)['code'],'INVALID_REQUEST')
        large=self.document(w=257,h=256)
        self.assertEqual(self.preview(large,options=dict(antialias='supersample4'),expected=1)['code'],'RESOURCE_LIMIT')
        effects_doc=self.document([rect(w=50,h=50,effects=[effects.effect('outline','stroke',[255]*4,radius=32)])],64,64)
        self.assertEqual(self.preview(effects_doc,scale=4,options=dict(antialias='supersample4'),expected=1)['code'],'RESOURCE_LIMIT')

    def test_mcp_discovery_preview_persistent_publish_and_revision_unchanged(self):
        c=Client();self.addCleanup(c.close);c.initialize()
        d=self.document([rect(x=.125,y=.25,w=5.5,h=4.5)])
        opts=dict(antialias='supersample4',padding=2)
        result=c.success('document.render',document=d,render_options=opts)
        self.assertEqual(result,self.preview(d,options=opts)[0])
        self.assertIn('render_quality',c.success('capabilities'))
        with tempfile.TemporaryDirectory() as temp:
            created=c.success('session.create',session_root=temp,session_id='quality-session',request_id='create',document=d)
            before=c.success('session.read',session_root=temp,session_id='quality-session')
            output=dict(output_root=temp,file_name='session.png',format='png',render_options=opts)
            c.success('session.publish',session_root=temp,session_id='quality-session',expected_revision=0,output=output)
            after=c.success('session.read',session_root=temp,session_id='quality-session')
            self.assertEqual(before,after)
            self.assertEqual(editing.png_pixels((Path(temp)/'session.png').read_bytes())[2],bytes.fromhex(result['data']))


if __name__=='__main__':unittest.main()
