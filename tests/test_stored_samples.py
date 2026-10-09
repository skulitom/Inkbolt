"""Native block documents: exact original pixels, pure deltas and durable readers."""
import base64
import copy
import hashlib
import json
import struct
import unittest
import zlib
from contextlib import closing

import test_agent_workspace as workspace
from test_images_cli import chunk
from test_samples_cli import decode, packed
from test_sample_conversion_cli import tiff
from test_mcp import Client
import test_jobs as jobs
from test_metadata_cli import carrier


def pixel(x, y):
    return [x % 65536, y % 65536, (x * 7919 + y * 3571) % 65536, 65535]


def png(w, h):
    compressor = zlib.compressobj()
    blocks = []
    for y in range(h):
        row = b''.join(struct.pack('>4H', *pixel(x, y)) for x in range(w))
        blocks.append(compressor.compress(b'\0' + row))
    data = b''.join(blocks) + compressor.flush()
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 16, 6, 0, 0, 0))
            + chunk(b'sRGB', b'\0') + chunk(b'IDAT', data) + chunk(b'IEND', b''))


class StoredSampleTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli
    save = workspace.AgentWorkspaceTests.save
    ref = workspace.AgentWorkspaceTests.ref

    def imported(self, w=132, h=132, data=None, **kw):
        data = data or png(w, h)
        source = self.root / 'original.bin'
        source.write_bytes(data)
        result = self.cli('sample.import', source_path='original.bin', id='native',
                          color_policy=kw.pop('color_policy', 'assume_srgb'), storage={}, **kw)
        self.assertEqual(source.read_bytes(), data)
        self.assertEqual(result['source_sha256'], hashlib.sha256(data).hexdigest())
        self.assertFalse(result['source_changed'])
        self.assertEqual(result['document']['items'][0]['content']['type'], 'stored_samples')
        self.assertEqual(result['storage']['kind'], 'native_tiles')
        return result['document']

    def files(self):
        return {str(p.relative_to(self.root)): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
                for p in self.root.rglob('*') if p.is_file()}

    def blocks(self):
        return {p.name: p.read_bytes() for p in (self.root / '.inkbolt/assets').glob('*.native-tile')}

    def grid(self, d):
        return d['items'][0]['content']['grid']

    def view(self, d, x=125, y=126, w=7, h=6):
        # Explicit independent document view; large-output admission is separate.
        d = copy.deepcopy(d)
        d['width'], d['height'] = w, h
        d['items'][0]['transform'] = [1, 0, 0, 1, -x, -y]
        return d

    def exported(self, d, depth='u16', **kw):
        return self.cli('document.export', document=d, format='tiff',
                        image_options=dict(depth=depth, channels='rgba', compression='none'), **kw)

    def patch(self, x=127, y=127, w=2, h=2, values=None, depth='u16'):
        values = values or [c for i in range(w*h) for c in [50001+i, 60003-i, 4321+i, 65535]]
        return dict(op='sample_replace', id='pixels', region=dict(x=x, y=y, width=w, height=h),
                    data_hex=packed(values, depth))

    def test_two_megapixel_import_exact_blocks_and_small_edit_snapshot(self):
        d = self.imported(1920, 1080)
        self.assertLess(len(json.dumps(d)), 20000)
        self.cli('sample.import', source_path='original.bin', id='inline',
                 color_policy='assume_srgb', error='RESOURCE_LIMIT')
        manifest = self.grid(d)['base']; blocks = self.blocks()
        self.assertEqual(len(manifest['tiles']), 15*9)
        # Independent public block framing and every original native channel.
        for index, name in enumerate(manifest['tiles']):
            blob = blocks[name+'.native-tile']; x0, y0 = index % 15 * 128, index // 15 * 128
            w, h = min(128, 1920-x0), min(128, 1080-y0)
            self.assertEqual(hashlib.sha256(blob).hexdigest(), name)
            self.assertEqual(blob[:20], b'INKTILE1'+struct.pack('<IIBBBB', w, h, 2, 4, 0, 0))
            expected = b''.join(struct.pack('<4H', *pixel(x, y)) for y in range(y0, y0+h) for x in range(x0, x0+w))
            self.assertEqual(blob[20:], expected)
        before = self.files(); op = self.patch()
        result = self.cli('document.edit', document=d, expected_revision=0, operations=[op])
        changed = result['document']
        self.assertEqual(self.files(), before)
        self.assertEqual(self.grid(changed)['base'], manifest)
        self.assertEqual(self.grid(changed)['patches'], [dict(region=op['region'], data_hex=op['data_hex'])])
        receipt = result['changes'][0]['details']
        self.assertFalse(receipt['files_written']); self.assertTrue(receipt['outside_region_preserved'])
        self.assertNotEqual(receipt['before_native_sha256'], receipt['after_native_sha256'])
        actual, _ = decode(self.exported(self.view(changed)))
        replacements = struct.unpack('<16H', bytes.fromhex(op['data_hex']))
        expected = []
        for y in range(126, 132):
            for x in range(125, 132):
                i = ((y-127)*2+x-127)*4
                expected.extend(replacements[i:i+4] if 127 <= x < 129 and 127 <= y < 129 else pixel(x, y))
        self.assertEqual(actual, expected)
        snapshot = self.cli('document.export', document=changed, format='snapshot')
        self.assertEqual(json.loads(snapshot['data']), changed)
        self.assertEqual(decode(self.exported(self.view(d)))[0],
                         [c for y in range(126, 132) for x in range(125, 132) for c in pixel(x, y)])
        overview = copy.deepcopy(d); overview['width'], overview['height'] = 480, 270
        overview['items'][0]['transform'] = [.25,0,0,.25,0,0]
        self.assertEqual(decode(self.exported(overview))[0],
                         [c for y in range(270) for x in range(480) for c in pixel(4*x+2,4*y+2)])
        self.assertEqual(self.files(), before)

    def test_dry_run_proposal_history_retry_and_snapshot_have_no_block_writes(self):
        d = self.view(self.imported())
        self.save(d); before = self.files(); action = dict(type='edit', operations=[self.patch()])
        proposal = self.cli('session.dry_run', session_id='work', request_id='change', expected_revision=0,
                            action=action, options=dict(include_document=True, preview=True, compare_pixels=True))
        self.assertEqual(self.files(), before)
        predicted = proposal['proposed_document']; base_blocks = self.blocks()
        committed = self.cli('session.apply_proposal', proposal=proposal['proposal'], action=action)
        self.assertEqual(committed['document'], predicted)
        self.assertEqual(committed['receipt'], proposal['predicted_receipt'])
        self.assertEqual(self.blocks(), base_blocks)
        self.assertEqual(decode(self.exported(self.ref(1)))[0], decode(self.exported(predicted))[0])
        replay = self.cli('session.apply_proposal', proposal=proposal['proposal'], action=action)
        self.assertTrue(replay['replayed'])
        undo = self.cli('session.apply', session_id='work', request_id='undo', expected_revision=1, action=dict(type='undo'))
        self.assertEqual(undo['document'], dict(d, revision=2))
        redo = self.cli('session.apply', session_id='work', request_id='redo', expected_revision=2, action=dict(type='redo'))
        self.assertEqual(redo['document'], dict(predicted, revision=3))
        self.assertTrue(self.cli('session.verify', session_id='work')['valid'])
        self.assertEqual(self.blocks(), base_blocks)
        self.assertLess(sum(p.stat().st_size for p in self.root.rglob('*.sqlite3')), 200000)
        backup = self.cli('session.backup', session_id='work', expected_revision=3, output=dict(file_name='native-history.sqlite3'))
        self.cli('session.recover', session_id='work', session_root='recovered', source=backup['backup'])
        recovered = dict(session_id='work', session_root='recovered', revision=3)
        self.assertEqual(decode(self.exported(recovered))[0], decode(self.exported(predicted))[0])
        self.assertEqual(self.blocks(), base_blocks)

    def test_unselected_corruption_detected_by_edit_render_check_and_transfer(self):
        d = self.imported(); hidden = self.root / '.inkbolt/assets' / (self.grid(d)['base']['tiles'][-1]+'.native-tile')
        hidden.write_bytes(hidden.read_bytes()[:-1]+b'\0')
        before = self.files(); view = self.view(d, 0, 0, 1, 1)
        self.exported(view, error='SAMPLE_TILE_CORRUPT')
        self.cli('document.edit', document=d, expected_revision=0, operations=[self.patch(0, 0, 1, 1)], error='SAMPLE_TILE_CORRUPT')
        d['items'][0]['visible'] = False
        report = self.cli('document.check', document=d)
        self.assertEqual(report['status'], 'fail')
        self.assertEqual(report['issues'][0]['error']['code'], 'SAMPLE_TILE_CORRUPT')
        destination = self.cli('document.create', id='target', kind='raster', width=1, height=1)
        self.cli('document.edit', document=destination, expected_revision=0,
                 operations=[dict(op='transfer', transfer=dict(source=d, ids=['pixels'], prefix='copy', verify_resources=True))],
                 error='SAMPLE_TILE_CORRUPT')
        self.assertEqual(self.files(), before)

    def test_noop_invalid_patch_atomic_batch_and_descriptor_hash(self):
        d = self.imported(2, 2); before = self.files()
        op = self.patch(0, 0, 1, 1, pixel(0, 0))
        result = self.cli('document.edit', document=d, expected_revision=0, operations=[op])
        self.assertNotIn('patches', self.grid(result['document']))
        details = result['changes'][0]['details']; self.assertEqual(details['before_native_sha256'], details['after_native_sha256'])
        for region, code in [(dict(x=4294967295, y=0, width=1, height=1),'INVALID_SAMPLE_STORE'),
                             (dict(x=0,y=0,width=0,height=1),'INVALID_STORED_SAMPLES'),
                             (dict(x=1,y=1,width=2,height=2),'INVALID_STORED_SAMPLES')]:
            self.cli('document.edit', document=d, expected_revision=0,
                     operations=[dict(op='properties', id='pixels', name='discard'), dict(op, region=region)], error=code)
        bad = copy.deepcopy(d); self.grid(bad)['base']['sha256'] = '0'*64
        self.cli('document.validate', document=bad, error='INVALID_SAMPLE_STORE')
        bad = copy.deepcopy(d); self.grid(bad)['patches'] = [dict(region=op['region'], data_hex='00')]
        self.cli('document.validate', document=bad, error='INVALID_STORED_SAMPLES')
        self.assertEqual(self.files(), before)

    def test_native_float_tiff_and_mcp_schema_are_available_without_byte_conversion(self):
        values = [2**-24, .5000000596046448, .875, 1, .25, .125, .0625, 1]
        d = self.imported(data=tiff(2, 1, values, depth='f32'))
        self.assertEqual(decode(self.exported(d, 'f32'))[0], values)
        with closing(Client(('--tools', 'core'), workspace=self.root)) as client:
            client.initialize()
            schema = client.success('schema.lookup', name='sample.import')
            self.assertIn('storage', json.dumps(schema))
            result = client.success('document.render', document=d)
            self.assertEqual(result['sample_precision']['sources'][0]['content'], 'stored_samples')

    def test_all_native_types_sampling_masks_filters_match_inline_across_tile_edges(self):
        for depth, channels in [('u8',4), ('u8',2), ('u16',4), ('u16',2), ('f32',4), ('f32',2)]:
            maximum = dict(u8=255, u16=65535, f32=1)[depth]
            values = [c for y in range(3) for x in range(132)
                      for c in ([((x+y*13)%127)/127*maximum]* (channels-1) + [maximum])]
            if depth != 'f32': values = [round(v) for v in values]
            data = tiff(132, 3, values, depth=depth, n=channels)
            stored = self.imported(data=data)
            inline = self.cli('sample.import', source_path='original.bin', id='native', color_policy='assume_srgb')['document']
            for sampling in ['nearest','bilinear','area','bicubic','lanczos3']:
                for d in [stored, inline]:
                    d['width'], d['height'] = 7, 6
                    item = d['items'][0]; item['transform'] = [.8, .1, .2, 1.4, -99, 0]
                    item['content']['grid']['sampling'] = sampling
                    item['opacity'] = .75
                    item['mask'] = dict(width=7, height=6, gray_hex=('80ffcc'*14))
                    item['filters'] = [dict(id='blur', operator=dict(type='box',radius=1),border='clamp')]
                self.assertEqual(decode(self.exported(stored, depth))[0], decode(self.exported(inline, depth))[0], (depth,channels,sampling))

    def test_retained_profile_and_hdr_values_use_their_declared_interpretation(self):
        values = [.125, .25, .5, 1, .25, .5, .75, 1]
        stored = self.imported(data=tiff(2,1,values,depth='f32'))
        inline = self.cli('sample.import', source_path='original.bin', id='native', color_policy='assume_srgb')['document']
        # Original fixture retags native blocks according to the published format.
        grid = self.grid(stored); manifest = grid['base']; spec = manifest['spec']; spec['encoding'] = 'profiled_rgb'
        root = self.root / '.inkbolt/assets'; names = []
        for name in manifest['tiles']:
            raw = bytearray((root/(name+'.native-tile')).read_bytes()); raw[18] = 2
            digest = hashlib.sha256(raw).hexdigest(); (root/(digest+'.native-tile')).write_bytes(raw); names.append(digest)
        manifest['tiles'] = names
        manifest['sha256'] = hashlib.sha256(b'INKGRID1'+b'INKTILE1'+struct.pack('<IIBBBB',2,1,4,4,2,0)+struct.pack('<I',128)+b''.join(bytes.fromhex(s) for s in names)).hexdigest()
        for d in [stored, inline]:
            g = self.grid(d); g['profile'] = dict(type='builtin',name='linear_srgb')
            if d is inline: g['encoding'] = 'profiled_rgb'
            self.cli('document.validate', document=d)
        self.assertEqual(decode(self.exported(stored,'f32'))[0], decode(self.exported(inline,'f32'))[0])
        expected = [(.125**(1/2.4)*1.055-.055),(.25**(1/2.4)*1.055-.055),(.5**(1/2.4)*1.055-.055),1]
        for actual, target in zip(decode(self.exported(stored,'f32'))[0][:4],expected): self.assertAlmostEqual(actual,target,places=4)
        hdr = [-2, 3, 2**-149, 1, -0.0, .125, .25, 1]
        d = self.imported(data=tiff(2,1,hdr,depth='f32'),color_policy='assume_linear_srgb')
        self.assertEqual(decode(self.exported(d,'f32'))[0], hdr)
        self.cli('document.render',document=d,error='HDR_VIEW_REQUIRED')

    def test_manifest_diagnostics_missing_store_limits_and_unsupported_consumers(self):
        caps = self.cli('capabilities')
        self.assertIn('stored_samples',caps['sample_precision']['contents'])
        self.assertFalse(caps['sample_precision']['import']['native_storage']['output_limits_changed'])
        self.assertTrue(caps['native_sample_store_library']['document_history_integration'])
        d = self.imported(2,2)
        packet = json.loads(carrier(base64.b64decode(self.exported(d,metadata_policy=dict(manifest=True))['data']),'tiff'))
        info = packet['manifest']['stored_samples']['pixels']
        self.assertEqual(info['base_manifest_sha256'],self.grid(d)['base']['sha256'])
        self.assertEqual(info['patch_count'],0); self.assertNotIn('data_hex',json.dumps(packet))
        for format in ['svg','pdf']:
            self.cli('document.export',document=d,format=format,error='UNSUPPORTED')
        self.exported(d,asset_root='missing',error='SAMPLE_TILE_MISSING')
        # Stored patches remain bounded and do not hide corrupt inherited data.
        too_many = copy.deepcopy(d)
        op = self.patch(0,0,1,1)
        self.grid(too_many)['patches'] = [dict(region=op['region'],data_hex=op['data_hex'])]*257
        self.cli('document.validate',document=too_many,error='RESOURCE_LIMIT')
        self.cli('document.edit',document=d,expected_revision=0,operations=[op],control=dict(timeout_ms=0),error='TIMEOUT')
        # Source byte cap is independent of admitted document dimensions. The
        # declared native size rejects before allocating or reading pixel data.
        (self.root/'oversize.tif').write_bytes(tiff(4096,1025,[],depth='f32'))
        before = self.files()
        self.cli('sample.import',source_path='oversize.tif',id='too-big',color_policy='assume_srgb',storage={},error='RESOURCE_LIMIT')
        self.assertEqual(self.files(),before)


