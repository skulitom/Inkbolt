"""Independent JPEG sample/orientation/framing checks through CLI and MCP."""
from contextlib import closing
import hashlib
import json
import math
import struct
import unittest

import synthetic_jpeg as fixture
import test_agent_workspace as workspace
import test_native_import_rows as rows
from test_mcp import Client
from test_sample_conversion_cli import png


class NativeJpegImportTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli
    check_blocks = rows.NativeImportRowTests.check_blocks

    def imported(self, data, *, stored=True, call=None, **fields):
        source = self.root / 'original.jpg'
        source.write_bytes(data)
        arguments = dict(source_path=source.name, id='jpeg', color_policy='assume_srgb',
                         orientation='apply', **({'storage': {}} if stored else {}))
        arguments.update(fields)
        out = (call or self.cli)('sample.import', **arguments)
        self.assertEqual(source.read_bytes(), data)
        if 'document' in out:
            self.assertEqual(out['source_sha256'], hashlib.sha256(data).hexdigest())
            self.assertEqual(out['source_bytes'], len(data))
            self.assertFalse(out['source_changed'])
            self.assertEqual(out['source_format'], 'jpeg')
        return out

    def test_baseline_progressive_gray_rgb_all_orientations_and_byte_orders(self):
        for progressive in (False, True):
            for channels in (1, 3):
                original = fixture.pixels(17, 9, channels)
                for little in (False, True):
                    for orientation in range(1, 9):
                        with self.subTest(progressive=progressive, channels=channels,
                                          little=little, orientation=orientation):
                            data = fixture.jpeg(channels=channels, progressive=progressive,
                                                extras=fixture.exif(orientation, little=little))
                            out = self.imported(data)
                            w, h, expected = fixture.oriented(original, 17, 9, channels, orientation)
                            self.check_blocks(out, w, h, 8, channels+1, expected)
                            self.assertEqual(out['normalization']['orientation'], dict(policy='apply',
                                source=orientation, effective=orientation, transformed=orientation != 1,
                                source_width=17, source_height=9, output_width=w, output_height=h))
                            inline = self.imported(data, stored=False)
                            self.assertEqual(bytes.fromhex(inline['document']['items'][0]['content']['grid']['data_hex']), expected)

    def test_ignore_retains_coded_pixels_and_thumbnail_does_not_rotate_primary(self):
        for orientation in range(1, 9):
            data = fixture.jpeg(extras=fixture.exif(orientation, thumbnail=9-orientation))
            out = self.imported(data, orientation='ignore')
            self.check_blocks(out, 17, 9, 8, 4, fixture.pixels(17, 9, 3))
            self.assertEqual(out['normalization']['orientation']['effective'], 1)
        out = self.imported(fixture.jpeg(extras=fixture.exif(thumbnail=6)))
        self.check_blocks(out, 17, 9, 8, 4, fixture.pixels(17, 9, 3))
        self.assertIsNone(out['normalization']['orientation']['source'])

    def test_subsampled_chroma_and_odd_dimensions_have_exact_neutral_pixels(self):
        expected = bytes(v for y in range(129) for x in range(133)
                         for v in [fixture.value(x, y, 0)] * 3 + [255])
        for progressive in (False, True):
            for sampling in ((2, 1), (2, 2)):
                with self.subTest(progressive=progressive, sampling=sampling):
                    out = self.imported(fixture.jpeg(133, 129, progressive=progressive, subsampling=sampling))
                    self.check_blocks(out, 133, 129, 8, 4, expected)

    def test_restart_intervals_preserve_samples_across_scan_and_row_boundaries(self):
        for progressive in (False, True):
            for restart in (1, 5):
                for sampling in (None, (2, 2)):
                    with self.subTest(progressive=progressive, restart=restart, sampling=sampling):
                        data = fixture.jpeg(133, 129, progressive=progressive,
                                            restart=restart, subsampling=sampling)
                        out = self.imported(data)
                        expected = (bytes(v for y in range(129) for x in range(133)
                                    for v in [fixture.value(x, y, 0)]*3+[255]) if sampling
                                    else fixture.pixels(133, 129, 3))
                        self.check_blocks(out, 133, 129, 8, 4, expected)

    def test_progressive_refinement_new_coefficients_and_eob_corrections(self):
        for new in (False, True):
            with self.subTest(new_coefficient=new):
                out = self.imported(fixture.refined(new_coefficient=new), stored=False)
                raw = bytes.fromhex(out['document']['items'][0]['content']['grid']['data_hex'])
                width = 8 if new else 16
                expected = [round(128 + math.sqrt(2) * (
                    5*math.cos((2*(x%8)+1)*math.pi/16)
                    + (math.cos((2*y+1)*math.pi/16) if new else 0)))
                    for y in range(8) for x in range(width)]
                self.assertEqual(raw[1::2], bytes([255])*len(expected))
                self.assertLessEqual(max(abs(a-b) for a,b in zip(raw[::2], expected)), 1)

    def test_stuffed_bytes_restart_numbers_padding_and_extra_entropy(self):
        data = fixture.jpeg(24, 8, channels=1, sample=lambda x,y,c: 128 if x < 16 else 0)
        self.assertIn(b'\xff\0', data)
        out = self.imported(data)
        self.check_blocks(out, 24, 8, 8, 2, (bytes([128,255])*16 + bytes([0,255])*8)*8)
        restart = fixture.jpeg(restart=1)
        bad_padding = bytearray(fixture.jpeg(8,8,channels=1))
        bad_padding[-3] &= 0xfe
        broken = [data.replace(b'\xff\0', b'\xff\xd9', 1),
                  restart.replace(b'\xff\xd0', b'\xff\xd1', 1),
                  fixture.jpeg(8,8,channels=1)[:-2] + b'\0\xff\xd9',
                  fixture.refined(eob_overrun=True), bytes(bad_padding)]
        # Use a fresh store per refusal so existing successful imports cannot mask writes.
        for index, candidate in enumerate(broken):
            with self.subTest(index=index):
                store = self.root / f'rejected-{index}'
                self.imported(candidate, storage=dict(store_root=str(store)), error='INVALID_IMAGE')
                self.assertFalse(store.exists())

    def test_odd_block_edges_source_identity_and_mcp_parity(self):
        data = fixture.jpeg(133, 129, progressive=True, extras=fixture.exif(6, srgb=True))
        out = self.imported(data, color_policy='require_srgb')
        w, h, expected = fixture.oriented(fixture.pixels(133, 129, 3), 133, 129, 3, 6)
        self.check_blocks(out, w, h, 8, 4, expected)
        self.assertEqual(out['interpretation'], 'declared_srgb')
        with closing(Client(('--tools', 'core'), workspace=self.root)) as client:
            client.initialize()
            def dispatch(command, **arguments):
                response = client.tool('run', command=command, arguments=arguments)
                self.assertFalse(response['isError'], response)
                return response['structuredContent']['result']
            actual = self.imported(data, call=dispatch, color_policy='require_srgb')
        self.assertEqual(actual['document'], out['document'])
        self.assertEqual(actual['storage']['created_tiles'], 0)
        self.assertEqual(actual['normalization'], out['normalization'])

    def test_explicit_policies_and_unchanged_png_request(self):
        data = fixture.jpeg()
        self.imported(data, orientation=None, error='INVALID_REQUEST')
        self.imported(data, color_policy='require_srgb', error='UNSUPPORTED')
        self.imported(data, color_policy='assume_linear_srgb', error='UNSUPPORTED')
        self.imported(data, color_policy='convert_srgb', error='UNSUPPORTED')
        self.imported(png(1, 1, [12, 34, 56, 255], depth=8, n=4), error='UNSUPPORTED')
        old = self.cli('sample.import', source_path='original.jpg', id='old', color_policy='assume_srgb')
        self.assertEqual(old['source_format'], 'png')
        self.assertNotIn('orientation', old['normalization'])
        self.assertIn('orientation transforms', old['losses'][0])

    def test_metadata_envelope_and_duplicate_or_missing_parts(self):
        packet = json.dumps(dict(schema='inkbolt.metadata.v1', document=dict(title='Original JPEG'), items={}),
                            separators=(',', ':')).encode()
        part = lambda i, n, data: fixture.segment(0xfe, b'INKBOLT-META\0' + struct.pack('>HH', i, n) + data)
        carrier = part(2, 2, packet[31:]) + part(1, 2, packet[:31])
        data = fixture.jpeg(extras=carrier)
        out = self.imported(data)
        self.assertEqual(out['metadata']['envelope_sha256'], hashlib.sha256(packet).hexdigest())
        self.assertEqual(out['metadata'], self.imported(data, stored=False)['metadata'])
        for extras in (carrier + part(1, 2, packet[:31]), part(2, 2, packet[31:]), part(0, 1, packet)):
            self.imported(fixture.jpeg(extras=extras), error='INVALID_METADATA')

    def test_preparation_refusals_never_publish_blocks(self):
        data = fixture.jpeg(progressive=True)
        corruptions = [
            (data[:-2], 'INVALID_IMAGE'), (data + b'x', 'INVALID_IMAGE'),
            (data[:-2] + fixture.segment(0xfe, b'INKBOLT-META\0\0\1\0\1{}') + data[-2:], 'UNSUPPORTED'),
            (fixture.jpeg(extras=fixture.segment(0xe2, b'unsupported profile')), 'UNSUPPORTED'),
            (fixture.jpeg(extras=fixture.exif(0)), 'INVALID_IMAGE'),
            (fixture.jpeg(extras=fixture.exif(9)), 'INVALID_IMAGE'),
            (fixture.jpeg(extras=fixture.exif(1) + fixture.exif(2)), 'INVALID_IMAGE'),
            (fixture.jpeg(extras=fixture.segment(0xe1, b'Exif\0\0II\x2a\0\xff\xff\xff\xff')), 'INVALID_IMAGE'),
        ]
        for broken, error in corruptions:
            with self.subTest(error=error, size=len(broken)):
                self.imported(broken, error=error)
                self.assertFalse((self.root / '.inkbolt').exists())
        # Invalid orientation remains an error when explicitly ignored.
        self.imported(fixture.jpeg(extras=fixture.exif(9)), orientation='ignore', error='INVALID_IMAGE')
        self.assertFalse((self.root / '.inkbolt').exists())

    def test_premature_end_marker_does_not_turn_truncated_entropy_into_pixels(self):
        for progressive in (False, True):
            with self.subTest(progressive=progressive):
                data = fixture.jpeg(133, 129, progressive=progressive)
                sos = data.index(b'\xff\xda')
                entropy = sos + 2 + int.from_bytes(data[sos+2:sos+4], 'big')
                truncated = data[:entropy+1] + b'\xff\xd9'
                self.imported(truncated, error='INVALID_IMAGE')
                self.assertFalse((self.root / '.inkbolt').exists())

    def test_dimension_and_scan_work_limits_fail_before_decode_or_store_creation(self):
        # Deliberately omit entropy/tables: admission must stop before decoding.
        def oversized(width, height, scans):
            frame = fixture.segment(0xc2, struct.pack('>BHHB', 8, height, width, 3)
                                    + b'R\x11\0G\x11\0B\x11\0')
            scan = fixture.segment(0xda, b'\3R\0G\0B\0\0\0\0') + b'\0'
            return b'\xff\xd8' + frame + scan * scans + b'\xff\xd9'
        cases = [(oversized(4097, 4096, 1), 'decoded pixel count'),
                 (oversized(1, 1, 129), 'scan count'),
                 (oversized(4096, 4096, 43), 'cumulative work')]
        for data, message in cases:
            with self.subTest(message=message):
                error = self.imported(data, error='RESOURCE_LIMIT')
                self.assertIn(message, error['message'])
                self.assertFalse((self.root / '.inkbolt').exists())

    def test_exif_cycles_duplicates_invalid_types_and_late_scan_headers(self):
        good = bytearray(fixture.exif(6))
        # Offset to the primary directory's next-pointer in this exact fixture.
        cycle = good.copy(); cycle[-4:] = struct.pack('<I', 8)
        wrong_type = good.copy(); wrong_type[22:24] = struct.pack('<H', 4)
        duplicate = fixture.segment(0xe1, b'Exif\0\0II\x2a\0\x08\0\0\0'
            + struct.pack('<H', 2) + bytes(good[20:32]) * 2 + bytes(4))
        for extra in (cycle, wrong_type, duplicate):
            self.imported(fixture.jpeg(extras=extra), orientation='ignore', error='INVALID_IMAGE')
            self.assertFalse((self.root / '.inkbolt').exists())
        data = fixture.jpeg(progressive=True)
        late = fixture.segment(0xda, b'\1Z\0\1\x3f\0') + b'\0'
        self.imported(data[:-2] + late + data[-2:], error='INVALID_IMAGE')
        self.assertFalse((self.root / '.inkbolt').exists())

    def test_scan_order_table_selection_and_duplicate_progression_are_rejected(self):
        data = fixture.jpeg()
        sos = data.index(b'\xff\xda')
        reordered = bytearray(data)
        reordered[sos+5], reordered[sos+7] = reordered[sos+7], reordered[sos+5]
        bad_table = bytearray(data); bad_table[sos+6] = 0x20
        progressive = fixture.jpeg(progressive=True)
        scan = progressive.index(b'\xff\xda')
        end = progressive.index(b'\xff\xda', scan+2)
        duplicate = progressive[:end] + progressive[scan:end] + progressive[end:]
        for malformed in (bytes(reordered), bytes(bad_table), duplicate):
            self.imported(malformed, error='INVALID_IMAGE')
            self.assertFalse((self.root / '.inkbolt').exists())

    def test_conflicting_color_declarations_and_embedded_exif_profile_are_refused(self):
        def tagged(tag, kind, count, inline):
            return fixture.segment(0xe1, b'Exif\0\0II\x2a\0\x08\0\0\0'
                + struct.pack('<HHHI', 1, tag, kind, count) + inline + bytes(4))
        profile = tagged(34675, 7, 4, b'ICC!')
        wrong_photo = tagged(262, 3, 1, b'\6\0\0\0')
        jfif = fixture.segment(0xe0, b'JFIF\0\1\2\0\0\1\0\1\0\0')
        for extra in (profile, wrong_photo, jfif):
            self.imported(fixture.jpeg(extras=extra), error='UNSUPPORTED')
            self.assertFalse((self.root / '.inkbolt').exists())
        right_photo = tagged(262, 3, 1, b'\2\0\0\0')
        out = self.imported(fixture.jpeg(extras=right_photo))
        self.check_blocks(out, 17, 9, 8, 4, fixture.pixels(17, 9, 3))


if __name__ == '__main__':
    unittest.main()
