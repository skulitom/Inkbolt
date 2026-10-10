"""Independent public-format reader for the emitted embedded-source subset."""
import layered_fixtures as f

def text(r):return r.take(r.number('I')*2).decode('utf-16-be').rstrip('\0')
def key(r):return r.take(r.number('I') or 4).decode('ascii')
def descriptor(r):
    name=text(r);kind=key(r);fields={}
    for _ in range(r.number('I')):
        k=key(r);assert k not in fields;fields[k]=value(r)
    return dict(name=name,kind=kind,fields=fields)
def value(r):
    kind=r.take(4)
    if kind==b'Objc':return descriptor(r)
    if kind==b'doub':return r.number('d')
    if kind==b'long':return r.number('i')
    if kind==b'TEXT':return text(r)
    if kind==b'enum':return (key(r),key(r))
    if kind==b'UntF':return (r.take(4).decode('ascii'),r.number('d'))
    if kind==b'VlLs':return [value(r) for _ in range(r.number('I'))]
    raise AssertionError(kind)
def placement(raw):
    r=f.Reader(raw);assert r.take(4)==b'soLD';assert r.number('I')==4;assert r.number('I')==16
    result=descriptor(r);assert not r.left();return result['fields']
def sources(raw):
    r=f.Reader(raw);out=[]
    while r.left():
        e=r.section(True);assert e.take(4)==b'liFD';version=e.number('I');assert version==7
        identity=e.take(e.number('B')).decode('ascii');name=text(e);filetype=e.take(4);creator=e.take(4)
        size=e.number('Q');assert e.number('B')==0;data=e.take(size)
        assert text(e)=='';assert e.number('d')==0;assert e.number('B')==0
        padding=-e.at%4;assert e.left()==padding;assert e.take(padding)==bytes(padding)
        out.append(dict(id=identity,name=name,type=filetype,creator=creator,data=data))
    return out
