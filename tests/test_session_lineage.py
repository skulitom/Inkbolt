"""Original storage fixtures, immutable migration and linked continuation contracts."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import unittest

from test_cli import EXE
from test_mcp import Client
from test_images_cli import png
import test_session_backups as backups


# Frozen original v1 contract, independently constructed (no runtime schema export).
V1 = [
    "CREATE TABLE states(id INTEGER PRIMARY KEY, payload BLOB NOT NULL, sha256 TEXT NOT NULL) STRICT",
    "CREATE TABLE meta(id INTEGER PRIMARY KEY CHECK(id=1), session_id TEXT NOT NULL, revision INTEGER NOT NULL, current_state INTEGER NOT NULL REFERENCES states(id), undo_json TEXT NOT NULL, redo_json TEXT NOT NULL, sha256 TEXT NOT NULL) STRICT",
    "CREATE TABLE requests(request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, revision INTEGER UNIQUE NOT NULL, payload BLOB NOT NULL, sha256 TEXT NOT NULL) STRICT",
    "CREATE TABLE snapshots(name TEXT PRIMARY KEY, state_id INTEGER NOT NULL REFERENCES states(id), revision INTEGER NOT NULL, sha256 TEXT NOT NULL) STRICT",
]


class SessionLineageTests(unittest.TestCase):
    setUp=backups.SessionBackupTests.setUp
    cli=backups.SessionBackupTests.cli
    save=backups.SessionBackupTests.save
    document=backups.SessionBackupTests.document
    apply=backups.SessionBackupTests.apply
    backup=backups.SessionBackupTests.backup
    recover=backups.SessionBackupTests.recover
    files=backups.SessionBackupTests.files
    dbpath=backups.SessionBackupTests.dbpath
    rows=backups.SessionBackupTests.rows
    identity=backups.SessionBackupTests.identity
    check_identity=backups.SessionBackupTests.check_identity
    fixture=backups.SessionBackupTests.fixture

    def v1(self):
        path=self.root/'v1.sqlite3'
        with closing(sqlite3.connect(path)) as db:
            db.execute('PRAGMA page_size=4096');db.execute('PRAGMA application_id=1229867859');db.execute('PRAGMA user_version=1')
            for sql in V1:db.execute(sql)
            for table,rows in self.rows(self.dbpath()).items():
                for row in rows:db.execute(f"INSERT INTO {table} VALUES({','.join('?' for _ in row)})",row)
            db.commit()
        return self.identity(path)

    def migrate(self,source,name='v2.sqlite3',**kw):
        return self.cli('session.migrate',session_id='work',source=source,target_version=kw.pop('target_version',2),output=dict(file_name=name),**kw)

    def continue_(self,parent,session='next',**kw):
        return self.cli('session.continue',session_id=session,request_id='continue',parent=parent,**kw)

    def parent(self,source,revision=1):
        return dict(source=source,session_id='work',revision=revision)

    def test_v1_remains_writable_and_migration_preserves_every_original_row(self):
        one=self.fixture();v1=self.v1();old=(self.root/'v1.sqlite3').read_bytes()
        self.recover(v1);before=self.cli('session.verify',session_id='work',session_root='recovered')
        self.assertEqual(before['storage_version'],1);self.assertIsNone(before['lineage'])
        result=self.migrate(v1);v2=result['backup'];self.check_identity(v2,self.root/'v2.sqlite3')
        self.assertEqual(result['session'],dict(before,storage_version=2));self.assertEqual(self.rows(self.root/'v2.sqlite3'),self.rows(self.root/'v1.sqlite3'))
        self.assertEqual((self.root/'v1.sqlite3').read_bytes(),old)
        with closing(sqlite3.connect(self.root/'v2.sqlite3')) as db:self.assertEqual(db.execute('SELECT * FROM lineage').fetchall(),[])
        self.recover(v2,root='migrated')
        for root in ['recovered','migrated']:
            retry=self.apply('one',0,one,session_root=root,control=dict(timeout_ms=0));self.assertTrue(retry['replayed'])
            self.assertEqual(self.cli('session.read',session_id='work',snapshot='first',session_root=root)['document'],dict(retry['document'],revision=2))
            self.apply('redo',4,dict(type='redo'),session_root=root)
        self.assertEqual(self.cli('session.verify',session_id='work',session_root='recovered')['storage_version'],1)
        self.assertEqual(self.cli('session.verify',session_id='work',session_root='migrated')['storage_version'],2)
        self.migrate(v2,name='redundant.sqlite3',error='MIGRATION_NOT_NEEDED')
        self.assertFalse((self.root/'redundant.sqlite3').exists())

    def test_continuation_selects_exact_revision_and_keeps_parent_history(self):
        self.fixture();source=self.backup(4)['backup'];before=self.files();parent=self.parent(source,3)
        result=self.continue_(parent);origin=result['lineage'];self.assertFalse(result['replayed']);self.assertEqual(result['receipt']['action'],'continue')
        self.assertEqual(result['document']['revision'],0);self.assertEqual(result['document']['items'][0]['opacity'],.5)
        old=self.cli('session.receipt',session_id='work',request_id='two')
        self.assertEqual(result['document'],dict(old['document'],revision=0));self.assertEqual(result['resources'],old['resources'])
        self.assertEqual(origin['parent'],parent);self.assertEqual(origin['source_head_revision'],4);self.assertEqual(origin['source_storage_version'],2)
        self.assertEqual(origin['source_state_sha256'],old['receipt']['state_sha256'])
        self.assertEqual(origin['source_history_sha256'],self.cli('session.verify',session_id='work')['history_sha256'])
        read=self.cli('session.read',session_id='next');self.assertEqual([read['undo_depth'],read['redo_depth'],len(read['snapshots'])],[0,0,0])
        verified=self.cli('session.verify',session_id='next');self.assertEqual(verified['lineage'],origin);self.assertEqual(verified['states'],1)
        self.cli('session.apply',session_id='next',request_id='edit',expected_revision=0,action=dict(type='edit',operations=[dict(op='properties',id='box',opacity=.8)]))
        self.assertEqual({p:v for p,v in self.files().items() if p in before},before)
        next_source=self.cli('session.backup',session_id='next',expected_revision=1,output=dict(file_name='next.sqlite3'))['backup']
        second=self.continue_(dict(source=next_source,session_id='next',revision=1),session='third')
        self.assertEqual(second['lineage']['parent']['session_id'],'next');self.assertEqual(second['document']['items'][0]['opacity'],.8)
        self.assertNotIn('lineage',second['lineage']['parent']) # bounded single link; no recursive expansion

    def test_durable_replay_needs_no_parent_and_preserves_compact_lineage(self):
        self.fixture();source=self.backup(4)['backup'];parent=self.parent(source)
        result=self.continue_(parent,response_mode='compact');self.assertLessEqual(len(json.dumps(result).encode()),8192)
        self.assertNotIn('document',result);self.assertEqual(result['document_ref']['revision'],0)
        self.cli('session.apply',session_id='next',request_id='undo-proof',expected_revision=0,action=dict(type='edit',operations=[dict(op='properties',id='box',opacity=.8)]))
        (self.root/'history.sqlite3').unlink()
        retry=self.continue_(parent,response_mode='compact',control=dict(timeout_ms=0));self.assertTrue(retry['replayed'])
        self.assertEqual(retry['current_revision'],1);self.assertEqual(retry['receipt_summary'],result['receipt_summary']);self.assertEqual(retry['lineage'],result['lineage'])
        self.assertEqual(self.cli('session.receipt',session_id='next',request_id='continue')['document']['items'][0]['opacity'],1)
        self.continue_(dict(parent,revision=2),error='REQUEST_ID_REUSED',control=dict(timeout_ms=0))
        self.assertEqual(self.cli('session.verify',session_id='next')['revision'],1)

    def test_rejections_never_publish_or_change_source(self):
        self.fixture();v1=self.v1();source=self.backup(4)['backup'];before=self.files()
        for command in ['migrate','continue']:
            call=(lambda s,**kw:self.migrate(s,**kw)) if command=='migrate' else (lambda s,**kw:self.continue_(self.parent(s),**kw))
            call(dict(v1,sha256='0'*64),error='SOURCE_MISMATCH')
            call(v1,control=dict(timeout_ms=0),error='TIMEOUT')
        self.migrate(v1,target_version=1,error='SESSION_FORMAT')
        self.continue_(self.parent(source,5),error='REVISION_NOT_FOUND')
        self.continue_(self.parent(source),session='work',error='INVALID_REQUEST')
        self.continue_(dict(self.parent(source),session_id='wrong'),error='SESSION_CORRUPT')
        self.assertEqual(self.files(),before);self.assertEqual(list(self.root.rglob('*.tmp')),[])
        self.migrate(v1);before=self.files();self.migrate(v1,error='OUTPUT_EXISTS');self.assertEqual(self.files(),before)

    def test_lineage_checksums_and_initial_receipt_links_are_checked(self):
        self.fixture();parent=self.parent(self.backup(4)['backup'])
        for variant in ['checksum','deleted','parent','initial','unknown','rowid']:
            self.continue_(parent,session=variant)
            path=self.root/'.inkbolt/sessions'/(hashlib.sha256(variant.encode()).hexdigest()+'.sqlite3')
            with closing(sqlite3.connect(path)) as db:
                if variant=='deleted':db.execute('DELETE FROM lineage')
                elif variant=='rowid':
                    db.execute('PRAGMA ignore_check_constraints=ON');db.execute('UPDATE lineage SET id=2')
                elif variant=='checksum':db.execute("UPDATE lineage SET sha256=?",('0'*64,))
                else:
                    payload=json.loads(db.execute('SELECT payload FROM lineage').fetchone()[0])
                    if variant=='parent':payload['parent']['revision']=2
                    if variant=='initial':payload['initial_state_sha256']='0'*64
                    if variant=='unknown':payload['version']=9
                    data=json.dumps(payload,separators=(',',':')).encode();db.execute('UPDATE lineage SET payload=?,sha256=?',(data,hashlib.sha256(data).hexdigest()))
                db.commit()
            before=self.files();self.cli('session.read',session_id=variant,error='SESSION_CORRUPT');self.cli('session.verify',session_id=variant,error='SESSION_CORRUPT');self.assertEqual(self.files(),before)

    def test_parent_byte_hash_and_new_canonical_hash_remain_distinct(self):
        self.save()
        with closing(sqlite3.connect(self.dbpath())) as db:
            payload=db.execute('SELECT payload FROM states WHERE id=0').fetchone()[0]+b' \n'
            source_hash=hashlib.sha256(payload).hexdigest();db.execute('UPDATE states SET payload=?,sha256=? WHERE id=0',(payload,source_hash))
            fingerprint,data=db.execute('SELECT fingerprint,payload FROM requests WHERE revision=0').fetchone()
            receipt=json.loads(data);receipt['state_sha256']=source_hash;data=json.dumps(receipt,separators=(',',':')).encode()
            digest=hashlib.sha256(json.dumps([fingerprint,list(data)],separators=(',',':')).encode()).hexdigest()
            db.execute('UPDATE requests SET payload=?,sha256=? WHERE revision=0',(data,digest));db.commit()
        source=self.backup(0)['backup'];before=self.files();result=self.continue_(self.parent(source,0))
        self.assertEqual(result['lineage']['source_state_sha256'],source_hash)
        self.assertNotEqual(result['lineage']['initial_state_sha256'],source_hash)
        self.assertEqual(result['lineage']['initial_state_sha256'],result['receipt']['state_sha256'])
        self.assertEqual(self.cli('session.verify',session_id='next')['lineage'],result['lineage'])
        self.assertEqual({p:v for p,v in self.files().items() if p in before},before)

    def test_competing_publishers_share_one_durable_continuation(self):
        self.fixture();parent=self.parent(self.backup(4)['backup']);v1=self.v1()
        def run(args):
            p=subprocess.run([str(EXE),'--workspace',str(self.root)],input=json.dumps(args).encode(),capture_output=True,timeout=30)
            self.assertEqual(p.stderr,b'');return json.loads(p.stdout)
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(run,[dict(command='session.continue',session_id='next',request_id='continue',parent=parent)]*2))
        self.assertTrue(all(r['ok'] for r in results));self.assertEqual(sum(not r['result']['replayed'] for r in results),1)
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(run,[dict(command='session.migrate',session_id='work',source=v1,target_version=2,output=dict(file_name='winner.sqlite3'))]*2))
        self.assertEqual(sum(r['ok'] for r in results),1);self.assertEqual(next(r for r in results if not r['ok'])['error']['code'],'OUTPUT_EXISTS')
        self.assertEqual(self.rows(self.root/'winner.sqlite3'),self.rows(self.root/'v1.sqlite3'));self.assertEqual(list(self.root.rglob('*.tmp')),[])

    def test_mcp_schema_workspace_and_v1_continuation(self):
        self.fixture();source=self.v1()
        with closing(Client(('--tools','core'),workspace=self.root)) as c:
            c.initialize()
            for command in ['session.continue','session.migrate']:
                self.assertEqual(c.success('schema.lookup',name=command)['name'],command)
            result=c.tool('run',command='session.continue',arguments=dict(session_id='next',request_id='continue',parent=self.parent(source,0),response_mode='compact'))['structuredContent']['result']
            self.assertEqual(result['lineage']['source_storage_version'],1);self.assertEqual(result['document_summary']['item_count'],0)
            self.assertEqual(self.cli('session.verify',session_id='next')['storage_version'],2)
            migrated=c.tool('run',command='session.migrate',arguments=dict(session_id='work',source=source,target_version=2,output=dict(file_name='mcp.sqlite3')))['structuredContent']['result']
            self.check_identity(migrated['backup'],self.root/'mcp.sqlite3')
            outside=dict(source,file_path=str(self.root.parent/'outside.sqlite3'))
            self.continue_(self.parent(outside),session='outside',error='PATH_OUTSIDE_WORKSPACE')

    def test_continuation_keeps_foreign_resources_until_explicit_rebinding(self):
        source_bytes=png(2,2,bytes([10,80,140,255]*4));(self.root/'original.png').write_bytes(source_bytes)
        asset=self.cli('asset.import',source_path='original.png')['asset']
        doc=self.document();doc['assets']={'source':asset};doc['items']=[dict(id='image',content=dict(type='image',asset_id='source',width=2,height=2))]
        self.save(doc);source=self.backup(0)['backup'];before=self.files();outer=self.root
        inner=outer/'portable';inner.mkdir();(inner/'parent.sqlite3').write_bytes(Path(source['file_path']).read_bytes());(inner/'original.png').write_bytes(source_bytes)
        try:
            self.root=inner;parent=self.parent(self.identity(inner/'parent.sqlite3'),0)
            continued=self.continue_(parent)
            self.assertTrue(Path(continued['resources']['asset_root']).samefile(outer/'.inkbolt/assets'))
            self.assertFalse((inner/'.inkbolt/assets').exists())
            ref=lambda revision:dict(session_id='next',revision=revision)
            self.cli('document.render',document=ref(0),error='PATH_OUTSIDE_WORKSPACE')
            self.cli('asset.import',source_path='original.png')
            action=dict(type='resources',resources=dict(asset_root='.inkbolt/assets',font_root=None))
            proposal=self.cli('session.dry_run',session_id='next',request_id='rebind',expected_revision=0,action=action)
            self.cli('session.apply_proposal',proposal=proposal['proposal'],action=action)
            self.assertEqual(self.cli('document.render',document=ref(1))['data'],'0a508cff'*4)
            self.assertEqual(self.cli('session.verify',session_id='next')['lineage'],continued['lineage'])
            self.check_identity(parent['source'],inner/'parent.sqlite3')
        finally:self.root=outer
        self.assertEqual({p:v for p,v in self.files().items() if p in before},before)

    def test_sidecars_and_unknown_storage_are_rejected_before_final_publication(self):
        self.fixture();source=self.v1();path=self.root/'v1.sqlite3'
        for suffix in ['-journal','-wal','-shm']:
            sidecar=Path(str(path)+suffix);sidecar.write_bytes(b'keep');before=self.files()
            self.migrate(source,error='BACKUP_SIDECAR');self.continue_(self.parent(source),error='BACKUP_SIDECAR');self.assertEqual(self.files(),before);sidecar.unlink()
            target=self.root/'.inkbolt/sessions'/(hashlib.sha256(b'next').hexdigest()+'.sqlite3'+suffix)
            target.write_bytes(b'keep');before=self.files();self.continue_(self.parent(source),error='OUTPUT_EXISTS');self.assertEqual(self.files(),before);target.unlink()
        for variant in ['unknown','corrupt']:
            modified=self.root/(variant+'.sqlite3');modified.write_bytes(path.read_bytes())
            with closing(sqlite3.connect(modified)) as db:
                if variant=='unknown':db.execute('PRAGMA user_version=99')
                else:db.execute("UPDATE states SET sha256=?",('0'*64,))
                db.commit()
            bad=self.identity(modified);before=self.files();error='SESSION_FORMAT' if variant=='unknown' else 'SESSION_CORRUPT'
            self.migrate(bad,error=error);self.continue_(self.parent(bad),error=error);self.assertEqual(self.files(),before)


if __name__=='__main__':unittest.main()
