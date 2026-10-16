"""Nonlocal source dependencies, independent sampling, and source preservation."""
import base64,copy,math,struct,unittest
from fractions import Fraction as F
import test_tiled_filter_families as family
import test_filters_cli as reference
import test_tiled_effects as effects
from test_mcp import Client
from test_render_quality_cli import rect
from test_samples_cli import decode
from test_image_io_cli import tiff_tags
from test_cli import EXE
import native_nonlocal_workload as workload


def radial(**kw):return dict(type='radial',center=[65.5,3.5],angle=40,zoom=.125,samples=3,**kw)


class NonlocalFilterTests(unittest.TestCase):
    setUp=family.TiledFilterFamilyTests.setUp
    cli=family.TiledFilterFamilyTests.cli
    document=family.TiledFilterFamilyTests.document
    exported=family.TiledFilterFamilyTests.exported
    pixels=family.TiledFilterFamilyTests.pixels
    source=family.TiledFilterFamilyTests.source
    filter=family.TiledFilterFamilyTests.filter

    def samples(self,d,tiled=True,**options):
        return decode(self.cli('document.export',document=d,format='tiff',
            image_options=dict(depth='f32',channels='rgba',compression='none'),
            render_options=dict(evaluation='tiled' if tiled else 'whole',**options)))[0]

    def test_independent_radial_and_twist_sampling_at_real_borders(self):
        w,h=137,7;d,values=self.source(w,h)
        source=[[float(v) for v in p] for p in reference.premult(values)]
        for twist in (False,True):
            op=family.creative(type='twist',center=[65.5,3.5],radius=70,angle=103) if twist else radial()
            for border in ('clamp','reflect','transparent'):
                self.filter(d,op,border);actual=self.samples(d);expected=[]
                for y in range(h):
                    for x in range(w):
                        dx,dy=x-65,y-3
                        if twist:
                            distance=math.hypot(dx,dy)/70
                            if distance>=1:p=source[y*w+x]
                            else:
                                a=math.radians(103)*(1-distance)**2
                                p=reference.bilinear(source,w,h,65+dx*math.cos(a)-dy*math.sin(a),3+dx*math.sin(a)+dy*math.cos(a),border)
                        else:
                            taps=[]
                            for t in (-.5,0,.5):
                                a=math.radians(40)*t;k=1+.125*t
                                taps.append(reference.bilinear(source,w,h,65+(dx*math.cos(a)-dy*math.sin(a))*k,3+(dx*math.sin(a)+dy*math.cos(a))*k,border))
                            p=[sum(t[c] for t in taps)/3 for c in range(4)]
                        expected.extend([float(v/p[3]) for v in p[:3]]+[float(p[3])] if p[3] else [0]*4)
                self.assertEqual(len(actual),len(expected))
                self.assertLess(max(abs(a-b) for a,b in zip(actual,expected)),1e-6)

    def test_affine_sources_both_tile_axes_and_outside_centers_match_whole(self):
        d,_=self.source(17,19);d.update(width=263,height=141)
        d['items'][0]['transform']=[1,.125,.25,1,121,119]
        for op in [dict(type='radial',center=[9,10],angle=63,zoom=.5,samples=5),
                   dict(type='radial',center=[-250,700],angle=-12,zoom=-.5,samples=3),
                   family.creative(type='twist',center=[8,10],radius=15,angle=257)]:
            for border in ('transparent','clamp','reflect'):
                self.filter(d,op,border)
                self.assertEqual(self.samples(d),self.samples(d,False),(op,border))

    def test_parent_clipped_sibling_and_stack_dependencies_keep_filter_order(self):
        d,_=self.source(17,19);d.update(width=263,height=141,resource_profile='large_raster')
        d['items'][0].update(transform=[1,0,0,1,119,115],parent='group')
        self.filter(d,dict(type='radial',center=[8,10],angle=19,zoom=.125,samples=3))
        d['items'][0]['filters'].append(dict(id='blur',operator=dict(type='gaussian',sigma=.5),border='reflect'))
        group=dict(id='group',content=dict(type='group',isolated=True),filters=[dict(id='outer',operator=dict(type='radial',center=[128,120],angle=-7,zoom=.125,samples=3),border='reflect')])
        clipped=rect('clipped',x=118,y=115,w=20,h=25,color=[40,210,70,177],parent='group',clip_to='source')
        clipped['filters']=[dict(id='twist',operator=family.creative(type='twist',center=[128,122],radius=20,angle=70))]
        d['items'].insert(0,group);d['items'].append(clipped);original=copy.deepcopy(d)
        for options in [dict(),dict(padding=3,crop_to_canvas=False)]:
            with self.subTest(options=options):
                self.assertEqual(self.samples(d,True,**options),self.samples(d,False,**options))
        self.assertEqual(d,original)
        self.assertEqual(self.samples(d,True,padding=3,antialias='supersample2'),
                         self.samples(d,False,padding=3,antialias='supersample2'))
        # Increase actual filter work beyond the larger tiled budget.
        expensive=copy.deepcopy(d)
        for item in expensive['items'][:2]:
            item['filters'][0]['operator']['samples']=129
        error=self.cli('document.export',document=expensive,format='png',render_options=dict(evaluation='tiled',padding=3,antialias='supersample2'),error='RESOURCE_LIMIT')
        self.assertIn('work',error['message'])
        d['width']=139
        self.assertEqual(self.samples(d,True,padding=3,antialias='supersample2'),
                         self.samples(d,False,padding=3,antialias='supersample2'))

    def test_native_two_megapixel_radial_edit_and_historical_channels(self):
        row=workload.run(family.measure.Case(EXE,self.root/'workload',workload.CASE,1))
        self.assertTrue(row['success'],row)
        self.assertEqual(row['process_calls'],7);self.assertEqual(row['blocked_steps'],0)

    def test_clipped_base_effects_masked_twist_and_knockout_keep_source_dependencies(self):
        # Base effects run after clipped siblings. Their source footprint must
        # pass through the sibling's nonlocal filter before reading its pixels.
        for knockout in (False,True):
            d=effects.TiledEffectTests.scene(self,knockout)
            clipped=next(item for item in d['items'] if item['id']=='clipped')
            clipped['filters']=[dict(id='twist',operator=family.creative(
                type='twist',center=[128,127],radius=12,angle=-43),border='reflect',opacity=.625,
                mask=dict(width=2,height=1,gray_hex='60d0',linked=False,transform=[12,0,0,30,112,113]))]
            original=copy.deepcopy(d)
            self.assertEqual(self.samples(d),self.samples(d,False))
            self.assertEqual(d,original)

    def test_agent_capabilities_and_nonlocal_exports_match_cli(self):
        client=Client(workspace=self.root);self.addCleanup(client.close);client.initialize()
        capability=client.success('capabilities')['render_quality']['evaluation']['tiled_filters']
        self.assertTrue({'radial','creative.twist'} <= set(capability['operators']))
        self.assertEqual(capability['unsupported'],['wrap'])
        d,_=self.source()
        for operator in [radial(),family.creative(type='twist',center=[66,4],radius=55,angle=-137)]:
            self.filter(d,operator,'reflect')
            args=dict(document=d,format='png',render_options=dict(evaluation='tiled'))
            self.assertEqual(client.success('document.export',**args),self.cli('document.export',**args))

    def test_integer_workload_oracle_matches_direct_rational_patch_sampling(self):
        w,h=131,130
        for patched in (False,True):
            result=workload.reference(w,h,patched)
            for x,y in [(0,0),(130,129),(65,65),(126,127),(127,127),(128,128),(129,128)]:
                total=[F(0)]*3
                for t in (-F(1,2),F(0),F(1,2)):
                    px=F(x)+(F(x)-F(w-1,2))*t/256
                    py=F(y)+(F(y)-F(h-1,2))*t/256
                    ix,iy=px//1,py//1;fx,fy=px-ix,py-iy
                    for dx,wx in [(0,1-fx),(1,fx)]:
                        for dy,wy in [(0,1-fy),(1,fy)]:
                            xx=min(w-1,max(0,ix+dx));yy=min(h-1,max(0,iy+dy))
                            p=workload.PATCH if patched and xx in (127,128) and yy in (127,128) else workload.pixel(xx,yy)
                            for c in range(3):total[c]+=p[c]*wx*wy/3
                expected=tuple(int(v+F(1,2)) for v in total)+(65535,)
                self.assertEqual(struct.unpack_from('<4H',result,(y*w+x)*8),expected)

    def test_short_native_strips_recheck_nonlocal_regions(self):
        item=dict(id='source',transform=[18000,0,0,8,0,0],content=dict(type='raster',
            width=1,height=3,rgba_hex='ff0000ff00ff00ff0000ffff',sampling='nearest'),
            filters=[dict(id='radial',operator=dict(type='radial',center=[.5,1.5],angle=0,zoom=1/4096,samples=3),border='clamp')])
        d=self.document([item],18000,24,'raster')
        a=self.cli('document.export',document=d,format='tiff',scale=2,
            image_options=dict(depth='f32',channels='rgba',compression='none'),render_options=dict(evaluation='tiled'))
        data=base64.b64decode(a['data']);tags=tiff_tags(data)
        self.assertGreater(len(tags[273]),1);self.assertLess(tags[278][0],128)
        y=0;row_bytes=36000*16
        for offset,count in zip(tags[273],tags[279]):
            for at in range(offset,offset+count,row_bytes):
                rgb=[F(0)]*3
                for t in (-F(1,2),F(0),F(1,2)):
                    pos=F(y)+(F(y)-F(47,2))*t/4096;iy=pos//1;fraction=pos-iy
                    for yy,weight in [(iy,1-fraction),(iy+1,fraction)]:
                        rgb[min(47,max(0,yy))//16]+=weight/3
                self.assertEqual(data[at:at+row_bytes],struct.pack('<4f',*map(float,rgb),1)*36000)
                y+=1
        self.assertEqual(y,48)

    def test_spatial_index_uses_the_complete_source_neighborhood(self):
        d,_=self.source(17,19);d.update(width=139,height=141,resource_profile='large_raster')
        d['items'][0]['transform']=[1,0,0,1,119,115]
        self.filter(d,dict(type='radial',center=[8,10],angle=45,zoom=.25,samples=3))
        expected=self.samples(d,False)
        d['items'].extend(rect(f'outside-{i}',x=900+i,y=900,w=1,h=1) for i in range(128))
        self.assertEqual(self.samples(d),expected)

    def test_disabled_nonlocal_controls_do_not_expand_the_render(self):
        d,_=self.source();expected=self.pixels(d)
        for op in [dict(type='radial',center=[32768,32768],angle=180,samples=129),
                   family.creative(type='twist',center=[0,0],radius=32768,angle=360000)]:
            for fields in [dict(enabled=False),dict(opacity=0)]:
                self.filter(d,op,**fields);self.assertEqual(self.pixels(d),expected)

    def test_work_limits_wrap_and_cancellation_never_publish(self):
        d=self.document([rect(w=1920,h=1080)],1920,1080)
        output=dict(file_name='failed.png',format='png',render_options=dict(evaluation='tiled'))
        self.filter(d,dict(type='radial',center=[960,540],angle=180,samples=129))
        self.cli('document.publish',document=d,output=output,error='RESOURCE_LIMIT')
        self.assertFalse((self.root/'failed.png').exists())
        self.filter(d,radial(),'wrap')
        self.cli('document.publish',document=d,output=output,error='UNSUPPORTED_TILED_RENDER')
        self.assertFalse((self.root/'failed.png').exists())
        self.filter(d,radial())
        self.cli('document.publish',document=d,output=output,control=dict(timeout_ms=0),error='TIMEOUT')
        self.assertFalse((self.root/'failed.png').exists())


if __name__=='__main__':unittest.main()
