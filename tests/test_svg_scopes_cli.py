"""Synthetic shadow-tree resources with independent colour/coverage oracles."""
import copy
import json
import tempfile
import unittest
import test_svg_import_cli as support
import test_svg_text_cli as text_support
from test_mcp import Client


def gradient(id='paint', color='currentColor'):
    return f'<linearGradient id="{id}"><stop offset="0" stop-color="{color}"/></linearGradient>'


class SvgScopeTests(unittest.TestCase):
    invoke = support.SvgImportTests.invoke
    imported = support.SvgImportTests.imported
    pixels = support.SvgImportTests.pixels

    def assert_pixels(self, document, rectangles):
        width, height, pixels = self.pixels(document)
        expected = []
        for y in range(height):
            for x in range(width):
                expected.extend(next((color for a, b, c, d, color in reversed(rectangles)
                                      if a <= x < c and b <= y < d), [0]*4))
        self.assertEqual(pixels, bytes(expected))

    def test_forward_scoped_gradient_uses_placement_color_and_retains_original_ids(self):
        body = '<use id="red" href="#tile" color="red"/><use id="blue" href="#tile" x="8" color="blue"/>'
        body += '<defs color="lime"><g id="tile"><rect id="art" width="4" height="3" fill="url(#paint)"/>'
        body += '<defs>' + gradient() + '</defs></g></defs>'
        text = support.svg(body)
        result = self.imported(text)
        self.assert_pixels(result['document'], [(0, 0, 4, 3, [255, 0, 0, 255]), (8, 0, 12, 3, [0, 0, 255, 255])])
        records = result['definitions']
        self.assertEqual(len(records), 3)
        self.assertEqual({r['source_id'] for r in records}, {'paint'})
        self.assertEqual({r['byte_offset'] for r in records}, {text.index('<linearGradient')})
        self.assertEqual(len({r.get('resource_scope', 0) for r in records}), 3)
        self.assertNotIn('\\u0000', json.dumps(result))
        # Different solid paints remain native overrides with shared geometry.
        rows = [r for r in result['mapping'] if r['source_id'] == 'art']
        self.assertEqual(rows[0]['item_id'], rows[1]['item_id'])

    def test_inherited_url_keeps_declaration_scope_and_explicit_url_uses_clone(self):
        body = '<defs color="lime"><g id="tile"><defs>' + gradient() + '</defs>'
        body += '<rect width="3" height="3"/><rect x="4" width="3" height="3" fill="inherit"/>'
        body += '<rect x="8" width="3" height="3" fill="url(#paint)"/></g></defs>'
        body += '<use href="#tile" color="red" fill="url(#paint)"/>'
        result = self.imported(support.svg(body))
        self.assert_pixels(result['document'], [(0, 0, 3, 3, [0, 255, 0, 255]),
            (4, 0, 7, 3, [0, 255, 0, 255]), (8, 0, 11, 3, [255, 0, 0, 255])])

    def test_nested_scopes_search_parent_before_original_and_sibling_external_resource(self):
        body = '<defs color="lime">' + gradient('outer', 'blue')
        body += '<g id="tile"><defs>' + gradient() + '</defs><use href="#leaf"/></g>'
        body += '<g id="leaf"><rect width="4" height="3" fill="url(#paint)"/>'
        body += '<rect x="4" width="4" height="3" fill="url(#outer)"/></g></defs>'
        body += '<use href="#tile" color="red"/>'
        result = self.imported(support.svg(body))
        self.assert_pixels(result['document'], [(0, 0, 4, 3, [255, 0, 0, 255]), (4, 0, 8, 3, [0, 0, 255, 255])])

    def test_gradient_href_chain_derived_stops_and_embedded_style(self):
        body = '<style>.painted {fill:url(#derived)} stop {stop-color:currentColor}</style>'
        body += '<defs color="lime"><g id="tile"><rect class="painted" width="4" height="3"/>'
        body += '<defs><linearGradient id="derived" href="#middle"/>'
        body += '<linearGradient id="middle" href="#base"/>' + gradient('base') + '</defs></g></defs>'
        body += '<use href="#tile" color="red"/><use href="#tile" color="blue" x="8"/>'
        result = self.imported(support.svg(body))
        self.assert_pixels(result['document'], [(0, 0, 4, 3, [255, 0, 0, 255]), (8, 0, 12, 3, [0, 0, 255, 255])])

    def test_scoped_clip_inherits_visibility_and_can_split_component_variants(self):
        body = '<defs><g id="tile"><defs><clipPath id="clip"><rect x="1" width="2" height="4"/></clipPath></defs>'
        body += '<rect width="4" height="4" visibility="visible" fill="red" clip-path="url(#clip)"/></g></defs>'
        body += '<use href="#tile" visibility="hidden"/><use href="#tile" x="8"/>'
        result = self.imported(support.svg(body))
        self.assert_pixels(result['document'], [(9, 0, 11, 4, [255, 0, 0, 255])])
        self.assertTrue(any('separate component variants' in loss for loss in result['losses']))

    def test_scoped_stroke_and_mask_definition_clip_resolve_forward_ids(self):
        body = '<defs><g id="tile"><defs><mask id="mask" mask-type="alpha" clip-path="url(#clip)">'
        body += '<defs><clipPath id="clip"><rect x="2" width="2" height="4"/></clipPath></defs>'
        body += '<rect width="8" height="4" fill="white"/></mask>' + gradient() + '</defs>'
        body += '<line x1="1" y1="1" x2="7" y2="1" stroke-width="2" stroke="url(#paint)" mask="url(#mask)"/></g></defs>'
        body += '<use href="#tile" color="red"/><use href="#tile" color="blue" x="8"/>'
        # A line has a degenerate object box, so mask coordinates are explicitly user-space.
        body = body.replace('mask-type="alpha"', 'mask-type="alpha" maskUnits="userSpaceOnUse" x="0" y="0" width="8" height="4"')
        result = self.imported(support.svg(body))
        self.assert_pixels(result['document'], [(2, 0, 4, 2, [255, 0, 0, 255]), (10, 0, 12, 2, [0, 0, 255, 255])])

    def test_mask_captures_scope_inheritance_and_nested_resource_context(self):
        body = '<defs color="lime"><g id="tile"><defs><mask id="mask" mask-type="luminance">'
        body += '<defs>' + gradient() + '</defs><rect width="4" height="4" fill="url(#paint)"/></mask></defs>'
        body += '<rect width="4" height="4" fill="white" mask="url(#mask)"/></g></defs>'
        body += '<use href="#tile" color="red"/><use href="#tile" color="blue" x="8"/>'
        result = self.imported(support.svg(body))
        # Independent sRGB luminance weights: red .2126, blue .0722.
        self.assert_pixels(result['document'], [(0, 0, 4, 4, [255, 255, 255, 54]), (8, 0, 12, 4, [255, 255, 255, 18])])
        masks = [r for r in result['definitions'] if r['source_id'] == 'mask']
        self.assertEqual(len({r['item_id'] for r in masks}), 3)
        self.assertEqual(len([r for r in result['definitions'] if r['source_id'] == 'paint']), 3)
        self.assertNotIn('\\u0000', json.dumps(result))

    def test_symbol_mask_percentages_and_repeated_mask_preparation(self):
        body = '<defs><symbol id="tile" viewBox="0 0 8 4"><defs><mask id="mask" mask-type="alpha">'
        body += '<defs><linearGradient id="paint" gradientUnits="userSpaceOnUse" x2="100%">'
        body += '<stop offset="0" stop-color="white" stop-opacity="0"/><stop offset="1" stop-color="white"/></linearGradient></defs>'
        body += '<rect width="8" height="4" fill="url(#paint)"/></mask></defs>'
        body += '<rect width="8" height="4" fill="red" mask="url(#mask)"/></symbol></defs>'
        body += '<use href="#tile" width="8" height="4"/><use href="#tile" x="16" width="16" height="8"/>'
        result = self.imported(support.svg(body))
        width, height, pixels = self.pixels(result['document'])
        expected = []
        for y in range(height):
            for x in range(width):
                t = (x+.5)/8 if x < 8 and y < 4 else (x-16+.5)/16 if 16 <= x < 32 and y < 8 else 0
                expected.extend([255, 0, 0, int(t*255+.5)] if t else [0]*4)
        self.assertLessEqual(max(abs(a-b) for a, b in zip(pixels, expected)), 1)
        # One nested gradient per scope, even though masks also have root-viewport copies.
        self.assertEqual(len([r for r in result['definitions'] if r['source_id'] == 'paint']), 3)

    def test_use_inside_scoped_mask_and_live_mask_edit(self):
        body = '<defs><rect id="white" width="4" height="4" fill="white"/><g id="tile"><defs>'
        body += '<mask id="mask" mask-type="alpha"><use href="#white"/></mask></defs>'
        body += '<rect width="4" height="4" fill="red" mask="url(#mask)"/></g></defs>'
        body += '<use id="a" href="#tile"/><use id="b" href="#tile" x="8"/>'
        result = self.imported(support.svg(body))
        target = next(r for r in result['mapping'] if r['source_id'] == 'mask' and r.get('instance_path', [{}])[0].get('source_id') == 'a')
        edited = self.invoke(dict(command='document.edit', document=result['document'], expected_revision=0,
            operations=[dict(op='properties', id=target['item_id'], visible=False)]))
        self.assert_pixels(edited['document'], [(8, 0, 12, 4, [255, 0, 0, 255])])

    def test_internal_key_spelling_cannot_collide_with_original_xml_ids(self):
        body = '<defs>' + gradient('1:paint', 'blue') + '<g id="tile"><defs>' + gradient() + '</defs>'
        body += '<rect width="4" height="4" fill="url(#paint)"/><rect x="4" width="4" height="4" fill="url(#1:paint)"/></g></defs>'
        body += '<use href="#tile" color="red"/>'
        result = self.imported(support.svg(body))
        self.assert_pixels(result['document'], [(0, 0, 4, 4, [255, 0, 0, 255]), (4, 0, 8, 4, [0, 0, 255, 255])])

    def test_missing_wrong_type_recursive_and_unused_unsupported_scoped_resources_fail(self):
        bodies = [
            '<defs><linearGradient id="paint" href="#paint"/></defs><rect width="1" height="1" fill="url(#paint)"/>',
            '<defs><clipPath id="paint"><rect width="1" height="1"/></clipPath></defs><rect width="1" height="1" fill="url(#paint)"/>',
            '<rect width="1" height="1" fill="url(#missing)"/>',
            '<defs><mask id="mask"><rect width="1" height="1" mask="url(#mask)"/></mask></defs>',
            '<defs><mask id="mask"><use href="#tile"/></mask></defs>',
            '<defs><clipPath id="clip"><image href="file.png"/></clipPath></defs>',
        ]
        for body in bodies:
            with self.subTest(body=body):
                error = self.imported(support.svg('<defs><g id="tile">' + body + '</g></defs><use href="#tile"/>'), 1)
                self.assertIn(error['code'], ('SVG_INVALID', 'SVG_UNSUPPORTED'))
                self.assertNotIn('\\u0000', json.dumps(error))

    def test_resource_limit_counts_original_and_each_cloned_definition(self):
        body = '<defs><g id="tile"><defs>' + gradient() + '</defs><rect width="1" height="1" fill="url(#paint)"/></g></defs>'
        result = self.imported(support.svg(body + '<use href="#tile"/>'*63), resource_profile='large_vector')
        self.assertEqual(len(result['definitions']), 64)
        error = self.imported(support.svg(body + '<use href="#tile"/>'*64), 1, resource_profile='large_vector')
        self.assertEqual(error['code'], 'RESOURCE_LIMIT')

    def test_insertion_remaps_resource_paths_and_session_retry_undo(self):
        body = '<defs><g id="tile"><defs>' + gradient() + '</defs><rect width="4" height="3" fill="url(#paint)"/></g></defs>'
        body += '<use id="red" href="#tile" color="red"/><use id="blue" href="#tile" x="8" color="blue"/>'
        document = self.invoke(dict(command='document.create', id='target', kind='vector', width=32, height=24))
        before = copy.deepcopy(document)
        client = Client(); self.addCleanup(client.close); client.initialize()
        with tempfile.TemporaryDirectory() as directory:
            common = dict(session_root=directory, session_id='scopes')
            client.success('session.create', **common, request_id='create', document=document)
            request = dict(**common, request_id='insert', expected_revision=0,
                action=dict(type='edit', operations=[dict(op='add_svg', svg=body, prefix='scope')]))
            result = client.success('session.apply', **request)
            self.assertTrue(client.success('session.apply', **request)['replayed'])
            ids = {item['id'] for item in result['document']['items']}
            # Read the operation receipt through the direct edit API as well.
            edit = self.invoke(dict(command='document.edit', document=document, expected_revision=0,
                operations=request['action']['operations']))
            for row in edit['changes'][0]['details']['definitions']:
                self.assertEqual(row['byte_offset'], body.index('<linearGradient'))
                for entry in row.get('instance_path', []):
                    self.assertEqual(body[entry['byte_offset']:entry['byte_offset']+4], '<use')
                    for field in ('item_id', 'instance_item_id', 'component_source_id'):
                        if field in entry:
                            self.assertIn(entry[field], ids)
            self.assert_pixels(result['document'], [(0, 0, 4, 3, [255, 0, 0, 255]), (8, 0, 12, 3, [0, 0, 255, 255])])
            undo = client.success('session.apply', **common, request_id='undo', expected_revision=1, action=dict(type='undo'))
            self.assertEqual(undo['document']['items'], before['items'])
            client.success('session.verify', **common)
        self.assertEqual(document, before)


