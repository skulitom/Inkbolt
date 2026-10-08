"""Original BMP/TGA fixtures and independent alpha/row equations."""
import base64
import copy
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
import test_editing_cli as editing
import test_image_io_cli as image_io
from test_image_io_cli import tiff_fixture, tiff_tags


def bmp(width, height, rgba, top=False, components=3):
    rows=[]
    for y in (range(height) if top else reversed(range(height))):
        row=b''.join(bytes((rgba[4*(y*width+x)+2],rgba[4*(y*width+x)+1],rgba[4*(y*width+x)]))+(b'\x19' if components==4 else b'') for x in range(width))
        rows.append(row+b'\xa5'*((-len(row))%4))
    pixels=b''.join(rows)
    return b'BM'+struct.pack('<IHHI',54+len(pixels),0,0,54)+struct.pack('<IiiHHIIiiII',40,width,-height if top else height,1,components*8,0,len(pixels),3780,3780,0,0)+pixels


def tga(width,height,rgba,origin=2,rle=False,gray=False,alpha=True,extension=None):
    channels=(2 if alpha else 1) if gray else (4 if alpha else 3)
    kind=(11 if rle else 3) if gray else (10 if rle else 2)
    header=struct.pack('<BBBHHBHHHHBB',0,0,kind,0,0,0,0,0,width,height,channels*8,(origin<<4)|(8 if alpha else 0))
    pixels=[]
    for y in (range(height) if origin&2 else reversed(range(height))):
        for x in (reversed(range(width)) if origin&1 else range(width)):
            p=rgba[(y*width+x)*4:(y*width+x+1)*4]
            pixels.append((bytes([p[0]]) if gray else p[2::-1])+(p[3:4] if alpha else b''))
    if rle:
        # Alternate one literal and one repeated run, including cross-row packets.
        runs=[];i=0
        while i<len(pixels):
            n=1
            while i+n<len(pixels) and n<128 and pixels[i+n]==pixels[i]:n+=1
            if n>1:runs.append(bytes([127+n])+pixels[i]);i+=n
            else:
                run=pixels[i:i+min(7,len(pixels)-i)];runs.append(bytes([len(run)-1])+b''.join(run));i+=len(run)
        raw=header+b''.join(runs)
    else:raw=header+b''.join(pixels)
    if extension is not None:
        ext=bytearray(495);struct.pack_into('<H',ext,0,495);ext[-1]=extension
        return raw+ext+struct.pack('<II',len(raw),0)+b'TRUEVISION-XFILE.\0'
    return raw


