"""Independent decorated-alpha oracles and global/regional effect contracts."""
import base64
import copy
from fractions import Fraction as F
from pathlib import Path
import sys
import struct
import unittest
import test_agent_workspace as workspace
import test_effects_coverage_cli as basic
import test_extended_effects_cli as extended
import test_blending_cli as blending
import test_tiled_render as tiled
from test_cli import EXE
from test_render_quality_cli import rect
from test_samples_cli import decode
from test_sample_conversion_cli import tiff
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import workload_cases as measure
import native_shadow_workload as workload


def gradient(end=12):
    return dict(type='linear',start=[0,0],end=[end,0],stops=[dict(offset=0,color=[30,210,80,0]),dict(offset=1,color=[230,40,120,255])])


class TiledEffectTests(unittest.TestCase):
    setUp=workspace.AgentWorkspaceTests.setUp
    cli=workspace.AgentWorkspaceTests.cli
    document=tiled.TiledRenderTests.document
    exported=tiled.TiledRenderTests.exported
    pixels=tiled.TiledRenderTests.pixels
    matches=blending.BlendingTests.matches

    def test_native_two_megapixel_shadow_patch_and_historical_output(self):
        row=workload.run(measure.Case(EXE,self.root/'workload',workload.CASE,1))
        self.assertTrue(row['success'],row)
        self.assertEqual(row['process_calls'],7)
        self.assertEqual(row['blocked_steps'],0)

    def test_rational_shadow_stroke_overlay_across_tiles_and_real_viewport(self):
        w,h=137,3
        values=[[x%256,80,(x*19)%256,(0,73,255)[x%3]] for y in range(h) for x in range(w)]
        source=list(map(blending.premul,values))
        item=basic.layer('source',values,w,fill_opacity=.5)
        d=self.document([item],w,h,'raster')
        variants=[
            [basic.effect('s','shadow',[30,80,110,171],offset=[1,1],sigma=0)],
            [basic.effect('s','shadow',[30,80,110,171],offset=[-.5,.25],sigma=.4)],
            [basic.effect('s','lit_shadow',[30,80,110,171],distance=1,sigma=0,azimuth=90)],
            [basic.effect('s','stroke',[90,170,50,190],radius=1,position='outside')],
            [basic.effect('s','stroke',[90,170,50,190],radius=1,position='inside')],
            [dict(basic.effect('s','stroke',[90,170,50,190],radius=2,position='center'),scale=.5)],
            [dict(basic.effect('s','overlay',[170,90,20,193]),contour=[[0,0],[.5,.75],[1,.8]])],
        ]
        for fx in variants:
            d['items'][0]['effects']=fx
            expected=extended.evaluate(source,w,h,fx,fill=F(1,2))
            self.matches(self.pixels(d)[2],expected)
            self.assertEqual(self.pixels(d),self.pixels(d,False))

    def scene(self,knockout=False):
        group=dict(id='group',content=dict(type='group',isolated=True,knockout=knockout),
                   filters=[dict(id='blur',operator=dict(type='box',radius=1),border='clamp')],
                   effects=[basic.effect('parent','lit_shadow',gradient(137),distance=2,sigma=.3)])
        source=rect('source',w=9,h=11,color=[80,110,160,173],parent='group',fill_opacity=.375,
                    transform=[1.25,.1,-.05,1.1,123.5,121.25])
        source['effects']=[basic.effect('shift','shadow',gradient(),offset=[.5,-.75],sigma=.4),
                           dict(basic.effect('outline','stroke',gradient(),radius=1,position='center'),contour=[[0,0],[.5,.75],[1,1]]),
                           basic.effect('tint','overlay',gradient())]
        source['mask']=dict(width=2,height=1,gray_hex='70df',transform=[6,0,0,15,0,0])
        source['clip']=dict(geometry=dict(shape='rect',x=0,y=0,width=12,height=12))
        clipped=rect('clipped',x=120,y=125,w=18,h=4,color=[220,80,20,171],parent='group',clip_to='source')
        clipped['effects']=[basic.effect('glaze','overlay',gradient(137))]
        d=self.cli('document.create',id='scene',kind='raster',resource_profile='large_raster',width=137,height=137)
        d['items']=[rect('back',w=137,h=137,color=[40,70,190,127]),group,
            rect('under',x=121,y=120,w=12,h=15,color=[30,200,70,173],parent='group'),source,clipped]
        return self.cli('document.validate',document=d)

    def test_nested_filters_gradient_paints_masks_clips_lighting_and_sampling(self):
        d=self.scene();before=copy.deepcopy(d)
        for antialias,padding,crop in [('coverage',0,True),('supersample2',3,True),('coverage',3,False)]:
            options=dict(antialias=antialias,padding=padding,crop_to_canvas=crop)
            self.assertEqual(self.pixels(d,True,**options),self.pixels(d,False,**options))
        self.assertEqual(d,before)
        d['global_light']=dict(azimuth=90)
        self.assertEqual(self.pixels(d),self.pixels(d,False))
        self.assertNotEqual(self.pixels(d),self.pixels(before))

    def test_knockout_shapes_and_indexed_effect_sources_keep_global_alpha(self):
        d=self.scene(True)
        self.assertEqual(self.pixels(d),self.pixels(d,False))
        # Spatial selection must retain sources whose decorated output is inside
        # the tile but whose intrinsic geometry lies outside its interior.
        d['height']=19
        for item in d['items']:
            if item['id']=='source': item['transform'][5]-=120
            elif item['id'] in ('clipped','under'): item['content']['geometry']['y']-=120
        d['items'].extend(rect(f'off-{i}',x=900+i,y=900,w=1,h=1) for i in range(128))
        self.assertEqual(self.pixels(d),self.pixels(d,False))

    def test_native_precision_fractional_shadow_and_partial_tiff_bands(self):
        item=rect('source',x=126,y=125,w=3,h=9,color=[17,91,153,173])
        item['effects']=[basic.effect('s','shadow',[20,70,130,179],offset=[.25,1.5],sigma=.4),basic.effect('o','overlay',gradient(267))]
        d=self.document([item],267,267)
        for depth in ('u16','f32'):
            options=dict(depth=depth,channels='rgba',compression='none')
            a=self.cli('document.export',document=d,format='tiff',image_options=options,render_options=dict(evaluation='tiled'))
            b=self.cli('document.export',document=d,format='tiff',image_options=options)
            self.assertEqual(decode(a)[0],decode(b)[0])

    def test_effect_work_limits_and_cancellation_preserve_destination(self):
        item=rect('source',w=60,h=60)
        item['effects']=[basic.effect(f'fx-{i}','stroke',[10,20,30,255],radius=32) for i in range(8)]
        d=self.document([item],263,141)
        output=dict(file_name='blocked.tiff',format='tiff',image_options=dict(depth='u16'),render_options=dict(evaluation='tiled'))
        self.cli('document.publish',document=d,output=output,error='RESOURCE_LIMIT')
        self.assertFalse((self.root/'blocked.tiff').exists())
        d['items'][0]['effects']=[basic.effect('fx','overlay',[10,20,30,255])]
        self.cli('document.publish',document=d,output=output,control=dict(timeout_ms=0),error='TIMEOUT')
        self.assertFalse((self.root/'blocked.tiff').exists())
        d['items'][0]['effects'][0]['enabled']=False
        self.assertEqual(self.pixels(d),self.pixels(d,False))

    def test_native_oracle_admits_only_the_two_exact_half_neighbors(self):
        raw=bytearray(workload.source_pixels(3,2));struct.pack_into('<H',raw,21*2,59431)
        expected=workload.reference(raw,3,2)
        self.assertIn(21,expected[1])
        values=list(struct.unpack('<24H',expected[0]))
        path=self.root/'oracle.tiff'
        def save(v): path.write_bytes(tiff(3,2,v,tags={274:(3,[1])}))
        save(values);workload.check(path,expected,3,2)
        low=values.copy();low[21]-=1;save(low);workload.check(path,expected,3,2)
        for index,delta in [(21,1),(21,-2),(0,1),(3,-1)]:
            wrong=values.copy();wrong[index]+=delta;save(wrong)
            with self.assertRaises(AssertionError): workload.check(path,expected,3,2)


if __name__=='__main__': unittest.main()
