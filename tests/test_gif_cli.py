"""Exact-palette GIF, original compressed streams and retained sequence controls."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import gif_fixtures as gif
import test_editing_cli as editing
import test_variants_cli as variants
from test_mcp import Client


class GifTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    edit=variants.VariantTests.edit

    def document(self,width,height,rgba):
        d=self.invoke(dict(command='document.create',id='gif-original',kind='raster',width=width,height=height))
        d['items']=[dict(id='pixels',content=dict(type='raster',width=width,height=height,rgba_hex=rgba.hex()))];return d

    def imported(self,root,data,sequence=False,expected=0,**kw):
        source=Path(root)/'original.gif';source.write_bytes(data);store=Path(root)/'assets'
        req=dict(command='sequence.import',id='gif',source=dict(type='gif',source_path=str(source),**kw),store_root=str(store),color_policy='assume_srgb') if sequence else dict(command='asset.import',source_path=str(source),store_root=str(store),color_policy='assume_srgb',**kw)
        result=self.invoke(req,expected);self.assertEqual(source.read_bytes(),data)
        if expected:return result
        if sequence:return result
        a=result['asset'];self.assertEqual(a['provenance']['source_sha256'],hashlib.sha256(data).hexdigest())
        return result,(store/(a['sha256']+'.rgba8')).read_bytes()[16:]

    def export(self,d,root=None,**kw):
        return self.invoke(dict(command='document.export',document=d,format='gif',asset_root=str(Path(root)/'assets') if root else None,**kw))

    def test_exact_palette_stills_transparency_and_all_256_opaque_colors(self):
        for transparent in (False,True):
            pixels=bytes(c for y in range(13) for x in range(17) for c in ([0,0,0,0] if transparent and (x+y)%5==0 else [30*(x%6),40*(y%5),90,255]))
            d=self.document(17,13,pixels);saved=copy.deepcopy(d);a=self.export(d);decoded=gif.decode(base64.b64decode(a['data']))
            self.assertEqual(decoded['frames'],[pixels]);self.assertEqual(decoded['controls'][0][1],0);self.assertIsNone(decoded['loop'])
            with tempfile.TemporaryDirectory() as root:self.assertEqual(self.imported(root,base64.b64decode(a['data']))[1],pixels)
            self.assertEqual(d,saved)
        pixels=bytes(c for i in range(256) for c in [i,255-i,(i*37)%256,255]);d=self.document(256,1,pixels)
        self.assertEqual(gif.decode(base64.b64decode(self.export(d)['data']))['frames'],[pixels])

    def test_compressed_dictionary_width_growth_deferred_clear_and_kwkwk(self):
        palette=[(i,255-i,(i*31)%256) for i in range(256)]
        indices=bytes(i%256 for i in range(12000))
        samples=[(indices,[256,*indices,257]),(bytes(5151),[256,0,*range(258,358),257])]
        with tempfile.TemporaryDirectory() as root:
            for indices,codes in samples:
                data=gif.fixture(len(indices),1,[dict(indices=indices,compressed=gif.codes(codes))],global_palette=palette)
                actual=self.imported(root,data)[1];expected=bytes(c for i in indices for c in [*palette[i],255]);self.assertEqual(actual,expected)
            for minimum in (2,3,4,5,6,7,8):
                indices=bytes(i%4 for i in range(140));data=gif.fixture(14,10,[dict(indices=indices,minimum=minimum)])
                self.assertEqual(self.imported(root,data)[1],gif.decode(data)['frames'][0])

    def test_sequence_rectangles_disposal_interlace_local_palettes_background_and_loops(self):
        frames=[dict(indices=bytes([1])*35,delay=10,disposal=1),
            dict(size=(3,3),offset=(1,1),indices=bytes([0,1,2]*3),alpha=0,delay=20,disposal=3,palette=[(0,0,0),(0,200,200),(200,200,0),(30,30,30)],interlaced=True),
            dict(size=(2,4),offset=(4,0),indices=bytes([2,0]*4),alpha=0,delay=30,disposal=2),
            dict(indices=bytes([0,3,0,0,0])*7,alpha=0,delay=40,disposal=1,interlaced=True)]
        for repeats in (None,0,1,7,65535):
            data=gif.fixture(7,5,frames,repeats=repeats);expected=gif.decode(data)
            with tempfile.TemporaryDirectory() as root:
                result=self.imported(root,data,True);d=result['document'];saved=copy.deepcopy(d)
                actual=gif.decode(base64.b64decode(self.export(d,root)['data']))
                self.assertEqual(actual['frames'],expected['frames']);self.assertEqual([c[1] for c in actual['controls']],[10,20,30,40])
                self.assertEqual(d['variants']['sequence']['plays'],1 if repeats is None else 0 if repeats==0 else repeats+1)
                self.assertEqual(actual['loop'],repeats);self.assertEqual(d,saved)
                self.assertEqual(self.imported(root,data,expected=1)['code'],'UNSUPPORTED')
        data=gif.fixture(3,1,[dict(indices=bytes([0,1,0]),alpha=0)],background=2)
        with tempfile.TemporaryDirectory() as root:
            result=self.imported(root,data,True,background='logical_screen');d=result['document']
            p=gif.decode(base64.b64decode(self.export(d,root)['data']))['frames'][0]
            self.assertEqual(p,bytes([30,190,50,255,220,20,40,255,30,190,50,255]))

    def test_public_and_stripped_metadata_and_profile_boundaries(self):
        d=self.document(3,2,bytes([70,110,150,255])*6);d['metadata']=dict(title='Original icons',private={'note':'do-not-publish'})
        for mode in ('public','strip'):
            a=self.export(d,metadata_policy=dict(mode=mode,provenance=True));data=base64.b64decode(a['data']);parts=gif.decode(data)['comments']
            self.assertEqual(len(parts),1);self.assertNotIn(b'do-not-publish',data)
            packet=json.loads(parts[0].removeprefix(b'Inkbolt metadata v1\n'));self.assertEqual(packet['document'],{'title':'Original icons'} if mode=='public' else None)
            with tempfile.TemporaryDirectory() as root:
                r,p=self.imported(root,data);self.assertEqual(r['metadata']['envelope'],packet)
                r=self.imported(root,data,True);self.assertEqual(r['source_receipts'][0]['metadata']['envelope'],packet)
        d['output_profile']=dict(type='builtin',name='display_p3')
        self.assertEqual(self.invoke(dict(command='document.export',document=d,format='gif'),1)['code'],'UNSUPPORTED')

    def test_palette_alpha_and_timing_losses_require_explicit_source_changes(self):
        sources=[(self.document(1,1,bytes([40,80,150,128])),'UNSUPPORTED_GIF_ALPHA'),
            (self.document(257,1,bytes(c for i in range(257) for c in [i%256,i//256,0,255])),'UNSUPPORTED_GIF_PALETTE'),
            (self.document(257,1,bytes(c for i in range(257) for c in [i%256,0,0,0 if i==256 else 255])),'UNSUPPORTED_GIF_PALETTE')]
        for d,code in sources:self.assertEqual(self.invoke(dict(command='document.export',document=d,format='gif'),1)['code'],code)
        d=self.document(1,1,bytes([40,80,150,255]));d=self.edit(d,dict(op='sequence_from_layers',ids=['pixels'],delay=dict(numerator=1,denominator=24)))
        self.assertEqual(self.invoke(dict(command='document.export',document=d,format='gif'),1)['code'],'UNSUPPORTED_GIF_TIMING')
        for delay in (dict(numerator=65535,denominator=1),dict(numerator=65535,denominator=100)):
            t=copy.deepcopy(d['variants']['sequence']);t['frames'][0]['delay']=delay;v=self.edit(d,dict(op='sequence_set',sequence=t))
            if delay['denominator']==1:self.assertEqual(self.invoke(dict(command='document.export',document=v,format='gif'),1)['code'],'UNSUPPORTED_GIF_TIMING')
            else:self.assertEqual(gif.decode(base64.b64decode(self.export(v)['data']))['controls'][0][1],65535)

    def test_malformed_blocks_compressed_codes_frames_controls_and_metadata_publish_nothing(self):
        valid=gif.fixture(2,2,[dict(indices=bytes([1,2,3,0]))]);cases=[valid[:n] for n in range(len(valid))]+[valid+b'extra']
        for codes in ([256,1,257],[256,258,257],[256,1,2,3,0,0,257],[256,1,400,257],[1,2,3,0,257]):
            cases.append(gif.fixture(2,2,[dict(indices=bytes(4),compressed=gif.codes(codes))]))
        cases += [gif.fixture(2,2,[dict(indices=bytes(4),alpha=7)]),gif.fixture(2,2,[dict(indices=bytes(4),disposal=7)]),gif.fixture(2,2,[dict(size=(3,2),indices=bytes(6))])]
        cases += [valid[:-1]+b'\x21\xff\x0bUNKNOWN-1.0\0\x3b',gif.fixture(2,2,[dict(indices=bytes(4))],comments=[b'Inkbolt metadata v1\n{}'])]
        with tempfile.TemporaryDirectory() as root:
            for i,data in enumerate(cases):
                path=Path(root)/f'{i}.gif';path.write_bytes(data);store=Path(root)/f'store{i}'
                r=self.invoke(dict(command='sequence.import',id='bad',source=dict(type='gif',source_path=str(path)),store_root=str(store),color_policy='assume_srgb'),1)
                self.assertIn(r['code'],['INVALID_IMAGE','INVALID_METADATA','UNSUPPORTED','RESOURCE_LIMIT']);self.assertFalse(store.exists());self.assertEqual(path.read_bytes(),data)
            self.assertEqual(len(self.imported(root,valid)[1]),16)

    def test_color_policy_deadlines_and_resource_limits(self):
        data=gif.fixture(1,1,[dict(indices=b'\x01')])
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'source.gif';path.write_bytes(data)
            req=dict(command='sequence.import',id='bounded',source=dict(type='gif',source_path=str(path)),store_root=str(Path(root)/'assets'))
            self.assertEqual(self.invoke(req,1)['code'],'COLOR_POLICY_REQUIRED')
            self.assertEqual(self.invoke(dict(req,color_policy='assume_srgb',control=dict(timeout_ms=0)),1)['code'],'TIMEOUT')
            self.assertFalse((Path(root)/'assets').exists())
            data=gif.fixture(1,1,[dict(indices=b'\x01')]*257);path.write_bytes(data)
            self.assertEqual(self.invoke(dict(req,color_policy='assume_srgb'),1)['code'],'RESOURCE_LIMIT');self.assertFalse((Path(root)/'assets').exists())

    def test_global_background_index_is_validated_before_any_asset_publication(self):
        data=gif.fixture(2,2,[dict(indices=bytes([1,2,3,0]))],background=255)
        with tempfile.TemporaryDirectory() as root:
            for background in ('transparent','logical_screen'):
                result=self.imported(root,data,True,1,background=background)
                self.assertEqual(result['code'],'INVALID_IMAGE');self.assertFalse((Path(root)/'assets').exists())
            self.assertEqual(self.imported(root,data,expected=1)['code'],'INVALID_IMAGE');self.assertFalse((Path(root)/'assets').exists())

    def test_mcp_import_edit_timing_undo_retry_reopen_and_create_only_publication(self):
        data=gif.fixture(3,2,[dict(indices=bytes([1])*6,delay=10),dict(indices=bytes([0,2])*3,alpha=0,delay=20)],repeats=2)
        c=Client();self.addCleanup(c.close);c.initialize()
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'original.gif';path.write_bytes(data);store=str(Path(root)/'assets')
            result=c.success('sequence.import',id='agent-gif',source=dict(type='gif',source_path=str(path)),store_root=store,color_policy='assume_srgb');d=result['document']
            session=dict(session_root=root,session_id='formats');c.success('session.create',**session,request_id='create',document=d,resources=dict(asset_root=store))
            changed=copy.deepcopy(d['variants']['sequence']);changed['frames'][0]['delay']=dict(numerator=3,denominator=10)
            action=dict(type='edit',operations=[dict(op='sequence_set',sequence=changed)])
            r=c.success('session.apply',**session,request_id='timing',expected_revision=0,action=action);self.assertEqual(r['document']['revision'],1)
            self.assertTrue(c.success('session.apply',**session,request_id='timing',expected_revision=0,action=action)['replayed'])
            out=dict(output_root=root,file_name='animation.gif',format='gif')
            c.success('session.publish',**session,expected_revision=1,output=out);published=(Path(root)/'animation.gif').read_bytes();self.assertEqual(gif.decode(published)['controls'][0][1],30)
            self.assertTrue(c.tool('session.publish',**session,expected_revision=1,output=out)['isError']);self.assertEqual((Path(root)/'animation.gif').read_bytes(),published)
            undo=c.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(undo['variants']['sequence'],d['variants']['sequence'])
            c.success('session.verify',**session);self.assertEqual(path.read_bytes(),data)
            c2=Client();self.addCleanup(c2.close);c2.initialize();read=c2.success('session.read',**session)
            self.assertEqual(read['document']['variants']['sequence'],d['variants']['sequence'])


if __name__=='__main__':unittest.main()
