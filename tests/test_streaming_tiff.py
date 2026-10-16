"""Final TIFF bytes, independent samples and create-only publication contracts."""
import base64
from contextlib import closing
import copy
import hashlib
import itertools
import json
import unittest
import zlib

import test_agent_workspace as workspace
import test_hdr_cli as hdr
from test_image_io_cli import tiff_tags
from test_mcp import Client
from test_profiles_cli import builtin, decode_srgb
from test_samples_cli import decode, layer
import test_stored_samples as native
import test_streaming_png as streaming_png


class StreamingTiffTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli
    document = streaming_png.StreamingPngTests.document
    invoke_in_scratch = streaming_png.StreamingPngTests.invoke_in_scratch
    imported = native.StoredSampleTests.imported

    def delivery(self, document, name, **options):
        before = native.StoredSampleTests.files(self)
        artifact = self.cli('document.export', document=document, format='tiff', **options)
        data = base64.b64decode(artifact['data'])
        output = dict(file_name=name+'.tiff', format='tiff', **options)
        pre = self.cli('document.preflight', document=document, output=output)
        self.assertTrue(pre['ready'], pre)
        self.assertEqual(native.StoredSampleTests.files(self), before)
        receipt = self.cli('document.publish', document=document, output=output)
        self.assertEqual(receipt, dict(pre['prepared_output'], created=True))
        self.assertEqual((self.root/output['file_name']).read_bytes(), data)
        self.assertEqual(receipt['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(receipt['bytes'], len(data))
        self.assertNotIn('data', receipt)
        return artifact, data

    def test_native_depths_channels_compressions_and_evaluations_keep_final_samples(self):
        # All codec routes exercise the same seek/backpatch publication boundary.
        for depth, channels in itertools.product(('u8','u16','f32'), ('rgba','gray_alpha')):
            maximum = {'u8':255, 'u16':65535, 'f32':1}[depth]
            values = [0, 1, 7, 127] if depth == 'u8' else [0, 1, 32769, 65535] if depth == 'u16' else [0, 2**-149, .5000000596046448, 1]
            expected = [c for v in values*33 for c in ([v,v,v,maximum] if channels=='rgba' else [v,maximum])]
            d = self.cli('document.create',id='precision',kind='raster',width=12,height=11)
            d['items'] = [layer(expected,depth,channels,w=12)]
            original = copy.deepcopy(d)
            for compression, evaluation in itertools.product(('none','deflate','lzw'), ('whole','tiled')):
                name = '-'.join((depth,channels,compression,evaluation))
                artifact, data = self.delivery(d,name,image_options=dict(depth=depth,channels=channels,compression=compression),
                    render_options=dict(evaluation=evaluation))
                if compression != 'lzw':
                    actual, tags = decode(artifact)
                    self.assertEqual(actual,expected)
                    self.assertEqual((tags[256],tags[257]),((12,),(11,)))
                else:
                    # Codec-independent sample checks above cover both layouts;
                    # LZW additionally checks real reimport (not an independent oracle).
                    self.assertEqual(tiff_tags(data)[259],(5,))
                    (self.root/'encoded.tiff').write_bytes(data)
                    imported = self.cli('sample.import',source_path='encoded.tiff',id='again',color_policy='assume_srgb')
                    self.assertEqual(imported['document']['items'][0]['content']['grid']['data_hex'],
                                     d['items'][0]['content']['grid']['data_hex'])
            self.assertEqual(d,original)

    def test_stored_native_pixels_cross_blocks_and_private_storage_without_source_changes(self):
        width,height = 521,269
        d = self.imported(width,height,storage={})
        original = copy.deepcopy(d)
        assets = native.StoredSampleTests.blocks(self)
        artifact,_ = self.delivery(d,'blocks',image_options=dict(depth='u16',compression='deflate'),render_options=dict(evaluation='tiled'))
        self.assertEqual(decode(artifact)[0],[v for y in range(height) for x in range(width) for v in native.pixel(x,y)])
        self.assertEqual(native.StoredSampleTests.blocks(self),assets)
        self.assertEqual(d,original)

    def test_rgba8_profiles_associated_alpha_metadata_and_density_have_independent_oracles(self):
        d = self.document(17,19)
        d['kind'] = 'raster'
        color = [27,83,199,128]
        d['items'] = [dict(id='pixels',content=dict(type='raster',width=17,height=19,rgba_hex=(bytes(color)*323).hex()))]
        d['output_profile'] = builtin('linear_srgb')
        d['metadata'] = dict(title='Original seekable TIFF fixture')
        d['resolution_ppi'] = 143.12345
        for alpha,evaluation in itertools.product(('associated','unassociated'),('whole','tiled')):
            artifact,data = self.delivery(d,alpha+'-'+evaluation,image_options=dict(alpha=alpha,compression='deflate'),
                render_options=dict(evaluation=evaluation),metadata_policy=dict(mode='public'))
            tags=tiff_tags(data)
            raw=b''.join(zlib.decompress(data[o:o+n]) for o,n in zip(tags[273],tags[279]))
            rgb=[round(255*decode_srgb(v/255)) for v in color[:3]]
            if alpha=='associated':rgb=[(v*128+127)//255 for v in rgb]
            self.assertEqual(raw,bytes(rgb+[128])*323)
            self.assertEqual(tags[338],(1 if alpha=='associated' else 2,))
            self.assertEqual(tags[282],(143123,1000))
            self.assertIn(b'Original seekable TIFF fixture',bytes(tags[270]))
            self.assertEqual(hashlib.sha256(bytes(tags[34675])).hexdigest(),artifact['color_profile']['icc_sha256'])

    def test_hdr_native_and_artboard_publication_keep_exact_samples(self):
        d = self.cli('document.create',id='linear',kind='raster',width=131,height=137)
        d['color_space']='linear_srgb'
        d['items']=[hdr.layer([-2,3,2**-149,1],w=1,transform=[131,0,0,137,0,0])]
        artifact,_=self.delivery(d,'hdr',image_options=dict(depth='f32'),render_options=dict(evaluation='tiled'))
        self.assertEqual(decode(artifact)[0],[-2,3,2**-149,1]*(131*137))
        d=self.document(100,80)
        color=[29,89,177,255]
        d['items']=[dict(id='page',transform=[1,0,0,1,11,9],content=dict(type='frame',frame=dict(
            role='artboard',width=17,height=21,background=color,bleed=dict(top=1,right=2,bottom=3,left=1))))]
        artifact=self.cli('artboard.export',document=d,format='tiff',include_bleed=True)['artifacts'][0]['artifact']
        output=dict(file_name='page.tiff',format='tiff',artboard_id='page',include_bleed=True)
        pre=self.cli('document.preflight',document=d,output=output)
        receipt=self.cli('document.publish',document=d,output=output)
        self.assertEqual(receipt,dict(pre['prepared_output'],created=True))
        data=(self.root/'page.tiff').read_bytes()
        self.assertEqual(data,base64.b64decode(artifact['data']))
        tags=tiff_tags(data)
        self.assertEqual((tags[256],tags[257]),((20,),(25,)))
        self.assertEqual(tags[259],(8,))
        self.assertEqual(b''.join(zlib.decompress(data[o:o+n]) for o,n in zip(tags[273],tags[279])),bytes(color)*500)

    def test_saved_revision_mcp_durable_replay_and_existing_output_remain_unchanged(self):
        d=self.document(33,35)
        saved=self.cli('session.create',session_id='work',request_id='create',document=d)['document']
        options=dict(image_options=dict(depth='u16',compression='lzw'),render_options=dict(evaluation='tiled'))
        _,data=self.delivery(d,'direct',**options)
        arguments=dict(document=dict(session_id='work',revision=0),output=dict(file_name='durable.tiff',format='tiff',**options),
                       receipt=dict(request_id='seekable'))
        with closing(Client(args=['--tools','core'],workspace=self.root)) as client:
            client.initialize()
            first=client.tool('run',command='document.publish',arguments=arguments)['structuredContent']['result']
            second=client.tool('run',command='document.publish',arguments=arguments)['structuredContent']['result']
            self.assertEqual(first['sha256'],hashlib.sha256(data).hexdigest())
            self.assertEqual(first['sha256'],second['sha256'])
            self.assertTrue(second['publication']['replayed'])
        self.cli('document.publish',document=d,output=arguments['output'],error='OUTPUT_EXISTS')
        self.assertEqual((self.root/'durable.tiff').read_bytes(),data)
        self.assertEqual(self.cli('document.validate',document=arguments['document']),saved)

    def test_file_free_preflight_and_failed_publication_clean_private_storage(self):
        d=self.document(33,35)
        output=dict(file_name='final.tiff',format='tiff',image_options=dict(depth='u16'),render_options=dict(evaluation='tiled'))
        request=dict(command='document.preflight',document=d,output=output)
        missing=self.root/'missing-scratch'
        result=self.invoke_in_scratch(request,missing)
        self.assertEqual(result.returncode,0,result.stdout)
        self.assertTrue(json.loads(result.stdout)['result']['ready'])
        self.assertFalse(missing.exists())
        scratch=self.root/'scratch';scratch.mkdir()
        invalid=dict(request,command='document.publish',output=dict(output,image_options=dict(depth='u16',alpha='associated')))
        result=self.invoke_in_scratch(invalid,scratch)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(list(scratch.iterdir()),[])
        self.assertFalse((self.root/'final.tiff').exists())
        result=self.invoke_in_scratch(dict(request,command='document.publish'),scratch)
        self.assertEqual(result.returncode,0,result.stdout)
        self.assertEqual(list(scratch.iterdir()),[])


if __name__=='__main__':unittest.main()
