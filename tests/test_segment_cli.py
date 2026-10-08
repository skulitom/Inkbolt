"""Local pixel assistance verified by enumeration, synthetic truth and atomic history."""
import base64
import copy
import random
import tempfile
import unittest
from pathlib import Path
import test_editing_cli as editing
import test_variants_cli as variants
from test_mcp import Client
from segment_reference import costs, exhaustive, original_document
from test_images_cli import png


class SegmentTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    edit=variants.VariantTests.edit
    def valid(self,d):return self.invoke(dict(command='document.validate',document=d))
    def segment(self,d,options,expected=0,**kw):return self.invoke(dict(command='assist.segment',document=d,id='pixels',options=options,**kw),expected)

    def test_minimum_energy_and_canonical_ties_against_all_labelings(self):
        rng=random.Random(718)
        for case in range(40):
            pixels=[[rng.randrange(4)*50 for _ in range(3)]+[rng.choice([0,128,255])] for _ in range(9)]
            o=dict(foreground=[[0,0]],background=[[2,2]],smoothness=rng.choice([0,1000,65535]),edge_scale=rng.choice([1,4096,260100]),include_costs=True)
            d=self.valid(original_document(pixels,3,3));r=self.segment(d,o);energy,mask,_=exhaustive(pixels,3,3,o);unary,pair,hard,_=costs(pixels,3,3,o)
            with self.subTest(case=case):
                self.assertEqual(r['minimum_energy'],energy);self.assertEqual(r['max_flow'],energy);self.assertEqual(r['data_cost']+r['boundary_cost'],energy)
                self.assertEqual(bytes.fromhex(r['mask']['gray_hex']),mask);self.assertEqual(r['class_costs'],unary);self.assertEqual(r['neighbor_costs'],[list(p) for p in pair]);self.assertEqual(r['hard_seed_cost'],hard)
                self.assertEqual(self.segment(d,o),r)

    def test_uniform_tie_uses_smallest_foreground_and_transparent_rgb_is_ignored(self):
        pixels=[[i*25,255-i*25,50,0] for i in range(9)];o=dict(foreground=[[1,1]],background=[[0,0]],smoothness=0)
        r=self.segment(self.valid(original_document(pixels,3,3)),o);self.assertEqual(r['minimum_energy'],0);self.assertEqual(bytes.fromhex(r['mask']['gray_hex']),bytes([0,0,0,0,255,0,0,0,0]))

    def test_neighbor_evidence_repairs_isolated_color_errors_in_an_original_object(self):
        w=h=48;pixels=[];truth=[]
        for y in range(h):
            for x in range(w):
                inside=12<=x<36 and 12<=y<36;v=120 if inside else 100
                if (x,y) in [(20,20),(28,29),(4,4),(42,39)]:v=220-v
                pixels.append([v,v,v,255]);truth.append(255 if inside else 0)
        o=dict(foreground=[[24,24]],background=[[0,0]])
        d=self.valid(original_document(pixels,w,h));r=self.segment(d,o);mask=bytes.fromhex(r['mask']['gray_hex']);self.assertEqual(mask,bytes(truth))
        unary_only=self.segment(d,dict(o,smoothness=0));self.assertNotEqual(unary_only['mask'],r['mask'])
        changed=self.edit(d,dict(op='assist_mask',id='pixels',options=o));self.assertEqual(changed['items'][0]['content'],d['items'][0]['content'])
        artifact=self.invoke(dict(command='document.export',document=changed,format='png'));rgba=editing.png_pixels(base64.b64decode(artifact['data']))[2]
        self.assertEqual(rgba[3::4],bytes(truth))
        for i,p in enumerate(pixels):self.assertEqual(rgba[i*4:i*4+4],bytes(p if truth[i] else [0,0,0,0]))

    def test_atomic_mask_replacement_locks_unknown_fields_and_cancel(self):
        d=self.valid(original_document([[120,120,120,255],[100,100,100,255]],2,1));o=dict(foreground=[[0,0]],background=[[1,0]])
        changed=self.edit(d,dict(op='assist_mask',id='pixels',options=o));self.assertEqual(self.edit(changed,dict(op='assist_mask',id='pixels',options=o),expected=1)['code'],'INVALID_ASSISTANCE')
        self.assertEqual(self.edit(changed,dict(op='assist_mask',id='pixels',options=o,replace_existing=True))['items'],changed['items'])
        locked=self.edit(d,dict(op='properties',id='pixels',locked=True));self.assertEqual(self.edit(locked,dict(op='assist_mask',id='pixels',options=o),expected=1)['code'],'LOCKED')
        self.assertEqual(self.segment(d,dict(o,model='missing'),1)['code'],'INVALID_REQUEST')
        self.assertEqual(self.segment(d,o,1,control=dict(timeout_ms=0))['code'],'TIMEOUT')
        for patch in [dict(foreground=[]),dict(background=[[0,0]]),dict(foreground=[[2,0]]),dict(foreground=[[0,0],[0,0]]),dict(smoothness=65536),dict(edge_scale=0),dict(edge_scale=260101)]:self.assertEqual(self.segment(d,dict(o,**patch),1)['code'],'INVALID_ASSISTANCE')

    def test_mcp_mask_undo_retry_and_failed_edit_preserve_source(self):
        d=self.valid(original_document([[120,120,120,255],[100,100,100,255]],2,1));o=dict(foreground=[[0,0]],background=[[1,0]])
        client=Client();self.addCleanup(client.close);client.initialize()
        with tempfile.TemporaryDirectory() as root:
            s=dict(session_root=root,session_id='segment');client.success('session.create',**s,request_id='create',document=d)
            report=client.success('assist.segment',document=d,id='pixels',options=o);self.assertEqual(report,self.segment(d,o))
            action=dict(type='edit',operations=[dict(op='assist_mask',id='pixels',options=o)])
            changed=client.success('session.apply',**s,request_id='mask',expected_revision=0,action=action)['document'];self.assertEqual(changed['items'][0]['content'],d['items'][0]['content'])
            self.assertTrue(client.success('session.apply',**s,request_id='mask',expected_revision=0,action=action)['replayed'])
            failed=client.tool('session.apply',**s,request_id='repeat',expected_revision=1,action=action);self.assertTrue(failed['isError']);self.assertEqual(client.success('session.read',**s)['document'],changed)
            restored=client.success('session.apply',**s,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(restored['items'],d['items']);self.assertTrue(client.success('session.verify',**s)['valid'])

    def test_verified_asset_crop_native_seeds_linked_mask_and_source_file_preservation(self):
        pixels=bytes(v for y in range(6) for x in range(8) for v in ([220,30,40,255] if x<4 else [20,80,200,255]))
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);source=root/'original.png';source.write_bytes(png(8,6,pixels));store=root/'assets';original=source.read_bytes()
            asset=self.invoke(dict(command='asset.import',source_path=str(source),store_root=str(store)))['asset']
            d=self.valid(dict(schema_version=2,id='cropped-selection',kind='raster',width=16,height=16,color_space='srgb',assets={'source':asset},items=[dict(id='pixels',transform=[1,0,0,1,2,2],content=dict(type='image',asset_id='source',width=8,height=12,crop=dict(x=2,y=1,width=4,height=4)))]))
            o=dict(foreground=[[0,0]],background=[[3,3]],smoothness=0)
            r=self.segment(d,o,asset_root=str(store));self.assertEqual((r['width'],r['height']),(4,4));self.assertEqual(r['mask']['transform'],[2,0,0,3,0,0]);self.assertEqual(bytes.fromhex(r['mask']['gray_hex']),bytes([255,255,0,0]*4))
            changed=self.edit(d,dict(op='assist_mask',id='pixels',options=o),asset_root=str(store));self.assertEqual(changed['assets'],d['assets']);self.assertEqual(changed['items'][0]['content'],d['items'][0]['content'])
            image=self.invoke(dict(command='document.export',document=changed,format='png',asset_root=str(store)));rgba=editing.png_pixels(base64.b64decode(image['data']))[2]
            self.assertEqual(rgba[3::4],bytes(255 if 2<=x<6 and 2<=y<14 else 0 for y in range(16) for x in range(16)))
            self.assertEqual(source.read_bytes(),original)
            embedded=self.invoke(dict(command='asset.embed',asset=asset,asset_root=str(store)));other=copy.deepcopy(d);other['assets']['source']=embedded
            self.assertEqual(self.segment(other,o)['mask'],r['mask'])
            blob=store/(asset['sha256']+'.rgba8');before=blob.read_bytes();blob.write_bytes(before[:-1]+bytes([before[-1]^1]))
            self.assertEqual(self.segment(d,o,1,asset_root=str(store))['code'],'ASSET_CORRUPT')

    def test_maximum_native_grid_and_resource_excess_are_explicit(self):
        w=h=256;pixels=[[220,30,40,255] if x<128 else [20,80,200,255] for y in range(h) for x in range(w)]
        d=self.valid(original_document(pixels,w,h));o=dict(foreground=[[1,1]],background=[[255,255]])
        r=self.segment(d,o);self.assertEqual(bytes.fromhex(r['mask']['gray_hex']),bytes(255 if x<128 else 0 for y in range(h) for x in range(w)));self.assertLessEqual(r['work'],67108864)
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);source=root/'large.png';source.write_bytes(png(257,256,bytes([40,50,60,255])*(257*256)))
            asset=self.invoke(dict(command='asset.import',source_path=str(source),store_root=str(root/'assets')))['asset']
            large=self.valid(dict(schema_version=2,id='large-asset',kind='raster',width=257,height=256,color_space='srgb',assets={'source':asset},items=[dict(id='pixels',content=dict(type='image',asset_id='source',width=257,height=256))]))
            self.assertEqual(self.segment(large,o,1,asset_root=str(root/'assets'))['code'],'RESOURCE_LIMIT')
        unsupported=self.valid(dict(schema_version=2,id='vector-item',kind='vector',width=2,height=1,color_space='srgb',items=[dict(id='pixels',content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=2,height=1),fill=[40,50,60,255]))]))
        self.assertEqual(self.segment(unsupported,dict(foreground=[[0,0]],background=[[1,0]]),1)['code'],'UNSUPPORTED')

    def test_eight_bit_sample_modes_match_and_high_depth_never_converts_silently(self):
        pixels=[[200,200,200,255],[50,50,50,255]]*2;d=self.valid(original_document(pixels,2,2));o=dict(foreground=[[0,0]],background=[[1,0]],smoothness=0);expected=self.segment(d,o)['mask']
        for channels,data in [('rgba',bytes(v for p in pixels for v in p)),('gray_alpha',bytes(v for p in pixels for v in [p[0],p[3]]))]:
            sample=copy.deepcopy(d);sample['items'][0]['content']=dict(type='samples',grid=dict(width=2,height=2,depth='u8',channels=channels,data_hex=data.hex()));sample=self.valid(sample)
            self.assertEqual(self.segment(sample,o)['mask'],expected);changed=self.edit(sample,dict(op='assist_mask',id='pixels',options=o));self.assertEqual(changed['items'][0]['content'],sample['items'][0]['content'])
            high=copy.deepcopy(sample);grid=high['items'][0]['content']['grid'];grid['depth']='u16';grid['data_hex']=b''.join((b*257).to_bytes(2,'little') for b in data).hex();high=self.valid(high)
            self.assertEqual(self.segment(high,o,1)['code'],'UNSUPPORTED')
