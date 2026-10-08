"""Original APNG framing and rational frame oracle; no engine implementation imports."""
from fractions import Fraction as F
import struct
import zlib
from test_images_cli import chunk, png
from test_editing_cli import png_pixels


def chunks(data):
    at=8;result=[]
    while at<len(data):
        n=struct.unpack_from('>I',data,at)[0];kind=data[at+4:at+8];payload=data[at+8:at+8+n]
        assert chunk(kind,payload)==data[at:at+12+n]
        result.append((kind,payload));at+=12+n
    assert at==len(data)
    return result


def apng(w,h,frames,plays=0,poster=None,tagged=True,interlace=False):
    parts=[(b'IHDR',struct.pack('>IIBBBBB',w,h,8,6,0,0,int(interlace)))]
    if tagged:parts.append((b'sRGB',b'\0'))
    parts.append((b'acTL',struct.pack('>II',len(frames),plays)));seq=0
    def data(width,height,rgba):
        return b''.join(p for k,p in chunks(png(width,height,rgba,interlace=interlace)) if k==b'IDAT')
    if poster is not None:parts.append((b'IDAT',data(w,h,poster)))
    for i,f in enumerate(frames):
        fw,fh=f.get('size',(w,h));x,y=f.get('offset',(0,0));num,den=f.get('delay',(1,10))
        parts.append((b'fcTL',struct.pack('>IIIIIHHBB',seq,fw,fh,x,y,num,den,f.get('dispose',0),f.get('blend',0))));seq+=1
        compressed=data(fw,fh,f['rgba'])
        if i==0 and poster is None:parts.append((b'IDAT',compressed))
        else:
            # Split compressed data to exercise monotonically numbered multiple fdAT chunks.
            for c in [compressed[:len(compressed)//2],compressed[len(compressed)//2:]]:
                parts.append((b'fdAT',struct.pack('>I',seq)+c));seq+=1
    parts.append((b'IEND',b''))
    return b'\x89PNG\r\n\x1a\n'+b''.join(chunk(k,p) for k,p in parts)


def reference(w,h,frames,linear=True):
    grid=[[0,0,0,0] for _ in range(w*h)];result=[]
    light=lambda b:(b/255)/12.92 if b/255<=0.04045 else ((b/255+0.055)/1.055)**2.4
    display=lambda v:12.92*v if v<=0.0031308 else 1.055*v**(1/2.4)-0.055
    nearest=lambda v:int(v+F(1,2))
    for f in frames:
        fw,fh=f.get('size',(w,h));ox,oy=f.get('offset',(0,0));previous=[c[:] for c in grid]
        for y in range(fh):
            for x in range(fw):
                s=list(f['rgba'][(y*fw+x)*4:(y*fw+x+1)*4]);i=(y+oy)*w+x+ox;d=grid[i]
                if not f.get('blend',0):grid[i]=s;continue
                a=F(s[3],255);b=F(d[3],255);out=a+b*(1-a)
                colors=[int(display(float((light(s[c])*a+light(d[c])*b*(1-a))/out))*255+0.5) if linear else nearest((s[c]*a+d[c]*b*(1-a))/out) for c in range(3)] if out else [0]*3
                grid[i]=colors+[nearest(out*255)]
        result.append(bytes(c for p in grid for c in p))
        if f.get('dispose',0)==1:
            for y in range(fh):
                for x in range(fw):grid[(y+oy)*w+x+ox]=[0]*4
        elif f.get('dispose',0)==2:grid=previous
    return result


def read_full(data):
    """Read the declared full-frame RGBA8 sequence output through independent PNG filters."""
    controls=[];payloads=[];sequence=0;header=None;plays=None
    for kind,payload in chunks(data):
        if kind==b'IHDR':header=payload
        elif kind==b'acTL':count,plays=struct.unpack('>II',payload)
        elif kind==b'fcTL':
            v=struct.unpack('>IIIIIHHBB',payload);assert v[0]==sequence;sequence+=1;controls.append(v[1:]);payloads.append(bytearray())
        elif kind==b'IDAT':payloads[-1].extend(payload)
        elif kind==b'fdAT':
            assert struct.unpack_from('>I',payload)[0]==sequence;sequence+=1;payloads[-1].extend(payload[4:])
    w,h=struct.unpack_from('>II',header);assert len(controls)==count
    pixels=[]
    for v,p in zip(controls,payloads):
        assert v[:4]==(w,h,0,0) and v[-2:]==(0,0)
        single=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',header)+chunk(b'IDAT',p)+chunk(b'IEND',b'')
        pixels.append(png_pixels(single)[2])
    return w,h,plays,controls,pixels
