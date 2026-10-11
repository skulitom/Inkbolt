"""Original Adam7 streams and independent complete native block identities."""
from contextlib import closing
import struct
import unittest
import zlib

from test_images_cli import chunk
from test_mcp import Client
import test_native_import_rows as native


# PNG section 8.1 assigns every position of this repeating cell to one pass.
# The fixture enumerates the cell, independently of the engine's stride table.
CELL = ((1, 6, 4, 6, 2, 6, 4, 6), (7,)*8,
        (5, 6, 5, 6, 5, 6, 5, 6), (7,)*8,
        (3, 6, 4, 6, 3, 6, 4, 6), (7,)*8,
        (5, 6, 5, 6, 5, 6, 5, 6), (7,)*8)


def filtered(raw, previous, stride, kind):
    result = bytearray()
    for i, value in enumerate(raw):
        left = raw[i-stride] if i >= stride else 0
        above = previous[i] if previous else 0
        corner = previous[i-stride] if previous and i >= stride else 0
        if kind == 4:
            estimate = left + above - corner
            prediction = min((left, above, corner), key=lambda v: abs(v-estimate))
        else:
            prediction = (0, left, above, (left+above)//2)[kind]
        result.append((value-prediction) % 256)
    return bytes([kind]) + result


def encode(width, height, depth, color, values, extras=(), fault=None):
    n = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    rows = []
    for number in range(1, 8):
        previous = b''
        for y in range(height):
            columns = [x for x in range(width) if CELL[y % 8][x % 8] == number]
            if not columns:
                continue
            samples = [v for x in columns for v in values[(y*width+x)*n:(y*width+x+1)*n]]
            if depth < 8:
                packed = bytearray((len(samples)*depth+7)//8)
                for i, v in enumerate(samples):
                    packed[i*depth//8] |= v << (8-depth-(i*depth % 8))
                raw = bytes(packed)
            else:
                raw = struct.pack('>' + ('H' if depth == 16 else 'B')*len(samples), *samples)
            rows.append(filtered(raw, previous, max(1, (n*depth+7)//8), (number+y) % 5))
            previous = raw
    if fault == 'filter':
        rows[-1] = b'\5' + rows[-1][1:]
    if fault == 'missing':
        rows.pop()
    data = zlib.compress(b''.join(rows))
    if fault == 'checksum':
        data = data[:-1] + bytes([data[-1] ^ 1])
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, depth, color, 0, 0, 1))
            + chunk(b'sRGB', b'\0') + b''.join(chunk(k, v) for k, v in extras)
            + b''.join(chunk(b'IDAT', data[i:i+71]) for i in range(0, len(data), 71))
            + chunk(b'IEND', b''))


class NativePngPassTests(unittest.TestCase):
    setUp = native.NativeImportRowTests.setUp
    cli = native.NativeImportRowTests.cli
    imported = native.NativeImportRowTests.imported
    check_blocks = native.NativeImportRowTests.check_blocks

    def check(self, data, width, height, depth, n, expected):
        result = self.imported(data)
        self.assertEqual(result['normalization']['decode_storage'], 'adam7_passes_to_native_blocks')
        return self.check_blocks(result, width, height, depth, n, expected)

    def test_all_channels_depths_and_filters_across_native_block_edges(self):
        w, h = 131, 133
        for depth in (8, 16):
            maximum = (1 << depth)-1
            for n, color in ((1, 0), (2, 4), (3, 2), (4, 6)):
                with self.subTest(depth=depth, channels=n):
                    values = [(x*7919+y*3571+c*2311) & maximum
                              for y in range(h) for x in range(w) for c in range(n)]
                    expected = [v for i in range(w*h) for v in
                                values[i*n:(i+1)*n]+([maximum] if n in (1, 3) else [])]
                    self.check(encode(w,h,depth,color,values), w,h,depth,2 if n<3 else 4,expected)

    def test_empty_passes_and_narrow_last_rows_never_create_phantom_pixels(self):
        for w, h in ((1,1), (1,17), (17,1), (2,3), (4,4), (5,9), (129,2), (3,257)):
            with self.subTest(width=w, height=h):
                values = [(i*997) % 65536 for i in range(w*h*4)]
                self.check(encode(w,h,16,6,values),w,h,16,4,values)

    def test_every_low_gray_depth_and_transparent_key_preserve_expansion(self):
        w, h = 133, 9
        for depth in (1, 2, 4):
            maximum = (1 << depth)-1
            values = [(x+3*y) & maximum for y in range(h) for x in range(w)]
            expected = [v for value in values for v in (value*255//maximum, 0 if value == 1 else 255)]
            self.check(encode(w,h,depth,0,values,[(b'tRNS',struct.pack('>H',1))]), w,h,8,2,expected)

    def test_every_palette_depth_partial_alpha_and_hidden_color(self):
        w, h = 129, 131
        for depth in (1, 2, 4, 8):
            count = 1 << depth
            palette = bytes(v for i in range(count) for v in (i, (i*73)%256, 255-i))
            alpha = bytes([0, 123])
            values = [(x+7*y) % count for y in range(h) for x in range(w)]
            expected = [v for i in values for v in
                        list(palette[i*3:i*3+3])+[alpha[i] if i < len(alpha) else 255]]
            self.check(encode(w,h,depth,3,values,[(b'PLTE',palette),(b'tRNS',alpha)]),w,h,8,4,expected)

    def test_rgb_and_gray_transparent_keys_keep_exact_sixteen_bit_color(self):
        w, h = 9, 11
        for n, color, key in ((1,0,[12345]), (3,2,[12345,23456,34567])):
            values = [v+(i%2) for i in range(w*h) for v in key]
            expected = [v for i in range(w*h) for v in
                        values[i*n:(i+1)*n]+[65535 if i%2 else 0]]
            data = encode(w,h,16,color,values,[(b'tRNS',struct.pack('>'+'H'*n,*key))])
            self.check(data,w,h,16,2 if n==1 else 4,expected)

    def test_late_pass_checksum_metadata_and_dimension_failures_publish_nothing(self):
        w, h = 129, 131
        values = [10,20,30,0]*(w*h)
        valid = encode(w,h,8,6,values)
        bad_metadata = valid[:-12]+chunk(b'iTXt',b'Inkbolt Metadata'+bytes(5)+b'{bad')+valid[-12:]
        oversized = (b'\x89PNG\r\n\x1a\n'
                     + chunk(b'IHDR',struct.pack('>IIBBBBB',3072,3072,16,6,0,0,1))
                     + chunk(b'sRGB',b'\0')+chunk(b'IDAT',zlib.compress(b''))+chunk(b'IEND',b''))
        cases = [(encode(w,h,8,6,values,fault=f),{},'INVALID_IMAGE')
                 for f in ('filter','missing','checksum')]
        cases += [(valid[:-12],{},'INVALID_IMAGE'), (bad_metadata,{},'INVALID_METADATA'),
                  (valid,dict(resolution_ppi=0),'INVALID_DOCUMENT'), (oversized,{},'RESOURCE_LIMIT')]
        for data, options, error in cases:
            with self.subTest(error=error, size=len(data), options=options):
                self.imported(data,error=error,**options)
                self.assertEqual([p.name for p in self.root.iterdir()],['source.png'])

    def test_zlib_checksum_is_checked_for_inline_and_noninterlaced_native_imports(self):
        for interlaced in (False, True):
            valid = native.png(3,3,[1,2,3,4]*9,depth=8,interlaced=interlaced)
            offset = valid.index(b'IDAT')
            size = struct.unpack('>I',valid[offset-4:offset])[0]
            stream = valid[offset+4:offset+4+size]
            corrupt = stream[:-1]+bytes([stream[-1]^1])
            data = valid[:offset-4]+chunk(b'IDAT',corrupt)+chunk(b'IEND',b'')
            with self.subTest(interlaced=interlaced):
                self.imported(data,error='INVALID_IMAGE')
                self.cli('sample.import',source_path='source.png',id='inline',error='INVALID_IMAGE')
                self.assertEqual([p.name for p in self.root.iterdir()],['source.png'])

    def test_mcp_and_reimport_preserve_exact_blocks_and_existing_file_times(self):
        w, h = 129, 131
        values = [(i*7919)%65536 for i in range(w*h*4)]
        data = encode(w,h,16,6,values)
        before = self.imported(data)
        self.check_blocks(before,w,h,16,4,values)
        store = self.root/'.inkbolt/assets'
        files = {p.name:(p.stat().st_mtime_ns,p.read_bytes()) for p in store.iterdir()}
        with closing(Client(('--tools','core'),workspace=self.root)) as client:
            client.initialize()
            response = client.tool('run',command='sample.import',arguments=dict(
                source_path='source.png',id='native',storage={}))
            self.assertFalse(response['isError'],response)
            after = response['structuredContent']['result']
            self.assertEqual(after['document'],before['document'])
            self.assertEqual(after['normalization'],before['normalization'])
            self.assertEqual(after['storage']['created_tiles'],0)
        self.assertEqual(files,{p.name:(p.stat().st_mtime_ns,p.read_bytes()) for p in store.iterdir()})
        self.assertEqual((self.root/'source.png').read_bytes(),data)


if __name__ == '__main__':
    unittest.main()
