"""Native TIFF chunk bands: exact samples, framing failures and source preservation."""
from contextlib import closing
import itertools
import struct
import unittest

import test_native_import_rows as png_rows
from test_sample_conversion_cli import tiff
from test_mcp import Client


class NativeTiffBandTests(unittest.TestCase):
    setUp = png_rows.NativeImportRowTests.setUp
    cli = png_rows.NativeImportRowTests.cli
    imported = png_rows.NativeImportRowTests.imported
    check_blocks = png_rows.NativeImportRowTests.check_blocks

    def check_tiff(self, data, w, h, depth, n, expected, **fields):
        policy = fields.pop('color_policy', 'assume_srgb')
        result = self.imported(data, color_policy=policy, **fields)
        self.assertEqual(result['normalization']['decode_storage'], 'chunk_bands_to_native_blocks')
        return self.check_blocks(result, w, h, depth, 2 if n <= 2 else 4, expected,
                                 'linear_srgb' if policy == 'assume_linear_srgb' else 'encoded_srgb')

    def test_all_native_depths_channels_planes_endianness_and_chunk_layouts(self):
        w, h = 17, 19
        for depth, n, planar, endian, tiled in itertools.product((8, 16, 'f32'), (1, 2, 3, 4), (False, True), ('<', '>'), (False, True)):
            maximum = 1 if depth == 'f32' else (1 << depth)-1
            values = [(i % 17)/16 if depth == 'f32' else (i*7919+3571) & maximum for i in range(w*h*n)]
            expected = [v for i in range(w*h) for v in values[i*n:(i+1)*n]+([maximum] if n % 2 else [])]
            with self.subTest(depth=depth, n=n, planar=planar, endian=endian, tiled=tiled):
                data = tiff(w, h, values, depth='f32' if depth == 'f32' else f'u{depth}', n=n,
                            planar=planar, endian=endian, compression=8,
                            **(dict(tile=(16, 16)) if tiled else dict(strip_rows=7)))
                self.check_tiff(data, w, h, depth, n, expected)

    def test_compressions_and_chunk_boundaries_cross_native_blocks(self):
        w, h, n = 131, 137, 4
        values = [(x*7919+y*3571+c*233) & 65535 for y in range(h) for x in range(w) for c in range(n)]
        manifests = []
        for compression, planar, tiled in itertools.product((1, 5, 8, 32946, 32773), (False, True), (False, True)):
            with self.subTest(compression=compression, planar=planar, tiled=tiled):
                data = tiff(w, h, values, planar=planar, endian='>', compression=compression,
                            **(dict(tile=(48, 32)) if tiled else dict(strip_rows=19)))
                manifests.append(self.check_tiff(data, w, h, 16, n, values))
        self.assertTrue(all(value == manifests[0] for value in manifests))

    def test_exact_float_bits_hdr_missing_alpha_and_white_zero(self):
        w, h = 129, 131
        words = [0x80000000, 1, 0x3f000001, 0x3f800000]
        pixel = list(struct.unpack('<4f', struct.pack('<4I', *words)))
        for planar in (False, True):
            data = tiff(w, h, pixel*(w*h), depth='f32', planar=planar, endian='>', strip_rows=17)
            self.check_tiff(data, w, h, 'f32', 4, pixel*(w*h))
        hdr = [-2, 3, 2**-149]*(w*h)
        expected = [v for i in range(w*h) for v in hdr[i*3:i*3+3]+[1]]
        self.check_tiff(tiff(w, h, hdr, depth='f32', n=3, planar=True, tile=(32, 16)),
                        w, h, 'f32', 3, expected, color_policy='assume_linear_srgb')
        for depth, values, maximum in [(8, [0, 1, 127, 255], 255), (16, [0, 1, 32767, 65535], 65535),
                                       ('f32', [0, .125, .5, 1], 1)]:
            source = values*33
            self.check_tiff(tiff(4, 33, source, depth='f32' if depth == 'f32' else f'u{depth}', n=1,
                                photo=0, strip_rows=7), 4, 33, depth, 1,
                            [v for value in source for v in [maximum-value, maximum]])

    def test_late_chunk_corruption_invalid_float_metadata_and_limits_write_nothing(self):
        w, h = 129, 137
        values = [.125, .25, .5, 1]*(w*h)
        valid = tiff(w, h, values, depth='f32', planar=True, strip_rows=17, compression=8)
        # Truncate the final plane's final compressed strip after earlier bands decode.
        for data, fields, error in [(valid[:-7], {}, 'INVALID_IMAGE'),
                                     (valid, dict(resolution_ppi=0), 'INVALID_DOCUMENT')]:
            self.imported(data, color_policy='assume_srgb', error=error, **fields)
            self.assertEqual([p.name for p in self.root.iterdir()], ['source.png'])
        for value in [float('nan'), float('inf'), -1, 1.0001]:
            invalid = values.copy(); invalid[-1] = value
            data = tiff(w, h, invalid, depth='f32', planar=True, strip_rows=17)
            self.imported(data, color_policy='assume_srgb', error='UNSUPPORTED_SAMPLE_RANGE')
            self.assertEqual([p.name for p in self.root.iterdir()], ['source.png'])
        for tags, error in [({270:(2,list(b'Inkbolt metadata v1\n{broken\0'))}, 'INVALID_METADATA'),
                            ({322:(4,[2**30]),323:(4,[2**30])}, 'RESOURCE_LIMIT')]:
            data = tiff(1, 1, [0], depth='u8', n=1, tile=(16, 16), tags=tags)
            self.imported(data, color_policy='assume_srgb', error=error)
            self.assertEqual([p.name for p in self.root.iterdir()], ['source.png'])

    def test_mcp_matches_cli_and_existing_blocks_remain_unchanged(self):
        w, h = 129, 133
        values = [c for y in range(h) for x in range(w) for c in [x*257, y*257]]
        data = tiff(w, h, values, n=2, endian='>', planar=True, strip_rows=13, compression=5)
        before = self.imported(data, color_policy='assume_srgb')
        old = {p.name:(p.stat().st_mtime_ns,p.read_bytes()) for p in (self.root/'.inkbolt/assets').iterdir()}
        with closing(Client(('--tools', 'core'), workspace=self.root)) as client:
            client.initialize()
            response = client.tool('run', command='sample.import', arguments=dict(source_path='source.png', id='native', storage={}, color_policy='assume_srgb'))
            self.assertFalse(response['isError'], response)
            after = response['structuredContent']['result']
        self.assertEqual(after['document'], before['document'])
        self.assertEqual(after['normalization'], before['normalization'])
        self.assertEqual(after['storage']['created_tiles'], 0)
        self.check_blocks(after, w, h, 16, 2, values)
        self.assertEqual(old, {p.name:(p.stat().st_mtime_ns,p.read_bytes()) for p in (self.root/'.inkbolt/assets').iterdir()})


if __name__ == '__main__':
    unittest.main()
