"""Reopen painted labels with a licensed font and verify their editable geometry."""
import base64
from contextlib import closing
import hashlib
import itertools
import unittest

from native_vector_fixture import pdf
from test_mcp import Client
from test_pdf_import import page_objects, stream
import test_pdf_searchable as searchable


def character_map(rows):
    return (b'/CIDInit /ProcSet findresource begin 12 dict begin begincmap '
            b'/CIDSystemInfo << /Registry (Inkbolt) /Ordering (Fixture) /Supplement 0 >> def '
            b'/CMapName /Fixture def /CMapType 2 def '
            b'1 begincodespacerange <0000> <FFFF> endcodespacerange ' + rows +
            b' endcmap CMapName currentdict /CMap defineresource pop end end')


def label_objects(font, show=b'<00020003> Tj', rows=b'1 beginbfrange <0002> <0003> <0041> endbfrange'):
    objects = page_objects(
        b'0 1 0 rg 32 2 10 7 re f q 0 0 1 rg BT /F 10 Tf 1 0 0 1 4 24 Tm ' + show + b' ET Q',
        resources=b'<< /Font << /F 5 0 R >> >>')
    objects.update({
        5: b'<< /Type /Font /Subtype /Type0 /BaseFont /Fixture /Encoding /Identity-H '
           b'/DescendantFonts [6 0 R] /ToUnicode 9 0 R >>',
        6: b'<< /Type /Font /Subtype /CIDFontType2 /BaseFont /Fixture '
           b'/CIDSystemInfo << /Registry (Inkbolt) /Ordering (Fixture) /Supplement 0 >> '
           b'/FontDescriptor 7 0 R /CIDToGIDMap /Identity /W [2 [600 650]] >>',
        7: b'<< /Type /FontDescriptor /FontName /Fixture /Flags 4 /FontFile2 8 0 R >>',
        8: stream(font, compress=True),
        9: stream(character_map(rows)),
    })
    return objects


