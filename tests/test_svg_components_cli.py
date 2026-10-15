"""Editable SVG source sharing, placement overrides and bounded fallback."""
import copy
import tempfile
import unittest
import test_svg_import_cli as support
import test_svg_text_cli as text_support
from test_mcp import Client


class SvgComponentTests(unittest.TestCase):
    invoke = support.SvgImportTests.invoke
    imported = support.SvgImportTests.imported
    pixels = support.SvgImportTests.pixels

    def source(self, result, name):
        rows = [row for row in result['mapping'] if row['source_id'] == name]
        self.assertEqual(len({row['item_id'] for row in rows}), 1)
        return rows[0]['item_id']

    def edit(self, document, operations, expected=0):
        return self.invoke(dict(command='document.edit', document=document,
            expected_revision=document['revision'], operations=operations), expected)

    def assert_pixels(self, document, rectangles):
        width, height, actual = self.pixels(document)
        expected = bytearray()
        for y in range(height):
            for x in range(width):
                color = [0] * 4
                for left, top, right, bottom, rgba in rectangles:
                    if left <= x < right and top <= y < bottom:
                        color = rgba
                expected.extend(color)
        self.assertEqual(actual, expected)

    def test_geometry_edits_update_placements_while_color_overrides_remain_local(self):
        result = self.imported(support.svg('<defs><rect id="tile" width="2" height="2"/></defs>'
            '<use id="a" href="#tile" x="2" fill="red"/><use id="b" href="#tile" x="12" fill="blue"/>'))
        source = self.source(result, 'tile')
        original = copy.deepcopy(result['document'])
        changed = self.edit(original, [dict(op='vector', id=source,
            geometry=dict(shape='rect', x=0, y=0, width=5, height=4), fill=[0, 255, 0, 255])])['document']
        self.assert_pixels(changed, [(2, 0, 7, 4, [0, 255, 0, 255]), (12, 0, 17, 4, [0, 0, 255, 255])])
        self.assertEqual(result['document'], original)
        self.assertEqual(sum(item['content']['type'] == 'component_source' for item in changed['items']), 1)
        self.assertEqual(sum(item['content']['type'] == 'instance' for item in changed['items']), 2)

    def test_visible_original_and_copies_share_geometry(self):
        result = self.imported(support.svg('<g fill="red"><rect id="tile" width="2" height="2"/></g>'
            '<use href="#tile" x="8" fill="blue"/>'))
        source = self.source(result, 'tile')
        paint = next(item['content']['fill'] for item in result['document']['items'] if item['id'] == source)
        changed = self.edit(result['document'], [dict(op='vector', id=source,
            geometry=dict(shape='rect', x=0, y=0, width=4, height=3), fill=paint)])['document']
        self.assert_pixels(changed, [(0, 0, 4, 3, [255, 0, 0, 255]), (8, 0, 12, 3, [0, 0, 255, 255])])
        self.assertTrue(any(row.get('original') for row in result['reuse']))

    def test_nested_components_share_geometry_through_different_inherited_colors(self):
        result = self.imported(support.svg('<defs><rect id="dot" width="1" height="1"/>'
            '<g id="pair"><use href="#dot"/><use href="#dot" x="4"/></g></defs>'
            '<use href="#pair" x="2" fill="red"/><use href="#pair" x="16" fill="blue"/>'))
        source = self.source(result, 'dot')
        changed = self.edit(result['document'], [dict(op='vector', id=source,
            geometry=dict(shape='rect', x=0, y=0, width=2, height=3), fill=[255, 0, 0, 255])])['document']
        self.assert_pixels(changed, [(2, 0, 4, 3, [255, 0, 0, 255]), (6, 0, 8, 3, [255, 0, 0, 255]),
                                    (16, 0, 18, 3, [0, 0, 255, 255]), (20, 0, 22, 3, [0, 0, 255, 255])])
        self.assertEqual(sum(item['content']['type'] == 'component_source' for item in changed['items']), 2)
        for row in result['mapping']:
            for placement in row.get('instance_path', []):
                self.assertIn(placement['item_id'], {item['id'] for item in changed['items']})

    def test_resized_symbols_share_source_but_keep_separate_viewports(self):
        result = self.imported(support.svg('<symbol id="s" viewBox="0 0 4 4">'
            '<rect id="tile" width="2" height="2" fill="red"/></symbol>'
            '<use href="#s" width="8" height="8"/>'
            '<use href="#s" x="16" width="4" height="4"/>'))
        source = self.source(result, 'tile')
        changed = self.edit(result['document'], [dict(op='vector', id=source,
            geometry=dict(shape='rect', x=0, y=0, width=6, height=3), fill=[255, 0, 0, 255])])['document']
        self.assert_pixels(changed, [(0, 0, 8, 6, [255, 0, 0, 255]), (16, 0, 20, 3, [255, 0, 0, 255])])
        self.assertEqual(len({row['component_source_id'] for row in result['reuse']}), 1)

    def test_instance_unlink_detaches_only_the_selected_placement(self):
        result = self.imported(support.svg('<defs><rect id="r" width="2" height="2" fill="red"/></defs>'
            '<use id="a" href="#r"/><use id="b" href="#r" x="8"/>'))
        row = next(row for row in result['mapping'] if row['source_id'] == 'b')
        detached = self.edit(result['document'], [dict(op='instance_unlink', id=row['instance_item_id'])])['document']
        self.assertEqual(self.pixels(detached), self.pixels(result['document']))
        changed = self.edit(detached, [dict(op='vector', id=self.source(result, 'r'),
            geometry=dict(shape='rect', x=0, y=0, width=4, height=4), fill=[0, 255, 0, 255])])['document']
        self.assert_pixels(changed, [(0, 0, 4, 4, [0, 255, 0, 255]), (8, 0, 10, 2, [255, 0, 0, 255])])

    def test_limits_keep_valid_expanded_content_and_report_reason(self):
        many = '<defs><rect id="r" width="1" height="1"/></defs>' + '<use href="#r"/>' * 100
        result = self.imported(support.svg(many))
        self.assertEqual({row['reason'] for row in result['reuse']}, {'component_resource_budget'})
        self.assertFalse(any(item['content']['type'] == 'instance' for item in result['document']['items']))
        definitions = ''.join(f'<rect id="r{i}" width="1" height="1"/>' for i in range(33))
        placements = ''.join(f'<use href="#r{i}"/>' for i in range(33))
        result = self.imported(support.svg('<defs>' + definitions + '</defs>' + placements))
        self.assertEqual(sum(item['content']['type'] == 'component_source' for item in result['document']['items']), 32)
        self.assertEqual(sum(row.get('reason') == 'component_definition_limit' for row in result['reuse']), 1)

    def test_deep_original_and_native_reference_depth_preserve_group_fallback(self):
        body = '<g>' * 15 + '<rect id="r" width="1" height="1"/>' + '</g>' * 15 + '<use href="#r" x="4"/>'
        chain = '<defs>' + ''.join(f'<use id="u{i}" href="#u{i+1}"/>' for i in range(9))
        chain += '<rect id="u9" width="1" height="1"/></defs><use href="#u0"/>'
        for source in (body, chain):
            with self.subTest(source=source):
                result = self.imported(support.svg(source))
                self.assertEqual({row['reason'] for row in result['reuse']}, {'component_resource_budget'})
                self.assertFalse(any(item['content']['type'] == 'instance' for item in result['document']['items']))
                self.assert_pixels(result['document'], [(0, 0, 1, 1, [0, 0, 0, 255])] +
                                   ([(4, 0, 5, 1, [0, 0, 0, 255])] if source == body else []))

    def test_insertion_remaps_component_receipts_and_raster_expands(self):
        text = '<defs><rect id="tile" width="3" height="2"/></defs><use href="#tile" fill="red"/>'
        for kind in ('vector', 'raster'):
            with self.subTest(kind=kind):
                document = self.invoke(dict(command='document.create', id='target', kind=kind, width=32, height=24))
                if kind == 'raster':
                    document['resource_profile'] = 'large_raster'
                result = self.edit(document, [dict(op='add_svg', svg=text, prefix='shared')])
                receipt = result['changes'][0]['details']
                ids = {item['id'] for item in result['document']['items']}
                for row in receipt['mapping'] + receipt['reuse']:
                    for field in ('item_id', 'host_item_id', 'instance_item_id', 'component_source_id'):
                        if field in row:
                            self.assertIn(row[field], ids)
                    for entry in row.get('instance_path', []) + row.get('component_path', []):
                        for field in ('item_id', 'instance_item_id', 'component_source_id'):
                            if field in entry:
                                self.assertIn(entry[field], ids)
                self.assertEqual(receipt['reuse'][0]['mode'], 'component' if kind == 'vector' else 'expanded')
                self.assert_pixels(result['document'], [(0, 0, 3, 2, [255, 0, 0, 255])])

    def test_overlapping_reference_targets_share_original_and_nested_copies(self):
        result = self.imported(support.svg('<g id="group" fill="red"><rect id="child" width="2" height="2"/></g>'
            '<use href="#group" x="10" fill="blue"/><use href="#child" x="20" fill="lime"/>'))
        source = self.source(result, 'child')
        paint = next(item['content']['fill'] for item in result['document']['items'] if item['id'] == source)
        changed = self.edit(result['document'], [dict(op='vector', id=source,
            geometry=dict(shape='rect', x=0, y=0, width=4, height=3), fill=paint)])['document']
        self.assert_pixels(changed, [(0, 0, 4, 3, [255, 0, 0, 255]), (10, 0, 14, 3, [255, 0, 0, 255]),
                                    (20, 0, 24, 3, [0, 255, 0, 255])])
        self.assertEqual(sum(item['content']['type'] == 'component_source' for item in changed['items']), 2)

    def test_destination_component_limit_falls_back_atomically(self):
        document = self.invoke(dict(command='document.create', id='target', kind='vector', width=32, height=24))
        document['items'] = [dict(id=f's{i}', content=dict(type='component_source')) for i in range(32)]
        before = copy.deepcopy(document)
        result = self.edit(document, [dict(op='add_svg', svg='<defs><rect id="r" width="2" height="2"/></defs><use href="#r"/>')])
        self.assertEqual(result['changes'][0]['details']['reuse'][0]['reason'], 'destination_component_budget')
        self.assertEqual(document, before)
        self.assertEqual(sum(item['content']['type'] == 'component_source' for item in result['document']['items']), 32)
        self.assert_pixels(result['document'], [(0, 0, 2, 2, [0, 0, 0, 255])])

    def test_session_retry_undo_and_dependency_locks_preserve_shared_source(self):
        result = self.imported(support.svg('<defs><rect id="r" width="2" height="2"/></defs>'
            '<use id="a" href="#r"/><use id="b" href="#r" x="8"/>'))
        source = self.source(result, 'r')
        second = next(row['instance_item_id'] for row in result['mapping'] if row['source_id'] == 'b')
        locked = self.edit(result['document'], [dict(op='properties', id=second, locked=True)])['document']
        error = self.edit(locked, [dict(op='properties', id=source, visible=False)], 1)
        self.assertEqual(error['code'], 'LOCKED')
        client = Client(); self.addCleanup(client.close); client.initialize()
        with tempfile.TemporaryDirectory() as directory:
            common = dict(session_root=directory, session_id='shared-svg')
            client.success('session.create', **common, request_id='create', document=result['document'])
            request = dict(**common, request_id='change', expected_revision=0,
                action=dict(type='edit', operations=[dict(op='properties', id=source, visible=False)]))
            changed = client.success('session.apply', **request)
            self.assertTrue(client.success('session.apply', **request)['replayed'])
            self.assert_pixels(changed['document'], [])
            undo = client.success('session.apply', **common, request_id='undo', expected_revision=1, action=dict(type='undo'))
            self.assertEqual(undo['document']['items'], result['document']['items'])
            client.success('session.verify', **common)


