"""A complete CLI/MCP review, queued delivery and history recovery workflow."""
from contextlib import closing
import base64
import hashlib
from pathlib import Path
import unittest

import test_jobs as jobs
import test_session_lineage as lineage
from test_editing_cli import png_pixels
from test_images_cli import png
from test_mcp import Client
from synthetic_font import geometric_font


class RecoveryWorkflowTests(unittest.TestCase):
    setUp = jobs.JobTests.setUp
    cli = jobs.JobTests.cli
    document = jobs.JobTests.document
    save = jobs.JobTests.save
    ledger = jobs.JobTests.ledger
    stop_owned = jobs.JobTests.stop_owned
    blocked_queue = jobs.JobTests.blocked_queue
    finish = jobs.JobTests.finish
    idle = jobs.JobTests.idle
    dbpath = lineage.SessionLineageTests.dbpath
    rows = lineage.SessionLineageTests.rows
    identity = lineage.SessionLineageTests.identity
    v1 = lineage.SessionLineageTests.v1

    def test_review_delivery_migration_restore_and_continuation_keep_their_exact_original_results(self):
        source_pixels = bytes([10, 20, 30, 255]*4)
        originals = {'original.png': png(2, 2, source_pixels), 'original.ttf': geometric_font(),
                     'license.txt': b'Original synthetic workflow fixture; permission to use and retain.'}
        for name, data in originals.items(): (self.root/name).write_bytes(data)
        asset = self.cli('asset.import', source_path='original.png')['asset']
        font = self.cli('font.import', source_path='original.ttf', license_path='license.txt')
        document = self.document()
        document['assets'] = {'picture': asset}; document['fonts'] = {'face': font}
        document['items'] = [dict(id='picture', content=dict(type='image', asset_id='picture', width=2, height=2)),
                             dict(id='badge', content=dict(type='vector', geometry=dict(shape='rect', x=0, y=0, width=1, height=1), fill=[250, 80, 30, 255]))]
        self.save(document)
        action = dict(type='edit', operations=[dict(op='properties', id='badge', opacity=.5)])

        with closing(Client(('--tools', 'core'), workspace=self.root)) as client:
            client.initialize()
            def remote(command, error=None, **arguments):
                response = client.tool('run', command=command, arguments=arguments)
                self.assertEqual(response['isError'], error is not None, response)
                if error:
                    self.assertEqual(response['structuredContent']['error']['code'], error)
                    return response['structuredContent']['error']
                return response['structuredContent']['result']

            source_database = self.dbpath().read_bytes()
            review = remote('session.dry_run', session_id='work', request_id='reviewed', expected_revision=0,
                            action=action, options=dict(preview=True, compare_pixels=True))
            self.assertEqual(self.dbpath().read_bytes(), source_database)
            preview = png_pixels(base64.b64decode(review['preview']['data']))[:3]
            committed = self.cli('session.apply_proposal', proposal=review['proposal'], action=action, response_mode='compact')
            self.assertEqual(committed['document_ref']['revision'], 1)
            self.assertFalse(committed['replayed'])
            retry = remote('session.apply_proposal', proposal=review['proposal'], action=action,
                           response_mode='compact', control=dict(timeout_ms=0))
            self.assertEqual(retry['receipt_summary'], committed['receipt_summary']); self.assertTrue(retry['replayed'])

            # Hold the owned worker lease so a later edit necessarily precedes encoding.
            with self.blocked_queue():
                ticket = remote('job.start', request_id='delivery', document=dict(session_id='work', revision=1),
                                output=dict(file_name='delivery.png', format='png'))
                self.assertEqual(ticket['document']['revision'], 1)
                remote('session.apply', session_id='work', request_id='newer', expected_revision=1,
                       action=dict(type='edit', operations=[dict(op='properties', id='badge', opacity=1)]))
            self.cli('job.resume', request_id='delivery'); self.finish('delivery'); self.idle()
            output_bytes = (self.root/'delivery.png').read_bytes()
            self.assertEqual(png_pixels(output_bytes)[:3], preview)
            self.assertEqual(preview[2][4:], source_pixels[4:])
            current = self.cli('document.render', document=dict(session_id='work', revision=2))
            self.assertNotEqual(bytes.fromhex(current['data'])[:4], preview[2][:4])
            result = remote('job.result', request_id='delivery')
            self.assertEqual(result['revision'], 1); self.assertEqual(result['sha256'], hashlib.sha256(output_bytes).hexdigest())
            remote('session.apply', session_id='work', request_id='named', expected_revision=2, action=dict(type='snapshot', name='delivered-history'))
            verified = self.cli('session.verify', session_id='work')
            original_rows = self.rows(self.dbpath())
            backup_args = dict(session_id='work', expected_revision=3, output=dict(file_name='backup.sqlite3'), receipt=dict(request_id='backup'))
            backup = remote('session.backup', **backup_args)
            self.assertEqual(backup['session'], verified)
            self.assertEqual(self.rows(self.root/'backup.sqlite3'), original_rows)

            # Independently construct the frozen v1 schema with every original row.
            v1_source = self.v1(); v1_bytes = (self.root/'v1.sqlite3').read_bytes()
            migration_args = dict(session_id='work', source=v1_source, target_version=2,
                                  output=dict(file_name='migrated.sqlite3'), receipt=dict(request_id='migration'))
            migrated = self.cli('session.migrate', **migration_args)
            self.assertEqual(migrated['session']['history_sha256'], verified['history_sha256'])
            self.assertEqual(self.rows(self.root/'migrated.sqlite3'), original_rows)
            self.assertEqual((self.root/'v1.sqlite3').read_bytes(), v1_bytes)
            restore_args = dict(session_id='work', session_root='restored', source=migrated['backup'], receipt=dict(request_id='restore'))
            restored = remote('session.recover', **restore_args)
            self.assertEqual(restored['session'], verified)
            undone = self.cli('session.apply', session_id='work', session_root='restored', request_id='undo-after-restore',
                              expected_revision=3, action=dict(type='undo'))
            self.assertEqual(undone['document']['items'][1]['opacity'], .5)
            self.assertEqual(undone['current_revision'], 4)
            old_edit = remote('session.apply_proposal', session_root='restored', proposal=review['proposal'], action=action,
                              response_mode='compact', control=dict(timeout_ms=0))
            self.assertEqual(old_edit['receipt_summary'], committed['receipt_summary'])
            self.assertEqual(old_edit['current_revision'], 4); self.assertEqual(old_edit['document_ref']['revision'], 1)
            rendered = self.cli('document.render', document=dict(session_id='work', session_root='restored', revision=4))
            self.assertEqual(bytes.fromhex(rendered['data']), preview[2])

            continue_args = dict(session_id='next', request_id='continue', parent=dict(source=backup['backup'], session_id='work', revision=1))
            continued = remote('session.continue', **continue_args)
            self.assertEqual(continued['document']['revision'], 0)
            self.assertEqual(continued['document']['items'][1]['opacity'], .5)
            self.assertEqual(continued['resources'], undone['resources'])
            self.assertEqual(self.rows(self.dbpath()), original_rows)

            # Preserve every file while making all original lookup paths unavailable.
            for path in [self.dbpath(), self.root/'backup.sqlite3', self.root/'v1.sqlite3', self.root/'migrated.sqlite3', self.root/'delivery.png']:
                path.rename(path.with_name('retained-'+path.name))
            for command, args, original in [('session.backup', backup_args, backup), ('session.migrate', migration_args, migrated), ('session.recover', restore_args, restored)]:
                replay = remote(command, **args, control=dict(timeout_ms=0))
                self.assertEqual(replay, dict(original, publication=dict(original['publication'], replayed=True)))
            replay = self.cli('session.continue', **continue_args, control=dict(timeout_ms=0))
            self.assertTrue(replay['replayed']); self.assertEqual(replay['document'], continued['document'])
            self.assertEqual(remote('session.verify', session_id='work', session_root='restored')['revision'], 4)
            self.assertEqual(remote('job.list')['records'][0]['request_id'], 'delivery')
            self.assertEqual(remote('job.result', request_id='delivery'), result)
            self.assertEqual((self.root/'retained-delivery.png').read_bytes(), output_bytes)
            self.assertFalse((self.root/'delivery.png').exists())
            for name, data in originals.items(): self.assertEqual((self.root/name).read_bytes(), data)


if __name__ == '__main__': unittest.main()
