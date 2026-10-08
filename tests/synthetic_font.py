"""Original geometric SFNT fixture, built from the public OpenType table specifications.
No downloaded font or font implementation is included. Shapes and metrics are deliberately
simple so independently calculated expected bounds and pixels can detect layout errors.
"""
import struct


def pack(fmt,*values):
    return struct.pack('>'+fmt,*values)


def checksum(data):
    data+=bytes((-len(data))%4)
    return sum(struct.unpack('>'+str(len(data)//4)+'I',data))&0xffffffff


def geometric_font(rectangle_advance=600, additional_mapping=None):
    def glyph(points):
        xs=[p[0] for p in points];ys=[p[1] for p in points]
        head=pack('hhhhhHH',1,min(xs),min(ys),max(xs),max(ys),len(points)-1,0)
        flags=bytes(p[2] for p in points)
        dx=[xs[0]]+[b-a for a,b in zip(xs,xs[1:])]
        dy=[ys[0]]+[b-a for a,b in zip(ys,ys[1:])]
        return head+flags+pack('h'*len(dx),*dx)+pack('h'*len(dy),*dy)
    rectangle=glyph([(50,0,1),(50,700,1),(450,700,1),(450,0,1)])
    arch=glyph([(0,0,1),(500,1000,0),(1000,0,1)])
    glyph_data=[b'',b'',rectangle,arch];loca=[0];glyf=b''
    for g in glyph_data:
        glyf+=g+bytes((-len(g))%4);loca.append(len(glyf))
    head=bytearray(54)
    struct.pack_into('>IIIIHH',head,0,0x10000,0x10000,0,0x5f0f3cf5,0,1000)
    struct.pack_into('>hhhhHHhhh',head,36,0,0,1000,1000,0,8,2,1,0)
    hhea=pack('IhhhHhhhhhhhhhhhH',0x10000,800,-200,0,1200,0,0,1000,1,0,0,0,0,0,0,0,4)
    mapping={32:1,65:2,66:3,233:2,128512:2}
    if additional_mapping:
        mapping.update(additional_mapping)
    cmap12=pack('HHIII',12,0,16+12*len(mapping),0,len(mapping))+b''.join(pack('III',c,c,g) for c,g in sorted(mapping.items()))
    cmap=pack('HHHHI',0,1,3,10,12)+cmap12
    kern=pack('HHHHHHHHHHHh',0,1,0,20,1,1,6,0,0,2,3,-100)
    tables={b'head':bytes(head),b'hhea':hhea,b'maxp':pack('IH'+'H'*13,0x10000,4,4,1,0,0,1,0,0,0,0,0,0,0,0),b'hmtx':b''.join(pack('Hh',a,l) for a,l in [(600,0),(300,0),(rectangle_advance,50),(1200,0)]),b'loca':pack('I'*5,*loca),b'glyf':glyf,b'cmap':cmap,b'kern':kern}
    n=len(tables);power=2**(n.bit_length()-1)
    header=pack('IHHHH',0x10000,n,power*16,power.bit_length()-1,n*16-power*16)
    offset=12+16*n;directory=b'';payload=b'';head_offset=None
    for tag,data in sorted(tables.items()):
        directory+=tag+pack('III',checksum(data),offset,len(data))
        if tag==b'head':head_offset=offset
        padded=data+bytes((-len(data))%4);payload+=padded;offset+=len(padded)
    font=bytearray(header+directory+payload)
    struct.pack_into('>I',font,head_offset+8,(0xb1b0afba-checksum(bytes(font)))&0xffffffff)
    assert checksum(bytes(font))==0xb1b0afba
    return bytes(font)
