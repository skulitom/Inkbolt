"""Banded JPEG pixels, historical framing and create-only delivery boundaries."""
import base64
from contextlib import closing
import copy
import hashlib
import json
import struct
import unittest

import test_agent_workspace as workspace
import test_stored_samples as native
import test_streaming_png as png
from test_image_io_cli import jpeg_segments
from test_profiles_cli import builtin, decode_srgb
from test_render_quality_cli import rect
from test_mcp import Client
import test_hdr_cli as hdr


def without_profile(data):
    """Remove only APP2; leave all entropy bytes and other header bytes intact."""
    result=bytearray(data[:2]);at=2
    while data[at+1] != 0xda:
        end=at+2+int.from_bytes(data[at+2:at+4],'big')
        if data[at+1] != 0xe2:result.extend(data[at:end])
        at=end
    return bytes(result)+data[at:]


class StreamingJpegTests(unittest.TestCase):
    setUp=workspace.AgentWorkspaceTests.setUp
    cli=workspace.AgentWorkspaceTests.cli
    document=png.StreamingPngTests.document
    imported=native.StoredSampleTests.imported
    invoke_in_scratch=png.StreamingPngTests.invoke_in_scratch

    def delivery(self,d,name,**options):
        before=native.StoredSampleTests.files(self)
        artifact=self.cli('document.export',document=d,format='jpeg',**options)
        data=base64.b64decode(artifact['data'])
        output=dict(file_name=name+'.jpg',format='jpeg',**options)
        pre=self.cli('document.preflight',document=d,output=output)
        self.assertTrue(pre['ready'],pre)
        self.assertEqual(native.StoredSampleTests.files(self),before)
        receipt=self.cli('document.publish',document=d,output=output)
        self.assertEqual(receipt,dict(pre['prepared_output'],created=True))
        self.assertEqual((self.root/output['file_name']).read_bytes(),data)
        self.assertEqual(receipt['bytes'],len(data))
        self.assertEqual(receipt['sha256'],hashlib.sha256(data).hexdigest())
        self.assertNotIn('data',receipt)
        return artifact,data

    def test_bands_mcu_padding_matte_and_profile_match_independent_input_equations(self):
        width,height=17,271
        source=bytes(c for y in range(height) for x in range(width)
            for c in ((x*7+y)%256,(y*3)%256,129,(x*11+y*13)%256))
        d=self.cli('document.create',id='matte',kind='raster',width=width,height=height)
        d['items']=[dict(id='pixels',content=dict(type='raster',width=width,height=height,rgba_hex=source.hex()))]
        d['output_profile']=builtin('linear_srgb')
        d['resolution_ppi']=143.12345
        original=copy.deepcopy(d);matte=[237,211,173]
        converted=bytearray()
        for at in range(0,len(source),4):
            alpha=source[at+3]
            rgb=[(source[at+c]*alpha+matte[c]*(255-alpha)+127)//255 for c in range(3)]
            converted.extend([round(255*decode_srgb(v/255)) for v in rgb]+[255])
        oracle=copy.deepcopy(d);del oracle['output_profile']
        oracle['items'][0]['content']['rgba_hex']=converted.hex()
        for chroma in ('full','half'):
            artifact,data=self.delivery(d,chroma,image_options=dict(chroma=chroma,quality=100,matte=matte),render_options=dict(evaluation='tiled'))
            expected=self.cli('document.export',document=oracle,format='jpeg',image_options=dict(chroma=chroma,quality=100))
            self.assertEqual(without_profile(data),base64.b64decode(expected['data']))
            segments=jpeg_segments(data);frame=dict(segments)[0xc0]
            self.assertEqual(struct.unpack('>BHHB',frame[:6]),(8,height,width,3))
            self.assertEqual(frame[7],0x11 if chroma=='full' else 0x22)
            self.assertEqual(struct.unpack('>HH',dict(segments)[0xe0][8:12]),(143,143))
            profile=b''.join(v[14:] for marker,v in segments if marker==0xe2)
            self.assertEqual(hashlib.sha256(profile).hexdigest(),artifact['color_profile']['icc_sha256'])
        self.assertEqual(d,original)

    def test_stored_multiband_source_and_whole_render_agree_without_mutation(self):
        d=self.imported(521,269,storage={})
        before=native.StoredSampleTests.blocks(self);original=copy.deepcopy(d)
        options=dict(image_options=dict(quality=95,matte=[203,127,71]))
        _,data=self.delivery(d,'native',render_options=dict(evaluation='tiled'),**options)
        whole=self.cli('document.export',document=d,format='jpeg',**options)
        self.assertEqual(data,base64.b64decode(whole['data']))
        self.assertEqual(native.StoredSampleTests.blocks(self),before)
        self.assertEqual(d,original)

    def test_public_metadata_stays_before_scan_and_saved_mcp_receipt_replays(self):
        d=self.document(33,35);d['metadata']=dict(title='Original streamed JPEG fixture')
        saved=self.cli('session.create',session_id='work',request_id='create',document=d)['document']
        options=dict(render_options=dict(evaluation='tiled',antialias='supersample2'),metadata_policy=dict(mode='public'))
        artifact,data=self.delivery(d,'direct',**options)
        segments=jpeg_segments(data)
        self.assertEqual([m for m,_ in segments][-2:],[0xfe,0xda])
        self.assertIn(b'Original streamed JPEG fixture',segments[-2][1])
        self.assertTrue(artifact['metadata']['embedded'])
        args=dict(document=dict(session_id='work',revision=0),output=dict(file_name='durable.jpg',format='jpeg',**options),receipt=dict(request_id='streamed'))
        with closing(Client(args=['--tools','core'],workspace=self.root)) as client:
            client.initialize()
            first=client.tool('run',command='document.publish',arguments=args)['structuredContent']['result']
            second=client.tool('run',command='document.publish',arguments=args)['structuredContent']['result']
            self.assertEqual(first['sha256'],hashlib.sha256(data).hexdigest())
            self.assertEqual(first['sha256'],second['sha256'])
            self.assertTrue(second['publication']['replayed'])
        self.cli('document.publish',document=d,output=args['output'],error='OUTPUT_EXISTS')
        self.assertEqual((self.root/'durable.jpg').read_bytes(),data)
        self.assertEqual(self.cli('document.validate',document=args['document']),saved)

    def test_file_free_preflight_late_alpha_and_cancellation_leave_no_output(self):
        d=self.document(17,271);d['items']=[rect(w=17,h=256,color=[27,83,199,255])]
        output=dict(file_name='final.jpg',format='jpeg',render_options=dict(evaluation='tiled'))
        scratch=self.root/'scratch';scratch.mkdir()
        request=dict(command='document.publish',document=d,output=output)
        failed=self.invoke_in_scratch(request,scratch)
        self.assertEqual(json.loads(failed.stdout)['error']['code'],'ALPHA_POLICY_REQUIRED')
        self.assertEqual(list(scratch.iterdir()),[])
        self.assertFalse((self.root/'final.jpg').exists())
        output['image_options']=dict(matte=[255]*3)
        missing=self.root/'missing'
        pre=self.invoke_in_scratch(dict(request,command='document.preflight'),missing)
        self.assertTrue(json.loads(pre.stdout)['result']['ready'])
        self.assertFalse(missing.exists())
        cancelled=self.invoke_in_scratch(dict(request,control=dict(timeout_ms=0)),scratch)
        self.assertNotEqual(cancelled.returncode,0)
        self.assertEqual(list(scratch.iterdir()),[])
        self.assertFalse((self.root/'final.jpg').exists())
        success=self.invoke_in_scratch(request,scratch)
        self.assertEqual(success.returncode,0,success.stdout)
        self.assertEqual(list(scratch.iterdir()),[])

    def test_hdr_view_and_artboard_bytes_agree_across_delivery_paths(self):
        d=self.cli('document.create',id='linear',kind='raster',width=17,height=271)
        d['color_space']='linear_srgb'
        d['items']=[hdr.layer([.5,2,4,1],w=1,transform=[17,0,0,271,0,0])]
        self.cli('document.export',document=d,format='jpeg',render_options=dict(evaluation='tiled'),error='HDR_VIEW_REQUIRED')
        self.delivery(d,'hdr',render_options=dict(evaluation='tiled',view=dict(exposure=0,tone_map='clip')))
        d=self.document(100,80)
        d['items']=[dict(id='page',transform=[1,0,0,1,11,9],content=dict(type='frame',frame=dict(role='artboard',width=17,height=21,
            background=[29,89,177,255],bleed=dict(top=1,right=2,bottom=3,left=1))))]
        options=dict(image_options=dict(matte=[255]*3),render_options=dict(evaluation='tiled'))
        artifact=self.cli('artboard.export',document=d,format='jpeg',include_bleed=True,**options)['artifacts'][0]['artifact']
        output=dict(file_name='page.jpg',format='jpeg',artboard_id='page',include_bleed=True,**options)
        pre=self.cli('document.preflight',document=d,output=output)
        receipt=self.cli('document.publish',document=d,output=output)
        self.assertEqual(receipt,dict(pre['prepared_output'],created=True))
        self.assertEqual((self.root/'page.jpg').read_bytes(),base64.b64decode(artifact['data']))
        self.assertEqual((artifact['width'],artifact['height']),(20,25))


if __name__=='__main__':unittest.main()
