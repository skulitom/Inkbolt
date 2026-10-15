"""Original repeated shapes with analytic placement, pixel and failure oracles."""
import copy
import tempfile
import unittest
import test_svg_import_cli as svg_support
from test_mcp import Client


class SvgReuseTests(unittest.TestCase):
    invoke = svg_support.SvgImportTests.invoke
    imported = svg_support.SvgImportTests.imported
    pixels = svg_support.SvgImportTests.pixels

    def assert_pixels(self, result, paint):
        width, height, pixels = self.pixels(result['document'])
        self.assertEqual(pixels, b''.join(bytes(paint(x, y)) for y in range(height) for x in range(width)))

    def test_forward_references_inherit_each_placement_not_definition_parent(self):
        text = svg_support.svg('<use id="red" href="#tile" fill="red"/>'
            '<use id="blue" href="#tile" x="6" fill="blue"/>'
            '<defs fill="lime"><rect id="tile" width="4" height="3"/></defs>')
        result = self.imported(text)
        self.assert_pixels(result, lambda x, y: [255, 0, 0, 255] if x < 4 and y < 3 else
                           [0, 0, 255, 255] if 6 <= x < 10 and y < 3 else [0, 0, 0, 0])
        rows = [r for r in result['mapping'] if r['source_id'] == 'tile']
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]['item_id'], rows[1]['item_id'])
        self.assertEqual([r['instance_path'][0]['source_id'] for r in rows], ['red', 'blue'])
        self.assertEqual([r['byte_offset'] for r in rows], [text.index('<rect')] * 2)
        self.assertTrue(any('independent editable groups' in loss for loss in result['losses']))

    def test_css_current_color_transform_order_and_ignored_shape_dimensions(self):
        text = svg_support.svg('<style>.shape{fill:currentColor}use{color:#123456}</style>'
            '<defs><g id="tile" transform="translate(1,1)"><rect class="shape" width="2" height="2"/></g></defs>'
            '<use href="#tile" x="25%" y="2" width="1" height="100" transform="scale(2)" opacity=".5"/>')
        # T(scale 2) * T(use 8,2) * T(source 1,1): rectangle [18,6,22,10].
        self.assert_pixels(self.imported(text), lambda x, y: [18, 52, 86, 128]
                           if 18 <= x < 22 and 6 <= y < 10 else [0, 0, 0, 0])

    def test_nested_references_legacy_href_and_original_artwork(self):
        text = '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="32" height="24">'
        text += '<g fill="red"><rect id="square" width="2" height="2"/></g>'
        text += '<defs><g id="icon"><use href="#square" x="1"/></g></defs>'
        text += '<use id="copy" xlink:href="#icon" x="5" fill="blue"/></svg>'
        result = self.imported(text)
        self.assert_pixels(result, lambda x, y: [255, 0, 0, 255] if x < 2 and y < 2 else
                           [0, 0, 255, 255] if 6 <= x < 8 and y < 2 else [0, 0, 0, 0])
        copies = [r for r in result['mapping'] if r['source_id'] == 'square']
        self.assertNotIn('instance_path', copies[0])
        self.assertEqual(len(copies[1]['instance_path']), 2)

    def test_explicit_source_paint_visibility_and_external_clip(self):
        text = svg_support.svg('<defs><clipPath id="clip"><rect x="1" width="2" height="4"/></clipPath>'
            '<g id="tile"><rect width="4" height="4" fill="red" visibility="visible"/></g></defs>'
            '<use href="#tile" fill="blue" visibility="hidden" clip-path="url(#clip)" x="4"/>'
            '<use href="#tile" x="12" display="none"/>')
        self.assert_pixels(self.imported(text), lambda x, y: [255, 0, 0, 255]
                           if 5 <= x < 7 and y < 4 else [0, 0, 0, 0])

    def test_cycles_external_missing_wrong_kind_and_unimplemented_scopes_refuse(self):
        cases = [
            '<use href="elsewhere.svg#tile"/>', '<use href="#missing"/>',
            '<use href="#encoded%20id"/>',
            '<use xmlns:xlink="http://www.w3.org/1999/xlink" href="#a" xlink:href="#b"/>',
            '<use id="self" href="#self"/>',
            '<defs><g id="a"><use href="#b"/></g><g id="b"><use href="#a"/></g></defs>',
            '<g id="a"><use href="#a"/></g>',
            '<defs><linearGradient id="g"><stop offset="0"/></linearGradient></defs><use href="#g"/>',
            '<defs><g id="g"><defs/><rect width="1" height="1"/></g></defs><use href="#g"/>',
            '<defs><svg id="s"><rect width="1" height="1"/></svg></defs><use href="#s"/>',
        ]
        for body in cases:
            with self.subTest(body=body):
                text = svg_support.svg(body)
                error = self.imported(text, 1)
                self.assertIn(error['code'], ('SVG_INVALID', 'SVG_UNSUPPORTED'))
                self.assertIn('byte_offset', error['details'])
        body = '<defs>' + ''.join(f'<g id="g{i}"><use href="#g{i+1}"/></g>' for i in range(20))
        body += '<rect id="g20" width="1" height="1"/></defs>'
        self.assertEqual(self.imported(svg_support.svg(body), 1)['code'], 'RESOURCE_LIMIT')

    def test_unused_shared_reference_graph_is_validated_without_expanding_copies(self):
        # Sixteen reference edges, with two uses per level: many possible copies,
        # but a small source graph. This is a DAG, not a circular reference.
        body = '<defs>' + ''.join(f'<g id="g{i}"><use href="#g{i+1}"/><use href="#g{i+1}"/></g>'
                                  for i in range(16))
        body += '<rect id="g16" width="1" height="1"/></defs>'
        result = self.imported(svg_support.svg(body))
        self.assertEqual(len(result['document']['items']), 1)
        self.assert_pixels(result, lambda x, y: [0, 0, 0, 0])

    def test_expansion_budget_and_unused_template_validation(self):
        text = svg_support.svg('<defs><rect id="r" width="1" height="1"/></defs>' + '<use href="#r"/>' * 150)
        self.assertEqual(self.imported(text, 1)['code'], 'RESOURCE_LIMIT')
        for bad in ['<rect width="-1" height="1"/>', '<path d="M0 0X1 1"/>',
                    '<image href="secret.png"/>', '<rect width="1" height="1" filter="url(#f)"/>']:
            self.imported(svg_support.svg('<defs>' + bad + '</defs>'), 1)
        for reference in ['fill="url(#missing)"', 'clip-path="url(#missing)"', 'mask="url(#missing)"']:
            self.assertEqual(self.imported(svg_support.svg('<defs><g ' + reference + '><rect width="1" height="1"/></g></defs>'), 1)['code'], 'SVG_INVALID')

    def test_atomic_insertion_remaps_occurrence_ids_and_original_offsets(self):
        document = self.invoke(dict(command='document.create', id='target', kind='vector', width=32, height=24))
        before = copy.deepcopy(document)
        text = '<defs><rect id="tile" width="2" height="2"/></defs>\n<use id="copy" href="#tile" x="4"/>'
        edited = self.invoke(dict(command='document.edit', document=document, expected_revision=0, operations=[dict(op='add_svg', svg=text, prefix='insert')]))
        # Edit details contain the shared insertion receipt, not an XML rewrite.
        receipt = edited['changes'][0]['details']
        copy_row = next(row for row in receipt['mapping'] if row['source_id'] == 'copy')
        tile_row = next(row for row in receipt['mapping'] if row['source_id'] == 'tile')
        self.assertEqual(copy_row['byte_offset'], text.index('<use'))
        self.assertEqual(tile_row['byte_offset'], text.index('<rect'))
        self.assertEqual(tile_row['instance_path'][0]['item_id'], copy_row['item_id'])
        self.assertEqual(tile_row['instance_path'][0]['byte_offset'], text.index('<use'))
        self.assertEqual(document, before)
        error = self.invoke(dict(command='document.edit', document=document, expected_revision=0, operations=[dict(op='add_svg', svg='<title>\u03bb</title>\n<use href="#missing"/>')]), 1)
        self.assertEqual(error['code'], 'SVG_INVALID')
        self.assertEqual(error['details']['byte_offset'], len('<title>\u03bb</title>\n'.encode()))
        self.assertEqual(document, before)

    def test_mcp_session_retry_failed_insert_and_undo_preserve_committed_state(self):
        client = Client(); self.addCleanup(client.close); client.initialize()
        text = '<defs><rect id="tile" width="3" height="2"/></defs><use href="#tile" fill="red"/>'
        with tempfile.TemporaryDirectory() as directory:
            common = dict(session_root=directory, session_id='reuse')
            document = self.invoke(dict(command='document.create', id='target', kind='vector', width=32, height=24))
            client.success('session.create', **common, request_id='create', document=document)
            request = dict(**common, request_id='insert', expected_revision=0,
                action=dict(type='edit', operations=[dict(op='add_svg', svg=text)]))
            applied = client.success('session.apply', **request)
            self.assertEqual(client.success('session.apply', **request), {**applied, 'replayed': True})
            self.assert_pixels(applied, lambda x, y: [255, 0, 0, 255] if x < 3 and y < 2 else [0, 0, 0, 0])
            self.invoke(dict(command='session.apply', **common, request_id='bad', expected_revision=1,
                action=dict(type='edit', operations=[dict(op='add_svg', svg='<use id="cycle" href="#cycle"/>')])), 1)
            self.assertEqual(client.success('session.read', **common)['document'], applied['document'])
            undone = client.success('session.apply', **common, request_id='undo', expected_revision=1, action=dict(type='undo'))
            self.assertEqual(undone['document']['items'], [])
            redone = client.success('session.apply', **common, request_id='redo', expected_revision=2, action=dict(type='redo'))
            self.assertEqual(redone['document']['items'], applied['document']['items'])


if __name__ == '__main__':
    unittest.main()
