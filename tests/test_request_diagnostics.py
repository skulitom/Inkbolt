"""Observed missing-field repairs, bounded hints and unchanged execution contracts."""
from contextlib import closing
import copy
import json
import unittest

import test_agent_workspace as workspace
import test_session_proposals as proposals
from test_mcp import Client


class RequestDiagnosticTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli
    document = workspace.AgentWorkspaceTests.document
    save = workspace.AgentWorkspaceTests.save
    files = proposals.SessionProposalTests.files

    def assert_hint(self, request, field, select=None, *, scoped=False):
        error = self.cli(**request, scoped=scoped, error='INVALID_REQUEST')
        self.assertEqual(error['details']['reason'], 'missing_field')
        self.assertEqual(error['details']['field'], field)
        self.assertIn(field, error['message'])
        query = dict(command='schema.lookup', name=request['command'])
        if select:
            query['select'] = select
        self.assertEqual(error['details']['schema_lookup'], query)
        help_result = self.cli(**query, scoped=scoped)
        self.assertIn(help_result['detail'], ('full', 'outline'))
        if help_result['detail'] == 'full':
            schema = help_result['schema']
            if field in schema.get('properties', {}):
                self.assertEqual(error['details']['expected']['type'], schema['properties'][field]['type'])
        return error

    def test_observed_missing_fields_have_executable_focused_help_and_no_writes(self):
        cases = [
            (dict(command='sample.import', source_path='original.png', id='photo', storage={}),
             'store_root', 'NativeStore'),
            (dict(command='session.receipt', session_id='work', request_id='move'),
             'session_root', None),
            (dict(command='session.history', session_root=str(self.root/'missing'), session_id='work'),
             'limit', None),
        ]
        with closing(Client(('--tools', 'core'))) as client, closing(Client()) as full:
            client.initialize()
            full.initialize()
            for request, field, select in cases:
                with self.subTest(command=request['command']):
                    error = self.assert_hint(request, field, select)
                    routed = client.tool('run', command=request['command'],
                                         arguments={k:v for k,v in request.items() if k!='command'})
                    self.assertEqual(routed['structuredContent']['error'], error)
                    direct = full.tool(request['command'], **{k:v for k,v in request.items() if k!='command'})
                    self.assertEqual(direct['structuredContent']['error'], error)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_fixing_the_field_works_and_workspace_defaults_are_preserved(self):
        self.save()
        receipt_request = dict(command='session.receipt', session_id='work', request_id='create')
        self.assert_hint(receipt_request, 'session_root')
        explicit = self.cli(**receipt_request, scoped=False, session_root=str(self.root/'.inkbolt/sessions'))
        default = self.cli(**receipt_request)
        self.assertEqual(default, explicit)
        history = dict(command='session.history', session_id='work')
        self.assert_hint(history, 'limit', scoped=True)
        history['limit'] = 2
        self.assertEqual(self.cli(**history)['entries'][0]['request_id'], 'create')

    def test_invalid_edit_keeps_head_files_and_request_id_available(self):
        self.save()
        request = dict(command='session.apply', session_id='work', request_id='edit',
                       expected_revision=0, action=dict(type='edit'))
        before = self.files()
        self.assert_hint(request, 'operations', 'Action', scoped=True)
        self.assertEqual(self.files(), before)
        self.cli('session.receipt', session_id='work', request_id='edit', error='REQUEST_NOT_FOUND')
        repaired = copy.deepcopy(request)
        repaired['action']['operations'] = [dict(op='add_svg', svg='<rect width="1" height="1"/>')]
        result = self.cli(**repaired)
        self.assertFalse(result['replayed'])
        self.assertTrue(self.cli(**repaired)['replayed'])

    def test_unknown_fields_values_and_commands_are_not_reflected_or_guessed(self):
        secret = 'untrusted-private-value-'*2000
        cases = [
            dict(command='session.receipt', session_root=str(self.root), session_id='work', request_id='move', **{secret: 1}),
            dict(command='session.receipt', session_root=secret, session_id=[], request_id='move'),
            dict(command=secret),
            dict(command='sample.import', source_path='original.png', id='photo', storage={'missing field `store_root`': 1}),
        ]
        limit = self.cli('capabilities')['request_diagnostics']['maximum_error_bytes']
        for request in cases:
            with self.subTest(command=str(request['command'])[:40]):
                error = self.cli(**request, scoped=False, error='INVALID_REQUEST')
                encoded = json.dumps(error, separators=(',', ':'), ensure_ascii=False).encode()
                self.assertLessEqual(len(encoded), limit)
                self.assertNotIn(b'untrusted-private-value', encoded)
                self.assertNotIn('field', error['details'])
                query = error['details']['schema_lookup']
                self.assertTrue(self.cli(**query, scoped=False))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_ambiguous_field_owner_uses_the_command_query_without_guessing_a_path(self):
        request = dict(command='session.apply', session_root=str(self.root), session_id='work',
                       request_id='missing-id', expected_revision=0,
                       action=dict(type='edit', operations=[dict(op='remove')]))
        error = self.assert_hint(request, 'id')
        self.assertNotIn('path', error['details'])
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