class EditablePdfText(unittest.TestCase):
    setUp = searchable.SearchablePdfTests.setUp
    install = searchable.SearchablePdfTests.install
    invoke = searchable.SearchablePdfTests.invoke
    document = searchable.SearchablePdfTests.document
    edit = searchable.SearchablePdfTests.edit
    export = searchable.SearchablePdfTests.export

    def open(self, data, expected=0, **kwargs):
        path = self.directory / 'label.pdf'
        path.write_bytes(data)
        result = self.invoke(dict(command='pdf.import', id='reopened', source_path=str(path),
                                  color_policy='encoded_srgb', **kwargs), expected)
        self.assertEqual(path.read_bytes(), data)
        return result

    def bind(self, data):
        error = self.open(data, 1)
        self.assertEqual(error['code'], 'PDF_FONT_NOT_BOUND')
        self.assertIn('decoded_byte_offset', error['details'])
        return dict(font_root=str(self.store), font_bindings=[
            dict(embedded_sha256=error['details']['embedded_sha256'], font_id='local', font=self.font)])

    def test_named_and_cid_compact_and_truetype_whole_and_subset(self):
        for cff, permissions in itertools.product((False, True), (8, 0x108)):
            with self.subTest(cff=cff, permissions=permissions):
                source = searchable.font_bytes(cff, permissions)
                self.install(source)
                original = self.document(text='AB fi', wrap=False)
                original['resolution_ppi'] = 72
                data = base64.b64decode(self.export(original, 'require_searchable')['data'])
                options = self.bind(data)
                receipt = self.open(data, **options)
                doc = receipt['document']
                frames = [i['content']['frame'] for i in doc['items'] if i['content']['type'] == 'text']
                self.assertEqual([f['text'] for f in frames], ['A', 'B', ' ', 'fi'])
                self.assertEqual(doc['fonts'], {'local': self.font})
                info, = receipt['font_sources']
                self.assertEqual(info['font_id'], 'local')
                self.assertEqual(info['embedded_sha256'] == hashlib.sha256(source).hexdigest(), permissions == 0x108)
                render = lambda d: self.invoke(dict(command='document.render', document=d, font_root=str(self.store)))['data']
                self.assertEqual(render(original), render(doc))
                self.assertEqual(self.source.read_bytes(), source)

    def test_revise_one_contiguous_label_via_workspace(self):
        font = searchable.font_bytes()
        self.install(font)
        data = pdf(label_objects(font))
        opts = self.bind(data)
        opts['font_root'] = 'fonts'
        with closing(Client(workspace=self.directory)) as client:
            client.initialize()
            receipt = client.success('pdf.import', id='reopened', source_path='label.pdf',
                                     color_policy='encoded_srgb', **opts)
        doc = receipt['document']
        label, = [i for i in doc['items'] if i['content']['type'] == 'text']
        self.assertEqual(label['content']['frame']['text'], 'AB')
        changed = self.edit(doc, [dict(op='text_range', id=label['id'], start=0, end=2, text='BA')])
        reference = self.open(pdf(label_objects(font, b'<00030002> Tj')), **{**opts, 'font_root': str(self.store)})['document']
        other = lambda d: [i for i in d['items'] if i['id'] != label['id']]
        self.assertEqual(other(doc), other(changed))
        comparable = lambda d: self.invoke(dict(command='document.render', document=d, font_root=str(self.store)))['data']
        self.assertNotEqual(comparable(doc), comparable(changed))
        self.assertEqual(comparable(changed), comparable(reference))
        self.assertGreater(self.export(changed, 'require_searchable')['pdf']['text_delivery']['embedded_font_programs'], 0)

    def test_line_matrices_and_consecutive_strings(self):
        font = searchable.font_bytes()
        self.install(font)
        show = br'(\000\002) Tj <0003> Tj 0 -12 TD <0002> Tj T* <0003> Tj'
        data = pdf(label_objects(font, show))
        doc = self.open(data, **self.bind(data))['document']
        labels = [i for i in doc['items'] if i['content']['type'] == 'text']
        self.assertEqual([i['content']['frame']['text'] for i in labels], list('ABAB'))
        positions = [i['transform'][4:] for i in labels]
        x, y = positions[0]
        self.assertEqual(positions[1:], [[x+6, y], [x, y+12], [x, y+24]])

    def test_rejects_wrong_width_glyph_unicode_and_unimplemented_text_state(self):
        font = searchable.font_bytes()
        self.install(font)
        opts = self.bind(pdf(label_objects(font)))
        for show, rows, edit_width in [
            (b'<00020003> Tj', b'2 beginbfchar <0002> <0041> <0003> <0042> endbfchar', True),
            (b'<0002> Tj', b'1 beginbfchar <0002> <0042> endbfchar', False),
            (b'<0003> Tj', b'1 beginbfchar <0002> <0041> endbfchar', False),
            (b'<0002> Tj', b'1 beginbfchar <0002> <D800> endbfchar', False),
            (b'<0002> Tj', b'2 beginbfchar <0002> <0041> <0002> <0041> endbfchar', False),
            (b'1 Tr <0002> Tj', b'1 beginbfchar <0002> <0041> endbfchar', False),
        ]:
            with self.subTest(show=show, rows=rows, width=edit_width):
                objects = label_objects(font, show, rows)
                if edit_width:
                    objects[6] = objects[6].replace(b'600 650', b'601 649')
                error = self.open(pdf(objects), 1, **opts)
                self.assertIn(error['code'], ('UNSUPPORTED', 'INVALID_PDF'))
                self.assertEqual(error['details']['object'], 4)

    def test_checks_painted_outlines_and_bound_file_identity(self):
        font = searchable.font_bytes()
        self.install(font)
        objects = label_objects(font, b'<0002> Tj')
        data = pdf(objects)
        opts = self.bind(data)
        objects[6] = objects[6].replace(b'/CIDToGIDMap /Identity', b'/CIDToGIDMap 10 0 R')
        objects[10] = stream(bytes([0, 0, 0, 0, 0, 7]))
        mismatch = self.open(pdf(objects), 1, **opts)
        self.assertEqual(mismatch['code'], 'UNSUPPORTED')
        self.assertIn('outline', mismatch['message'].lower())
        pinned, = opts['font_bindings']
        changed = dict(pinned, embedded_sha256='0'*64)
        error = self.open(data, 1, **{**opts, 'font_bindings':[changed]})
        self.assertEqual(error['details']['embedded_sha256'], hashlib.sha256(font).hexdigest())
        duplicate = self.open(data, 1, **{**opts, 'font_bindings':[pinned, pinned]})
        self.assertEqual(duplicate['code'], 'INVALID_PDF')

    def test_declines_color_font_program_even_if_a_plain_outline_is_present(self):
        tables = searchable.tables(searchable.font_bytes())
        tables[b'COLR'] = bytes(14)
        source = pdf(label_objects(searchable.sfnt(tables)))
        error = self.open(source, 1)
        self.assertEqual(error['code'], 'UNSUPPORTED')
        self.assertEqual(error['details']['object'], 4)
