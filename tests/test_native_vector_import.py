"""Independent source framing, editable geometry, pixels, rejection and history."""
import base64
from contextlib import closing
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zlib

import native_vector_fixture as fixture
import test_boards_cli as boards
from test_editing_cli import png_pixels
from test_mcp import Client


class NativeVectorImport(unittest.TestCase):
    invoke = boards.BoardCliTests.invoke
    edit = boards.BoardCliTests.edit
    exports = boards.BoardCliTests.exports

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.serial = 0

    def read(self, data=None, expected=0, **options):
        self.serial += 1
        path = self.root / f'source-{self.serial}.vector'
        data = fixture.source() if data is None else data
        path.write_bytes(data)
        before = set(self.root.iterdir())
        result = self.invoke(dict(command='vector.import', id='native', source_path=str(path),
                                  color_policy='encoded_srgb', **options), expected)
        self.assertEqual(path.read_bytes(), data)
        self.assertEqual(set(self.root.iterdir()), before)
        if not expected:
            self.assertEqual(result['source']['sha256'], hashlib.sha256(data).hexdigest())
            self.assertFalse(result['source']['modified'])
            self.assertEqual(len(result['losses']), 4)
        return result

    def pixels(self, document, visible=True, opacity=1):
        rows = self.exports(document)['artifacts']
        self.assertEqual([r['name'] for r in rows], ['first','detail'])
        for index, row in enumerate(rows):
            w,h,p,_ = png_pixels(base64.b64decode(row['artifact']['data']))
            self.assertEqual((w,h), [(12,8),(8,6)][index])
            for y in range(h):
                for x in range(w):
                    if index == 0:
                        hit = visible and 2 <= x < 8 and 2 <= y < 6
                        color = [round(255*opacity),0,round(255*(1-opacity)),255] if hit else [0,0,255,255]
                    else:
                        color = [0,255,0,255] if 2 <= x < 6 and 1 <= y < 4 else [0,0,0,0]
                    # At half opacity either neighboring byte is valid under the existing
                    # engine's final rounding; geometry and opaque coverage are exact.
                    actual = p[(y*w+x)*4:(y*w+x+1)*4]
                    tolerance = 1 if index == 0 and hit and opacity == .5 else 0
                    self.assertTrue(all(abs(a-b)<=tolerance for a,b in zip(actual,color)), (index,x,y,actual,color))

    def test_direct_geometry_and_every_pixel_use_native_data_not_preview(self):
        result = self.read()
        d = result['document']
        self.assertEqual(result['counts'], dict(artboards=2,layers=2,paths=3))
        self.assertEqual(result['source']['preview_pages'], 1)
        self.assertEqual((d['width'],d['height'],d['resolution_ppi']), (24,8,72))
        self.assertEqual(result['mapping']['source_to_document'], [1,0,0,-1,4,12])
        items = {i['id']:i for i in d['items']}
        self.assertEqual(items['board-1']['transform'], [1,0,0,1,16,2])
        self.assertEqual(items['board-1']['content']['frame']['scope'], 'scene')
        self.assertEqual(items['path-2']['parent'], 'layer-1')
        self.assertEqual(items['path-2']['content']['geometry']['commands'], [
            dict(verb='move',to=[-2,10]),dict(verb='line',to=[4,10]),
            dict(verb='line',to=[4,6]),dict(verb='line',to=[-2,6]),dict(verb='close')])
        self.pixels(d)

    def test_raw_zstandard_flate_many_blocks_indirect_lengths_and_name_escapes_agree(self):
        original = self.read()['document']
        for compressed,flate,indirect,pieces in [(True,False,False,1),(False,True,False,1),
                                                (True,True,True,12),(False,False,True,12)]:
            with self.subTest(compressed=compressed,flate=flate,indirect=indirect,pieces=pieces):
                objects = fixture.objects(compressed=compressed,flate=flate,indirect_length=indirect,pieces=pieces)
                objects[3] = objects[3].replace(b'/PieceInfo', b'/Piece#49nfo')
                result = self.read(fixture.pdf(objects))
                self.assertEqual(result['document'], original)
                self.assertEqual(result['source']['blocks'], pieces)
                self.assertEqual(result['source']['compression'], 'zstandard' if compressed else 'none')

    def test_curve_handles_visibility_locks_and_opacity_are_editable(self):
        result = self.read(fixture.source(data=fixture.artwork(curve=True, locked=True, board_locked=True)))
        items = {i['id']:i for i in result['document']['items']}
        self.assertEqual(items['path-2']['content']['geometry']['commands'][1],
                         dict(verb='cubic',control1=[0,11],control2=[2,11],to=[4,10]))
        self.assertTrue(items['path-2']['locked']); self.assertTrue(items['board-1']['locked'])
        error = self.edit(result['document'], [dict(op='transform',id='path-2',matrix=[1,0,0,1,1,0])], 1)
        self.assertEqual(error['code'], 'LOCKED')
        for options in [dict(visible=False),dict(layer_visible=False),dict(opacity=.5),dict(layer_locked=True)]:
            d = self.read(fixture.source(data=fixture.artwork(**options)))['document']
            self.pixels(d, visible=options.get('visible',True) and options.get('layer_visible',True), opacity=options.get('opacity',1))
            if options.get('layer_locked'):
                self.assertTrue(next(i for i in d['items'] if i['id']=='layer-1')['locked'])

    def test_saved_revision_retry_undo_and_create_only_delivery_preserve_sources(self):
        d = self.read()['document']
        original = copy.deepcopy(d)
        saved = self.invoke(dict(command='document.export', document=d, format='snapshot'))['data']
        self.assertEqual(self.invoke(dict(command='document.validate', document=json.loads(saved))), d)
        session = dict(session_root=str(self.root), session_id='native-history')
        self.invoke(dict(command='session.create', request_id='create', document=d, **session))
        request = dict(command='session.apply', request_id='hide', expected_revision=0, **session,
                       action=dict(type='edit',operations=[dict(op='properties',id='path-2',visible=False)]))
        changed = self.invoke(request)
        again = self.invoke(request)
        self.assertTrue(again['replayed']); self.assertEqual(again['document'],changed['document'])
        self.pixels(changed['document'], visible=False)
        restored = self.invoke(dict(command='session.apply',request_id='undo',expected_revision=1,
                                    action=dict(type='undo'),**session))['document']
        self.assertEqual(restored['items'], original['items']); self.pixels(restored)
        output = dict(output_root=str(self.root),file_name='delivered.svg',format='svg')
        request = dict(command='document.publish',document=d,output=output)
        published = self.invoke(request)
        before = Path(published['path']).read_bytes()
        self.assertEqual(self.invoke(request,1)['code'], 'OUTPUT_EXISTS')
        self.assertEqual(Path(published['path']).read_bytes(),before)
        self.assertEqual(d,original)

    def test_compression_checksum_completion_declared_size_and_trailing_data(self):
        data = fixture.artwork()
        frame = fixture.zstandard_raw(data)
        variants = [frame[:-1], frame+b'extra', frame+frame,
                    fixture.zstandard_raw(data,declared=len(data)+1),
                    fixture.zstandard_raw(data,declared=len(data)-1),
                    fixture.zstandard_raw(data,checksum=0)]
        for encoded in variants:
            with self.subTest(size=len(encoded)):
                error = self.read(fixture.source(data=data,compressed=True,encoded=b'%AI24_ZStandard_Data'+encoded),1)
                self.assertEqual(error['code'], 'INVALID_VECTOR_SOURCE')
        for raw in [zlib.compress(data)[:-1],zlib.compress(data)+b'extra',zlib.compress(data)[:-1]+b'\0']:
            objects = fixture.objects()
            objects[7] = f'<< /Length {len(raw)} /Filter /FlateDecode >>\nstream\n'.encode()+raw+b'\nendstream'
            self.assertEqual(self.read(fixture.pdf(objects),1)['code'], 'INVALID_VECTOR_SOURCE')

    def test_container_framing_duplicate_fields_refs_and_wrong_metadata_fail(self):
        cases = []
        for obj,old,new in [(2,b'/Count 1',b'/Count 2'),(2,b'[3 0 R]',b'[2 0 R]'),
                            (3,b'/Private 5 0 R',b'/Private 99 0 R'),
                            (5,b'/NumBlock 1',b'/NumBlock 1 /NumBlock 1'),
                            (5,b'/AIPrivateData1 7 0 R',b'/AIPrivateData1 4 0 R'),
                            (7,b'/Length ',b'/Length 1 /Unused '),
                            (1,b'/Pages 2 0 R',b'/Pages 1 0 R')]:
            objects = fixture.objects(); objects[obj] = objects[obj].replace(old,new)
            cases.append(fixture.pdf(objects))
        cases += [fixture.source(metadata=b'wrong header'),fixture.pdf(fixture.objects(),xref_delta=1),fixture.source()+b'trailing']
        for data in cases:
            with self.subTest(digest=hashlib.sha256(data).hexdigest()[:10]):
                self.read(data,1)

    def test_unknown_versions_encryption_and_ambiguous_editable_containers_fail(self):
        cases = [fixture.source(creator=31),fixture.pdf(fixture.objects(),trailer_extra=b'/Encrypt 1 0 R '),
                 fixture.pdf(fixture.objects(),trailer_extra=b'/Prev 0 ')]
        objects = fixture.objects(); objects[8] = objects[5]
        objects[3] = objects[3].replace(b'/PieceInfo <<',b'/PieceInfo << /Other << /Private 8 0 R >>')
        cases.append(fixture.pdf(objects))
        for obj,old,new in [(5,b'/ContainerVersion 12',b'/ContainerVersion 13'),
                            (5,b'/RoundtripVersion 24',b'/RoundtripVersion 25'),
                            (5,b'/NumBlock 1',b'/NumBlock 1 /FutureFeature true')]:
            objects = fixture.objects(); objects[obj] = objects[obj].replace(old,new)
            cases.append(fixture.pdf(objects))
        for data in cases:
            self.assertEqual(self.read(data,1)['code'], 'UNSUPPORTED')

    def test_unsupported_artwork_is_rejected_without_partial_document(self):
        data = fixture.artwork()
        cases = [(b'0 O', b'1 O'),(b'0 XR',b'1 XR'),(b'\nf\n',b'\nS\n'),
                 (b'0 1 0 0 0 Xy',b'0 1 1 0 0 Xy'),(b'0 /Real (BleedTopValue)',b'1 /Real (BleedTopValue)'),
                 (b'%AI9_ColorModel: 1',b'%AI9_ColorModel: 2'),(b'%AI24_LargeCanvasScale: 1',b'%AI24_LargeCanvasScale: 10'),
                 (b'1 0 0 Xa',b'.123 0 0 Xa'),(b'(overlay)',b'(ov\\351rlay)'),
                 (b'%%EndProlog',b'1 0 translate\n%%EndProlog'),
                 (b'\nLB\n',b'\nunknownPaintingOperator\nLB\n')]
        for old,new in cases:
            with self.subTest(old=old):
                self.assertIn(old,data)
                error = self.read(fixture.source(data=data.replace(old,new)),1)
                self.assertEqual(error['code'], 'UNSUPPORTED')
                self.assertNotIn('document',error)

    def test_syntax_damage_string_escaping_and_resource_bounds(self):
        data = fixture.artwork().replace(b'(overlay)',b'(over_x28_lay_x29__name)')
        d = self.read(fixture.source(data=data))['document']
        self.assertEqual(next(i for i in d['items'] if i['id']=='path-2')['name'], 'over(lay) name')
        for old,new in [(b'(ArtboardArray) ,',b'(ArtboardArray)'),(b'/Array :',b'/Array '),
                         (b'%%EndSetup',b'%%EndProlog\n%%EndSetup'),(b'4 10 L',b'NaN 10 L'),
                         (b'0 /Bool (IsArtboardSelected)',b'2 /Bool (IsArtboardSelected)')]:
            self.read(fixture.source(data=fixture.artwork().replace(old,new)),1)
        self.assertEqual(self.read(b'x'*(16*1024*1024+1),1)['code'], 'RESOURCE_LIMIT')
        objects = fixture.objects(); objects[5] = objects[5].replace(b'/NumBlock 1',b'/NumBlock 257')
        self.assertEqual(self.read(fixture.pdf(objects),1)['code'], 'RESOURCE_LIMIT')
        self.assertEqual(self.read(expected=1,resource_profile='large_raster')['code'], 'INVALID_REQUEST')

    def test_cli_mcp_workspace_discovery_and_required_color_policy(self):
        path = self.root/'native.vector'; path.write_bytes(fixture.source())
        args = dict(id='native',source_path=str(path),color_policy='encoded_srgb')
        cli = self.invoke(dict(command='vector.import',**args))
        with closing(Client(('--tools','core'),workspace=self.root)) as client:
            client.initialize()
            response = client.tool('run',command='vector.import',arguments={**args,'source_path':'native.vector'})
            self.assertFalse(response['isError'],response)
            self.assertEqual(response['structuredContent']['result'],cli)
            schema = client.success('schema.lookup',name='vector.import')['schema']
            self.assertIn('color_policy',schema['required'])
            cap = client.tool('run',command='capabilities',arguments={})['structuredContent']['result']
            self.assertIn('vector.import',cap['commands'])
            self.assertEqual(cap['native_vector_import']['native_delivery'],'native_vector_subset')
            del args['color_policy']
            failed = client.tool('run',command='vector.import',arguments=args)
            self.assertEqual(failed['structuredContent']['error']['code'],'INVALID_REQUEST')


if __name__ == '__main__':
    unittest.main()
