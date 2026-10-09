"""Compact discovery and routed execution, checked through independent processes."""
from contextlib import closing
import json
from pathlib import Path
import tempfile
import unittest

from test_mcp import Client
from test_sessions_cli import invoke


def catalog(client):
    result = []
    cursor = None
    while True:
        page = client.rpc('tools/list', {} if cursor is None else {'cursor': cursor})['result']
        result.extend(page['tools'])
        cursor = page.get('nextCursor')
        if cursor is None:
            return result


class AgentDiscoveryTests(unittest.TestCase):
    def test_small_catalog_and_schema_lookup_preserve_legacy_discovery(self):
        with closing(Client(('--tools', 'core'))) as core, closing(Client()) as full:
            core.initialize(); full.initialize()
            small, large = catalog(core), catalog(full)
            size = len(json.dumps(small, separators=(',', ':')).encode())
            self.assertLessEqual(size, 96 * 1024)
            self.assertLess(size * 10, len(json.dumps(large, separators=(',', ':')).encode()))
            routed = next(t for t in small if t['name'] == 'inkbolt_run')
            self.assertEqual(set(routed['inputSchema']['properties']['command']['enum']),
                             set(full.success('capabilities')['commands']))
            self.assertEqual(core.rpc('tools/list', {'cursor': 'inkbolt-tools-v1:8'})['error']['code'], -32602)
            focused = core.success('schema.lookup', name='operation', select='transform')
            self.assertEqual(focused, invoke({'command': 'schema.lookup', 'name': 'operation', 'select': 'transform'})['result'])
            self.assertEqual(focused['schema']['properties']['op']['const'], 'transform')
            self.assertEqual(core.success('schema.lookup', name='document')['detail'], 'outline')
            self.assertEqual(core.success('schema.lookup', name='document', full=True)['detail'], 'full')
            schema = core.tool('run', command='schema', arguments={})['structuredContent']['result']
            self.assertEqual(schema, full.success('schema'))

    def test_routed_edit_render_retry_conflict_and_undo_match_direct_execution(self):
        with closing(Client(('--tools', 'core'))) as c, tempfile.TemporaryDirectory() as directory:
            c.initialize()
            def run(command, **arguments):
                r = c.tool('run', command=command, arguments=arguments)
                self.assertFalse(r['isError'], r)
                return r['structuredContent']['result']
            doc = run('document.create', id='compact', kind='vector', width=8, height=8)
            item = dict(id='square', content=dict(type='vector', geometry=dict(shape='rect', x=1, y=2, width=3, height=4), fill=[20,60,180,255]))
            edited = run('document.edit', document=doc, expected_revision=0, operations=[dict(op='add', item=item)])
            self.assertEqual(edited, invoke(dict(command='document.edit', document=doc, expected_revision=0, operations=[dict(op='add', item=item)]))['result'])
            self.assertEqual(run('document.render', document=edited['document']), c.success('document.render', document=edited['document']))
            s = dict(session_root=directory, session_id='compact')
            run('session.create', **s, request_id='create', document=doc)
            request = dict(**s, request_id='add', expected_revision=0, action=dict(type='edit', operations=[dict(op='add', item=item)]))
            first = run('session.apply', **request)
            repeated = run('session.apply', **request)
            self.assertTrue(repeated['replayed']); self.assertEqual(first['receipt'], repeated['receipt'])
            conflict = c.tool('run', command='session.apply', arguments={**request, 'request_id': 'stale'})
            self.assertEqual(conflict['structuredContent']['error']['code'], 'REVISION_CONFLICT')
            output = dict(output_root=directory, file_name='compact.png', format='png')
            published = run('session.publish', **s, expected_revision=1, output=output)
            before = Path(published['path']).read_bytes()
            self.assertEqual(c.tool('run', command='session.publish', arguments=dict(**s, expected_revision=1, output=output))['structuredContent']['error']['code'], 'OUTPUT_EXISTS')
            self.assertEqual(Path(published['path']).read_bytes(), before)
            run('session.apply', **s, request_id='undo', expected_revision=1, action=dict(type='undo'))
            self.assertFalse(run('session.diff', **s, from_revision=0, to_revision=2, compare_pixels=True)['changed'])

    def test_dispatcher_cannot_bypass_validation_or_reach_unknown_commands(self):
        with closing(Client(('--tools', 'core'))) as c:
            c.initialize()
            for args in [dict(command='unknown', arguments={}), dict(command='capabilities', arguments=[], extra=True),
                         dict(command='capabilities', arguments={'command': 'document.create'}),
                         dict(command='capabilities', arguments={}, unexpected=1),
                         dict(command='document.create', arguments=dict(id='bad', kind='vector', width=2, height=2, unexpected=1)),
                         dict(command='run', arguments={})]:
                self.assertEqual(c.tool('run', **args)['structuredContent']['error']['code'], 'INVALID_REQUEST')
            response = c.tool('run', command='document.create', arguments=dict(id='bad', kind='vector', width=0, height=2))
            self.assertEqual(response['structuredContent']['error']['code'], 'INVALID_DOCUMENT')
            self.assertEqual(c.rpc('ping')['result'], {})


if __name__ == '__main__':
    unittest.main()
