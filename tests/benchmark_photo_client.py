"""Original synthetic B10 baseline client, independent of the engine and judge.

Only handles the supplied noninterlaced filter-zero RGBA16 fixture. Native byte
processing avoids Pillow's multichannel 8-bit display conversion. Real baseline
runs use the pinned Pillow environment for the focused preview.
"""
import array
import json
from pathlib import Path
import struct
import sys
import zlib


def repaired_source(path):
    encoded=path.read_bytes();assert encoded[:8]==b'\x89PNG\r\n\x1a\n'
    at=8;blocks=[];header=None
    while at<len(encoded):
        length=struct.unpack_from('>I',encoded,at)[0];kind=encoded[at+4:at+8]
        data=encoded[at+8:at+8+length]
        assert zlib.crc32(kind+data)==struct.unpack_from('>I',encoded,at+8+length)[0]
        if kind==b'IHDR': header=struct.unpack('>IIBBBBB',data)
        elif kind==b'IDAT': blocks.append(data)
        at+=length+12
    assert header==(1920,1080,16,6,0,0,0)
    rows=zlib.decompress(b''.join(blocks));stride=1920*8+1
    assert len(rows)==1080*stride and all(rows[y*stride]==0 for y in range(1080))
    values=array.array('H');values.frombytes(b''.join(rows[y*stride+1:(y+1)*stride] for y in range(1080)))
    if sys.byteorder=='little':values.byteswap()
    for y in range(766,780):
        source=(y*1920+1054)*4;target=(y*1920+1150)*4
        values[target:target+48]=values[source:source+48]
    preview=bytes((v*255+32767)//65535 for y in range(766,780) for v in values[(y*1920+1150)*4:(y*1920+1162)*4])
    if sys.byteorder!='little':values.byteswap()
    return values.tobytes(),preview


def native_tiff(samples):
    entries={256:(4,[1920]),257:(4,[1080]),258:(3,[16]*4),259:(3,[1]),262:(3,[2]),
             273:(4,[0]),274:(3,[1]),277:(3,[4]),278:(4,[1080]),279:(4,[len(samples)]),
             284:(3,[1]),338:(3,[2]),339:(3,[1]*4)}
    def header():
        rows=[];tail=bytearray();start=8+2+len(entries)*12+4
        for tag,(kind,values) in sorted(entries.items()):
            data=struct.pack('<'+{3:'H',4:'I'}[kind]*len(values),*values)
            if len(data)>4:
                pointer=struct.pack('<I',start+len(tail));tail.extend(data)
            else:pointer=data.ljust(4,b'\0')
            rows.append(struct.pack('<HHI',tag,kind,len(values))+pointer)
        return b'II'+struct.pack('<HIH',42,8,len(entries))+b''.join(rows)+bytes(4)+tail
    entries[273]=(4,[len(header())])
    return header()+samples


def main():
    root=Path(sys.argv[1]);samples,preview=repaired_source(root/'original.png')
    with (root/'edited.tiff').open('xb') as output:output.write(native_tiff(samples))
    value=dict(width=1920,height=1080,image='edited.tiff',depth='u16',channels='rgba',
               encoding='encoded_srgb',transform=[1,0,0,1,0,0])
    with (root/'editable.json').open('x',encoding='utf-8') as output:json.dump(value,output)
    with (root/'preview.png').open('xb') as output:
        if '--pillow' in sys.argv:
            from PIL import Image
            Image.frombytes('RGBA',(12,14),preview).save(output,format='PNG')
        else:
            def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
            rows=b''.join(b'\0'+preview[y*48:(y+1)*48] for y in range(14))
            output.write(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',12,14,8,6,0,0,0))+
                         chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b''))


if __name__=='__main__':main()
