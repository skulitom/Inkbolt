"""Original image interchange fixtures; independent TIFF framing and exact pixel checks."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib
import test_editing_cli as editing
from test_images_cli import canonical, png
import test_boards_cli as boards
from test_mcp import Client


def tiff_fixture(width, height, pixels, channels=4, endian='<', planar=False, photo=None, compression=1, extra=None, bits=8, tags=None):
    """Original classic TIFF with one strip per plane; no codec implementation reused."""
    p=lambda fmt,*v:struct.pack(endian+fmt,*v)
    photo=(1 if channels<3 else 2) if photo is None else photo
    planes=[pixels[c::channels] for c in range(channels)] if planar else [pixels]
    if compression in (8,32946):planes=[zlib.compress(v) for v in planes]
    if compression==32773:
        planes=[b''.join(bytes([len(v[i:i+128])-1])+v[i:i+128] for i in range(0,len(v),128)) for v in planes]
    values={256:(4,[width]),257:(4,[height]),258:(3,[bits]*channels),259:(3,[compression]),262:(3,[photo]),273:(4,[0]*len(planes)),277:(3,[channels]),278:(4,[height]),279:(4,list(map(len,planes))),284:(3,[2 if planar else 1])}
    if channels in (2,4):values[338]=(3,[2] if extra is None else extra)
    if tags:values.update(tags)
    def encode(values):
        start=8+2+len(values)*12+4;tail=bytearray();rows=[]
        for tag,(kind,vs) in sorted(values.items()):
            raw=p({1:'B',3:'H',4:'I'}[kind]*len(vs),*vs)
            if len(raw)>4:
                address=p('I',start+len(tail));tail.extend(raw)
                if len(tail)%2:tail.append(0)
            else:address=raw.ljust(4,b'\0')
            rows.append(p('HHI',tag,kind,len(vs))+address)
        return (b'II' if endian=='<' else b'MM')+p('HIH',42,8,len(values))+b''.join(rows)+p('I',0)+tail
    header=encode(values);offset=len(header);offsets=[]
    for plane in planes:offsets.append(offset);offset+=len(plane)
    values[273]=(4,offsets)
    return encode(values)+b''.join(planes)


def tiff_tags(data):
    endian='<' if data[:2]==b'II' else '>'
    u=lambda fmt,at:struct.unpack_from(endian+fmt,data,at)
    assert u('H',2)==(42,)
    at=u('I',4)[0];count=u('H',at)[0];result={}
    for i in range(count):
        entry=at+2+12*i;tag,kind,n=u('HHI',entry);fmt,size={1:('B',1),2:('B',1),3:('H',2),4:('I',4),5:('I',8)}[kind]
        offset=entry+8 if n*size<=4 else u('I',entry+8)[0]
        result[tag]=u(fmt*(n*2 if kind==5 else n),offset)
    return result


def tiff_uncompressed(data):
    tags=tiff_tags(data);assert tags[259]==(1,) and tags[258]==(8,8,8,8) and tags[338]==(2,)
    raw=b''.join(data[o:o+n] for o,n in zip(tags[273],tags[279]))
    return tags[256][0],tags[257][0],raw,tags


def jpeg_segments(data):
    assert data[:2]==b'\xff\xd8';at=2;segments=[]
    while at<len(data):
        assert data[at]==255;marker=data[at+1];n=int.from_bytes(data[at+2:at+4],'big');payload=data[at+4:at+2+n]
        segments.append((marker,payload));at+=2+n
        if marker==0xda:break
    assert data[-2:]==b'\xff\xd9'
    return segments


class ImageInterchangeTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def document(self,width=17,height=11,opaque=False):
        d=self.invoke(dict(command='document.create',id='image-fixture',kind='raster',width=width,height=height))
        pixels=bytes(c for y in range(height) for x in range(width) for c in (30+x*5%150,40+y*7%150,60+(x+y)*3%150,255 if opaque else [0,64,128,192,255][(x+y)%5]))
        d['items']=[dict(id='pixels',content=dict(type='raster',width=width,height=height,rgba_hex=pixels.hex()))]
        return d,pixels
    def exported(self,d,format,expected=0,**options):
        return self.invoke(dict(command='document.export',document=d,format=format,**options),expected)
    def imported(self,root,data,expected=0,policy='assume_srgb'):
        source=Path(root)/'original.bin';source.write_bytes(data);store=Path(root)/'assets'
        result=self.invoke(dict(command='asset.import',source_path=str(source),store_root=str(store),color_policy=policy),expected)
        self.assertEqual(source.read_bytes(),data)
        if not expected:
            asset=result['asset'];raw=(store/(asset['sha256']+'.rgba8')).read_bytes()
            self.assertEqual(asset['sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual(asset['provenance']['source_sha256'],hashlib.sha256(data).hexdigest())
            return result,raw[16:]
        return result

    def test_tiff_original_endian_planar_alpha_gray_and_compression_samples(self):
        with tempfile.TemporaryDirectory() as root:
            for channels in (1,2,3,4):
                pixels=bytes((i*37+19)%256 for i in range(21*channels))
                expected=bytes(v for i in range(21) for v in ([pixels[i]]*3+[255] if channels==1 else [pixels[2*i]]*3+[pixels[2*i+1]] if channels==2 else list(pixels[3*i:3*i+3])+[255] if channels==3 else pixels[4*i:4*i+4]))
                for endian in ('<','>'):
                    for planar in (False,True):
                        for compression in (1,8,32946,32773):
                            with self.subTest(channels=channels,endian=endian,planar=planar,compression=compression):
                                result,raw=self.imported(root,tiff_fixture(7,3,pixels,channels,endian,planar,compression=compression))
                                self.assertEqual(raw,expected);self.assertEqual(result['source_format'],'tiff')
                                self.assertEqual(result['asset']['provenance']['interpretation'],'assumed_srgb')

    def test_tiff_white_is_zero_gray_normalizes_and_alpha_semantics_fail_explicitly(self):
        with tempfile.TemporaryDirectory() as root:
            for channels in (1,2):
                pixels=bytes([0,64,128,255] if channels==1 else [0,19,64,53,128,99,255,201])
                expected=bytes(v for i in range(4) for v in [255-pixels[i*channels]]*3+[pixels[i*channels+1] if channels==2 else 255])
                for planar in (False,True):
                    data=tiff_fixture(4,1,pixels,channels,planar=planar,photo=0)
                    if channels==1:self.assertEqual(self.imported(root,data)[1],expected)
                    else:self.assertEqual(self.imported(root,data,1)['code'],'UNSUPPORTED')

    def test_export_tiff_tags_density_exact_pixels_and_roundtrips_all_compressions(self):
        d,_=self.document();d['resolution_ppi']=143.12345;before=copy.deepcopy(d)
        with tempfile.TemporaryDirectory() as root:
            for scale in (1,2):
                png_art=self.exported(d,'png',scale=scale);w,h,expected,_=editing.png_pixels(base64.b64decode(png_art['data']))
                for compression,tag in [('none',1),('lzw',5),('deflate',8)]:
                    artifact=self.exported(d,'tiff',scale=scale,image_options=dict(compression=compression));data=base64.b64decode(artifact['data']);tags=tiff_tags(data)
                    self.assertEqual(tags[259],(tag,));self.assertEqual(tags[338],(2,));self.assertEqual(tags[274],(1,));self.assertEqual(tags[296],(2,))
                    self.assertAlmostEqual(tags[282][0]/tags[282][1],round(d['resolution_ppi']*scale,3),places=3)
                    self.assertEqual(artifact['media_type'],'image/tiff');self.assertEqual(artifact['settings']['compression'],compression)
                    if compression=='none':self.assertEqual(tiff_uncompressed(data)[:3],(w,h,expected))
                    result,raw=self.imported(root,data);self.assertEqual(raw,expected);self.assertEqual((result['asset']['width'],result['asset']['height']),(w,h))
                    # Export->import normalizes transparent RGB exactly like the existing render contract.
                    self.assertEqual(hashlib.sha256(canonical(w,h,expected)).hexdigest(),result['asset']['sha256'])
            self.assertEqual(d,before)

    def test_png_tiff_and_raw_import_share_exact_canonical_identity(self):
        d,pixels=self.document(3,2)
        with tempfile.TemporaryDirectory() as root:
            a,raw=self.imported(root,png(3,2,pixels));self.assertEqual(raw,pixels)
            b,raw=self.imported(root,tiff_fixture(3,2,pixels));self.assertEqual(raw,pixels)
            self.assertEqual(a['asset']['sha256'],b['asset']['sha256']);self.assertFalse(b['created'])
            self.assertEqual(len(list((Path(root)/'assets').iterdir())),1)
            self.assertNotEqual(a['asset']['provenance']['source_sha256'],b['asset']['provenance']['source_sha256'])

    def test_jpeg_alpha_requires_matte_and_roundtrip_is_declared_lossy(self):
        d,_=self.document();before=copy.deepcopy(d)
        self.assertEqual(self.exported(d,'jpeg',1)['code'],'ALPHA_POLICY_REQUIRED')
        with tempfile.TemporaryDirectory() as root:
            for matte in ([255]*3,[20,50,80]):
                for chroma in ('full','half'):
                    artifact=self.exported(d,'jpeg',image_options=dict(quality=100,chroma=chroma,matte=matte));data=base64.b64decode(artifact['data'])
                    self.assertEqual(artifact['media_type'],'image/jpeg');self.assertEqual(artifact['settings']['matte'],matte)
                    self.assertTrue(any('lossy' in text for text in artifact['losses']))
                    markers=dict(jpeg_segments(data));frame=markers[0xc0];self.assertEqual(struct.unpack('>BHHB',frame[:6]),(8,11,17,3));self.assertEqual(frame[7],0x11 if chroma=='full' else 0x22)
                    result,raw=self.imported(root,data);self.assertEqual(result['source_format'],'jpeg');self.assertEqual(raw[3::4],bytes([255])*187)
            self.assertEqual(d,before)

    def test_opaque_jpeg_default_quality_scale_density_and_grayscale_framing(self):
        d,_=self.document(16,16,True);d['resolution_ppi']=123.4
        artifact=self.exported(d,'jpeg',scale=2);markers=dict(jpeg_segments(base64.b64decode(artifact['data'])))
        self.assertEqual(artifact['settings'],dict(quality=90,chroma='full',matte=None,resolution_ppi=247.0))
        self.assertEqual(markers[0xe0][:5],b'JFIF\0');self.assertEqual(markers[0xe0][7],1);self.assertEqual(struct.unpack('>HH',markers[0xe0][8:12]),(247,247))

    def test_jpeg_original_smooth_chart_obeys_declared_fixture_error_bounds(self):
        width,height=96,64;d,_=self.document(width,height,True)
        pixels=bytes(v for y in range(height) for x in range(width) for v in (30+x,40+y*2,50+(x+y)//2,255));d['items'][0]['content']['rgba_hex']=pixels.hex()
        with tempfile.TemporaryDirectory() as root:
            for chroma in ('full','half'):
                for quality,bound in [(100,4),(90,6),(75,9)]:
                    data=base64.b64decode(self.exported(d,'jpeg',image_options=dict(quality=quality,chroma=chroma))['data'])
                    _,raw=self.imported(root,data);self.assertLessEqual(max(abs(a-b) for a,b in zip(raw,pixels)),bound)

    def test_image_artboard_batches_preflight_all_pixels_and_scale_limits(self):
        d,_=self.document(1,1,True);d['items']=[dict(id='b'+str(i),content=dict(type='frame',frame=dict(role='artboard',width=1024,height=1024))) for i in range(5)]
        for format in ('jpeg','tiff'):
            r=self.invoke(dict(command='artboard.export',document=d,format=format),1);self.assertEqual(r['code'],'RESOURCE_LIMIT');self.assertNotIn('artifacts',r)
        # Per-output scale/dimension rules are shared with the existing rasterizer.
        d,_=self.document(1,1,True)
        for format in ('jpeg','tiff'):
            for scale in (0,5):self.assertEqual(self.exported(d,format,1,scale=scale)['code'],'INVALID_REQUEST')

    def test_strict_format_specific_options_and_unknown_fields_fail(self):
        d,_=self.document(2,2,True)
        cases=[('jpeg',dict(quality=0)),('jpeg',dict(quality=101)),('jpeg',dict(quality=1.5)),('jpeg',dict(chroma='quarter')),('jpeg',dict(matte=[0,0])),('jpeg',dict(compression='lzw')),('tiff',dict(quality=90)),('tiff',dict(matte=[0,0,0])),('tiff',dict(chroma='full')),('tiff',dict(compression='lossy')),('png',{}),('snapshot',{}),('svg',{}),('jpeg',dict(unexpected=True))]
        for format,options in cases:
            with self.subTest(format=format,options=options):self.assertEqual(self.exported(d,format,1,image_options=options)['code'],'INVALID_REQUEST')

    def test_jpeg_truncation_trailing_marker_metadata_and_limits_fail_before_storage(self):
        d,_=self.document(4,4,True);data=base64.b64decode(self.exported(d,'jpeg')['data'])
        cases=[data[:-2],data+b'trailing',data[:25],b'\xff\xd8\xff\xd9',data[:2]+b'\xff\xe0\x00\x01'+data[2:]]
        for marker in (0xe1,0xe2,0xed,0xee):
            cases.extend([data[:2]+bytes([255,marker,0,3,1])+data[2:],data[:-2]+bytes([255,marker,0,3,1])+data[-2:]])
        with tempfile.TemporaryDirectory() as root:
            for bad in cases:
                self.assertIn(self.imported(root,bad,1)['code'],['INVALID_IMAGE','UNSUPPORTED']);self.assertFalse((Path(root)/'assets').exists())
            huge=bytearray(data);at=huge.index(b'\xff\xc0');huge[at+5:at+9]=struct.pack('>HH',65535,65535)
            self.assertEqual(self.imported(root,huge,1)['code'],'RESOURCE_LIMIT');self.assertFalse((Path(root)/'assets').exists())

    def test_tiff_metadata_alpha_pages_depth_limits_and_corruption_fail_before_storage(self):
        pixels=bytes([20,40,60,128])*4;plain=tiff_fixture(2,2,pixels)
        cases=[(tiff_fixture(2,2,bytes([255,0,0,20])*4,extra=[1]),'INVALID_IMAGE'),(tiff_fixture(2,2,pixels,extra=[0]),'UNSUPPORTED'),(tiff_fixture(2,2,pixels,tags={274:(3,[6])}),'UNSUPPORTED'),(tiff_fixture(2,2,pixels,bits=16),'UNSUPPORTED'),(tiff_fixture(2,2,pixels,compression=7),'UNSUPPORTED'),(tiff_fixture(32769,1,b'1234'),'RESOURCE_LIMIT'),(plain[:-3],'INVALID_IMAGE'),(b'IIinvalid','INVALID_IMAGE')]
        for tag in (301,318,319,330,34665,34675,50706):cases.append((tiff_fixture(2,2,pixels,tags={tag:(1,[1,2,3,4,5])}),'UNSUPPORTED'))
        cases.append((tiff_fixture(2,2,pixels,tags={339:(3,[2,2,2,2])}),'UNSUPPORTED'))
        multipage=bytearray(plain);count=struct.unpack_from('<H',multipage,8)[0];struct.pack_into('<I',multipage,10+count*12,len(plain));multipage.extend(plain[8:]);cases.append((multipage,'UNSUPPORTED'))
        with tempfile.TemporaryDirectory() as root:
            for bad,code in cases:
                with self.subTest(code=code,sha=hashlib.sha256(bad).hexdigest()):
                    self.assertEqual(self.imported(root,bad,1)['code'],code);self.assertFalse((Path(root)/'assets').exists())

    def test_untagged_color_policy_is_required_and_existing_store_is_never_replaced(self):
        d,_=self.document(2,2,True)
        with tempfile.TemporaryDirectory() as root:
            for format in ('jpeg','tiff'):
                data=base64.b64decode(self.exported(d,format)['data']);self.assertEqual(self.imported(root,data,1,policy='require_srgb')['code'],'COLOR_POLICY_REQUIRED')
                result,_=self.imported(root,data);path=Path(root)/'assets'/(result['asset']['sha256']+'.rgba8');path.write_bytes(b'original occupied file')
                self.assertEqual(self.imported(root,data,1)['code'],'ASSET_CORRUPT');self.assertEqual(path.read_bytes(),b'original occupied file')

    def test_publication_extensions_receipts_create_only_and_alpha_failure(self):
        d,_=self.document();before=copy.deepcopy(d)
        with tempfile.TemporaryDirectory() as root:
            for format,names in [('jpeg',['image.jpg','image.jpeg','IMAGE.JPG']),('tiff',['image.tif','image.tiff'])]:
                for index,name in enumerate(names):
                    # Avoid case-insensitive collisions on Windows.
                    folder=Path(root)/(str(index)+'-'+name.replace('.','-'));folder.mkdir()
                    options=dict(output_root=str(folder),file_name=name,format=format,image_options=dict(matte=[255]*3,quality=95) if format=='jpeg' else dict(compression='none'))
                    request=dict(command='document.publish',document=d,output=options)
                    r=self.invoke(request);data=(folder/name).read_bytes();self.assertEqual(r['sha256'],hashlib.sha256(data).hexdigest());self.assertEqual(r['bytes'],len(data));self.assertIn('settings',r)
                    self.assertEqual(self.invoke(request,1)['code'],'OUTPUT_EXISTS');self.assertEqual((folder/name).read_bytes(),data);self.assertEqual(len(list(folder.iterdir())),1)
            options=dict(output_root=root,file_name='transparent.jpg',format='jpeg')
            self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=options),1)['code'],'ALPHA_POLICY_REQUIRED');self.assertFalse((Path(root)/'transparent.jpg').exists())
            options.update(file_name='wrong.png',image_options=dict(matte=[255]*3))
            self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=options),1)['code'],'INVALID_REQUEST');self.assertEqual(d,before)

    def test_artboard_ranges_bleed_scale_and_atomic_failure_share_format_contracts(self):
        helper=boards.BoardCliTests();d=helper.fixture('raster');original=copy.deepcopy(d)
        for scale in (1,2):
            pngs=self.invoke(dict(command='artboard.export',document=d,format='png',include_bleed=True,scale=scale))
            for format in ('tiff','jpeg'):
                options=dict(compression='none') if format=='tiff' else dict(matte=[255]*3)
                result=self.invoke(dict(command='artboard.export',document=d,format=format,image_options=options,include_bleed=True,scale=scale))
                self.assertEqual([a['id'] for a in result['artifacts']],['wide','tall'])
                for a,b in zip(result['artifacts'],pngs['artifacts']):
                    self.assertEqual(a['source_bounds'],b['source_bounds']);self.assertEqual(a['trim_box'],b['trim_box']);self.assertEqual((a['artifact']['width'],a['artifact']['height']),(b['artifact']['width'],b['artifact']['height']))
                    if format=='tiff':self.assertEqual(tiff_uncompressed(base64.b64decode(a['artifact']['data']))[:3],editing.png_pixels(base64.b64decode(b['artifact']['data']))[:3])
                selected=self.invoke(dict(command='artboard.export',document=d,format=format,image_options=options,selection=dict(type='range',start=1,end=2)));self.assertEqual([a['id'] for a in selected['artifacts']],['tall'])
        error=self.invoke(dict(command='artboard.export',document=d,format='jpeg'),1);self.assertEqual(error['code'],'ALPHA_POLICY_REQUIRED');self.assertEqual(error['artboard_id'],'tall');self.assertNotIn('artifacts',error);self.assertEqual(d,original)

    def test_mcp_import_publish_durable_session_revision_and_undo(self):
        c=Client();self.addCleanup(c.close);c.initialize();d,pixels=self.document(4,3,True)
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'source.tiff';source.write_bytes(tiff_fixture(4,3,pixels));data=source.read_bytes();store=Path(root)/'assets'
            asset=c.success('asset.import',source_path=str(source),store_root=str(store),color_policy='assume_srgb')['asset']
            session=dict(session_root=root,session_id='image-session');c.success('session.create',**session,request_id='create',document=d,resources=dict(asset_root=str(store)))
            ops=[dict(op='asset_put',id='import',asset=asset),dict(op='add',item=dict(id='placed',content=dict(type='image',asset_id='import',width=4,height=3)))]
            r=c.success('session.apply',**session,request_id='place',expected_revision=0,action=dict(type='edit',operations=ops));self.assertEqual(r['document']['revision'],1)
            for format,name in [('jpeg','out.jpg'),('tiff','out.tif')]:
                output=dict(output_root=root,file_name=name,format=format)
                r=c.success('session.publish',**session,expected_revision=1,output=output);self.assertEqual(r['revision'],1)
                self.assertEqual(r['sha256'],hashlib.sha256((Path(root)/name).read_bytes()).hexdigest())
            self.assertTrue(c.tool('session.publish',**session,expected_revision=0,output=dict(output_root=root,file_name='stale.jpg',format='jpeg'))['isError']);self.assertFalse((Path(root)/'stale.jpg').exists())
            undone=c.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertNotIn('placed',[i['id'] for i in undone['items']]);c.success('session.verify',**session)
            self.assertEqual(source.read_bytes(),data)


if __name__=='__main__':unittest.main()
