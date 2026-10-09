"""Indexed mixed scenes retain exact output, topology and source identities."""
import base64
import copy
import json
import unittest
import test_agent_workspace as workspace
import test_tiled_render as tiled
import test_workload_measurement as workload
import test_samples_cli as samples
import test_layer_clipping_cli as clipping
import test_pixel_warps_cli as warps
from synthetic_font import geometric_font
from test_images_cli import png
from test_editing_cli import png_pixels
from test_render_quality_cli import rect
from test_cli import EXE,ROOT


class SpatialRenderTests(unittest.TestCase):
    setUp=workspace.AgentWorkspaceTests.setUp
    cli=workspace.AgentWorkspaceTests.cli
    document=tiled.TiledRenderTests.document
    exported=tiled.TiledRenderTests.exported
    pixels=tiled.TiledRenderTests.pixels

    def field(self,kind='vector'):
        if kind=='raster':
            return [clipping.layer(f'r{i}',[[30+i,90,150,173]],transform=[1.25,0,0,2.5,i%20*3,i//20*4]) for i in range(140)]
        return [rect(f'r{i}',x=i%20*3,y=i//20*4,w=1.25,h=2.5,color=[30+i,90,150,173]) for i in range(140)]

    def test_original_mixed_5001_case_passes_every_pixel(self):
        row=workload.measure.run_case(workload.measure.Case(EXE,self.root/'mixed','mixed-5001',1))
        self.assertTrue(row['success'],row)
        self.assertEqual(row['blocked_steps'],0)

    def test_groups_masks_clipping_and_knockout_preserve_composition(self):
        for isolated,knockout in [(True,False),(False,False),(True,True),(False,True)]:
            items=self.field('raster')+[
                clipping.layer('base',[[80,120,190,128],[30,170,90,255]],parent='g',transform=[7,0,0,10,0,0]),
                clipping.layer('texture',[[190,80,30,255],[40,90,230,127]],parent='g',clip_to='base',blend='multiply',transform=[7,0,0,10,0,0]),
                dict(id='grade',parent='g',content=dict(type='adjustment',adjustment=dict(clip_to='texture',operators=[dict(type='exposure',stops=-1)]))),
                # A separate sibling outside most tiles must still terminate the clipping run.
                clipping.layer('end',[[30,100,210,255]],parent='g',transform=[1,0,0,1,32,20]),
                dict(id='g',transform=[1,.125,.125,1,17.25,3.5],opacity=.625,
                     mask=dict(width=2,height=1,gray_hex='b0e0',transform=[20,0,0,20,0,0]),
                     content=dict(type='group',isolated=isolated,knockout=knockout))]
            d=self.document(items,64,32,'raster');before=copy.deepcopy(d)
            for antialias in ['none','coverage','supersample2']:
                for padding in [0,3]:
                    a=self.pixels(d,True,antialias=antialias,padding=padding)[2]
                    b=self.pixels(d,False,antialias=antialias,padding=padding)[2]
                    self.assertEqual(a,b)
            self.assertEqual(d,before)

    def test_native_strips_and_revised_item_rebuild_spatial_membership(self):
        source=samples.layer([10001,20002,30003,65535]*4,w=2,transform=[12,0,0,12,7.25,5.5])
        d=self.document(self.field('raster')+[source],64,32,'raster')
        def artifact(doc,evaluation):
            return self.cli('document.export',document=doc,format='tiff',image_options=dict(depth='u16',compression='deflate'),render_options=dict(evaluation=evaluation,padding=3))
        a=artifact(d,'tiled');b=artifact(d,'whole')
        self.assertEqual(samples.decode(a)[0],samples.decode(b)[0])
        saved=self.cli('session.create',session_id='s',request_id='create',document=d,response_mode='compact')['document_ref']
        before=self.pixels(saved)[2]
        changed=self.cli('session.apply',session_id='s',expected_revision=0,request_id='move',response_mode='compact',action=dict(type='edit',operations=[dict(op='transform',id='source',matrix=[12,0,0,12,39.25,5.5])]))
        current=changed['document_ref']
        self.assertNotEqual(self.pixels(current)[2],before)
        self.assertEqual(self.pixels(saved)[2],before)
        self.assertEqual(self.pixels(current)[2],self.pixels(current,False)[2])
        self.cli('session.verify',session_id='s')

    def test_text_curved_strokes_cropped_images_and_warps_have_conservative_bounds(self):
        (self.root/'font.ttf').write_bytes(geometric_font())
        (self.root/'LICENSE.txt').write_bytes((ROOT/'LICENSE').read_bytes())
        font=self.cli('font.import',source_path='font.ttf',license_path='LICENSE.txt')
        (self.root/'image.png').write_bytes(png(8,8,warps.chart()))
        asset=self.cli('asset.import',source_path='image.png')['asset']
        curve=rect('curve');curve['content']['geometry']=dict(shape='ellipse',cx=22.375,cy=13.25,rx=9.75,ry=4.625)
        curve['content']['stroke']=dict(width=1.75,color=[240,30,100,173])
        d=self.document(self.field()+[curve],64,32)
        d['fonts']={'geometry':font};d['assets']={'image':asset}
        d['items'] += [dict(id='text',transform=[1,.125,-.125,1,30.25,11.5],content=dict(type='text',frame=dict(text='AB',width=25,height=20,style=dict(font_id='geometry',size=10,fill=[25,100,200,255])))),
                       dict(id='image',transform=[2,.125,.125,1.5,39.25,7.5],content=dict(type='image',asset_id='image',width=8,height=8,crop=dict(x=2,y=1,width=4,height=4),sampling='bicubic'))]
        for aa in ['coverage','supersample2']:
            self.assertEqual(self.pixels(d,True,antialias=aa)[2],self.pixels(d,False,antialias=aa)[2])
        item=clipping.layer('warp',[list(warps.chart()[i:i+4]) for i in range(0,256,4)],width=8,
                            transform=[2,.125,.25,1.5,17.25,7.5],pixel_warp=warps.mesh())
        d=self.document(self.field('raster')+[item],64,32,'raster')
        self.assertEqual(self.pixels(d)[2],self.pixels(d,False)[2])

    def test_dense_scene_still_fails_and_failed_export_preserves_source(self):
        d=self.document([rect(f'p{i}',w=512,h=512) for i in range(140)],512,512)
        before=copy.deepcopy(d)
        self.cli('document.export',document=d,format='png',render_options=dict(evaluation='tiled'),error='RESOURCE_LIMIT')
        self.assertEqual(d,before)

    def test_curved_and_retained_compound_clips_preserve_coverage(self):
        ellipse=dict(shape='ellipse',cx=23.375,cy=16.25,rx=17.5,ry=9.75)
        hole=dict(shape='rect',x=20.25,y=9.5,width=8.5,height=7.25)
        compound=dict(shape='compound',mode='difference',operands=[dict(geometry=ellipse),dict(geometry=hole)])
        for geometry in [ellipse,compound]:
            item=rect('clipped',w=60,h=30,color=[170,90,200,213])
            item['clip']=dict(geometry=geometry,transform=[1,.125,-.125,1,1.75,-.5])
            d=self.document(self.field()+[item],64,32)
            for aa in ['none','coverage','supersample2']:
                self.assertEqual(self.pixels(d,True,antialias=aa,padding=3)[2],
                                 self.pixels(d,False,antialias=aa,padding=3)[2])


if __name__=='__main__':unittest.main()
