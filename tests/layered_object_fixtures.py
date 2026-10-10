"""Original synthetic placed records; source pixels and caches deliberately differ."""
import struct
import layered_fixtures as f
import test_layered_metadata_cli as m

POLICY = dict(sampling='nearest', sharing='independent_copies')
PIXELS = bytes([201, 31, 61, 255, 20, 160, 90, 128, 11, 22, 233, 0,
                45, 70, 195, 255, 211, 199, 30, 64, 19, 155, 209, 255])


def comp(selected=-1):
    return [('compID', m.integer(selected)), ('originalCompID', m.integer(-1))]


def warp(amount=0):
    return [('warpStyle', m.enum('warpStyle', 'warpNone')), ('warpValue', m.number(amount)),
            ('warpPerspective', m.number(0)), ('warpPerspectiveOther', m.number(0)),
            ('warpRotate', m.enum('Ornt', 'Hrzn')),
            ('bounds', m.obj('classFloatRect', [(k, m.number(v)) for k, v in
                [('Top ', 0), ('Left', 0), ('Btom', 2), ('Rght', 3)]])),
            ('uOrder', m.integer(4)), ('vOrder', m.integer(4))]


def corners(matrix, size=(3, 2)):
    a,b,c,d,e,g = matrix
    return [v for x,y in [(0,0),(size[0],0),size,(0,size[1])]
            for v in [a*x+c*y+e,b*x+d*y+g]]


def placement(source='source-a', placed='placed-a', matrix=(1,0,0,1,2,1),
              size=(3,2), ppi=96, changes=None, legacy=False, version=4):
    points = corners(matrix, size)
    fields = dict(Idnt=m.txt(source), placed=m.txt(placed), PgNm=m.integer(1),
                  totalPages=m.integer(1), Crop=m.integer(1), frameCount=m.integer(1),
                  Annt=m.integer(16), Type=m.integer(2), comp=m.integer(-1))
    fields.update({k:m.obj('null', [('numerator',m.integer(0)),('denominator',m.integer(24))])
                   for k in ['frameStep','duration']})
    fields.update(Trnf=m.sequence([m.number(v) for v in points]),
                  nonAffineTransform=m.sequence([m.number(v) for v in points]),
                  warp=m.obj('warp',warp()), compInfo=m.obj('null',comp()))
    fields['Sz  '] = m.obj('Pnt ', [('Wdth',m.number(size[0])),('Hght',m.number(size[1]))])
    fields['Rslt'] = b'UntF#Rsl'+struct.pack('>d',ppi)
    fields.update(changes or {})
    result = f.tag(b'SoLE' if version==5 else b'SoLd',b'soLD'+f.U32(version)+m.versioned('null',list(fields.items())))
    if legacy:
        payload = b'plcL'+f.U32(3)+bytes([len(source)])+source.encode()+b''.join(f.U32(v) for v in [1,1,16,2])
        payload += b''.join(struct.pack('>d',v) for v in points)+f.U32(0)+m.versioned('warp',warp())
        result = f.tag(b'PlLd',payload)+result
    return result


def source(compression=0, version=1, **kwargs):
    return f.make([dict(name='Original translucent pixels',width=3,height=2,rgba=PIXELS)],
                  w=3,h=2,compression=compression,version=version,**kwargs)


def entry(data, identity='source-a', version=8, kind=b'liFD', opening=True, suffix=b''):
    payload = kind+f.U32(version)+bytes([len(identity)])+identity.encode()+f.unicode('original-source')+b'8BPBTEST'+f.U64(len(data))+bytes([opening])
    if opening:
        payload += m.versioned('null',[('compInfo',m.obj('null',comp()))])
    payload += data
    if version>=5: payload += f.unicode('original-child')
    if version>=6: payload += struct.pack('>d',0)
    if version>=7: payload += b'\0'
    if version>=8: payload += m.versioned('null',[('contentID',m.txt('original-content'))])
    return f.large_section(payload+suffix)


def global_sources(entries, version=1, tag=b'lnk2'):
    data=b''.join(entries)
    frame=f.large_section if version==2 and tag==b'lnk2' else f.section
    return b'8BIM'+tag+frame(data)+bytes(-len(data)%4)


def cache(extra=None, identity=1, **kwargs):
    result=dict(name='Editable placement',width=3,height=2,xy=(2,1),rgba=bytes([9,8,7,255])*6,
                id=identity,extra=placement() if extra is None else extra)
    result.update(kwargs)
    return result


def outer(data=None, layers=None, entries=None, version=1, **kwargs):
    data=source() if data is None else data
    return f.make([cache()] if layers is None else layers,version=version,
                  global_extra=global_sources([entry(data)] if entries is None else entries,version),**kwargs)
