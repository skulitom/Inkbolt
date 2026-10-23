"""Larger native edit windows checked against independent pixel calculations."""
import copy
from contextlib import closing
import math
import struct
import unittest

import test_native_retouch as native
import test_pixel_brush_cli as brush
from test_mcp import Client
from test_sample_conversion_cli import tiff


def coverage(center, diameter, x, y):
    radius = diameter / 2
    dx, dy = abs(x + .5 - center[0]), abs(y + .5 - center[1])
    if (dx + .5)**2 + (dy + .5)**2 <= radius**2:
        return 1.0
    if max(0, dx - .5)**2 + max(0, dy - .5)**2 >= radius**2:
        return 0.0
    return brush.kernel_area(center, diameter, 1, x, y)


class LargeEditWindowTests(unittest.TestCase):
    setUp = native.NativeRetouchTests.setUp
    cli = native.NativeRetouchTests.cli
    raw = native.NativeRetouchTests.raw
    files = native.NativeRetouchTests.files
    save = native.NativeRetouchTests.save

    def imported(self, width, height, values, depth='u16', channels=4):
        path = self.root / f'original-{len(list(self.root.glob("original-*")))}.tiff'
        data = tiff(width, height, values, depth=depth, n=channels)
        path.write_bytes(data)
        result = self.cli('sample.import', source_path=str(path), id='large-window',
                          color_policy='assume_srgb', storage=dict(storage_version=2))
        self.assertEqual(path.read_bytes(), data)
        return result['document']

    def edit(self, document, operations, **kwargs):
        return self.cli('document.edit', document=document,
                        expected_revision=document['revision'], operations=operations, **kwargs)

    def preserved(self, before):
        after = self.files()
        for name, digest in before.items():
            self.assertEqual(after[name], digest, name)

    def test_maximum_brush_window_all_six_formats_against_circle_integral(self):
        weights = [coverage([256, 256], 512, x, y) for y in range(512) for x in range(512)]
        for depth in ['u8', 'u16', 'f32']:
            maximum = dict(u8=255, u16=65535, f32=1)[depth]
            for channels in [2, 4]:
                with self.subTest(depth=depth, channels=channels):
                    original = [0] * (channels - 1) + [maximum]
                    document = self.imported(512, 512, original * (512*512), depth, channels)
                    before = self.files()
                    operation = dict(op='brush_stroke', id='pixels', stroke=brush.brush(
                        [[256, 256]], diameter=512, mode=dict(type='paint', color=[255]*4)))
                    result = self.edit(document, [operation])
                    details = result['changes'][0]['details']
                    self.assertEqual(details['working_window'], [0, 0, 512, 512])
                    self.assertGreater(details['changed_pixels'], 65536)
                    self.assertLessEqual(details['processing_memory_bound_bytes'], 128*1024*1024)
                    raw = self.raw(result['document'])
                    actual = struct.iter_unpack('<' + dict(u8='B', u16='H', f32='f')[depth]*channels, raw)
                    for values, weight in zip(actual, weights):
                        wanted = weight * maximum
                        if depth != 'f32':
                            wanted = math.floor(wanted + .5)
                        tolerance = 2e-7 if depth == 'f32' else 1
                        self.assertEqual(values[-1], maximum)
                        for value in values[:-1]:
                            self.assertLessEqual(abs(value-wanted), tolerance)
                            if weight in (0, 1):
                                self.assertEqual(value, wanted)
                    self.assertEqual(self.raw(document), struct.pack('<'+dict(u8='B',u16='H',f32='f')[depth]*channels, *original)*(512*512))
                    self.preserved(before)

    def test_unaligned_large_brush_modes_keep_frozen_sampling_and_final_opacity(self):
        width, height = 515, 323
        values = [(x*73 % 50000, y*101 % 50000, (x+y)*41 % 50000, 60000)
                  for y in range(height) for x in range(width)]
        document = self.imported(width, height, [c for pixel in values for c in pixel])
        centers = [[65.5,65.5],[449.5,257.5]]
        weights = [[(x,y,coverage(center,128,x,y)) for y in range(1,height,64)
                    for x in range(1,width,64) if coverage(center,128,x,y)>0] for center in centers]
        original_pm = lambda x,y: [v/65535*60000/65535 for v in values[y*width+x][:3]]+[60000/65535]
        color = brush.pm([30,100,210,128])
        for mode in [dict(type='paint',color=[30,100,210,128]), dict(type='erase'),
                     dict(type='mixer',color=[30,100,210,128],pickup=.5,load=.25),
                     dict(type='smudge',border='clamp')]:
            with self.subTest(mode=mode):
                surface = {}
                reservoir = color[:]
                for dab, selected in enumerate(weights):
                    frozen = surface.copy()
                    get = lambda x,y: frozen.get((x,y),original_pm(x,y))
                    total = sum(w for x,y,w in selected)
                    if mode['type']=='mixer':
                        picked = [sum(get(x,y)[k]*w for x,y,w in selected)/total for k in range(4)]
                        reservoir = brush.lerp(brush.lerp(reservoir,color,.25),picked,.5)
                    for x,y,weight in selected:
                        before = get(x,y)
                        a = weight*.5
                        if mode['type']=='paint': after=brush.over(before,color,a)
                        elif mode['type']=='erase': after=[v*(1-a) for v in before]
                        elif mode['type']=='mixer': after=brush.over(before,reservoir,a)
                        elif dab:
                            after=brush.lerp(before,get(x-384,y-192),a)
                        else: after=before
                        surface[x,y]=after
                operation = dict(op='brush_stroke',id='pixels',stroke=brush.brush(centers,
                    diameter=128,spacing=4,flow=.5,opacity=.5,mode=mode,
                    texture=dict(width=64,height=64,gray_hex=bytes(255 if i==65 else 0 for i in range(4096)).hex())))
                result=self.edit(document,[operation]);expected=bytearray(self.raw(document))
                for (x,y),pixel in surface.items():
                    pm=brush.lerp(original_pm(x,y),pixel,.5)
                    encoded=[int(v/pm[3]*65535+.5) for v in pm[:3]]+[int(pm[3]*65535+.5)]
                    offset=(y*width+x)*8;expected[offset:offset+8]=struct.pack('<4H',*encoded)
                actual=self.raw(result['document'])
                self.assertEqual(actual,expected)
                self.assertEqual(result['changes'][0]['details']['working_window'],[1,1,513,321])

    def test_maximum_retouch_clone_all_six_formats_uses_original_overlapping_source(self):
        width,height=514,258
        for depth in ['u8','u16','f32']:
            maximum=dict(u8=255,u16=65535,f32=1)[depth]
            for channels in [2,4]:
                with self.subTest(depth=depth,channels=channels):
                    values=[v for y in range(height) for x in range(width)
                            for v in [((x+y+c)%8)/8*maximum if depth=='f32' else (x+y+c)%128
                                      for c in range(channels-1)]+[maximum]]
                    document=self.imported(width,height,values,depth,channels)
                    original=self.raw(document);stride=channels*dict(u8=1,u16=2,f32=4)[depth]
                    expected=bytearray(original)
                    for y in range(1,257):
                        start=(y*width+1)*stride
                        expected[start:start+512*stride]=original[start-stride:start+511*stride]
                    operation=dict(op='retouch',id='pixels',options=dict(source_id='pixels',
                        region=dict(x=1,y=1,width=512,height=256),source_transform=[1,0,0,1,-1,0],
                        sampling='nearest',mode=dict(type='clone')))
                    before=self.files();result=self.edit(document,[operation])
                    self.assertEqual(self.raw(result['document']),expected)
                    self.assertEqual(self.raw(document),original);self.preserved(before)
                    details=result['changes'][0]['details']
                    self.assertEqual(details['region_pixels'],131072)
                    self.assertEqual(details['working_window'],[0,0,514,258])

    def test_maximum_heal_window_and_mcp_proposal_retry_history_are_atomic(self):
        width,height=514,258
        color=[12000,24000,36000,65535]
        values=[c for y in range(height) for x in range(width)
                for c in (color if x in (0,513) or y in (0,257) else [3000,6000,9000,65535])]
        document=self.imported(width,height,values)
        source=self.imported(width,height,color*(width*height))['items'][0]
        source['id']='source';source['visible']=False;document['items'].append(source)
        original=self.raw(document);self.save(document)
        action=dict(type='edit',operations=[dict(op='retouch',id='pixels',options=dict(
            source_id='source',region=dict(x=1,y=1,width=512,height=256),mode=dict(type='heal')))])
        before=self.files()
        self.cli('session.apply',session_id='work',request_id='failed',expected_revision=0,
                 action=dict(type='edit',operations=action['operations']+[dict(op='remove',id='missing')]),error='NOT_FOUND')
        self.assertEqual(self.files(),before)
        with closing(Client(('--tools','core'),workspace=self.root)) as client:
            client.initialize()
            proposal=client.success('session.dry_run',session_id='work',request_id='heal',expected_revision=0,
                                    action=action)
            self.assertEqual(self.files(),before)
            saved=client.success('session.apply_proposal',proposal=proposal['proposal'],action=action)
            expected=struct.pack('<4H',*color)*(width*height)
            self.assertEqual(self.raw(saved['document']),expected)
            self.assertEqual(saved['receipt'],proposal['predicted_receipt'])
            self.assertTrue(client.success('session.apply_proposal',proposal=proposal['proposal'],action=action)['replayed'])
            undone=client.success('session.apply',session_id='work',request_id='undo',expected_revision=1,action=dict(type='undo'))
            self.assertEqual(self.raw(undone['document']),original)
            redone=client.success('session.apply',session_id='work',request_id='redo',expected_revision=2,action=dict(type='redo'))
            self.assertEqual(self.raw(redone['document']),expected)
        self.assertEqual(self.raw(document),original)

    def test_oversized_and_legacy_windows_fail_without_publishing_blocks(self):
        document=self.imported(514,514,[0,0,0,65535]*(514*514))
        operations=[dict(op='brush_stroke',id='pixels',stroke=brush.brush([[256.5,256.5]],diameter=512)),
                    dict(op='retouch',id='pixels',options=dict(source_id='pixels',region=dict(x=0,y=0,width=513,height=256),mode=dict(type='clone')))]
        for operation in operations:
            before=self.files();self.edit(document,[operation],error='RESOURCE_LIMIT')
            self.assertEqual(self.files(),before)
        legacy=copy.deepcopy(document);legacy['items'][0]['content']['grid']['storage_version']=1
        operations[0]['stroke']['points']=[dict(point=[256,256])]
        operations[1]['options']['region']['width']=512
        for operation in operations:
            before=self.files();self.edit(legacy,[operation],error='RESOURCE_LIMIT')
            self.assertEqual(self.files(),before)

    def test_large_heal_domain_has_independent_nonzero_screened_solution(self):
        width,height=514,258
        selected=lambda x,y: 1<=x<=512 and 1<=y<=256 and (x+y)%2==0
        values=[c for y in range(height) for x in range(width)
                for c in [30000 if selected(x,y) else 20000]*3+[65535]]
        document=self.imported(width,height,values)
        source=self.imported(width,height,[10000,10000,10000,65535]*(width*height))['items'][0]
        source['id']='source';source['visible']=False;document['items'].append(source)
        gray=bytes(255 if selected(x,y) else 0 for y in range(1,257) for x in range(1,513))
        operation=dict(op='retouch',id='pixels',options=dict(source_id='source',
            region=dict(x=1,y=1,width=512,height=256,gray_hex=gray.hex()),
            mode=dict(type='heal',screening=4,tolerance=1e-12)))
        result=self.edit(document,[operation])
        # Every selected cell has four fixed neighbors. The independent system
        # is diagonal: (4+4)*correction = 4*(20000-10000), so output is 15000.
        expected=b''.join(struct.pack('<4H',*([15000 if selected(x,y) else 20000]*3+[65535]))
                          for y in range(height) for x in range(width))
        self.assertEqual(self.raw(result['document']),expected)
        self.assertEqual(result['changes'][0]['details']['solver_iterations'],[1,1,1,0])

    def test_large_window_memory_admission_and_cancellation_are_atomic(self):
        document=self.imported(512,512,[0,0,0,65535]*(512*512))
        cancel=self.root/'cancel';cancel.write_text('cancel')
        operation=dict(op='brush_stroke',id='pixels',stroke=brush.brush([[256,256]],diameter=512))
        before=self.files()
        self.edit(document,[operation],control=dict(cancel_file=str(cancel)),error='CANCELLED')
        self.assertEqual(self.files(),before)
        # An extremely thin window intersects many complete native blocks.
        # Admission must reject their real memory cost before missing-block I/O.
        fake=copy.deepcopy(document);grid=fake['items'][0]['content']['grid']
        width,height=256,32768;spec=dict(width=width,height=height,depth='f32',channels='rgba',encoding='encoded_srgb')
        import hashlib
        tiles=['0'*64]*512
        header=b'INKTILE1'+struct.pack('<IIBBBB',width,height,4,4,0,0)
        identity=hashlib.sha256(b'INKGRID1'+header+struct.pack('<I',128)+bytes(32)*len(tiles)).hexdigest()
        grid['base']=dict(version=1,spec=spec,tiles=tiles,sha256=identity)
        fake['width']=width;fake['height']=height;fake['resource_profile']='large_raster'
        stroke=brush.brush([[128,1.5],[128,height-2.5]],diameter=1,spacing=4)
        error=self.edit(fake,[dict(op='brush_stroke',id='pixels',stroke=stroke)],error='RESOURCE_LIMIT')
        self.assertIn('memory bound',error['message'])
        options=dict(source_id='pixels',region=dict(x=127,y=0,width=2,height=height),mode=dict(type='clone'))
        error=self.edit(fake,[dict(op='retouch',id='pixels',options=options)],error='RESOURCE_LIMIT')
        self.assertIn('memory bound',error['message']);self.assertEqual(self.files(),before)


if __name__=='__main__': unittest.main()
