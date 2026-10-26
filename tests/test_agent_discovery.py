"""Compact discovery and routed execution, checked through independent processes."""
from contextlib import closing
import base64
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_mcp import Client
from test_sessions_cli import EXE, invoke
from synthetic_font import geometric_font
from mcp_artifacts import restore
from test_editing_cli import png_pixels
from external_workspace import files as workspace_files


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
    def test_focused_examples_are_bounded_scoped_and_identical_in_cli_mcp(self):
        index = invoke(dict(command='schema.lookup', name='index'))['result']
        caps = invoke(dict(command='capabilities'))['result']['agent_discovery']
        with tempfile.TemporaryDirectory() as directory:
            for workspace in (None, directory):
                with closing(Client(('--tools', 'essentials'), workspace=workspace)) as client:
                    client.initialize()
                    for query in index['example_queries']:
                        with self.subTest(query=query, workspace=workspace):
                            prefix = ['--workspace', workspace] if workspace else []
                            process = subprocess.run([str(EXE), *prefix], input=json.dumps(query).encode(),
                                                     capture_output=True, timeout=20)
                            self.assertEqual(process.returncode, 0, process.stdout)
                            self.assertEqual(process.stderr, b'')
                            cli = json.loads(process.stdout)
                            arguments = {k: v for k, v in query.items() if k != 'command'}
                            self.assertEqual(cli, client.tool('schema.lookup', **arguments)['structuredContent'])
                            example = cli['result']['example']
                            self.assertLessEqual(len(json.dumps(example, separators=(',', ':')).encode()),
                                                 caps['schema_examples']['maximum_bytes'])
                            self.assertEqual(set(example), {'kind', 'value', 'requires', 'usage'})
                            wire = client.tool('schema.lookup', **arguments, full=True)
                            full = wire['structuredContent']['result']
                            self.assertEqual(example, full['example'])
                            # Measure the engine's actual JSON bytes: Python formats tiny floats differently.
                            raw_schema = wire['content'][0]['text'].split('"schema":', 1)[1]
                            schema, end = json.JSONDecoder().raw_decode(raw_schema)
                            self.assertEqual(schema, full['schema'])
                            self.assertEqual(full['schema_bytes'], len(raw_schema[:end].encode()))
                    for alias, nested in [('operation', 'Operation/text'), ('content', 'Content/text')]:
                        direct = client.success('schema.lookup', name=alias, select='text', full=True)
                        indirect = client.success('schema.lookup', name='session.apply', select=nested, full=True)
                        self.assertEqual(direct['schema'], indirect['schema'])
                        self.assertEqual(direct['example'], indirect['example'])
                    for name, select in [('operation', 'reorder'), ('session.dry_run', 'Options')]:
                        self.assertNotIn('example', client.success('schema.lookup', name=name, select=select))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_advertised_examples_execute_preserve_artwork_and_review_without_writes(self):
        queries = invoke(dict(command='schema.lookup', name='index'))['result']['example_queries']
        examples = {(q['name'], q.get('select')): invoke(q)['result']['example']['value'] for q in queries}
        self.assertEqual(len(examples), 8)  # Boolean execution is covered by test_boolean_edit_cli.
        for transport in ('cli', 'mcp'):
            with self.subTest(transport=transport), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                font = geometric_font()
                license_bytes = b'Original synthetic fixture; permission to use and redistribute.\n'
                (root / 'typeface.ttf').write_bytes(font)
                (root / 'typeface-license.txt').write_bytes(license_bytes)
                with closing(Client(('--tools', 'essentials'), workspace=root)) as client:
                    client.initialize()

                    def call(request, workspace=root, adapter=client):
                        if transport == 'mcp':
                            arguments = {k: v for k, v in request.items() if k != 'command'}
                            result = restore(adapter.tool('run', command=request['command'], arguments=arguments))
                        else:
                            process = subprocess.run([str(EXE), '--workspace', str(workspace)],
                                                     input=json.dumps(request).encode(), capture_output=True, timeout=20)
                            self.assertEqual(process.stderr, b'')
                            result = json.loads(process.stdout)
                            self.assertEqual(process.returncode, 0, result)
                        self.assertTrue(result['ok'], result)
                        return result['result']

                    def command(name, **arguments):
                        return call(dict(command=name, **arguments))

                    imported = call(examples['font.import', None])
                    self.assertTrue((root / '.inkbolt/fonts').is_dir())
                    blank = command('document.validate', document=examples['document', None])
                    blank_root = root / 'blank'
                    blank_root.mkdir()
                    with closing(Client(('--tools', 'essentials'), workspace=blank_root)) as blank_client:
                        blank_client.initialize()
                        call(examples['session.create', None], blank_root, blank_client)
                        created = call(dict(command='session.read', session_id='example'), blank_root, blank_client)
                    self.assertEqual(created['document'], blank)
                    self.assertEqual(created['current_revision'], 0)
                    # Give the review example its separately declared populated-session prerequisites.
                    populated = copy.deepcopy(blank)
                    populated['fonts'] = {'face': imported}
                    populated['items'] = [dict(id='label', content=copy.deepcopy(examples['content', 'text'])),
                        dict(id='untouched', content=dict(type='vector', geometry=dict(shape='rect',
                             x=48, y=48, width=8, height=8), fill=[0, 200, 0, 255]))]
                    populated['items'][0]['content']['frame']['width'] = 16
                    populated = command('document.validate', document=populated)
                    text_result = command('document.edit', document=populated, expected_revision=0,
                                          operations=[examples['operation', 'text']])['document']
                    expected = copy.deepcopy(populated)
                    expected['revision'] = 1
                    expected['items'][0]['content']['frame']['width'] = 32
                    self.assertEqual(text_result, expected)
                    transformed = command('document.edit', document=text_result, expected_revision=1,
                                          operations=[examples['operation', 'transform']])['document']
                    expected['revision'] = 2
                    expected['items'][0]['transform'] = [1, 0, 0, 1, 4, 4]
                    self.assertEqual(transformed, expected)
                    pixels = bytes.fromhex(command('document.render', document=transformed)['data'])
                    self.assertEqual(pixels[(50 * 64 + 50) * 4:(50 * 64 + 51) * 4], bytes([0, 200, 0, 255]))
                    self.assertTrue(any(pixels[(y * 64 + x) * 4 + 3] for y in range(4, 28) for x in range(4, 36)))
                    command('session.create', session_id='example', request_id='setup',
                            document=populated)
                    review_request = copy.deepcopy(examples['session.dry_run', None])
                    before = {p: p.read_bytes() for p in workspace_files(root)}
                    reviewed = call(review_request)
                    self.assertEqual({p: p.read_bytes() for p in workspace_files(root)}, before)
                    self.assertFalse(reviewed['committed'])
                    self.assertIn('preview', reviewed)
                    self.assertEqual(command('session.read', session_id='example')['current_revision'], 0)
                    committed = command('session.apply_proposal', proposal=reviewed['proposal'],
                                        action=review_request['action'])
                    self.assertEqual(committed['document'], text_result)
                    width, height, preview_pixels, _ = png_pixels(base64.b64decode(reviewed['preview']['data']))
                    self.assertEqual((width, height), (64, 64))
                    self.assertEqual(preview_pixels, bytes.fromhex(command('document.render', document=text_result)['data']))
                    self.assertEqual(command('session.read', session_id='example')['undo_depth'], 1)
                    self.assertEqual((root / 'typeface.ttf').read_bytes(), font)
                    self.assertEqual((root / 'typeface-license.txt').read_bytes(), license_bytes)

    def test_essentials_has_bounded_discovery_and_mode_bound_cursors(self):
        with tempfile.TemporaryDirectory() as directory:
            for workspace in (None, directory):
                with closing(Client(('--tools', 'essentials'), workspace=workspace)) as client:
                    client.initialize()
                    first = client.rpc('tools/list')['result']
                    self.assertEqual([t['name'] for t in first['tools'][:2]],
                                     ['inkbolt_schema_lookup', 'inkbolt_run'])
                    self.assertEqual(first['nextCursor'], 'inkbolt-tools-essentials-v1:8')
                    self.assertEqual(first, client.rpc('tools/list')['result'])
                    tools = catalog(client)
                    self.assertEqual(len(tools), 10)
                    self.assertLessEqual(len(json.dumps(tools, separators=(',', ':')).encode()), 24 * 1024)
                    caps = client.tool('run', command='capabilities', arguments={})['structuredContent']['result']
                    self.assertEqual(caps['agent_discovery']['mcp_default'], 'full')
                    self.assertEqual(caps['agent_discovery']['mcp_essentials_max_tools'], len(tools))
                    self.assertEqual(caps['agent_discovery']['mcp_essentials_budget_bytes'], 24 * 1024)
                    for cursor in ('inkbolt-tools-core-v2:8', 'inkbolt-tools-v1:8'):
                        self.assertEqual(client.rpc('tools/list', dict(cursor=cursor))['error']['code'], -32602)
                    # Unlisted direct tools remain undiscoverable; the shared dispatcher reaches them.
                    self.assertEqual(client.rpc('tools/call', dict(name='inkbolt_document_create', arguments={}))['error']['code'], -32602)
                    created = client.tool('run', command='document.create', arguments=dict(
                        id='essentials', kind='vector', width=8, height=8))['structuredContent']
                    self.assertTrue(created['ok'])
                    for tool in tools:
                        for prop in tool['inputSchema']['properties'].values():
                            query = prop.get('x-inkbolt-schema', {})
                            if 'select' in query:
                                found = client.success('schema.lookup', **query, full=True)
                                self.assertEqual(found['detail'], 'full')

    def test_nested_schema_routes_and_error_recovery_match_cli_mcp(self):
        with tempfile.TemporaryDirectory() as directory:
            for workspace in (None, directory):
                with self.subTest(workspace=workspace), closing(Client(('--tools', 'core'), workspace=workspace)) as client:
                    client.initialize()

                    def lookup(**arguments):
                        request = dict(command='schema.lookup', **arguments)
                        prefix = ['--workspace', workspace] if workspace else []
                        process = subprocess.run([str(EXE), *prefix], input=json.dumps(request).encode(),
                                                 capture_output=True, timeout=20)
                        self.assertEqual(process.stderr, b'')
                        cli = json.loads(process.stdout)
                        self.assertEqual(process.returncode, 0 if cli['ok'] else 1)
                        mcp = client.tool('schema.lookup', **arguments)['structuredContent']
                        self.assertEqual(cli, mcp)
                        return cli

                    error = lookup(name='session.apply', select='edit')['error']
                    self.assertEqual(error['code'], 'SCHEMA_NOT_FOUND')
                    self.assertEqual(error['details']['field'], 'select')
                    suggested = dict(error['details']['suggested_lookup'])
                    self.assertEqual(suggested.pop('command'), 'schema.lookup')
                    edited = lookup(**suggested)['result']
                    self.assertEqual(suggested['select'], 'Action/edit')
                    if edited['detail'] == 'full':
                        self.assertEqual(edited['schema']['properties']['type']['const'], 'edit')
                    outline = lookup(name='session.apply', select='Action')['result']
                    route = next(v['select'] for v in outline['variants'] if v['value'] == 'edit')
                    self.assertEqual(lookup(name='session.apply', select=route)['result'], edited)
                    transformed = lookup(name='session.apply', select='Action/edit/Operation/transform')['result']
                    self.assertEqual(transformed['schema']['properties']['op']['const'], 'transform')
                    self.assertEqual(transformed['schema'], lookup(name='operation', select='transform')['result']['schema'])
                    self.assertLess(len(json.dumps(outline, separators=(',', ':')).encode()), 12 * 1024)
                    self.assertEqual(list(Path(directory).iterdir()), [])

    def test_cli_help_is_compact_json_with_working_examples_and_no_input_effects(self):
        flags = invoke(dict(command='capabilities'))['result']['agent_discovery']['cli_help_arguments']
        self.assertEqual(flags, ['--help', '-h'])
        reference = None
        with tempfile.TemporaryDirectory() as directory:
            for prefix in ([], ['--workspace', directory]):
                for flag in flags:
                    with self.subTest(prefix=prefix, flag=flag):
                        result = subprocess.run([str(EXE), *prefix, flag], input=b'not a JSON request',
                                                capture_output=True, timeout=20)
                        self.assertEqual(result.returncode, 0, result.stdout)
                        self.assertEqual(result.stderr, b'')
                        self.assertEqual(len(result.stdout.splitlines()), 1)
                        self.assertLess(len(result.stdout), 4096)
                        reply = json.loads(result.stdout)
                        self.assertTrue(reply['ok'])
                        if reference is None:
                            reference = reply
                        self.assertEqual(reply, reference)
                caps = subprocess.run([str(EXE), '--workspace', directory, 'capabilities'],
                                      capture_output=True, timeout=20, check=True)
                self.assertEqual(reference['result']['workspace_defaults'],
                                 json.loads(caps.stdout)['result']['workspace']['defaults'])
            self.assertEqual(list(Path(directory).iterdir()), [])
        for request in reference['result']['examples']:
            with self.subTest(request=request):
                self.assertTrue(invoke(request)['ok'])
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([str(EXE), '--workspace', str(Path(directory) / 'missing'), '--help'],
                                    capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 1)
            self.assertFalse(json.loads(result.stdout)['ok'])

    def test_reorder_guidance_identifies_sibling_scope_and_preserves_other_items(self):
        focused = invoke(dict(command='schema.lookup', name='operation', select='reorder'))['result']
        self.assertEqual(focused['detail'], 'full')
        description = focused['schema']['properties']['index']['description']
        self.assertIn('zero-based sibling position', description)
        self.assertIn('including the moved item', description)
        self.assertIn('not an offset into document.items', description)
        doc = invoke(dict(command='document.create', id='sibling-order', kind='vector', width=8, height=8))['result']
        doc['items'] = [
            dict(id='g0', content=dict(type='group')),
            dict(id='a', parent='g0', content=dict(type='group')),
            dict(id='g1', content=dict(type='group')),
            dict(id='b', parent='g0', content=dict(type='group')),
            dict(id='c', parent='g1', content=dict(type='group')),
        ]
        # Normalize defaults once, then compare exact retained objects after reordering.
        doc = invoke(dict(command='document.edit', document=doc, expected_revision=0,
                          operations=[dict(op='reorder', id='a', index=0)]))['result']['document']
        before = copy.deepcopy(doc)
        global_index = next(i for i, item in enumerate(doc['items']) if item['id'] == 'b')
        bad = invoke(dict(command='document.edit', document=doc, expected_revision=doc['revision'],
                          operations=[dict(op='reorder', id='b', index=global_index)]))
        self.assertFalse(bad['ok'])
        self.assertEqual(bad['error']['code'], 'INVALID_OPERATION')
        self.assertIn('less than 2', bad['error']['message'])
        self.assertIn('not an offset into document.items', bad['error']['message'])
        good = invoke(dict(command='document.edit', document=doc, expected_revision=doc['revision'],
                           operations=[dict(op='reorder', id='b', index=0)]))['result']['document']
        self.assertEqual(doc, before)
        self.assertEqual({item['id']: item for item in good['items']},
                         {item['id']: item for item in before['items']})
        self.assertEqual([item['id'] for item in good['items'] if item.get('parent') == 'g0'], ['b', 'a'])
        self.assertEqual([item['id'] for item in good['items'] if item.get('parent') is None], ['g0', 'g1'])
        self.assertEqual([item['id'] for item in good['items'] if item.get('parent') == 'g1'], ['c'])
        self.assertEqual(good['revision'], before['revision'] + 1)

    def test_first_page_can_discover_and_run_commands_with_stable_complete_pagination(self):
        with tempfile.TemporaryDirectory() as directory:
            for workspace in (None, directory):
                with self.subTest(workspace=workspace), closing(Client(('--tools', 'core'), workspace=workspace)) as c:
                    c.initialize()
                    first = c.rpc('tools/list')['result']
                    names = [tool['name'] for tool in first['tools']]
                    self.assertEqual(names[:2], ['inkbolt_schema_lookup', 'inkbolt_run'])
                    self.assertEqual(len(names), 8)
                    # Use only tools discovered on page one before following its cursor.
                    schema = c.rpc('tools/call', dict(name=names[0], arguments=dict(name='document.create')))['result']
                    self.assertFalse(schema['isError'])
                    self.assertEqual(schema['structuredContent']['result']['detail'], 'full')
                    made = c.rpc('tools/call', dict(name=names[1], arguments=dict(command='document.create',
                        arguments=dict(id='first-page', kind='vector', width=8, height=8))))['result']
                    self.assertFalse(made['isError'])
                    self.assertEqual(made['structuredContent']['result']['id'], 'first-page')
                    caps = c.tool('run', command='capabilities', arguments={})['structuredContent']['result']
                    self.assertEqual(caps['agent_discovery']['mcp_compact_first_tools'], names[:2])
                    self.assertEqual(first['nextCursor'], 'inkbolt-tools-core-v2:8')
                    self.assertEqual(first, c.rpc('tools/list')['result'])
                    page = first
                    while 'nextCursor' in page:
                        params = dict(cursor=page['nextCursor'])
                        page = c.rpc('tools/list', params)['result']
                        self.assertEqual(page, c.rpc('tools/list', params)['result'])
                        names.extend(tool['name'] for tool in page['tools'])
                    self.assertEqual(len(names), 22)
                    self.assertEqual(len(set(names)), len(names))
                    self.assertEqual(names[2:], sorted(names[2:]))
                    self.assertEqual(names, [tool['name'] for tool in catalog(c)])
                    for cursor in ('inkbolt-tools-core-v1:8', 'inkbolt-tools-v1:8'):
                        self.assertEqual(c.rpc('tools/list', dict(cursor=cursor))['error']['code'], -32602)

    def test_small_catalog_and_schema_lookup_preserve_legacy_discovery(self):
        with closing(Client(('--tools', 'core'))) as core, closing(Client()) as full:
            core.initialize(); full.initialize()
            small, large = catalog(core), catalog(full)
            self.assertEqual([t['name'] for t in large], sorted(t['name'] for t in large))
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
        with closing(Client(('--tools', 'essentials'))) as c, tempfile.TemporaryDirectory() as directory:
            c.initialize()
            def run(command, **arguments):
                r = c.tool('run', command=command, arguments=arguments)
                self.assertFalse(r['isError'], r)
                return r['structuredContent']['result']
            doc = run('document.create', id='compact', kind='vector', width=8, height=8)
            item = dict(id='square', content=dict(type='vector', geometry=dict(shape='rect', x=1, y=2, width=3, height=4), fill=[20,60,180,255]))
            edited = run('document.edit', document=doc, expected_revision=0, operations=[dict(op='add', item=item)])
            self.assertEqual(edited, invoke(dict(command='document.edit', document=doc, expected_revision=0, operations=[dict(op='add', item=item)]))['result'])
            self.assertEqual(run('document.render', document=edited['document']), invoke(dict(command='document.render', document=edited['document']))['result'])
            s = dict(session_root=directory, session_id='compact')
            c.success('session.create', **s, request_id='create', document=doc)
            request = dict(**s, request_id='add', expected_revision=0, action=dict(type='edit', operations=[dict(op='add', item=item)]))
            first = c.success('session.apply', **request)
            repeated = run('session.apply', **request)
            self.assertTrue(repeated['replayed']); self.assertEqual(first['receipt'], repeated['receipt'])
            conflict = c.tool('run', command='session.apply', arguments={**request, 'request_id': 'stale'})
            self.assertEqual(conflict['structuredContent']['error']['code'], 'REVISION_CONFLICT')
            output = dict(output_root=directory, file_name='compact.png', format='png')
            published = c.success('session.publish', **s, expected_revision=1, output=output)
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
