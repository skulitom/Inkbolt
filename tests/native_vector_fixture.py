"""Original tiny editable data and PDF/Zstandard framing, using only stdlib."""
import zlib
import uuid


def board(name, rect, locked=False):
    left, top, right, bottom = rect
    return f'''/Dictionary :
1 /Real (PAR) , ({name}) /UnicodeString (Name) ,
{left} {top} /RealPointRelToROrigin (PositionPoint1) ,
{right} {bottom} /RealPointRelToROrigin (PositionPoint2) ,
0 0 /RealPoint (RulerOrigin) , 0 /Bool (IsArtboardDefaultName) ,
0 /Int (DisplayMark) , {int(locked)} /Bool (IsArtboardLocked) ,
0 /Bool (IsArtboardSelected) , ({uuid.uuid5(uuid.NAMESPACE_URL, 'inkbolt-fixture-'+name)}) /String (ArtboardUUID) ,
/FillStyle : 0 1 0 0 0 Xy 0 J 0 j 1 w 10 M []0 d 0 XR 0 0 Xd /Def ; (EachArtboardColor) ,
; ,
'''


def layer(name, body, visible=True, locked=False):
    flag = int(visible)
    return f'''%AI5_BeginLayer
{flag} 1 {int(not locked)} 1 0 0 {flag} 0 40 80 120 0 50 0 Lb
({name}) Ln
0 AE
{body}
LB
%AI5_EndLayer--
'''


def path(name, points, rgb=(1, 0, 0), visible=True, locked=False, opacity=1):
    return f'''{int(locked)} A {int(not visible)} Xw
0 O 0 {opacity} 0 0 0 Xy
0 0 0 0 {' '.join(str(x) for x in rgb)} Xa
0 J 0 j 1 w 10 M []0 d 0 XR
{points}
f
%_/ArtDictionary : /XMLUID : ({name}) ; (AI10_ArtUID), ;
4 As
'''


def artwork(curve=False, visible=True, locked=False, opacity=1, layer_visible=True,
            layer_locked=False, board_locked=False):
    # Nonzero origin and two separated views over one layer tree.
    typed = '/Document : /Dictionary :\n/Array :\n' + board('first', (-4, 12, 8, 4))
    typed += board('detail', (12, 10, 20, 4), board_locked) + '; (ArtboardArray) ,\n'
    typed += ''.join(f'0 /Real (Bleed{edge}Value) ,\n' for edge in ('Top','Right','Bottom','Left'))
    typed += '; /Recorded , /Dictionary : ; /NotRecorded , ;'
    setup = '\n'.join('%_' + line for line in typed.splitlines())
    first = path('underlay', '-4 12 m 8 12 L 8 4 L -4 4 L -4 12 L', (0,0,1))
    first += path('detail-fill', '14 9 m 18 9 L 18 6 L 14 6 L 14 9 L', (0,1,0))
    points = ('-2 10 m 0 11 2 11 4 10 C 4 6 L -2 6 L -2 10 L' if curve
              else '-2 10 m 4 10 L 4 6 L -2 6 L -2 10 L')
    top = path('overlay', points, visible=visible, locked=locked, opacity=opacity)
    return ('''%!PS-Original-Inkbolt-Fixture
%%AI8_CreatorVersion: 30.0.0
%AI5_FileFormat 14.0
%AI9_ColorModel: 1
%AI24_LargeCanvasScale: 1
%AI5_NumLayers: 2
%%BeginProlog
%%EndProlog
%%BeginSetup
%AI9_BeginDocumentData
''' + setup + '\n%AI9_EndDocumentData\n%%EndSetup\n' + layer('Base', first) +
            layer('Top', top, layer_visible, layer_locked) +
            '%%PageTrailer\ngsave annotatepage grestore showpage\n%%Trailer\n%%EOF\n').encode('ascii')


def zstandard_raw(data, declared=None, checksum=None):
    """RFC 8878 single-segment frame containing original raw blocks."""
    size = len(data) if declared is None else declared
    # Four-byte frame content size, single segment, optional content checksum.
    frame = bytearray(b'\x28\xb5\x2f\xfd' + bytes([0xa0 | (4 if checksum is not None else 0)]))
    frame += size.to_bytes(4, 'little')
    for start in range(0, len(data), 131072):
        chunk = data[start:start+131072]
        frame += ((len(chunk) << 3) | int(start+len(chunk)==len(data))).to_bytes(3, 'little')
        frame += chunk
    if checksum is not None:
        frame += checksum.to_bytes(4, 'little')
    return bytes(frame)


def objects(data=None, compressed=False, pieces=1, flate=False, indirect_length=False,
            encoded=None, metadata=None, creator=30):
    data = artwork() if data is None else data
    metadata = data.split(b'%%BeginProlog')[0] if metadata is None else metadata
    if encoded is None:
        encoded = b'%AI24_ZStandard_Data' + zstandard_raw(data) if compressed else data
    blocks = [encoded[len(encoded)*n//pieces:len(encoded)*(n+1)//pieces] for n in range(pieces)]
    # Deliberately unrelated preview; it must never become editable artwork.
    result = {
        1: b'<< /Type /Catalog /Pages 2 0 R >>',
        2: b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        3: b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 1 1] /Contents 4 0 R /PieceInfo << /InkboltFixture << /Private 5 0 R >> >> >>',
        4: b'<< /Length 11 >>\nstream\n0 0 1 1 re\n\nendstream',
    }
    mapping = ' '.join(f'/AIPrivateData{n+1} {n+7} 0 R' for n in range(pieces))
    result[5] = (f'<< /ContainerVersion 12 /CreatorVersion {creator} /RoundtripVersion 24 '
                 f'/NumBlock {pieces} /AIMetaData 6 0 R {mapping} ' +
                 ('/RoundtripStreamType 2 ' if compressed else '') + '>>').encode()
    for n, chunk in enumerate([metadata] + blocks, 6):
        raw = zlib.compress(chunk) if flate else chunk
        length_id = 7+pieces+(n-6)
        length = f'{length_id} 0 R' if indirect_length else str(len(raw))
        if indirect_length:
            result[length_id] = str(len(raw)).encode()
        result[n] = (f'<< /Length {length} ' + ('/Filter /FlateDecode ' if flate else '') + '>>\nstream\n').encode() + raw + b'\nendstream'
    return result


def pdf(objects, trailer_extra=b'', xref_delta=0):
    out = bytearray(b'%PDF-1.7\n% original synthetic container\n')
    offsets = {}
    for key, value in sorted(objects.items()):
        offsets[key] = len(out)
        out += f'{key} 0 obj\n'.encode() + value + b'\nendobj\n'
    xref = len(out)
    out += f'xref\n0 {max(objects)+1}\n0000000000 65535 f \n'.encode()
    for key in range(1, max(objects)+1):
        out += (f'{offsets[key]:010d} 00000 n \n' if key in offsets else '0000000000 00000 f \n').encode()
    out += f'trailer\n<< /Size {max(objects)+1} /Root 1 0 R '.encode() + trailer_extra
    return bytes(out + f'>>\nstartxref\n{xref+xref_delta}\n%%EOF\n'.encode())


def source(**kwargs):
    return pdf(objects(**kwargs))
