"""Original RGB ICC fixtures, independent transfer equations and metadata framing."""
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
import test_image_io_cli as images
import test_boards_cli as boards
from test_images_cli import png,chunk
from test_mcp import Client


def builtin(name):return dict(type='builtin',name=name)
def embedded(data):return dict(type='icc',data=base64.b64encode(data).decode())
def linear_profile(gamma=1,large=False,lut=False):
    """Original v4 matrix/TRC profile. Public D50 sRGB primaries; no bundled profile."""
    fixed=lambda x:struct.pack('>i',round(x*65536))
    xyz=lambda v:b'XYZ '+bytes(4)+b''.join(fixed(x) for x in v)
    def mluc(text):
        raw=text.encode('utf-16be');return b'mluc'+bytes(4)+struct.pack('>II4sII',1,12,b'enUS',len(raw),28)+raw
    tags={b'desc':mluc('Inkbolt original gamma fixture'),b'cprt':mluc('Original synthetic fixture; MIT'),b'wtpt':xyz([.9642,1,.8249]),b'rXYZ':xyz([.4360747,.2225045,.0139322]),b'gXYZ':xyz([.3850649,.7168786,.0971045]),b'bXYZ':xyz([.1430804,.0606169,.7141733])}
    for color in b'rgb':tags[bytes([color])+b'TRC']=b'curv'+bytes(4)+struct.pack('>IH',1,round(gamma*256))
    if lut:
        matrix=[[.4360747,.3850649,.1430804],[.2225045,.7168786,.0606169],[.0139322,.0971045,.7141733]]
        corners=[round(sum(row[c]*point[c] for c in range(3))*32768) for r in (0,1) for g in (0,1) for b in (0,1) for point in [(r,g,b)] for row in matrix]
        table=struct.pack('>6H',0,65535,0,65535,0,65535)
        data=b'mft2'+bytes(4)+bytes([3,3,2,0])+b''.join(fixed(v) for v in [1,0,0,0,1,0,0,0,1])+struct.pack('>HH',2,2)+table+struct.pack('>'+str(len(corners))+'H',*corners)+table
        tags={k:v for k,v in tags.items() if k in (b'desc',b'cprt',b'wtpt')};tags[b'A2B0']=data;tags[b'A2B1']=data
    if large:tags[b'note']=b'text'+bytes(4)+b'original optional metadata '*4000
    offset=132+len(tags)*12;table=[];body=bytearray()
    for signature,data in sorted(tags.items()):
        table.append(signature+struct.pack('>II',offset+len(body),len(data)));body.extend(data);body.extend(bytes(-len(body)%4))
    header=bytearray(128);struct.pack_into('>I',header,0,offset+len(body));header[8:12]=b'\x04\x30\0\0';header[12:24]=b'mntrRGB XYZ ';struct.pack_into('>6H',header,24,2000,1,1,0,0,0);header[36:40]=b'acsp';struct.pack_into('>I',header,64,1);header[68:80]=b''.join(fixed(v) for v in [.9642,1,.8249]);header[80:84]=b'Inkb'
    return bytes(header)+struct.pack('>I',len(tags))+b''.join(table)+body


def png_profile(data):
    _,_,_,chunks=editing.png_pixels(data)
    assert b'sRGB' not in chunks
    field=chunks[b'iCCP'];at=field.index(0);assert field[at+1]==0
    return zlib.decompress(field[at+2:])
def tiff_profile(data):
    return bytes(images.tiff_tags(data)[34675])
def jpeg_profile(data):
    parts={};total=None
    for marker,payload in images.jpeg_segments(data):
        if marker==0xe2 and payload.startswith(b'ICC_PROFILE\0'):
            assert payload[12] not in parts;parts[payload[12]]=payload[14:]
            assert total in (None,payload[13]);total=payload[13]
    assert set(parts)==set(range(1,total+1))
    return b''.join(parts[i] for i in range(1,total+1))
def encode_srgb(v):return 12.92*v if v<=.0031308 else 1.055*v**(1/2.4)-.055
def decode_srgb(v):return v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4


class ProfileTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def document(self,kind='raster'):
        d=self.invoke(dict(command='document.create',id='profiles',kind=kind,width=16,height=4))
        pixels=bytes(v for y in range(4) for x in range(16) for v in (x*17,(15-x)*17,(x*73)%256,[0,64,128,255][y]))
        if kind=='raster':d['items']=[dict(id='pixels',content=dict(type='raster',width=16,height=4,rgba_hex=pixels.hex()))]
        else:d['items']=[dict(id='p'+str(y*16+x),content=dict(type='vector',geometry=dict(shape='rect',x=x,y=y,width=1,height=1),fill=list(pixels[(y*16+x)*4:(y*16+x+1)*4]))) for y in range(4) for x in range(16)]
        return d,pixels
    def edit(self,d,profile,expected=0):return self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='output_profile',profile=profile)]),expected)
    def export(self,d,format='png',expected=0,**kw):return self.invoke(dict(command='document.export',document=d,format=format,**kw),expected)
    def imported(self,root,data,expected=0,**kw):
        source=Path(root)/'original.bin';source.write_bytes(data);before=source.read_bytes();store=Path(root)/'assets'
        request=dict(command='asset.import',source_path=str(source),store_root=str(store),color_policy='convert_srgb');request.update(kw)
        r=self.invoke(request,expected);self.assertEqual(source.read_bytes(),before)
        if expected:return r
        self.assertEqual(r['asset']['provenance']['source_sha256'],hashlib.sha256(data).hexdigest())
        return r,(store/(r['asset']['sha256']+'.rgba8')).read_bytes()[16:]

    def test_original_linear_and_gamma_tagged_png_convert_independent_equations(self):
        _,pixels=self.document()
        with tempfile.TemporaryDirectory() as root:
            for gamma in (1,1.8,2.2):
                profile=linear_profile(gamma);actual_gamma=round(gamma*256)/256
                data=png(16,4,pixels,tagged=False,extra=[(b'iCCP',b'original\0\0'+zlib.compress(profile))]);r,raw=self.imported(root,data)
                expected=bytes(v if i%4==3 else round(255*encode_srgb((v/255)**actual_gamma)) for i,v in enumerate(pixels))
                # ICC fixed-point D50 primaries differ slightly from ideal sRGB;
                # the encoded dark-channel response permits two byte levels.
                self.assertLessEqual(max(abs(a-b) for a,b in zip(raw,expected)),2);self.assertEqual(raw[3::4],pixels[3::4])
                self.assertEqual(r['asset']['provenance']['interpretation'],'converted_srgb');self.assertEqual(r['asset']['provenance']['source_profile_sha256'],hashlib.sha256(profile).hexdigest())
                self.assertEqual(self.imported(root,data,1,color_policy='assume_srgb')['code'],'UNSUPPORTED')

    def test_original_rgb_lookup_profile_converts_tagged_samples(self):
        _,pixels=self.document();profile=linear_profile(lut=True);data=png(16,4,pixels,tagged=False,extra=[(b'iCCP',b'original\0\0'+zlib.compress(profile))])
        with tempfile.TemporaryDirectory() as root:
            result,raw=self.imported(root,data);expected=bytes(v if i%4==3 else round(255*encode_srgb(v/255)) for i,v in enumerate(pixels))
            self.assertLessEqual(max(abs(a-b) for a,b in zip(raw,expected)),2);self.assertEqual(result['asset']['provenance']['source_profile_sha256'],hashlib.sha256(profile).hexdigest())

    def test_explicit_untagged_input_profiles_and_tag_conflicts(self):
        _,pixels=self.document();raw_png=png(16,4,pixels,tagged=False);profile=linear_profile()
        with tempfile.TemporaryDirectory() as root:
            result,raw=self.imported(root,raw_png,input_profile=embedded(profile));expected=bytes(v if i%4==3 else round(255*encode_srgb(v/255)) for i,v in enumerate(pixels));self.assertLessEqual(max(abs(a-b) for a,b in zip(raw,expected)),1)
            self.assertEqual(self.imported(root,raw_png,1)['code'],'COLOR_POLICY_REQUIRED')
            self.assertEqual(self.imported(root,png(16,4,pixels),1,input_profile=embedded(profile))['code'],'PROFILE_CONFLICT')
            data=png(16,4,pixels,tagged=False,extra=[(b'iCCP',b'original\0\0'+zlib.compress(profile))]);self.assertEqual(self.imported(root,data,input_profile=embedded(profile))[1],raw)
            self.assertEqual(self.imported(root,data,1,input_profile=builtin('display_p3'))['code'],'PROFILE_CONFLICT')

    def test_profiled_png_and_tiff_convert_all_pixels_keep_alpha_and_exact_profile_bytes(self):
        for kind in ('vector','raster'):
            d,pixels=self.document(kind);before=copy.deepcopy(d);profile=linear_profile();changed=self.edit(d,embedded(profile))['document']
            preview=self.invoke(dict(command='document.render',document=d));working=bytes.fromhex(preview['data']);self.assertEqual(preview,self.invoke(dict(command='document.render',document=changed)))
            expected=bytes(v if i%4==3 else round(255*decode_srgb(v/255)) for i,v in enumerate(working))
            for format in ('png','tiff'):
                kw=dict(image_options=dict(compression='none')) if format=='tiff' else {}
                artifact=self.export(changed,format,**kw);data=base64.b64decode(artifact['data']);embedded_bytes=png_profile(data) if format=='png' else tiff_profile(data);self.assertEqual(embedded_bytes,profile)
                actual=editing.png_pixels(data)[2] if format=='png' else images.tiff_uncompressed(data)[2]
                self.assertEqual(actual[3::4],working[3::4]);self.assertLessEqual(max(abs(a-b) for a,b in zip(actual,expected)),1)
                self.assertEqual(artifact['color_profile']['icc_sha256'],hashlib.sha256(profile).hexdigest());self.assertEqual(artifact['color_space'],'icc_rgb')
                self.assertEqual(self.export(changed,format,**kw),artifact)
            self.assertEqual(d,before);self.assertEqual(json.loads(self.export(changed,'snapshot')['data']),changed)

    def test_builtins_embed_valid_reproducible_profiles_and_reimport(self):
        d,_=self.document()
        with tempfile.TemporaryDirectory() as root:
            for name in ('srgb','linear_srgb','display_p3'):
                changed=self.edit(d,builtin(name))['document'];first=self.export(changed);second=self.export(changed);self.assertEqual(first,second);profile=png_profile(base64.b64decode(first['data']));self.assertEqual(profile[36:40],b'acsp');self.assertEqual(struct.unpack_from('>6H',profile,24),(2000,1,1,0,0,0))
                if name=='srgb':self.assertEqual(editing.png_pixels(base64.b64decode(first['data']))[2],bytes.fromhex(self.invoke(dict(command='document.render',document=d))['data']))
                for format,extract in [('png',png_profile),('tiff',tiff_profile),('jpeg',jpeg_profile)]:
                    kw=dict(image_options=dict(matte=[240]*3,quality=100)) if format=='jpeg' else {}
                    artifact=self.export(changed,format,**kw);data=base64.b64decode(artifact['data']);self.assertEqual(extract(data),profile);result,raw=self.imported(root,data);self.assertEqual(result['asset']['provenance']['source_profile_sha256'],hashlib.sha256(profile).hexdigest())
                    if format!='jpeg':self.assertEqual(raw[3::4],bytes.fromhex(self.invoke(dict(command='document.render',document=d))['data'])[3::4])

    def test_profile_assignment_clear_diff_snapshot_and_unsupported_svg_are_explicit(self):
        d,_=self.document('vector');before=copy.deepcopy(d);changed=self.edit(d,builtin('display_p3'))['document'];difference=self.invoke(dict(command='document.diff',before=d,after=changed,compare_pixels=True))
        self.assertTrue(difference['changed']);self.assertEqual(difference['rendered_pixels']['changed_pixels'],0)
        self.assertEqual(self.export(changed,'svg',1)['code'],'UNSUPPORTED');cleared=self.edit(changed,None)['document'];self.assertNotIn('output_profile',cleared);self.export(cleared,'svg');self.assertEqual(d,before)

    def test_profile_validation_byte_table_bounds_unknown_fields_and_batch_rollback(self):
        d,_=self.document();original=linear_profile();cases=[b'bad',original[:-1],original+b'junk']
        for at,value in [(0,2**32-1),(128,2**32-1),(136,0),(140,2**32-1)]:
            bad=bytearray(original);struct.pack_into('>I',bad,at,value);cases.append(bad)
        for data in cases:self.assertIn(self.edit(d,embedded(data),1)['code'],['INVALID_PROFILE','RESOURCE_LIMIT'])
        for profile in [dict(type='builtin',name='unknown'),dict(type='builtin',name='srgb',intent='absolute'),dict(type='icc',data='%%'),dict(type='icc',data='A'*(256*1024*4//3+16))]:
            self.assertIn(self.edit(d,profile,1)['code'],['INVALID_REQUEST','INVALID_PROFILE','RESOURCE_LIMIT'])
        bad=bytearray(original);bad[16:20]=b'CMYK';self.assertEqual(self.edit(d,embedded(bad),1)['code'],'UNSUPPORTED')
        self.assertEqual(self.invoke(dict(command='document.edit',document=d,expected_revision=0,operations=[dict(op='output_profile',profile=builtin('srgb')),dict(op='remove',id='missing')]),1)['operation_index'],1);self.assertNotIn('output_profile',d)

    def test_large_jpeg_profile_segments_missing_duplicate_and_out_of_order(self):
        d,_=self.document();profile=linear_profile(large=True);changed=self.edit(d,embedded(profile))['document'];artifact=self.export(changed,'jpeg',image_options=dict(matte=[255]*3));data=base64.b64decode(artifact['data']);self.assertEqual(jpeg_profile(data),profile)
        # Locate APP2 blocks using independent marker lengths, before the entropy stream.
        at=2;parts=[]
        while at<len(data):
            marker=data[at+1];n=int.from_bytes(data[at+2:at+4],'big');end=at+2+n
            if marker==0xe2:parts.append((at,end,data[at:end]))
            if marker==0xda:break
            at=end
        self.assertGreater(len(parts),1);without=data[:parts[0][0]]+data[parts[-1][1]:];start=parts[0][0]
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(self.imported(root,data)[0]['asset']['provenance']['source_profile_sha256'],hashlib.sha256(profile).hexdigest())
            reordered=without[:start]+b''.join(p[2] for p in reversed(parts))+without[start:];self.assertEqual(self.imported(root,reordered)[1],self.imported(root,data)[1])
            missing=without[:start]+parts[0][2]+without[start:];self.assertEqual(self.imported(root,missing,1)['code'],'INVALID_IMAGE')
            duplicate=without[:start]+b''.join(p[2] for p in parts)+parts[0][2]+without[start:];self.assertEqual(self.imported(root,duplicate,1)['code'],'INVALID_IMAGE')

    def test_mcp_profile_history_publication_revisions_and_source_preservation(self):
        c=Client();self.addCleanup(c.close);c.initialize();d,_=self.document();profile=builtin('linear_srgb')
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='profiles');c.success('session.create',**session,request_id='create',document=d)
            changed=c.success('session.apply',**session,request_id='profile',expected_revision=0,action=dict(type='edit',operations=[dict(op='output_profile',profile=profile)]))['document'];self.assertEqual(changed['output_profile'],profile)
            receipt=c.success('session.publish',**session,expected_revision=1,output=dict(output_root=root,file_name='result.png',format='png'));data=(Path(root)/'result.png').read_bytes();self.assertEqual(receipt['color_profile']['icc_sha256'],hashlib.sha256(png_profile(data)).hexdigest())
            undo=c.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertNotIn('output_profile',undo)
            redo=c.success('session.apply',**session,request_id='redo',expected_revision=2,action=dict(type='redo'))['document'];self.assertEqual(redo['output_profile'],profile);c.success('session.verify',**session);self.assertNotIn('output_profile',d)

    def test_artboards_bleed_ranges_and_create_only_receipts_preserve_profile(self):
        d=boards.BoardCliTests().fixture('raster');profile=linear_profile();d=self.edit(d,embedded(profile))['document'];original=copy.deepcopy(d)
        for format,extract in [('png',png_profile),('tiff',tiff_profile),('jpeg',jpeg_profile)]:
            options=dict(image_options=dict(matte=[255]*3)) if format=='jpeg' else {}
            result=self.invoke(dict(command='artboard.export',document=d,format=format,include_bleed=True,scale=2,selection=dict(type='ids',ids=['tall','wide']),**options))
            self.assertEqual([a['id'] for a in result['artifacts']],['tall','wide'])
            for artifact in result['artifacts']:
                self.assertEqual(extract(base64.b64decode(artifact['artifact']['data'])),profile)
            with tempfile.TemporaryDirectory() as root:
                output=dict(output_root=root,file_name='board.'+dict(png='png',tiff='tif',jpeg='jpg')[format],format=format,artboard_id='wide',include_bleed=True,scale=2,**options)
                request=dict(command='document.publish',document=d,output=output);receipt=self.invoke(request);data=(Path(root)/output['file_name']).read_bytes();self.assertEqual(data,base64.b64decode(result['artifacts'][1]['artifact']['data']));self.assertEqual(receipt['color_profile']['icc_sha256'],hashlib.sha256(profile).hexdigest())
                self.assertEqual(self.invoke(request,1)['code'],'OUTPUT_EXISTS');self.assertEqual((Path(root)/output['file_name']).read_bytes(),data)
        self.assertEqual(d,original)

    def test_tiff_tagged_source_and_explicit_profile_jpeg_match_normalized_identity(self):
        d,pixels=self.document();profile=linear_profile()
        with tempfile.TemporaryDirectory() as root:
            source=images.tiff_fixture(16,4,pixels,tags={34675:(1,list(profile))});r,raw=self.imported(root,source)
            tagged=png(16,4,pixels,tagged=False,extra=[(b'iCCP',b'original\0\0'+zlib.compress(profile))]);other,expected=self.imported(root,tagged);self.assertEqual(raw,expected);self.assertEqual(r['asset']['sha256'],other['asset']['sha256']);self.assertFalse(other['created'])
            self.assertEqual(r['color_conversion']['intent'],'relative_colorimetric');self.assertEqual(r['color_conversion']['alpha'],'unchanged')
            jpeg=base64.b64decode(self.export(d,'jpeg',image_options=dict(matte=[255]*3,quality=100))['data']);assigned,converted=self.imported(root,jpeg,input_profile=embedded(profile));assumed,decoded=self.imported(root,jpeg,color_policy='assume_srgb')
            wanted=bytes(v if i%4==3 else round(255*encode_srgb(v/255)) for i,v in enumerate(decoded));self.assertLessEqual(max(abs(a-b) for a,b in zip(converted,wanted)),2);self.assertNotEqual(assigned['asset']['sha256'],assumed['asset']['sha256'])

    def test_png_conflicting_duplicate_bad_profiles_and_gray_semantics_fail(self):
        _,pixels=self.document();profile=linear_profile();icc=(b'iCCP',b'original\0\0'+zlib.compress(profile))
        fixtures=[png(16,4,pixels,extra=[icc]),png(16,4,pixels,tagged=False,extra=[icc,icc]),png(16,4,pixels,tagged=False,extra=[(b'iCCP',b'bad\0\0'+zlib.compress(b'invalid profile'))])]
        with tempfile.TemporaryDirectory() as root:
            for data in fixtures:self.assertIn(self.imported(root,data,1)['code'],['INVALID_IMAGE','INVALID_PROFILE']);self.assertFalse((Path(root)/'assets').exists())
            gray=png(1,1,b'',color=0,raw=b'\0\x80',tagged=False,extra=[icc]);self.assertEqual(self.imported(root,gray,1)['code'],'UNSUPPORTED')

    def test_input_profile_validation_and_converted_provenance_fail_closed(self):
        d,pixels=self.document();profile=linear_profile();source=png(16,4,pixels,tagged=False)
        with tempfile.TemporaryDirectory() as root:
            for policy in ('require_srgb','assume_srgb'):self.assertEqual(self.imported(root,source,1,input_profile=embedded(profile),color_policy=policy)['code'],'UNSUPPORTED')
            result,_=self.imported(root,source,input_profile=embedded(profile));asset=result['asset'];self.assertEqual(self.invoke(dict(command='asset.verify',asset=asset,asset_root=str(Path(root)/'assets')))['valid'],True)
            for change in [{'source_profile_sha256':None},{'source_profile_sha256':'bad'},{'interpretation':'assumed_srgb'}]:
                invalid=copy.deepcopy(asset);invalid['provenance'].update(change);self.assertEqual(self.invoke(dict(command='asset.verify',asset=invalid,asset_root=str(Path(root)/'assets')),1)['code'],'INVALID_DOCUMENT')

    def test_profile_inspection_and_transfer_keep_destination_color_context(self):
        source,_=self.document('vector');source=self.edit(source,builtin('linear_srgb'))['document'];destination=self.invoke(dict(command='document.create',id='destination',kind='vector',width=16,height=4));destination=self.edit(destination,builtin('display_p3'))['document']
        transfer=self.invoke(dict(command='document.edit',document=destination,expected_revision=1,operations=[dict(op='transfer',transfer=dict(source=source,ids=['p20'],prefix='copy'))]))['document'];self.assertEqual(transfer['output_profile'],destination['output_profile']);self.assertEqual(source['output_profile'],builtin('linear_srgb'))
        profile=png_profile(base64.b64decode(self.export(transfer)['data']));summary=self.invoke(dict(command='document.inspect',document=transfer))['output_profile'];self.assertEqual(summary['icc_sha256'],hashlib.sha256(profile).hexdigest());self.assertNotIn('data',summary)


if __name__=='__main__':unittest.main()
