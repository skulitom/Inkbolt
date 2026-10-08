"""Original descriptions, independent container parsing and source-preserving privacy checks."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing
import test_image_io_cli as images
import test_profiles_cli as profiles
import test_boards_cli as boards
from test_images_cli import chunk
from test_mcp import Client
from synthetic_font import geometric_font


PRIVATE = 'C:\\private-original\\work\\notes.txt'
PUBLIC = dict(title='Original diagram',description='Unicode café 漢字 🦉 <&>\nline two',author='Fixture author',rights='Original fixture',tags=['diagram','release-1'],properties={'brief':'Agent-readable description'},private={'local_path':PRIVATE})
NOTE = dict(note='Keep this editable',tags=['primary','source'],private={'review':'private-note-marker'})
PNG_KEY = b'Inkbolt Metadata'
JPEG_PREFIX = b'INKBOLT-META\0'


def public(record):
    result=copy.deepcopy(record);result.pop('private',None);return result


def carrier(data,format):
    if format=='png':
        _,_,_,chunks=editing.png_pixels(data)
        value=chunks.get(b'iTXt')
        if value is None:return None
        assert value.startswith(PNG_KEY+bytes(5))
        return value[len(PNG_KEY)+5:]
    if format=='jpeg':
        parts={};total=None
        for marker,payload in images.jpeg_segments(data):
            if marker!=0xfe or not payload.startswith(JPEG_PREFIX):continue
            index,n=struct.unpack('>HH',payload[len(JPEG_PREFIX):len(JPEG_PREFIX)+4])
            assert total in (None,n) and index not in parts
            total=n;parts[index]=payload[len(JPEG_PREFIX)+4:]
        if not parts:return None
        assert set(parts)==set(range(1,total+1))
        return b''.join(parts[i] for i in range(1,total+1))
    if format=='tiff':
        tags=images.tiff_tags(data)
        value=tags.get(270)
        if value is None:return None
        raw=bytes(value).rstrip(b'\0');assert raw.startswith(b'Inkbolt metadata v1\n')
        return raw[len(b'Inkbolt metadata v1\n'):]
    root=ET.fromstring(data);node=root.find('{http://www.w3.org/2000/svg}metadata/{urn:inkbolt:metadata:1}inkbolt')
    return None if node is None else node.text.encode()


class MetadataTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def document(self,kind='vector'):
        d=self.invoke(dict(command='document.create',id='metadata-original',kind=kind,width=16,height=8,resolution_ppi=150.5))
        d['items']=[dict(id='art',content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=16,height=8),fill=[20,80,150,255]))] if kind=='vector' else [dict(id='art',content=dict(type='raster',width=16,height=8,rgba_hex=bytes([20,80,150,255]*128).hex()))]
        # Validate/canonicalize the original to make byte comparisons meaningful.
        return json.loads(self.export(d,'snapshot')['data'])
    def edit(self,d,ops,expected=0):
        result=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=ops),expected)
        return result if expected else result['document']
    def annotated(self,kind='vector'):
        d=self.document(kind)
        return self.edit(d,[dict(op='metadata',value=PUBLIC),dict(op='metadata',id='art',value=NOTE)])
    def export(self,d,format,expected=0,**kw):
        if format=='jpeg':kw.setdefault('image_options',dict(quality=100,chroma='full'))
        return self.invoke(dict(command='document.export',document=d,format=format,**kw),expected)
    def data(self,d,format,**kw):
        a=self.export(d,format,**kw);return base64.b64decode(a['data']) if a['encoding']=='base64' else a['data'].encode()
    def pixels(self,d):return self.invoke(dict(command='document.render',document=d))['data']
    def imported(self,root,data,**kw):
        source=Path(root)/'original.bin';source.write_bytes(data)
        result=self.invoke(dict(command='asset.import',source_path=str(source),store_root=str(Path(root)/'store'),color_policy='assume_srgb',**kw))
        self.assertEqual(source.read_bytes(),data);return result

    def test_document_and_object_unicode_records_snapshot_and_pixels(self):
        for kind in ('vector','raster'):
            d=self.document(kind);before=copy.deepcopy(d);changed=self.annotated(kind)
            saved=self.data(changed,'snapshot');reopened=json.loads(saved)
            self.assertEqual(reopened['metadata'],PUBLIC);self.assertEqual(reopened['items'][0]['metadata'],NOTE)
            self.assertEqual(self.pixels(reopened),self.pixels(d));self.assertEqual(d,before)
            inspect=self.invoke(dict(command='document.inspect',document=reopened));self.assertEqual(inspect['metadata'],PUBLIC);self.assertEqual(inspect['items'][0]['metadata'],NOTE)
            diff=self.invoke(dict(command='document.diff',before=d,after=reopened,compare_pixels=True))
            self.assertEqual(diff['rendered_pixels']['changed_pixels'],0);self.assertIn('metadata',[v['field'] for v in diff['metadata']]);self.assertIn('metadata',diff['items'][0]['fields'])

    def test_public_records_are_exact_in_independently_parsed_all_formats(self):
        for kind in ('vector','raster'):
            d=self.annotated(kind);original=copy.deepcopy(d)
            for format in (('png','jpeg','tiff','svg') if kind=='vector' else ('png','jpeg','tiff')):
                data=self.data(d,format);packet=carrier(data,format);value=json.loads(packet)
                self.assertEqual(value['document'],public(PUBLIC));self.assertEqual(value['items'],{'art':public(NOTE)})
                self.assertNotIn(PRIVATE.encode(),data);self.assertNotIn(b'private-note-marker',data)
                self.assertEqual(value['delivery']['format'],format);self.assertEqual(value['delivery']['orientation'],'top_left')
                artifact=self.export(d,format);self.assertEqual(artifact['metadata']['envelope_sha256'],hashlib.sha256(packet).hexdigest())
                self.assertEqual(data,self.data(d,format))
            self.assertEqual(d,original)

    def test_privacy_stripping_preserves_pixel_codecs_color_and_density(self):
        d=self.annotated('raster');d=self.edit(d,[dict(op='output_profile',profile=profiles.builtin('linear_srgb'))]);clean=copy.deepcopy(d);clean.pop('metadata');clean['items'][0].pop('metadata')
        for format,extract in [('png',profiles.png_profile),('jpeg',profiles.jpeg_profile),('tiff',profiles.tiff_profile)]:
            kept=self.data(d,format);stripped=self.data(d,format,metadata_policy=dict(mode='strip'))
            self.assertIsNone(carrier(stripped,format));self.assertEqual(stripped,self.data(clean,format));self.assertEqual(extract(kept),extract(stripped))
            self.assertNotIn(b'Original diagram',stripped);self.assertEqual(self.export(d,format,metadata_policy=dict(mode='strip'))['metadata']['private_fields'],'removed')
        snapped=json.loads(self.data(d,'snapshot',metadata_policy=dict(mode='strip')));self.assertEqual(snapped,clean)
        visible=json.loads(self.data(d,'snapshot',metadata_policy=dict(mode='public')));self.assertEqual(visible['metadata'],public(PUBLIC));self.assertEqual(visible['items'][0]['metadata'],public(NOTE))

    def test_asset_import_recovers_metadata_without_changing_pixel_identity(self):
        d=self.annotated('raster')
        with tempfile.TemporaryDirectory() as root:
            for format in ('png','jpeg','tiff'):
                data=self.data(d,format);tagged=self.imported(root,data);plain=self.imported(root,self.data(d,format,metadata_policy=dict(mode='strip')))
                self.assertEqual(tagged['asset']['sha256'],plain['asset']['sha256']);self.assertFalse(plain['created'])
                self.assertEqual(tagged['metadata']['envelope'],json.loads(carrier(data,format)));self.assertIn('untrusted',tagged['metadata']['trust']);self.assertNotIn('metadata',plain)

    def test_provenance_digest_matches_independent_canonical_document(self):
        d=self.annotated();policy=dict(mode='public',manifest=True,provenance=True)
        sanitized=copy.deepcopy(d);sanitized['metadata']=public(PUBLIC);sanitized['items'][0]['metadata']=public(NOTE)
        # JSON numbers emitted by the Rust snapshot preserve float-vs-integer
        # tokens. Use a separate canonical writer over that typed snapshot.
        saved=json.loads(self.data(d,'snapshot',metadata_policy=dict(mode='public')))
        digest=hashlib.sha256(json.dumps(saved,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        for format in ('png','jpeg','tiff','svg'):
            packet=json.loads(carrier(self.data(d,format,metadata_policy=policy),format));self.assertEqual(packet['provenance']['source_sha256'],digest)
            self.assertEqual(packet['manifest']['images'],{});self.assertEqual(packet['manifest']['fonts'],{});self.assertNotIn('time',packet['provenance'])
        changed=copy.deepcopy(d);changed['metadata']['private']['local_path']='D:/other-private-location'
        self.assertEqual(self.data(d,'png',metadata_policy=policy),self.data(changed,'png',metadata_policy=policy))

    def test_named_asset_manifest_keeps_hashes_and_omits_runtime_locations(self):
        d=self.annotated('raster');source=self.data(self.document('raster'),'png')
        with tempfile.TemporaryDirectory() as root:
            imported=self.imported(root,source);d['assets']={'original':imported['asset']}
            art=self.export(d,'png',asset_root=str(Path(root)/'store'),metadata_policy=dict(manifest=True));value=json.loads(carrier(base64.b64decode(art['data']),'png'))
            self.assertEqual(value['manifest']['images']['original'],dict(sha256=imported['asset']['sha256'],width=16,height=8))
            self.assertNotIn(root,json.dumps(value));self.assertNotIn('source_path',json.dumps(value));self.assertEqual(self.invoke(dict(command='document.inspect',document=d))['resource_manifest'],value['manifest'])

    def test_metadata_validation_and_atomic_failures_preserve_original(self):
        d=self.document();original=copy.deepcopy(d)
        invalid=[dict(tags=['same','same']),dict(tags=['']),dict(tags=['x'*129]),dict(title='nul\0'),dict(note='x'*8193),dict(properties={'bad/key':'value'}),dict(unexpected=True)]
        for record in invalid:self.assertIn(self.edit(d,[dict(op='metadata',value=record)],1)['code'],['INVALID_METADATA','RESOURCE_LIMIT','INVALID_REQUEST'])
        self.assertEqual(self.edit(d,[dict(op='metadata',value=PUBLIC),dict(op='metadata',id='missing',value=NOTE)],1)['operation_index'],1);self.assertEqual(d,original)
        d['items'][0]['locked']=True;self.assertEqual(self.edit(d,[dict(op='metadata',id='art',value=NOTE)],1)['code'],'LOCKED')
        self.assertEqual(self.export(d,'png',1,metadata_policy=dict(mode='strip',unknown=True))['code'],'INVALID_REQUEST')

    def test_record_and_document_metadata_budgets_and_legacy_rejection(self):
        d=self.document();large=dict(description='a'*8000,note='b'*8000,properties={'pad':'x'*1000})
        self.assertEqual(self.edit(d,[dict(op='metadata',value=large)],1)['code'],'RESOURCE_LIMIT')
        d['items']=[dict(id='p'+str(i),content=dict(type='vector',geometry=dict(shape='rect',x=i,y=0,width=1,height=1),fill=[0,0,0,255]),metadata=dict(note='n'*8000,description='d'*7000)) for i in range(5)]
        self.assertEqual(self.invoke(dict(command='document.validate',document=d),1)['code'],'RESOURCE_LIMIT')
        old=self.invoke(dict(command='document.create',id='old',kind='vector',width=1,height=1));old['schema_version']=1;old['metadata']=dict(title='invalid legacy')
        self.assertEqual(self.invoke(dict(command='document.validate',document=old),1)['code'],'INVALID_DOCUMENT')

    def test_duplicate_transfer_clear_and_undo_preserve_metadata_ownership(self):
        d=self.annotated();copied=self.edit(d,[dict(op='duplicate',id='art',new_id='copy')]);self.assertEqual(copied['items'][1]['metadata'],NOTE)
        cleared=self.edit(copied,[dict(op='metadata',id='copy',value=None)]);self.assertNotIn('metadata',cleared['items'][1]);self.assertEqual(cleared['items'][0]['metadata'],NOTE)
        destination=self.document();destination['id']='destination';destination['items']=[];destination['metadata']=dict(title='Destination notes')
        moved=self.edit(destination,[dict(op='transfer',transfer=dict(source=d,ids=['art'],prefix='placed'))]);self.assertEqual(moved['metadata'],destination['metadata']);self.assertEqual(moved['items'][0]['metadata'],NOTE)

    def test_mcp_session_metadata_history_publication_and_retry(self):
        c=Client();self.addCleanup(c.close);c.initialize();d=self.document()
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='metadata');c.success('session.create',**session,request_id='create',document=d)
            request=dict(**session,request_id='description',expected_revision=0,action=dict(type='edit',operations=[dict(op='metadata',value=PUBLIC),dict(op='metadata',id='art',value=NOTE)]))
            result=c.success('session.apply',**request);replay=c.success('session.apply',**request);self.assertTrue(replay['replayed']);self.assertEqual(replay['document'],result['document'])
            out=dict(output_root=root,file_name='public.png',format='png',metadata_policy=dict(provenance=True,manifest=True));receipt=c.success('session.publish',**session,expected_revision=1,output=out)
            data=(Path(root)/'public.png').read_bytes();self.assertEqual(receipt['sha256'],hashlib.sha256(data).hexdigest());self.assertEqual(receipt['metadata']['envelope_sha256'],hashlib.sha256(carrier(data,'png')).hexdigest())
            undone=c.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'));self.assertNotIn('metadata',undone['document'])
            redone=c.success('session.apply',**session,request_id='redo',expected_revision=2,action=dict(type='redo'));self.assertEqual(redone['document']['metadata'],PUBLIC);c.success('session.verify',**session)

    def test_artboard_range_metadata_view_provenance_and_create_only_publication(self):
        d=boards.BoardCliTests().fixture('vector');d=self.edit(d,[dict(op='metadata',value=PUBLIC)]);original=copy.deepcopy(d)
        policy=dict(mode='public',manifest=True,provenance=True)
        for format in ('png','jpeg','tiff','svg'):
            options=dict(image_options=dict(matte=[255]*3)) if format=='jpeg' else {}
            a=self.invoke(dict(command='artboard.export',document=d,format=format,metadata_policy=policy,selection=dict(type='ids',ids=['wide','tall']),include_bleed=True,**options))['artifacts']
            self.assertEqual([v['id'] for v in a],['wide','tall'])
            for v in a:
                artifact=v['artifact'];data=base64.b64decode(artifact['data']) if artifact['encoding']=='base64' else artifact['data'].encode();packet=json.loads(carrier(data,format));self.assertEqual(packet['document'],public(PUBLIC));self.assertEqual([packet['delivery']['width'],packet['delivery']['height']],v['logical_size'])
            with tempfile.TemporaryDirectory() as root:
                output=dict(output_root=root,file_name='board.'+format,format=format,artboard_id='wide',include_bleed=True,metadata_policy=policy,**options)
                receipt=self.invoke(dict(command='document.publish',document=d,output=output));before=(Path(root)/output['file_name']).read_bytes();self.assertEqual(receipt['metadata']['envelope_sha256'],hashlib.sha256(carrier(before,format)).hexdigest())
                self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=output),1)['code'],'OUTPUT_EXISTS');self.assertEqual(before,(Path(root)/output['file_name']).read_bytes())
        self.assertEqual(d,original)

    def test_svg_metadata_roundtrip_escapes_markup_and_retains_mapped_notes(self):
        d=self.annotated();data=self.data(d,'svg');root=ET.fromstring(data);self.assertEqual(len(root.findall('{http://www.w3.org/2000/svg}metadata')),1)
        reopened=self.invoke(dict(command='svg.import',id='reopened',source=dict(kind='text',text=data.decode())))['document']
        self.assertEqual(reopened['metadata'],public(PUBLIC));notes=[i['metadata'] for i in reopened['items'] if 'metadata' in i];self.assertEqual(notes,[public(NOTE)])
        self.assertEqual(self.pixels(reopened),self.pixels(d))

    def test_multipart_jpeg_metadata_and_reordered_missing_duplicate_parts(self):
        d=self.document('raster');d['items'][0]['metadata']=dict(note='🦉'*2000,description='🦉'*2000);d['metadata']=dict(note='🦉'*2000,description='🦉'*2000)
        data=self.data(d,'jpeg');raw=carrier(data,'jpeg');self.assertGreater(len(raw),60000)
        at=2;blocks=[]
        while data[at:at+2]!=b'\xff\xda':
            n=int.from_bytes(data[at+2:at+4],'big');end=at+2+n
            if data[at+1]==254 and data[at+4:].startswith(JPEG_PREFIX):blocks.append((at,end,data[at:end]))
            at=end
        self.assertGreater(len(blocks),1);base=data[:blocks[0][0]]+data[blocks[-1][1]:];start=blocks[0][0]
        with tempfile.TemporaryDirectory() as root:
            expected=self.imported(root,data)['metadata'];reordered=base[:start]+b''.join(b[2] for b in reversed(blocks))+base[start:];self.assertEqual(self.imported(root,reordered)['metadata'],expected)
            for bad in [base[:start]+blocks[0][2]+base[start:],base[:start]+b''.join(b[2] for b in blocks)+blocks[0][2]+base[start:]]:
                source=Path(root)/'bad.jpg';source.write_bytes(bad);self.assertEqual(self.invoke(dict(command='asset.import',source_path=str(source),store_root=str(Path(root)/'badstore'),color_policy='assume_srgb'),1)['code'],'INVALID_METADATA');self.assertFalse((Path(root)/'badstore').exists())

    def test_malformed_own_metadata_rejected_before_asset_publication(self):
        d=self.annotated('raster');data=self.data(d,'png');packet=carrier(data,'png');value=json.loads(packet)
        with tempfile.TemporaryDirectory() as root:
            for raw in [b'not json',json.dumps(dict(value,schema='unknown')).encode(),json.dumps(dict(value,document=dict(private={'local':PRIVATE}))).encode()]:
                plain=self.data(d,'png',metadata_policy=dict(mode='strip'));bad=plain[:-12]+chunk(b'iTXt',PNG_KEY+bytes(5)+raw)+plain[-12:]
                source=Path(root)/'bad.png';source.write_bytes(bad);store=Path(root)/'badstore';result=self.invoke(dict(command='asset.import',source_path=str(source),store_root=str(store)),1)
                self.assertEqual(result['code'],'INVALID_METADATA');self.assertFalse(store.exists());self.assertEqual(source.read_bytes(),bad)
            duplicate=data[:-12]+chunk(b'iTXt',PNG_KEY+bytes(5)+packet)+data[-12:];source=Path(root)/'duplicate.png';source.write_bytes(duplicate)
            self.assertEqual(self.invoke(dict(command='asset.import',source_path=str(source),store_root=str(Path(root)/'store')),1)['code'],'INVALID_METADATA')

    def test_font_manifest_retains_license_identity_without_local_paths(self):
        d=self.annotated()
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'original.ttf';license=Path(root)/'license.txt';source.write_bytes(geometric_font());license.write_text('Original synthetic geometry fixture; MIT')
            fonts=Path(root)/'fonts';record=self.invoke(dict(command='font.import',source_path=str(source),license_path=str(license),store_root=str(fonts)));d['fonts']={'original':record}
            value=json.loads(carrier(self.data(d,'png',font_root=str(fonts),metadata_policy=dict(manifest=True)),'png'))['manifest']
            self.assertEqual(value['fonts']['original'],dict(sha256=hashlib.sha256(source.read_bytes()).hexdigest(),license_sha256=hashlib.sha256(license.read_bytes()).hexdigest(),face_index=0,byte_count=len(source.read_bytes())))
            self.assertNotIn(root,json.dumps(value));self.assertEqual(source.read_bytes(),geometric_font())

    def test_delivery_orientation_density_scale_and_profile_policy_match_actual_bytes(self):
        d=self.annotated('raster');d=self.edit(d,[dict(op='output_profile',profile=profiles.builtin('display_p3'))])
        for scale in (1,2,4):
            for format,extract in [('png',profiles.png_profile),('jpeg',profiles.jpeg_profile),('tiff',profiles.tiff_profile)]:
                data=self.data(d,format,scale=scale,metadata_policy=dict(mode='strip',provenance=True));packet=json.loads(carrier(data,format));delivery=packet['delivery'];self.assertIsNone(packet['document']);self.assertEqual(packet['items'],{})
                self.assertEqual([delivery['width'],delivery['height']],[16*scale,8*scale]);self.assertEqual(delivery['orientation'],'top_left');self.assertEqual(delivery['profile']['icc_sha256'],hashlib.sha256(extract(data)).hexdigest())
                if format=='png':
                    _,_,_,chunks=editing.png_pixels(data);x,y,unit=struct.unpack('>IIB',chunks[b'pHYs']);self.assertEqual(x,y);self.assertEqual(unit,1);actual=x*.0254
                elif format=='tiff':
                    tags=images.tiff_tags(data);self.assertEqual(tags[274],(1,));self.assertEqual(tags[296],(2,));actual=tags[282][0]/tags[282][1]
                else:
                    app0=next(payload for marker,payload in images.jpeg_segments(data) if marker==224);self.assertEqual(app0[:5],b'JFIF\0');self.assertEqual(app0[7],1);x,y=struct.unpack('>HH',app0[8:12]);self.assertEqual(x,y);actual=x
                self.assertAlmostEqual(actual,delivery['resolution_ppi'],places=9)
        # Orientation metadata is never silently reapplied during import.
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'rotated.tiff';source.write_bytes(images.tiff_fixture(1,1,bytes([0,0,0,255]),tags={274:(3,[6])}));store=Path(root)/'store'
            self.assertEqual(self.invoke(dict(command='asset.import',source_path=str(source),store_root=str(store),color_policy='assume_srgb'),1)['code'],'UNSUPPORTED');self.assertFalse(store.exists())

    def test_svg_unknown_nested_or_malformed_metadata_is_explicit(self):
        data=self.data(self.annotated(),'svg').decode();root=ET.fromstring(data);metadata=root.find('{http://www.w3.org/2000/svg}metadata');group=ET.Element('{http://www.w3.org/2000/svg}g');root.remove(metadata);group.append(metadata);root.append(group)
        nested=ET.tostring(root,encoding='unicode')
        for text in [nested,data.replace('urn:inkbolt:metadata:1','urn:unknown:metadata'),data.replace('<metadata>','<metadata>unexpected text')]:
            self.assertIn(self.invoke(dict(command='svg.import',id='bad',source=dict(kind='text',text=text)),1)['code'],['SVG_INVALID','SVG_UNSUPPORTED'])


if __name__=='__main__':unittest.main()
