"""Original synthetic no-engine client. This is a harness control, never a model trial."""
import json
from pathlib import Path
import shutil
import struct
import sys
import zlib

root=Path(sys.argv[1]);source=root/'original.tiff';target=root/'edited.tiff'
# Read only standard TIFF directory fields. This control does not import any
# engine, benchmark solver, fixture generator or artifact oracle.
with source.open('rb') as stream:
    assert stream.read(4)==b'II*\0'
    stream.seek(struct.unpack('<I',stream.read(4))[0]);count=struct.unpack('<H',stream.read(2))[0]
    entries=[struct.unpack('<HHI4s',stream.read(12)) for _ in range(count)]
    assert stream.read(4)==bytes(4)
    tags={}
    for tag,kind,size,data in entries:
        unit={3:2,4:4}[kind]
        if size*unit>4:
            stream.seek(struct.unpack('<I',data)[0]);data=stream.read(size*unit)
        else:data=data[:size*unit]
        tags[tag]=struct.unpack('<'+('H' if kind==3 else 'I')*size,data)
    width,height=tags[256][0],tags[257][0]
    assert (width,height)==(8192,6144) and tags[258]==(16,)*4 and tags[259]==(1,)
    strip_height=tags[278][0]
    def offset(x,y):return tags[273][y//strip_height]+((y%strip_height)*width+x)*8
    stream.seek(0)
    with target.open('xb') as output:shutil.copyfileobj(stream,output,1024*1024)
    preview=bytearray()
    with target.open('r+b') as output:
        for y in range(3835,3835+16):
            stream.seek(offset(5114-96,y));row=stream.read(20*8)
            output.seek(offset(5114,y));output.write(row)
            preview.extend((v[0]*255+32767)//65535 for v in struct.iter_unpack('<H',row))
def chunk(name,data):
    return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data)&0xffffffff)
png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',20,16,8,6,0,0,0))
png+=chunk(b'IDAT',zlib.compress(b''.join(b'\0'+preview[y*80:(y+1)*80] for y in range(16))))+chunk(b'IEND',b'')
with (root/'preview.png').open('xb') as output:output.write(png)
with (root/'editable.json').open('x') as output:
    json.dump(dict(width=width,height=height,image='edited.tiff',depth='u16',channels='rgba',encoding='encoded_srgb',
                   transform=[1,0,0,1,0,0]),output)
