"""Fresh-process history checks, independently decoded pixels and SQLite receipts."""
import base64
import copy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from test_cli import EXE
from test_editing_cli import png_pixels


def invoke(request):
    p = subprocess.run([str(EXE)], input=json.dumps(request).encode(), capture_output=True, timeout=20)
    assert p.stderr == b"", p.stderr
    result = json.loads(p.stdout)
    assert p.returncode == (0 if result['ok'] else 1)
    return result


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.session = 'original'

    def call(self, command, expected=None, **kw):
        r = invoke(dict(command=command, session_root=str(self.root), session_id=self.session, **kw))
        if expected:
            self.assertFalse(r['ok'], r)
            self.assertEqual(r['error']['code'], expected, r)
            return r['error']
        self.assertTrue(r['ok'], r)
        return r['result']

    def create(self, kind='vector', **kw):
        d = invoke(dict(command='document.create', id='source', kind=kind, width=8, height=6))['result']
        d['revision'] = 37  # A new session has its own monotonic revision space.
        self.original = copy.deepcopy(d)
        return self.call('session.create', request_id='create', document=d, **kw)

    def apply(self, rev, rid, action, **kw):
        return self.call('session.apply', expected_revision=rev, request_id=rid, action=action, **kw)

    def edit(self, rev, rid, ops, **kw):
        return self.apply(rev, rid, dict(type='edit', operations=ops, label='Original fixture'), **kw)

    def shape(self):
        return dict(id='box', content=dict(type='vector', geometry=dict(shape='rect', x=1, y=1, width=3, height=2), fill=[19,83,211,255]))

    def pixels(self, doc):
        result = invoke(dict(command='document.export', document=doc, format='png'))
        self.assertTrue(result['ok'], result)
        return png_pixels(base64.b64decode(result['result']['data']))[2]

    def db_path(self):
        return self.root / (hashlib.sha256(self.session.encode()).hexdigest()+'.sqlite3')

    def test_vector_grouped_history_restores_exact_geometry_and_all_pixels(self):
        initial = self.create()['document']
        ops = [dict(op='add', item=self.shape()), dict(op='transform', id='box', matrix=[1,0,0,1,2,1])]
        edited = self.edit(0, 'draw', ops)['document']
        self.assertEqual(edited['items'][0]['transform'], [1,0,0,1,2,1])
        expected = b''.join(bytes([19,83,211,255]) if 3<=x<6 and 2<=y<4 else bytes(4) for y in range(6) for x in range(8))
        self.assertEqual(self.pixels(edited), expected)
        undo = self.apply(1, 'undo', dict(type='undo'))['document']
        self.assertEqual(undo, dict(initial, revision=2))
        self.assertEqual(self.pixels(undo), bytes(8*6*4))
        redo = self.apply(2, 'redo', dict(type='redo'))['document']
        self.assertEqual(redo, dict(edited, revision=3))
        self.assertEqual(self.pixels(redo), expected)
        self.assertEqual(self.call('session.read')['undo_depth'], 1)
        self.assertTrue(self.call('session.verify')['valid'])

    def test_raster_undo_redo_snapshot_branch_and_failed_batch_isolation(self):
        self.create('raster')
        original_pixels = bytes([71,13,9,255])*48
        item = dict(id='pixels', content=dict(type='raster', width=8, height=6, rgba_hex=original_pixels.hex()))
        before = self.edit(0, 'add', [dict(op='add', item=item)])['document']
        self.apply(1, 'save', dict(type='snapshot', name='before'))
        self.assertEqual(self.call('session.read', snapshot='before')['document'], dict(before, revision=2))
        op = dict(op='pixel_fill', id='pixels', rect=dict(x=2,y=1,width=4,height=3), color=[5,180,120,255])
        after = self.edit(2, 'paint', [op])['document']
        expected = b''.join(bytes([5,180,120,255]) if 2<=x<6 and 1<=y<4 else bytes([71,13,9,255]) for y in range(6) for x in range(8))
        self.assertEqual(self.pixels(after), expected)
        undo = self.apply(3, 'undo', dict(type='undo'))['document']
        self.assertEqual(undo, dict(before, revision=4))
        self.assertEqual(self.pixels(undo), original_pixels)
        redo = self.apply(4, 'redo', dict(type='redo'))['document']
        self.assertEqual(redo, dict(after, revision=5))
        self.assertEqual(self.pixels(redo), expected)
        e = self.edit(5, 'invalid', [dict(op='properties', id='pixels', name='discard'),dict(op='remove', id='absent')], expected='NOT_FOUND')
        self.assertEqual(e['operation_index'], 1)
        self.assertEqual(self.call('session.read')['document'], redo)
        self.call('session.receipt', request_id='invalid', expected='REQUEST_NOT_FOUND')
        restored = self.apply(5, 'restore', dict(type='restore', name='before'))['document']
        self.assertEqual(self.pixels(restored), original_pixels)
        self.assertEqual(self.apply(6, 'undo-restore', dict(type='undo'))['document'], dict(after, revision=7))
        self.edit(7, 'branch', [dict(op='properties', id='pixels', name='branch')])
        self.apply(8, 'redo-branch', dict(type='redo'), expected='HISTORY_BOUNDARY')
        self.assertEqual(self.call('session.read', snapshot='before')['document'], dict(before, revision=2))
        self.apply(8, 'remove-name', dict(type='remove_snapshot', name='before'))
        self.call('session.read', snapshot='before', expected='SNAPSHOT_NOT_FOUND')
        self.assertTrue(self.call('session.verify')['valid'])

    def test_idempotent_replay_returns_original_receipt_after_new_edits(self):
        self.create()
        ops = [dict(op='add', item=self.shape())]
        first = self.edit(0, 'draw', ops)
        self.edit(1, 'rename', [dict(op='properties', id='box', name='new')])
        retry = self.edit(0, 'draw', ops, control=dict(timeout_ms=0))
        self.assertTrue(retry['replayed'])
        self.assertEqual(retry['current_revision'], 2)
        self.assertEqual(retry['receipt'], first['receipt'])
        self.assertEqual(retry['document'], first['document'])
        self.assertEqual(self.call('session.receipt', request_id='draw'), retry)
        self.edit(1, 'draw', ops, expected='REQUEST_ID_REUSED')
        self.apply(0, 'stale', dict(type='undo'), expected='REVISION_CONFLICT')
        replay = self.call('session.create', request_id='create', document=self.original)
        self.assertEqual(replay['current_revision'], 2)
        self.assertEqual(replay['document']['revision'], 0)
        self.call('session.create', request_id='other', document=self.original, expected='SESSION_EXISTS')
        history = self.call('session.history', limit=2)
        self.assertEqual([r['revision'] for r in history['entries']], [0,1])
        self.assertTrue(history['has_more'])
        self.assertEqual(self.call('session.history', after_revision=1, limit=2)['entries'][0]['revision'], 2)
        self.assertEqual(self.call('session.verify')['requests'], 3)

    def test_resource_bindings_snapshots_and_source_file_are_preserved(self):
        source = self.root/'source.json'
        self.create(resources=dict(asset_root=str(self.root/'images'),font_root=str(self.root/'fonts')))
        payload = json.dumps(self.original).encode()
        source.write_bytes(payload)
        old = self.call('session.read')
        self.apply(0, 'resources', dict(type='resources', resources=dict(asset_root=str(self.root/'other'))))
        undo = self.apply(1, 'undo', dict(type='undo'))
        self.assertEqual(undo['resources'], old['resources'])
        self.assertEqual(undo['document'], dict(old['document'],revision=2))
        self.assertEqual(source.read_bytes(), payload)
        self.apply(2, 'save', dict(type='snapshot',name='saved'))
        self.apply(3, 'duplicate', dict(type='snapshot',name='saved'), expected='SNAPSHOT_EXISTS')
        self.assertEqual(self.call('session.verify')['revision'], 3)

    def test_concurrent_writers_and_creators_have_one_committed_winner(self):
        d = self.create()['document']
        def writer(n):
            return invoke(dict(command='session.apply', session_root=str(self.root),session_id=self.session,expected_revision=0,request_id=f'writer{n}',action=dict(type='edit',operations=[dict(op='add',item=self.shape())])))
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(writer, range(6)))
        self.assertEqual(sum(r['ok'] for r in results), 1, results)
        self.assertTrue(all(r['ok'] or r['error']['code'] in ('REVISION_CONFLICT','SESSION_BUSY') for r in results), results)
        self.assertEqual(self.call('session.verify')['requests'], 2)
        self.session = 'concurrent-create'
        req = dict(command='session.create',session_root=str(self.root),session_id=self.session,request_id='create',document=d)
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(invoke,[req]*6))
        self.assertTrue(all(r['ok'] for r in results), results)
        self.assertEqual(sum(not r['result']['replayed'] for r in results), 1)
        self.assertEqual(self.call('session.verify')['requests'], 1)

    def test_cancellation_timeout_invalid_controls_and_busy_store_preserve_head(self):
        self.create()
        self.apply(0, 'timeout', dict(type='snapshot',name='no'), control=dict(timeout_ms=0),expected='TIMEOUT')
        marker = self.root/'cancel'
        marker.write_text('caller owned')
        self.apply(0,'cancel',dict(type='snapshot',name='no'),control=dict(cancel_file=str(marker)),expected='CANCELLED')
        for ctl in (dict(timeout_ms=60001),dict(cancel_file='relative'),dict(timeout_ms=-1),dict(extra=True)):
            result=invoke(dict(command='session.apply',session_root=str(self.root),session_id=self.session,request_id='bad',expected_revision=0,action=dict(type='snapshot',name='no'),control=ctl))
            self.assertFalse(result['ok'])
        with closing(sqlite3.connect(self.db_path())) as db, db:
            db.execute('BEGIN IMMEDIATE')
            self.apply(0,'busy',dict(type='snapshot',name='no'),expected='SESSION_BUSY')
            db.rollback()
        self.assertEqual(self.call('session.read')['current_revision'],0)
        self.assertEqual(marker.read_text(),'caller owned')
        self.apply(0,'valid',dict(type='snapshot',name='yes'))
        self.assertEqual(self.call('session.verify')['requests'],2)

    def test_independent_state_receipt_checksums_and_corruption_rejection(self):
        self.create()
        self.edit(0,'draw',[dict(op='add',item=self.shape())])
        with closing(sqlite3.connect(self.db_path())) as db, db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            states=db.execute('SELECT id,payload,sha256 FROM states ORDER BY id').fetchall()
            self.assertEqual([r[0] for r in states],[0,1])
            for sid, payload, checksum in states:
                self.assertEqual(hashlib.sha256(payload).hexdigest(),checksum)
                state=json.loads(payload)
                self.assertEqual(state['document']['revision'],0)
            for fingerprint,payload,checksum in db.execute('SELECT fingerprint,payload,sha256 FROM requests'):
                combined=json.dumps([fingerprint,list(payload)],separators=(',',':')).encode()
                self.assertEqual(hashlib.sha256(combined).hexdigest(),checksum)
            db.execute("UPDATE requests SET fingerprint=? WHERE request_id='draw'",('0'*64,))
        self.call('session.read',expected='SESSION_CORRUPT')
        self.call('session.verify',expected='SESSION_CORRUPT')
        self.session='content-corruption'
        self.create()
        with closing(sqlite3.connect(self.db_path())) as db, db:
            db.execute('UPDATE states SET payload=? WHERE id=0',(b'{}',))
        self.call('session.read',expected='SESSION_CORRUPT')
        self.apply(0,'change',dict(type='snapshot',name='no'),expected='SESSION_CORRUPT')
        self.session='schema-corruption'
        self.create()
        with closing(sqlite3.connect(self.db_path())) as db, db:
            db.execute('CREATE TABLE sqliteXextra(data BLOB)')
        self.call('session.read',expected='SESSION_FORMAT')

    def test_snapshot_and_history_bounds_fail_without_eviction(self):
        self.create()
        for n in range(32):
            self.apply(n,f'save{n}',dict(type='snapshot',name=f's{n}'))
        self.apply(32,'overflow',dict(type='snapshot',name='overflow'),expected='RESOURCE_LIMIT')
        self.apply(32,'invalid-undo',dict(type='undo',steps=0),expected='INVALID_REQUEST')
        self.call('session.history',limit=129,expected='INVALID_REQUEST')
        self.call('session.history',limit=1,after_revision=2**64-1,expected='INVALID_REQUEST')
        self.assertEqual(len(self.call('session.read')['snapshots']),32)
        self.assertEqual(self.call('session.verify')['requests'],33)


if __name__ == '__main__':
    unittest.main()
