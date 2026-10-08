"""Original monochrome OpenType fixtures, assembled with the Python standard library.

Glyphs are numbered rectangles, not a typeface. Table layouts follow the public
OpenType specification; substitutions and anchors have independent exact oracles.
"""
import struct
from synthetic_font import pack, checksum


MAPPING = {
    32: 1, ord('A'): 2, ord('B'): 3, ord('e'): 4, ord('é'): 5, 0x301: 6,
    0x628: 7, 0x62A: 12, 0x5D0: 17, 0x5D1: 18, 0x4E00: 19, 0x3042: 20,
    0x30A2: 21, 0x30FC: 21, 0x915: 22, 0x93F: 23, ord('f'): 24, ord('i'): 25,
    ord(','): 27, 0xAC00: 28, 0x1100: 29, 0x1161: 30, 0x3B1: 31, 0x416: 32,
}
SETS = {
    'latin': {32, 65, 66, 101, 233, 102, 105, 44},
    'marks': {32, 65, 66, 101, 0x301},
    'arabic': {32, 0x628, 0x62A},
    'hebrew': {32, 0x5D0, 0x5D1},
    'east': {32, 0x4E00, 0x3042, 0x30A2, 0x30FC, 0xAC00},
    'indic': {32, 0x915, 0x93F},
    'all': set(MAPPING),
}
ADVANCES = [600, 300, 600, 650, 500, 500, 0] + [600] * 10 + [700, 700,
    1000, 1000, 1000, 700, 300, 400, 200, 500, 300, 1000, 500, 500, 700, 800]


def rectangle(gid):
    """Known, glyph-distinct rectangle x/y extrema (font units)."""
    if gid in (0, 1):
        return None
    if gid == 6:
        return (0, 0, 100, 100)
    return (50, 0, 150 + gid * 10, 400 + gid * 5)


def sfnt(tables):
    n = len(tables); power = 2 ** (n.bit_length() - 1)
    header = pack('IHHHH', 0x10000, n, power*16, power.bit_length()-1, n*16-power*16)
    offset = 12 + 16*n; directory = b''; payload = b''; head_offset = None
    for tag, data in sorted(tables.items()):
        directory += tag + pack('III', checksum(data), offset, len(data))
        if tag == b'head': head_offset = offset
        padded = data + bytes((-len(data)) % 4); payload += padded; offset += len(padded)
    result = bytearray(header + directory + payload)
    struct.pack_into('>I', result, head_offset+8, (0xB1B0AFBA-checksum(result)) & 0xFFFFFFFF)
    assert checksum(result) == 0xB1B0AFBA
    return bytes(result)


def coverage(glyphs):
    return pack('HH', 1, len(glyphs)) + pack('H'*len(glyphs), *glyphs)


def layout_table(scripts, features, lookups, languages=None):
    """OpenType layout version 1; script default LangSys; explicit lookup indices."""
    def records(entries):
        offset = 2 + 6*len(entries); directory = pack('H', len(entries)); data = b''
        for tag, table in sorted(entries.items()):
            directory += tag + pack('H', offset); data += table; offset += len(table)
        return directory + data
    def langsys(indices):
        return pack('HHH', 0, 0xFFFF, len(indices)) + pack('H'*len(indices), *indices)
    def script_table(tag, indices):
        lang = (languages or {}).get(tag, {})
        default = langsys(indices); header_size = 4 + 6*len(lang)
        header = pack('HH', header_size, len(lang)); offset = header_size+len(default); data=b''
        for name, features in sorted(lang.items()):
            table=langsys(features);header+=name+pack('H',offset);data+=table;offset+=len(table)
        return header+default+data
    script_list = records({tag: script_table(tag, indices) for tag,indices in scripts.items()})
    feature_list = records({tag: pack('HH', 0, len(indices)) + pack('H'*len(indices), *indices)
        for tag, indices in features.items()})
    offset = 2 + 2*len(lookups); lookup_list = pack('H', len(lookups)); data = b''
    for kind, subtable in lookups:
        table = pack('HHHH', kind, 0, 1, 8) + subtable
        lookup_list += pack('H', offset); data += table; offset += len(table)
    lookup_list += data
    return pack('IHHH', 0x10000, 10, 10+len(script_list), 10+len(script_list)+len(feature_list)) + script_list + feature_list + lookup_list