class SvgComponentTextTests(unittest.TestCase):
    setUp = text_support.SvgTextTests.setUp
    invoke = text_support.SvgTextTests.invoke
    imported = text_support.SvgTextTests.imported
    pixels = text_support.SvgTextTests.pixels

    def test_text_contexts_partition_without_freezing_shared_text_edits(self):
        result = self.imported('<defs><text id="label" x="3.5" y="12" font-family="Geometry" font-size="10">A</text></defs>'
            '<use href="#label" fill="red"/><use href="#label" x="16" fill="red"/>'
            '<use href="#label" y="12" fill="blue"/>')
        rows = [row for row in result['mapping'] if row['source_id'] == 'label']
        self.assertEqual(rows[0]['item_id'], rows[1]['item_id'])
        self.assertNotEqual(rows[0]['item_id'], rows[2]['item_id'])
        self.assertTrue(any('separate component variants' in loss for loss in result['losses']))
        changed = self.invoke(dict(command='document.edit', document=result['document'], expected_revision=0,
            font_root=str(self.store), operations=[dict(op='text_range', id=rows[0]['item_id'], start=0, end=1, text='')]))['document']
        width, height, pixels = self.pixels(changed)
        self.assertEqual(pixels, bytes(v for y in range(height) for x in range(width)
            for v in ([0, 0, 255, 255] if 4 <= x < 8 and 17 <= y < 24 else [0]*4)))


if __name__ == '__main__':
    unittest.main()
