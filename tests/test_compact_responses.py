"""Compact results retain recoverable state and leave durable retry identity unchanged."""
from contextlib import closing
import json
import unittest

import test_agent_workspace as workspace
from test_mcp import Client


class CompactResponseTests(unittest.TestCase):
    setUp = workspace.AgentWorkspaceTests.setUp
    cli = workspace.AgentWorkspaceTests.cli
    document = workspace.AgentWorkspaceTests.document
    save = workspace.AgentWorkspaceTests.save
    ref = workspace.AgentWorkspaceTests.ref

    def test_large_snapshot_is_recoverable_with_small_receipts(self):
        doc = self.cli('document.create', id='pixels', kind='raster', width=256, height=256)
        pixels = bytes([17, 55, 142, 255] * (256 * 256)).hex()
        doc['items'] = [dict(id='paint', content=dict(type='raster', width=256, height=256, rgba_hex=pixels))]
        full = self.save(doc)
        compact = self.save(doc, response_mode='compact', control=dict(timeout_ms=0))
        encoded = json.dumps(compact, separators=(',', ':')).encode()
        self.assertLessEqual(len(encoded), 8192)
        self.assertGreater(len(json.dumps(full).encode()), 512 * 1024)
        self.assertNotIn(b'rgba_hex', encoded)
        self.assertNotIn('document', compact)
        self.assertEqual(compact['omitted'], ['document', 'receipt.changes'])
        self.assertTrue(compact['replayed'])
        self.assertEqual(compact['document_summary']['item_count'], 1)
        self.assertEqual(compact['document_ref']['revision'], 0)
        self.assertEqual(self.cli('document.render', document=compact['document_ref'])['data'], pixels)
        recovered = self.cli('session.receipt', **compact['receipt_ref'], response_mode='full')
        self.assertEqual(recovered['receipt'], full['receipt'])
        self.assertEqual(recovered['document'], full['document'])
        read = self.cli('session.read', session_id='work', response_mode='compact')
        self.assertEqual(read['document_ref'], compact['document_ref'])
        self.assertEqual(read['snapshot_count'], 0)
        self.assertEqual(self.cli('session.read', session_id='work', response_mode='full'),
                         self.cli('session.read', session_id='work'))

    def test_cli_mcp_retry_and_named_snapshot_keep_historical_revision(self):
        self.save(response_mode='compact')
        item = dict(id='square', content=dict(type='vector', geometry=dict(shape='rect', x=0, y=0, width=2, height=2), fill=[5, 75, 155, 255]))
        arguments = dict(session_id='work', request_id='add', expected_revision=0,
                         action=dict(type='edit', operations=[dict(op='add', item=item)]))
        first = self.cli('session.apply', **arguments, response_mode='compact')
        self.cli('session.apply', session_id='work', request_id='remove', expected_revision=1,
                 action=dict(type='edit', operations=[dict(op='remove', id='square')]), response_mode='full')
        with closing(Client(('--tools', 'core'), workspace=self.root)) as c:
            c.initialize()
            packet = c.tool('session.apply', **arguments, response_mode='compact')
            self.assertLessEqual(len(json.dumps(packet, separators=(',', ':')).encode()), 8192)
            retry = packet['structuredContent']['result']
            self.assertTrue(retry['replayed'])
            self.assertEqual(retry['current_revision'], 2)
            self.assertEqual(retry['document_ref']['revision'], 1)
            self.assertEqual(retry['receipt_summary'], first['receipt_summary'])
            self.assertEqual(retry['receipt_summary']['change_count'], 1)
            receipt = c.tool('run', command='session.receipt', arguments=dict(**retry['receipt_ref'], response_mode='compact'))['structuredContent']['result']
            self.assertEqual(receipt, retry)
            self.assertEqual(c.success('document.render', document=retry['document_ref'])['data'], bytes([5, 75, 155, 255] * 4).hex())
            current = c.success('session.read', session_id='work', response_mode='compact')
            self.assertEqual(c.success('document.render', document=current['document_ref'])['data'], bytes(16).hex())
            c.success('session.apply', session_id='work', request_id='snapshot', expected_revision=2,
                      action=dict(type='snapshot', name='empty'), response_mode='compact')
            c.success('session.apply', **dict(arguments, request_id='new-add', expected_revision=3), response_mode='compact')
            read = c.success('session.read', session_id='work', snapshot='empty', response_mode='compact')
            self.assertEqual(read['document_ref']['revision'], 3)
            self.assertEqual(read['current_revision'], 4)
            self.assertEqual(read['snapshot_count'], 1)
            self.assertEqual(c.success('document.render', document=read['document_ref'])['data'], bytes(16).hex())
        self.assertEqual(self.cli('session.read', session_id='work')['current_revision'], 4)

    def test_invalid_or_unsupported_response_policy_fails_before_mutation(self):
        doc = self.document()
        for mode in [None, True, 'brief', {'type': 'compact'}]:
            self.cli('session.create', session_id='work', request_id='create', document=doc, response_mode=mode, error='INVALID_REQUEST')
        self.cli('document.publish', document=doc, output=dict(file_name='absent.json', format='snapshot'),
                 response_mode='compact', error='INVALID_REQUEST')
        self.assertFalse((self.root / '.inkbolt').exists())
        self.assertFalse((self.root / 'absent.json').exists())
        self.save()
        self.cli('session.apply', session_id='work', request_id='bad', expected_revision=0,
                 action=dict(type='snapshot', name='absent'), response_mode='brief', error='INVALID_REQUEST')
        self.assertEqual(self.cli('session.read', session_id='work')['current_revision'], 0)
        self.cli('session.receipt', session_id='work', request_id='bad', error='REQUEST_NOT_FOUND')


if __name__ == '__main__':
    unittest.main()
