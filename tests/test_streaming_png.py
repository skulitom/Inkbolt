"""Independent band pixels and exact create-only PNG delivery contracts."""
import base64
from contextlib import closing
import copy
import hashlib
import json
import os
import subprocess
import unittest

from test_cli import EXE
import test_agent_workspace as workspace
import test_stored_samples as native
from test_editing_cli import png_pixels
from test_mcp import Client
from test_profiles_cli import builtin, decode_srgb, png_profile
from test_render_quality_cli import rect
import test_hdr_cli as hdr


class StreamingPngTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli
    imported = native.StoredSampleTests.imported

    def document(self, width=533, height=279):
        d = self.cli('document.create', id='streamed', kind='vector', width=width, height=height)
        d['items'] = [rect(w=width, h=height, color=[27,83,199,255]),
                      rect('inset', 131, 129, 137, 131, [211,49,7,255])]
        return d

    def exported(self, d, **options):
        artifact = self.cli('document.export', document=d, format='png', **options)
        return artifact, base64.b64decode(artifact['data'])

    def delivery(self, d, name, **options):
        artifact, data = self.exported(d, **options)
        output = dict(file_name=name+'.png', format='png', **options)
        before = native.StoredSampleTests.files(self)
        pre = self.cli('document.preflight', document=d, output=output)
        self.assertTrue(pre['ready'], pre)
        self.assertEqual(native.StoredSampleTests.files(self), before)
        receipt = self.cli('document.publish', document=d, output=output)
        self.assertEqual(receipt, dict(pre['prepared_output'], created=True))
        self.assertEqual((self.root/output['file_name']).read_bytes(), data)
        self.assertEqual(receipt['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(receipt['bytes'], len(data))
        return artifact, data

    def test_short_bands_keep_every_native_sample_and_inline_file_preflight_bytes(self):
        width, height = 531, 271
        d = self.imported(width, height, storage={})
        original = copy.deepcopy(d)
        _, data = self.delivery(d, 'native', render_options=dict(evaluation='tiled'))
        expected = bytes(round(v*255/65535) for y in range(height) for x in range(width) for v in native.pixel(x,y))
        self.assertEqual(png_pixels(data)[:3], (width, height, expected))
        self.assertEqual(self.exported(d)[1], data)
        self.assertEqual(d, original)

    def test_wide_scaled_native_source_keeps_decode_work_and_every_output_sample(self):
        # More source blocks than the reader cache, enlarged to the maximum
        # output width. Too-short bands repeatedly decode the complete source.
        width, height, scale = 8192, 65, 4
        d = self.imported(width, height, storage={})
        before = native.StoredSampleTests.files(self)
        request = dict(command='document.export', document=d, format='png', scale=scale,
                       render_options=dict(evaluation='tiled'))
        result = subprocess.run([str(EXE), '--workspace', str(self.root)],
            input=json.dumps(request).encode(), capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stderr, b'')
        artifact = json.loads(result.stdout)['result']
        w, h, actual = png_pixels(base64.b64decode(artifact['data']))[:3]
        self.assertEqual((w, h), (width*scale, height*scale))
        for y in range(height):
            row = b''.join(bytes((v*255+32767)//65535 for v in native.pixel(x,y))*scale
                           for x in range(width))
            self.assertEqual(actual[y*scale*w*4:(y+1)*scale*w*4], row*scale)
        self.assertEqual(native.StoredSampleTests.files(self), before)

    def test_profiles_metadata_and_short_last_bands_have_independent_color_oracle(self):
        d = self.document()
        d['output_profile'] = builtin('linear_srgb')
        d['metadata'] = dict(title='Original banded color fixture')
        for evaluation in ('whole','tiled'):
            artifact, data = self.delivery(d, 'profile-'+evaluation,
                render_options=dict(evaluation=evaluation), metadata_policy=dict(mode='public'))
            width, height, raw = png_pixels(data)[:3]
            expected = bytearray()
            for y in range(height):
                for x in range(width):
                    color = [211,49,7] if 131<=x<268 and 129<=y<260 else [27,83,199]
                    expected.extend([round(255*decode_srgb(c/255)) for c in color]+[255])
            self.assertLessEqual(max(abs(a-b) for a,b in zip(raw,expected)), 1)
            self.assertEqual(len(raw), len(expected))
            self.assertTrue(artifact['metadata']['embedded'])
            self.assertEqual(hashlib.sha256(png_profile(data)).hexdigest(), artifact['color_profile']['icc_sha256'])

    def test_supersampling_transparency_and_mcp_durable_replay_keep_one_result(self):
        d = self.document(133, 137)
        d['items'] = [rect(x=2, y=3, w=127, h=131, color=[17,101,233,128])]
        options = dict(render_options=dict(evaluation='tiled', antialias='supersample2'))
        _, data = self.delivery(d, 'alpha', **options)
        width, height, raw = png_pixels(data)[:3]
        expected = bytes(v for y in range(height) for x in range(width)
            for v in ([17,101,233,128] if 2<=x<129 and 3<=y<134 else [0,0,0,0]))
        self.assertEqual(raw, expected)
        arguments = dict(document=d, output=dict(file_name='durable.png',format='png',**options),
                         receipt=dict(request_id='streamed'))
        with closing(Client(args=['--tools','core'], workspace=self.root)) as client:
            client.initialize()
            first = client.tool('run', command='document.publish', arguments=arguments)['structuredContent']['result']
            self.assertEqual((self.root/'durable.png').read_bytes(), data)
            second = client.tool('run', command='document.publish', arguments=arguments)['structuredContent']['result']
            self.assertEqual(first['sha256'], second['sha256'])
            self.assertTrue(second['publication']['replayed'])
        self.cli('document.publish', document=d, output=arguments['output'], error='OUTPUT_EXISTS')
        self.assertEqual((self.root/'durable.png').read_bytes(), data)

    def test_hdr_display_view_is_applied_before_band_quantization(self):
        width, height = 267, 259
        d = self.cli('document.create',id='linear',kind='raster',width=width,height=height)
        d['color_space'] = 'linear_srgb'
        d['items'] = [hdr.layer([.25,.5,2,1],w=1,transform=[width,0,0,height,0,0])]
        before = copy.deepcopy(d)
        _, data = self.delivery(d, 'display', render_options=dict(evaluation='tiled',view=dict(tone_map='clip')))
        expected = bytes([int(hdr.encoded(v)*255+hdr.D('.5')) for v in [hdr.D('.25'),hdr.D('.5'),hdr.D(1)]]+[255])
        self.assertEqual(png_pixels(data)[:3], (width,height,expected*(width*height)))
        self.assertEqual(d,before)

    def test_artboard_bleed_stream_matches_inline_artboard_and_independent_pixels(self):
        d = self.document(600,400)
        color = [29,89,177,255]
        d['items'] = [dict(id='page',transform=[1,0,0,1,31,29],content=dict(type='frame',frame=dict(
            role='artboard',width=267,height=261,background=color,bleed=dict(top=1,right=2,bottom=3,left=1))))]
        options=dict(evaluation='tiled')
        artifact=self.cli('artboard.export',document=d,format='png',render_options=options,include_bleed=True)['artifacts'][0]['artifact']
        data=base64.b64decode(artifact['data'])
        output=dict(file_name='page.png',format='png',artboard_id='page',include_bleed=True,render_options=options)
        pre=self.cli('document.preflight',document=d,output=output)
        self.assertTrue(pre['ready'],pre)
        receipt=self.cli('document.publish',document=d,output=output)
        self.assertEqual(receipt,dict(pre['prepared_output'],created=True))
        self.assertEqual((self.root/'page.png').read_bytes(),data)
        self.assertEqual(png_pixels(data)[:3],(270,265,bytes(color)*(270*265)))

    def invoke_in_scratch(self, request, scratch):
        env=dict(os.environ, TMP=str(scratch), TEMP=str(scratch), TMPDIR=str(scratch))
        return subprocess.run([str(EXE),'--workspace',str(self.root)], input=json.dumps(request).encode(),
            capture_output=True, timeout=20, env=env)

    def test_preflight_needs_no_temporary_directory_and_failed_publication_cleans_private_files(self):
        d = self.document(33,35)
        output = dict(file_name='final.png',format='png',render_options=dict(evaluation='tiled'))
        request = dict(command='document.preflight',document=d,output=output)
        missing = self.root/'no-scratch-directory'
        pre = self.invoke_in_scratch(request,missing)
        self.assertEqual(pre.returncode,0,pre.stderr)
        self.assertTrue(json.loads(pre.stdout)['result']['ready'])
        self.assertFalse(missing.exists())
        scratch=self.root/'private';scratch.mkdir()
        invalid=dict(request,command='document.publish',output=dict(output,image_options=dict(quality=50)))
        result=self.invoke_in_scratch(invalid,scratch)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(list(scratch.iterdir()),[])
        self.assertFalse((self.root/'final.png').exists())
        result=self.invoke_in_scratch(dict(request,command='document.publish'),scratch)
        self.assertEqual(result.returncode,0,result.stdout)
        self.assertEqual(list(scratch.iterdir()),[])



if __name__=='__main__':unittest.main()
