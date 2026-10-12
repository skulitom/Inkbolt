"""Original pixel, identity, resource and transactional oracles for SVG authoring."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from advertised_limits import capabilities
from external_workspace import files as workspace_files
from synthetic_font import geometric_font
from test_mcp import Client
from test_svg_import_cli import svg
import test_transfer_cli as transfer


BOX = '<rect id="box" x="2" y="3" width="4" height="5" fill="#2864dc"/>'


class SvgInsertionTests(unittest.TestCase):
    invoke = transfer.TransferTests.invoke
    create = transfer.TransferTests.create
    edit = transfer.TransferTests.edit
    pixels = transfer.TransferTests.pixels

    def insert(self, document, source=BOX, expected=0, resources=None, **options):
        return self.edit(document, dict(op='add_svg', svg=source, **options),
                         expected=expected, **(resources or {}))

    def details(self, result):
        return result['changes'][0]['details']

    def mapped(self, result, source_id):
        identifier = next(row['item_id'] for row in self.details(result)['mapping']
                          if row['source_id'] == source_id)
        return transfer.byid(result['document'], identifier)

    def test_fragment_parent_local_pixels_and_unchanged_destination(self):
        document = self.create()
        document['items'] = [transfer.group('parent', transform=[2, 0, 0, 2, 10, 2]),
                             transfer.rect('existing', x=1, y=1)]
        normalized = self.invoke(dict(command='document.validate', document=document))
        source = '<!-- original é -->' + BOX
        result = self.insert(document, source, parent='parent')
        out, receipt = result['document'], self.details(result)
        self.assertEqual(result, self.insert(document, source, parent='parent'))
        self.assertEqual(receipt['source'], dict(kind='svg_fragment', bytes=len(source.encode()),
                         sha256=hashlib.sha256(source.encode()).hexdigest()))
        self.assertEqual(receipt['placement'], 'parent_local')
        self.assertFalse(receipt['viewport_clipped'])
        root = transfer.byid(out, receipt['root_id'])
        self.assertEqual(root['parent'], 'parent')
        self.assertEqual(root['transform'], [1, 0, 0, 1, 0, 0])
        synthetic = receipt['mapping'][0]
        self.assertTrue(synthetic['synthetic'])
        self.assertIsNone(synthetic['byte_offset'])
        self.assertEqual(receipt['mapping'][1]['byte_offset'], source.encode().index(b'<rect'))
        self.assertEqual(out['items'][:2], normalized['items'])
        self.assertEqual({k:v for k,v in out.items() if k not in ('items', 'revision')},
                         {k:v for k,v in normalized.items() if k not in ('items', 'revision')})
        for scale in (1, 2):
            w, h, pixels = self.pixels(out, scale)
            expected = bytes(v for y in range(h) for x in range(w) for v in
                             ([40,100,220,255] if (14 <= (x+.5)/scale < 22 and 8 <= (y+.5)/scale < 18)
                              or (1 <= (x+.5)/scale < 5 and 1 <= (y+.5)/scale < 5) else [0]*4))
            self.assertEqual(pixels, expected)
        snapshot = self.invoke(dict(command='document.export', document=out, format='snapshot'))
        self.assertEqual(json.loads(snapshot['data']), out)

    def test_full_svg_retains_viewbox_viewport_and_root_clip(self):
        body = ('<defs><clipPath id="cut"><rect width="20" height="3"/></clipPath></defs>'
                '<rect id="box" x="-10" y="-10" width="30" height="30" fill="red"/>')
        source = svg(body, 'width="8" height="8" viewBox="0 0 4 4" clip-path="url(#cut)"')
        document = self.create()
        document['items'] = [transfer.group('parent', transform=[2,0,0,1,10,2])]
        result = self.insert(document, source, parent='parent')
        receipt = self.details(result)
        self.assertTrue(receipt['viewport_clipped'])
        self.assertEqual(receipt['source']['kind'], 'svg_document')
        self.assertEqual(receipt['mapping'][0]['byte_offset'], 0)
        w, h, pixels = self.pixels(result['document'])
        self.assertEqual(pixels, bytes(v for y in range(h) for x in range(w) for v in
                                     ([255,0,0,255] if 10 <= x < 26 and 2 <= y < 8 else [0]*4)))

    def test_generated_ids_repeated_insert_explicit_collision_and_followup_edit(self):
        document = self.create()
        first = self.insert(document)
        second = self.insert(first['document'])
        self.assertEqual(self.details(first)['prefix'], 'svg-1')
        self.assertEqual(self.details(second)['prefix'], 'svg-2')
        self.assertEqual(second['document']['revision'], 2)
        self.assertTrue(set(self.details(first)['item_ids'].values()).isdisjoint(
                        self.details(second)['item_ids'].values()))
        self.insert(first['document'], prefix='svg-1', expected=1)
        result = self.edit(document, dict(op='add_svg', svg=BOX, prefix='p'),
                           dict(op='properties', id='p-svg-1', visible=False))
        self.assertFalse(transfer.byid(result['document'], 'p-svg-1')['visible'])
        self.assertEqual(result['changes'][0]['action'], 'svg_added')
        self.assertEqual(result['changes'][0]['id'], 'p-svg-0')

    def test_fragment_definitions_masks_clips_gradient_and_editable_geometry(self):
        source = ('<defs><linearGradient id="paint" x2="1"><stop offset="0" stop-color="red"/>'
                  '<stop offset="1" stop-color="red"/></linearGradient>'
                  '<clipPath id="clip"><rect width="6" height="8"/></clipPath>'
                  '<mask id="mask" maskUnits="userSpaceOnUse" x="0" y="0" width="8" height="8">'
                  '<rect width="8" height="4" fill="white"/></mask></defs>'
                  '<rect id="box" width="8" height="8" fill="url(#paint)" '
                  'clip-path="url(#clip)" mask="url(#mask)"/>')
        document = self.create()
        document['items'] = [transfer.group('parent', transform=[2,0,0,2,10,2])]
        result = self.insert(document, source, parent='parent')
        item = self.mapped(result, 'box')
        mask = transfer.byid(result['document'], item['artwork_mask']['source'])
        self.assertEqual(mask['content']['type'], 'mask_source')
        self.assertIsNone(mask.get('parent'))
        w, h, pixels = self.pixels(result['document'])
        self.assertEqual(pixels, bytes(v for y in range(h) for x in range(w) for v in
                                     ([255,0,0,255] if 10 <= x < 22 and 2 <= y < 10 else [0]*4)))
        ids = {i['id'] for i in result['document']['items']}
        for row in self.details(result)['mapping']:
            self.assertIn(row['item_id'], ids)
        arc = self.insert(document, '<path id="curve" d="M8 0 A8 8 0 0 1 0 8"/>')
        self.assertEqual(self.mapped(arc, 'curve')['content']['geometry']['shape'], 'path')
        self.assertEqual(self.details(arc)['approximations'][0]['byte_offset'], 0)
        self.assertTrue(self.details(arc)['losses'])
        encoded = self.invoke(dict(command='document.export', document=result['document'], format='svg'))
        reopened = self.invoke(dict(command='svg.import', id='reopened', source=dict(kind='text', text=encoded['data'])))
        self.assertEqual(self.pixels(reopened['document']), self.pixels(result['document']))

    def test_destination_compositing_and_profiles_match_native_edits(self):
        for kind, profile in [('vector', 'standard'), ('vector', 'large_vector'),
                              ('raster', 'large_raster')]:
            for space in (('srgb', 'linear_srgb') if kind == 'raster' else ('srgb',)):
                with self.subTest(kind=kind, profile=profile, space=space):
                    document = self.create(kind=kind)
                    document.update(resource_profile=profile, color_space=space)
                    document['items'] = [transfer.rect('back', x=2, y=3, width=4, height=5,
                                                       color=[255,0,0,255])]
                    result = self.insert(document, BOX.replace('fill="#2864dc"', 'fill="blue" opacity=".5"'))
                    manual = self.edit(document, dict(op='add', item=dict(
                        transfer.rect('manual', x=2, y=3, width=4, height=5, color=[0,0,255,255]), opacity=.5)))
                    options = dict(render_options=dict(view=dict(tone_map='clip'))) if space == 'linear_srgb' else {}
                    self.assertEqual(self.pixels(result['document'], **options), self.pixels(manual['document'], **options))
                    self.assertEqual(result['document'].get('resource_profile', 'standard'), profile)
                    self.assertEqual(result['document']['kind'], kind)
        # The standard raster profile permits vector geometry only inside
        # nonprinting mask sources. Insertion observes that existing contract.
        document = self.create(kind='raster')
        self.assertEqual(self.insert(document, expected=1)['code'], 'INVALID_DOCUMENT')
        document['items'] = [dict(id='mask', content=dict(type='mask_source'))]
        result = self.insert(document, parent='mask')
        self.assertEqual(self.pixels(result['document'])[2], bytes(document['width']*document['height']*4))

    def test_font_reuse_pinned_bytes_and_failure_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            font_path = root/'original.ttf'; font_path.write_bytes(geometric_font())
            license_path = root/'LICENSE'; license_path.write_bytes((Path(__file__).resolve().parents[1]/'LICENSE').read_bytes())
            store = root/'fonts'
            font = self.invoke(dict(command='font.import', source_path=str(font_path),
                                   license_path=str(license_path), store_root=str(store)))
            document = self.create(); document['fonts'] = {'existing': font}
            bindings = [dict(family='Geometry', font_id='existing')]
            source = '<text id="label" x="3.5" y="12" font-family="Geometry" font-size="10" fill="#205080">AA</text>'
            files_before = {str(p): p.read_bytes() for p in workspace_files(root) if p.is_file()}
            first = self.insert(document, source, font_bindings=bindings, resources=dict(font_root=str(store)))
            second = self.insert(first['document'], source, font_bindings=bindings, resources=dict(font_root=str(store)))
            self.assertEqual(second['document']['fonts'], {'existing': font})
            self.assertEqual(self.details(second)['font_ids'], {'existing': 'existing'})
            self.assertEqual(self.mapped(first, 'label')['content']['type'], 'text')
            w, h, pixels = self.pixels(first['document'], font_root=str(store))
            self.assertEqual(pixels, bytes(v for y in range(h) for x in range(w) for v in
                                         ([32,80,128,255] if 5 <= y < 12 and (4 <= x < 8 or 10 <= x < 14) else [0]*4)))
            self.assertEqual(files_before, {str(p): p.read_bytes() for p in workspace_files(root) if p.is_file()})
            missing = self.insert(document, source, expected=1, resources=dict(font_root=str(store)))
            self.assertEqual(missing['code'], 'SVG_FONT_NOT_BOUND')
            self.assertEqual(self.insert(document, source, expected=1, font_bindings=bindings)['code'], 'FONT_ROOT_REQUIRED')
            (store/(font['sha256']+'.font')).write_bytes(b'corrupt original fixture')
            self.assertEqual(self.insert(document, source, expected=1, font_bindings=bindings,
                             resources=dict(font_root=str(store)))['code'], 'FONT_CORRUPT')

    def test_request_derived_bytes_and_existing_node_item_limits(self):
        caps = capabilities()['svg_import']
        self.assertEqual(caps['insertion']['source_bytes'], capabilities()['agent_inputs']['request_bytes'])
        source = '<!--' + 'x'*caps['source_bytes'] + '-->' + BOX
        self.assertGreater(len(source), caps['source_bytes'])
        self.insert(self.create(), source)
        self.assertEqual(self.invoke(dict(command='svg.import', id='small', source=dict(kind='text', text=svg(source))), 1)['code'], 'RESOURCE_LIMIT')
        for source in ['<!--x-->'*caps['xml_nodes'] + BOX,
                       '<rect width="1" height="1"/>'*capabilities()['resource_profiles']['standard']['items']]:
            self.insert(self.create(), source, expected=1)
        self.insert(self.create(), prefix='x'*(caps['insertion']['prefix_bytes']+1), expected=1)

    def test_invalid_inputs_locked_ancestors_and_batch_rollback(self):
        document = self.create()
        document['items'] = [transfer.group('locked', locked=True), transfer.group('child', 'locked'), transfer.rect('shape')]
        for parent, code in [('locked','LOCKED'), ('child','LOCKED'), ('missing','NOT_FOUND'), ('shape','INVALID_REQUEST')]:
            with self.subTest(parent=parent):
                error = self.insert(document, parent=parent, expected=1)
                self.assertEqual(error['code'], code)
                self.assertNotIn('document', error)
        for source in ['<rect>', '<image href="file:///absent"/>', '<script/>',
                       '<!DOCTYPE svg><svg/>', '<svg xmlns="foreign"/>',
                       '<rect id="same"/><rect id="same"/>']:
            error = self.edit(document, dict(op='add_svg', svg=BOX), dict(op='add_svg', svg=source), expected=1)
            self.assertNotIn('document', error)
        self.insert(document, prefix='', expected=1)
        self.insert(document, font_bindings=[dict(family='Geometry', font_id='absent')], expected=1)
        self.insert(document, unsupported='omit', expected=1)

    def test_mcp_session_dry_run_apply_retry_undo_redo_and_stale_revision(self):
        client = Client(('--tools', 'core')); self.addCleanup(client.close); client.initialize()
        schema = client.success('schema.lookup', name='operation', select='add_svg')
        self.assertEqual(schema['schema']['properties']['op']['const'], 'add_svg')
        with tempfile.TemporaryDirectory() as directory:
            common = dict(session_root=directory, session_id='svg')
            document = self.create()
            client.success('session.create', **common, request_id='create', document=document)
            action = dict(type='edit', operations=[dict(op='add_svg', svg=BOX)])
            files_before = {str(p): p.read_bytes() for p in workspace_files(Path(directory)) if p.is_file()}
            predicted = client.success('session.dry_run', **common, request_id='insert', expected_revision=0,
                                       action=action, options=dict(include_document=True))
            self.assertEqual(files_before, {str(p): p.read_bytes() for p in workspace_files(Path(directory)) if p.is_file()})
            applied = client.success('session.apply_proposal', session_root=directory, proposal=predicted['proposal'], action=action)
            self.assertEqual(applied['document'], predicted['proposed_document'])
            self.assertEqual(applied['receipt'], predicted['predicted_receipt'])
            replayed = client.success('session.apply', **common, request_id='insert', expected_revision=0, action=action)
            self.assertTrue(replayed['replayed'])
            self.assertEqual(applied['receipt'], replayed['receipt'])
            self.assertEqual(self.invoke(dict(command='session.read', **common))['document'], applied['document'])
            stale = self.invoke(dict(command='session.apply', **common, request_id='stale', expected_revision=0, action=action), 1)
            self.assertEqual(stale['code'], 'REVISION_CONFLICT')
            failed = self.invoke(dict(command='session.apply', **common, request_id='bad', expected_revision=1,
                action=dict(type='edit', operations=[dict(op='add_svg', svg=BOX), dict(op='add_svg', svg='<image/>')])), 1)
            self.assertNotIn('document', failed)
            self.assertEqual(client.success('session.read', **common)['document'], applied['document'])
            undone = client.success('session.apply', **common, request_id='undo', expected_revision=1, action=dict(type='undo'))
            self.assertEqual(undone['document']['items'], [])
            redone = client.success('session.apply', **common, request_id='redo', expected_revision=2, action=dict(type='redo'))
            self.assertEqual(redone['document']['items'], applied['document']['items'])
            self.assertFalse(client.tool('run', command='session.verify', arguments=common)['isError'])

    def test_document_metadata_exclusion_item_metadata_and_schema_example(self):
        source = self.create('source')
        source['metadata'] = dict(title='Source document')
        source['items'] = [dict(transfer.rect('art'), metadata=dict(title='Source item'))]
        encoded = self.invoke(dict(command='document.export', document=source, format='svg'))['data']
        destination = self.create()
        destination['metadata'] = dict(title='Destination document')
        result = self.insert(destination, encoded)
        self.assertEqual(result['document']['metadata']['title'], 'Destination document')
        self.assertEqual(self.mapped(result, 'art')['metadata']['title'], 'Source item')
        self.assertTrue(any('excludes source document metadata' in loss for loss in self.details(result)['losses']))
        example = json.loads((Path(__file__).resolve().parents[1]/'examples/add-svg.json').read_text())
        result = self.invoke(example)
        self.assertEqual(self.details(result)['prefix'], 'badge')
        self.assertEqual(len(self.details(result)['approximations']), 1)


if __name__ == '__main__':
    unittest.main()