def unicode_font(coverage_set='all', *, ascent=1000, advance_scale=1, ligature_advance=500, additional_mapping=None):
    codes = SETS[coverage_set] if isinstance(coverage_set, str) else set(coverage_set)
    count = len(ADVANCES); glyf = b''; loca = [0]
    for gid in range(count):
        box = rectangle(gid)
        if box:
            x0, y0, x1, y1 = box
            # One clockwise contour, four on-curve points, signed coordinate deltas.
            glyph = pack('hhhhhHH', 1, x0, y0, x1, y1, 3, 0) + bytes([1]*4)
            glyph += pack('hhhhhhhh', x0, 0, x1-x0, 0, y0, y1-y0, 0, y0-y1)
            glyf += glyph + bytes((-len(glyph)) % 4)
        loca.append(len(glyf))
    head = bytearray(54)
    struct.pack_into('>IIIIHH', head, 0, 0x10000, 0x10000, 0, 0x5F0F3CF5, 0, 1000)
    struct.pack_into('>hhhhHHhhh', head, 36, 0, 0, 1000, 1000, 0, 8, 2, 1, 0)
    hhea = pack('IhhhHhhhhhhhhhhhH', 0x10000, ascent, -200, 0, 2000, 0, 0, 1000,
        1, 0, 0, 0, 0, 0, 0, 0, count)
    mapping = {c: g for c, g in MAPPING.items() if c in codes}
    if additional_mapping:
        mapping.update(additional_mapping)
    cmap12 = pack('HHIII', 12, 0, 16+12*len(mapping), 0, len(mapping)) + b''.join(
        pack('III', c, c, g) for c, g in sorted(mapping.items()))
    lookups = []
    # Sorted feature order: fina, init, isol, liga, locl, medi.
    for delta in [4, 2, 1]:
        sub = pack('HHHHH', 2, 10, 2, 7+delta, 12+delta) + coverage([7, 12])
        lookups.append((1, sub))
    # GSUB ligature format1: f,i -> glyph26.
    lookups.append((4, pack('HHHH', 1, 8, 1, 14) + coverage([24]) +
        pack('HHHHH', 1, 4, 26, 2, 25)))
    lookups.append((1, pack('HHHHH', 2, 10, 2, 10, 15) + coverage([7, 12])))
    lookups.append((1, pack('HHHH', 2, 8, 1, 3) + coverage([2])))
    gsub = layout_table({b'arab': [0, 1, 2, 5], b'dev2': [], b'latn': [3]},
        {b'fina':[0], b'init':[1], b'isol':[2], b'liga':[3], b'locl':[5], b'medi':[4]},
        lookups, languages={b'latn':{b'TRK ':[3,4]}})
    # GPOS mark-to-base: acute anchor(0,0) to base anchor(300,750).
    mc = coverage([6]); bc = coverage([2, 3, 4])
    ma = pack('HHH', 1, 0, 6) + pack('Hhh', 1, 0, 0)
    ba = pack('HHHH', 3, 8, 14, 20) + pack('Hhh', 1, 300, 750)*3
    sub = pack('HHHHHH', 1, 12, 12+len(mc), 1, 12+len(mc)+len(bc),
        12+len(mc)+len(bc)+len(ma)) + mc + bc + ma + ba
    gpos = layout_table({b'latn': [0]}, {b'mark': [0]}, [(4, sub)])
    classes = [3 if gid == 6 else 1 for gid in range(2, count)]
    gdef = pack('IHHHH', 0x10000, 12, 0, 0, 0) + pack('HHH', 1, 2, len(classes)) + pack('H'*len(classes), *classes)
    advances = ADVANCES.copy(); advances[26] = ligature_advance
    tables = {b'head': bytes(head), b'hhea': hhea,
        b'maxp': pack('IH'+'H'*13, 0x10000, count, 4, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0),
        b'hmtx': b''.join(pack('Hh', a*advance_scale, 0 if i in (0, 1, 6) else 50) for i, a in enumerate(advances)),
        b'loca': pack('I'*len(loca), *loca), b'glyf': glyf,
        b'cmap': pack('HHHHI', 0, 1, 3, 10, 12)+cmap12,
        b'GSUB': gsub, b'GPOS': gpos, b'GDEF': gdef}
    return sfnt(tables)
