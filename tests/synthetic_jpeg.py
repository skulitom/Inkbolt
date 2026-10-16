"""Original DC-only JPEG fixtures; no encoder/library or external image inputs.

An 8x8 constant block has only a DC coefficient, exactly 8*(sample-128),
with unit quantization. Thus decoded samples have an independent exact oracle.
"""
import struct


def segment(marker, body):
    return bytes([255, marker]) + struct.pack('>H', len(body) + 2) + body


def exif(orientation=None, *, little=True, srgb=False, thumbnail=None):
    order = '<' if little else '>'
    pack = lambda fmt, *v: struct.pack(order + fmt, *v)
    entries = []
    if orientation is not None:
        entries.append(pack('HHI', 274, 3, 1) + pack('H', orientation) + bytes(2))
    primary_end = 8 + 2 + 12 * (len(entries) + int(srgb)) + 4
    if srgb:
        entries.append(pack('HHII', 34665, 4, 1, primary_end))
    color = pack('HHHIH', 1, 40961, 3, 1, 1) + bytes(2) + pack('I', 0) if srgb else b''
    thumb_at = primary_end + len(color) if thumbnail is not None else 0
    primary = pack('H', len(entries)) + b''.join(entries) + pack('I', thumb_at)
    thumb = (pack('HHHIH', 1, 274, 3, 1, thumbnail) + bytes(2) + pack('I', 0)
             if thumbnail is not None else b'')
    return segment(0xe1, b'Exif\0\0' + (b'II' if little else b'MM')
                   + pack('HI', 42, 8) + primary + color + thumb)


def value(x, y, channel):
    return 24 + ((x // 8) * 29 + (y // 8) * 41 + channel * 53) % 208


def pixels(width, height, channels):
    return bytes(v for y in range(height) for x in range(width)
                 for v in [*(value(x, y, c) for c in range(channels)), 255])


def entropy(bits):
    bits += '1' * (-len(bits) % 8)
    raw = bytes(int(bits[i:i+8], 2) for i in range(0, len(bits), 8))
    return raw.replace(b'\xff', b'\xff\0')


def jpeg(width=17, height=9, *, channels=3, progressive=False, extras=b'', subsampling=None,
         restart=0, sample=value):
    ids = [1] if channels == 1 else [1, 2, 3] if subsampling else list(b'RGB')
    mh, mv = subsampling or (1, 1)
    factors = [(mh, mv), (1, 1), (1, 1)][:channels]
    quant = segment(0xdb, bytes([0]) + bytes([1]) * 64)
    # Twelve four-bit DC codes; one one-bit AC end-of-block code.
    tables = segment(0xc4, bytes([0, 0, 0, 0, 12]) + bytes(12) + bytes(range(12))
                     + bytes([16, 1]) + bytes(15) + bytes([0]))
    frame = segment(0xc2 if progressive else 0xc0,
                    struct.pack('>BHHB', 8, height, width, channels)
                    + b''.join(bytes([i, (h << 4) | v, 0]) for i, (h, v) in zip(ids, factors)))
    scan = lambda components, first, last: segment(0xda, bytes([len(components)])
                    + b''.join(bytes([i, 0]) for i in components) + bytes([first, last, 0]))
    previous = [0] * channels
    dc_units = []
    def coded(units):
        interval = restart or len(units)
        return b''.join((bytes([255, 0xd0 + ((i//interval-1) % 8)]) if i else b'')
                       + entropy(''.join(units[i:i+interval]))
                       for i in range(0, len(units), interval))
    blocks = [(x, y) for y in range(0, height, mv*8) for x in range(0, width, mh*8)]
    for index, (x, y) in enumerate(blocks):
        if restart and index % restart == 0:
            previous = [0] * channels
        dc_bits = []
        for c in range(channels):
            h, v = factors[c]
            for dy in range(v):
                for dx in range(h):
                    channel = 128 if subsampling and c else sample(x+dx*8, y+dy*8, c)
                    dc = 8 * (channel - 128)
                    difference, previous[c] = dc - previous[c], dc
                    size = abs(difference).bit_length()
                    amplitude = difference if difference >= 0 else difference + (1 << size) - 1
                    dc_bits.append(f'{size:04b}' + (f'{amplitude:0{size}b}' if size else '')
                                   + ('' if progressive else '0'))
        dc_units.append(''.join(dc_bits))
    scans = scan(ids, 0, 0 if progressive else 63) + coded(dc_units)
    if progressive:
        for i, (h, v) in zip(ids, factors):
            count = ((width*h + mh*8-1)//(mh*8)) * ((height*v + mv*8-1)//(mv*8))
            scans += scan([i], 1, 63) + coded(['0'] * count)
    interval = segment(0xdd, struct.pack('>H', restart)) if restart else b''
    return b'\xff\xd8' + extras + quant + tables + frame + interval + scans + b'\xff\xd9'


def refined(*, new_coefficient=False, eob_overrun=False):
    """Original progressive AC refinement: two blocks/EOB run or one new term.

    Unit: DC=0; zigzag AC[1] starts at 4, then refines to 5. The optional new
    AC[2]=1 exercises sign-before-correction ordering. Quantization is 8.
    """
    width = 8 if new_coefficient else 16
    quant = segment(0xdb, bytes([0]) + bytes([8])*64)
    tables = segment(0xc4, bytes([0, 1]) + bytes(15) + bytes([0])
                     + bytes([16, 0, 0, 5]) + bytes(13) + bytes([0, 2, 1, 0xf0, 0x10]))
    frame = segment(0xc2, struct.pack('>BHHB', 8, 8, width, 1) + b'\1\x11\0')
    scan = lambda first,last,approx: segment(0xda, bytes([1,1,0,first,last,approx]))
    dc = scan(0,0,0) + entropy('0' * (width//8))
    initial = scan(1,63,1) + entropy('00110000' * (width//8))
    # Table codes 010 = new size-one value, 100 = two/three-block EOB run.
    bits = '01011000' if new_coefficient else '100' + ('1' if eob_overrun else '0') + '11'
    refinement = scan(1,63,0x10) + entropy(bits)
    return b'\xff\xd8' + quant + tables + frame + dc + initial + refinement + b'\xff\xd9'


def oriented(raw, width, height, channels, orientation):
    """Forward placement oracle, independent of the engine's inverse lookup."""
    ow, oh = (height, width) if orientation >= 5 else (width, height)
    output = bytearray(len(raw))
    unit = channels + 1
    for y in range(height):
        for x in range(width):
            ox, oy = {
                1: (x, y), 2: (width-1-x, y), 3: (width-1-x, height-1-y),
                4: (x, height-1-y), 5: (y, x), 6: (height-1-y, x),
                7: (height-1-y, width-1-x), 8: (y, width-1-x),
            }[orientation]
            output[(oy*ow+ox)*unit:(oy*ow+ox+1)*unit] = raw[(y*width+x)*unit:(y*width+x+1)*unit]
    return ow, oh, bytes(output)
