"""Original symbols checked against explicit rectangles and coordinate oracles."""
import unittest
import test_svg_import_cli as support
import test_svg_text_cli as text_support


class SvgSymbolTests(unittest.TestCase):
    invoke = support.SvgImportTests.invoke
    imported = support.SvgImportTests.imported
    pixels = support.SvgImportTests.pixels

    def check(self, body, rectangles, attrs='width="32" height="24"'):
        result = self.imported(support.svg(body, attrs))
        for scale in (1, 2):
            width, height, actual = self.pixels(result['document'], scale)
            expected = bytearray()
            for y in range(height):
                for x in range(width):
                    point = ((x + .5) / scale, (y + .5) / scale)
                    color = [0, 0, 0, 0]
                    for left, top, right, bottom, rgba in rectangles:
                        if left <= point[0] < right and top <= point[1] < bottom:
                            color = rgba
                    expected.extend(color)
            self.assertEqual(actual, expected)
        return result

    def test_symbol_defaults_auto_dimensions_and_use_overrides(self):
        for symbol, use, box in [
            ('', '', (0, 0, 32, 24)),
            ('width="auto" height="auto"', 'width="auto" height="auto"', (0, 0, 32, 24)),
            ('width="8" height="6"', '', (0, 0, 8, 6)),
            ('width="8" height="6"', 'width="auto" height="auto"', (0, 0, 8, 6)),
            ('width="8" height="6"', 'width="25%" height="50%"', (0, 0, 8, 12)),
            ('width="50%" height="25%"', 'width="4"', (0, 0, 4, 6)),
        ]:
            with self.subTest(symbol=symbol, use=use):
                result = self.check(f'<symbol id="s" {symbol}><rect width="100" height="100" fill="red"/></symbol>'
                    f'<use href="#s" {use}/>', [(*box, [255, 0, 0, 255])])
                row = next(row for row in result['mapping'] if row['source_id'] == 's')
                self.assertEqual(row['viewport_size'], [box[2], box[3]])
                self.assertIn(row['viewport_item_id'], {item['id'] for item in result['document']['items']})

    def test_meet_alignment_grid_and_nonzero_viewbox_origin(self):
        # Wide/tall slots leave exactly eight units of horizontal/vertical slack.
        for horizontal, hx in [('Min', 0), ('Mid', 4), ('Max', 8)]:
            for vertical, vy in [('Min', 0), ('Mid', 4), ('Max', 8)]:
                align = f'x{horizontal}Y{vertical}'
                with self.subTest(align=align):
                    symbol = f'<symbol id="s" viewBox="4 6 4 4" preserveAspectRatio="{align}"><rect x="4" y="6" width="4" height="4" fill="red"/></symbol>'
                    self.check(symbol + '<use href="#s" width="16" height="8"/>',
                               [(hx, 0, hx + 8, 8, [255, 0, 0, 255])])
                    self.check(symbol + '<use href="#s" width="8" height="16"/>',
                               [(0, vy, 8, vy + 8, [255, 0, 0, 255])])
        self.check('<symbol id="s" viewBox="4 6 4 4"><rect x="4" y="6" width="4" height="4" fill="red"/></symbol>'
                   '<use href="#s" width="16" height="8"/>', [(4, 0, 12, 8, [255, 0, 0, 255])])

    def test_slice_none_and_default_viewport_clip(self):
        for aspect, rect in [('xMidYMid slice', (6, 4, 10, 12)), ('none', (7, 4, 9, 12))]:
            self.check(f'<symbol id="s" viewBox="0 0 8 4" preserveAspectRatio="{aspect}">'
                '<rect x="3" width="2" height="4" fill="red"/></symbol>'
                '<use href="#s" x="4" y="4" width="8" height="8"/>',
                [(*rect, [255, 0, 0, 255])])
        for overflow, rect in [('', (4, 4, 12, 12)), ('overflow="visible"', (2, 2, 14, 14)),
                               ('style="overflow:visible"', (2, 2, 14, 14))]:
            self.check(f'<symbol id="s" viewBox="0 0 4 4" {overflow}>'
                '<rect x="-1" y="-1" width="6" height="6" fill="red"/></symbol>'
                '<use href="#s" x="4" y="4" width="8" height="8"/>', [(*rect, [255, 0, 0, 255])])

    def test_symbol_and_use_effects_have_distinct_coordinate_systems(self):
        body = '<defs><clipPath id="inner"><rect x="1" width="2" height="4"/></clipPath>'
        body += '<clipPath id="outer"><rect x="3" width="3" height="8"/></clipPath></defs>'
        body += '<symbol id="s" viewBox="0 0 4 4" clip-path="url(#inner)" opacity=".5">'
        body += '<rect width="4" height="4" fill="red"/></symbol>'
        body += '<use href="#s" x="4" y="2" width="8" height="8" clip-path="url(#outer)"/>'
        # Inner clip scales to x=2..6; host clip is x=3..6; host translates by4.
        self.check(body, [(7, 2, 10, 10, [255, 0, 0, 128])])

    def test_transform_and_position_order(self):
        self.check('<symbol id="s" x="1" y="2" transform="scale(2)" width="2" height="2">'
            '<rect width="2" height="2" fill="red"/></symbol>'
            '<use href="#s" x="3" y="1" transform="translate(2,1) scale(2)"/>',
            [(12, 11, 20, 19, [255, 0, 0, 255])])

    def test_anchors_distinguish_omission_origin_percent_and_keywords(self):
        for anchor, left in [('', 12), ('refX="0"', 16), ('refX="2"', 12),
                             ('refX="50%"', 12), ('refX="center"', 12),
                             ('refX="left"', 16), ('refX="right"', 8)]:
            with self.subTest(anchor=anchor):
                # Mapped viewBox origin is -4; explicit zero shifts the viewport.
                self.check(f'<symbol id="s" viewBox="2 0 4 4" {anchor}>'
                    '<rect x="2" width="4" height="4" fill="red"/></symbol>'
                    '<use href="#s" x="12" y="4" width="8" height="8"/>',
                    [(left, 4, left + 8, 12, [255, 0, 0, 255])])
        for anchor, top in [('top', 10), ('center', 6), ('bottom', 2), ('50%', 6)]:
            self.check(f'<symbol id="s" viewBox="0 0 4 4" refY="{anchor}">'
                '<rect width="4" height="4" fill="red"/></symbol>'
                '<use href="#s" x="4" y="10" width="8" height="8"/>',
                [(4, top, 12, top + 8, [255, 0, 0, 255])])

    def test_only_direct_symbol_instances_paint_and_host_display_still_applies(self):
        self.check('<style>symbol{display:none;fill:red}</style>'
            '<symbol id="s"><rect width="4" height="4"/>'
            '<symbol id="nested"><rect width="32" height="24" fill="blue"/></symbol></symbol>'
            '<use href="#s" x="4" width="4" height="4"/>'
            '<use href="#s" x="12" width="4" height="4" display="none"/>',
            [(4, 0, 8, 4, [255, 0, 0, 255])])

    def test_nested_symbols_percentages_restore_enclosing_viewport(self):
        self.check('<symbol id="outer" viewBox="0 0 8 8">'
            '<use href="#inner" x="50%" width="50%" height="50%"/></symbol>'
            '<symbol id="inner" viewBox="0 0 2 2"><rect width="2" height="2" fill="red"/></symbol>'
            '<use href="#outer" x="2" width="16" height="16"/>'
            '<use href="#inner" x="75%" y="50%" width="4" height="4"/>',
            [(10, 0, 18, 8, [255, 0, 0, 255]), (24, 12, 28, 16, [255, 0, 0, 255])])

    def test_zero_size_preserves_empty_occurrence_and_validates_references(self):
        for dimension in ['width="0"', 'height="0"']:
            result = self.check('<defs><mask id="m"><rect width="4" height="4" fill="white"/></mask></defs>'
                '<symbol id="s" viewBox="0 0 4 4"><rect width="4" height="4"/></symbol>'
                f'<use href="#s" {dimension} mask="url(#m)"/>', [])
            row = next(row for row in result['mapping'] if row['source_id'] == 's')
            self.assertTrue(row['empty_viewport'])
            self.assertFalse(any(item['content']['type'] in ('instance', 'component_source')
                                 for item in result['document']['items']))
            self.assertTrue(any('Zero-size symbol' in loss for loss in result['losses']))
        self.imported(support.svg('<symbol id="s"/><use href="#s" width="0" mask="url(#missing)"/>'), 1)

    def test_invalid_and_unimplemented_symbol_semantics_refuse_even_unused(self):
        for attrs in ['width="-1"', 'height="-1%"', 'viewBox="0 0 0 1"',
                      'viewBox="0 0 1 1" preserveAspectRatio="bad"', 'refX="bottom"',
                      'overflow="scroll"', 'overflow="inherit"', 'width="1em"']:
            with self.subTest(attrs=attrs):
                error = self.imported(support.svg(f'<symbol id="s" {attrs}><rect width="1" height="1"/></symbol>'), 1)
                self.assertIn(error['code'], ('SVG_INVALID', 'SVG_UNSUPPORTED'))
        for body in ['<defs overflow="hidden"/>', '<mask id="m" overflow="hidden"/>',
                     '<rect width="1" height="1" overflow="hidden"/>']:
            self.assertEqual(self.imported(support.svg(body), 1)['code'], 'SVG_UNSUPPORTED')

    def mask_fixture(self):
        return ('<defs><rect id="white" width="4" height="4" fill="white"/>'
            '<mask id="m" maskUnits="userSpaceOnUse" x="0" y="0" width="100%" height="100%">'
            '<use href="#white" x="50%"/></mask></defs>'
            '<symbol id="small" viewBox="0 0 8 8"><rect width="8" height="8" fill="red" mask="url(#m)"/></symbol>'
            '<symbol id="big" viewBox="0 0 16 8"><rect width="16" height="8" fill="blue" mask="url(#m)"/></symbol>'
            '<use href="#small" width="8" height="8"/>'
            '<use href="#big" x="8" width="16" height="8"/>'
            '<rect transform="translate(0,8)" width="32" height="4" fill="lime" mask="url(#m)"/>')

    def test_mask_content_is_bound_per_referencing_user_viewport(self):
        result = self.check(self.mask_fixture(), [(4, 0, 8, 4, [255, 0, 0, 255]),
                                                  (16, 0, 20, 4, [0, 0, 255, 255]),
                                                  (16, 8, 20, 12, [0, 255, 0, 255])])
        sources = [row for row in result['mapping'] if row['source_id'] == 'm']
        self.assertEqual(len(sources), 3)
        self.assertEqual({tuple(row['resource_viewport']) for row in sources if 'resource_viewport' in row},
                         {(8, 8), (16, 8)})
        self.assertEqual(len({row['item_id'] for row in sources}), 3)
        self.assertTrue(any('viewport-specific copies' in loss for loss in result['losses']))

    def test_matching_viewports_reuse_one_mask_source(self):
        result = self.check(self.mask_fixture() + '<use href="#small" x="24" width="8" height="8"/>',
            [(4, 0, 8, 4, [255, 0, 0, 255]), (16, 0, 20, 4, [0, 0, 255, 255]),
             (16, 8, 20, 12, [0, 255, 0, 255]), (28, 0, 32, 4, [255, 0, 0, 255])])
        self.assertEqual(sum(row['source_id'] == 'm' for row in result['mapping']), 3)

    def test_mask_variants_collect_nested_definitions_only_once(self):
        nested = ('<mask id="unused"><rect width="1" height="1" fill="white"/></mask>'
            '<linearGradient id="gradient"><stop offset="0" stop-color="white"/></linearGradient>')
        body = self.mask_fixture().replace('<use href="#white" x="50%"/>',
            nested + '<use href="#white" x="50%"/>')
        result = self.check(body, [(4, 0, 8, 4, [255, 0, 0, 255]),
                                  (16, 0, 20, 4, [0, 0, 255, 255]),
                                  (16, 8, 20, 12, [0, 255, 0, 255])])
        for source in ('unused', 'gradient'):
            self.assertEqual(sum(row['source_id'] == source for row in result['definitions']), 1)
        self.assertEqual(sum(row['source_id'] == 'unused' for row in result['mapping']), 1)

    def test_user_space_gradients_resolve_against_each_symbol_viewbox(self):
        body = ('<linearGradient id="g" gradientUnits="userSpaceOnUse" x2="100%" y2="0">'
            '<stop offset="0" stop-color="red"/><stop offset="50%" stop-color="red"/>'
            '<stop offset="50%" stop-color="blue"/><stop offset="100%" stop-color="blue"/></linearGradient>'
            '<symbol id="small" viewBox="0 0 8 4"><rect width="8" height="4" fill="url(#g)"/></symbol>'
            '<symbol id="large" viewBox="0 0 16 4"><rect width="16" height="4" fill="url(#g)"/></symbol>'
            '<use href="#small" width="8" height="4"/>'
            '<use href="#large" y="4" width="16" height="4"/>')
        self.check(body, [(0, 0, 4, 4, [255, 0, 0, 255]), (4, 0, 8, 4, [0, 0, 255, 255]),
                          (0, 4, 8, 8, [255, 0, 0, 255]), (8, 4, 16, 8, [0, 0, 255, 255])])

    def test_symbol_viewport_and_effects_survive_ordinary_svg_export(self):
        body = self.mask_fixture()
        result = self.imported(support.svg(body))
        exported = self.invoke(dict(command='document.export', document=result['document'], format='svg'))
        again = self.imported(exported['data'])
        for scale in (1, 2):
            self.assertEqual(self.pixels(result['document'], scale), self.pixels(again['document'], scale))

    def test_atomic_insertion_remaps_viewport_and_mask_resource_occurrences(self):
        document = self.invoke(dict(command='document.create', id='target', kind='vector', width=32, height=24))
        text = self.mask_fixture()
        result = self.invoke(dict(command='document.edit', document=document, expected_revision=0,
            operations=[dict(op='add_svg', svg=text, prefix='symbols')]))
        receipt = result['changes'][0]['details']
        ids = {item['id'] for item in result['document']['items']}
        for row in receipt['mapping']:
            for field in ('item_id', 'viewport_item_id', 'resource_item_id'):
                if field in row:
                    self.assertIn(row[field], ids)
            for instance in row.get('instance_path', []):
                self.assertIn(instance['item_id'], ids)
                self.assertTrue(text[instance['byte_offset']:].startswith('<use'))
        self.assertEqual(self.pixels(result['document']), self.pixels(self.imported(support.svg(text))['document']))


class SvgSymbolTextTests(unittest.TestCase):
    setUp = text_support.SvgTextTests.setUp
    invoke = text_support.SvgTextTests.invoke
    imported = text_support.SvgTextTests.imported
    pixels = text_support.SvgTextTests.pixels

    def test_percent_coordinates_and_inherited_font_resolve_inside_symbol(self):
        result = self.imported('<symbol id="s" viewBox="0 0 16 12">'
            '<text x="25%" dx="-.5" y="100%" font-size="50%">A</text></symbol>'
            '<use href="#s" font-family="Geometry" font-size="20" width="32" height="24" fill="red"/>')
        width, height, pixels = self.pixels(result['document'])
        expected = bytes(v for y in range(height) for x in range(width)
                         for v in ([255, 0, 0, 255] if 8 <= x < 16 and 10 <= y < 24 else [0] * 4))
        self.assertEqual(pixels, expected)


if __name__ == '__main__':
    unittest.main()
