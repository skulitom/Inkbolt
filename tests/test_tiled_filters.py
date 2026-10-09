"""Independent convolution and whole/regional boundary, mask and budget checks."""
import base64
import copy
from fractions import Fraction
from pathlib import Path
import sys
import struct
import unittest
import test_agent_workspace as workspace
import test_filters_cli as reference
import test_tiled_render as tiled
from test_cli import EXE
from test_render_quality_cli import rect
from test_samples_cli import decode
from test_image_io_cli import tiff_tags
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import measure_workloads as measure
import native_filter_workload as workload


class TiledFilterTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli
    document = tiled.TiledRenderTests.document
    exported = tiled.TiledRenderTests.exported
    pixels = tiled.TiledRenderTests.pixels

    def test_box_full_native_two_megapixel_edit_and_history(self):
        row = workload.run(measure.Case(EXE,self.root/'workload',workload.CASE,1))
        self.assertTrue(row['success'],row)
        self.assertEqual(row['process_calls'],7)
        self.assertEqual(row['blocked_steps'],0)

    def test_independent_alpha_convolution_across_tile_edges_and_viewport_borders(self):
        w,h = 137,3
        values = [(x%256,y*90,(x*17)%256,(0,71,255)[x%3]) for y in range(h) for x in range(w)]
        item = dict(id='source',content=dict(type='raster',width=w,height=h,rgba_hex=bytes(c for p in values for c in p).hex()))
        d=self.document([item],w,h,'raster')
        for border in ('transparent','clamp','reflect'):
            d['items'][0]['filters']=[dict(id='blur',operator=dict(type='box',radius=2),border=border)]
            expected=reference.convolution(reference.premult(values),w,h,[Fraction(1,5)]*5,border)
            expected=reference.unpremult(expected)
            actual=self.pixels(d)[2]
            wanted=bytes(min(255,max(0,int(v*255+Fraction(1,2)))) for v in expected)
            self.assertEqual(actual,wanted)

    def test_stacked_container_filters_masks_padding_supersampling_and_spatial_index(self):
        group=dict(id='parent',content=dict(type='group',isolated=True),filters=[dict(id='outer',operator=dict(type='gaussian',sigma=.5),border='reflect')])
        item=rect('source',x=123,y=60,w=14,h=18,color=[210,30,70,177],parent='parent')
        item['filters']=[dict(id='inner',operator=dict(type='box',radius=2),border='clamp'),dict(id='motion',operator=dict(type='directional',length=2.5,angle=27,samples=3),border='transparent')]
        item['filters'][0]['mask']=dict(width=2,height=1,gray_hex='50e0',transform=[12,0,0,30,115,50],linked=False)
        d=self.document([group,item],263,141)
        original=copy.deepcopy(d)
        for antialias,padding,crop in [('coverage',0,True),('supersample2',3,True),('coverage',3,False)]:
            options=dict(antialias=antialias,padding=padding,crop_to_canvas=crop)
            self.assertEqual(self.pixels(d,True,**options),self.pixels(d,False,**options))
        d['items'].extend(rect(f'outside-{i}',x=900+i,y=900,w=1,h=1) for i in range(128))
        self.assertEqual(self.pixels(d),self.pixels(d,False))
        self.assertEqual(d['items'][:2],original['items'])

    def test_surface_directional_and_native_depth_at_partial_edges(self):
        item=dict(id='source',content=dict(type='raster',width=3,height=2,rgba_hex=bytes([60,80,120,255,210,10,40,171,40,200,60,0]*2).hex()),transform=[8,0,0,9,124,119])
        d=self.document([item],267,139,'raster')
        for operator in [dict(type='surface',radius=1,threshold=.3),dict(type='directional',length=3.5,angle=87,samples=3),dict(type='gaussian',sigma=.6)]:
            d['items'][0]['filters']=[dict(id='filter',operator=operator,border='clamp')]
            for depth in ('u16','f32'):
                options=dict(depth=depth,channels='rgba',compression='none')
                a=self.cli('document.export',document=d,format='tiff',image_options=options,render_options=dict(evaluation='tiled'))
                b=self.cli('document.export',document=d,format='tiff',image_options=options)
                self.assertEqual(decode(a)[0],decode(b)[0])

    def test_short_native_codec_bands_preserve_all_filter_neighborhoods(self):
        # f32 strips must split below the usual composition tile height. Every
        # row crosses the same two-color boundary; the five taps are exact.
        group=dict(id='group',content=dict(type='group',isolated=True),filters=[dict(id='box',operator=dict(type='box',radius=1),border='clamp')])
        d=self.document([group,rect('left',w=9000,h=24,color=[255,0,0,255],parent='group'),rect('right',x=9000,w=9000,h=24,color=[0,0,255,255],parent='group')],18000,24)
        artifact=self.cli('document.export',document=d,format='tiff',scale=2,image_options=dict(depth='f32',channels='rgba',compression='none'),render_options=dict(evaluation='tiled'))
        data=base64.b64decode(artifact['data']);tags=tiff_tags(data)
        self.assertGreater(len(tags[273]),1)
        self.assertLess(tags[278][0],128)
        row=b''.join(struct.pack('<4f',sum(x+dx<18000 for dx in range(-2,3))/5,0,sum(x+dx>=18000 for dx in range(-2,3))/5,1) for x in range(36000))
        height=0
        for offset,count in zip(tags[273],tags[279]):
            rows=count//len(row)
            self.assertEqual(data[offset:offset+count],row*rows)
            height+=rows
        self.assertEqual(height,48)

    def test_unsupported_semantics_limits_cancellation_and_no_publication(self):
        item=rect('source',w=30,h=30)
        d=self.document([item],263,141)
        output=dict(file_name='failed.png',format='png',render_options=dict(evaluation='tiled'))
        for operator,border in [(dict(type='box',radius=1),'wrap'),(dict(type='radial',center=[1,1],angle=10),'clamp')]:
            d['items'][0]['filters']=[dict(id='filter',operator=operator,border=border,enabled=False)]
            self.cli('document.publish',document=d,output=output,error='UNSUPPORTED_TILED_RENDER')
            self.assertFalse((self.root/'failed.png').exists())
        d['items'][0]['filters']=[dict(id=f'blur-{i}',operator=dict(type='gaussian',sigma=16)) for i in range(8)]
        self.cli('document.publish',document=d,output=output,error='RESOURCE_LIMIT')
        self.assertFalse((self.root/'failed.png').exists())
        d['items'][0]['filters']=[dict(id='blur',operator=dict(type='box',radius=1))]
        self.cli('document.publish',document=d,output=output,control=dict(timeout_ms=0),error='TIMEOUT')
        self.assertFalse((self.root/'failed.png').exists())


if __name__ == '__main__': unittest.main()
