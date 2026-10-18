"""Proxy/refine certificates checked against exhaustive native labeling oracles."""
import base64
import copy
from contextlib import closing
from fractions import Fraction as F
import hashlib
import itertools
import json
import math
import random
import struct
import unittest

import test_native_repair as repair
from test_mcp import Client
from mcp_artifacts import restore
from test_images_cli import png
from test_editing_cli import png_pixels
from test_proof_cli import scalar as scalar_png


def solve(unary, pairs, pins):
    unary = copy.deepcopy(unary)
    hard = 1 + sum(max(c) for c in unary) + sum(w for _, _, w in pairs)
    for i, selected in pins.items():
        unary[i][int(selected)] = hard
    free = [i for i in range(len(unary)) if i not in pins]
    best = None
    for bits in itertools.product([False, True], repeat=len(free)):
        labels = pins | dict(zip(free, bits))
        energy = sum(c[not labels[i]] for i, c in enumerate(unary)) + sum(w for a, b, w in pairs if labels[a] != labels[b])
        selected = {i for i in labels if labels[i]}
        if best is None or energy < best:
            best, intersection = energy, selected
        elif energy == best:
            intersection &= selected
    labels = [i in intersection for i in range(len(unary))]
    data = sum(c[not labels[i]] for i, c in enumerate(unary))
    return labels, dict(minimum_energy=str(best), max_flow=str(best), data_cost=str(data), boundary_cost=str(best-data), hard_seed_cost=str(hard)), unary


