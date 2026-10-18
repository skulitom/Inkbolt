"""Native-region cuts checked by exhaustive labels and rational sample features."""
import base64
import copy
from contextlib import closing
from fractions import Fraction as F
import itertools
import hashlib
import json
import random
import struct
import unittest

import test_native_repair as repair
import test_editing_cli as editing
from test_images_cli import png
from test_mcp import Client
from mcp_artifacts import restore


def reference(pixels, width, height, options, depth):
    maximum = 255 if depth == 'u8' else 65535
    scale = (maximum // 255) ** 2
    features = []
    for p in pixels:
        if len(p) == 2:
            p = [p[0]] * 3 + [p[1]]
        if depth == 'f32':
            p = [F(struct.unpack('<f', struct.pack('<f', v))[0]) for v in p]
            feature = [int(v*p[3]*maximum+F(1,2)) for v in p[:3]] + [int(p[3]*maximum+F(1,2))]
        else:
            feature = [(v*p[3]+maximum//2)//maximum for v in p[:3]] + [p[3]]
        features.append(feature)
    distance = lambda a,b: sum((x-y)**2 for x,y in zip(a,b))
    origin = options['region']
    seeds = [[(y-origin['y'])*width+x-origin['x'] for x,y in options[k]] for k in ['foreground','background']]
    unary = [[min(distance(p,features[i]) for i in s) for s in seeds] for p in features]
    pairs = []
    strength = options.get('smoothness',4096)*scale
    edge = options.get('edge_scale',4096)*scale
    for y in range(height):
        for x in range(width):
            i = y*width+x
            for xx,yy in [(x+1,y),(x,y+1)]:
                if xx<width and yy<height:
                    j = yy*width+xx
                    pairs.append([i,j,strength*edge//(edge+distance(features[i],features[j]))])
    hard = 1+sum(max(c) for c in unary)+sum(w for _,_,w in pairs)
    for i in seeds[0]:unary[i][1] = hard
    for i in seeds[1]:unary[i][0] = hard
    fixed = {i:True for i in seeds[0]} | {i:False for i in seeds[1]}
    free = [i for i in range(len(pixels)) if i not in fixed]
    best = None
    for bits in itertools.product([False,True],repeat=len(free)):
        labels = fixed | dict(zip(free,bits))
        energy = sum(c[0 if labels[i] else 1] for i,c in enumerate(unary)) + sum(w for a,b,w in pairs if labels[a]!=labels[b])
        foreground = {i for i in labels if labels[i]}
        if best is None or energy<best:best,intersection = energy,foreground
        elif energy==best:intersection &= foreground
    return best,bytes(255 if i in intersection else 0 for i in range(len(pixels))),unary,pairs,hard


class NativeSegmentationTests(unittest.TestCase):
    setUp = repair.NativeRepairTests.setUp
    cli = repair.NativeRepairTests.cli
    save = repair.NativeRepairTests.save
    ref = repair.NativeRepairTests.ref
    files = repair.NativeRepairTests.files
    raw = repair.NativeRepairTests.raw
    imported = repair.NativeRepairTests.imported

    def segment(self,d,options,**kw):
        return self.cli('assist.segment',document=d,id='pixels',options=options,**kw)

    def edit(self,d,operations,**kw):
        return self.cli('document.edit',document=d,expected_revision=d['revision'],operations=operations,**kw)

    def test_six_formats_three_representations_cross_block_exact_cuts_and_baked_samples(self):
        width,height = 132,7
        region = dict(x=127,y=2,width=3,height=3)
        for depth in ['u8','u16','f32']:
            for channels in [2,4]:
                maximum = dict(u8=255,u16=65535,f32=1)[depth]
                pixels = []
                for y in range(height):
                    for x in range(width):
                        components = [1+(x*3+y*5+c*2)%7 for c in range(channels-1)]
                        alpha = [0,4,8][(x+y)%3]
                        pixels.append([(v/8 if depth=='f32' else v*maximum//8) for v in components+[alpha]])
                window = [pixels[y*width+x] for y in range(2,5) for x in range(127,130)]
                for version in [None,1,2]:
                    with self.subTest(depth=depth,channels=channels,version=version):
                        d = self.imported(width,height,[v for p in pixels for v in p],depth,channels,version)
                        original = self.raw(d)
                        files = self.files()
                        for strength in [0,65535]:
                            o = dict(region=region,foreground=[[127,2]],background=[[129,4]],smoothness=strength,edge_scale=260100,include_costs=True)
                            r = self.segment(d,o)
                            energy,mask,unary,pairs,hard = reference(window,3,3,o,depth)
                            self.assertEqual((r['minimum_energy'],r['max_flow']),(energy,energy))
                            self.assertEqual(r['data_cost']+r['boundary_cost'],energy)
                            self.assertEqual(r['class_costs'],unary)
                            self.assertEqual(r['neighbor_costs'],pairs)
                            self.assertEqual(r['hard_seed_cost'],hard)
                            self.assertEqual(bytes.fromhex(r['mask']['gray_hex']),mask)
                            self.assertEqual(r['mask']['transform'],[1,0,0,1,127,2])
                            self.assertEqual(r['analysis']['region'],region)
                            self.assertEqual(r['analysis']['feature_bits'],8 if depth=='u8' else 16)
                            self.assertEqual(r['analysis']['source_preparation_work'],0 if version is None else width*height*3)
                            self.assertEqual(r['work'],r['analysis']['local_work']+r['analysis']['source_preparation_work'])
                            self.assertEqual(r['analysis']['approximation'] is not None,depth=='f32')
                        self.assertEqual(self.files(),files)
                        masked = self.edit(d,[dict(op='assist_mask',id='pixels',options=o)])['document']
                        self.assertEqual(masked['items'][0]['content'],d['items'][0]['content'])
                        operations = []
                        if version == 1:
                            before_bake = self.files()
                            self.edit(masked,[dict(op='mask_apply',id='pixels')],error='MIGRATION_REQUIRED')
                            self.assertEqual(self.files(),before_bake)
                            operations.append(dict(op='sample_storage_migrate',id='pixels'))
                        baked = self.edit(masked,operations+[dict(op='mask_apply',id='pixels')])['document']
                        expected = bytearray(original)
                        channel_bytes = dict(u8=1,u16=2,f32=4)[depth]
                        stride = channels*channel_bytes
                        for y in range(height):
                            for x in range(width):
                                selected = 127<=x<130 and 2<=y<5 and mask[(y-2)*3+x-127]
                                if not selected:
                                    at = (y*width+x)*stride+(channels-1)*channel_bytes
                                    expected[at:at+channel_bytes] = bytes(channel_bytes)
                        self.assertEqual(self.raw(baked),expected)
                        self.assertEqual(self.raw(d),original)

    def test_true_u16_distinctions_and_float_quantization_are_explicit(self):
        values = [v for code in [10000,10001,10001] for v in [code,code,code,65535]]
        d = self.imported(3,1,values)
        o = dict(foreground=[[0,0]],background=[[1,0]],smoothness=0)
        r = self.segment(d,o)
        self.assertEqual(bytes.fromhex(r['mask']['gray_hex']),bytes([255,0,0]))
        self.assertEqual(r['analysis']['feature_bits'],16)
        self.assertIsNone(r['analysis']['approximation'])
        floating = self.imported(3,1,[v/65535 for v in values],depth='f32')
        report = self.segment(floating,o)
        self.assertEqual(report['mask'],r['mask'])
        self.assertEqual(report['analysis']['approximation']['maximum_feature_rounding_error'],.5/65535)
        self.assertFalse(report['analysis']['approximation']['source_converted'])
        linear = self.imported(3,1,[.25,.5,.75,1.0]*3,depth='f32',version=None)
        linear['items'][0]['content']['grid']['encoding'] = 'linear_srgb'
        linear['color_space'] = 'linear_srgb'
        self.cli('document.validate',document=linear)
        self.segment(linear,o,error='UNSUPPORTED')

    def test_binary32_edge_cases_match_exact_rational_objective(self):
        from_bits = lambda bits: struct.unpack('<f',struct.pack('<I',bits))[0]
        edge_bits = [0,0x80000000,1,0x7fffff,0x800000,0x3f000000,0x3f7fffff,0x3f800000]
        for code in [0,1,63,127,255,4095,32767,65534]:
            half = struct.unpack('<I',struct.pack('<f',(code+.5)/65535))[0]
            edge_bits.extend([half-1,half,half+1])
        rng = random.Random(518922)
        cases = [[from_bits(b) for b in edge_bits[i:i+8]] for i in range(0,len(edge_bits),8)]
        cases += [[from_bits(rng.randrange(0x3f800001)) for _ in range(8)] for _ in range(8)]
        for channels in [2,4]:
            for case,values in enumerate(cases):
                pixels = [[values[(i+c)%len(values)] for c in range(channels-1)] +
                          [[1.0,.5,from_bits(0x3f7fffff),values[i%len(values)]][i%4]] for i in range(6)]
                o = dict(region=dict(x=0,y=0,width=3,height=2),foreground=[[0,0]],background=[[2,1]],
                         smoothness=[0,4096,65535][case%3],edge_scale=[1,4096,260100][case%3],include_costs=True)
                with self.subTest(channels=channels,case=case):
                    d = self.imported(3,2,[v for p in pixels for v in p],depth='f32',n=channels,version=None if case%2 else 2)
                    original = self.raw(d)
                    r = self.segment(d,o)
                    energy,mask,unary,pairs,hard = reference(pixels,3,2,o,'f32')
                    self.assertEqual((r['minimum_energy'],r['max_flow']),(energy,energy))
                    self.assertEqual(bytes.fromhex(r['mask']['gray_hex']),mask)
                    self.assertEqual(r['class_costs'],unary)
                    self.assertEqual(r['neighbor_costs'],pairs)
                    self.assertEqual(r['hard_seed_cost'],hard)
                    self.assertEqual(self.raw(d),original)

    def test_asset_crop_global_region_seeds_and_rotated_mask_placement(self):
        source = self.root/'asset.png'
        source.write_bytes(png(8,6,bytes(v for y in range(6) for x in range(8) for v in ([220,30,40,255] if x<4 else [20,80,200,255]))))
        asset = self.cli('asset.import',source_path=str(source))['asset']
        d = self.cli('document.validate',document=dict(schema_version=2,id='rotated-region',kind='raster',width=16,height=16,color_space='srgb',assets={'source':asset},items=[dict(id='pixels',transform=[0,1,-1,0,14,2],content=dict(type='image',asset_id='source',width=8,height=12,crop=dict(x=2,y=1,width=4,height=4)))]))
        o = dict(region=dict(x=1,y=1,width=2,height=2),foreground=[[1,1]],background=[[2,2]],smoothness=0)
        before = self.files()
        r = self.segment(d,o)
        self.assertEqual(bytes.fromhex(r['mask']['gray_hex']),bytes([255,0]*2))
        self.assertEqual(r['mask']['transform'],[2,0,0,3,2,3])
        result = self.edit(d,[dict(op='assist_mask',id='pixels',options=o)])['document']
        image = self.cli('document.export',document=result,format='png')
        rgba = editing.png_pixels(base64.b64decode(image['data']))[2]
        expected = bytes(v for y in range(16) for x in range(16) for v in ([220,30,40,255] if 5<=x<11 and 4<=y<6 else [0,0,0,0]))
        self.assertEqual(rgba,expected)
        self.assertEqual(self.files(),before)
        embedded = self.cli('asset.embed',asset=asset)
        d['assets']['source'] = embedded
        self.assertEqual(self.segment(d,o)['mask'],r['mask'])

    def test_invalid_regions_memory_admission_and_far_corruption_are_atomic(self):
        d = self.imported(260,7,[10003,20011,30013,65535]*(260*7))
        o = dict(region=dict(x=127,y=2,width=3,height=3),foreground=[[127,2]],background=[[129,4]])
        before = self.files()
        for patch in [dict(region=dict(x=259,y=0,width=2,height=1)),dict(region=dict(x=0,y=0,width=0,height=1)),dict(region=dict(x=4294967295,y=0,width=2,height=1)),dict(foreground=[[0,0]]),dict(background=[[127,2]])]:
            self.segment(d,dict(o,**patch),error='INVALID_ASSISTANCE')
        self.segment(d,o,error='TIMEOUT',control=dict(timeout_ms=0))
        self.assertEqual(self.files(),before)
        enormous = dict(schema_version=2,id='memory',kind='raster',width=4096,height=2048,color_space='srgb',assets={'source':dict(width=4096,height=2048,sha256='a'*64,storage=dict(type='stored'))},items=[dict(id='pixels',content=dict(type='image',asset_id='source',width=4096,height=2048))])
        self.segment(enormous,dict(region=dict(x=0,y=0,width=2,height=1),foreground=[[0,0]],background=[[1,0]]),error='RESOURCE_LIMIT')
        name = d['items'][0]['content']['grid']['base']['tiles'][-1]
        path = self.root/'.inkbolt/assets'/f'{name}.native-tile'
        data = path.read_bytes();path.write_bytes(data[:-1]+bytes([data[-1]^1]))
        self.segment(d,o,error='SAMPLE_TILE_CORRUPT')

    def test_mcp_private_review_retry_history_and_failed_batch_preserve_source(self):
        d = self.imported(8,5,[v for y in range(5) for x in range(8) for v in ([10001,20003,30007,65535] if x<4 else [40009,50021,60013,65535])])
        original = self.raw(d)
        self.save(d)
        o = dict(region=dict(x=2,y=1,width=4,height=3),foreground=[[2,1]],background=[[5,3]],smoothness=0)
        action = dict(type='edit',operations=[dict(op='assist_mask',id='pixels',options=o)])
        with closing(Client(('--tools','core'),workspace=self.root)) as c:
            c.initialize()
            response = c.tool('run',command='assist.segment',arguments=dict(document=self.ref(),id='pixels',options=o))
            self.assertFalse(response['isError'],response)
            report = restore(response)['result']
            self.assertEqual(report,self.segment(d,o))
            before = self.files()
            preview = c.success('session.dry_run',session_id='work',request_id='mask',expected_revision=0,action=action,options=dict(include_document=True))
            self.assertEqual(self.files(),before)
            failed_batch = dict(type='edit',operations=action['operations']+[dict(op='remove',id='missing')])
            rejected = c.tool('session.apply',session_id='work',request_id='late-failure',expected_revision=0,action=failed_batch)
            self.assertEqual(rejected['structuredContent']['error']['code'],'NOT_FOUND')
            self.assertEqual(self.files(),before)
            saved = c.success('session.apply_proposal',proposal=preview['proposal'],action=action)
            self.assertEqual(saved['receipt'],preview['predicted_receipt'])
            self.assertEqual(saved['document']['items'][0]['content'],d['items'][0]['content'])
            self.assertTrue(c.success('session.apply_proposal',proposal=preview['proposal'],action=action)['replayed'])
            rejected = c.tool('session.apply',session_id='work',request_id='bad',expected_revision=1,action=action)
            self.assertTrue(rejected['isError'])
            self.assertEqual(c.success('session.read',session_id='work')['document'],saved['document'])
            undone = c.success('session.apply',session_id='work',request_id='undo',expected_revision=1,action=dict(type='undo'))
            self.assertEqual(undone['document']['items'],d['items'])
            redone = c.success('session.apply',session_id='work',request_id='redo',expected_revision=2,action=dict(type='redo'))
            self.assertEqual(redone['document']['items'],saved['document']['items'])
            verified = c.tool('run',command='session.verify',arguments=dict(session_id='work'))
            self.assertFalse(verified['isError'],verified)
            self.assertTrue(restore(verified)['result']['valid'])
        self.assertEqual(self.raw(d),original)

    def test_maximum_region_remains_reviewable_with_compact_receipts_and_full_mask(self):
        d = self.imported(256,256,[v for y in range(256) for x in range(256)
                                 for v in ([10001,65535] if x<128 else [50001,65535])],n=2)
        self.save(d)
        o = dict(region=dict(x=0,y=0,width=256,height=256),foreground=[[0,0]],background=[[255,255]],smoothness=0,include_costs=True)
        action = dict(type='edit',operations=[dict(op='assist_mask',id='pixels',options=o)])
        before = self.files()
        review = self.cli('session.dry_run',session_id='work',request_id='maximum',expected_revision=0,action=action)
        self.assertEqual(self.files(),before)
        done = self.cli('session.apply_proposal',proposal=review['proposal'],action=action)
        self.assertEqual(done['receipt'],review['predicted_receipt'])
        self.assertLessEqual(len(json.dumps(done['receipt']).encode()),8192)
        mask = bytes([255]*128+[0]*128)*256
        self.assertEqual(bytes.fromhex(done['document']['items'][0]['mask']['gray_hex']),mask)
        self.assertEqual(done['document']['items'][0]['content'],d['items'][0]['content'])
        detail = done['receipt']['changes'][0]['details']
        self.assertEqual(detail['result_format'],'native_selection_summary_v1')
        self.assertEqual(detail['mask_summary']['gray_sha256'],hashlib.sha256(mask).hexdigest())
        self.assertNotIn('gray_hex',detail['mask_summary'])
        self.assertNotIn('mask',detail)
        self.assertNotIn('class_costs',detail)
        self.assertNotIn('neighbor_costs',detail)
        self.assertFalse(detail['cost_arrays_included'])
        self.assertEqual((detail['minimum_energy'],detail['max_flow']),(0,0))
        self.assertTrue(self.cli('session.apply_proposal',proposal=review['proposal'],action=action)['replayed'])
        self.assertTrue(self.cli('session.verify',session_id='work')['valid'])
