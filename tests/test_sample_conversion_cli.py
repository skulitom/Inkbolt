"""Original byte-order fixtures and independent rational/decimal conversion checks."""
import base64
import copy
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib
import test_editing_cli as editing
import test_samples_cli as samples
from test_images_cli import chunk
from test_mcp import Client


def values(d):
    g=d['items'][0]['content']['grid'];raw=bytes.fromhex(g['data_hex']);size={'u8':1,'u16':2,'f32':4}[g['depth']]
    return list(struct.unpack('<'+{'u8':'B','u16':'H','f32':'f'}[g['depth']]*(len(raw)//size),raw))


def tiff(w,h,components,depth='u16',n=4,endian='<',planar=False,compression=1,photo=None,extra=None,tags=None,tile=None,strip_rows=None):
    """Minimal original classic-TIFF fixture writer; data supplied as native numbers."""
    fmt={'u8':'B','u16':'H','f32':'f'}[depth];bits={'u8':8,'u16':16,'f32':32}[depth]
    p=lambda f,*v:struct.pack(endian+f,*v)
    planes=[components[c::n] for c in range(n)] if planar else [components]
    if tile:
        nc=1 if planar else n;tw,th=tile
        planes=[[plane[(y*w+x)*nc+c] if x<w and y<h else 0 for y in range(y0,y0+th) for x in range(x0,x0+tw) for c in range(nc)] for plane in planes for y0 in range(0,h,th) for x0 in range(0,w,tw)]
    elif strip_rows:
        nc=1 if planar else n
        planes=[plane[y*w*nc:min(y+strip_rows,h)*w*nc] for plane in planes for y in range(0,h,strip_rows)]
    raw=[p(fmt*len(a),*a) for a in planes]
    if compression in (8,32946):raw=[zlib.compress(a) for a in raw]
    if compression==32773:
        # Original PackBits literal packets, independent of the engine encoder.
        raw=[b''.join(bytes([len(a[i:i+128])-1])+a[i:i+128] for i in range(0,len(a),128)) for a in raw]
    if compression==5:
        def lzw(data):
            # Original literal/clear code stream, plus a repeated-code fixture.
            if len(data)==256 and len(set(data))==1:codes=[256,data[0]]+list(range(258,279))+[259,257]
            else:codes=[c for v in data for c in [256,v]]+[257]
            bits=''.join(format(c,'09b') for c in codes);bits+='0'*(-len(bits)%8)
            return bytes(int(bits[i:i+8],2) for i in range(0,len(bits),8))
        raw=[lzw(a) for a in raw]
    entries={256:(4,[w]),257:(4,[h]),258:(3,[bits]*n),259:(3,[compression]),262:(3,[1 if n<3 else 2] if photo is None else [photo]),273:(4,[0]*len(raw)),277:(3,[n]),278:(4,[strip_rows or h]),279:(4,[len(a) for a in raw]),284:(3,[2 if planar else 1]),339:(3,[3 if depth=='f32' else 1]*n)}
    if n in [2,4]:entries[338]=(3,[2] if extra is None else extra)
    if tile:
        for tag in [273,278,279]:del entries[tag]
        entries.update({322:(4,[tile[0]]),323:(4,[tile[1]]),324:(4,[0]*len(raw)),325:(4,[len(a) for a in raw])})
    if tags:entries.update(tags)
    def header():
        tail=bytearray();rows=[];start=8+2+len(entries)*12+4
        for tag,(kind,vs) in sorted(entries.items()):
            data=p({1:'B',2:'B',3:'H',4:'I'}[kind]*len(vs),*vs)
            if len(data)>4:
                at=p('I',start+len(tail));tail.extend(data);tail.extend(bytes(len(tail)%2))
            else:at=data.ljust(4,b'\0')
            rows.append(p('HHI',tag,kind,len(vs))+at)
        return (b'II' if endian=='<' else b'MM')+p('HIH',42,8,len(entries))+b''.join(rows)+p('I',0)+tail
    at=len(header());offsets=[]
    for a in raw:offsets.append(at);at+=len(a)
    entries[324 if tile else 273]=(4,offsets)
    return header()+b''.join(raw)


def png(w,h,components,depth=16,n=4,tagged=True,extras=(),interlaced=False):
    fmt='H' if depth==16 else 'B';color={1:0,2:4,3:2,4:6}[n]
    rows=[]
    passes=[(0,0,1,1)] if not interlaced else [(0,0,8,8),(4,0,8,8),(0,4,4,8),(2,0,4,4),(0,2,2,4),(1,0,2,2),(0,1,1,2)]
    for x0,y0,dx,dy in passes:
        if x0>=w or y0>=h:continue
        for y in range(y0,h,dy):
            row=[c for x in range(x0,w,dx) for c in components[(y*w+x)*n:(y*w+x+1)*n]]
            rows.append(b'\0'+struct.pack('>'+fmt*len(row),*row))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,depth,color,0,0,int(interlaced)))+(chunk(b'sRGB',b'\0') if tagged else b'')+b''.join(chunk(k,v) for k,v in extras)+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')


class SampleConversionTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    document=samples.SampleTests.document
    def convert(self,d,depth='u16',channels='rgba',expected=0,**kw):
        return self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='sample_convert',id=d['items'][0]['id'],conversion=dict(depth=depth,channels=channels,**kw))]),expected)
    def imported(self,data,expected=0,policy='assume_srgb',**kw):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'original.bin';p.write_bytes(data)
            r=self.invoke(dict(command='sample.import',source_path=str(p),id='imported',color_policy=policy,**kw),expected)
            self.assertEqual(p.read_bytes(),data);self.assertEqual([f.name for f in Path(root).iterdir()],['original.bin'])
            if not expected:self.assertEqual(r['source_sha256'],hashlib.sha256(data).hexdigest());self.assertFalse(r['source_changed'])
            return r

    def test_all_integer_depth_endpoints_and_byte_promotions_are_exact(self):
        original=[c for i in range(256) for c in [i,255-i,(i*37)%256,0 if i%2 else i]]
        d=self.document([samples.layer(original,'u8')]);before=copy.deepcopy(d)
        out=self.convert(d)['document'];self.assertEqual(values(out),[v*257 for v in original])
        self.assertEqual(values(self.convert(out,'u8')['document']),original);self.assertEqual(d,before)
        d['items'][0]['content']=dict(type='raster',width=256,height=1,rgba_hex=bytes(original).hex(),sampling='bilinear')
        r=self.convert(d);self.assertTrue(r['changes'][0]['details']['promoted_inline_rgba8']);self.assertEqual(values(r['document']),[v*257 for v in original]);self.assertEqual(r['document']['items'][0]['content']['grid']['sampling'],'bilinear')

    def test_float_conversion_uses_exact_binary32_values_and_preserves_hidden_color(self):
        v=[c for x in [0,2**-149,2**-24,.4999999701976776,.5,.5000000596046448,1] for c in [x,.125,.875,2**-24]]
        d=self.document([samples.layer(v,'f32')]);out=self.convert(d)['document']
        self.assertEqual(values(out),[int(F(x)*65535+F(1,2)) for x in v]);self.assertTrue(all(v==0 for v in values(out)[3::4]))
        self.assertTrue(any(v>0 for v in values(out)[::4]))
        f=self.convert(out,'f32')['document'];self.assertEqual(values(f),[struct.unpack('<f',struct.pack('<f',x/65535))[0] for x in values(out)])

    def test_encoded_gray_has_independent_integer_weight_reference(self):
        vals=[c for i in range(100) for c in [i*641,(65535-i*233),i*317,i*431]]
        d=self.document([samples.layer(vals)]);r=self.convert(d,channels='gray_alpha',gray='encoded_luma')
        expected=[c for i in range(0,len(vals),4) for c in [int(F(2126*vals[i]+7152*vals[i+1]+722*vals[i+2],10000)+F(1,2)),vals[i+3]]]
        self.assertEqual(values(r['document']),expected)
        self.assertLessEqual(r['changes'][0]['details']['maximum_quantization_error'],.5/65535+1e-15)
        tie=self.document([samples.layer([9245,43937,45073,3874])])
        self.assertEqual(values(self.convert(tie,channels='gray_alpha',gray='encoded_luma')['document']),[36644,3874])

    def test_linear_gray_matches_fifty_digit_transfer_reference_and_differs_from_encoded(self):
        vals=[c for p in [[65535,0,0,12345],[0,65535,0,0],[0,0,65535,65535],[1000,10000,50000,23456]] for c in p]
        d=self.document([samples.layer(vals)]);r=self.convert(d,channels='gray_alpha',gray='linear_luminance')['document']
        with localcontext() as ctx:
            ctx.prec=50
            def dec(v):return v/D('12.92') if v<=D('.04045') else ((v+D('.055'))/D('1.055'))**D('2.4')
            def enc(v):return v*D('12.92') if v<=D('.0031308') else D('1.055')*v**(D(1)/D('2.4'))-D('.055')
            expected=[]
            for i in range(0,len(vals),4):
                y=sum(dec(D(vals[i+c])/65535)*D(k)/10000 for c,k in enumerate([2126,7152,722]));expected.extend([int(enc(y)*65535+D('.5')),vals[i+3]])
        self.assertEqual(values(r),expected)
        self.assertNotEqual(values(self.convert(d,channels='gray_alpha',gray='encoded_luma')['document']),expected)

    def test_neutral_gray_roundtrip_and_identical_requests_preserve_source_text(self):
        v=[12345,23456,0,65535];d=self.document([samples.layer(v,channels='gray_alpha')]);d['items'][0]['content']['grid']['data_hex']=samples.packed(v,'u16').upper()
        r=self.convert(d,channels='gray_alpha');self.assertEqual(r['document']['items'],d['items']);self.assertEqual(r['changes'][0]['details']['quantized_channels'],0)
        rgba=self.convert(d)['document'];self.assertEqual(values(rgba),[12345]*3+[23456]+[0]*3+[65535]);self.assertEqual(values(self.convert(rgba,channels='gray_alpha')['document']),v)

    def test_gray_policy_locks_and_atomic_failures_are_explicit(self):
        d=self.document([samples.layer([1,2,3,65535])]);source=copy.deepcopy(d)
        self.assertEqual(self.convert(d,channels='gray_alpha',expected=1)['code'],'GRAYSCALE_CONVERSION_REQUIRED')
        self.assertEqual(self.convert(d,gray='encoded_luma',expected=1)['code'],'INVALID_OPERATION')
        locked=copy.deepcopy(d);locked['items'][0]['locked']=True;self.assertIn('LOCK',self.convert(locked,expected=1)['code'])
        ops=[dict(op='properties',id='source',name='pending'),dict(op='sample_convert',id='source',conversion=dict(depth='f32',channels='gray_alpha'))]
        self.assertEqual(self.invoke(dict(command='document.edit',document=d,expected_revision=0,operations=ops),1)['operation_index'],1);self.assertEqual(d,source)

    def test_png_eight_and_sixteen_bit_all_channels_are_exact_and_alpha_is_added(self):
        for depth,maximum in [(8,255),(16,65535)]:
            for n in [1,2,3,4]:
                v=[(i*37+1)%(maximum+1) for i in range(9*7*n)]
                for interlace in [False,True]:
                    r=self.imported(png(9,7,v,depth,n,interlaced=interlace),policy='require_srgb')
                    expected=[c for i in range(0,len(v),n) for c in v[i:i+n]+([maximum] if n%2 else [])]
                    self.assertEqual(values(r['document']),expected);self.assertEqual(r['document']['items'][0]['content']['grid']['depth'],'u16' if depth==16 else 'u8');self.assertEqual(r['interpretation'],'declared_srgb')

    def test_png_transparent_sixteen_bit_key_and_low_bits_expand_without_color_loss(self):
        v=[12345,12346,0,65535];r=self.imported(png(4,1,v,n=1,extras=[(b'tRNS',struct.pack('>H',12345))]))
        self.assertEqual(values(r['document']),[12345,0,12346,65535,0,65535,65535,65535])
        data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',4,1,2,0,0,0,0))+chunk(b'sRGB',b'\0')+chunk(b'IDAT',zlib.compress(b'\0\x1b'))+chunk(b'IEND',b'')
        r=self.imported(data);self.assertEqual(values(r['document']),[0,255,85,255,170,255,255,255]);self.assertEqual(r['normalization']['input_depth'],2)

    def test_tiff_all_depths_channels_byte_orders_and_planes_are_exact(self):
        for depth,maximum in [('u8',255),('u16',65535),('f32',1)]:
            for n in [1,2,3,4]:
                v=[(i*37+1)%(maximum+1) for i in range(5*3*n)] if depth!='f32' else [(i%17)/16 for i in range(5*3*n)]
                expected=[c for i in range(0,len(v),n) for c in v[i:i+n]+([maximum] if n%2 else [])]
                for endian in ['<','>']:
                    for planar in [False,True]:
                        r=self.imported(tiff(5,3,v,depth,n,endian,planar,compression=8));self.assertEqual(values(r['document']),expected);self.assertEqual(r['document']['items'][0]['content']['grid']['depth'],depth)

    def test_white_zero_grayscale_inversion_and_float_subnormal_bits(self):
        for depth,vals,maximum in [('u8',[0,1,127,255],255),('u16',[0,1,32767,65535],65535),('f32',[0,.125,.5,1],1)]:
            r=self.imported(tiff(4,1,vals,depth,1,photo=0));self.assertEqual(values(r['document']),[c for v in vals for c in [maximum-v,maximum]])
        vals=[-0.0,2**-149,.5000000596046448,1];r=self.imported(tiff(1,1,vals,'f32',4,endian='>'))
        self.assertEqual(r['document']['items'][0]['content']['grid']['data_hex'],samples.packed(vals,'f32'))

    def test_padded_lzw_tiles_decode_complete_planes_and_enforce_work_limit(self):
        for depth,maximum in [('u8',255),('u16',65535),('f32',1)]:
            for n in [1,2,3,4]:
                v=[(i%17)/16 if depth=='f32' else i*31%(maximum+1) for i in range(23*19*n)]
                if depth=='u8' and n==1:v=[0]*len(v)
                for planar in [False,True]:
                    data=tiff(23,19,v,depth,n,planar=planar,compression=5,tile=(16,16))
                    self.assertEqual(values(self.imported(data)['document']),[c for i in range(0,len(v),n) for c in v[i:i+n]+([maximum] if n%2 else [])])
        too_padded=tiff(1,1,[0],depth='u8',n=1,tile=(16,16),tags={322:(4,[2**30]),323:(4,[2**30])})
        self.assertEqual(self.imported(too_padded,expected=1)['code'],'RESOURCE_LIMIT')

    def test_import_policy_profile_orientation_sequence_and_hdr_rejections(self):
        data=png(1,1,[1,2,3,4],tagged=False)
        self.assertEqual(self.imported(data,expected=1,policy='require_srgb')['code'],'COLOR_POLICY_REQUIRED')
        self.assertEqual(self.imported(data,expected=1,policy='convert_srgb')['code'],'UNSUPPORTED')
        for tag,payload in [(b'iCCP',b'profile\0\0'+zlib.compress(b'original')),(b'eXIf',b'original'),(b'acTL',struct.pack('>II',1,0)),(b'cICP',b'\x01\x01\0\x01')]:
            self.assertEqual(self.imported(png(1,1,[1,2,3,4],extras=[(tag,payload)]),expected=1)['code'],'UNSUPPORTED')
        for tags in [{274:(3,[3])},{34675:(1,[1,2,3])},{339:(3,[2]*4)},{330:(4,[8])}]:
            self.assertEqual(self.imported(tiff(1,1,[1,2,3,4],tags=tags),expected=1)['code'],'UNSUPPORTED')
        for extra in [[0],[1]]:self.assertEqual(self.imported(tiff(1,1,[1,2,3,4],extra=extra),expected=1)['code'],'UNSUPPORTED')
        self.assertEqual(self.imported(tiff(1,1,[2,0,0,1],'f32'),expected=1)['code'],'UNSUPPORTED_SAMPLE_RANGE')
        sequence=bytearray(tiff(1,1,[1,2,3,4]));count=struct.unpack_from('<H',sequence,8)[0];second=bytes(sequence[8:14+count*12]);struct.pack_into('<I',sequence,10+count*12,len(sequence));sequence.extend(second)
        self.assertEqual(self.imported(bytes(sequence),expected=1)['code'],'UNSUPPORTED')

    def test_malformed_framing_and_invalid_document_limits_reject_without_writes(self):
        data=png(2,1,[1,2,3,65535]*2)
        for bad in [data[:-8],data+b'extra',data[:30]+bytes([data[30]^1])+data[31:],b'II*\0\xff\xff\xff\x7f']:
            self.assertEqual(self.imported(bad,expected=1)['code'],'INVALID_IMAGE')
        self.assertEqual(self.imported(data,expected=1,resolution_ppi=0)['code'],'INVALID_DOCUMENT')
        huge=tiff(256,256,[.5,0,0,1]*65536,'f32');self.assertEqual(self.imported(huge,expected=1)['code'],'RESOURCE_LIMIT')

    def test_native_export_reimport_keeps_six_sample_layouts_and_chosen_density(self):
        for depth,maximum in [('u8',255),('u16',65535),('f32',1)]:
            for channels in ['rgba','gray_alpha']:
                vals=[maximum,maximum//2 if depth!='f32' else .5,0,maximum] if channels=='rgba' else [.5 if depth=='f32' else maximum//2,maximum]
                d=self.document([samples.layer(vals,depth,channels)])
                a=self.invoke(dict(command='document.export',document=d,format='tiff',image_options=dict(depth=depth,channels=channels)))
                r=self.imported(base64.b64decode(a['data']),resolution_ppi=144)
                self.assertEqual(values(r['document']),vals);self.assertEqual(r['document']['resolution_ppi'],144)

    def test_mcp_readonly_import_and_durable_conversion_history_retry_and_publication(self):
        c=Client();self.addCleanup(c.close);c.initialize()
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'original.png';raw=png(2,1,[65535,0,0,12345,0,65535,0,65535]);source.write_bytes(raw)
            d=c.success('sample.import',source_path=str(source),id='native')['document'];self.assertEqual(source.read_bytes(),raw)
            args=dict(session_root=root,session_id='conversion');c.success('session.create',**args,request_id='create',document=d)
            action=dict(type='edit',operations=[dict(op='sample_convert',id='pixels',conversion=dict(depth='u16',channels='gray_alpha',gray='linear_luminance'))])
            edited=c.success('session.apply',**args,request_id='convert',expected_revision=0,action=action)['document']
            self.assertEqual(c.success('session.apply',**args,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'],dict(d,revision=2))
            redo=c.success('session.apply',**args,request_id='redo',expected_revision=2,action=dict(type='redo'))['document'];self.assertEqual(redo,dict(edited,revision=3))
            replay=c.success('session.apply',**args,request_id='convert',expected_revision=0,action=action);self.assertTrue(replay['replayed']);self.assertEqual(replay['current_revision'],3)
            c.success('session.publish',**args,expected_revision=3,output=dict(output_root=root,file_name='gray.tiff',format='tiff',image_options=dict(depth='u16',channels='gray_alpha')))
            self.assertEqual(values(c.success('sample.import',source_path=str(Path(root)/'gray.tiff'),id='gray',color_policy='assume_srgb')['document']),values(edited));c.success('session.verify',**args)
            self.assertEqual(source.read_bytes(),raw)


if __name__=='__main__':unittest.main()