def read_bmp(data):
    assert data[:2]==b'BM'
    size,_,_,offset=struct.unpack_from('<IHHI',data,2)
    header,w,h,planes,bpp,method,n,xppm,yppm,colors,important=struct.unpack_from('<IiiHHIIiiII',data,14)
    assert (size,offset,header,planes,bpp,method,colors,important)==(len(data),54,40,1,24,0,0,0)
    stride=((w*24+31)//32)*4;assert n==abs(h)*stride
    rows=[]
    for y in (reversed(range(h)) if h>0 else range(-h)):
        row=data[offset+y*stride:offset+(y+1)*stride]
        rows.append(b''.join(bytes([row[x*3+2],row[x*3+1],row[x*3],255]) for x in range(w)))
    return w,abs(h),b''.join(rows),(xppm,yppm)


def read_tga(data):
    _,map_type,kind,_,_,_,_,_,w,h,depth,descriptor=struct.unpack_from('<BBBHHBHHHHBB',data)
    assert (map_type,kind,depth,descriptor)==(0,2,32,40)
    extension,developer=struct.unpack_from('<II',data,len(data)-26)
    assert developer==0 and extension==18+w*h*4 and data[-18:]==b'TRUEVISION-XFILE.\0'
    assert struct.unpack_from('<H',data,extension)[0]==495 and data[extension+494]==3
    return w,h,b''.join(bytes([data[i+2],data[i+1],data[i],data[i+3]]) for i in range(18,extension,4))


class LegacyImageTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    document=image_io.ImageInterchangeTests.document
    exported=image_io.ImageInterchangeTests.exported
    imported=image_io.ImageInterchangeTests.imported

    def test_bmp_rows_padding_orientation_unused_byte_and_exact_identity(self):
        with tempfile.TemporaryDirectory() as root:
            for w in (1,2,3,4,7):
                _,p=self.document(w,5,opaque=True)
                for top in (False,True):
                    for components in (3,4):
                        r,pixels=self.imported(root,bmp(w,5,p,top,components))
                        self.assertEqual(pixels,p);self.assertEqual(r['source_format'],'bmp')
                        self.assertEqual((r['asset']['width'],r['asset']['height']),(w,5))

    def test_tga_all_origins_rle_gray_alpha_and_source_hidden_rgb(self):
        with tempfile.TemporaryDirectory() as root:
            for gray in (False,True):
                for alpha in (False,True):
                    p=b''.join(bytes([40,40,40,0 if alpha else 255]) for _ in range(17))
                    p+=b''.join(bytes([i*7]*3+[i*11 if alpha else 255]) for i in range(18))
                    for origin in range(4):
                        for rle in (False,True):
                            r,pixels=self.imported(root,tga(7,5,p,origin,rle,gray,alpha))
                            self.assertEqual(pixels,p);self.assertEqual(r['source_format'],'tga')

    def test_tga_version_two_alpha_types_and_premultiplied_reconstruction(self):
        p=bytes([0,0,0,0, 10,20,30,64, 42,80,127,128, 220,90,50,255])
        with tempfile.TemporaryDirectory() as root:
            for typ in range(5):
                actual=self.imported(root,tga(4,1,p,extension=typ))[1]
                expected=bytearray(p)
                for i in range(0,len(p),4):
                    if typ<2:expected[i+3]=255
                    if typ==4:
                        a=p[i+3]
                        expected[i:i+3]=bytes((c*255+a//2)//a if a else 0 for c in p[i:i+3])
                self.assertEqual(actual,expected)
            bad=tga(1,1,bytes([100,0,0,20]),extension=4)
            self.assertEqual(self.imported(root,bad,1)['code'],'INVALID_IMAGE')

    def test_tga_undeclared_alpha_is_opaque_and_id_field_is_bounded(self):
        data=bytearray(tga(2,1,bytes([10,20,30,0,40,50,60,128])))
        data[17]=32
        with tempfile.TemporaryDirectory() as root:
            expected=bytes([10,20,30,255,40,50,60,255])
            self.assertEqual(self.imported(root,data)[1],expected)
            data[0]=7;data[18:18]=b'fixture'
            self.assertEqual(self.imported(root,data)[1],expected)

    def test_original_exports_independent_pixels_matte_density_and_no_source_changes(self):
        d,_=self.document();d['resolution_ppi']=143.12345;saved=copy.deepcopy(d)
        with tempfile.TemporaryDirectory() as root:
            for scale in (1,2,4):
                png=self.exported(d,'png',scale=scale);w,h,expected,_=editing.png_pixels(base64.b64decode(png['data']))
                a=self.exported(d,'tga',scale=scale);data=base64.b64decode(a['data'])
                self.assertEqual(read_tga(data),(w,h,expected));self.assertEqual(a['media_type'],'image/x-tga')
                self.assertEqual(self.imported(root,data)[1],expected)
                self.assertEqual(self.exported(d,'bmp',1,scale=scale)['code'],'ALPHA_POLICY_REQUIRED')
                for matte in ([255]*3,[19,60,110]):
                    a=self.exported(d,'bmp',scale=scale,image_options=dict(matte=matte));data=base64.b64decode(a['data'])
                    out=bytes(c for i in range(0,len(expected),4) for c in [*( (expected[i+k]*expected[i+3]+matte[k]*(255-expected[i+3])+127)//255 for k in range(3)),255])
                    ppm=round(d['resolution_ppi']*scale/0.0254)
                    self.assertEqual(read_bmp(data),(w,h,out,(ppm,ppm)));self.assertEqual(self.imported(root,data)[1],out)
            self.assertEqual(d,saved)

    def test_tiff_associated_output_values_tags_and_unassociation(self):
        d,_=self.document();png=self.exported(d,'png');w,h,p,_=editing.png_pixels(base64.b64decode(png['data']))
        expected=bytes(c for i in range(0,len(p),4) for c in [*((v*p[i+3]+127)//255 for v in p[i:i+3]),p[i+3]])
        with tempfile.TemporaryDirectory() as root:
            for compression in ('none','lzw','deflate'):
                a=self.exported(d,'tiff',image_options=dict(alpha='associated',compression=compression))
                data=base64.b64decode(a['data']);tags=tiff_tags(data);self.assertEqual(tags[338],(1,))
                self.assertEqual(a['settings']['alpha'],'associated');self.assertTrue(any('Unassociation' in x for x in a['losses']))
                if compression=='none':
                    stored=b''.join(data[o:o+n] for o,n in zip(tags[273],tags[279]));self.assertEqual(stored,expected)
                actual=self.imported(root,data)[1]
                inverse=bytes(c for i in range(0,len(p),4) for c in [*((v*255+p[i+3]//2)//p[i+3] if p[i+3] else 0 for v in expected[i:i+3]),p[i+3]])
                self.assertEqual(actual,inverse)
            for endian in ('<','>'):
                for planar in (False,True):
                    data=tiff_fixture(w,h,expected,extra=[1],endian=endian,planar=planar)
                    self.assertEqual(self.imported(root,data)[1],inverse)

    def test_profile_and_metadata_boundaries_are_explicit(self):
        d,_=self.document(3,2,True)
        d['output_profile']=dict(type='builtin',name='display_p3')
        for fmt in ('bmp','tga'):self.assertEqual(self.exported(d,fmt,1)['code'],'UNSUPPORTED')
        d.pop('output_profile');d['metadata']=dict(title='Original chart',private=dict(note='local'))
        for fmt in ('bmp','tga'):
            self.assertEqual(self.exported(d,fmt,1)['code'],'UNSUPPORTED')
            a=self.exported(d,fmt,metadata_policy=dict(mode='strip'));self.assertNotIn(b'Original chart',base64.b64decode(a['data']))
        # Untagged interpretation is never inferred from an extension or supplied RGB bytes.
        with tempfile.TemporaryDirectory() as root:
            data=bmp(1,1,bytes([30,60,90,255]))
            self.assertEqual(self.imported(root,data,1,policy='require_srgb')['code'],'COLOR_POLICY_REQUIRED')
            path=Path(root)/'declared.bmp';path.write_bytes(data)
            r=self.invoke(dict(command='asset.import',source_path=str(path),store_root=str(Path(root)/'converted'),color_policy='convert_srgb',input_profile=dict(type='builtin',name='linear_srgb')))
            raw=(Path(root)/'converted'/(r['asset']['sha256']+'.rgba8')).read_bytes()[16:]
            for c,v in zip([30,60,90],raw[:3]):
                x=c/255;expected=round(255*(12.92*x if x<=.0031308 else 1.055*x**(1/2.4)-.055));self.assertLessEqual(abs(v-expected),1)
            self.assertEqual(path.read_bytes(),data)

    def test_malformed_lengths_offsets_dimensions_packets_and_headers_fail_before_storage(self):
        original=bytes([10,20,30,255])*6;cases=[]
        b=bmp(3,2,original);t=tga(3,2,original,extension=3)
        for src in (b,t):cases.extend([src[:i] for i in (0,1,2,10,17,len(src)-1)]+[src+b'x'])
        for offset,fmt,value in [(2,'I',999),(10,'I',40),(18,'i',-1),(22,'i',-2147483648),(26,'H',0),(30,'I',1),(34,'I',999),(14,'I',124)]:
            q=bytearray(b);struct.pack_into('<'+fmt,q,offset,value);cases.append(q)
        for offset,value in [(1,1),(2,1),(16,15),(17,0xc8)]:q=bytearray(t);q[offset]=value;cases.append(q)
        q=bytearray(t);struct.pack_into('<I',q,len(q)-26,1);cases.append(q)
        q=bytearray(t);struct.pack_into('<I',q,len(q)-22,18);cases.append(q)
        q=bytearray(tga(3,2,original,rle=True));q[18]=255;cases.append(q)
        with tempfile.TemporaryDirectory() as root:
            for i,data in enumerate(cases):
                source=Path(root)/f'source{i}.bin';source.write_bytes(data);store=Path(root)/f'store{i}'
                r=self.invoke(dict(command='asset.import',source_path=str(source),store_root=str(store),color_policy='assume_srgb'),1)
                self.assertIn(r['code'],('INVALID_IMAGE','UNSUPPORTED','RESOURCE_LIMIT'));self.assertFalse(store.exists());self.assertEqual(source.read_bytes(),data)
            self.assertEqual(self.imported(root,b)[1],original)

    def test_strict_options_and_create_only_publication(self):
        d,_=self.document(7,5,True)
        for fmt,option in [('bmp',dict(quality=90)),('tga',dict(matte=[0,0,0])),('jpeg',dict(alpha='associated')),('tiff',dict(alpha='bad'))]:
            self.assertEqual(self.exported(d,fmt,1,image_options=option)['code'],'INVALID_REQUEST')
        self.assertEqual(self.exported(d,'tiff',1,image_options=dict(depth='u16',alpha='associated'))['code'],'UNSUPPORTED')
        with tempfile.TemporaryDirectory() as root:
            for fmt in ('bmp','tga'):
                output=dict(output_root=root,file_name='chart.'+fmt,format=fmt)
                req=dict(command='document.publish',document=d,output=output)
                self.invoke(req);path=Path(root)/output['file_name'];data=path.read_bytes()
                self.invoke(req,1);self.assertEqual(path.read_bytes(),data)
                self.assertEqual(self.imported(root,data)[1],read_bmp(data)[2] if fmt=='bmp' else read_tga(data)[2])

    def test_board_ranges_bleed_quality_and_atomic_alpha_failure(self):
        import test_boards_cli as boards
        d=boards.BoardCliTests().fixture();saved=copy.deepcopy(d)
        quality=dict(antialias='supersample2',averaging_space='linear_srgb')
        png=self.invoke(dict(command='artboard.export',document=d,format='png',include_bleed=True,scale=2,render_options=quality))
        for fmt in ('tga','bmp'):
            options=dict(image_options=dict(matte=[255]*3)) if fmt=='bmp' else {}
            result=self.invoke(dict(command='artboard.export',document=d,format=fmt,include_bleed=True,scale=2,render_options=quality,**options))
            for a,b in zip(result['artifacts'],png['artifacts']):
                w,h,p,_=editing.png_pixels(base64.b64decode(b['artifact']['data']));data=base64.b64decode(a['artifact']['data'])
                if fmt=='bmp':p=bytes(c for i in range(0,len(p),4) for c in [*((v*p[i+3]+255*(255-p[i+3])+127)//255 for v in p[i:i+3]),255])
                self.assertEqual((read_bmp(data) if fmt=='bmp' else read_tga(data))[:3],(w,h,p));self.assertEqual(a['source_bounds'],b['source_bounds'])
            selected=self.invoke(dict(command='artboard.export',document=d,format=fmt,selection=dict(type='range',start=1,end=2),**options))
            self.assertEqual([a['id'] for a in selected['artifacts']],['tall'])
        e=self.invoke(dict(command='artboard.export',document=d,format='bmp'),1)
        self.assertEqual(e['code'],'ALPHA_POLICY_REQUIRED');self.assertNotIn('artifacts',e);self.assertEqual(d,saved)

    def test_tiff_alpha_profile_metadata_options_compose_in_destination_space(self):
        import test_metadata_cli as metadata
        d,_=self.document(7,5);d['metadata']=dict(title='Original alpha chart',private={'note':'not-for-export'})
        for profiled in (False,True):
            if profiled:d['output_profile']=dict(type='builtin',name='display_p3')
            for mode in ('public','strip'):
                options=dict(compression='none');policy=dict(mode=mode)
                straight=self.exported(d,'tiff',image_options=options,metadata_policy=policy);s=base64.b64decode(straight['data']);st=tiff_tags(s)
                rgba=b''.join(s[o:o+n] for o,n in zip(st[273],st[279]))
                associated=self.exported(d,'tiff',image_options=dict(options,alpha='associated'),metadata_policy=policy);a=base64.b64decode(associated['data']);at=tiff_tags(a)
                stored=b''.join(a[o:o+n] for o,n in zip(at[273],at[279]))
                expected=bytes(c for i in range(0,len(rgba),4) for c in [*((v*rgba[i+3]+127)//255 for v in rgba[i:i+3]),rgba[i+3]])
                self.assertEqual(stored,expected);self.assertEqual(at.get(34675),st.get(34675));self.assertEqual(34675 in at,profiled)
                self.assertEqual(metadata.carrier(a,'tiff'),metadata.carrier(s,'tiff'));self.assertNotIn(b'not-for-export',a)


if __name__=='__main__':unittest.main()
