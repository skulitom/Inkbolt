"""Original layered byte fixtures and an independent structural reader."""
import struct,zlib
U16=lambda v:struct.pack('>H',v)
I16=lambda v:struct.pack('>h',v)
U32=lambda v:struct.pack('>I',v)
U64=lambda v:struct.pack('>Q',v)
I32=lambda v:struct.pack('>i',v)
section=lambda b:U32(len(b))+b
large_section=lambda b:U64(len(b))+b
unicode=lambda s:U32(len(s.encode('utf-16-be'))//2)+s.encode('utf-16-be')
def resource(id,data):return b'8BIM'+U16(id)+b'\0\0'+section(data)+bytes(len(data)%2)
def tag(key,data):return b'8BIM'+key+section(data)+bytes(len(data)%2)
def plane(data,width,compression,version=1):
    if not data:return U16(compression)+(zlib.compress(b'') if compression in [2,3] else b'')
    if compression==0:return U16(0)+data
    if compression in [2,3]:
        if compression==3:data=bytes(v if i%width==0 else (v-data[i-1])%256 for i,v in enumerate(data))
        return U16(compression)+zlib.compress(data)
    # Independently encode literals only; the engine must also decode its repeated runs.
    rows=[b''.join(bytes([len(chunk)-1])+chunk for chunk in [data[i+j:i+min(width,j+128)] for j in range(0,width,128)]) for i in range(0,len(data),width)]
    count=U32 if version==2 else U16
    return U16(1)+b''.join(count(len(r)) for r in rows)+b''.join(rows)
def make(layers,w=8,h=6,compression=0,profile=None,extra_resources=b'',global_extra=b'',merged=None,merged_channels=4,info_alignment=2,version=1,global_mask=b''):
    outer=large_section if version==2 else section;length=U64 if version==2 else U32
    records=I16(-len(layers) if merged_channels==4 else len(layers));channels=b''
    for index,l in enumerate(layers): # File order bottom to top.
        lw,lh=l['width'],l['height'];x,y=l.get('xy',(0,0));p=bytes(l['rgba']);count=lw*lh
        channel_ids=l.get('channel_ids',[-1,0,1,2]);data=l['channel_data'] if 'channel_data' in l else [plane(bytes(p[(3 if c==-1 else c)::4]),lw,compression,version) for c in channel_ids]
        extra=section(l.get('mask',b''))+section(l.get('ranges',b''))+b'\0\0\0\0'+tag(b'luni',unicode(l['name'])+bytes(l.get('name_padding',0)))+tag(b'lyid',U32(l.get('id',index+1)))+l.get('extra',b'')
        records+=b''.join(I32(v) for v in [y,x,y+lh,x+lw])+U16(len(channel_ids))+b''.join(I16(c)+length(len(d)) for c,d in zip(channel_ids,data))+b'8BIM'+l.get('blend',b'norm')+bytes([l.get('opacity',255),l.get('clipping',0),l.get('flags',8 if l.get('visible',True) else 10),0])+section(extra)
        channels+=b''.join(data)
    info=records+channels;info+=bytes((-len(info))%info_alignment);layer_section=outer(info)+section(global_mask)+global_extra
    resources=(resource(1039,profile) if profile else b'')+extra_resources
    merged=bytes(merged) if merged is not None else bytes(w*h*merged_channels)
    return b'8BPS'+U16(version)+bytes(6)+U16(merged_channels)+U32(h)+U32(w)+U16(8)+U16(3)+U32(0)+section(resources)+outer(layer_section)+plane(merged,w,compression,version)
class Reader:
    def __init__(self,b):self.b=b;self.at=0
    def take(self,n):r=self.b[self.at:self.at+n];assert len(r)==n;self.at+=n;return r
    def number(self,fmt):return struct.unpack('>'+fmt,self.take(struct.calcsize('>'+fmt)))[0]
    def section(self,wide=False):return Reader(self.take(self.number('Q' if wide else 'I')))
    def left(self):return len(self.b)-self.at
def decode(b,w,h,version=1):
    r=Reader(b);c=r.number('H')
    if c==0:out=r.take(w*h)
    elif c==1:
        sizes=[r.number('I' if version==2 else 'H') for _ in range(h)];out=bytearray()
        for size in sizes:
            row=Reader(r.take(size));start=len(out)
            while row.left():
                n=row.number('b')
                if n>=0:out.extend(row.take(n+1))
                elif n!=-128:out.extend(row.take(1)*(-n+1))
            assert len(out)-start==w
        out=bytes(out)
    else:
        d=zlib.decompressobj();out=bytearray(d.decompress(r.take(r.left()))+d.flush());assert d.eof and not d.unused_data
        if c==3 and w:
            for start in range(0,len(out),w):
                for i in range(start+1,start+w):out[i]=(out[i]+out[i-1])%256
        out=bytes(out)
    assert len(out)==w*h and not r.left();return out
def parse(b):
    r=Reader(b);assert r.take(4)==b'8BPS';version=r.number('H');assert version in [1,2] and r.take(6)==bytes(6)
    n,h,w,depth,mode=[r.number(f) for f in ['H','I','I','H','H']];assert depth==8 and mode==3
    assert not r.section().left();resources=r.section();values={}
    while resources.left():
        assert resources.take(4)==b'8BIM';id=resources.number('H');length=resources.number('B');resources.take(length);resources.take((length+1)%2);data=resources.section().b;resources.take(len(data)%2);values[id]=data
    ls=r.section(version==2);info=ls.section(version==2);count=info.number('h');layers=[]
    for _ in range(abs(count)):
        box=[info.number('i') for _ in range(4)];channels=[(info.number('h'),info.number('Q' if version==2 else 'I')) for _ in range(info.number('H'))];assert info.take(4)==b'8BIM';blend=info.take(4);opacity,clipping,flags,filler=info.take(4);ex=info.section();mask=ex.section().b;ranges=ex.section().b;length=ex.number('B');ex.take(length);ex.take((4-(length+1)%4)%4);tags={}
        while ex.left():
            assert ex.take(4)==b'8BIM';key=ex.take(4);data=ex.section().b;ex.take(len(data)%2);tags[key]=data
        name=tags[b'luni'];assert len(name)==4+int.from_bytes(name[:4],'big')*2
        layers.append(dict(bounds=box,channels=channels,blend=blend,opacity=opacity,clipping=clipping,visible=not flags&2,name=name[4:].decode('utf-16-be'),tags=tags,mask=mask))
    for l in layers:
        y,x,bottom,right=l['bounds'];planes={}
        for c,length in l['channels']:
            if c==-2:
                my,mx,mb,mr=struct.unpack('>4i',l['mask'][:16]);planes[c]=decode(info.take(length),mr-mx,mb-my,version)
            else:planes[c]=decode(info.take(length),right-x,bottom-y,version)
        l['mask_gray']=planes.get(-2)
        l['rgba']=bytes(v for i in range((bottom-y)*(right-x)) for v in [planes[0][i],planes[1][i],planes[2][i],planes.get(-1,bytes([255])*((bottom-y)*(right-x)))[i]])
    assert info.take(info.left()) in [b'',b'\0'];assert not ls.section().left() and not ls.left()
    merged=decode(r.take(r.left()),w,h*n,version);return dict(version=version,width=w,height=h,channels=n,layers=layers,resources=values,merged=merged)