class StoredSampleJobTests(unittest.TestCase):
    setUp = jobs.JobTests.setUp
    cli = jobs.JobTests.cli
    ledger = jobs.JobTests.ledger
    stop_owned = jobs.JobTests.stop_owned
    finish = jobs.JobTests.finish
    idle = jobs.JobTests.idle
    blocked_queue = jobs.JobTests.blocked_queue
    imported = StoredSampleTests.imported
    grid = StoredSampleTests.grid
    view = StoredSampleTests.view
    exported = StoredSampleTests.exported

    def test_pinned_job_matches_native_output_and_replays_without_source(self):
        d = self.view(self.imported()); expected = self.exported(d)
        output = dict(file_name='native.tif',format='tiff',image_options=dict(depth='u16',channels='rgba',compression='none'))
        self.cli('job.start',request_id='native',document=d,output=output)
        self.finish('native'); self.idle()
        self.assertEqual((self.root/'native.tif').read_bytes(),base64.b64decode(expected['data']))
        receipt = self.cli('job.result',request_id='native')
        for block in (self.root/'.inkbolt/assets').glob('*.native-tile'): block.unlink()
        replay = self.cli('job.start',request_id='native',document=d,output=output)
        self.assertTrue(replay['replayed']); self.assertEqual(replay['state'],'completed')
        self.assertEqual(self.cli('job.result',request_id='native'),receipt)

    def test_queued_job_rechecks_unselected_and_hidden_native_dependencies(self):
        d = self.view(self.imported()); d['items'][0]['visible'] = False
        with self.blocked_queue():
            self.cli('job.start',request_id='missing',document=d,output=dict(file_name='never.png',format='png'))
            name = self.grid(d)['base']['tiles'][-1]
            (self.root/'.inkbolt/assets'/(name+'.native-tile')).unlink()
        self.cli('job.resume',request_id='missing')
        state = self.finish('missing','failed'); self.idle()
        self.assertEqual(state['error']['code'],'SAMPLE_TILE_MISSING')
        self.assertFalse((self.root/'never.png').exists())


if __name__ == '__main__':
    unittest.main()
