"""Bounded large-canvas reviews with independent pixels, units and source identity."""
import base64
import copy
import hashlib
from fractions import Fraction as F
from contextlib import closing
import json
import struct
import unittest
from advertised_limits import capabilities
import xml.etree.ElementTree as ET

import test_agent_workspace as workspace
from test_editing_cli import png_pixels
from test_mcp import Client
from test_mcp_preview import restore
from test_profiles_cli import embedded, linear_profile, png_profile
from pdf_reader import Pdf
from test_images_cli import canonical
from synthetic_font import geometric_font
from test_cli import ROOT


def rect(key, x, y, width, height, color, **kw):
    return dict(id=key, content=dict(type='vector', geometry=dict(shape='rect', x=x,
        y=y, width=width, height=height), fill=color), **kw)


def scene(size=10000, items=None):
    return dict(schema_version=2, id='overview-source', kind='vector', width=size,
        height=size, color_space='srgb', resolution_ppi=72, resource_profile='large_vector',
        vector_canvas=dict(origin_px=[0,0], size_px=[size,size], unit='pt'), items=items or [])


class VectorOverviews(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli
    save = workspace.AgentWorkspaceTests.save
    ref = workspace.AgentWorkspaceTests.ref

    def view(self, d, size=(100,100), **kw):
        return self.cli('document.preview', document=d, options=dict(max_size=list(size), **kw))

    def pixels(self, r):
        return png_pixels(base64.b64decode(r['artifact']['data']))[:3]

    def test_original_10000_square_precision_and_bounded_overview(self):
        d=scene(items=[rect('fractional',9990.125,.125,.375,.625,[255,0,0,255],
                           transform=[1,0,0,1,.000123,-.000321]),
                       rect('marker',4000,4000,1000,1000,[0,0,255,255])])
        before=copy.deepcopy(d)
        self.cli('document.preview',document=d,error='RESOURCE_LIMIT')
        result=self.view(d)
        w,h,p=self.pixels(result);self.assertEqual((w,h),(100,100))
        for y in range(h):
            for x in range(w):
                color=list(p[(y*w+x)*4:(y*w+x+1)*4])
                if 40<=x<50 and 40<=y<50:self.assertEqual(color,[0,0,255,255])
                elif not (x>=98 and y<2):self.assertEqual(color,[0,0,0,0])
        self.assertEqual(result['full_render']['evaluation_dimensions'],[100,100])
        self.assertEqual(result['mapping']['pixel_to_world'],[100,0,0,100,0,0])
        self.assertEqual(result['actual_bounds'],[0,0,10000,10000])
        validated=self.cli('document.validate',document=d)
        snapshot=self.cli('document.export',document=validated,format='snapshot')
        self.assertEqual(json.loads(snapshot['data']),validated)
        self.assertEqual(self.view(json.loads(snapshot['data'])),self.view(validated))
        self.assertEqual(d,before)

    def test_original_20000_square_retains_physical_page_and_exact_coarse_pixels(self):
        d=scene(20000,[rect('physical',1001.25,991.25,202.5,305,[255,0,0,255])])
        svg=ET.fromstring(self.cli('document.export',document=d,format='svg')['data'])
        self.assertEqual([svg.attrib[k] for k in ['width','height']],['20000pt','20000pt'])
        page=Pdf(self.cli('document.export',document=d,format='pdf')).pages[0]
        self.assertEqual([v*page['UserUnit'] for v in page['MediaBox']],[0,0,20000,20000])
        r=self.view(d,(200,200),render_options=dict(antialias='none'))
        w,h,p=self.pixels(r);self.assertEqual((w,h),(200,200))
        expected=bytes(c for y in range(h) for x in range(w) for c in
            ([255,0,0,255] if F('1001.25')<=100*x+50<F('1203.75')
             and F('991.25')<=100*y+50<F('1296.25') else [0,0,0,0]))
        self.assertEqual(p,expected)
        self.assertEqual(r['overview_scale'],.01)
        chunks=png_pixels(base64.b64decode(r['artifact']['data']))[3]
        self.assertEqual(struct.unpack('>IIB',chunks[b'pHYs']),(round(.72/.0254),)*2+(1,))
        self.assertFalse(r['source_changed'])

    def test_5000_distinct_editable_cells_preserve_every_overview_pixel(self):
        d=scene(10000,[rect('cell-'+str(i),100*(i%100),100*(i//100),100,100,
                           [i%100,i//100,73,255]) for i in range(5000)])
        r=self.view(d)
        w,h,p=self.pixels(r)
        expected=bytes(c for y in range(100) for x in range(100)
                       for c in ([x,y,73,255] if y<50 else [0,0,0,0]))
        self.assertEqual((w,h,p),(100,100,expected))
        self.assertEqual(len(d['items']),5000)
        self.assertEqual(d['items'][4999]['content']['geometry']['x'],9900)

    def test_nonzero_origin_aspect_ratio_fractional_edges_and_no_enlargement(self):
        d=scene(10240,[rect('full',-10,-10,11000,6000,[48,112,192,255])])
        d.update(height=5120,vector_canvas=dict(origin_px=[-.25,.5],size_px=[10240,5120],unit='pt'))
        r=self.view(d,(320,320));self.assertEqual(self.pixels(r),(320,160,bytes([48,112,192,255])*320*160))
        self.assertEqual(r['mapping']['pixel_to_world'],[32,0,0,32,-.25,.5])
        self.assertEqual(r['mapping']['world_to_pixel'],[1/32,0,0,1/32,.25/32,-.5/32])
        small=scene(4,[rect('full',0,0,4,4,[20,40,80,255])])
        self.assertEqual(self.pixels(self.view(small,(100,100))),(4,4,bytes([20,40,80,255])*16))
        small.update(vector_canvas=dict(origin_px=[0,0],size_px=[3.5,2.5],unit='pt'),height=3)
        r=self.view(small,(8,8));w,h,p=self.pixels(r);self.assertEqual((w,h),(4,3))
        self.assertEqual(list(p[-4:]),[20,40,80,64])

    def test_nested_groups_clips_opacity_and_both_scalar_mask_spaces(self):
        base=rect('base',0,0,100,100,[0,0,255,255])
        g=dict(id='g',transform=[1,0,0,1,20,20],opacity=.5,content=dict(type='group'))
        red=rect('red',0,0,60,60,[255,0,0,255],parent='g',
                 clip=dict(geometry=dict(shape='rect',x=0,y=0,width=40,height=40)),
                 mask=dict(width=2,height=1,gray_hex='ff00',transform=[20,0,0,40,0,0],linked=True))
        d=scene(100,[base,g,red]);before=copy.deepcopy(d)
        r=self.view(d,(10,10));w,h,p=self.pixels(r)
        expected=bytes(c for y in range(10) for x in range(10)
                       for c in ([128,0,128,255] if 2<=x<4 and 2<=y<6 else [0,0,255,255]))
        self.assertEqual((w,h,p),(10,10,expected))
        red['mask'].update(linked=False,transform=[20,0,0,40,20,20])
        self.assertEqual(self.pixels(self.view(d,(10,10))),(w,h,p))
        self.assertEqual(before['items'][1],g)

    def test_saved_mcp_profile_identity_contact_sheet_and_unchanged_history(self):
        d=scene(10000,[rect('full',0,0,10000,10000,[100,150,200,173])])
        profile=linear_profile();d['output_profile']=embedded(profile)
        self.save(d)
        old=self.cli('session.read',session_id='work')
        options=dict(max_size=[32,32]);r=self.view(self.ref(),(32,32))
        self.assertEqual(png_profile(base64.b64decode(r['artifact']['data'])),profile)
        with closing(Client(('--tools','core'),workspace=self.root)) as c:
            c.initialize();actual=c.tool('document.preview',document=self.ref(),options=options,response_format='preview')
            self.assertEqual(restore(actual),dict(ok=True,result=r))
            self.assertEqual(len(actual['content']),2)
        sheet=self.cli('document.contact_sheet',document=self.ref(),options=dict(views=[options,options],columns=2,cell_size=[32,32],gap=0))
        self.assertEqual(sheet['evaluation_pixels'],2048)
        self.assertEqual(sheet['views'][1]['sheet_to_world'],[312.5,0,0,312.5,-10000,0])
        self.assertEqual(self.cli('session.read',session_id='work'),old)

    def test_original_font_and_image_keep_local_samples_and_source_files(self):
        font_bytes=geometric_font();source=self.root/'original.ttf';source.write_bytes(font_bytes)
        license=self.root/'license.txt';license.write_bytes((ROOT/'LICENSE').read_bytes())
        font=self.cli('font.import',source_path='original.ttf',license_path='license.txt')
        rgba=bytes([255,0,0,255,0,0,255,255,0,255,0,255,0,0,0,0])
        asset=dict(width=2,height=2,sha256=hashlib.sha256(canonical(2,2,rgba)).hexdigest(),
                   storage=dict(type='embedded',rgba_hex=rgba.hex()))
        d=scene(items=[dict(id='label',transform=[1,0,0,1,1000,2000],
                content=dict(type='text',frame=dict(text='A',width=6000,height=5000,
                    style=dict(font_id='geometry',size=1000,fill=[25,100,200,255])))),
            dict(id='image',transform=[1000,0,0,1000,2000,1000],
                 content=dict(type='image',asset_id='checker',width=2,height=2,sampling='nearest'))])
        d.update(fonts=dict(geometry=font),assets=dict(checker=asset))
        before=copy.deepcopy(d);w,h,p=self.pixels(self.view(d))
        expected=bytearray(w*h*4)
        for y in range(100):
            for x in range(100):
                color=[0,0,0,0]
                if 21<=y<28 and 10<=x<15:color=[25,100,200,128 if x in [10,14] else 255]
                if 20<=x<40 and 10<=y<30:
                    index=((y-10)//10*2+(x-20)//10)*4;color=list(rgba[index:index+4])
                expected[(y*w+x)*4:(y*w+x+1)*4]=bytes(color)
        self.assertEqual(p,expected)
        self.assertEqual(source.read_bytes(),font_bytes);self.assertEqual(d,before)

    def test_object_stroke_gradient_frame_and_scene_marker_use_projected_geometry(self):
        line=dict(id='stroke',content=dict(type='vector',geometry=dict(shape='path',commands=[
            dict(verb='move',to=[1000,1000]),dict(verb='line',to=[5000,1000])]),fill=None,
            stroke=dict(width=200,color=[30,100,210,255],dash=dict(array=[1000,1000],offset=0))))
        frame=dict(id='frame',transform=[1,0,0,1,6000,1000],content=dict(type='frame',frame=dict(
            width=2000,height=2000,background=[30,60,90,255])))
        child=rect('child',1000,1000,2000,2000,[255,0,0,255],parent='frame')
        marker=dict(id='board',content=dict(type='frame',frame=dict(role='artboard',scope='scene',width=10000,height=10000)))
        gradient=rect('gradient',1000,5000,8000,1000,dict(type='linear',start=[1000,0],end=[9000,0],
            stops=[dict(offset=0,color=[0,0,0,255]),dict(offset=1,color=[255,255,255,255])]))
        d=scene(items=[line,frame,child,marker,gradient]);before=copy.deepcopy(d)
        w,h,p=self.pixels(self.view(d))
        for y in range(h):
            for x in range(w):
                expected=[0,0,0,0]
                if 9<=y<11 and (10<=x<20 or 30<=x<40):expected=[30,100,210,255]
                if 60<=x<80 and 10<=y<30:expected=[30,60,90,255]
                if 70<=x<80 and 20<=y<30:expected=[255,0,0,255]
                if 10<=x<90 and 50<=y<60:
                    shade=int(F(255)*(F(x)+F(1,2)-10)/80+F(1,2));expected=[shade]*3+[255]
                self.assertEqual(list(p[(y*w+x)*4:(y*w+x+1)*4]),expected,(x,y))
        self.assertEqual(d,before)

    def test_contact_sheet_admission_counts_overview_evaluation_before_font_reads(self):
        d=scene(items=[dict(id='label',content=dict(type='text',frame=dict(text='A',width=10,height=10,
            style=dict(font_id='missing',size=8,fill=[0,0,0,255]))))])
        d['fonts']={'missing':dict(sha256='a'*64,license_sha256='b'*64,face_index=0,bytes=100)}
        self.cli('document.contact_sheet',document=d,options=dict(views=[dict(max_size=[1024,1024])]*5),error='RESOURCE_LIMIT')

    def test_invalid_or_unsupported_overviews_fail_without_weakening_limits(self):
        d=scene()
        for options in [dict(max_size=[0,100]),dict(max_size=[capabilities()['focused_previews']['vector_overview']['axes'][1]+1,100]),dict(max_size=[100,100],scale=2),
                        dict(max_size=[100,100],focus=dict(type='region',bounds=[0,0,1,1])),
                        dict(max_size=[100,100],render_options=dict(padding=1)),
                        dict(max_size=[100,100],render_options=dict(crop_to_canvas=False)),
                        dict(max_size=[100,100],render_options=dict(evaluation='tiled'))]:
            self.cli('document.preview',document=d,options=options,error='INVALID_REQUEST')
        self.cli('document.preview',document=d,options=dict(max_size=[1024,1024],render_options=dict(antialias='supersample2')),error='RESOURCE_LIMIT')
        item=rect('hidden',0,0,10,10,[255,0,0,255],visible=False)
        item['content']['stroke']=dict(width=1,color=[0,0,0,255],scaling='document')
        self.cli('document.preview',document=scene(items=[item]),options=dict(max_size=[100,100]),error='UNSUPPORTED')
        item['content'].pop('stroke')
        item['filters']=[dict(id='blur',operator=dict(type='box',radius=1))]
        self.cli('document.preview',document=scene(items=[item]),options=dict(max_size=[100,100]),error='UNSUPPORTED')
        marker=self.root/'cancel';marker.write_text('owned')
        self.cli('document.preview',document=d,options=dict(max_size=[100,100]),control=dict(cancel_file='cancel'),error='CANCELLED')
        self.assertEqual(marker.read_text(),'owned')


if __name__=='__main__':unittest.main()
