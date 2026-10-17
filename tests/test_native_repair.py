"""Independent typed repair checks, bounded distant moves and durable atomic edits."""
import copy
from contextlib import closing
import hashlib
import math
import struct
import unittest

import test_agent_workspace as workspace
import test_native_retouch as native
import test_repair_cli as legacy
from test_mcp import Client
from test_sample_conversion_cli import tiff
from test_samples_cli import packed


class NativeRepairTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli
    save = workspace.AgentWorkspaceTests.save
    ref = workspace.AgentWorkspaceTests.ref
    raw = native.NativeRetouchTests.raw
    files = native.NativeRetouchTests.files
    assert_codes = native.NativeRetouchTests.assert_codes

    def imported(self, w, h, values, depth='u16', n=4, version=2, **kwargs):
        path = self.root / f'source-{len(list(self.root.glob("source-*")))}.tiff'
        path.write_bytes(tiff(w, h, values, depth=depth, n=n))
        args = dict(source_path=str(path), id='repair', color_policy='assume_srgb', **kwargs)
        if version is not None:
            args['storage'] = dict(storage_version=version)
        return self.cli('sample.import', **args)['document']

    def apply(self, d, o, **kwargs):
        return self.cli('document.edit', document=d, expected_revision=d['revision'],
                        operations=[dict(op='repair', id='pixels', options=o)], **kwargs)

    def test_fill_six_native_formats_three_representations_cross_block_exact_bits(self):
        w, h = 138, 7
        r = legacy.region(127, 2, 2, 2)
        for depth in ['u8', 'u16', 'f32']:
            for n in [2, 4]:
                maximum = dict(u8=255, u16=65535, f32=1)[depth]
                def pixel(x, y):
                    codes = [1 + (x % 4 + y % 3 + c) % 5 for c in range(n-1)]
                    return [(c/8 if depth == 'f32' else c*maximum//8) for c in codes] + [maximum]
                clean = [v for y in range(h) for x in range(w) for v in pixel(x, y)]
                damaged = clean[:]
                for y in range(2, 4):
                    for x in range(127, 129):
                        damaged[(y*w+x)*n:(y*w+x+1)*n] = [maximum]*(n-1) + [maximum]
                for version in [None, 1, 2]:
                    with self.subTest(depth=depth, channels=n, version=version):
                        d = self.imported(w, h, damaged, depth, n, version)
                        original = self.raw(d)
                        f = legacy.fill(donor_region=legacy.region(0, 0, 12, 7))
                        result = self.apply(d, legacy.options(r, dict(type='fill', fill=f)))
                        self.assertEqual(self.raw(result['document']), bytes.fromhex(packed(clean, depth)))
                        self.assertEqual(self.raw(d), original)
                        detail = result['changes'][0]['details']
                        self.assertEqual(detail['changed_pixels'], 4)
                        self.assertEqual(detail['changed_bounds'], [127, 2, 129, 4])
                        self.assertEqual(detail['quantization'], 'final_native_depth_once')
                        self.assertEqual(detail['window_pixels'], 16)
                        self.assertEqual(detail['source_window_pixels'], 84)
                        self.assertEqual(detail['work'], detail['local_work'] + detail['source_preparation_work'])

    def test_typed_fill_replays_exhaustive_donor_minima_without_eight_bit_rounding(self):
        # The independent original repair oracle consumes normalized RGBA8-valued
        # floats, so nonintegral codes retain all input precision in its arithmetic.
        w, h = 15, 11
        clean = [[4001+(x%4)*7003, 7007+(y%3)*9001, 12001+((x+y)%3)*3331, 61001] for y in range(h) for x in range(w)]
        damaged = copy.deepcopy(clean)
        r = legacy.region(5, 4, 3, 3, [255, 128, 255, 255, 0, 255, 64, 255, 128])
        for i, weight in enumerate(legacy.weights(r, w, h)):
            if weight: damaged[i] = [65001, 123, 64003, 59003]
        f = legacy.fill(error=1, donor_region=legacy.region(0, 0, 5, 11))
        d = self.imported(w, h, [c for p in damaged for c in p])
        result = self.apply(d, legacy.options(r, dict(type='fill', fill=f), opacity=.625))
        scaled = [[c*255/65535 for c in p] for p in damaged]
        synthesized, coverage = legacy.replay_synthesis(scaled, scaled, w, h, w, h, r, f,
            result['changes'][0]['details']['action']['synthesis'])
        expected = bytearray(self.raw(d))
        for i, weight in enumerate(coverage):
            before = native.legacy.pm(scaled[i])
            value = [a+(b-a)*weight*.625 for a, b in zip(before, synthesized[i])]
            if value == before: continue
            straight = [c/value[3] for c in value[:3]] + [value[3]] if value[3] else [0]*4
            expected[i*8:(i+1)*8] = struct.pack('<4H', *(int(max(0,min(1,c))*65535+.5) for c in straight))
        self.assertEqual(self.raw(result['document']), expected)

    def test_distant_move_two_megapixels_reads_disjoint_windows_preserves_every_byte(self):
        w, h = 4096, 512
        background = [10003, 20011, 30013, 65535]
        values = background * (w*h)
        r = legacy.region(127, 127, 2, 2)
        for y in range(127, 129):
            for x in range(127, 129):
                values[(y*w+x)*4:(y*w+x+1)*4] = [50001+x, 40003+y, 12347, 65535]
        d = self.imported(w, h, values)
        original = self.raw(d)
        f = legacy.fill(donor_region=legacy.region(0, 0, 5, 5))
        o = legacy.options(r, dict(type='move', offset=[3840, 256], fill=f))
        result = self.apply(d, o)
        expected = bytearray(original)
        for y in range(127, 129):
            for x in range(127, 129):
                a = (y*w+x)*8; b = ((y+256)*w+x+3840)*8
                expected[a:a+8] = struct.pack('<4H', *background)
                expected[b:b+8] = original[a:a+8]
        self.assertEqual(self.raw(result['document']), expected)
        self.assertEqual(self.raw(d), original)
        receipt = result['changes'][0]['details']
        self.assertEqual(receipt['window_pixels'], 32)
        self.assertEqual(receipt['source_window_pixels'], 25)
        self.assertEqual(receipt['changed_pixels'], 8)
        self.assertEqual(receipt['source_preparation_work'], w*h*3)
        self.apply(d, legacy.options(r, dict(type='fill', fill=legacy.fill())), error='RESOURCE_LIMIT')

    def test_patch_search_and_healing_use_true_native_precision(self):
        w, h = 7, 6
        source = [[7001+x*277, 13003+y*577, 25007+x*y*31, 55001+x*233] for y in range(h) for x in range(w)]
        target = [[20003+x*31, 21001+y*71, 34003+x+y, 59003] for y in range(h) for x in range(w)]
        r = legacy.region(2, 2, 3, 2, [255, 128, 0, 64, 255, 255])
        for mode in ['clone', 'heal']:
            d = self.imported(w, h, [c for p in target for c in p])
            item = self.imported(w, h, [c for p in source for c in p], version=None)['items'][0]
            item['id'] = 'source'; item['visible'] = False; d['items'].append(item)
            blend = dict(type=mode, **(dict(screening=.25, tolerance=1e-12) if mode=='heal' else {}))
            a = dict(type='patch', source_id='source', source_origin=[2, 2], max_context_rms=1, blend=blend)
            o = legacy.options(r, a, opacity=.625)
            expected = native.oracle(target, source, w, h, dict(source_id='source', region=r, mode=blend, opacity=.625))
            result = self.apply(d, o)
            self.assert_codes(self.raw(result['document']), expected)
            self.assertEqual(result['document']['items'][1], item)
            self.assertEqual(result['changes'][0]['details']['action']['source_origin'], [2, 2])
        # Search must choose using sixteen-bit context, not an RGBA8 preview.
        target = copy.deepcopy(source); target[3*w+3] = [65000, 0, 65000, 65535]
        d = self.imported(w, h, [c for p in target for c in p])
        src = self.imported(w, h, [c for p in source for c in p])['items'][0]
        src['id']='source'; src['visible']=False; d['items'].append(src)
        a=dict(type='patch', source_id='source', source_origin=[2, 2], search_radius=2, max_context_rms=0, blend=dict(type='clone'))
        result=self.apply(d, legacy.options(legacy.region(3,3,1,1), a))
        self.assertEqual(result['changes'][0]['details']['action']['source_origin'], [3,3])
        self.assertEqual(self.raw(result['document']),bytes.fromhex(packed([c for p in source for c in p],'u16')))

    def test_guided_quantiles_soft_alpha_selection_and_final_native_quality_gate(self):
        w,h=8,7
        target=[[4001+x*203,13001+y*407,27011+x*y*113,53003+x*71] for y in range(h) for x in range(w)]
        target[3*w+3]=[62003,1009,65001,61001]
        guide=[[12001,14003,17011,65535]]*(w*h)
        d=self.imported(w,h,[c for p in target for c in p])
        src=self.imported(w,h,[c for p in guide for c in p],version=1)['items'][0]
        src['id']='source';src['locked']=True;d['items'].append(src)
        selected=bytes(128 if x>=3 else 0 for y in range(h) for x in range(w))
        d['selection']=dict(width=w,height=h,gray_hex=selected.hex())
        r=legacy.region(2,2,3,3,[255,128,255,255,255,0,64,255,255])
        a=dict(type='edge_correct',guide_id='source',radius=2,range_sigma=.1,max_change_rms=1,minimum_effective_samples=2)
        o=legacy.options(r,a,opacity=.625,use_selection=True)
        result=self.apply(d,o); expected=bytearray(self.raw(d)); maximum=0
        pm=lambda p:[c/65535*(p[3]/65535) for c in p[:3]]+[p[3]/65535]
        before=list(map(pm,target))
        for i,weight in enumerate(legacy.weights(r,w,h)):
            weight*=selected[i]/255
            if not weight:continue
            samples=[(j,(3-abs(dx))*(3-abs(dy))) for j,dx,dy in legacy.window(i,w,h,2)]
            total=sum(v for _,v in samples); channels=[]
            for k in range(4):
                accum=0
                for value,j,v in sorted((before[j][k],j,v) for j,v in samples):
                    accum+=v
                    if accum>=total/2: channels.append(value); break
            value=[old+(new-old)*weight*.625 for old,new in zip(before[i],channels)]
            if value!=before[i]:
                raw=[int(max(0,min(1,c/value[3]))*65535+.5) for c in value[:3]]+[int(value[3]*65535+.5)]
                expected[i*8:(i+1)*8]=struct.pack('<4H',*raw)
                maximum=max(maximum,math.sqrt(legacy.mse(before[i],pm(raw))))
        self.assertEqual(self.raw(result['document']),expected)
        receipt=result['changes'][0]['details']['action']
        self.assertAlmostEqual(receipt['maximum_change_rms'],maximum,places=14)
        failed=copy.deepcopy(o);failed['action']['max_change_rms']=maximum/2
        files=self.files();self.apply(d,failed,error='REPAIR_QUALITY');self.assertEqual(self.files(),files)
        self.assertEqual(result['document']['items'][1],src)

    def test_hidden_float_bits_noops_encoding_and_gray_conversion_refusals(self):
        hidden=[-0.0,struct.unpack('<f',b'\1\0\0\0')[0],.5,0.0]*35
        d=self.imported(7,5,hidden,depth='f32');original=self.raw(d)
        o=legacy.options(legacy.region(2,2,1,1),dict(type='edge_correct',guide_id='pixels',radius=1,range_sigma=.1,max_change_rms=0))
        self.assertEqual(self.raw(self.apply(d,o)['document']),original)
        gray=self.imported(7,5,[30001,65535]*35,n=2)
        source=self.imported(7,5,[10003,20011,30013,65535]*35)['items'][0]
        source['id']='source';gray['items'].append(source)
        f=legacy.fill('source',error=1)
        files=self.files()
        self.apply(gray,legacy.options(legacy.region(2,2,1,1),dict(type='fill',fill=f)),error='GRAYSCALE_CONVERSION_REQUIRED')
        self.assertEqual(self.files(),files)
        path=self.root/'linear.tiff';path.write_bytes(tiff(7,5,[.1,.2,.3,1.0]*35,depth='f32'))
        linear=self.cli('sample.import',source_path=str(path),id='linear',color_policy='assume_linear_srgb',storage={})['document']
        self.apply(linear,o,error='UNSUPPORTED_REPAIR_ENCODING')

    def test_mcp_dry_run_retry_undo_and_quality_failures_preserve_resources(self):
        w,h=138,7;values=[10003,20011,30013,65535]*(w*h)
        values[(3*w+127)*4:(3*w+128)*4]=[61001,123,64003,65535]
        d=self.imported(w,h,values);original=self.raw(d);self.save(d)
        o=legacy.options(legacy.region(127,3,1,1),dict(type='fill',fill=legacy.fill(donor_region=legacy.region(0,0,5,5))))
        action=dict(type='edit',operations=[dict(op='repair',id='pixels',options=o)])
        files=self.files()
        with closing(Client(('--tools','core'),workspace=self.root)) as c:
            c.initialize()
            proposal=c.success('session.dry_run',session_id='work',request_id='repair',expected_revision=0,action=action,options=dict(include_document=True))
            self.assertEqual(self.files(),files)
            saved=c.success('session.apply_proposal',proposal=proposal['proposal'],action=action)
            projected = copy.deepcopy(proposal['proposed_document'])
            staged = projected['items'][0]['content']['grid'].pop('staged')
            self.assertTrue(staged['pending'])
            self.assertEqual(saved['document'],projected)
            self.assertEqual(saved['receipt'],proposal['predicted_receipt'])
            self.assertTrue(c.success('session.apply_proposal',proposal=proposal['proposal'],action=action)['replayed'])
            self.assertNotEqual(self.raw(saved['document']),original)
            undone=c.success('session.apply',session_id='work',request_id='undo',expected_revision=1,action=dict(type='undo'))
            self.assertEqual(self.raw(undone['document']),original)
            redone=c.success('session.apply',session_id='work',request_id='redo',expected_revision=2,action=dict(type='redo'))
            self.assertEqual(self.raw(redone['document']),self.raw(saved['document']))
            c.success('session.apply',session_id='work',request_id='undo-again',expected_revision=3,action=dict(type='undo'))
        failed=copy.deepcopy(action)
        failed['operations'][0]['options']['max_boundary_rms']=0
        # A soft repair leaves a nonzero seam and must not advance the session.
        failed['operations'][0]['options']['opacity']=.5
        files=self.files()
        self.cli('session.apply',session_id='work',request_id='reject',expected_revision=4,action=failed,error='REPAIR_QUALITY')
        self.assertEqual(self.files(),files)

    def test_far_dependency_corruption_rejected_despite_local_window(self):
        w,h=260,7;values=[10003,20011,30013,65535]*(w*h)
        d=self.imported(w,h,values)
        name=d['items'][0]['content']['grid']['base']['tiles'][-1]
        path=self.root/'.inkbolt/assets'/f'{name}.native-tile'
        blob=path.read_bytes();path.write_bytes(blob[:-1]+bytes([blob[-1]^1]))
        o=legacy.options(legacy.region(2,2,1,1),dict(type='edge_correct',guide_id='pixels',radius=1,range_sigma=.1,max_change_rms=1))
        self.apply(d,o,error='SAMPLE_TILE_CORRUPT')

    def test_self_donor_exclusion_move_overlap_boundaries_and_atomic_rejections(self):
        w,h=138,7; background=[10003,20011,30013,65535]
        values=background*(w*h)
        for x in [127,128]: values[(3*w+x)*4:(3*w+x+1)*4]=[50001+x,40003,12347,65535]
        d=self.imported(w,h,values); original=self.raw(d)
        r=legacy.region(127,3,2,1)
        f=legacy.fill(donor_region=legacy.region(124,0,10,7))
        for offset in [[1,0],[-1,0],[0,0]]:
            o=legacy.options(r,dict(type='move',offset=offset,fill=f))
            result=self.apply(d,o);expected=bytearray(original)
            if offset!=[0,0]:
                for x in [127,128]:expected[(3*w+x)*8:(3*w+x+1)*8]=struct.pack('<4H',*background)
                for x in [127,128]:expected[(3*w+x+offset[0])*8:(3*w+x+offset[0]+1)*8]=original[(3*w+x)*8:(3*w+x+1)*8]
            self.assertEqual(self.raw(result['document']),expected)
        o=legacy.options(r,dict(type='fill',fill=f));files=self.files()
        self.apply(d,o,control=dict(timeout_ms=0),error='TIMEOUT')
        locked=copy.deepcopy(d);locked['items'][0]['locked']=True
        self.apply(locked,o,error='LOCKED')
        bad=copy.deepcopy(o);bad['action']['fill']['donor_region']=legacy.region(127,3,2,1)
        self.apply(d,bad,error='REPAIR_QUALITY')
        bad=copy.deepcopy(o);bad['action']['fill']['donor_region']=legacy.region(0,0,3,3,[255]*8+[128])
        self.apply(d,bad,error='INVALID_REPAIR')
        bad=legacy.options(r,dict(type='move',offset=[100,0],fill=f))
        self.apply(d,bad,error='INVALID_REPAIR')
        bad=legacy.options(r,dict(type='patch',source_id='pixels',source_origin=[127,3],search_radius=0,max_context_rms=1,blend=dict(type='clone')))
        self.apply(d,bad,error='REPAIR_QUALITY')
        self.assertEqual(self.files(),files)

    def test_mixed_raster_target_typed_source_and_empty_domain_are_explicit(self):
        w,h=7,5
        d=self.imported(w,h,[50,70,90,255]*(w*h),depth='u8',version=None)
        d['items'][0]['content']=dict(type='raster',width=w,height=h,rgba_hex=self.raw(d).hex())
        values=[10003,20011,30013,65535]*(w*h)
        source=self.imported(w,h,values)['items'][0];source['id']='source';d['items'].append(source)
        o=legacy.options(legacy.region(2,2,1,1),dict(type='fill',fill=legacy.fill('source',error=1)))
        result=self.apply(d,o);expected=bytearray(self.raw(d))
        expected[(2*w+2)*4:(2*w+3)*4]=bytes(int(c*255/65535+.5) for c in values[:4])
        self.assertEqual(self.raw(result['document']),expected)
        detail=result['changes'][0]['details']
        self.assertEqual(detail['target_identity_kind'],'rgba8_image')
        self.assertEqual(detail['source_identity_kind'],'native_tile_manifest')
        empty=copy.deepcopy(o);empty['region']['gray_hex']='00'
        self.assertEqual(self.raw(self.apply(d,empty)['document']),self.raw(d))


if __name__=='__main__':
    unittest.main()
