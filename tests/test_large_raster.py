"""Explicit larger raster layouts keep native precision and independent budgets."""
import copy
import json
import sys
import unittest
from contextlib import closing
from test_cli import EXE, ROOT
import test_agent_workspace as workspace
import test_samples_cli as samples
from test_mcp import Client

sys.path.insert(0, str(ROOT/'tools'))
import measure_workloads as measure
import native_layout_workload as layout


class LargeRasterTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli

    def document(self, count=257):
        d = self.cli('document.create', id='layout', kind='raster', width=64, height=64,
                     resource_profile='large_raster')
        d['items'] = [dict(id=f'p{i}', transform=[1, 0, 0, 1, i % 64, i//64],
                          content=dict(type='raster', width=1, height=1, rgba_hex='145096ff'))
                      for i in range(count)]
        return d

    def test_original_5000_annotation_native_layout_edit_and_history(self):
        case = measure.Case(EXE, self.root/'native-layout', layout.CASE, 1)
        row = layout.run(case)
        self.assertTrue(row['success'], row)
        self.assertEqual(row['process_calls'], 7)
        self.assertEqual(row['blocked_steps'], 0)
        self.assertEqual((case.root/'initial.tiff').read_bytes(), (case.root/'historical.tiff').read_bytes())
        self.assertNotEqual((case.root/'initial.tiff').read_bytes(), (case.root/'edited.tiff').read_bytes())

    def test_profile_is_explicit_reversible_discoverable_and_kind_specific(self):
        original = self.cli('document.create', id='small', kind='raster', width=2, height=2)
        self.assertNotIn('resource_profile', original)
        changed = self.cli('document.edit', document=original, expected_revision=0,
                          operations=[dict(op='resource_profile', profile='large_raster')])['document']
        self.assertEqual(changed, dict(original, resource_profile='large_raster', revision=1))
        restored = self.cli('document.edit', document=changed, expected_revision=1,
                           operations=[dict(op='resource_profile', profile='standard')])['document']
        self.assertEqual(restored, dict(original, revision=2))
        self.assertEqual(json.loads(self.cli('document.export', document=changed, format='snapshot')['data']), changed)
        self.assertEqual(self.cli('document.inspect', document=changed)['resource_profile'], 'large_raster')
        caps = self.cli('capabilities')['resource_profiles']['large_raster']
        self.assertEqual((caps['kind'], caps['items'], caps['geometry_commands'], caps['snapshot_bytes']),
                         ('raster', 8192, 131072, 8*1024*1024))
        self.assertFalse(caps['raises_processing_limits'])
        self.cli('document.create', id='wrong', kind='vector', width=2, height=2,
                 resource_profile='large_raster', error='INVALID_DOCUMENT')
        self.cli('document.create', id='wrong', kind='raster', width=2, height=2,
                 resource_profile='large_vector', error='INVALID_DOCUMENT')
        self.cli('document.validate', document=dict(changed, schema_version=1), error='INVALID_DOCUMENT')
        self.cli('svg.import', id='wrong', source=dict(kind='file', source_path='absent.svg'),
                 resource_profile='large_raster', error='INVALID_DOCUMENT')

    def test_item_inline_pixel_and_path_limits_remain_independent(self):
        d = self.document(8192)
        self.assertEqual(len(self.cli('document.validate', document=d)['items']), 8192)
        d['items'].append(dict(d['items'][0], id='overflow'))
        self.cli('document.validate', document=d, error='RESOURCE_LIMIT')
        d = self.document()
        standard = copy.deepcopy(d); standard.pop('resource_profile')
        self.cli('document.validate', document=standard, error='RESOURCE_LIMIT')
        self.cli('document.edit', document=d, expected_revision=0,
                 operations=[dict(op='resource_profile', profile='standard')], error='RESOURCE_LIMIT')
        self.assertEqual(d, self.document())
        d = self.document(0)
        d['items'] = [dict(id='too-many-inline-pixels', content=dict(type='raster', width=257, height=256,
                                                                  rgba_hex='145096ff'*(257*256)))]
        self.cli('document.validate', document=d, error='RESOURCE_LIMIT')
        d['items'] = [dict(id='too-many-commands', content=dict(type='vector', fill=[20, 80, 150, 255],
            geometry=dict(shape='path', commands=[dict(verb='move', to=[0, 0])]+[dict(verb='line', to=[1, 1])]*4096)))]
        self.cli('document.validate', document=d, error='RESOURCE_LIMIT')

    def test_mixed_geometry_and_snapshot_budgets_and_downgrade_are_explicit(self):
        d = self.document(0)
        commands = [dict(verb='move', to=[0, 0])]+[dict(verb='line', to=[i % 2, 1]) for i in range(4095)]
        item = dict(id='path', content=dict(type='vector', fill=[20, 80, 150, 255],
                                          geometry=dict(shape='path', commands=commands)))
        d['items'] = [dict(item, id=f'path{i}') for i in range(32)]
        self.cli('document.validate', document=d)
        overflow = copy.deepcopy(d); overflow['items'].append(dict(item, id='overflow'))
        self.cli('document.validate', document=overflow, error='RESOURCE_LIMIT')
        cubic = dict(verb='cubic', to=[.12345678901234568, .9876543210987654],
                     control1=[.12345678901234568, .9876543210987654],
                     control2=[.12345678901234568, .9876543210987654])
        large_path = dict(shape='path', commands=[commands[0]]+[cubic]*4095)
        large_item = dict(id='large', content=dict(type='vector', fill=[20, 80, 150, 255], geometry=large_path))
        large = dict(d, items=[dict(large_item, id=f'large{i}') for i in range(16)])
        failure = self.cli('document.validate', document=large, error='RESOURCE_LIMIT')
        self.assertIn('Snapshot', failure['message'])
        d['items'] = [item]
        self.cli('document.edit', document=d, expected_revision=0,
                 operations=[dict(op='resource_profile', profile='standard')], error='INVALID_DOCUMENT')
        standard = copy.deepcopy(d); standard.pop('resource_profile')
        self.cli('document.validate', document=standard, error='INVALID_DOCUMENT')

    def test_mcp_proposal_retry_undo_and_redo_preserve_profile_and_historical_revision(self):
        d = self.document()
        with closing(Client(workspace=self.root)) as c:
            c.initialize()
            initial = c.success('session.create', session_id='large', request_id='create', document=d)['document']
            failure = c.tool('session.apply', session_id='large', request_id='bad', expected_revision=0,
                             action=dict(type='edit', operations=[dict(op='resource_profile', profile='standard')]))
            self.assertEqual(failure['structuredContent']['error']['code'], 'RESOURCE_LIMIT')
            action = dict(type='edit', operations=[dict(op='remove', id='p256'),
                                                  dict(op='resource_profile', profile='standard')])
            proposed = c.success('session.dry_run', session_id='large', request_id='revise', expected_revision=0,
                                 action=action, options=dict(include_document=True))
            self.assertTrue(proposed['dry_run'])
            self.assertFalse(proposed['committed'])
            self.assertEqual(c.success('session.read', session_id='large')['document'], initial)
            changed = c.success('session.apply_proposal', proposal=proposed['proposal'], action=action)
            self.assertEqual(changed['document'], proposed['proposed_document'])
            self.assertNotIn('resource_profile', changed['document'])
            self.assertEqual(len(changed['document']['items']), 256)
            replay = c.success('session.apply_proposal', proposal=proposed['proposal'], action=action)
            self.assertTrue(replay['replayed'])
            self.assertEqual(replay['document'], changed['document'])
            undo = c.success('session.apply', session_id='large', request_id='undo', expected_revision=1, action=dict(type='undo'))
            self.assertEqual(undo['document'], dict(initial, revision=2))
            redo = c.success('session.apply', session_id='large', request_id='redo', expected_revision=2, action=dict(type='redo'))
            self.assertEqual(redo['document'], dict(changed['document'], revision=3))
            historical = c.success('document.export', document=dict(session_id='large', revision=0), format='snapshot')
            self.assertEqual(json.loads(historical['data']), initial)
            self.assertTrue(c.success('session.verify', session_id='large')['valid'])

    def test_dense_overlap_and_cancelled_publication_do_not_gain_processing_budget(self):
        d = self.document(300)
        for item in d['items']: item['transform'] = [512, 0, 0, 512, 0, 0]
        d['width'] = d['height'] = 512
        self.cli('document.export', document=d, format='png', render_options=dict(evaluation='tiled'), error='RESOURCE_LIMIT')
        self.cli('document.publish', document=d, output=dict(file_name='cancelled.png', format='png',
                 render_options=dict(evaluation='tiled')), control=dict(timeout_ms=0), error='TIMEOUT')
        self.assertFalse((self.root/'cancelled.png').exists())

    def test_native_pixels_and_curved_vector_overlays_share_whole_and_indexed_semantics(self):
        d = self.document(140)
        for item in d['items']: item['transform'][5] += 1000
        native = samples.layer([10001, 20002, 30003, 65535]*4, w=2, transform=[32, 0, 0, 32, 0, 0])
        overlay = dict(id='curve', parent='group', opacity=.625,
            content=dict(type='vector', geometry=dict(shape='ellipse', cx=20.375, cy=21.25, rx=11.5, ry=6.625),
                         fill=[170, 90, 200, 213], stroke=dict(width=1.75, color=[240, 30, 100, 173])),
            clip=dict(geometry=dict(shape='rect', x=14.25, y=9.5, width=19.5, height=27.25)))
        group = dict(id='group', transform=[1, .125, -.125, 1, 4.25, 1.5],
                     mask=dict(width=2, height=1, gray_hex='b0e0', transform=[24, 0, 0, 48, 0, 0]),
                     content=dict(type='group', isolated=True))
        d['items'] = [native]+d['items']+[overlay, group]
        before = copy.deepcopy(d)
        for aa in ('coverage', 'supersample2'):
            results = [self.cli('document.export', document=d, format='tiff',
                               image_options=dict(depth='u16', compression='deflate'),
                               render_options=dict(evaluation=mode, antialias=aa, padding=3))
                       for mode in ('whole', 'tiled')]
            self.assertEqual(samples.decode(results[0])[0], samples.decode(results[1])[0])
        self.assertEqual(d, before)


if __name__ == '__main__': unittest.main()
