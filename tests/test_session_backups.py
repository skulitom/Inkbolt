"""Whole-history backup/recovery with independent SQLite rows and byte identities."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import unittest
from external_workspace import files as workspace_files

import test_agent_workspace as workspace
from test_images_cli import png
from test_mcp import Client


class SessionBackupTests(unittest.TestCase):
    setUp=workspace.AgentWorkspaceTests.setUp
    cli=workspace.AgentWorkspaceTests.cli
    save=workspace.AgentWorkspaceTests.save
    document=workspace.AgentWorkspaceTests.document
    ref=workspace.AgentWorkspaceTests.ref

    def apply(self,rid,revision,action,**kw):
        return self.cli('session.apply',session_id='work',request_id=rid,expected_revision=revision,action=action,**kw)

    def backup(self,revision,name='history.sqlite3',**kw):
        return self.cli('session.backup',session_id='work',expected_revision=revision,output=dict(file_name=name),**kw)

    def recover(self,source,root='recovered',**kw):
        return self.cli('session.recover',session_id='work',session_root=root,source=source,**kw)

    def files(self):
        return {str(p.relative_to(self.root)):(p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest()) for p in workspace_files(self.root) if p.is_file()}

    def dbpath(self,root='.inkbolt/sessions'):
        return self.root/root/(hashlib.sha256(b'work').hexdigest()+'.sqlite3')

    def rows(self,path):
        with closing(sqlite3.connect(path)) as db:
            return {table:db.execute(f'SELECT * FROM {table} ORDER BY {key}').fetchall() for table,key in [('meta','id'),('states','id'),('requests','revision'),('snapshots','name')]}

    def identity(self,path):
        data=path.read_bytes();return dict(file_path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())

    def check_identity(self,identity,path):
        self.assertTrue(Path(identity['file_path']).samefile(path))
        self.assertEqual(dict(identity,file_path=str(path)),self.identity(path))

    def fixture(self):
        self.save()
        one=dict(type='edit',operations=[dict(op='add',item=dict(id='box',content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=1,height=1),fill=[20,70,130,255])))])
        self.apply('one',0,one)
        self.apply('named',1,dict(type='snapshot',name='first'))
        self.apply('two',2,dict(type='edit',operations=[dict(op='properties',id='box',opacity=.5)]))
        self.apply('undo',3,dict(type='undo'))
        return one

    def test_complete_history_roundtrip_and_independent_continuation(self):
        one=self.fixture();state=self.cli('session.read',session_id='work');rows=self.rows(self.dbpath());before=self.files()
        result=self.backup(4);source=result['backup'];backup=self.root/'history.sqlite3'
        self.check_identity(source,backup);self.assertEqual(self.rows(backup),rows)
        self.assertEqual(result['session'],self.cli('session.verify',session_id='work'))
        self.assertEqual(result['session']['undo_depth'],1);self.assertEqual(result['session']['redo_depth'],1);self.assertEqual(result['session']['snapshots'],1)
        self.assertFalse(result['resources_copied']);self.assertFalse(result['migration_performed'])
        self.assertEqual({p:v for p,v in self.files().items() if p in before},before)
        receipt=self.recover(source);restored=self.dbpath('recovered')
        self.assertEqual(restored.read_bytes(),backup.read_bytes());self.assertEqual(self.rows(restored),rows)
        self.assertEqual(receipt['session'],result['session']);self.assertFalse(receipt['external_resources_verified'])
        self.assertEqual(self.cli('session.read',session_id='work',session_root='recovered'),state)
        for name in [None,'first']:
            self.assertEqual(self.cli('session.read',session_id='work',snapshot=name),self.cli('session.read',session_id='work',session_root='recovered',snapshot=name))
        for rid in ['create','one','named','two','undo']:
            self.assertEqual(self.cli('session.receipt',session_id='work',request_id=rid),self.cli('session.receipt',session_id='work',session_root='recovered',request_id=rid))
        replay=self.apply('one',0,one,session_root='recovered',control=dict(timeout_ms=0));self.assertTrue(replay['replayed']);self.assertEqual(replay['current_revision'],4)
        self.apply('redo',4,dict(type='redo'),session_root='recovered')
        self.assertEqual(self.cli('session.read',session_id='work',session_root='recovered')['document']['items'][0]['opacity'],.5)
        self.assertEqual(self.cli('session.read',session_id='work'),state);self.check_identity(source,backup)
        self.recover(source,error='OUTPUT_EXISTS');self.backup(4,error='OUTPUT_EXISTS')
        self.assertEqual(self.cli('session.verify',session_id='work',session_root='recovered')['revision'],5)

    def test_racing_publishers_preserve_one_complete_winner(self):
        self.fixture()
        def request(command,**kw):
            from test_cli import EXE
            import subprocess
            p=subprocess.run([str(EXE),'--workspace',str(self.root)],input=json.dumps(dict(command=command,session_id='work',**kw)).encode(),capture_output=True,timeout=30)
            self.assertEqual(p.stderr,b'');return json.loads(p.stdout)
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda _:request('session.backup',expected_revision=4,output=dict(file_name='winner.sqlite3')),range(2)))
        self.assertEqual(sum(r['ok'] for r in results),1);self.assertEqual(next(r for r in results if not r['ok'])['error']['code'],'OUTPUT_EXISTS')
        source=next(r for r in results if r['ok'])['result']['backup'];self.check_identity(source,self.root/'winner.sqlite3')
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda _:request('session.recover',session_root='restored',source=source),range(2)))
        self.assertEqual(sum(r['ok'] for r in results),1);self.assertEqual(next(r for r in results if not r['ok'])['error']['code'],'OUTPUT_EXISTS')
        self.assertEqual(self.dbpath('restored').read_bytes(),(self.root/'winner.sqlite3').read_bytes())
        self.assertEqual(list(self.root.rglob('*.tmp')),[])

    def test_rejection_preserves_backups_and_all_existing_destinations(self):
        self.fixture();source=self.backup(4)['backup'];backup=self.root/'history.sqlite3'
        for mutate in [dict(bytes=source['bytes']+1),dict(sha256='0'*64),dict(sha256=source['sha256'].upper()),dict(bytes=128*1024*1024+1)]:
            before=self.files();error='INVALID_REQUEST' if 'sha256' in mutate and mutate['sha256']!= '0'*64 or mutate.get('bytes',0)>128*1024*1024 else 'SOURCE_MISMATCH'
            self.recover(dict(source,**mutate),error=error);self.assertEqual(self.files(),before)
        before=self.files();self.cli('session.recover',session_id='wrong',session_root='recovered',source=source,error='SESSION_CORRUPT');self.assertEqual(self.files(),before)
        for suffix in ['-journal','-wal','-shm']:
            target=self.dbpath('blocked-'+suffix[1:]);target.parent.mkdir();sidecar=Path(str(target)+suffix);sidecar.write_bytes(b'keep')
            before=self.files();self.recover(source,root=target.parent.name,error='OUTPUT_EXISTS');self.assertEqual(self.files(),before)
            sidecar=Path(str(backup)+suffix);sidecar.write_bytes(b'keep')
            before=self.files();self.recover(source,error='BACKUP_SIDECAR');self.assertEqual(self.files(),before);sidecar.unlink()
        before=self.files();self.backup(3,name='stale.sqlite3',error='REVISION_CONFLICT');self.assertEqual(self.files(),before)
        for name in ['CON.sqlite3','../escape.sqlite3','wrong.json','.inkbolt-history.sqlite3']:
            self.backup(4,name=name,error='INVALID_REQUEST')
        self.assertEqual(self.files(),before)
        self.recover(source,root='.inkbolt/sessions',error='OUTPUT_EXISTS')

    def test_corrupt_or_future_backup_is_never_repaired_or_published(self):
        self.fixture();self.backup(4)
        for variant in ['state','receipt','head','version','schema','truncated']:
            path=self.root/(variant+'.sqlite3');path.write_bytes((self.root/'history.sqlite3').read_bytes())
            if variant=='truncated':path.write_bytes(path.read_bytes()[:100])
            else:
                with closing(sqlite3.connect(path)) as db:
                    if variant=='state':db.execute("UPDATE states SET payload=x'00' WHERE id=0")
                    if variant=='receipt':db.execute("UPDATE requests SET sha256=? WHERE revision=0",('0'*64,))
                    if variant=='head':db.execute("UPDATE meta SET sha256=?",('0'*64,))
                    if variant=='version':db.execute('PRAGMA user_version=99')
                    if variant=='schema':db.execute('CREATE TABLE extra(x)')
                    db.commit()
            before=self.files();self.recover(self.identity(path),root='restore-'+variant,error='SESSION_FORMAT' if variant in ['schema','version'] else 'SESSION_CORRUPT');self.assertEqual(self.files(),before)
        self.assertEqual(list(self.root.rglob('*.tmp')),[])

    def test_stale_receipt_chain_is_checked(self):
        self.fixture()
        # Recompute local row checksums to test semantic linkage, independently of simple byte corruption.
        with closing(sqlite3.connect(self.dbpath())) as db:
            fingerprint,payload=db.execute('SELECT fingerprint,payload FROM requests WHERE revision=3').fetchone()
            receipt=json.loads(payload);receipt['from_state']=0
            payload=json.dumps(receipt,separators=(',',':')).encode();digest=hashlib.sha256(json.dumps([fingerprint,list(payload)],separators=(',',':')).encode()).hexdigest()
            db.execute('UPDATE requests SET payload=?,sha256=? WHERE revision=3',(payload,digest));db.commit()
        before=self.files();self.backup(4,error='SESSION_CORRUPT');self.cli('session.verify',session_id='work',error='SESSION_CORRUPT');self.assertEqual(self.files(),before)

    def test_snapshot_must_match_its_exact_historical_revision(self):
        self.fixture()
        with closing(sqlite3.connect(self.dbpath())) as db:
            snapshot=dict(name='first',state_id=3,revision=2)
            digest=hashlib.sha256(json.dumps(snapshot,separators=(',',':')).encode()).hexdigest()
            db.execute('UPDATE snapshots SET state_id=3,sha256=? WHERE name=?',(digest,'first'));db.commit()
        before=self.files();self.backup(4,error='SESSION_CORRUPT');self.assertEqual(self.files(),before)

    def test_history_byte_count_measures_stored_payload_not_normalized_json(self):
        self.save();original=self.cli('session.verify',session_id='work')
        with closing(sqlite3.connect(self.dbpath())) as db:
            payload=db.execute('SELECT payload FROM states WHERE id=0').fetchone()[0]+b' \n'
            state_hash=hashlib.sha256(payload).hexdigest();db.execute('UPDATE states SET payload=?,sha256=? WHERE id=0',(payload,state_hash))
            fingerprint,receipt=db.execute('SELECT fingerprint,payload FROM requests WHERE revision=0').fetchone()
            receipt=json.loads(receipt);receipt['state_sha256']=state_hash;receipt=json.dumps(receipt,separators=(',',':')).encode()
            digest=hashlib.sha256(json.dumps([fingerprint,list(receipt)],separators=(',',':')).encode()).hexdigest()
            db.execute('UPDATE requests SET payload=?,sha256=? WHERE revision=0',(receipt,digest));db.commit()
        verified=self.cli('session.verify',session_id='work');self.assertEqual(verified['state_bytes'],original['state_bytes']+2)
        backup=self.backup(0);self.assertEqual(backup['session'],verified)

    def test_cancellation_and_mcp_share_the_same_checked_contract(self):
        self.fixture();before=self.files()
        self.backup(4,control=dict(timeout_ms=0),error='TIMEOUT');self.assertEqual(self.files(),before)
        with closing(Client(('--tools','core'),workspace=self.root)) as c:
            c.initialize()
            result=c.tool('run',command='session.backup',arguments=dict(session_id='work',expected_revision=4,output=dict(file_name='mcp.sqlite3')))['structuredContent']['result']
            self.check_identity(result['backup'],self.root/'mcp.sqlite3')
            source=result['backup'];before=self.files()
            self.recover(source,control=dict(timeout_ms=0),error='TIMEOUT');self.assertEqual(self.files(),before)
            actual=c.tool('run',command='session.recover',arguments=dict(session_id='work',session_root='mcp-restored',source=source))['structuredContent']['result']
            self.assertEqual(actual['session'],result['session']);self.assertEqual(self.dbpath('mcp-restored').read_bytes(),(self.root/'mcp.sqlite3').read_bytes())
        self.assertEqual(list(self.root.rglob('*.tmp')),[])

    def test_resource_stores_stay_external_and_rebinding_is_explicit(self):
        source_bytes=png(2,2,bytes([10,80,140,255]*4));(self.root/'original.png').write_bytes(source_bytes)
        asset=self.cli('asset.import',source_path='original.png')['asset']
        doc=self.document();doc['assets']={'source':asset};doc['items']=[dict(id='image',content=dict(type='image',asset_id='source',width=2,height=2))]
        doc=self.save(doc)['document'];backup=self.backup(0)['backup'];before=self.files();outer=self.root
        inner=outer/'portable';inner.mkdir();(inner/'history.sqlite3').write_bytes(Path(backup['file_path']).read_bytes());(inner/'original.png').write_bytes(source_bytes)
        try:
            self.root=inner
            source=self.identity(inner/'history.sqlite3');self.recover(source,root='.inkbolt/sessions')
            self.assertEqual(self.cli('session.read',session_id='work')['document'],doc)
            self.cli('document.render',document=self.ref(),error='PATH_OUTSIDE_WORKSPACE')
            self.assertFalse((inner/'.inkbolt/assets').exists())
            self.assertEqual(self.cli('asset.import',source_path='original.png')['asset'],asset)
            action=dict(type='resources',resources=dict(asset_root='.inkbolt/assets',font_root=None))
            proposal=self.cli('session.dry_run',session_id='work',request_id='rebind',expected_revision=0,action=action)
            self.cli('session.apply_proposal',proposal=proposal['proposal'],action=action)
            self.assertEqual(self.cli('document.render',document=self.ref(1))['data'],'0a508cff'*4)
            self.assertEqual(self.cli('session.read',session_id='work')['current_revision'],1)
        finally:self.root=outer
        self.assertEqual({p:v for p,v in self.files().items() if p in before},before)


if __name__=='__main__':unittest.main()
