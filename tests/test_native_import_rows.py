"""Independent native-block bytes for row-decoded PNG and buffered fallbacks."""
from contextlib import closing
import hashlib
import struct
import unittest
import zlib

import test_agent_workspace as workspace
from test_images_cli import chunk
from test_mcp import Client
from test_sample_conversion_cli import png, tiff


def packed_png(width, height, depth, color, rows, extras=()):
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, depth, color, 0, 0, 0))
            + chunk(b'sRGB', b'\0') + b''.join(chunk(k, v) for k, v in extras)
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


class NativeImportRowTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli

    def imported(self, data, call=None, **fields):
        source = self.root / 'source.png'
        source.write_bytes(data)
        result = (call or self.cli)('sample.import', source_path='source.png',
                                    id='native', storage={}, **fields)
        self.assertEqual(source.read_bytes(), data)
        if 'document' in result:
            self.assertEqual(result['source_sha256'], hashlib.sha256(data).hexdigest())
            self.assertFalse(result['source_changed'])
        return result

    def check_blocks(self, result, width, height, depth, n, expected):
        manifest = result['document']['items'][0]['content']['grid']['base']
        unit = depth // 8
        self.assertEqual(manifest['spec'], dict(width=width, height=height,
                         depth=f'u{depth}', channels='rgba' if n == 4 else 'gray_alpha',
                         encoding='encoded_srgb'))
        self.assertEqual(result['storage']['decoded_bytes'], width * height * n * unit)
        row_bytes = width * n * unit
        raw = struct.pack('<' + ('H' if depth == 16 else 'B') * len(expected), *expected)
        hashes = []
        for y in range(0, height, 128):
            for x in range(0, width, 128):
                w, h = min(128, width-x), min(128, height-y)
                header = b'INKTILE1' + struct.pack('<IIBBBB', w, h, unit, n, 0, 0)
                payload = b''.join(raw[j*row_bytes+x*n*unit:j*row_bytes+(x+w)*n*unit]
                                   for j in range(y, y+h))
                digest = hashlib.sha256(header + payload).hexdigest()
                hashes.append(digest)
                self.assertEqual((self.root / '.inkbolt/assets' / (digest+'.native-tile')).read_bytes(),
                                 header + payload)
        self.assertEqual(manifest['tiles'], hashes)
        identity = (b'INKGRID1INKTILE1' + struct.pack('<IIBBBBI', width, height, unit, n, 0, 0, 128)
                    + b''.join(bytes.fromhex(h) for h in hashes))
        self.assertEqual(manifest['sha256'], hashlib.sha256(identity).hexdigest())
        self.assertEqual(result['storage']['manifest_sha256'], manifest['sha256'])
        return manifest

    def test_every_channel_depth_and_opaque_alpha_across_short_edge_blocks(self):
        w, h = 131, 133
        for depth in (8, 16):
            maximum = (1 << depth)-1
            for n in (1, 2, 3, 4):
                with self.subTest(depth=depth, channels=n):
                    values = [(x*7919 + y*3571 + c*2311) & maximum
                              for y in range(h) for x in range(w) for c in range(n)]
                    expanded = [v for i in range(w*h)
                                for v in values[i*n:(i+1)*n] + ([maximum] if n in (1, 3) else [])]
                    out = self.imported(png(w, h, values, depth=depth, n=n))
                    self.assertEqual(out['normalization']['decode_storage'], 'rows_to_native_blocks')
                    self.check_blocks(out, w, h, depth, 2 if n < 3 else 4, expanded)

    def test_palette_low_bits_and_transparency_expand_exactly(self):
        palette = bytes([10, 20, 30, 41, 51, 61])
        cases = [
            (packed_png(4, 1, 2, 0, b'\0\x1b'), 4, 1, 8, 2,
             [0, 255, 85, 255, 170, 255, 255, 255]),
            (packed_png(2, 1, 1, 3, b'\0\x40', [(b'PLTE', palette), (b'tRNS', bytes([128, 0]))]),
             2, 1, 8, 4, [10, 20, 30, 128, 41, 51, 61, 0]),
            (png(3, 1, [12345, 12346, 12345], n=1, extras=[(b'tRNS', struct.pack('>H', 12345))]),
             3, 1, 16, 2, [12345, 0, 12346, 65535, 12345, 0]),
            (png(2, 1, [11, 22, 33, 11, 22, 34], n=3, depth=8,
                 extras=[(b'tRNS', struct.pack('>3H', 11, 22, 33))]),
             2, 1, 8, 4, [11, 22, 33, 0, 11, 22, 34, 255]),
        ]
        for data, w, h, depth, n, expected in cases:
            with self.subTest(depth=depth, channels=n, width=w):
                result = self.imported(data)
                self.assertEqual(result['normalization']['decode_storage'], 'rows_to_native_blocks')
                self.check_blocks(result, w, h, depth, n, expected)

    def test_interlaced_tiff_and_inline_fallbacks_keep_identical_sample_meaning(self):
        w, h = 129, 131
        for depth, n in ((8, 2), (16, 4)):
            values = [(i*7919) % (1 << depth) for i in range(w*h*n)]
            row_result = self.imported(png(w, h, values, n=n, depth=depth))
            expected = self.check_blocks(row_result, w, h, depth, n, values)
            interlaced = self.imported(png(w, h, values, n=n, depth=depth, interlaced=True))
            self.assertEqual(interlaced['normalization']['decode_storage'], 'complete_decoded_frame')
            self.assertEqual(self.check_blocks(interlaced, w, h, depth, n, values), expected)
            buffered = self.imported(tiff(w, h, values, n=n, depth=f'u{depth}'), color_policy='assume_srgb')
            self.assertEqual(self.check_blocks(buffered, w, h, depth, n, values), expected)
            self.assertEqual(interlaced['storage']['created_tiles'], 0)
            self.assertEqual(buffered['storage']['created_tiles'], 0)
        self.imported(png(2, 1, [12, 34], n=1, depth=8))
        inline = self.cli('sample.import', source_path='source.png', id='inline')
        self.assertEqual(inline['normalization']['decode_storage'], 'complete_decoded_frame')
        self.assertEqual(inline['document']['items'][0]['content']['grid']['data_hex'], '0cff22ff')

    def test_late_decode_and_metadata_errors_publish_no_blocks(self):
        w, h = 129, 129
        valid = png(w, h, [1, 2, 3, 4]*(w*h), depth=8)
        # Valid chunk CRCs reach the row decoder; the last row uses an invalid filter.
        invalid_filter = packed_png(w, h, 8, 6, (b'\0'+bytes([1, 2, 3, 4])*w)*(h-1)
                                    + b'\5'+bytes([1, 2, 3, 4])*w)
        # A truncated zlib stream retains valid PNG chunk framing and CRCs.
        offset = valid.index(b'IDAT')
        length = struct.unpack('>I', valid[offset-4:offset])[0]
        incomplete = (valid[:offset-4] + chunk(b'IDAT', valid[offset+4:offset+4+length-5])
                      + chunk(b'IEND', b''))
        metadata = valid[:-12] + chunk(b'iTXt', b'Inkbolt Metadata'+bytes(5)+b'{broken') + valid[-12:]
        for data, fields, code in [
            (invalid_filter, {}, 'INVALID_IMAGE'), (incomplete, {}, 'INVALID_IMAGE'),
            (valid[:-12], {}, 'INVALID_IMAGE'), (metadata, {}, 'INVALID_METADATA'),
            (valid, dict(resolution_ppi=0), 'INVALID_DOCUMENT'),
            (valid, dict(color_policy='assume_linear_srgb'), 'UNSUPPORTED'),
        ]:
            with self.subTest(code=code, fields=fields, size=len(data)):
                self.imported(data, error=code, **fields)
                self.assertEqual([p.name for p in self.root.iterdir()], ['source.png'])

    def test_mcp_receipt_and_reimport_reuse_preserve_existing_files(self):
        w, h = 129, 129
        values = [c for y in range(h) for x in range(w) for c in [x*257, y*257, x+y, 65535]]
        data = png(w, h, values)
        before = self.imported(data)
        manifest = self.check_blocks(before, w, h, 16, 4, values)
        files = {p.name: (p.stat().st_mtime_ns, p.read_bytes())
                 for p in (self.root / '.inkbolt/assets').iterdir()}
        with closing(Client(('--tools', 'core'), workspace=self.root)) as client:
            client.initialize()
            def dispatch(command, **arguments):
                response = client.tool('run', command=command, arguments=arguments)
                self.assertFalse(response['isError'], response)
                return response['structuredContent']['result']
            after = self.imported(data, call=dispatch)
            self.assertEqual(after['document'], before['document'])
            self.assertEqual(after['normalization'], before['normalization'])
            self.assertEqual(self.check_blocks(after, w, h, 16, 4, values), manifest)
            self.assertEqual(after['storage']['created_tiles'], 0)
            self.assertEqual(after['storage']['existing_tiles'], len(set(manifest['tiles'])))
        self.assertEqual(files, {p.name: (p.stat().st_mtime_ns, p.read_bytes())
                                for p in (self.root / '.inkbolt/assets').iterdir()})


if __name__ == '__main__':
    unittest.main()
