"""Row-based original scale fixtures and independent native/TIFF/PNG checks."""
import hashlib
import mmap
import struct
from workload_cases import png_pixels, tiff_tags, require


def file_hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_tiff(path, width, height, row):
    """Original little-endian RGBA16 TIFF, with at most 128 rows per strip."""
    sizes = [width*8*min(128, height-y) for y in range(0, height, 128)]
    tags = {256:(4,[width]), 257:(4,[height]), 258:(3,[16]*4), 259:(3,[1]),
            262:(3,[2]), 273:(4,[0]*len(sizes)), 277:(3,[4]), 278:(4,[128]),
            279:(4,sizes), 284:(3,[1]), 338:(3,[2]), 339:(3,[1]*4)}
    def header():
        start = 8+2+12*len(tags)+4
        entries, tail = [], bytearray()
        for tag, (kind, values) in sorted(tags.items()):
            raw = struct.pack('<'+{3:'H',4:'I'}[kind]*len(values), *values)
            address = struct.pack('<I', start+len(tail)) if len(raw)>4 else raw.ljust(4,b'\0')
            if len(raw)>4:
                tail.extend(raw)
                if len(tail)%2: tail.append(0)
            entries.append(struct.pack('<HHI',tag,kind,len(values))+address)
        return b'II'+struct.pack('<HIH',42,8,len(tags))+b''.join(entries)+bytes(4)+tail
    offset = len(header()); offsets = []
    for size in sizes:
        offsets.append(offset); offset += size
    tags[273] = (4, offsets)
    with path.open('xb') as stream:
        stream.write(header())
        for y in range(height):
            value = row(y)
            require(len(value)==width*8, 'Wrong fixture row length')
            stream.write(value)


def check_native(root, document, width, height, row, depth='u16', tolerance=0):
    """Verify every channel, block framing/hash and the manifest identity."""
    grid = document['items'][0]['content']['grid']
    require(grid.get('storage_version')==2 and not grid.get('patches') and not grid.get('staged'),
            'Expected durable version-2 native storage')
    manifest = grid['base']; code, unit = (2,8) if depth=='u16' else (1,4)
    require(manifest['spec']==dict(width=width,height=height,depth=depth,channels='rgba',encoding='encoded_srgb'),
            'Wrong native sample meaning')
    names, maximum = [], 0
    for top in range(0,height,128):
        rows = [row(y) for y in range(top,min(height,top+128))]
        for left in range(0,width,128):
            w,h = min(128,width-left),len(rows)
            index = len(names); name = manifest['tiles'][index]; names.append(name)
            blob = (root/'.inkbolt/assets'/(name+'.native-tile')).read_bytes()
            expected = b''.join(r[left*unit:(left+w)*unit] for r in rows)
            require(blob[:20]==b'INKTILE1'+struct.pack('<IIBBBB',w,h,code,4,0,0)
                    and len(blob)==20+len(expected) and hashlib.sha256(blob).hexdigest()==name,
                    'Invalid native block framing or identity')
            if tolerance:
                require(depth=='u8', 'Byte tolerance is only defined for RGBA8')
                error = max(abs(a-b) for a,b in zip(blob[20:],expected,strict=True))
                maximum = max(maximum,error)
                require(error<=tolerance and blob[23::4]==expected[3::4], 'JPEG channel error exceeds its bound')
            else:
                require(blob[20:]==expected, f'Native sample mismatch at block {left},{top}')
    typed = b'INKTILE1'+struct.pack('<IIBBBB',width,height,code,4,0,0)
    identity = b'INKGRID1'+typed+struct.pack('<I',128)+b''.join(bytes.fromhex(n) for n in names)
    require(names==manifest['tiles'] and hashlib.sha256(identity).hexdigest()==manifest['sha256'],
            'Native manifest identity or extent mismatch')
    return maximum


def check_tiff(path, width, height, row):
    with path.open('rb') as stream, mmap.mmap(stream.fileno(),0,access=mmap.ACCESS_READ) as data:
        tags = tiff_tags(data)
        require(data[:2]==b'II' and tags[256]==(width,) and tags[257]==(height,)
                and tags[258]==(16,)*4 and tags[259]==(1,) and tags[277]==(4,)
                and tags[338]==(2,) and tags[339]==(1,)*4 and tags.get(284,(1,))==(1,)
                and tags.get(274,(1,))==(1,), 'Wrong TIFF sample meaning')
        require(len(tags[273])==len(tags[279]), 'Missing TIFF strips')
        y=0
        for offset,size in zip(tags[273],tags[279],strict=True):
            require(size%(width*8)==0 and offset+size<=len(data), 'Invalid TIFF strip extent')
            for start in range(offset,offset+size,width*8):
                require(y<height and data[start:start+width*8]==row(y), f'TIFF sample mismatch at row {y}')
                y+=1
        require(y==height, 'Missing TIFF rows')


def check_png(path, width, height, row):
    w,h,actual,_ = png_pixels(path.read_bytes())
    require((w,h)==(width,height) and len(actual)==width*height*4, 'Wrong PNG extent')
    for y in range(height):
        require(actual[y*width*4:(y+1)*width*4]==row(y), f'PNG sample mismatch at row {y}')
