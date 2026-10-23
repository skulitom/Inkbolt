"""Large encoded layered files retain original samples through bounded channel readers."""
import hashlib
import json
import struct
import subprocess
import unittest

import layered_stream_fixtures as fixture
import test_agent_workspace as workspace
from test_cli import EXE


class StreamingLayeredTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp

    def cli(self, *, error=None, **kw):
        request = dict(command='layered.import',source_path='original.layered',id='streaming',
                       resource_profile='large_raster',color_policy='assume_srgb',storage={})
        request.update(kw)
        run = subprocess.run([str(EXE),'--workspace',str(self.root)],input=json.dumps(request).encode(),
                             capture_output=True,timeout=60)
        self.assertFalse(run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(run.returncode,int(error is not None),result)
        if error:
            self.assertEqual(result['error']['code'],error,result)
            return result['error']
        self.assertTrue(result['ok'],result)
        return result['result']

    def check_tiles(self, document, w, h):
        self.assertEqual((document['width'],document['height'],document['resource_profile']),(w,h,'large_raster'))
        item = document['items'][0]
        self.assertEqual(item['name'],'Original coordinate planes')
        grid = item['content']['grid'];m=grid['base']
        self.assertEqual(grid['storage_version'],2)
        self.assertEqual(m['spec'],dict(width=w,height=h,depth='u8',channels='rgba',encoding='encoded_srgb'))
        columns=(w+127)//128
        self.assertEqual(len(m['tiles']),columns*((h+127)//128))
        for index,digest in enumerate(m['tiles']):
            x,y=index%columns*128,index//columns*128
            tw,th=min(128,w-x),min(128,h-y)
            blob=(self.root/'.inkbolt/assets'/f'{digest}.native-tile').read_bytes()
            self.assertEqual(hashlib.sha256(blob).hexdigest(),digest)
            self.assertEqual(blob[:20],b'INKTILE1'+struct.pack('<IIBBBB',tw,th,1,4,0,0))
            expected=bytearray(tw*th*4)
            expected[0::4]=bytes((x+dx)%256 for dx in range(tw))*th
            expected[1::4]=b''.join(bytes([(y+dy)%256])*tw for dy in range(th))
            expected[2::4]=bytes([(x//128+y//128)%256])*(tw*th)
            expected[3::4]=bytes([255 if x//128%2 else 0])*(tw*th)
            self.assertEqual(blob[20:],expected)
        identity=b'INKGRID1'+b'INKTILE1'+struct.pack('<IIBBBB',w,h,1,4,0,0)+struct.pack('<I',128)
        identity+=b''.join(bytes.fromhex(digest) for digest in m['tiles'])
        self.assertEqual(hashlib.sha256(identity).hexdigest(),m['sha256'])

    def test_raw_and_rle_files_above_old_limit_preserve_every_sample_and_source(self):
        w,h=2051,2049
        for version,compression in ((1,0),(2,1)):
            path=self.root/f'original-{version}.layered'
            source=fixture.write(path,w,h,version=version,compression=compression)
            self.assertGreater(source['bytes'],32*1024*1024)
            self.cli(source_path=path.name,storage=None,resource_profile='standard',error='RESOURCE_LIMIT')
            result=self.cli(source_path=path.name,expected_sha256=source['sha256'])
            self.assertEqual(result['source_sha256'],source['sha256'])
            self.assertEqual(result['source_bytes'],source['bytes'])
            self.assertFalse(result['source_changed'])
            self.check_tiles(result['document'],w,h)
            merged=hashlib.sha256()
            for _ in range(h*4):merged.update(bytes(w))
            self.assertEqual(result['merged_cache']['sample_sha256'],merged.hexdigest())
            with path.open('rb') as stream:self.assertEqual(hashlib.file_digest(stream,'sha256').hexdigest(),source['sha256'])

    def test_channel_length_above_32_mib_uses_wide_container_and_bounded_rows(self):
        w,h=8192,4097
        path=self.root/'original.layered';source=fixture.write(path,w,h,version=2)
        self.assertGreater(source['channel_bytes'],32*1024*1024)
        result=self.cli(expected_sha256=source['sha256'])
        self.check_tiles(result['document'],w,h)
        self.assertLess(len(json.dumps(result['document'])),160000)
        with path.open('rb') as stream:self.assertEqual(hashlib.file_digest(stream,'sha256').hexdigest(),source['sha256'])

    def test_large_late_trailer_and_source_mismatch_publish_no_blocks(self):
        path=self.root/'original.layered';fixture.write(path,2051,2049)
        with path.open('ab') as stream:stream.write(b'x')
        with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        self.cli(expected_sha256='0'*64,error='SOURCE_MISMATCH')
        self.assertFalse((self.root/'.inkbolt').exists())
        self.cli(expected_sha256=digest,error='INVALID_LAYERED_FILE')
        self.assertFalse((self.root/'.inkbolt').exists())
        with path.open('rb') as stream:self.assertEqual(hashlib.file_digest(stream,'sha256').hexdigest(),digest)

    def test_encoded_and_metadata_bounds_remain_distinct(self):
        metadata=self.root/'metadata.layered'
        with metadata.open('xb') as stream:
            stream.write(b'8BPS'+struct.pack('>H',1)+bytes(6)+struct.pack('>HIIHHII',4,1,1,8,3,0,32*1024*1024))
            for _ in range(512):stream.write(bytes(65536))
        self.cli(source_path=metadata.name,error='RESOURCE_LIMIT')
        self.assertFalse((self.root/'.inkbolt').exists())
        oversized=self.root/'oversized.layered'
        with oversized.open('xb') as stream:
            stream.write(b'original oversized input')
            stream.truncate(544*1024*1024+1)
        before=(oversized.stat().st_size,oversized.stat().st_mtime_ns)
        self.cli(source_path=oversized.name,error='RESOURCE_LIMIT')
        self.assertEqual((oversized.stat().st_size,oversized.stat().st_mtime_ns),before)
        self.assertFalse((self.root/'.inkbolt').exists())


if __name__=='__main__':unittest.main()
