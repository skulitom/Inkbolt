"""Original compressed fixtures exceed the old frame cap without large Python grids."""
import hashlib
import struct
import unittest
import zlib

import test_agent_workspace as workspace


def pixel(x, y, unit):
    if unit == 2:
        return struct.pack('<4H', x * 7919 % 65536, y * 3571 % 65536, x ^ y, 65535)
    # Distinct low bits, signed zero and a subnormal must survive exactly.
    return struct.pack('<4I', 0x3f000000 + x, 0x3e800000 + y,
                       0x80000000 if (x + y) % 2 else 1, 0x3f800000)


def png_fixture(width, height, interlaced=False):
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    codec = zlib.compressobj()
    encoded = []
    passes = ([(0,0,8,8),(4,0,8,8),(0,4,4,8),(2,0,4,4),(0,2,2,4),(1,0,2,2),(0,1,1,2)]
              if interlaced else [(0,0,1,1)])
    for x0, y0, dx, dy in passes:
        if x0 >= width or y0 >= height:
            continue
        for y in range(y0, height, dy):
            row = b''.join(struct.pack('>4H', *struct.unpack('<4H', pixel(x // 128, y // 128, 2)))
                           * max(0, (min(128, width - x) - x0 + dx - 1)//dx)
                           for x in range(0, width, 128))
            encoded.append(codec.compress(b'\0' + row))
    encoded.append(codec.flush())
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 16, 6, 0, 0, int(interlaced)))
            + chunk(b'sRGB', b'\0') + chunk(b'IDAT', b''.join(encoded)) + chunk(b'IEND', b''))


def tiff_fixture(width, height, unit=2, whole_strip=False, tile_size=128):
    chunks = []
    cw, ch = (width, height) if whole_strip else (tile_size, tile_size)
    for y0 in range(0, height, ch):
        for x0 in range(0, width, cw):
            codec = zlib.compressobj()
            parts = []
            for y in range(y0, y0 + ch):
                row = b''.join(pixel(x // 128, y // 128, unit) * min(128, x0 + cw - x)
                               for x in range(x0, x0 + cw, 128))
                parts.append(codec.compress(row))
            parts.append(codec.flush())
            chunks.append(b''.join(parts))
    offsets_tag, lengths_tag = (273, 279) if whole_strip else (324, 325)
    tags = {256:(4,[width]),257:(4,[height]),258:(3,[unit*8]*4),259:(3,[8]),262:(3,[2]),
            277:(3,[4]),284:(3,[1]),338:(3,[2]),339:(3,[3 if unit == 4 else 1]*4),
            offsets_tag:(4,[0]*len(chunks)),lengths_tag:(4,[len(c) for c in chunks])}
    tags.update({278:(4,[height])} if whole_strip else {322:(4,[cw]),323:(4,[ch])})
    def header():
        tail = bytearray()
        rows = []
        start = 8 + 2 + len(tags)*12 + 4
        for tag, (kind, values) in sorted(tags.items()):
            blob = struct.pack('<' + ('H' if kind == 3 else 'I')*len(values), *values)
            if len(blob) > 4:
                field = struct.pack('<I', start + len(tail))
                tail.extend(blob)
            else:
                field = blob.ljust(4, b'\0')
            rows.append(struct.pack('<HHI', tag, kind, len(values)) + field)
        return b'II' + struct.pack('<HIH', 42, 8, len(tags)) + b''.join(rows) + bytes(4) + tail
    at = len(header())
    offsets = []
    for chunk in chunks:
        offsets.append(at)
        at += len(chunk)
    tags[offsets_tag] = (4, offsets)
    return header() + b''.join(chunks)


def verify_blocks(result, root, width, height, unit):
    manifest = result['document']['items'][0]['content']['grid']['base']
    expected_spec = dict(width=width, height=height, depth='u16' if unit == 2 else 'f32',
                         channels='rgba', encoding='encoded_srgb')
    assert manifest['spec'] == expected_spec
    identities = []
    for y in range(0, height, 128):
        for x in range(0, width, 128):
            w, h = min(128, width-x), min(128, height-y)
            expected = (b'INKTILE1' + struct.pack('<IIBBBB', w, h, unit, 4, 0, 0)
                        + pixel(x // 128, y // 128, unit)*(w*h))
            identity = hashlib.sha256(expected).hexdigest()
            assert (root/(identity + '.native-tile')).read_bytes() == expected
            identities.append(identity)
    assert len(set(identities)) == len(identities), 'Every block must be distinct'
    assert manifest['tiles'] == identities
    raw = (b'INKGRID1INKTILE1' + struct.pack('<IIBBBBI', width, height, unit, 4, 0, 0, 128)
           + b''.join(bytes.fromhex(i) for i in identities))
    assert manifest['sha256'] == hashlib.sha256(raw).hexdigest()
    assert result['storage']['decoded_bytes'] == width*height*4*unit
    assert result['storage']['manifest_sha256'] == manifest['sha256']


class NativeImportCapacityTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli

    def test_png_and_tiff_above_old_frame_limit_preserve_every_native_byte(self):
        # 72 MiB RGBA16 and 68 MiB binary32: both exceeded the old 64 MiB cap.
        for kind, width, height, unit in [('png',3072,3072,2), ('tiff',2112,2112,4)]:
            with self.subTest(kind=kind):
                data = png_fixture(width, height) if kind == 'png' else tiff_fixture(width, height, unit)
                path = self.root/(kind + '.image')
                path.write_bytes(data)
                result = self.cli('sample.import', source_path=path.name, id=kind,
                                  color_policy='assume_srgb', storage={})
                self.assertEqual(path.read_bytes(), data)
                self.assertEqual(result['source_sha256'], hashlib.sha256(data).hexdigest())
                self.assertEqual(result['source_bytes'], len(data))
                self.assertFalse(result['source_changed'])
                verify_blocks(result, self.root/'.inkbolt/assets', width, height, unit)

    def test_source_defined_full_frame_chunk_keeps_separate_codec_limit(self):
        data = tiff_fixture(3072, 3072, whole_strip=True)
        path = self.root/'too-large-chunk.tif'
        path.write_bytes(data)
        self.cli('sample.import', source_path=path.name, id='large', storage={},
                 color_policy='assume_srgb', error='RESOURCE_LIMIT')
        self.assertEqual(path.read_bytes(), data)
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_tiled_native_work_is_not_inline_or_codec_capacity(self):
        caps = self.cli('capabilities')['native_sample_store_library']['import']
        self.assertGreater(caps['max_decoded_bytes'], caps['max_codec_allocation_bytes'])
        self.assertGreater(caps['max_tiff_padded_tile_bytes'], caps['max_codec_allocation_bytes'])
        # Tiny cropped content still charges the padded source tile. Its decoded
        # work exceeds 256 MiB; a compressed file is not permission to allocate it.
        data = bytearray(tiff_fixture(1, 1, tile_size=128))
        count = struct.unpack_from('<H', data, 8)[0]
        for index in range(count):
            at = 10 + 12*index
            if struct.unpack_from('<H', data, at)[0] in (322, 323):
                struct.pack_into('<I', data, at+8, 8192)
        path = self.root/'padded.tif'
        path.write_bytes(data)
        self.cli('sample.import', source_path=path.name, id='padded', storage={},
                 color_policy='assume_srgb', error='RESOURCE_LIMIT')
        self.assertEqual(list(self.root.iterdir()), [path])


if __name__ == '__main__':
    unittest.main()
