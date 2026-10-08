"""Original GIF test framing and an independent dictionary/bit-string reader."""
import struct


def blocks(data):
    return b''.join(bytes([len(data[i:i+255])])+data[i:i+255] for i in range(0,len(data),255))+b'\0'


def codes(values, minimum=8):
    clear=1<<minimum;end=clear+1;next_code=end+1;width=minimum+1;previous=False;bits=[]
    for v in values:
        bits.extend((v>>i)&1 for i in range(width))
        if v==clear:next_code=end+1;width=minimum+1;previous=False
        elif v==end:pass
        else:
            if previous and next_code<4096:
                next_code+=1
                if next_code==1<<width and width<12:width+=1
            previous=True
    return bytes(sum(bits[j]<<i for i,j in enumerate(range(k,min(k+8,len(bits))))) for k in range(0,len(bits),8))


def fixture(width,height,frames,global_palette=None,repeats=None,background=0,comments=()):
    global_palette=global_palette or [(0,0,0),(220,20,40),(30,190,50),(40,80,210)]
    n=max(2,len(global_palette)).bit_length()-1
    assert 1<<n==len(global_palette)
    result=b'GIF89a'+struct.pack('<HHBBB',width,height,128+n-1,background,0)+bytes(c for p in global_palette for c in p)
    if repeats is not None:result+=b'\x21\xff\x0bNETSCAPE2.0\x03\x01'+struct.pack('<H',repeats)+b'\0'
    for comment in comments:result+=b'\x21\xfe'+blocks(comment)
    for f in frames:
        w,h=f.get('size',(width,height));x,y=f.get('offset',(0,0));alpha=f.get('alpha');disposal=f.get('disposal',1)
        result+=b'\x21\xf9\x04'+struct.pack('<BHB',disposal*4+(alpha is not None),f.get('delay',0),alpha or 0)+b'\0'
        local=f.get('palette');flag=64 if f.get('interlaced') else 0
        if local:flag|=128+(len(local).bit_length()-2)
        result+=b'\x2c'+struct.pack('<HHHHB',x,y,w,h,flag)
        if local:result+=bytes(c for p in local for c in p)
        indices=f['indices']
        if f.get('interlaced'):
            rows=[y for start,step in [(0,8),(4,8),(2,4),(1,2)] for y in range(start,h,step)]
            indices=b''.join(bytes(indices[y*w:(y+1)*w]) for y in rows)
        minimum=f.get('minimum',8)
        compressed=f.get('compressed',codes([1<<minimum,*indices,(1<<minimum)+1],minimum))
        result+=bytes([minimum])+blocks(compressed)
    return result+b'\x3b'


def decode(data):
    """Different representation from the engine: strings of bits and byte strings."""
    assert data[:6] in (b'GIF87a',b'GIF89a');w,h,flags,bg,_=struct.unpack_from('<HHBBB',data,6);at=13
    global_palette=[]
    if flags&128:
        n=2<<(flags&7);global_palette=[data[at+i*3:at+i*3+3] for i in range(n)];at+=3*n
    frames=[];controls=[];comments=[];loop=None;gce=(0,0,None);canvas=bytearray(w*h*4)
    def read_blocks():
        nonlocal at
        parts=[]
        while data[at]:
            n=data[at];at+=1;parts.append(data[at:at+n]);at+=n
        at+=1;return b''.join(parts)
    while data[at]!=59:
        marker=data[at];at+=1
        if marker==33:
            label=data[at];at+=1
            if label==249:
                assert data[at]==4 and data[at+5]==0;f,delay,alpha=struct.unpack_from('<BHB',data,at+1);at+=6;gce=((f>>2)&7,delay,alpha if f&1 else None)
            elif label==254:comments.append(read_blocks())
            elif label==255:
                n=data[at];at+=1;name=data[at:at+n];at+=n;payload=read_blocks();assert name==b'NETSCAPE2.0';loop=int.from_bytes(payload[1:],'little')
            else:raise AssertionError(label)
            continue
        assert marker==44;x,y,fw,fh,flags=struct.unpack_from('<HHHHB',data,at);at+=9;palette=global_palette
        if flags&128:
            n=2<<(flags&7);palette=[data[at+i*3:at+i*3+3] for i in range(n)];at+=n*3
        minimum=data[at];at+=1;packed=read_blocks();binary=''.join(f'{v:08b}'[::-1] for v in packed)
        clear=1<<minimum;end=clear+1;width=minimum+1;table={i:bytes([i]) for i in range(clear)};next_code=end+1;previous=b'';pos=0;indices=b''
        while True:
            code=int(binary[pos:pos+width][::-1],2);pos+=width
            if code==clear:table={i:bytes([i]) for i in range(clear)};next_code=end+1;width=minimum+1;previous=b'';continue
            if code==end:break
            current=table.get(code,previous+previous[:1]);assert current
            indices+=current
            if previous and next_code<4096:
                table[next_code]=previous+current[:1];next_code+=1
                width=min(12,max(minimum+1,next_code.bit_length()))
            previous=current
        assert len(indices)==fw*fh
        rows=range(fh) if flags&64==0 else [r for s,step in [(0,8),(4,8),(2,4),(1,2)] for r in range(s,fh,step)]
        previous=canvas[:];dispose,delay,alpha=gce
        for line,row in enumerate(rows):
            for col in range(fw):
                index=indices[line*fw+col]
                if index!=alpha:
                    i=((y+row)*w+x+col)*4;canvas[i:i+4]=palette[index]+b'\xff'
        frames.append(bytes(canvas));controls.append((dispose,delay,alpha));gce=(0,0,None)
        if dispose==2:
            for yy in range(y,y+fh):canvas[(yy*w+x)*4:(yy*w+x+fw)*4]=bytes(fw*4)
        elif dispose==3:canvas=previous
    assert at+1==len(data)
    return dict(width=w,height=h,frames=frames,controls=controls,loop=loop,comments=comments)
