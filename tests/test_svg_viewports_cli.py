"""Nested SVGs checked against independent rectangles and original source identity."""
import hashlib
from pathlib import Path
import tempfile
import unittest
import test_svg_import_cli as support
import test_svg_symbols_cli as symbols
import test_svg_text_cli as text_support
from test_mcp import Client


RED = [255, 0, 0, 255]
BLUE = [0, 0, 255, 255]
GREEN = [0, 255, 0, 255]


class SvgViewportTests(unittest.TestCase):
    invoke = support.SvgImportTests.invoke
    imported = support.SvgImportTests.imported
    pixels = support.SvgImportTests.pixels
    check = symbols.SvgSymbolTests.check

    def test_dimensions_defaults_percentages_and_absolute_units(self):
        for attrs, box in [('', (0, 0, 32, 24)),
                           ('width="auto" height="auto"', (0, 0, 32, 24)),
                           ('x="25%" y="25%" width="50%" height="50%"', (8, 6, 24, 18)),
                           ('x="3pt" y=".0625in" width="6pt" height=".125in"', (4, 6, 12, 18))]:
            with self.subTest(attrs=attrs):
                result = self.check(f'<svg id="v" {attrs}><rect width="100" height="100" fill="red"/></svg>',
                                    [(*box, RED)])
                row = next(row for row in result['mapping'] if row['source_id'] == 'v')
                self.assertEqual(row['viewport_size'], [box[2] - box[0], box[3] - box[1]])
                self.assertIn(row['viewport_item_id'], {i['id'] for i in result['document']['items']})

    def test_nested_percentages_use_nearest_viewbox_and_restore_siblings(self):
        body = ('<svg x="25%" y="25%" width="50%" height="50%" viewBox="0 0 8 6">'
                '<svg x="50%" width="50%" height="100%"><rect width="20" height="20" fill="red"/></svg>'
                '</svg><svg x="75%" y="50%" width="25%" height="25%">'
                '<rect width="20" height="20" fill="blue"/></svg>')
        self.check(body, [(16, 6, 24, 18, RED), (24, 12, 32, 18, BLUE)],
                   attrs='width="32" height="24" viewBox="0 0 16 12"')

    def test_meet_grid_and_nonzero_viewbox_origin(self):
        for horizontal, hx in [('Min', 0), ('Mid', 4), ('Max', 8)]:
            for vertical, vy in [('Min', 0), ('Mid', 4), ('Max', 8)]:
                for size, box in [('16 8', (2 + hx, 2, 10 + hx, 10)),
                                  ('8 16', (2, 2 + vy, 10, 10 + vy))]:
                    width, height = size.split()
                    with self.subTest(horizontal=horizontal, vertical=vertical, size=size):
                        self.check(f'<svg x="2" y="2" width="{width}" height="{height}" '
                                   f'viewBox="4 6 4 4" preserveAspectRatio="x{horizontal}Y{vertical}">'
                                   '<rect x="4" y="6" width="4" height="4" fill="red"/></svg>', [(*box, RED)])

    def test_slice_none_and_aspect_without_viewbox(self):
        for aspect, box in [('xMidYMid slice', (6, 4, 10, 12)), ('none', (7, 4, 9, 12)),
                            ('none meet', (7, 4, 9, 12)), ('none slice', (7, 4, 9, 12))]:
            self.check(f'<svg x="4" y="4" width="8" height="8" viewBox="0 0 8 4" preserveAspectRatio="{aspect}">'
                       '<rect x="3" width="2" height="4" fill="red"/></svg>', [(*box, RED)])
        self.check('<svg x="4" y="2" width="8" height="8" preserveAspectRatio="xMaxYMax slice">'
                   '<rect width="2" height="3" fill="red"/></svg>', [(4, 2, 6, 5, RED)])
        self.imported(support.svg('<svg preserveAspectRatio="bad"/>'), 1)

    def test_transform_order_default_clip_and_css_overflow(self):
        for declaration, box in [('', (6, 6, 14, 14)), ('overflow="visible"', (4, 4, 16, 16)),
                                 ('class="visible"', (4, 4, 16, 16)),
                                 ('class="visible" style="overflow:hidden"', (6, 6, 14, 14))]:
            self.check('<style>.visible{overflow:visible}</style>'
                       f'<svg transform="translate(2,2) scale(2)" x="2" y="2" width="4" height="4" '
                       f'viewBox="0 0 4 4" {declaration}>'
                       '<rect x="-1" y="-1" width="6" height="6" fill="red"/></svg>', [(*box, RED)])

    def test_content_effects_visibility_and_opacity_apply_once(self):
        self.check('<defs><clipPath id="c"><rect x="1" width="2" height="4"/></clipPath></defs>'
                   '<svg x="4" y="2" width="8" height="8" viewBox="0 0 4 4" '
                   'clip-path="url(#c)" opacity=".5" visibility="hidden">'
                   '<rect width="4" height="4" visibility="visible" fill="red"/></svg>'
                   '<svg display="none"><rect width="32" height="24" display="inline" fill="blue"/></svg>',
                   [(6, 2, 10, 10, [255, 0, 0, 128])])

    def test_gradients_bind_nested_user_coordinates(self):
        self.check('<linearGradient id="g" gradientUnits="userSpaceOnUse" x2="100%" y2="0">'
                   '<stop offset="0" stop-color="red"/><stop offset="50%" stop-color="red"/>'
                   '<stop offset="50%" stop-color="blue"/><stop offset="100%" stop-color="blue"/></linearGradient>'
                   '<svg width="8" height="4" viewBox="0 0 4 2"><rect width="4" height="2" fill="url(#g)"/></svg>'
                   '<svg y="4" width="16" height="4"><rect width="16" height="4" fill="url(#g)"/></svg>'
                   '<rect y="8" width="32" height="4" fill="url(#g)"/>',
                   [(0, 0, 4, 4, RED), (4, 0, 8, 4, BLUE), (0, 4, 8, 8, RED),
                    (8, 4, 16, 8, BLUE), (0, 8, 16, 12, RED), (16, 8, 32, 12, BLUE)])

    def test_nested_svg_inside_mask_uses_each_referencing_viewport(self):
        body = ('<mask id="m" maskUnits="userSpaceOnUse" x="0" y="0" width="100%" height="100%">'
                '<svg x="50%" width="25%" height="100%"><rect width="100" height="100" fill="white"/></svg>'
                '</mask><svg width="8" height="4"><rect width="8" height="4" fill="red" mask="url(#m)"/></svg>'
                '<svg y="4" width="16" height="4"><rect width="16" height="4" fill="blue" mask="url(#m)"/></svg>')
        result = self.check(body, [(4, 0, 6, 4, RED), (8, 4, 12, 8, BLUE)])
        # The original root context is validated as well as the two used variants.
        self.assertEqual(sum(row['source_id'] == 'm' for row in result['mapping']), 3)
        exported = self.invoke(dict(command='document.export', document=result['document'], format='svg'))
        again = self.imported(exported['data'])
        for scale in (1, 2):
            self.assertEqual(self.pixels(result['document'], scale), self.pixels(again['document'], scale))

    def test_nested_svg_inside_symbol_and_reused_group(self):
        self.check('<symbol id="s" viewBox="0 0 8 8"><svg x="50%" y="25%" width="50%" height="50%">'
                   '<rect width="10" height="10" fill="red"/></svg></symbol>'
                   '<use href="#s" width="16" height="16"/>', [(8, 4, 16, 12, RED)])
        self.check('<defs><g id="g"><svg width="4" height="4"><rect width="8" height="8"/></svg></g></defs>'
                   '<use href="#g" fill="red"/><use href="#g" x="8" fill="blue"/>',
                   [(0, 0, 4, 4, RED), (8, 0, 12, 4, BLUE)])

    def test_reused_svg_shares_geometry_and_retains_distinct_viewports(self):
        body = ('<svg id="v" x="2" width="8" height="8" viewBox="0 0 4 4">'
                '<rect id="r" width="2" height="2" fill="red"/></svg>'
                '<use href="#v" x="16" width="4" height="4"/>')
        result = self.check(body, [(2, 0, 6, 4, RED), (18, 0, 20, 2, RED)])
        ids = {row['item_id'] for row in result['mapping'] if row['source_id'] == 'r'}
        self.assertEqual(len(ids), 1)
        self.assertEqual(len({row['component_source_id'] for row in result['reuse']}), 1)
        self.assertTrue(any(row.get('original') for row in result['reuse']))
        changed = self.invoke(dict(command='document.edit', document=result['document'], expected_revision=0,
            operations=[dict(op='vector', id=ids.pop(), fill=RED,
                             geometry=dict(shape='rect', x=0, y=0, width=6, height=3))]))['document']
        expected = self.check('<rect x="2" width="8" height="6" fill="red"/>'
                              '<rect x="18" width="4" height="3" fill="red"/>',
                              [(2, 0, 10, 6, RED), (18, 0, 22, 3, RED)])
        for scale in (1, 2):
            self.assertEqual(self.pixels(changed, scale), self.pixels(expected['document'], scale))

    def test_zero_viewport_preserves_siblings_definitions_and_declares_content_loss(self):
        for dimension in ('width="0"', 'height="0"'):
            result = self.check(f'<g><svg id="empty" {dimension}><defs><rect id="r" width="2" height="2"/></defs>'
                                '<rect width="8" height="8" fill="blue"/></svg>'
                                '<use href="#r" fill="red"/><rect x="8" width="4" height="4" fill="lime"/></g>',
                                [(0, 0, 2, 2, RED), (8, 0, 12, 4, GREEN)])
            row = next(row for row in result['mapping'] if row['source_id'] == 'empty')
            self.assertTrue(row['empty_viewport'])
            self.assertTrue(any('Zero-size SVG' in loss for loss in result['losses']))
        for content in ('<image href="missing.png"/>', '<rect width="2" height="2" fill="url(#missing)"/>',
                        '<use href="#missing"/>', '<svg viewBox="0 0 0 1"/>'):
            with self.subTest(content=content):
                self.imported(support.svg(f'<svg width="0">{content}</svg>'), 1)
        self.imported(support.svg('<svg width="0" mask="url(#missing)"/>'), 1)

    def test_versions_share_root_compatibility_and_conflicts_fail_located(self):
        for root, nested in [('', ''), ('version="1.0"', 'version="1.1"'),
                             ('version="2.0"', ''), ('version="2.0"', 'version="2.0"')]:
            self.check(f'<svg {nested}><rect width="2" height="2" fill="red"/></svg>',
                       [(0, 0, 2, 2, RED)], attrs=f'width="32" height="24" {root}')
        for root, nested in [('', '2.0'), ('version="2.0"', '1.1'), ('', '3.0')]:
            text = support.svg(f'<svg id="bad" version="{nested}"/>', f'width="32" height="24" {root}')
            error = self.imported(text, 1)
            self.assertEqual(error['code'], 'SVG_UNSUPPORTED')
            self.assertEqual(error['details']['byte_offset'], text.index('<svg id="bad"'))

    def test_invalid_unused_templates_and_generated_group_depth_fail(self):
        for attrs in ('width="-1"', 'height="-1%"', 'viewBox="0 0 0 4"',
                      'overflow="scroll"', 'refX="0"', 'width="1em"', 'preserveAspectRatio="none bad"'):
            for wrapper in ('<svg {attrs}/>', '<defs><svg {attrs}/></defs>'):
                with self.subTest(attrs=attrs, wrapper=wrapper):
                    error = self.imported(support.svg(wrapper.format(attrs=attrs)), 1)
                    self.assertIn(error['code'], ('SVG_INVALID', 'SVG_UNSUPPORTED'))
        # Each input viewport expands to two native groups, both charged to the
        # unchanged hierarchy limit; eight levels plus root and leaf exceed it.
        self.check('<svg>' * 7 + '<rect width="2" height="2" fill="red"/>' + '</svg>' * 7,
                   [(0, 0, 2, 2, RED)])
        error = self.imported(support.svg('<svg>' * 8 + '<rect width="2" height="2"/>' + '</svg>' * 8), 1)
        self.assertEqual(error['code'], 'RESOURCE_LIMIT')

    def test_file_source_is_immutable_and_insertion_remaps_viewport_ids(self):
        text = support.svg('<title>Original café</title><svg id="v" x="4" width="8" height="8" viewBox="0 0 4 4">'
                           '<rect id="r" width="4" height="4" fill="red"/></svg><use href="#v" x="16"/>')
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'original.svg'
            original = text.encode()
            path.write_bytes(original)
            result = self.invoke(dict(command='svg.import', id='file', source=dict(kind='file', source_path=str(path))))
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(result['source']['sha256'], hashlib.sha256(original).hexdigest())
        document = self.invoke(dict(command='document.create', id='target', kind='vector', width=32, height=24))
        inserted = self.invoke(dict(command='document.edit', document=document, expected_revision=0,
            operations=[dict(op='add_svg', svg=text, prefix='viewport')]))
        ids = {item['id'] for item in inserted['document']['items']}
        for row in inserted['changes'][0]['details']['mapping']:
            for field in ('item_id', 'viewport_item_id', 'instance_item_id', 'component_source_id'):
                if field in row:
                    self.assertIn(row[field], ids)
            self.assertTrue(original[row['byte_offset']:].startswith(('<' + row['element']).encode()))
            for placement in row.get('instance_path', []):
                self.assertIn(placement['item_id'], ids)
        for scale in (1, 2):
            self.assertEqual(self.pixels(result['document'], scale), self.pixels(inserted['document'], scale))

    def test_mcp_insertion_proposal_retry_undo_and_failed_batch_are_atomic(self):
        client = Client(('--tools', 'core'))
        self.addCleanup(client.close)
        client.initialize()
        with tempfile.TemporaryDirectory() as temporary:
            common = dict(session_root=temporary, session_id='viewports')
            document = self.invoke(dict(command='document.create', id='target', kind='vector', width=32, height=24))
            client.success('session.create', **common, request_id='create', document=document)
            text = support.svg('<svg x="4" y="2" width="8" height="8" viewBox="0 0 4 4">'
                               '<rect width="8" height="8" fill="red"/></svg>')
            action = dict(type='edit', operations=[dict(op='add_svg', svg=text)])
            preview = client.success('session.dry_run', **common, request_id='insert', expected_revision=0,
                                     action=action, options=dict(include_document=True))
            self.assertEqual(client.success('session.read', **common)['document'], document)
            applied = client.success('session.apply_proposal', session_root=temporary,
                                     proposal=preview['proposal'], action=action)
            self.assertEqual(applied['document'], preview['proposed_document'])
            self.assertEqual(applied['receipt'], preview['predicted_receipt'])
            expected = self.check('<rect x="4" y="2" width="8" height="8" fill="red"/>', [(4, 2, 12, 10, RED)])
            self.assertEqual(self.pixels(applied['document']), self.pixels(expected['document']))
            retry = client.success('session.apply', **common, request_id='insert', expected_revision=0, action=action)
            self.assertTrue(retry['replayed'])
            self.assertEqual(retry['receipt'], applied['receipt'])
            failed = self.invoke(dict(command='session.apply', **common, request_id='bad', expected_revision=1,
                action=dict(type='edit', operations=[dict(op='add_svg', svg=text),
                    dict(op='add_svg', svg='<svg><svg viewBox="0 0 0 4"/></svg>')])), 1)
            self.assertNotIn('document', failed)
            self.assertEqual(client.success('session.read', **common)['document'], applied['document'])
            undone = client.success('session.apply', **common, request_id='undo', expected_revision=1, action=dict(type='undo'))
            self.assertEqual(undone['document']['items'], [])
            redone = client.success('session.apply', **common, request_id='redo', expected_revision=2, action=dict(type='redo'))
            self.assertEqual(redone['document']['items'], applied['document']['items'])
            self.assertFalse(client.tool('run', command='session.verify', arguments=common)['isError'])


class SvgViewportTextTests(unittest.TestCase):
    setUp = text_support.SvgTextTests.setUp
    invoke = text_support.SvgTextTests.invoke
    imported = text_support.SvgTextTests.imported
    pixels = text_support.SvgTextTests.pixels

    def test_text_percentage_positions_reset_and_restore_with_viewports(self):
        result = self.imported('<svg x="2" width="16" height="16" viewBox="0 0 8 8">'
            '<text font-family="Geometry" font-size="10" x="43.75%" y="150%" fill="red">A</text></svg>'
            '<text font-family="Geometry" font-size="10" x="60.9375%" y="50%" fill="blue">A</text>')
        # Nested glyph [4,8]x[5,12] maps to [10,18]x[10,24], clipped at y16.
        # Following glyph resolves against the outer 32x24 viewport, x20..24.
        for scale in (1, 2):
            width, height, actual = self.pixels(result['document'], scale)
            expected = bytes(value for y in range(height) for x in range(width)
                for value in (RED if 10*scale <= x < 18*scale and 10*scale <= y < 16*scale
                              else BLUE if 20*scale <= x < 24*scale and 5*scale <= y < 12*scale else [0]*4))
            self.assertEqual(actual, expected)
