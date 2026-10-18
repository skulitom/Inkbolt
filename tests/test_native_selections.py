"""Native selection bytes, local consumers, private review and immutable history."""
import copy
import hashlib
import math
import struct
import unittest

import test_native_masks as masks
import test_native_mask_application as application
import test_pixel_brush_cli as brush
import test_repair_cli as repair
from test_mcp import Client
from contextlib import closing


class NativeSelectionTests(unittest.TestCase):
    setUp = masks.NativeMaskTests.setUp
    cli = masks.NativeMaskTests.cli
    save = masks.NativeMaskTests.save
    ref = masks.NativeMaskTests.ref
    files = masks.NativeMaskTests.files
    blocks = masks.NativeMaskTests.blocks
    mask = masks.NativeMaskTests.mask
    source = application.NativeMaskApplicationTests.source
    raw = application.NativeMaskApplicationTests.raw

    def document(self, w=133, h=131):
        return self.cli('document.create', id='selections', kind='raster', width=w, height=h)

    def edit(self, d, operations, **kw):
        return self.cli('document.edit', document=d, expected_revision=d['revision'], operations=operations, **kw)

    def values(self, selection):
        if 'native' not in selection:
            return bytes.fromhex(selection['gray_hex'])
        grid = selection['native']; manifest = grid['base']
        w, h = selection['width'], selection['height']
        pending = {p['sha256']: bytes.fromhex(p['data_hex']) for p in grid.get('staged', {}).get('pending', [])}
        result = bytearray(w*h)
        for i, digest in enumerate(manifest['tiles']):
            blob = pending[digest] if digest in pending else (self.root/'.inkbolt/assets'/(digest+'.native-tile')).read_bytes()
            self.assertEqual(hashlib.sha256(blob).hexdigest(), digest)
            self.assertEqual(blob[:8], b'INKSCAL1')
            tw, th = struct.unpack_from('<II', blob, 8)
            self.assertEqual(blob[16:20], bytes([1,1,0,0]))
            self.assertEqual(len(blob), 20+tw*th)
            left, top = i % math.ceil(w/128)*128, i // math.ceil(w/128)*128
            for y in range(th):
                result[(top+y)*w+left:(top+y)*w+left+tw] = blob[20+y*tw:20+(y+1)*tw]
        expected, _ = masks.scalar(w,h,lambda x,y: result[y*w+x])
        self.assertEqual(manifest, expected)
        return bytes(result)

    def stats(self, d):
        return self.cli('document.inspect', document=d, selection_statistics=True)['selection']

    def test_shape_set_algebra_refinement_and_statistics_match_all_inline_bytes(self):
        a = self.document(); a['selection'], inline = self.mask()
        b = copy.deepcopy(a); b['selection'] = inline
        shapes = [dict(shape='rect', x=125.25,y=1.5,width=7.5,height=127.25),
                  dict(shape='ellipse',cx=128.25,cy=127.5,rx=4.5,ry=3.25),
                  dict(shape='polygon',points=[[0.25,126.5],[132,125.25],[130.5,131],[1.5,129]])]
        for mode, shape in zip(['replace','add','subtract'],shapes):
            op = dict(op='selection_shape',boundary=shape,combine=mode)
            a=self.edit(a,[op])['document']; b=self.edit(b,[op])['document']
            self.assertEqual(self.values(a['selection']),self.values(b['selection']))
        for op in [dict(op='selection_invert')]+[dict(op='selection_refine',mode=mode,radius=radius)
                  for mode,radius in [('expand',1),('contract',2),('feather',3),('feather',0)]]:
            a=self.edit(a,[op])['document']; b=self.edit(b,[op])['document']
            self.assertEqual(self.values(a['selection']),self.values(b['selection']))
            self.assertEqual(self.stats(a),self.stats(b))
        self.assertNotIn('native',b['selection'])
        structural=self.cli('document.inspect',document=a,scoped=False)['selection']
        self.assertIsNone(structural['statistics'])
        self.assertEqual(structural['native_sha256'],a['selection']['native']['base']['sha256'])
        self.cli('document.inspect',document=a,selection_statistics=True,scoped=False,error='SAMPLE_ROOT_REQUIRED')

    def test_large_automatic_storage_has_independent_rectangle_bytes_and_mask_bake(self):
        w,h=513,513
        raw=struct.pack('<4H',1234,2345,3456,50001)*(w*h)
        d=self.source(raw,w,h)
        boundary=dict(shape='rect',x=127.25,y=128.5,width=260.5,height=255.25)
        d=self.edit(d,[dict(op='selection_shape',boundary=boundary)])['document']
        expected=bytes(math.floor(max(0,min(x+1,387.75)-max(x,127.25))*max(0,min(y+1,383.75)-max(y,128.5))*255+.5)
                       for y in range(h) for x in range(w))
        self.assertEqual(self.values(d['selection']),expected)
        self.assertEqual(d['selection']['gray_hex'],'')
        info=self.stats(d)
        self.assertEqual(info['sha256'],hashlib.sha256(expected).hexdigest())
        self.assertEqual(info['bounds'],[127,128,388,384])
        original=copy.deepcopy(d)
        masked=self.edit(d,[dict(op='mask_from_selection',id='pixels',linked=False)])['document']
        self.assertEqual(masked['items'][0]['mask']['native'],d['selection']['native'])
        baked=self.edit(masked,[dict(op='mask_apply',id='pixels')])['document']
        expected_raw=b''.join(struct.pack('<4H',1234,2345,3456,(50001*v*2+255)//510) for v in expected)
        self.assertEqual(self.raw(baked),expected_raw)
        self.assertEqual(d,original)
        self.assertEqual(self.raw(d),raw)

    def test_canvas_crop_scale_and_small_consumers_preserve_native_coverage(self):
        a=self.document(9,7); a['selection'],inline=self.mask(9,7)
        b=copy.deepcopy(a);b['selection']=inline
        for action in [dict(type='crop',x=-2,y=1,width=13,height=9),
                       dict(type='scale',width=17,height=11,sampling='bilinear'),
                       dict(type='scale',width=7,height=5,sampling='lanczos3')]:
            for target in [a,b]:
                result=self.edit(target,[dict(op='canvas',action=action)])['document']
                target.clear();target.update(result)
            self.assertEqual(self.values(a['selection']),self.values(b['selection']))
        channel=dict(op='channel_calculate',id='coverage',name='Coverage',calculation=dict(type='copy',source=dict(type='selection')))
        ca=self.edit(a,[channel])['document'];cb=self.edit(b,[channel])['document']
        self.assertEqual(ca['channels'],cb['channels'])
        for mode in ['add','subtract','intersect','replace']:
            op=dict(op='channel_load',id='coverage',combine=mode)
            ca=self.edit(ca,[op])['document'];cb=self.edit(cb,[op])['document']
            self.assertEqual(self.values(ca['selection']),self.values(cb['selection']))
        self.assertIn('native',ca['selection'])

    def test_local_brush_retouch_and_repair_use_world_mapped_native_selection(self):
        w,h=133,7
        raw=b''.join(struct.pack('<4H',x*127,y*701,31003,65535) for y in range(h) for x in range(w))
        a=self.source(raw,w,h);a['selection'],inline=self.mask(w,h)
        b=copy.deepcopy(a);b['selection']=inline
        a['items'][0]['transform']=b['items'][0]['transform']=[1,0,0,1,-1,0]
        operations=[dict(op='brush_stroke',id='pixels',stroke=brush.brush([[127.5,3.5]],diameter=5,mode=dict(type='erase'),use_selection=True)),
                    dict(op='retouch',id='pixels',options=dict(source_id='pixels',region=repair.region(126,2,3,2),mode=dict(type='clone'),source_transform=[1,0,0,1,-10,0],use_selection=True)),
                    dict(op='repair',id='pixels',options=repair.options(repair.region(126,2,3,2),dict(type='patch',source_id='pixels',source_origin=[3,2],search_radius=0,context_radius=1,max_context_rms=1,blend=dict(type='clone')),use_selection=True))]
        for op in operations:
            with self.subTest(operation=op['op']):
                missing=copy.deepcopy(a);missing.pop('selection')
                self.edit(missing,[op],error={'brush_stroke':'INVALID_BRUSH','retouch':'INVALID_RETOUCH','repair':'INVALID_REPAIR'}[op['op']])
                ra=self.edit(a,[op]);rb=self.edit(b,[op])
                self.assertEqual(self.raw(ra['document']),self.raw(rb['document']))
                self.assertGreater(ra['changes'][0]['details']['changed_pixels'],0)
                if op['op']!='repair':
                    self.assertEqual(ra['changes'][0]['details']['source_preparation_work']-rb['changes'][0]['details']['source_preparation_work'],w*h*3)

    def test_private_review_retry_history_and_failed_batch_keep_original(self):
        d=self.document(513,513)
        self.save(d)
        op=dict(op='selection_shape',boundary=dict(shape='rect',x=127.25,y=128.5,width=250,height=256))
        before=self.blocks()
        review=self.cli('session.dry_run',session_id='work',request_id='review',expected_revision=0,action=dict(type='edit',operations=[op]),options=dict(include_document=True))
        self.assertEqual(self.blocks(),before)
        expected=self.values(review['proposed_document']['selection'])
        request=dict(session_id='work',request_id='selection',expected_revision=0,action=dict(type='edit',operations=[op]))
        first=self.cli('session.apply',**request);again=self.cli('session.apply',**request)
        self.assertTrue(again['replayed']);self.assertEqual(first['document'],again['document'])
        self.assertNotIn('staged',first['document']['selection']['native'])
        self.assertEqual(self.values(first['document']['selection']),expected)
        self.assertEqual(self.stats(self.ref(1))['sha256'],hashlib.sha256(expected).hexdigest())
        before=self.blocks()
        self.cli('session.apply',session_id='work',request_id='bad',expected_revision=1,
                 action=dict(type='edit',operations=[dict(op='selection_invert'),dict(op='remove',id='missing')]),error='NOT_FOUND')
        self.assertEqual(self.blocks(),before)
        undone=self.cli('session.apply',session_id='work',request_id='undo',expected_revision=1,action=dict(type='undo'))
        self.assertNotIn('selection',undone['document'])
        redone=self.cli('session.apply',session_id='work',request_id='redo',expected_revision=2,action=dict(type='redo'))
        self.assertEqual(self.values(redone['document']['selection']),expected)
        self.cli('session.verify',session_id='work')
        backup=self.cli('session.backup',session_id='work',expected_revision=3,output=dict(file_name='selection-history.sqlite3'))
        self.cli('session.recover',session_id='work',session_root='restored',source=backup['backup'])
        restored=self.cli('session.read',session_id='work',session_root='restored')['document']
        self.assertEqual(self.values(restored['selection']),expected)
        historical=self.cli('document.validate',document=self.ref(1))
        self.assertEqual(self.values(historical['selection']),expected)
        with closing(Client(('--tools','core'),workspace=self.root)) as client:
            client.initialize()
            inspected=client.success('document.inspect',document=self.ref(3),selection_statistics=True)
            self.assertEqual(inspected['selection']['sha256'],hashlib.sha256(expected).hexdigest())

    def test_corrupt_off_window_source_cancel_and_malformed_planes_fail_explicitly(self):
        d=self.document(133,131);d['selection'],_=self.mask()
        for update in [dict(gray_hex='00'),dict(width=132)]:
            invalid=copy.deepcopy(d);invalid['selection'].update(update)
            self.cli('document.validate',document=invalid,error='INVALID_DOCUMENT')
        channel=dict(name='invalid-native-channel',role=dict(type='alpha'),plane=d['selection'])
        self.edit(d,[dict(op='channel_put',id='native',channel=channel)],error='UNSUPPORTED')
        marker=self.root/'cancel';marker.write_text('stop')
        self.edit(d,[dict(op='selection_invert')],control=dict(cancel_file=str(marker)),error='CANCELLED')
        digest=d['selection']['native']['base']['tiles'][-1]
        path=self.root/'.inkbolt/assets'/(digest+'.native-tile')
        data=bytearray(path.read_bytes());data[-1]^=1;path.write_bytes(data)
        self.cli('document.inspect',document=d,selection_statistics=True,error='SAMPLE_TILE_CORRUPT')
        self.edit(d,[dict(op='selection_shape',boundary=dict(shape='rect',x=0,y=0,width=1,height=1),combine='intersect')],error='SAMPLE_TILE_CORRUPT')
        check=self.cli('document.check',document=d,options=dict(resources=True))
        self.assertEqual(check['status'],'fail')
        self.assertIn('SAMPLE_TILE_CORRUPT',str(check))
        self.assertIn('/selection/native',str(check))

    def test_fill_noop_dedup_large_inline_mask_and_native_canvas_growth(self):
        d=self.document(513,513)
        d=self.edit(d,[dict(op='selection_fill',selected=True)])['document']
        self.assertEqual(self.values(d['selection']),bytes([255])*(513*513))
        before=self.blocks()
        same=self.edit(d,[dict(op='selection_fill',selected=True),dict(op='selection_refine',mode='feather',radius=0)])['document']
        self.assertEqual(d['selection'],same['selection']);self.assertEqual(self.blocks(),before)
        empty=self.edit(same,[dict(op='selection_invert')])['document']
        self.assertEqual(self.values(empty['selection']),bytes(513*513))
        self.assertIsNone(self.stats(empty)['bounds'])
        small=self.document(256,257)
        small=self.edit(small,[dict(op='selection_fill',selected=True)])['document']
        self.assertNotIn('native',small['selection'])
        small['items']=[dict(id='pixel',transform=[2,0,0,3,4,5],content=dict(type='raster',width=1,height=1,rgba_hex='ffffffff'))]
        masked=self.edit(small,[dict(op='mask_from_selection',id='pixel',linked=True)])['document']
        self.assertEqual(self.values(masked['items'][0]['mask']),bytes([255])*(256*257))
        self.assertEqual(masked['items'][0]['mask']['transform'],[.5,0,0,1/3,-2,-5/3])
        grown=self.edit(small,[dict(op='canvas',action=dict(type='extent',width=513,height=513,anchor='top_left'))])['document']
        self.assertEqual(self.values(grown['selection']),b''.join(bytes([255])*256+bytes(257) if y<257 else bytes(513) for y in range(513)))


if __name__=='__main__':
    unittest.main()