class SvgScopeTextTests(unittest.TestCase):
    setUp = text_support.SvgTextTests.setUp
    invoke = text_support.SvgTextTests.invoke
    imported = text_support.SvgTextTests.imported
    pixels = text_support.SvgTextTests.pixels

    def test_delayed_scoped_mask_text_keeps_font_size_and_colour_inheritance(self):
        body = '<defs font-family="Geometry" font-size="10"><g id="tile"><defs><mask id="mask" mask-type="alpha">'
        body += '<text x="3.5" y="12" fill="currentColor">A</text></mask></defs>'
        body += '<rect width="16" height="24" fill="red" mask="url(#mask)"/></g></defs>'
        body += '<use href="#tile" font-family="Geometry" font-size="10" color="white"/>'
        body += '<use href="#tile" x="16" font-family="Geometry" font-size="5" color="white"/>'
        result = self.imported(body)
        width, height, pixels = self.pixels(result['document'], 2)
        # The geometric fixture glyph occupies [.05,.45]x[-.7,0] em from baseline.
        expected = []
        for y in range(height):
            for x in range(width):
                alpha = 255 if 8 <= x < 16 and 10 <= y < 24 else 0
                if 17 <= y < 24:
                    # Half-size glyph is [39.5,43.5] at this output scale.
                    coverage = max(0, min(x+1, 43.5) - max(x, 39.5))
                    alpha = max(alpha, int(coverage*255+.5))
                expected.extend([255, 0, 0, alpha] if alpha else [0]*4)
        expected = bytes(expected)
        self.assertEqual(pixels, expected)
        self.assertEqual(result['document']['fonts'], {'geometric': self.font})


if __name__ == '__main__':
    unittest.main()
