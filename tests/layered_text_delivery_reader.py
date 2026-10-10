"""Independent reader for original editable text delivery fixtures.

Only tests use this small byte grammar; it does not call the engine's parser.
"""
import struct
import layered_fixtures as f
import layered_delivery_reader as d
from synthetic_font import geometric_font, pack
from synthetic_unicode_font import sfnt
from synthetic_variable_font import tables


def named_font(name='InkboltDeliveryFixture-Regular', advance=600, names=None, source=None):
    source=tables(source if source is not None else geometric_font(advance, {ord(c):2 for c in '()\\'}))
    values=[name] if names is None else names
    records=b'';strings=b''
    for i,value in enumerate(values):
        raw=value.encode('utf-16-be')
        records+=pack('HHHHHH',3,1,0x409+i,6,len(raw),len(strings));strings+=raw
    source[b'name']=pack('HHH',0,len(values),6+12*len(values))+records+strings
    return sfnt(source)


def data(raw):
    i=0
    def space():
        nonlocal i
        while i<len(raw) and raw[i] in b' \t\r\n':i+=1
    def value():
        nonlocal i
        space()
        if raw[i:i+2]==b'<<':
            i+=2;out={}
            while True:
                space()
                if raw[i:i+2]==b'>>':i+=2;return out
                assert raw[i]==47;i+=1;start=i
                while raw[i] not in b' \t\r\n':i+=1
                key=raw[start:i].decode('ascii');assert key not in out;out[key]=value()
        if raw[i]==91:
            i+=1;out=[]
            while True:
                space()
                if raw[i]==93:i+=1;return out
                out.append(value())
        if raw[i]==40:
            i+=1;out=bytearray()
            while raw[i]!=41:
                if raw[i]==92:i+=1;assert raw[i] in b'()\\'
                out.append(raw[i]);i+=1
            i+=1;assert out[:2]==b'\xfe\xff';return out[2:].decode('utf-16-be')
        start=i
        while i<len(raw) and raw[i] not in b' \t\r\n<>[]':i+=1
        token=raw[start:i];assert token
        if token in [b'true',b'false']:return token==b'true'
        return float(token) if b'.' in token else int(token)
    out=value();space();assert i==len(raw);return out


def record(raw):
    r=f.Reader(raw);assert r.number('H')==1
    matrix=struct.unpack('>6d',r.take(48));assert r.number('H')==50 and r.number('I')==16
    desc=d.descriptor(r);assert desc['kind']=='TxLr'
    assert r.number('H')==1 and r.number('I')==16
    warp=d.descriptor(r);assert warp['kind']=='warp'
    assert r.take(16)==bytes(16) and not r.left()
    fields=desc['fields'];return dict(matrix=list(matrix),fields=fields,data=data(fields['EngineData']),warp=warp['fields'])
