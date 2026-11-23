"""Editable PDF page graphics, located refusals and immutable sources."""
import base64
from contextlib import closing
import hashlib
from pathlib import Path
import tempfile
import unittest
import zlib

from native_vector_fixture import pdf
import test_boards_cli as boards
from test_mcp import Client


def stream(data, fields=b'', compress=False):
    if compress:
        data = zlib.compress(data)
        fields += b' /Filter /FlateDecode'
    return b'<< ' + fields + b' /Length %d >>\nstream\n' % len(data) + data + b'\nendstream'


def page_objects(contents, *, fields=b'', resources=b'<< >>'):
    return {
        1: b'<< /Type /Catalog /Pages 2 0 R >>',
        2: b'<< /Type /Pages /Kids [3 0 R] /Count 1 /MediaBox [0 0 48 40] /Resources ' + resources + b' >>',
        3: b'<< /Type /Page /Parent 2 0 R /Contents 4 0 R ' + fields + b' >>',
        4: stream(contents),
    }


class EditablePdfPage(unittest.TestCase):
    invoke = boards.BoardCliTests.invoke
    edit = boards.BoardCliTests.edit
    rectangle = boards.BoardCliTests.rectangle

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.source = Path(temp.name) / 'artwork.pdf'

    def read(self, data, expected=0, **changes):
        self.source.write_bytes(data)
        request = dict(command='pdf.import', id='reopened', source_path=str(self.source), color_policy='encoded_srgb')
        result = self.invoke({**request, **changes}, expected)
        self.assertEqual(self.source.read_bytes(), data)
        if expected == 0:
            self.assertEqual(result['source']['sha256'], hashlib.sha256(data).hexdigest())
        return result

    def rgba(self, doc, scale=1):
        return bytes.fromhex(self.invoke(dict(command='document.render', document=doc, scale=scale))['data'])

    def test_published_curves_opacity_and_an_edit_recover_all_samples(self):
        original = self.invoke(dict(command='document.create', id='paths', kind='vector', width=64, height=48))
        original['resolution_ppi'] = 72
        first = self.rectangle('rectangle', None, 'vector', 4, 8, 20, 18, [217,42,81,255])
        last = dict(id='curve', transform=[1,.25,-.5,1,25,7], content=dict(type='vector',fill=[24,145,212,128],
                    fill_rule='even_odd', geometry=dict(shape='path',commands=[dict(verb='move',to=[0,0]),
                    dict(verb='cubic',control1=[2,12],control2=[16,9],to=[15,2]),dict(verb='line',to=[10,18]),dict(verb='close')])))
        original['items'] = [first, last]
        data = base64.b64decode(self.invoke(dict(command='document.export', document=original, format='pdf'))['data'])
        result = self.read(data)
        doc = result['document']
        shapes = [i for i in doc['items'] if i['content']['type']=='vector']
        self.assertEqual(len(shapes), 2)
        self.assertEqual(shapes[1]['content']['geometry']['commands'][1],
                         dict(verb='cubic', control1=[21,19.5], control2=[36.5,20], to=[39,12.75]))
        self.assertEqual(shapes[1]['content']['fill_rule'], 'even_odd')
        self.assertEqual({m['item_id'] for m in result['mapping']}, {i['id'] for i in doc['items']})
        self.assertTrue(result['losses'])
        for scale in [1,2]:
            self.assertEqual(self.rgba(doc, scale), self.rgba(original, scale))
        edited = self.edit(doc,[dict(op='fill', id=shapes[1]['id'], paint=[200,63,12,240])])
        last['content']['fill'] = [200,63,12,240]
        self.assertEqual(self.rgba(edited,2), self.rgba(original,2))
        self.assertNotEqual(self.rgba(doc), self.rgba(edited))

    def test_independent_page_program_form_clips_resource_scope_and_stack(self):
        # Opaque blue paper and two fills inside one half-opacity isolated group.
        # Group opacity applies once across the overlap. Its BBox clips each side.
        objects = page_objects(b'0 0 1 rg 0 0 48 40 re f q /Fade gs 1 0 0 1 4 5 cm /A Do Q',
                               resources=b'<< /ExtGState << /Fade 6 0 R >> /XObject << /A 5 0 R >> >>')
        objects[5] = stream(b'1 0 0 rg -10 -10 40 40 re f 0 1 0 rg 10 0 20 10 re f',
                            b'/Type /XObject /Subtype /Form /BBox [0 0 20 10] /Resources << >> '
                            b'/Group << /S /Transparency /I true /CS /DeviceRGB >>', True)
        objects[6] = b'<< /ca .5 >>'
        result = self.read(pdf(objects))
        rgba = self.rgba(result['document'])
        pixel = lambda x,y: tuple(rgba[4*(48*y+x):4*(48*y+x+1)])
        self.assertEqual(pixel(2,30), (0,0,255,255))
        self.assertEqual(pixel(26,30), (0,0,255,255))
        for x, channels in [(7,(128,0,127)),(18,(0,128,127))]:
            self.assertTrue(all(abs(a-b)<=1 for a,b in zip(pixel(x,30),channels)),pixel(x,30))
        objects[4] = stream(b'q 4 4 6 8 re W n 0 g 0 0 48 40 re f Q 1 g 1 1 1 1 re f')
        clipped = self.rgba(self.read(pdf(objects))['document'])
        opaque = {(i%48,i//48) for i,x in enumerate(clipped[3::4]) if x}
        self.assertEqual(opaque, {(x,y) for x in range(4,10) for y in range(28,36)}|{(1,38)})

    def test_rotated_second_page_inherited_crop_units_and_content_array(self):
        objects=page_objects(b'BT')
        objects[2]=b'<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 /MediaBox [10 20 40 50] /Resources << >> >>'
        objects[5]=b'<< /Type /Page /Parent 2 0 R /CropBox [12 22 24 42] /Rotate 90 /UserUnit 2 /Contents 8 0 R >>'
        objects[6]=stream(b'q % joined state\n 0.25 g 12 22 m 16 22 l')
        objects[7]=stream(b'16 25 l 12 25 l h f Q',compress=True)
        objects[8]=b'[6 0 R 7 0 R]'
        data=pdf(objects)
        result=self.read(data,page_index=1)
        self.assertEqual(result['source']['pages'],2)
        self.assertEqual(result['page']['source_to_document'],[0,2,2,0,-44,-24])
        doc=result['document']
        self.assertEqual((doc['width'],doc['height']),(40,24))
        rgba=self.rgba(doc)
        self.assertEqual(sum(v!=0 for v in rgba[3::4]),6*8)
        self.assertEqual(rgba[:4],bytes([64,64,64,255]))
        self.assertEqual(result['mapping'][-1]['object'],7)
        self.assertEqual(self.read(data,1,page_index=2)['code'],'INVALID_REQUEST')

    def test_refusals_identify_page_stream_and_decoded_offset(self):
        for suffix in [b'BT',b'/Missing Do',b'Q',b'1 2 m S',b'0 1 0 0 k',b'notAnOperator']:
            with self.subTest(suffix=suffix):
                data=pdf(page_objects(b'0 g 1 2 3 4 re f '+suffix))
                error=self.read(data,1)
                self.assertEqual(error['details']['page_index'],0)
                self.assertEqual(error['details']['object'],4)
                self.assertGreaterEqual(error['details']['decoded_byte_offset'],16)
        for fields in [b'/Annots [9 0 R]', b'/Rotate 45']:
            self.assertEqual(self.read(pdf(page_objects(b'', fields=fields)),1)['details']['object'],3)
        objects=page_objects(b'/Loop Do',resources=b'<< /XObject << /Loop 5 0 R >> >>')
        objects[5]=stream(b'/Loop Do',b'/Subtype /Form /BBox [0 0 5 5]')
        self.assertEqual(self.read(pdf(objects),1)['code'],'RESOURCE_LIMIT')

    def test_fractional_crop_persists_across_canvas_pixel_rounding(self):
        for use_form in (False, True):
            contents = b'0 0 4.5 5 re W n 0 0 4.5 5 re W n 0 g 0 0 48 40 re f'
            objects = page_objects(b'/A Do' if use_form else contents,
                                   fields=b'/CropBox [0 0 4.5 5]',
                                   resources=b'<< /XObject << /A 5 0 R >> >>' if use_form else b'<< >>')
            if use_form:
                objects[5] = stream(contents, b'/Subtype /Form /BBox [0 0 4.5 5]')
            doc = self.read(pdf(objects))['document']
            self.assertEqual(doc['vector_canvas']['size_px'], [4.5,5])
            pixels = self.rgba(doc)
            for y in range(5):
                self.assertEqual(pixels[4*5*y+3:4*5*(y+1):4], bytes([255]*4+[128]))
            self.assertEqual(self.rgba(doc,2)[3::4], bytes([255])*(9*10))

    def test_reused_form_resolves_each_invocations_color_and_resources(self):
        objects = page_objects(b'q /A Do Q 1 0 0 1 12 0 cm /B Do',
                               resources=b'<< /XObject << /A 5 0 R /B 6 0 R >> >>')
        for object_id, state_id, color in [(5,8,b'1 0 0'), (6,9,b'0 0 1')]:
            fields = b'/Subtype /Form /BBox [0 0 10 10] /Resources << /ExtGState << /Fade %d 0 R >> /XObject << /Mark 7 0 R >> >>' % state_id
            objects[object_id] = stream(color+b' rg /Mark Do',fields)
        objects[7] = stream(b'/Fade gs 0 0 10 10 re f', b'/Subtype /Form /BBox [0 0 10 10]')
        objects[8], objects[9] = b'<< /ca .25 >>', b'<< /ca .75 >>'
        result = self.read(pdf(objects))
        pixels = self.rgba(result['document'])
        def at(x):
            i = 4*(48*36+x)
            return tuple(pixels[i:i+4])
        self.assertEqual(at(5), (255,0,0,64))
        self.assertEqual(at(16), (0,0,255,191))
        occurrences = [m for m in result['mapping'] if m['object']==7]
        self.assertEqual(len({m['item_id'] for m in occurrences}),2)

    def test_session_retry_undo_and_new_pdf_publication(self):
        data=pdf(page_objects(b'1 0 0 rg 1 2 3 4 re f'))
        result=self.read(data)
        original=result['document']
        item=result['mapping'][-1]['item_id']
        session=dict(session_root=str(self.source.parent/'sessions'),session_id='page')
        self.invoke(dict(command='session.create',request_id='open',document=original,**session))
        request=dict(command='session.apply',request_id='color',expected_revision=0,**session,
                     action=dict(type='edit',operations=[dict(op='fill',id=item,paint=[0,0,160,255])]))
        edited=self.invoke(request)['document']
        self.assertTrue(self.invoke(request)['replayed'])
        publish=dict(command='document.publish',document=edited,output=dict(
            output_root=str(self.source.parent),file_name='edited.pdf',format='pdf'))
        saved=Path(self.invoke(publish)['path']).read_bytes()
        self.assertEqual(self.invoke(publish,1)['code'],'OUTPUT_EXISTS')
        self.assertEqual(self.source.read_bytes(),data)
        again=self.invoke(dict(command='pdf.import',id='again',source_path=str(self.source.parent/'edited.pdf'),
                               color_policy='encoded_srgb'))['document']
        self.assertEqual(self.rgba(again),self.rgba(edited))
        undo=self.invoke(dict(command='session.apply',request_id='undo',expected_revision=1,
                              action=dict(type='undo'),**session))['document']
        self.assertEqual(self.rgba(undo),self.rgba(original))
        self.assertNotEqual(self.rgba(undo),self.rgba(edited))
        self.assertEqual((self.source.parent/'edited.pdf').read_bytes(),saved)

    def test_cli_and_mcp_reopen_the_same_workspace_file(self):
        result=self.read(pdf(page_objects(b'1 0 0 rg 1 2 3 4 re f')))
        with closing(Client(('--tools','essentials'),workspace=self.source.parent)) as client:
            client.initialize()
            schema=client.success('schema.lookup',name='pdf.import')['schema']
            self.assertIn('color_policy',schema['required'])
            response=client.tool('run',command='pdf.import',arguments=dict(id='reopened',source_path=self.source.name,color_policy='encoded_srgb'))
            self.assertFalse(response['isError'],response)
            self.assertEqual(response['structuredContent']['result'],result)
