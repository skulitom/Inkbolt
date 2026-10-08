"""Independent bounded PDF test reader: classic xref, direct lengths, paths and forms.

This is an assertion helper for original fixtures, not a general PDF importer.
External consumer verification additionally checks these files outside the engine.
"""
import base64
import re


class Ref(int): pass
class Name(str): pass


TOKEN = re.compile(rb'\s+|%[^\r\n]*|<<|>>|\[|\]|/[^\s<>\[\]()/]+|\([^()]*\)|[^\s<>\[\]()/]+')


def parse(data):
    tokens = [v for v in TOKEN.findall(data) if not v.isspace() and not v.startswith(b'%')]
    at = 0
    def value():
        nonlocal at
        token=tokens[at];at+=1
        if token==b'<<':
            result={}
            while tokens[at]!=b'>>':
                key=value();assert isinstance(key,Name) and key not in result
                result[key]=value()
            at+=1;return result
        if token==b'[':
            result=[]
            while tokens[at]!=b']':result.append(value())
            at+=1;return result
        if token.startswith(b'/'):return Name(token[1:].decode())
        if token.startswith(b'('):return token[1:-1].decode()
        if token in (b'true',b'false'):return token==b'true'
        if token==b'null':return None
        assert re.fullmatch(rb'[+-]?(?:\d+(?:\.\d*)?|\.\d+)',token),token
        n=float(token) if b'.' in token else int(token)
        if tokens[at:at+2]==[b'0',b'R']:at+=2;return Ref(n)
        return n
    result=value();assert at==len(tokens),(tokens[at:],data)
    return result


def multiply(a,b):
    return [a[0]*b[0]+a[2]*b[1],a[1]*b[0]+a[3]*b[1],
        a[0]*b[2]+a[2]*b[3],a[1]*b[2]+a[3]*b[3],
        a[0]*b[4]+a[2]*b[5]+a[4],a[1]*b[4]+a[3]*b[5]+a[5]]


def point(m,p):return [m[0]*p[0]+m[2]*p[1]+m[4],m[1]*p[0]+m[3]*p[1]+m[5]]


class Pdf:
    def __init__(self,artifact):
        self.data=base64.b64decode(artifact['data']) if isinstance(artifact,dict) else artifact
        assert self.data.startswith((b'%PDF-1.7\n', b'%PDF-2.0\n'))
        match=re.search(rb'startxref\n(\d+)\n%%EOF\n$',self.data);assert match
        start=int(match[1]);tail=self.data[start:]
        header=re.match(rb'xref\n0 (\d+)\n',tail);assert header
        count=int(header[1]);rows=tail[header.end():header.end()+20*count]
        assert rows[:20]==b'0000000000 65535 f \n'
        trailer=tail[header.end()+20*count:];assert trailer.startswith(b'trailer\n')
        self.trailer=parse(trailer[8:trailer.index(b'\nstartxref')]);assert self.trailer['Size']==count
        offsets=[int(rows[n*20:n*20+10]) for n in range(1,count)]+[start]
        assert offsets==sorted(set(offsets))
        self.objects={};self.streams={}
        for n,(lo,hi) in enumerate(zip(offsets,offsets[1:]),1):
            chunk=self.data[lo:hi];prefix=f'{n} 0 obj\n'.encode()
            assert chunk.startswith(prefix) and chunk.endswith(b'\nendobj\n')
            body=chunk[len(prefix):-8]
            if b'\nstream\n' in body:
                head,stream=body.split(b'\nstream\n',1);obj=parse(head)
                length=obj['Length'];assert len(stream)==length+10 and stream[length:]==b'\nendstream'
                self.streams[n]=stream[:length]
            else:obj=parse(body)
            self.objects[n]=obj
        self.catalog=self.get(self.trailer['Root']);assert self.catalog['Type']=='Catalog'
        tree=self.get(self.catalog['Pages']);assert tree['Type']=='Pages'
        self.pages=[self.get(r) for r in tree['Kids']];assert len(self.pages)==tree['Count']
        for page in self.pages:assert page['Type']=='Page' and page['Parent']==self.catalog['Pages']
        def refs(v):
            if isinstance(v,Ref):assert v in self.objects
            elif isinstance(v,dict):
                for child in v.values():refs(child)
            elif isinstance(v,list):
                for child in v:refs(child)
        for obj in self.objects.values():refs(obj)

    def get(self,ref):assert isinstance(ref,Ref);return self.objects[ref]

    def paths(self,page=0):
        """Flatten invoked forms to painted paths in top-left logical coordinates."""
        p=self.pages[page];media=p['MediaBox'];height=media[3]
        result=[]
        def visit(data,resources,matrix,opacity,active):
            args=[];path=[];stack=[];color=None;alpha=1
            for token in data.split():
                if re.fullmatch(rb'[+-]?(?:\d+(?:\.\d*)?|\.\d+)',token):args.append(float(token));continue
                if token.startswith(b'/'):args.append(token[1:].decode());continue
                if token==b'q':stack.append((matrix[:],color,alpha))
                elif token==b'Q':matrix,color,alpha=stack.pop()
                elif token==b'cm':matrix=multiply(matrix,args)
                elif token==b'rg':color=args[:]
                elif token==b'gs':alpha=self.get(resources['ExtGState'][args[0]])['ca']
                elif token in (b'm',b'l',b'c'):path.append((token.decode(),[point(matrix,args[i:i+2]) for i in range(0,len(args),2)]))
                elif token==b'h':path.append(('h',[]))
                elif token==b'n':path=[]
                elif token in (b'f',b'f*'):
                    result.append(dict(path=path,color=color,alpha=opacity*alpha,rule=token.decode()));path=[]
                elif token==b'Do':
                    ref=resources['XObject'][args[0]];obj=self.get(ref)
                    if obj['Subtype']=='Form':
                        assert ref not in active
                        visit(self.streams[ref],obj['Resources'],matrix,opacity*alpha,active|{ref})
                else:assert token in (b'W',b'W*',b'sh'),token
                args=[]
            assert not args and not stack
        visit(self.streams[p['Contents']],p['Resources'],[1,0,0,1,0,0],1,set())
        for entry in result:
            for _,points in entry['path']:
                for v in points:v[1]=height-v[1]
        return result
