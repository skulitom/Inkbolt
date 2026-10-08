"""Original ordered frame exchange, alpha/disposal, exact timing and retained editing."""
import base64
import copy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import test_editing_cli as editing
import test_variants_cli as variants
from test_images_cli import chunk, png
from test_mcp import Client
import sequence_fixtures as fixtures


class SequenceTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    edit=variants.VariantTests.edit

    def imported(self,root,data,**kw):
        path=Path(root)/'input.png';path.write_bytes(data)
        space=kw.pop('compositing_space','linear_srgb')
        request=dict(command='sequence.import',source=dict(type='apng',source_path=str(path),compositing_space=space),store_root=str(Path(root)/'assets'),id='sequence',**kw)
        d=self.invoke(request)['document'];self.assertEqual(path.read_bytes(),data)
        return d

    def export(self,d,root=None,**kw):
        return self.invoke(dict(command='document.export',document=d,format='apng',asset_root=str(Path(root)/'assets') if root else None,**kw))

    def originals(self):
        return [dict(rgba=bytes([190,60,20,128])*12,dispose=2,delay=(1,0)),
            dict(size=(2,2),offset=(1,1),rgba=bytes([20,160,220,64])*4,blend=1,dispose=0,delay=(3,7)),
            dict(size=(3,1),offset=(0,2),rgba=bytes([210,0,50,192])*3,blend=1,dispose=2,delay=(0,0)),
            dict(size=(1,2),offset=(3,0),rgba=bytes([10,20,240,0])*2,dispose=1,delay=(65535,65535)),
            dict(size=(2,1),offset=(2,2),rgba=bytes([40,200,120,255])*2,blend=1,delay=(1,24))]

    def test_subframes_disposal_alpha_default_poster_and_interlacing(self):
        frames=self.originals();expected=fixtures.reference(4,3,frames)
        # Display exports intentionally normalize colors beneath zero alpha.
        expected=[bytes(v if p[i//4*4+3] else 0 for i,v in enumerate(p)) for p in expected]
        for poster in [None,bytes([1,2,3,255])*12]:
            for interlace in [False,True]:
                with tempfile.TemporaryDirectory() as root:
                    d=self.imported(root,fixtures.apng(4,3,frames,plays=7,poster=poster,interlace=interlace));saved=copy.deepcopy(d)
                    a=self.export(d,root);w,h,plays,controls,pixels=fixtures.read_full(base64.b64decode(a['data']))
                    self.assertEqual((w,h,plays),(4,3,7));self.assertEqual(pixels,expected)
                    self.assertEqual([v[4:6] for v in controls],[f['delay'] for f in frames])
                    self.assertEqual(a['sequence']['frames'][0]['rgba_sha256'],hashlib.sha256(expected[0]).hexdigest())
                    if poster:self.assertFalse(next(i for i in d['items'] if i['id']=='poster')['visible'])
                    self.assertEqual(json.loads(self.invoke(dict(command='document.export',document=d,format='snapshot'))['data']),saved)

    def test_explicit_image_order_duplicate_states_names_and_source_hashes(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);sources=[];pixels=[]
            for name,rgba in [('zeta.png',[200,10,40,255]),('alpha.png',[10,30,220,128])]:
                p=root/name;p.write_bytes(png(3,2,bytes(rgba)*6));sources.append(p);pixels.append(bytes(rgba)*6)
            ordered=[sources[0],sources[1],sources[0]];delays=[(1,24),(3,100),(1,0)]
            req=dict(command='sequence.import',id='ordered',source=dict(type='images',plays=3,frames=[dict(source_path=str(p),delay=dict(numerator=n,denominator=d)) for p,(n,d) in zip(ordered,delays)]),store_root=str(root/'assets'))
            result=self.invoke(req);d=result['document'];a=self.export(d,root);decoded=fixtures.read_full(base64.b64decode(a['data']))
            self.assertEqual(decoded[4],[pixels[0],pixels[1],pixels[0]]);self.assertEqual(len(d['assets']),2)
            self.assertEqual([f['dataset'] for f in d['variants']['sequence']['frames']],['image-0','image-1','image-0'])
            for receipt,path in zip(result['source_receipts'],ordered):self.assertEqual(receipt['import']['asset']['provenance']['source_sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(self.invoke(req)['document'],d)

    def test_layer_conversion_variant_edits_readonly_locked_stills_and_loss_receipts(self):
        d=variants.VariantTests.document(self);original=copy.deepcopy(d)
        d=self.edit(d,dict(op='sequence_from_layers',ids=['badge','tile'],delay=dict(numerator=1,denominator=12),plays=0))
        self.assertEqual([i['content'] for i in d['items']],[i['content'] for i in original['items']])
        a=self.export(d);frames=fixtures.read_full(base64.b64decode(a['data']))[4]
        self.assertEqual(frames[0][(2*24+12)*4:(2*24+12)*4+4],bytes([20,100,230,255]))
        self.assertEqual(frames[0][(2*24+2)*4:(2*24+2)*4+4],bytes(4))
        d=self.edit(d,dict(op='properties',id='badge',locked=True),dict(op='properties',id='tile',locked=True))
        self.assertEqual(fixtures.read_full(base64.b64decode(self.export(d)['data']))[4],frames)
        still=self.invoke(dict(command='sequence.open',document=d,id='frame-1'))
        self.assertNotIn('variants',still['document']);self.assertTrue(still['source_preserved'])
        self.assertEqual(editing.png_pixels(base64.b64decode(self.invoke(dict(command='document.export',document=still['document'],format='png'))['data']))[2],frames[1])
        self.assertEqual(self.edit(d,dict(op='sequence_frame',id='frame-1'),expected=1)['code'],'LOCKED')
        self.assertFalse(any('Only the selected variant' in s for s in a['losses']))

    def test_rational_durations_zero_denominator_repeats_and_reference_validation(self):
        d=variants.VariantTests.document(self);d=self.edit(d,dict(op='sequence_from_layers',ids=['tile'],delay=dict(numerator=1,denominator=3)))
        delays=[(i%7,p) for i,p in enumerate([3,5,7,11,13,17,19,23,29,31,37,41,43,47,53,59,61,67,71,73])]
        timeline=dict(plays=4,frames=[dict(id='f'+str(i),dataset='frame-0',delay=dict(numerator=n,denominator=p)) for i,(n,p) in enumerate(delays)])
        d=self.edit(d,dict(op='sequence_set',sequence=timeline));a=self.invoke(dict(command='sequence.inspect',document=d));expected=sum((Fraction(n,p) for n,p in delays),Fraction())
        self.assertEqual(a['duration_seconds'],dict(numerator=str(expected.numerator),denominator=str(expected.denominator)))
        bad=copy.deepcopy(timeline);bad['frames'][0]['dataset']='missing'
        self.assertEqual(self.edit(d,dict(op='sequence_set',sequence=bad),expected=1)['code'],'INVALID_SEQUENCE')
        self.assertEqual(self.edit(d,dict(op='variants_clear',bake=True),expected=1)['code'],'INVALID_VARIANT')
        cleared=self.edit(d,dict(op='sequence_set',sequence=None),dict(op='variants_clear',bake=True));self.assertNotIn('variants',cleared)

    def test_corrupt_sequence_numbers_counts_rectangles_data_and_profiles_fail(self):
        data=fixtures.apng(4,3,self.originals());parts=fixtures.chunks(data);broken=[]
        for kind,offset,value in [(b'acTL',0,99),(b'fcTL',0,2),(b'fcTL',4,0),(b'fcTL',12,100)]:
            copy_parts=copy.deepcopy(parts)
            for i,(k,p) in enumerate(copy_parts):
                if k==kind:q=bytearray(p);struct.pack_into('>I',q,offset,value);copy_parts[i]=(k,bytes(q));break
            broken.append(copy_parts)
        broken.append([v for v in parts if v[0]!=b'fdAT'])
        broken.append(parts[:-1]+[(b'fcTL',parts[3][1]),parts[-1]])
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'bad.png'
            for items in broken:
                path.write_bytes(data[:8]+b''.join(chunk(k,p) for k,p in items))
                r=self.invoke(dict(command='sequence.import',id='bad',source=dict(type='apng',source_path=str(path)),store_root=str(Path(root)/'assets')),1)
                self.assertIn(r['code'],['INVALID_SEQUENCE','INVALID_IMAGE']);self.assertFalse((Path(root)/'assets').exists())
            path.write_bytes(fixtures.apng(4,3,self.originals(),tagged=False))
            self.assertEqual(self.invoke(dict(command='sequence.import',id='bad',source=dict(type='apng',source_path=str(path)),store_root=str(Path(root)/'assets')),1)['code'],'COLOR_POLICY_REQUIRED')
            self.assertIn('document',self.invoke(dict(command='sequence.import',id='ok',source=dict(type='apng',source_path=str(path)),store_root=str(Path(root)/'assets'),color_policy='assume_srgb')))

    def test_mcp_sequence_timing_history_publication_retry_and_cancellation(self):
        d=variants.VariantTests.document(self);d=self.edit(d,dict(op='sequence_from_layers',ids=['tile','badge'],delay=dict(numerator=1,denominator=24)))
        client=Client();self.addCleanup(client.close);client.initialize()
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='sequence');client.success('session.create',**session,request_id='create',document=d)
            timeline=copy.deepcopy(d['variants']['sequence']);timeline['frames'].reverse();timeline['frames'][0]['delay']=dict(numerator=3,denominator=0)
            action=dict(type='edit',operations=[dict(op='sequence_set',sequence=timeline)])
            changed=client.success('session.apply',**session,request_id='timing',expected_revision=0,action=action)['document']
            self.assertEqual(client.success('sequence.inspect',document=changed)['frames'][0]['id'],'frame-1')
            output=dict(output_root=root,file_name='animation.apng',format='apng')
            receipt=client.success('session.publish',**session,expected_revision=1,output=output);self.assertEqual(receipt['sequence']['frames'][0]['delay'],dict(numerator=3,denominator=0))
            self.assertEqual(client.tool('session.publish',**session,expected_revision=1,output=output)['structuredContent']['error']['code'],'OUTPUT_EXISTS')
            self.assertEqual(client.tool('session.publish',**session,expected_revision=1,output=dict(output,file_name='cancelled.apng'),control=dict(timeout_ms=0))['structuredContent']['error']['code'],'TIMEOUT');self.assertFalse((Path(root)/'cancelled.apng').exists())
            self.assertEqual(client.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'))['document']['variants']['sequence'],d['variants']['sequence'])
            self.assertEqual(client.success('session.apply',**session,request_id='redo',expected_revision=2,action=dict(type='redo'))['document']['variants']['sequence'],timeline)
            self.assertTrue(client.success('session.apply',**session,request_id='timing',expected_revision=0,action=action)['replayed']);self.assertTrue(client.success('session.verify',**session)['valid'])

    def test_png_frame_artifacts_metadata_scale_and_source_preservation(self):
        d=variants.VariantTests.document(self);d=self.edit(d,dict(op='sequence_from_layers',ids=['tile','badge'],delay=dict(numerator=1,denominator=20)))
        d['metadata']=dict(title='Frame collection',private={'draft':'private-note'})
        before=copy.deepcopy(d)
        a=self.invoke(dict(command='sequence.export',document=d,scale=2,render_options=dict(antialias='none'),metadata_policy=dict(mode='public',provenance=True)))
        self.assertEqual((a['width'],a['height']),(48,24));self.assertEqual([f['file_name'] for f in a['frames']],['frame-0000.png','frame-0001.png'])
        animation=fixtures.read_full(base64.b64decode(self.export(d,scale=2,render_options=dict(antialias='none'))['data']))[4]
        for i,f in enumerate(a['frames']):
            raw=base64.b64decode(f['artifact']['data']);self.assertEqual(f['sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual(editing.png_pixels(raw)[2],animation[i]);self.assertNotIn(b'private-note',raw)
        self.assertEqual(d,before)
        self.assertEqual(self.invoke(dict(command='sequence.export',document=d,control=dict(timeout_ms=0)),1)['code'],'TIMEOUT')

    def test_palette_gray_rgb_transparency_and_native_depth_rejection(self):
        fixtures_by_color=[
            (png(2,1,b'',color=2,raw=b'\0\x0a\x14\x1e\x28\x32\x3c'),bytes([10,20,30,255,40,50,60,255])),
            (png(2,1,b'',color=0,raw=b'\0\x40\xc0'),bytes([64,64,64,255,192,192,192,255])),
            (png(2,1,b'',color=4,raw=b'\0\x40\x80\xc0\xff'),bytes([64,64,64,128,192,192,192,255])),
            (png(2,1,b'',color=3,depth=1,raw=b'\0\x40',extra=[(b'PLTE',bytes([10,20,30,40,50,60])),(b'tRNS',bytes([128,255]))]),bytes([10,20,30,128,40,50,60,255]))]
        for raw,expected in fixtures_by_color:
            parts=fixtures.chunks(raw);animated=[]
            for kind,p in parts:
                if kind==b'IDAT':animated.extend([(b'acTL',struct.pack('>II',1,1)),(b'fcTL',struct.pack('>IIIIIHHBB',0,2,1,0,0,1,5,0,0))])
                animated.append((kind,p))
            with tempfile.TemporaryDirectory() as root:
                d=self.imported(root,raw[:8]+b''.join(chunk(k,p) for k,p in animated))
                self.assertEqual(fixtures.read_full(base64.b64decode(self.export(d,root)['data']))[4],[expected])
        with tempfile.TemporaryDirectory() as root:
            data=fixtures.apng(4,3,self.originals());parts=fixtures.chunks(data);p=bytearray(parts[0][1]);p[8]=16;parts[0]=(b'IHDR',bytes(p));path=Path(root)/'deep.png';path.write_bytes(data[:8]+b''.join(chunk(k,p) for k,p in parts))
            self.assertEqual(self.invoke(dict(command='sequence.import',source=dict(type='apng',source_path=str(path)),id='deep',store_root=str(Path(root)/'assets')),1)['code'],'UNSUPPORTED')

    def test_limits_missing_resources_failed_publication_and_mismatched_frames(self):
        with tempfile.TemporaryDirectory() as root:
            d=self.imported(root,fixtures.apng(4,3,self.originals()))
            asset=next(iter(d['assets'].values()));stored=Path(root)/'assets'/(asset['sha256']+'.rgba8');stored.write_bytes(b'corrupt-test-copy')
            output=dict(output_root=root,file_name='failed.apng',format='apng')
            self.assertEqual(self.invoke(dict(command='document.publish',document=d,resources=dict(asset_root=str(Path(root)/'assets')),output=output),1)['code'],'ASSET_CORRUPT');self.assertFalse((Path(root)/'failed.apng').exists())
            first=Path(root)/'first.png';second=Path(root)/'second.png';first.write_bytes(png(1,1,bytes([1,2,3,255])));second.write_bytes(png(2,1,bytes([1,2,3,255])*2))
            source=dict(type='images',frames=[dict(source_path=str(p),delay=dict(numerator=1,denominator=10)) for p in [first,second]])
            self.assertEqual(self.invoke(dict(command='sequence.import',source=source,id='mismatch',store_root=str(Path(root)/'other-assets')),1)['code'],'INVALID_SEQUENCE')
            self.assertEqual(first.read_bytes(),png(1,1,bytes([1,2,3,255])))
        d=variants.VariantTests.document(self);d=self.edit(d,dict(op='sequence_from_layers',ids=['tile'],delay=dict(numerator=1,denominator=10)))
        timeline=dict(frames=[dict(id='f'+str(i),dataset='frame-0',delay=dict(numerator=1,denominator=24)) for i in range(256)])
        d=self.edit(d,dict(op='sequence_set',sequence=timeline));self.assertEqual(len(fixtures.read_full(base64.b64decode(self.export(d)['data']))[4]),256)
        timeline['frames'].append(dict(id='overflow',dataset='frame-0',delay=dict(numerator=1,denominator=1)))
        self.assertEqual(self.edit(d,dict(op='sequence_set',sequence=timeline),expected=1)['code'],'RESOURCE_LIMIT')

    def test_existing_variant_position_opacity_and_definition_updates_keep_timing(self):
        d=variants.VariantTests.document(self);d=variants.VariantTests.define(self,d,variants.VariantTests.definition(self))
        timeline=dict(plays=2,frames=[dict(id='first',dataset='moved',delay=dict(numerator=1,denominator=7)),dict(id='second',dataset='child',delay=dict(numerator=2,denominator=7))])
        d=self.edit(d,dict(op='sequence_set',sequence=timeline))
        original=copy.deepcopy(d);a=self.export(d);pixels=fixtures.read_full(base64.b64decode(a['data']))[4]
        for p in pixels:self.assertEqual(p[(4*24+6)*4:(4*24+6)*4+4],bytes([200,40,20,255]))
        self.assertEqual(pixels[0][(2*24+12)*4:(2*24+12)*4+4],bytes([20,100,230,255]));self.assertEqual(pixels[1][(2*24+12)*4:(2*24+12)*4+4],bytes(4))
        definition=copy.deepcopy(d['variants']['definition']);definition['datasets']['moved']['values']['place']['value']=[3,5]
        d=self.edit(d,dict(op='variants_set',definition=definition));self.assertEqual(d['variants']['sequence'],timeline)
        definition['datasets'].pop('child');self.assertEqual(self.edit(d,dict(op='variants_set',definition=definition),expected=1)['code'],'INVALID_SEQUENCE')
        self.assertEqual(original['items'],variants.VariantTests.document(self)['items'])


    def test_linear_and_encoded_frame_composition_are_explicit(self):
        frames=[dict(rgba=bytes([0,0,0,255])*2),dict(rgba=bytes([255,255,255,128])*2,blend=1)]
        for space,wanted in [('linear_srgb',188),('encoded_srgb',128)]:
            with tempfile.TemporaryDirectory() as root:
                d=self.imported(root,fixtures.apng(2,1,frames),compositing_space=space)
                self.assertEqual(fixtures.read_full(base64.b64decode(self.export(d,root)['data']))[4][1],bytes([wanted,wanted,wanted,255])*2)
                a=self.invoke(dict(command='sequence.import',source=dict(type='apng',source_path=str(Path(root)/'input.png')),store_root=str(Path(root)/'assets'),id='default'))
                self.assertEqual(a['source_receipts'][-1]['compositing_space'],'linear_srgb')

    def test_aggregate_supersampling_and_padding_work_is_bounded(self):
        d=variants.VariantTests.document(self);d['width']=128;d['height']=128
        d=self.edit(d,dict(op='sequence_from_layers',ids=['tile'],delay=dict(numerator=1,denominator=10)))
        timeline=dict(plays=0,frames=[dict(id=f'f{i}',dataset='frame-0',delay=dict(numerator=1,denominator=10)) for i in range(256)])
        d=self.edit(d,dict(op='sequence_set',sequence=timeline))
        for options in [dict(antialias='supersample4'),dict(padding=256)]:
            for command in ['sequence.export','document.export']:
                q=dict(command=command,document=d,render_options=options)
                if command=='document.export':q['format']='apng'
                self.assertEqual(self.invoke(q,1)['code'],'RESOURCE_LIMIT')


if __name__=='__main__':unittest.main()
