"""Independent filter samples plus complete whole/tiled coordinate equivalence."""
import base64
import copy
from fractions import Fraction as F
from pathlib import Path
import struct
import sys
import unittest

import test_agent_workspace as workspace
import test_tiled_render as tiled
import test_filters_cli as reference
from test_detail_spatial_cli import detail, spatial, seeded
from test_render_quality_cli import rect
from test_samples_cli import decode
from test_image_io_cli import tiff_tags
from test_cli import EXE
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import workload_cases as measure
import native_detail_workload as workload


def creative(**operator): return dict(type='creative',operator=operator)


def operators():
    return [detail(type='sharpen',amount=.625),detail(type='unsharp',sigma=.6,amount=1.5,threshold=.07),
        detail(type='median',radius=1),detail(type='noise',amount=.13,seed=79,monochrome=False),
        spatial(type='offset',offset=[-1.25,2.5]),spatial(type='mosaic',size=7),
        spatial(type='displace',amount=[2.5,-3.25],map=dict(width=2,height=2,
            vectors=[[-1,-1],[1,-1],[-1,1],[1,1]],transform=[30,0,0,20,101,117],sampling='bilinear')),
        creative(type='relief',angle=23,distance=2.25,strength=.7),creative(type='high_pass',sigma=.6),
        creative(type='extrema',radius=1,mode='minimum'),creative(type='extrema',radius=1,mode='maximum'),
        creative(type='tone_fold',threshold=.45),creative(type='edge_ink',strength=.8),
        creative(type='stroke_rank',radius=2,angle=27,quantile=.75),
        creative(type='value_field',seed=91,cell_size=7.25,octaves=2,origin=[-3,2],low=[20,70,130],high=[240,150,40]),
        creative(type='field_repair',keep_parity=0),creative(type='field_repair',keep_parity=1)]


class TiledFilterFamilyTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli
    document = tiled.TiledRenderTests.document
    exported = tiled.TiledRenderTests.exported
    pixels = tiled.TiledRenderTests.pixels

    def test_native_two_megapixel_detail_edit_and_historical_channels(self):
        row=workload.run(measure.Case(EXE,self.root/'workload',workload.CASE,1))
        self.assertTrue(row['success'],row)
        self.assertEqual(row['process_calls'],7)
        self.assertEqual(row['blocked_steps'],0)

    def test_integer_detail_oracle_clamps_borders_and_detects_a_local_change(self):
        raw=struct.pack('<12H',100,100,100,65535,200,200,200,65535,100,100,100,65535)
        expected=struct.pack('<12H',0,0,0,65535,400,400,400,65535,0,0,0,65535)
        self.assertEqual(workload.reference(raw,3,1),expected)
        changed=bytearray(raw);struct.pack_into('<H',changed,8,201)
        self.assertNotEqual(workload.reference(changed,3,1),expected)

    def source(self,w=137,h=9):
        values=[((17*x+11*y)%256,(31*x+7*y)%256,(13*x+43*y)%256,(0,71,179,255)[(x+3*y)%4])
                for y in range(h) for x in range(w)]
        item=dict(id='source',content=dict(type='raster',width=w,height=h,
                  rgba_hex=bytes(v for p in values for v in p).hex()))
        return self.document([item],w,h,'raster'),values

    def filter(self,d,operator,border='clamp',**fields):
        d['items'][0]['filters']=[dict(id='filter',operator=operator,border=border,**fields)]

    def assert_samples(self,d,expected):
        codes=[v*255 for v in reference.unpremult(expected)]
        wanted=bytearray(max(0,min(255,int(v+F(1,2)))) for v in codes)
        actual=self.pixels(d)[2]
        # Only an exact mathematical half-code admits either adjacent result
        # after the existing f64 filter composition; every other byte is exact.
        for i,v in enumerate(codes):
            if v%1==F(1,2) and actual[i]==wanted[i]-1:wanted[i]=actual[i]
        self.assertEqual(actual,bytes(wanted))

    def test_every_added_operator_preserves_native_depth_across_both_tile_axes(self):
        # A compact transformed source straddles both 128-pixel boundaries.
        d,_=self.source(17,19)
        d.update(width=141,height=143)
        d['items'][0]['transform']=[1,.125,.25,1,121,119]
        for operator in operators():
            for border in ('transparent','clamp','reflect'):
                with self.subTest(operator=operator,border=border):
                    self.filter(d,operator,border)
                    options=dict(depth='f32',channels='rgba',compression='none')
                    a=self.cli('document.export',document=d,format='tiff',image_options=options,
                               render_options=dict(evaluation='tiled'))
                    b=self.cli('document.export',document=d,format='tiff',image_options=options)
                    self.assertEqual(decode(a)[0],decode(b)[0])

    def test_sharpen_median_and_extrema_have_independent_alpha_neighborhoods(self):
        w,h=137,5
        d,values=self.source(w,h);source=reference.premult(values)
        for kind in ('sharpen','median','minimum','maximum'):
            for border in ('transparent','clamp','reflect'):
                operator=(detail(type='sharpen',amount=.5) if kind=='sharpen' else
                          detail(type='median',radius=1) if kind=='median' else
                          creative(type='extrema',radius=1,mode=kind))
                self.filter(d,operator,border);expected=[]
                for y in range(h):
                    for x in range(w):
                        p=source[y*w+x];alpha=p[3]
                        if not alpha:expected.append([F(0)]*4);continue
                        taps=((-1,0),(1,0),(0,-1),(0,1)) if kind=='sharpen' else tuple((a,b) for b in (-1,0,1) for a in (-1,0,1))
                        neighbors=[reference.fetch(source,w,h,x+dx,y+dy,border) for dx,dy in taps]
                        if kind=='sharpen':
                            average=[sum(q[c] for q in neighbors)/4 for c in range(4)]
                            color=[max(0,min(1,p[c]/alpha+F(1,2)*(p[c]/alpha-(average[c]/average[3] if average[3] else p[c]/alpha)))) for c in range(3)]
                        else:
                            channels=[[q[c]/q[3] for q in neighbors if q[3]] for c in range(3)]
                            color=[sorted(v)[len(v)//2] if kind=='median' else
                                   min(v) if kind=='minimum' else max(v) for v in channels]
                        expected.append([v*alpha for v in color]+[alpha])
                self.assert_samples(d,expected)

    def test_mosaic_and_field_repair_independent_global_cells_and_partial_edges(self):
        w,h=137,133
        d,values=self.source(w,h);source=reference.premult(values)
        self.filter(d,spatial(type='mosaic',size=7))
        expected=[[F(0)]*4 for _ in source]
        for y in range(0,h,7):
            for x in range(0,w,7):
                positions=[yy*w+xx for yy in range(y,min(h,y+7)) for xx in range(x,min(w,x+7))]
                average=[sum(source[i][c] for i in positions)/len(positions) for c in range(4)]
                for i in positions:expected[i]=average
        self.assert_samples(d,expected)
        for parity in (0,1):
            self.filter(d,creative(type='field_repair',keep_parity=parity))
            kept=list(range(parity,h,2));expected=[]
            for y in range(h):
                before=max(kept[0],y-1);after=min(kept[-1],y+1)
                for x in range(w):
                    expected.append(source[y*w+x] if y%2==parity else
                                    [(a+b)/2 for a,b in zip(source[before*w+x],source[after*w+x])])
            self.assert_samples(d,expected)

    def test_seeded_noise_uses_full_viewport_coordinates_across_tiles(self):
        w,h=137,5
        d,values=self.source(w,h)
        for distribution in ('uniform','gaussian'):
            for mono in (False,True):
                self.filter(d,detail(type='noise',amount=.125,seed=4294967295,
                                    distribution=distribution,monochrome=mono))
                expected=[]
                for i,p in enumerate(values):
                    alpha=F(p[3],255)
                    colors=[max(0,min(1,F(p[c],255)+F(1,8)*seeded(4294967295,i%w,i//w,0 if mono else c,distribution))) for c in range(3)]
                    expected.append([v*alpha for v in colors]+[alpha])
                self.assert_samples(d,expected)

    def test_stacks_masks_padding_supersampling_and_spatial_selection_keep_coordinates(self):
        d,_=self.source(17,19);d.update(width=137,height=139,resource_profile='large_raster')
        d['items'][0].update(transform=[1,.125,.25,1,115,116],parent='group')
        d['items'][0]['filters']=[dict(id='noise',operator=detail(type='noise',amount=.125,seed=63)),
            dict(id='cells',operator=spatial(type='mosaic',size=3),border='reflect',opacity=.7,
                 mask=dict(width=2,height=1,gray_hex='60d0',linked=False,transform=[12,0,0,30,112,113])),
            dict(id='shift',operator=spatial(type='offset',offset=[1.25,-.75]),border='clamp')]
        group=dict(id='group',content=dict(type='group',isolated=True),filters=[
            dict(id='rows',operator=creative(type='field_repair',keep_parity=1)),
            dict(id='detail',operator=detail(type='unsharp',sigma=.5,amount=.75))])
        d['items'].insert(0,group);original=copy.deepcopy(d)
        for antialias,padding,crop in [('coverage',0,True),('coverage',3,False),('supersample2',3,True)]:
            options=dict(antialias=antialias,padding=padding,crop_to_canvas=crop)
            self.assertEqual(self.pixels(d,True,**options),self.pixels(d,False,**options))
        self.assertEqual(d,original)
        d['items'].extend(rect(f'outside-{i}',x=900+i,y=900,w=1,h=1) for i in range(128))
        self.assertEqual(self.pixels(d),self.pixels(d,False))
        d['items'][0]['content']['knockout']=True
        d['items'].insert(2,rect('clipped',x=119,y=121,w=15,h=8,color=[210,70,20,179],
                                parent='group',clip_to='source'))
        # The off-canvas items select indexed composition. Whole evaluation's
        # conservative knockout budget includes them, so use the complete
        # visible three-item scene as its independently bounded reference.
        visible=copy.deepcopy(d)
        visible['items']=[item for item in visible['items'] if not item['id'].startswith('outside-')]
        self.assertEqual(self.pixels(d),self.pixels(visible,False))

    def test_short_native_strips_keep_full_viewport_row_parity(self):
        item=dict(id='source',transform=[18000,0,0,8,0,0],content=dict(type='raster',
            width=1,height=3,rgba_hex='ff0000ff00ff00ff0000ffff',sampling='nearest'),
            filters=[dict(id='rows',operator=creative(type='field_repair',keep_parity=1))])
        d=self.document([item],18000,24,'raster')
        artifact=self.cli('document.export',document=d,format='tiff',scale=2,
            image_options=dict(depth='f32',channels='rgba',compression='none'),
            render_options=dict(evaluation='tiled'))
        data=base64.b64decode(artifact['data']);tags=tiff_tags(data)
        self.assertGreater(len(tags[273]),1)
        self.assertLess(tags[278][0],128)
        y=0;row_bytes=36000*16
        for offset,count in zip(tags[273],tags[279]):
            for position in range(offset,offset+count,row_bytes):
                neighbors=[y] if y%2 else [max(1,y-1),min(47,y+1)]
                rgb=[sum(v//16==c for v in neighbors)/len(neighbors) for c in range(3)]
                self.assertEqual(data[position:position+row_bytes],struct.pack('<4f',*rgb,1)*36000)
                y+=1
        self.assertEqual(y,48)

    def test_nonlocal_unsupported_work_limits_and_cancel_never_publish(self):
        d=self.document([rect(w=16,h=16)],137,139)
        output=dict(file_name='failed.png',format='png',render_options=dict(evaluation='tiled'))
        for op,border in [(creative(type='twist',center=[5,5],radius=7,angle=30),'wrap'),
                          (dict(type='radial',center=[5,5],angle=10),'wrap'),
                          (detail(type='median',radius=1),'wrap')]:
            self.filter(d,op,border,enabled=False)
            self.cli('document.publish',document=d,output=output,error='UNSUPPORTED_TILED_RENDER')
            self.assertFalse((self.root/'failed.png').exists())
        d.update(width=1920,height=1080)
        self.filter(d,detail(type='noise',amount=.1,seed=3))
        self.cli('document.publish',document=d,output=output,error='RESOURCE_LIMIT')
        self.assertFalse((self.root/'failed.png').exists())
        self.filter(d,detail(type='sharpen',amount=.5))
        self.cli('document.publish',document=d,output=output,control=dict(timeout_ms=0),error='TIMEOUT')
        self.assertFalse((self.root/'failed.png').exists())


if __name__=='__main__':unittest.main()
