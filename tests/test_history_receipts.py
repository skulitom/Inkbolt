"""History creation retries, immutable byte proofs and mutable restoration receipts."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import unittest

from test_cli import EXE
from test_mcp import Client
import test_session_lineage as lineage


class HistoryReceiptTests(unittest.TestCase):
    setUp = lineage.SessionLineageTests.setUp
    cli = lineage.SessionLineageTests.cli
    save = lineage.SessionLineageTests.save
    document = lineage.SessionLineageTests.document
    apply = lineage.SessionLineageTests.apply
    backup = lineage.SessionLineageTests.backup
    recover = lineage.SessionLineageTests.recover
    files = lineage.SessionLineageTests.files
    dbpath = lineage.SessionLineageTests.dbpath
    rows = lineage.SessionLineageTests.rows
    identity = lineage.SessionLineageTests.identity
    fixture = lineage.SessionLineageTests.fixture
    v1 = lineage.SessionLineageTests.v1

    def args(self, kind, rid='history'):
        base = dict(session_id='work', receipt=dict(request_id=rid))
        if kind == 'backup':
            return dict(base, expected_revision=4, output=dict(file_name='saved.sqlite3'))
        if kind == 'recover':
            return dict(base, session_root='restored', source=self.identity(self.root/'v1.sqlite3'))
        return dict(base, source=self.identity(self.root/'v1.sqlite3'), target_version=2, output=dict(file_name='migrated.sqlite3'))

    def run_history(self, kind, args=None, **kw):
        return self.cli('session.'+kind, **(args or self.args(kind)), **kw)

    def ledger(self):
        return self.root/'.inkbolt/publications/publications.sqlite3'

    def saved(self, **kw):
        return self.cli('publication.receipt', request_id='history', **kw)

    def finish(self, **kw):
        return self.cli('publication.recover', request_id='history', **kw)

    def record(self):
        with closing(sqlite3.connect(self.ledger())) as db:
            return json.loads(db.execute("SELECT payload FROM publications WHERE request_id='history'").fetchone()[0])

    def change(self, **changes):
        record = self.record(); record.update(changes)
        data = json.dumps(record, separators=(',', ':')).encode()
        with closing(sqlite3.connect(self.ledger())) as db:
            db.execute("UPDATE publications SET payload=?,sha256=? WHERE request_id='history'", (data, hashlib.sha256(data).hexdigest())); db.commit()
        return record

    def prepared(self, kind):
        self.fixture(); self.v1()
        args = self.args(kind); result = self.run_history(kind, args)
        record = self.record()
        os.link(record['target'], record['staging_path'])
        self.change(phase='prepared')
        return args, result, record

    def test_all_three_replay_original_receipts_after_sources_and_outputs_disappear(self):
        self.fixture(); self.v1()
        requests = [(kind, self.args(kind, kind)) for kind in ['backup', 'recover', 'migrate']]
        results = [self.run_history(kind, args) for kind, args in requests]
        self.assertEqual(self.rows(self.root/'saved.sqlite3'), self.rows(self.dbpath()))
        self.assertEqual(self.rows(self.root/'migrated.sqlite3'), self.rows(self.root/'v1.sqlite3'))
        self.assertEqual(self.rows(self.dbpath('restored')), self.rows(self.root/'v1.sqlite3'))
        self.apply('advance', 4, dict(type='redo'))
        for (kind, args), result in zip(requests, results):
            replay = self.run_history(kind, args, control=dict(timeout_ms=0))
            self.assertEqual(replay, dict(result, publication=dict(result['publication'], replayed=True)))
        for path in [self.dbpath(), self.root/'v1.sqlite3', self.root/'saved.sqlite3', self.root/'migrated.sqlite3', self.dbpath('restored')]: path.unlink()
        before = self.files()
        for (kind, args), result in zip(requests, results):
            replay = self.run_history(kind, args, control=dict(timeout_ms=0))
            self.assertEqual(replay, dict(result, publication=dict(result['publication'], replayed=True)))
            self.assertEqual(self.cli('publication.recover', request_id=kind, control=dict(timeout_ms=0)), replay)
        self.assertEqual(self.files(), before)

    def test_changed_inputs_or_history_kind_cannot_reuse_a_request(self):
        self.fixture(); self.v1(); args = self.args('backup'); self.run_history('backup', args)
        for altered in [dict(args, expected_revision=3), dict(args, output=dict(file_name='other.sqlite3')), dict(args, session_id='another'), dict(args, session_root='elsewhere')]:
            self.run_history('backup', altered, error='REQUEST_ID_REUSED')
        for kind in ['recover', 'migrate']: self.run_history(kind, error='REQUEST_ID_REUSED')
        self.assertFalse((self.root/'other.sqlite3').exists())

    def test_prepared_restore_recovery_keeps_newer_edits_and_hot_journal_evidence(self):
        args, original, record = self.prepared('recover')
        self.cli('session.apply', session_root='restored', session_id='work', request_id='advance', expected_revision=4, action=dict(type='redo'))
        current = self.cli('session.verify', session_root='restored', session_id='work')
        self.assertEqual(current['revision'], 5)
        self.assertNotEqual(self.identity(Path(record['target']))['sha256'], record['sha256'])
        # Receipt recognition must not open SQLite or attempt to repair a live journal.
        sidecar = Path(record['target']+'-journal'); sidecar.write_bytes(b'owned writer evidence')
        data = Path(record['target']).read_bytes()
        result = self.run_history('recover', args, control=dict(timeout_ms=0))
        self.assertEqual(result['session'], original['session'])
        self.assertEqual(result['session']['revision'], 4)
        self.assertEqual(Path(record['target']).read_bytes(), data)
        self.assertEqual(sidecar.read_bytes(), b'owned writer evidence')
        sidecar.unlink()
        self.assertEqual(self.cli('session.verify', session_root='restored', session_id='work'), current)
        self.assertFalse(Path(record['staging_path']).exists())

    def test_changed_restore_with_missing_destination_is_never_recreated(self):
        _, _, record = self.prepared('recover')
        self.cli('session.apply', session_root='restored', session_id='work', request_id='advance', expected_revision=4, action=dict(type='redo'))
        Path(record['target']).unlink(); before = self.files()
        self.finish(error='PUBLICATION_CONFLICT')
        self.assertEqual(self.files(), before)

    def test_immutable_history_output_requires_original_bytes_even_if_same_file(self):
        _, _, record = self.prepared('migrate')
        with closing(sqlite3.connect(record['target'])) as db:
            db.execute('PRAGMA user_version=1'); db.commit()
        before = self.files(); self.finish(error='PUBLICATION_CONFLICT'); self.assertEqual(self.files(), before)

    def test_restore_requires_both_physical_identity_witnesses(self):
        _, _, record = self.prepared('recover')
        path = Path(record['target']); data = path.read_bytes(); path.unlink(); path.write_bytes(data)
        before = self.files(); self.finish(error='PUBLICATION_CONFLICT'); self.assertEqual(self.files(), before)
        path.unlink(); os.link(record['staging_path'], path)
        stage = Path(record['staging_path']); stage.unlink(); stage.write_bytes(data)
        before = self.files(); self.finish(error='PUBLICATION_CONFLICT'); self.assertEqual(self.files(), before)
        stage.unlink(); before = self.files(); self.finish(error='PUBLICATION_EVIDENCE_MISSING'); self.assertEqual(self.files(), before)

    def test_absent_history_target_checks_sidecars_and_cancellation_before_link(self):
        args, _, record = self.prepared('backup')
        path = Path(record['target']); data = path.read_bytes(); path.unlink(); self.dbpath().unlink()
        before = self.files(); self.finish(control=dict(timeout_ms=0), error='TIMEOUT'); self.assertEqual(self.files(), before)
        for suffix in ['-journal', '-wal', '-shm']:
            sidecar = Path(str(path)+suffix); sidecar.write_bytes(b'preserve')
            before = self.files(); self.finish(error='OUTPUT_EXISTS'); self.assertEqual(self.files(), before); sidecar.unlink()
        result = self.run_history('backup', args)
        self.assertEqual(path.read_bytes(), data); self.assertTrue(result['publication']['replayed'])

    def test_record_versions_kind_and_bounds_are_checked_without_loosening_exports(self):
        _, _, record = self.prepared('backup')
        for change in [dict(version=1), dict(history='unknown'), dict(history=None), dict(bytes=128*1024*1024+1)]:
            self.change(**change); before = self.files(); self.finish(error='PUBLICATION_CORRUPT'); self.assertEqual(self.files(), before)
            self.change(**record)
        caps = self.cli('capabilities')['durable_publication']
        self.assertEqual(caps['maximum_output_bytes'], 32*1024*1024)
        self.assertEqual(caps['maximum_history_bytes'], 128*1024*1024)

    def test_prepared_history_from_relocated_ledger_cannot_escape_workspace(self):
        _, _, record = self.prepared('migrate'); path = Path(record['target']); path.unlink()
        inner = self.root/'inner'; dest = inner/'.inkbolt/publications'; dest.mkdir(parents=True)
        (dest/'publications.sqlite3').write_bytes(self.ledger().read_bytes()); outer = self.root
        try:
            self.root = inner; self.assertEqual(self.saved()['state'], 'prepared')
            self.finish(error='PATH_OUTSIDE_WORKSPACE'); self.assertFalse(path.exists())
        finally: self.root = outer

    def test_concurrent_history_requests_share_one_success_and_preserve_competing_output(self):
        self.fixture(); self.v1()
        for kind in ['backup', 'recover', 'migrate']:
            args = self.args(kind, kind)
            def call(_):
                request = dict(command='session.'+kind, **args)
                p = subprocess.run([str(EXE), '--workspace', str(self.root)], input=json.dumps(request).encode(), capture_output=True, timeout=30)
                self.assertEqual(p.stderr, b''); return json.loads(p.stdout)
            with ThreadPoolExecutor(4) as pool: results = list(pool.map(call, range(4)))
            self.assertTrue(all(r['ok'] for r in results), results)
            self.assertEqual(sum(not r['result']['publication']['replayed'] for r in results), 1)
            before = self.files(); self.run_history(kind, dict(args, receipt=dict(request_id='other')), error='OUTPUT_EXISTS'); self.assertEqual(self.files(), before)

    def test_mcp_schema_workspace_defaults_and_original_optional_behavior(self):
        self.fixture(); self.v1()
        with closing(Client(('--tools', 'core'), workspace=self.root)) as client:
            client.initialize()
            for kind in ['backup', 'recover', 'migrate']:
                schema = client.success('schema.lookup', name='session.'+kind, full=True)['schema']
                self.assertNotIn('receipt', schema['required'])
                self.assertNotIn('receipt_root', schema['$defs']['ReceiptTarget']['required'])
                args = self.args(kind, kind)
                response = client.tool('run', command='session.'+kind, arguments=args)
                self.assertFalse(response['isError'], response)
                result = response['structuredContent']['result']
                response = client.tool('run', command='session.'+kind, arguments=dict(args, control=dict(timeout_ms=0)))
                self.assertFalse(response['isError'], response)
                replay = response['structuredContent']['result']
                self.assertEqual(replay['session'], result['session']); self.assertTrue(replay['publication']['replayed'])
        raw = self.cli('schema.lookup', scoped=False, name='session.backup', full=True)['schema']
        self.assertIn('receipt_root', raw['$defs']['ReceiptTarget']['required'])
        job = self.cli('schema.lookup', name='job.list', full=True)['schema']
        self.assertNotIn('job_root', job['required'])
        plain = self.backup(4, name='plain.sqlite3'); self.assertNotIn('publication', plain)
        self.backup(4, name='plain.sqlite3', error='OUTPUT_EXISTS')

    def test_checked_history_above_export_byte_limit_uses_history_limit(self):
        self.fixture(); source = self.v1(); path = Path(source['file_path'])
        # Free pages are legal SQLite history and make a realistic large copy
        # without manufacturing new document limits or copied application assets.
        with closing(sqlite3.connect(path)) as db:
            db.execute('CREATE TABLE original_padding(data BLOB)')
            db.execute('INSERT INTO original_padding VALUES(zeroblob(?))', (33*1024*1024,))
            db.commit(); db.execute('DROP TABLE original_padding'); db.commit()
        self.assertGreater(path.stat().st_size, 32*1024*1024)
        source = self.identity(path); original = path.read_bytes()
        restored = self.run_history('recover')
        self.assertEqual(Path(restored['database']).read_bytes(), original)
        copied = self.cli('session.backup', session_id='work', session_root='restored', expected_revision=4, output=dict(file_name='large.sqlite3'), receipt=dict(request_id='large'))
        self.assertGreater(copied['backup']['bytes'], 32*1024*1024)
        self.assertEqual(self.rows(self.root/'large.sqlite3'), self.rows(path))
        migrated = self.run_history('migrate', self.args('migrate', 'migration'))
        self.assertGreater(migrated['backup']['bytes'], 32*1024*1024)
        self.assertEqual(self.rows(Path(migrated['backup']['file_path'])), self.rows(path))
        self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__': unittest.main()