def reference(pixels, width, height, o, depth):
    maximum = 255 if depth == 'u8' else 65535
    features = []
    for p in pixels:
        if len(p) == 2: p = [p[0]]*3 + [p[1]]
        if depth == 'f32':
            p = [F(struct.unpack('<f', struct.pack('<f', v))[0]) for v in p]
            features.append([int(v*p[3]*maximum+F(1,2)) for v in p[:3]] + [int(p[3]*maximum+F(1,2))])
        else:
            features.append([(v*p[3]+maximum//2)//maximum for v in p[:3]]+[p[3]])
    distance = lambda a,b: sum((x-y)**2 for x,y in zip(a,b))
    scale = (maximum//255)**2
    strength, edge = o['smoothness']*scale, o['edge_scale']*scale
    weight = lambda a,b: strength*edge//(edge+distance(a,b))
    step, radius = o['proxy']['step'], o['proxy']['refine_radius']
    columns, rows = math.ceil(width/step), math.ceil(height/step)
    cells = [[] for _ in range(columns*rows)]
    membership = []
    for i in range(width*height):
        cell = (i//width//step)*columns+(i%width//step)
        cells[cell].append(i); membership.append(cell)
    centers = []
    for cells_in_cell in cells:
        xs, ys = [i%width for i in cells_in_cell], [i//width for i in cells_in_cell]
        centers.append(((min(ys)+max(ys))//2)*width+(min(xs)+max(xs))//2)
    seed_indices = [[y*width+x for x,y in o[name]] for name in ['foreground','background']]
    prototypes = [[features[i] for i in indices] for indices in seed_indices]
    unary = lambda f: [min(distance(f,p) for p in ps) for ps in prototypes]
    costs = [[v*len(cells[i]) for v in unary(features[c])] for i,c in enumerate(centers)]
    native_pairs = []
    coarse_pair_lengths = {}
    for y in range(height):
        for x in range(width):
            i = y*width+x
            for xx,yy in [(x+1,y),(x,y+1)]:
                if xx < width and yy < height:
                    j = yy*width+xx; native_pairs.append((i,j,weight(features[i],features[j])))
                    a,b = membership[i],membership[j]
                    if a != b: coarse_pair_lengths[a,b] = coarse_pair_lengths.get((a,b),0)+1
    pairs = [(a,b,length*weight(features[centers[a]],features[centers[b]])) for (a,b),length in coarse_pair_lengths.items()]
    pins = {membership[i]: class_id == 0 for class_id, indices in enumerate(seed_indices) for i in indices}
    coarse, coarse_certificate, coarse_costs = solve(costs,pairs,pins)
    initial = [coarse[c] for c in membership]
    endpoints = {i for a,b,_ in native_pairs if initial[a] != initial[b] for i in (a,b)}
    band = [i for i in range(width*height) if any(max(abs(i%width-j%width),abs(i//width-j//width)) < radius for j in endpoints)]
    index = {i:j for j,i in enumerate(band)}
    fine_costs = [unary(features[i]) for i in band]
    fine_pairs = []
    for a,b,w in native_pairs:
        if a in index and b in index: fine_pairs.append((index[a],index[b],w))
        elif a in index: fine_costs[index[a]][initial[b]] += w
        elif b in index: fine_costs[index[b]][initial[a]] += w
    before = sum(c[not initial[i]] for i,c in zip(band,fine_costs)) + sum(w for a,b,w in fine_pairs if initial[band[a]] != initial[band[b]])
    pins = {index[i]: class_id == 0 for class_id, indices in enumerate(seed_indices) for i in indices if i in index}
    fine, fine_certificate, fine_costs = solve(fine_costs,fine_pairs,pins)
    final = initial[:]
    for i, label in zip(band,fine): final[i] = label
    return dict(mask=bytes(255 if v else 0 for v in final),coarse=coarse_certificate,fine=fine_certificate,before=str(before),
                coarse_costs=coarse_costs,coarse_pairs=pairs,fine_costs=fine_costs,fine_pairs=fine_pairs,
                coordinates=[[i%width,i//width] for i in band],coarse_labels=coarse,initial_labels=[initial[i] for i in band])


class ProxySegmentationTests(unittest.TestCase):
    setUp = repair.NativeRepairTests.setUp
    cli = repair.NativeRepairTests.cli
    save = repair.NativeRepairTests.save
    ref = repair.NativeRepairTests.ref
    files = repair.NativeRepairTests.files
    raw = repair.NativeRepairTests.raw
    imported = repair.NativeRepairTests.imported

    def segment(self,d,o,**kw):
        return self.cli('assist.segment',document=d,id='pixels',options=o,**kw)

    def edit(self,d,o,**kw):
        return self.cli('document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='assist_mask',id='pixels',options=o)],**kw)

    def mask_values(self,mask):
        manifest = mask['native']['base']
        w,h = mask['width'],mask['height']; result = bytearray(w*h)
        for i,digest in enumerate(manifest['tiles']):
            blob = (self.root/'.inkbolt/assets'/(digest+'.native-tile')).read_bytes()
            self.assertEqual(hashlib.sha256(blob).hexdigest(),digest)
            self.assertEqual(blob[:8],b'INKSCAL1')
            tw,th = struct.unpack_from('<II',blob,8)
            self.assertEqual(blob[16:20],bytes([1,1,0,0]))
            self.assertEqual(len(blob),20+tw*th)
            left,top = i%math.ceil(w/128)*128,i//math.ceil(w/128)*128
            for y in range(th):result[(top+y)*w+left:(top+y)*w+left+tw] = blob[20+y*tw:20+(y+1)*tw]
        return bytes(result)

    def test_exhaustive_two_stage_objectives_all_formats_storage_short_cells_and_ties(self):
        rng = random.Random(73231)
        case = 0
        for depth,n,version in itertools.product(['u8','u16','f32'],[2,4],[None,1,2]):
            w,h = [(3,3),(5,2)][case%2]
            maximum = dict(u8=255,u16=65535,f32=1)[depth]
            codes = [[rng.randrange(9) for _ in range(n-1)]+[rng.choice([0,4,8])] for _ in range(w*h)]
            if case%5 == 0:codes = [[4]*(n-1)+[8] for _ in range(w*h)]
            pixels = [[(c/8 if depth=='f32' else c*maximum//8) for c in p] for p in codes]
            o = dict(foreground=[[0,0]],background=[[w-1,h-1]],smoothness=[0,65535][case%2],edge_scale=260100,
                     proxy=dict(step=2,refine_radius=1),include_costs=True)
            with self.subTest(depth=depth,channels=n,version=version):
                d = self.imported(w,h,[v for p in pixels for v in p],depth,n,version)
                original, files = self.raw(d),self.files()
                expected = reference(pixels,w,h,o,depth)
                actual = self.segment(d,o)
                self.assertEqual(self.files(),files)
                for name,key in [('proxy_cut','coarse'),('refinement_cut','fine')]:
                    for field,value in expected[key].items():self.assertEqual(actual[name][field],value)
                for name,key in [('coarse','coarse'),('refinement','fine')]:
                    detail = actual['costs'][name]
                    self.assertEqual(detail['class_costs'],[[str(v) for v in c] for c in expected[key+'_costs']])
                    self.assertEqual(sorted(detail['neighbor_costs']),sorted([[a,b,str(w)] for a,b,w in expected[key+'_pairs']]))
                self.assertEqual(actual['costs']['refinement']['coordinates'],expected['coordinates'])
                self.assertEqual(actual['costs']['refinement']['initial_labels'],expected['initial_labels'])
                self.assertEqual(actual['initial_conditional_energy'],expected['before'])
                self.assertLessEqual(int(actual['refinement_cut']['minimum_energy']),int(expected['before']))
                self.assertEqual(actual['mask_summary']['gray_sha256'],hashlib.sha256(expected['mask']).hexdigest())
                edited = self.edit(d,o)
                self.assertEqual(self.mask_values(edited['document']['items'][0]['mask']),expected['mask'])
                detail = edited['changes'][0]['details']
                self.assertNotIn('costs',detail);self.assertFalse(detail['cost_arrays_included'])
                self.assertEqual(edited['document']['items'][0]['content'],d['items'][0]['content'])
                self.assertEqual(self.raw(d),original)
                self.assertFalse(actual['approximation']['global_native_optimum'])
            case += 1

    def test_step_one_matches_native_exact_selection_and_same_class_cell_seeds_are_preserved(self):
        pixels = [[10000+i%3,30001-i%2,50001,55003] for i in range(12)]
        d = self.imported(4,3,[v for p in pixels for v in p])
        base = dict(foreground=[[0,0],[1,0]],background=[[3,2]],smoothness=65535,edge_scale=260100,include_costs=True)
        native = self.segment(d,base)
        o = dict(base,proxy=dict(step=1,refine_radius=2))
        proxy = self.segment(d,o)
        self.assertEqual(proxy['mask_summary']['gray_sha256'],hashlib.sha256(bytes.fromhex(native['mask']['gray_hex'])).hexdigest())
        self.assertEqual(int(proxy['proxy_cut']['minimum_energy']),native['minimum_energy'])
        self.assertEqual(self.mask_values(self.edit(d,o)['document']['items'][0]['mask']),bytes.fromhex(native['mask']['gray_hex']))
        o['proxy'] = dict(step=2,refine_radius=1)
        expected = reference(pixels,4,3,o,'u16')
        self.assertEqual(self.segment(d,o)['mask_summary']['gray_sha256'],hashlib.sha256(expected['mask']).hexdigest())

    def test_shifted_native_boundary_full_mask_preview_mcp_private_review_and_history(self):
        w,h,boundary = 513,257,259
        d = self.imported(w,h,[v for y in range(h) for x in range(w) for v in ([10001,65535] if x<boundary else [50001,65535])],n=2)
        original = self.raw(d); self.save(d)
        o = dict(foreground=[[0,0]],background=[[512,256]],smoothness=0,proxy=dict(step=16,refine_radius=8,include_preview=True))
        expected = bytes([255]*boundary+[0]*(w-boundary))*h
        before = self.files(); r = self.segment(d,o)
        self.assertEqual(self.files(),before)
        self.assertGreater(int(r['initial_conditional_energy']),0)
        self.assertEqual(r['refinement_cut']['minimum_energy'],'0')
        self.assertEqual(r['mask_summary']['gray_sha256'],hashlib.sha256(expected).hexdigest())
        pw,ph,preview,_ = scalar_png(r['preview'])
        self.assertEqual((pw,ph),(33,17))
        centers = [(x+min(x+16,w)-1)//2 for x in range(0,w,16)]
        self.assertEqual(preview,bytes(255 if x<boundary else 0 for _ in range(ph) for x in centers))
        action = dict(type='edit',operations=[dict(op='assist_mask',id='pixels',options=o)])
        with closing(Client(workspace=self.root)) as c:
            c.initialize()
            response = c.tool('assist.segment',document=self.ref(),id='pixels',options=o)
            self.assertEqual(restore(response)['result'],r)
            images = [x for x in response['content'] if x['type']=='image']
            self.assertEqual(len(images),1)
            self.assertNotIn('data',response['structuredContent']['result']['preview'])
            self.assertEqual(images[0]['data'],r['preview']['data'])
            review = c.success('session.dry_run',session_id='work',request_id='proxy',expected_revision=0,action=action)
            self.assertEqual(self.files(),before)
            failed = c.tool('session.apply',session_id='work',request_id='failed-proxy',expected_revision=0,
                            action=dict(type='edit',operations=action['operations']+[dict(op='remove',id='missing')]))
            self.assertEqual(failed['structuredContent']['error']['code'],'NOT_FOUND')
            self.assertEqual(self.files(),before)
            saved = c.success('session.apply_proposal',proposal=review['proposal'],action=action)
            self.assertEqual(saved['receipt'],review['predicted_receipt'])
            self.assertLess(len(json.dumps(saved['receipt']).encode()),8192)
            self.assertEqual(self.mask_values(saved['document']['items'][0]['mask']),expected)
            self.assertTrue(c.success('session.apply_proposal',proposal=review['proposal'],action=action)['replayed'])
            undone = c.success('session.apply',session_id='work',request_id='undo',expected_revision=1,action=dict(type='undo'))
            self.assertEqual(undone['document']['items'],d['items'])
            redone = c.success('session.apply',session_id='work',request_id='redo',expected_revision=2,action=dict(type='redo'))
            self.assertEqual(redone['document']['items'],saved['document']['items'])
        self.assertEqual(self.raw(d),original)
        masked = saved['document']
        baked = self.cli('document.edit',document=masked,expected_revision=masked['revision'],operations=[dict(op='mask_apply',id='pixels')])['document']
        self.assertEqual(self.raw(baked),b''.join(original[i*4:i*4+2]+(original[i*4+2:i*4+4] if selected else b'\x00\x00') for i,selected in enumerate(expected)))

    def test_maximum_native_band_and_explicit_graph_memory_work_refusals(self):
        def document(w):
            return self.imported(w,512,[v for y in range(512) for x in range(w)
                                        for v in ([10001,65535] if (x//4+y//4)%2==0 else [50001,65535])],n=2)
        d = document(512)
        o = dict(foreground=[[0,0]],background=[[5,0]],smoothness=0,proxy=dict(step=4,refine_radius=4))
        before = self.files()
        r = self.segment(d,o)
        expected = bytes(255 if (x//4+y//4)%2==0 else 0 for y in range(512) for x in range(512))
        self.assertEqual(r['refinement_pixels'],262144)
        self.assertEqual(r['mask_summary']['gray_sha256'],hashlib.sha256(expected).hexdigest())
        self.assertLessEqual(r['processing_memory_bound_bytes'],256*1024*1024)
        self.segment(d,dict(o,include_costs=True),error='RESOURCE_LIMIT')
        self.segment(d,dict(o,foreground=[[i*8,0] for i in range(32)],background=[[i*8+4,0] for i in range(32)]),error='RESOURCE_LIMIT')
        self.assertEqual(self.files(),before)
        oversized = document(514)
        before = self.files()
        self.segment(oversized,o,error='RESOURCE_LIMIT')
        self.segment(oversized,dict(o,proxy=dict(step=1,refine_radius=1)),error='RESOURCE_LIMIT')
        self.assertEqual(self.files(),before)

    def test_large_weighted_certificates_preserve_integers_above_json_double_precision(self):
        w,h = 1025,1025
        d = self.imported(w,h,[v for y in range(h) for x in range(w) for v in ([0,65535] if x<512 else [65535,65535])],n=2)
        o = dict(foreground=[[0,0]],background=[[1024,1024]],smoothness=0,proxy=dict(step=64,refine_radius=1))
        r = self.segment(d,o)
        hard = 1+w*h*3*65535**2
        self.assertGreater(hard,2**53)
        self.assertEqual(r['proxy_cut']['hard_seed_cost'],str(hard))
        self.assertEqual(r['refinement_cut']['minimum_energy'],'0')
        self.assertEqual(r['mask_summary']['gray_sha256'],hashlib.sha256(bytes([255]*512+[0]*513)*h).hexdigest())

    def test_crop_region_global_seeds_transformed_mask_and_immutable_asset(self):
        source = self.root/'source.png'
        source.write_bytes(png(8,6,bytes(v for y in range(6) for x in range(8) for v in ([220,30,40,255] if x<4 else [20,80,200,255]))))
        original = source.read_bytes()
        asset = self.cli('asset.import',source_path=str(source))['asset']
        d = self.cli('document.validate',document=dict(schema_version=2,id='crop-proxy',kind='raster',width=16,height=16,color_space='srgb',assets={'source':asset},items=[dict(id='pixels',transform=[0,1,-1,0,14,2],content=dict(type='image',asset_id='source',width=8,height=12,crop=dict(x=2,y=1,width=4,height=4)))]))
        o = dict(region=dict(x=1,y=1,width=2,height=2),foreground=[[1,1]],background=[[2,2]],smoothness=0,proxy=dict(step=1,refine_radius=1))
        result = self.edit(d,o)['document']
        self.assertEqual(result['items'][0]['mask']['transform'],[2,0,0,3,2,3])
        self.assertEqual(self.mask_values(result['items'][0]['mask']),bytes([255,0]*2))
        image = self.cli('document.export',document=result,format='png')
        rgba = png_pixels(base64.b64decode(image['data']))[2]
        self.assertEqual(rgba,bytes(v for y in range(16) for x in range(16) for v in ([220,30,40,255] if 5<=x<11 and 4<=y<6 else [0,0,0,0])))
        self.assertEqual(source.read_bytes(),original)

    def test_refusals_and_corrupt_unsampled_dependencies_publish_nothing(self):
        d = self.imported(260,7,[10003,20011,30013,65535]*(260*7))
        o = dict(region=dict(x=0,y=0,width=4,height=3),foreground=[[0,0]],background=[[3,2]],proxy=dict(step=2,refine_radius=1))
        before = self.files()
        for patch in [dict(proxy=dict(step=0,refine_radius=1)),dict(proxy=dict(step=2,refine_radius=0)),
                      dict(proxy=dict(step=1025,refine_radius=1)),dict(proxy=dict(step=2,refine_radius=65)),
                      dict(background=[[1,0]]),dict(background=[[0,0]]),dict(foreground=[[259,6]])]:
            self.segment(d,dict(o,**patch),error='INVALID_ASSISTANCE')
        self.segment(d,o,error='TIMEOUT',control=dict(timeout_ms=0))
        self.assertEqual(self.files(),before)
        digest = d['items'][0]['content']['grid']['base']['tiles'][-1]
        path = self.root/'.inkbolt/assets'/(digest+'.native-tile')
        original = path.read_bytes();path.write_bytes(original[:-1]+bytes([original[-1]^1]))
        self.segment(d,o,error='SAMPLE_TILE_CORRUPT')

    def test_unsampled_island_outside_band_remains_an_explicit_approximation(self):
        w,h=16,4
        pixels=[[10001,65535] if x<8 else [50001,65535] for y in range(h) for x in range(w)]
        pixels[2*w]=[50001,65535]
        d=self.imported(w,h,[v for p in pixels for v in p],n=2)
        o=dict(foreground=[[0,0]],background=[[15,3]],smoothness=0)
        native=self.segment(d,o)
        proxy=self.segment(d,dict(o,proxy=dict(step=4,refine_radius=1)))
        self.assertEqual(bytes.fromhex(native['mask']['gray_hex'])[2*w],0)
        expected=bytes([255]*8+[0]*8)*h
        self.assertEqual(proxy['mask_summary']['gray_sha256'],hashlib.sha256(expected).hexdigest())
        self.assertFalse(proxy['approximation']['global_native_optimum'])
        self.assertIn('small_features_outside_refinement_band_may_be_missed',proxy['approximation']['losses'])


if __name__ == '__main__':unittest.main()
