"""Content-bound paging through actual CLI/MCP, with independent field/coordinate checks."""
from contextlib import closing
import copy
import json
import unittest

import test_agent_workspace as workspace
from test_mcp import Client


def rectangle(i):
    return dict(id=f'item-{i:04}', name=f'Original item {i}', visible=i % 7 != 0, locked=i % 11 == 0,
                content=dict(type='vector', geometry=dict(shape='rect', x=i, y=2, width=1, height=3), fill=[20, 80, 170, 255]))


class PagedInspectionTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli
    document = workspace.AgentWorkspaceTests.document
    save = workspace.AgentWorkspaceTests.save
    ref = workspace.AgentWorkspaceTests.ref

    def page(self, doc, **options):
        return self.cli('document.inspect.page', document=doc, options=options)

    def all_records(self, doc, **options):
        records = []; cursor = None
        while True:
            page = self.page(doc, **options, cursor=cursor)
            self.assertLessEqual(len(json.dumps(page, separators=(',', ':')).encode()), 32768)
            self.assertEqual(page['offset'], len(records))
            records.extend(page['records'])
            cursor = page['next_cursor']
            if cursor is None:
                self.assertEqual(len(records), page['total'])
                return records

    def test_large_inventory_pages_selected_fields_and_exact_bounds(self):
        doc = self.document(); doc['resource_profile'] = 'large_vector'
        doc['items'] = [rectangle(i) for i in range(513)]
        source = copy.deepcopy(doc)
        records = self.all_records(doc, limit=128, view=dict(collection='items', fields=['name', 'bounds']))
        self.assertEqual([r['id'] for r in records], [i['id'] for i in doc['items']])
        for i, row in enumerate(records):
            self.assertEqual(row, dict(id=f'item-{i:04}', index=i, name=f'Original item {i}', geometry_bounds=[i, 2, i+1, 5]))
        self.assertEqual(doc, source)
        selected = self.page(doc, view=dict(collection='items', ids=['item-0012', 'item-0000'], fields=[]))
        self.assertEqual(selected['records'], [dict(id='item-0000', index=0), dict(id='item-0012', index=12)])
        empty = self.page(doc, view=dict(collection='items', types=['raster']))
        self.assertEqual(empty['records'], []); self.assertIsNone(empty['next_cursor'])

    def test_default_fields_hierarchy_locks_and_legacy_semantics_agree(self):
        doc = self.document()
        doc['items'] = [dict(id='group', transform=[1, 0, 0, 1, 10, 20], visible=False, locked=True, content=dict(type='group')),
                        rectangle(1), rectangle(2)]
        doc['items'][1]['parent'] = 'group'
        full = self.cli('document.inspect', document=doc)
        rows = self.all_records(doc, limit=1)
        for row, old in zip(rows, full['items']):
            for key, value in row.items():
                if key != 'edit_blocked_by_locks': self.assertEqual(value, old[key])
        self.assertFalse(rows[1]['effective_visible']); self.assertTrue(rows[1]['edit_blocked_by_locks'])
        self.assertEqual(rows[1]['geometry_bounds'], [11, 22, 12, 25])
        self.assertFalse(rows[2]['edit_blocked_by_locks'])

    def test_cursor_binds_content_view_limit_and_saved_history(self):
        doc = self.document(); doc['items'] = [rectangle(i) for i in range(5)]
        doc['items'][1]['locked'] = False
        self.save(doc)
        first = self.page(self.ref(), limit=2)
        cursor = first['next_cursor']
        for changed in [dict(doc, revision=1), dict(doc, width=3), dict(doc, items=list(reversed(doc['items'])))]:
            self.cli('document.inspect.page', document=changed, options=dict(limit=2, cursor=cursor), error='STALE_CURSOR')
        for options in [dict(limit=3), dict(limit=2, view=dict(collection='items', fields=[]))]:
            self.cli('document.inspect.page', document=doc, options=dict(**options, cursor=cursor), error='STALE_CURSOR')
        for offset in ['0', '01', '-1', '5', '9999999999999999999999999']:
            malformed = cursor.rsplit(':', 1)[0] + ':' + offset
            self.cli('document.inspect.page', document=doc, options=dict(limit=2, cursor=malformed), error='INVALID_CURSOR')
        self.cli('session.apply', session_id='work', request_id='rename', expected_revision=0,
                 action=dict(type='edit', operations=[dict(op='properties', id='item-0001', name='New name')]))
        expected = self.page(self.ref(), limit=2, cursor=cursor)
        with closing(Client(('--tools', 'core'), workspace=self.root)) as c:
            c.initialize()
            self.assertEqual(c.success('document.inspect.page', document=self.ref(), options=dict(limit=2, cursor=cursor)), expected)
            self.assertEqual(c.tool('document.inspect.page', document=self.ref(1), options=dict(limit=2, cursor=cursor))['structuredContent']['error']['code'], 'STALE_CURSOR')
        self.assertEqual(self.cli('session.read', session_id='work')['current_revision'], 1)

    def test_anchor_pages_preserve_indices_handles_contours_and_compound_placement(self):
        commands = [dict(cmd='move', to=[0, 0]), dict(cmd='cubic', control1=[1, 0], control2=[2, 3], to=[3, 3]), dict(cmd='line', to=[0, 3]), dict(cmd='close'),
                    dict(cmd='move', to=[5, 5]), dict(cmd='line', to=[6, 5])]
        doc = self.document()
        doc['items'] = [dict(id='path', transform=[2, 0, 0, 3, 7, 11], content=dict(type='work_path', geometry=dict(shape='path', commands=commands)))]
        for command in commands: command['verb'] = command.pop('cmd')
        rows = self.all_records(doc, limit=2, view=dict(collection='anchors', id='path'))
        self.assertEqual([r['command_index'] for r in rows], [0, 1, 2, 4, 5])
        self.assertEqual([r['contour_index'] for r in rows], [0, 0, 0, 1, 1])
        self.assertEqual([r['anchor_index'] for r in rows], [0, 1, 2, 0, 1])
        for row in rows:
            x, y = row['local']; self.assertEqual(row['world'], [2*x+7, 3*y+11])
        self.assertEqual(rows[1]['incoming_segment_handles']['world_control2'], [11, 20])
        legacy = self.cli('document.query', document=doc, query=dict(include_anchors=True))
        self.assertEqual(rows, legacy['items'][0]['anchors'])
        leaf = doc['items'][0]['content']['geometry']
        doc['items'][0]['content']['geometry'] = dict(shape='compound',mode='union',operands=[
            dict(geometry=leaf,transform=[1,0,0,1,0,0]),
            dict(geometry=leaf,transform=[1,0,0,1,10,0])])
        compound = self.all_records(doc,limit=3,view=dict(collection='anchors',id='path'))
        self.assertEqual([r['component'] for r in compound], [[0]]*5+[[1]]*5)
        for first,second in zip(compound[:5],compound[5:]):
            self.assertEqual(second['world'],[first['world'][0]+20,first['world'][1]])
        legacy = self.cli('document.query',document=doc,query=dict(include_anchors=True))
        self.assertEqual(compound,legacy['items'][0]['anchors'])

    def test_byte_budget_large_geometry_resources_and_invalid_requests(self):
        doc = self.document(); doc['items'] = [rectangle(i) for i in range(4)]
        for item in doc['items']: item['metadata'] = dict(description='x'*8000, note='y'*7000)
        page = self.page(doc, limit=128, view=dict(collection='items', fields=['metadata']))
        self.assertEqual(page['returned'], 1); self.assertIsNotNone(page['next_cursor'])
        self.assertEqual(len(self.all_records(doc, limit=128, view=dict(collection='items', fields=['metadata']))), 4)
        for options, code in [(dict(limit=0),'INVALID_REQUEST'), (dict(limit=129),'INVALID_REQUEST'),
                              (dict(view=dict(collection='items', fields=['name','name'])),'INVALID_REQUEST'),
                              (dict(view=dict(collection='items', fields=['unknown'])),'INVALID_REQUEST'),
                              (dict(view=dict(collection='items', ids=['missing'])),'INSPECTION_ID_NOT_FOUND'),
                              (dict(view=dict(collection='items', ids=['item-0001','item-0001'])),'INVALID_REQUEST')]:
            self.cli('document.inspect.page', document=doc, options=options, error=code)
        self.cli('document.inspect.page', document=doc, control=dict(timeout_ms=0), error='TIMEOUT')
        doc = self.document()
        doc['assets'] = {name:dict(width=1,height=1,sha256=digit*64,storage=dict(type='stored')) for name,digit in [('z','0'),('a','1')]}
        doc['fonts'] = {name:dict(sha256=digit*64,license_sha256='a'*64,face_index=0,bytes=4) for name,digit in [('z','0'),('a','1')]}
        self.assertEqual([r['id'] for r in self.all_records(doc,limit=1,view=dict(collection='assets'))], ['a','z'])
        self.assertEqual([r['id'] for r in self.all_records(doc,limit=1,view=dict(collection='fonts'))], ['a','z'])
        self.assertFalse((self.root/'.inkbolt').exists())

    def test_oversized_geometry_has_actionable_error_and_paged_anchor_recovery(self):
        doc=self.document()
        commands=[dict(verb='move',to=[0,0])]+[dict(verb='line',to=[i%100,i//100]) for i in range(1,1201)]
        doc['items']=[dict(id='large-path',content=dict(type='work_path',geometry=dict(shape='path',commands=commands)))]
        error=self.cli('document.inspect.page',document=doc,options=dict(view=dict(collection='items',fields=['geometry'])),error='INSPECTION_RECORD_TOO_LARGE')
        self.assertIn('anchors',error['message'])
        anchors=self.all_records(doc,limit=128,view=dict(collection='anchors',id='large-path'))
        self.assertEqual(len(anchors),1201)
        self.assertEqual([a['command_index'] for a in anchors],list(range(1201)))
        self.assertEqual([a['local'] for a in anchors],[c['to'] for c in commands])


if __name__ == '__main__': unittest.main()
