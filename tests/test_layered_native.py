"""Original multi-megapixel layered inputs, independent native blocks and revision oracles."""
import base64
import copy
import hashlib
import json
import struct
import unittest
import zlib
from contextlib import closing

import layered_fixtures as f
import layered_object_fixtures as objects
import test_agent_workspace as workspace
from test_editing_cli import png_pixels
from test_layered_groups_cli import marker
from test_layered_masks_cli import masked
from test_mcp import Client
from test_profiles_cli import linear_profile


class NativeLayeredTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli

    def imported(self, raw, **kw):
        source = self.root / 'original.layered'
        source.write_bytes(raw)
        result = self.cli('layered.import', source_path=source.name, id='layered',
                          color_policy=kw.pop('color_policy', 'assume_srgb'),
                          storage=kw.pop('storage', {}), **kw)
        self.assertEqual(source.read_bytes(), raw)
        if 'document' in result:
            self.assertEqual(result['source_sha256'], hashlib.sha256(raw).hexdigest())
            self.assertFalse(result['source_changed'])
        return result

    def assert_grid(self, item, rgba, w, h):
        self.assertEqual(item['content']['type'], 'stored_samples')
        grid = item['content']['grid']
        self.assertEqual(grid['storage_version'], 2)
        self.assertFalse(grid.get('patches'))
        m = grid['base']
        self.assertEqual(m['spec'], dict(width=w, height=h, depth='u8', channels='rgba', encoding='encoded_srgb'))
        columns = (w+127)//128
        self.assertEqual(len(m['tiles']), columns*((h+127)//128))
        for index, digest in enumerate(m['tiles']):
            x, y = index % columns * 128, index // columns * 128
            tw, th = min(128, w-x), min(128, h-y)
            blob = (self.root/'.inkbolt/assets'/f'{digest}.native-tile').read_bytes()
            self.assertEqual(hashlib.sha256(blob).hexdigest(), digest)
            self.assertEqual(blob[:20], b'INKTILE1'+struct.pack('<IIBBBB', tw, th, 1, 4, 0, 0))
            expected = b''.join(rgba[((y+dy)*w+x)*4:((y+dy)*w+x+tw)*4] for dy in range(th))
            self.assertEqual(blob[20:], expected)
        identity = b'INKGRID1'+b'INKTILE1'+struct.pack('<IIBBBB', w, h, 1, 4, 0, 0)+struct.pack('<I',128)
        identity += b''.join(bytes.fromhex(digest) for digest in m['tiles'])
        self.assertEqual(hashlib.sha256(identity).hexdigest(), m['sha256'])

    def test_all_compressions_versions_preserve_every_channel_and_merged_hash(self):
        w, h = 257, 3
        rgba = hashlib.shake_256(b'original layered channel fixture').digest(w*h*4)
        layer = dict(name='Δ pixels', width=w, height=h, rgba=rgba, xy=(-2, 1), opacity=153)
        merged = hashlib.shake_256(b'independent merged cache').digest(w*h*4)
        for version in (1, 2):
            for compression in range(4):
                with self.subTest(version=version, compression=compression):
                    result = self.imported(f.make([layer], w=w, h=h, version=version,
                                                 compression=compression, merged=merged))
                    item = result['document']['items'][0]
                    self.assert_grid(item, rgba, w, h)
                    self.assertEqual(item['transform'], [1,0,0,1,-2,1])
                    self.assertEqual(item['opacity'], 153/255)
                    self.assertEqual(item['name'], layer['name'])
                    self.assertNotIn('resource_profile', result['document'])
                    self.assertEqual(result['merged_cache']['sample_sha256'], hashlib.sha256(merged).hexdigest())
                    self.assertFalse(result['merged_cache']['used_for_editable_reconstruction'])

    def test_two_megapixel_edit_history_snapshot_and_independent_preview(self):
        w, h = 1920, 1080
        rgba = bytearray(hashlib.shake_256(b'original two megapixel layered source').digest(w*h*4))
        rgba[3::4] = b'\xff'*(w*h)
        top = bytes([201,27,93,255])*130*129
        layers = [dict(name='original', width=w, height=h, rgba=rgba),
                  dict(name='overlay', width=130, height=129, rgba=top, xy=(300,200))]
        raw = f.make(layers, w=w, h=h, compression=2)
        self.imported(raw, storage=None, error='RESOURCE_LIMIT')
        self.imported(raw, error='RESOURCE_LIMIT')
        result = self.imported(raw, resource_profile='large_raster')
        d = result['document']
        self.assertEqual(d['resource_profile'], 'large_raster')
        self.assertLess(len(json.dumps(d)), 20000)
        self.assert_grid(d['items'][0], rgba, w, h)
        self.assert_grid(d['items'][1], top, 130,129)
        original_blocks = {p.name: p.read_bytes() for p in (self.root/'.inkbolt/assets').glob('*.native-tile')}
        self.cli('session.create', session_id='work', request_id='create', document=d)
        patch = bytes([29,45,231,255])*4
        action = dict(type='edit', operations=[dict(op='sample_replace', id='layer-1',
            region=dict(x=127,y=127,width=2,height=2), data_hex=patch.hex())])
        edited = self.cli('session.apply', session_id='work', request_id='edit', expected_revision=0, action=action)['document']
        changed = bytearray(rgba)
        for y in (127,128): changed[(y*w+127)*4:(y*w+129)*4] = patch[:8]
        self.assert_grid(edited['items'][0], changed, w,h)
        self.assertEqual(edited['items'][1], d['items'][1])
        undo = self.cli('session.apply', session_id='work', request_id='undo', expected_revision=1, action=dict(type='undo'))['document']
        self.assertEqual(undo, dict(d, revision=2))
        redo = self.cli('session.apply', session_id='work', request_id='redo', expected_revision=2, action=dict(type='redo'))['document']
        self.assertEqual(redo, dict(edited, revision=3))
        snapshot = self.cli('document.export', document=dict(session_id='work', revision=0), format='snapshot')
        self.assertEqual(json.loads(snapshot['data']), d)
        self.assertTrue(self.cli('session.verify', session_id='work')['valid'])
        for name, blob in original_blocks.items(): self.assertEqual((self.root/'.inkbolt/assets'/name).read_bytes(), blob)
        view = copy.deepcopy(edited)
        view['width'], view['height'] = 6,6
        for item in view['items']:
            item['transform'][4] -= 125
            item['transform'][5] -= 125
        png = self.cli('document.export', document=view, format='png')
        expected = b''.join(changed[(y*w+125)*4:(y*w+131)*4] for y in range(125,131))
        self.assertEqual(png_pixels(base64.b64decode(png['data']))[2], expected)
        self.assertEqual((self.root/'original.layered').read_bytes(), raw)

    def test_groups_masks_color_conversion_and_hidden_pixels_match_inline(self):
        rgba = bytes([64,128,192,0, 23,61,97,255])*6
        pixel = dict(name='pixel', width=4,height=3,rgba=rgba,xy=(2,1),visible=False)
        records = [marker(3), masked(pixel,gray=b'\x40\xff',box=(1,2,2,4),compression=3), marker(1,'folder',mode=b'pass')]
        raw = f.make(records, compression=3, profile=linear_profile())
        inline = self.imported(raw, storage=None, color_policy='convert_srgb')['document']
        native = self.imported(raw, color_policy='convert_srgb')['document']
        for actual, expected in zip(native['items'], inline['items']):
            if expected['content']['type'] == 'raster':
                self.assert_grid(actual, bytes.fromhex(expected['content']['rgba_hex']), 4,3)
                actual = dict(actual, content=expected['content'])
            self.assertEqual(actual, expected)

    def test_malformed_late_data_and_invalid_document_publish_nothing(self):
        layer = dict(name='pixel',width=129,height=129,rgba=bytes([7,81,29,0])*129*129)
        raw = f.make([layer],w=129,h=129,compression=2)
        for bad in (raw[:-1], raw+b'extra', raw[:-5]+b'bad!!'):
            self.imported(bad, error='INVALID_LAYERED_FILE')
            self.assertFalse((self.root/'.inkbolt').exists())
        self.imported(raw, expected_sha256='0'*64, error='SOURCE_MISMATCH')
        self.assertFalse((self.root/'.inkbolt').exists())
        self.imported(raw, control=dict(timeout_ms=0), error='TIMEOUT')
        self.assertFalse((self.root/'.inkbolt').exists())
        self.cli('layered.import', source_path='original.layered', id='', color_policy='assume_srgb', storage={}, error='INVALID_DOCUMENT')
        self.assertFalse((self.root/'.inkbolt').exists())

    def test_channel_underflow_overflow_trailer_and_checksum_fail_before_publication(self):
        layer = dict(name='bad channel',width=3,height=2,rgba=b'')
        channels = [f.plane(bytes([31])*6,3,2)]*4
        for encoded in (f.U16(2)+zlib.compress(bytes(5)), f.U16(2)+zlib.compress(bytes(7)),
                        channels[0]+b'\0', channels[0][:-1],
                        f.U16(1)+f.U16(2)+f.U16(2)+bytes([253,7,254,8]),
                        f.U16(0)+bytes(7)):
            bad = f.make([dict(layer,channel_data=[encoded]+channels[1:])])
            self.imported(bad, error='INVALID_LAYERED_FILE')
            self.assertFalse((self.root/'.inkbolt').exists())

    def test_native_policy_and_limits_are_explicit_and_discoverable_through_mcp(self):
        raw = f.make([dict(name='pixel',width=1,height=1,rgba=bytes([1,2,3,4]))])
        self.imported(raw, storage=None, resource_profile='large_raster', error='UNSUPPORTED_LAYERED_SEMANTICS')
        self.imported(raw, resource_profile='large_vector', error='UNSUPPORTED_LAYERED_SEMANTICS')
        self.imported(raw, storage=dict(storage_version=1), error='UNSUPPORTED_LAYERED_SEMANTICS')
        with closing(Client(workspace=self.root)) as c:
            c.initialize()
            caps = c.success('capabilities')['layered_interchange']['native_import']
            self.assertEqual(caps['aggregate_retained_pixels'], 8192**2)
            self.assertEqual(caps['file_bytes'],32*1024*1024)
            imported = c.success('layered.import',source_path='original.layered',id='mcp',color_policy='assume_srgb',storage={})
            self.assert_grid(imported['document']['items'][0],bytes([1,2,3,4]),1,1)
            self.assertEqual(imported['storage']['storage_version'],2)

    def test_nested_sources_keep_native_blocks_and_validate_all_before_publish(self):
        raw = objects.outer(objects.source(compression=3), compression=2)
        result = self.imported(raw, embedded_objects=objects.POLICY)
        obj = result['document']['items'][0]['content']['object']
        snapshot = json.loads(obj['snapshot'])
        self.assertEqual(obj['sha256'], hashlib.sha256(obj['snapshot'].encode()).hexdigest())
        self.assert_grid(snapshot['items'][0], objects.PIXELS,3,2)
        repeated = self.imported(raw, embedded_objects=objects.POLICY)
        self.assertEqual(repeated['document'], result['document'])
        self.assertTrue(all(row['created_tiles']==0 for row in repeated['storage']['layers']))
        self.assertFalse(result['embedded_placements'][0]['cache_used_for_editable_reconstruction'])
        before = {p.name:p.read_bytes() for p in (self.root/'.inkbolt/assets').glob('*') if p.is_file()}
        bad = objects.outer(objects.source(compression=3)+b'extra', compression=2)
        self.imported(bad, embedded_objects=objects.POLICY, error='INVALID_LAYERED_FILE')
        after = {p.name:p.read_bytes() for p in (self.root/'.inkbolt/assets').glob('*') if p.is_file()}
        self.assertEqual(before,after)

    def test_opaque_rgb_and_admission_refusals_do_not_allocate_or_publish_large_layers(self):
        rgb = dict(name='opaque',width=3,height=2,rgba=bytes([13,67,211,0])*6,channel_ids=[2,0,1])
        result = self.imported(f.make([rgb],compression=3))
        self.assert_grid(result['document']['items'][0],bytes([13,67,211,255])*6,3,2)
        before = {p.name:p.read_bytes() for p in (self.root/'.inkbolt/assets').glob('*') if p.is_file()}
        # Tiny encoded records declare excessive extents. Admission must precede decoding.
        huge = dict(name='oversized',width=8192,height=8192,rgba=b'',channel_data=[b'\0\0']*4)
        for raw in (f.make([huge],w=8193,h=8192,merged=b''),
                    f.make([huge,huge],w=1,h=1,merged=b''),
                    f.make([dict(huge,width=8193)],w=1,h=1,merged=b'')):
            self.imported(raw,resource_profile='large_raster',error='RESOURCE_LIMIT')
        deep = bytearray(f.make([rgb]));deep[22:24]=f.U16(16)
        self.imported(deep,error='UNSUPPORTED_LAYERED_SEMANTICS')
        after = {p.name:p.read_bytes() for p in (self.root/'.inkbolt/assets').glob('*') if p.is_file()}
        self.assertEqual(before,after)


if __name__ == '__main__': unittest.main()
