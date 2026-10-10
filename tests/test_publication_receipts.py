"""Durable publication checked against file bytes and independent SQLite records."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import unittest
from external_workspace import files as workspace_files
import test_agent_workspace as workspace
from test_cli import EXE
from test_images_cli import png
from test_mcp import Client


class PublicationReceiptTests(unittest.TestCase):
    setUp=workspace.AgentWorkspaceTests.setUp
    cli=workspace.AgentWorkspaceTests.cli
    document=workspace.AgentWorkspaceTests.document
    save=workspace.AgentWorkspaceTests.save

    def publish(self,doc=None,rid='export',name='result.png',**kw):
        return self.cli('document.publish',document=doc or self.document(),output=dict(file_name=name,format=kw.pop('format','png')),receipt=dict(request_id=rid),**kw)

    def saved(self,rid='export',**kw):
        return self.cli('publication.receipt',request_id=rid,**kw)

    def recover(self,rid='export',**kw):
        return self.cli('publication.recover',request_id=rid,**kw)

    def ledger(self):return self.root/'.inkbolt/publications/publications.sqlite3'

    def files(self):
        return {str(p.relative_to(self.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in workspace_files(self.root) if p.is_file()}

    def change(self,fn):
        with closing(sqlite3.connect(self.ledger())) as db:
            record=json.loads(db.execute('SELECT payload FROM publications WHERE request_id=?',('export',)).fetchone()[0]);fn(record)
            payload=json.dumps(record,separators=(',',':')).encode();db.execute('UPDATE publications SET payload=?,sha256=? WHERE request_id=?',(payload,hashlib.sha256(payload).hexdigest(),'export'));db.commit()
        return record

    def prepared(self):
        self.publish()
        with closing(sqlite3.connect(self.ledger())) as db:record=json.loads(db.execute('SELECT payload FROM publications').fetchone()[0])
        os.link(record['target'],record['staging_path'])
        self.change(lambda r:r.update(phase='prepared'))
        return record

    def test_exact_receipt_replay_and_historical_result_without_output(self):
        doc=self.document();result=self.publish(doc);path=self.root/'result.png';data=path.read_bytes()
        self.assertEqual(result['sha256'],hashlib.sha256(data).hexdigest());self.assertEqual(result['bytes'],len(data))
        self.assertEqual(result['publication']['state'],'complete');self.assertFalse(result['publication']['replayed'])
        self.assertEqual(list(self.root.glob('*.tmp')),[])
        with closing(sqlite3.connect(self.ledger())) as db:
            payload,sha=db.execute('SELECT payload,sha256 FROM publications').fetchone();record=json.loads(payload)
            self.assertEqual(hashlib.sha256(payload).hexdigest(),sha);self.assertEqual(record['phase'],'complete');self.assertEqual(record['bytes'],len(data))
        before=self.files();replayed=self.publish(doc,control=dict(timeout_ms=0));self.assertTrue(replayed['publication']['replayed']);self.assertEqual(self.files(),before)
        expected=dict(result,publication=dict(result['publication'],replayed=True))
        self.assertEqual(replayed,expected);self.assertEqual(self.saved()['result'],expected)
        path.unlink();self.assertEqual(self.recover(control=dict(timeout_ms=0)),expected);self.assertFalse(path.exists())
        self.assertFalse(self.saved()['output_rechecked'])
        self.publish(dict(doc,width=3),error='REQUEST_ID_REUSED');self.publish(doc,name='other.png',error='REQUEST_ID_REUSED')

    def test_session_retry_survives_advanced_or_missing_source_and_resources(self):
        image=png(2,2,bytes([10,80,140,255]*4));(self.root/'source.png').write_bytes(image)
        asset=self.cli('asset.import',source_path='source.png')['asset'];doc=self.document();doc['assets']={'image':asset};doc['items']=[dict(id='image',content=dict(type='image',asset_id='image',width=2,height=2))]
        self.save(doc)
        args=dict(session_id='work',expected_revision=0,output=dict(file_name='saved.png',format='png'),receipt=dict(request_id='export'))
        result=self.cli('session.publish',**args)
        self.cli('session.apply',session_id='work',request_id='change',expected_revision=0,action=dict(type='edit',operations=[dict(op='properties',id='image',opacity=.5)]))
        retry=self.cli('session.publish',**args,control=dict(timeout_ms=0));self.assertEqual(retry['sha256'],result['sha256']);self.assertEqual(retry['observed_current_revision'],0)
        for file in (self.root/'.inkbolt/assets').iterdir():file.unlink()
        dbpath=self.root/'.inkbolt/sessions'/(hashlib.sha256(b'work').hexdigest()+'.sqlite3');dbpath.unlink()
        self.assertEqual(self.cli('session.publish',**args,control=dict(timeout_ms=0)),retry)
        self.assertEqual((self.root/'source.png').read_bytes(),image)

    def test_prepared_recovery_publishes_once_without_original_document(self):
        record=self.prepared();path=Path(record['target']);data=path.read_bytes();path.unlink()
        self.assertEqual(self.saved()['state'],'prepared');self.assertIsNone(self.saved()['result'])
        before=self.files();self.recover(control=dict(timeout_ms=0),error='TIMEOUT');self.assertEqual(self.files(),before)
        result=self.recover();self.assertEqual(path.read_bytes(),data);self.assertTrue(result['publication']['replayed'])
        self.assertEqual(self.saved()['state'],'complete');self.assertFalse(Path(record['staging_path']).exists())
        self.assertEqual(self.recover(),result)

    def test_only_the_actual_staged_file_can_be_recognized_as_published(self):
        record=self.prepared();path=Path(record['target']);data=path.read_bytes();path.unlink();path.write_bytes(data)
        before=self.files();self.recover(error='PUBLICATION_CONFLICT');self.assertEqual(self.files(),before)
        path.unlink();os.link(record['staging_path'],path)
        result=self.recover(control=dict(timeout_ms=0));self.assertEqual(result['sha256'],hashlib.sha256(data).hexdigest())
        self.assertEqual(self.saved()['state'],'complete');self.assertEqual(path.read_bytes(),data)

    def test_missing_or_changed_evidence_is_preserved_and_rejected(self):
        record=self.prepared();stage=Path(record['staging_path']);path=Path(record['target']);data=stage.read_bytes()
        stage.write_bytes(b'x'*len(data));before=self.files();self.recover(error='PUBLICATION_CONFLICT');self.assertEqual(self.files(),before)
        stage.write_bytes(data);stage.unlink();before=self.files();self.recover(error='PUBLICATION_EVIDENCE_MISSING');self.assertEqual(self.files(),before)
        self.assertEqual(path.read_bytes(),data)

    def test_corrupt_rows_unknown_schema_and_outside_workspace_do_not_publish(self):
        record=self.prepared();path=Path(record['target']);path.unlink()
        self.change(lambda r:r.update(sha256='0'*64));before=self.files();self.recover(error='PUBLICATION_CORRUPT');self.assertEqual(self.files(),before)
        self.change(lambda r:r.update(sha256=record['sha256']))
        with closing(sqlite3.connect(self.ledger())) as db:db.execute('PRAGMA user_version=99');db.commit()
        before=self.files();self.recover(error='PUBLICATION_FORMAT');self.assertEqual(self.files(),before)
        with closing(sqlite3.connect(self.ledger())) as db:db.execute('PRAGMA user_version=1');db.commit()
        nested=self.root/'inner';nested.mkdir();dest=nested/'.inkbolt/publications';dest.mkdir(parents=True);(dest/'publications.sqlite3').write_bytes(self.ledger().read_bytes());outer=self.root
        try:
            self.root=nested
            self.assertEqual(self.saved()['state'],'prepared')
            self.recover(error='PATH_OUTSIDE_WORKSPACE');self.assertFalse(path.exists())
        finally:self.root=outer

    def test_existing_outputs_cancelled_new_work_and_wrong_ids_remain_unchanged(self):
        self.saved(error='PUBLICATION_NOT_FOUND');self.recover(error='PUBLICATION_NOT_FOUND');self.assertEqual(self.files(),{})
        self.publish(control=dict(timeout_ms=0),error='TIMEOUT');self.assertEqual(self.files(),{})
        path=self.root/'result.png';path.write_bytes(b'keep');before=self.files()
        self.publish(error='OUTPUT_EXISTS');self.assertEqual(self.files(),before)
        self.publish(rid='../../bad',error='INVALID_REQUEST');self.assertEqual(self.files(),before)
        self.publish(name='.inkbolt-publication-sneak.png',error='INVALID_REQUEST');self.assertEqual(self.files(),before)

    def test_racing_same_request_and_competing_request_ids_never_overwrite(self):
        doc=self.document()
        def run(rid):
            args=dict(command='document.publish',document=doc,output=dict(file_name='result.png',format='png'),receipt=dict(request_id=rid))
            p=subprocess.run([str(EXE),'--workspace',str(self.root)],input=json.dumps(args).encode(),capture_output=True,timeout=30);self.assertEqual(p.stderr,b'');return json.loads(p.stdout)
        with ThreadPoolExecutor(4) as pool:results=list(pool.map(run,['export']*4))
        self.assertTrue(all(r['ok'] for r in results),results);self.assertEqual(sum(not r['result']['publication']['replayed'] for r in results),1)
        before=self.files();result=run('other');self.assertFalse(result['ok']);self.assertEqual(result['error']['code'],'OUTPUT_EXISTS');self.assertEqual(self.files(),before)

    def test_mcp_and_different_encoders_share_original_receipts(self):
        doc=self.document()
        with closing(Client(('--tools','core'),workspace=self.root)) as c:
            c.initialize()
            for format,extension in [('png','png'),('jpeg','jpg'),('tiff','tif'),('svg','svg'),('pdf','pdf'),('snapshot','json')]:
                output=dict(file_name='format.'+extension,format=format)
                if format=='jpeg':output['image_options']=dict(matte=[255,255,255])
                response=c.tool('run',command='document.publish',arguments=dict(document=doc,output=output,receipt=dict(request_id=format)))['structuredContent']
                self.assertTrue(response['ok'],(format,response));result=response['result']
                data=(self.root/('format.'+extension)).read_bytes();self.assertEqual(result['sha256'],hashlib.sha256(data).hexdigest())
                saved=c.tool('run',command='publication.receipt',arguments=dict(request_id=format))['structuredContent']['result']
                self.assertEqual(saved['result']['sha256'],result['sha256']);self.assertEqual(saved['state'],'complete')
                self.assertEqual(self.recover(format)['losses'],result['losses'])
            plain=self.cli('document.publish',document=doc,output=dict(file_name='plain.png',format='png'))
            self.assertNotIn('publication',plain);self.assertEqual((self.root/'plain.png').read_bytes(),(self.root/'format.png').read_bytes())


if __name__=='__main__':unittest.main()
