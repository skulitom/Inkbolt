"""Real CLI/MCP job contracts with independent bytes and SQLite inspection."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import json
import msvcrt
from pathlib import Path
import shutil
import sqlite3
import subprocess
from threading import Event
import time
import unittest
import test_agent_workspace as workspace
from test_cli import EXE
from test_editing_cli import png_pixels
from test_images_cli import png
from test_mcp import Client
from synthetic_font import geometric_font


class JobTests(unittest.TestCase):
    cli=workspace.AgentWorkspaceTests.cli
    document=workspace.AgentWorkspaceTests.document
    save=workspace.AgentWorkspaceTests.save

    def setUp(self):
        workspace.AgentWorkspaceTests.setUp(self)
        self.addCleanup(self.stop_owned)

    def ledger(self): return self.root/'.inkbolt/jobs/jobs.sqlite3'

    def stop_owned(self):
        if not self.ledger().exists(): return
        # Only handles whose creation time matches this fixture's recorded process
        # may be stopped. An observation race or reused PID is never a kill target.
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)];kernel.GetProcessTimes.restype=wintypes.BOOL
        kernel.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT];kernel.TerminateProcess.restype=wintypes.BOOL
        kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];kernel.WaitForSingleObject.restype=wintypes.DWORD
        kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
        identities=[]
        with closing(sqlite3.connect(self.ledger(),timeout=3)) as db:
            try:
                identities.append(json.loads(db.execute('SELECT payload FROM runtime').fetchone()[0]).get('owner'))
                identities.extend(json.loads(row[0]).get('runner') for row in db.execute('SELECT state FROM jobs'))
            except sqlite3.DatabaseError:return
        for identity in filter(None,identities):
            handle=kernel.OpenProcess(0x100000|0x1000|1,False,identity['pid'])
            if not handle:continue
            try:
                values=[wintypes.FILETIME() for _ in range(4)]
                if not kernel.GetProcessTimes(handle,*(ctypes.byref(v) for v in values)):continue
                created=(values[0].dwHighDateTime<<32)|values[0].dwLowDateTime
                if created!=identity['created']:continue
                kernel.TerminateProcess(handle,19)
                self.assertEqual(kernel.WaitForSingleObject(handle,10000),0)
            finally:kernel.CloseHandle(handle)

    @contextmanager
    def blocked_queue(self):
        root=self.root/'.inkbolt/jobs';root.mkdir(parents=True,exist_ok=True)
        with (root/'worker.lock').open('a+b') as lease:
            lease.seek(0);msvcrt.locking(lease.fileno(),msvcrt.LK_NBLCK,1)
            try:yield
            finally:lease.seek(0);msvcrt.locking(lease.fileno(),msvcrt.LK_UNLCK,1)

    def start(self,doc=None,rid='one',name=None,**kw):
        return self.cli('job.start',request_id=rid,document=doc or self.document(),output=dict(file_name=name or rid+'.png',format='png'),**kw)

    def finish(self,rid='one',expected='completed'):
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            result=self.cli('job.wait',request_id=rid,wait_ms=1000)
            if result['state'] not in ['queued','running']:
                self.assertEqual(result['state'],expected,result)
                return result
            self.assertFalse(result['recovery_required'],result)
        self.fail('Job failed to reach its terminal state')

    def idle(self):
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            with closing(sqlite3.connect(self.ledger(),timeout=3)) as db:
                runtime=json.loads(db.execute('SELECT payload FROM runtime').fetchone()[0])
            if runtime['owner'] is None:return
            time.sleep(.02)
        self.fail('Supervisor did not release its queue')

    def test_cli_ticket_survives_caller_exit_and_preserves_historical_result(self):
        doc=self.document();ticket=self.start(doc);self.assertLess(len(json.dumps(ticket).encode()),8192)
        self.assertNotIn('items',ticket['document']);self.assertEqual(ticket['request_id'],'one')
        completed=self.finish();data=(self.root/'one.png').read_bytes()
        self.assertEqual(png_pixels(data)[:3],(2,2,bytes(16)))
        result=self.cli('job.result',request_id='one');self.assertEqual(result['sha256'],hashlib.sha256(data).hexdigest())
        self.assertEqual(completed['output']['bytes'],len(data));self.assertEqual(result['revision'],0)
        self.idle();(self.root/'one.png').unlink()
        replay=self.start(doc,control=dict(timeout_ms=0));self.assertTrue(replay['replayed']);self.assertEqual(replay['state'],'completed')
        self.assertEqual(self.cli('job.resume',request_id='one',control=dict(timeout_ms=0))['state'],'completed')
        self.assertEqual(self.cli('job.result',request_id='one'),result);self.assertFalse((self.root/'one.png').exists())
        self.start(dict(doc,width=3),error='REQUEST_ID_REUSED')

    def test_saved_revision_and_asset_bytes_are_pinned_before_background_execution(self):
        pixels=bytes([20,100,220,255]*4);source=png(2,2,pixels);(self.root/'original.png').write_bytes(source)
        asset=self.cli('asset.import',source_path='original.png')['asset']
        doc=self.document();doc['assets']={'picture':asset};doc['items']=[dict(id='picture',content=dict(type='image',asset_id='picture',width=2,height=2))]
        self.save(doc)
        with self.blocked_queue():
            ticket=self.start(dict(session_id='work',revision=0));self.assertTrue(ticket['recovery_required'])
            self.cli('session.apply',session_id='work',request_id='edit',expected_revision=0,action=dict(type='edit',operations=[dict(op='properties',id='picture',opacity=.25)]))
        self.cli('job.resume',request_id='one');self.finish()
        self.assertEqual(png_pixels((self.root/'one.png').read_bytes())[:3],(2,2,pixels))
        self.assertEqual(self.cli('job.result',request_id='one')['revision'],0)
        self.assertEqual((self.root/'original.png').read_bytes(),source)
        self.assertEqual(self.cli('session.read',session_id='work')['document']['revision'],1)

    def test_changed_asset_and_retained_license_fail_and_require_explicit_resume(self):
        (self.root/'image.png').write_bytes(png(2,2,bytes([20,90,160,255]*4)))
        asset=self.cli('asset.import',source_path='image.png')['asset']
        (self.root/'face.ttf').write_bytes(geometric_font());(self.root/'license.txt').write_text('Original synthetic font fixture permission.')
        font=self.cli('font.import',source_path='face.ttf',license_path='license.txt')
        for rid,field,resource,folder,suffix,expected in [('asset','assets',asset,'assets','rgba8','ASSET_CORRUPT'),('font','fonts',font,'fonts','license','FONT_CORRUPT')]:
            doc=self.document();doc[field]={'unused':resource}
            sha=resource['license_sha256'] if suffix=='license' else resource['sha256']
            path=self.root/'.inkbolt'/folder/(sha+'.'+suffix);original=path.read_bytes()
            with self.blocked_queue():
                self.start(doc,rid=rid);path.write_bytes(b'x'*len(original))
            self.cli('job.resume',request_id=rid);failed=self.finish(rid,'failed');self.assertEqual(failed['error']['code'],expected)
            self.assertFalse((self.root/(rid+'.png')).exists());self.idle()
            path.write_bytes(original);self.cli('job.resume',request_id=rid);self.finish(rid);self.idle()

    def test_executable_mutation_stalls_the_pinned_queue_until_original_build_returns(self):
        engine=self.root/'worker.exe';shutil.copyfile(EXE,engine)
        with self.blocked_queue(): self.start(options=dict(worker_executable=str(engine)))
        with engine.open('ab') as file:file.write(b'original identity-mutation fixture')
        attempted=self.cli('job.resume',request_id='one');self.assertEqual(attempted['launch_error']['code'],'JOB_EXECUTABLE_CHANGED')
        self.assertTrue(attempted['recovery_required']);self.assertFalse((self.root/'one.png').exists())
        shutil.copyfile(EXE,engine);self.cli('job.resume',request_id='one');self.finish();self.idle()

    def test_cancelled_queue_and_observation_timeout_do_not_publish_or_restart(self):
        with self.blocked_queue():
            self.start();self.cli('job.wait',request_id='one',wait_ms=30001,error='INVALID_REQUEST')
            self.cli('job.wait',request_id='one',wait_ms=1000,control=dict(timeout_ms=0),error='TIMEOUT')
            self.assertFalse(self.cli('job.status',request_id='one')['cancel_requested'])
            self.assertEqual(self.cli('job.cancel',request_id='one')['state'],'cancelled')
        self.assertEqual(self.cli('job.resume',request_id='one')['state'],'cancelled');self.assertFalse((self.root/'one.png').exists())
        self.cli('job.result',request_id='one',error='JOB_NOT_COMPLETED')

    def test_concurrent_identical_submissions_produce_one_attempt_and_output(self):
        doc=self.document()
        with ThreadPoolExecutor(max_workers=4) as pool:
            tickets=list(pool.map(lambda _:self.start(doc),range(4)))
        self.assertTrue(any(not r['replayed'] for r in tickets));self.finish();self.idle()
        with closing(sqlite3.connect(self.ledger())) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],1)
            state=json.loads(db.execute('SELECT state FROM jobs').fetchone()[0]);self.assertEqual(state['attempt'],1)
        self.assertEqual(len(list(self.root.glob('one.png'))),1)

    def test_mcp_eof_leaves_background_work_and_cli_result_matches(self):
        doc=self.document()
        with closing(Client(('--tools','core'),workspace=self.root)) as client:
            client.initialize()
            reply=client.tool('run',command='job.start',arguments=dict(request_id='one',document=doc,output=dict(file_name='one.png',format='png')))
            self.assertFalse(reply['isError']);self.assertEqual(reply['structuredContent']['result']['request_id'],'one')
        self.finish()
        expected=self.cli('job.result',request_id='one')
        with closing(Client(('--tools','core'),workspace=self.root)) as client:
            client.initialize();actual=client.tool('run',command='job.result',arguments=dict(request_id='one'))['structuredContent']['result']
        self.assertEqual(actual,expected)

    def test_background_formats_keep_exact_synchronous_bytes_and_loss_receipts(self):
        doc=self.document();doc['items']=[dict(id='square',content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=2,height=2),fill=[20,80,180,255]))]
        for format,extension in [('snapshot','json'),('svg','svg'),('pdf','pdf'),('jpeg','jpg'),('tiff','tif')]:
            options=dict(format=format,file_name='job.'+extension)
            if format=='jpeg':options['image_options']=dict(matte=[255,255,255])
            self.cli('job.start',request_id=format,document=doc,output=options);self.finish(format)
            result=self.cli('job.result',request_id=format)
            direct=self.cli('document.publish',document=doc,output=dict(options,file_name='direct.'+extension))
            self.assertEqual((self.root/('job.'+extension)).read_bytes(),(self.root/('direct.'+extension)).read_bytes())
            self.assertEqual(result['sha256'],direct['sha256']);self.assertEqual(result['losses'],direct['losses'])

    def test_unknown_database_corrupt_state_workspace_and_existing_output_are_preserved(self):
        self.start();self.finish();self.idle()
        original=(self.root/'one.png').read_bytes()
        self.start(rid='existing',name='one.png');failed=self.finish('existing','failed')
        self.assertEqual(failed['error']['code'],'OUTPUT_EXISTS');self.assertEqual((self.root/'one.png').read_bytes(),original);self.idle()
        with closing(sqlite3.connect(self.ledger())) as db:db.execute('UPDATE jobs SET state_sha256=?',('0'*64,));db.commit()
        self.cli('job.status',request_id='one',error='JOB_CORRUPT')
        with closing(sqlite3.connect(self.ledger())) as db:db.execute('PRAGMA user_version=99');db.commit()
        before=self.ledger().read_bytes();self.cli('job.resume',request_id='one',error='JOB_FORMAT');self.assertEqual(self.ledger().read_bytes(),before)
        self.cli('job.status',job_root=str(self.root.parent),request_id='one',error='PATH_OUTSIDE_WORKSPACE')
        self.cli('job.start',job_root=str(self.root/'fresh-jobs'),request_id='never',document=self.document(),output=dict(file_name='never.png',format='png'),control=dict(timeout_ms=0),error='TIMEOUT')
        self.assertFalse((self.root/'never.png').exists())

    def test_list_missing_queue_defaults_schemas_and_cancellation_do_not_create_work(self):
        empty=self.cli('job.list')
        self.assertFalse(empty['exists']);self.assertEqual(empty['records'],[])
        self.assertEqual(empty['snapshot_total'],0);self.assertIsNone(empty['next_cursor'])
        self.assertFalse((self.root/'.inkbolt').exists())
        with closing(Client(('--tools','core'),workspace=self.root)) as client:
            client.initialize()
            reply=client.tool('run',command='job.list',arguments={})
            self.assertFalse(reply['isError']);self.assertEqual(reply['structuredContent']['result'],empty)
        for limit in [0,33]:self.cli('job.list',options=dict(limit=limit),error='INVALID_REQUEST')
        for cursor in ['not-a-cursor','a'*1025]:self.cli('job.list',options=dict(cursor=cursor),error='INVALID_CURSOR')
        self.cli('job.list',control=dict(timeout_ms=0),error='TIMEOUT')
        self.cli('job.list',job_root=str(self.root.parent),error='PATH_OUTSIDE_WORKSPACE')
        self.assertFalse((self.root/'.inkbolt').exists())
        found=self.cli('schema.lookup',name='job.list')
        self.assertEqual(found['detail'],'full')
        self.assertIn('job.list',self.cli('capabilities')['jobs']['commands'])

    def test_list_pages_preserve_admission_membership_while_progress_and_queue_change(self):
        ids=['zeta','alpha','middle','last','front']
        with self.blocked_queue():
            for rid in ids:self.start(rid=rid)
            before=self.ledger().read_bytes()
            first=self.cli('job.list',options=dict(limit=2))
            self.assertEqual(self.ledger().read_bytes(),before)
            self.assertEqual([r['request_id'] for r in first['records']],ids[:2])
            self.assertEqual(first['snapshot_total'],5);self.assertEqual(first['current_total'],5)
            self.start(rid='new-arrival');self.cli('job.cancel',request_id='middle')
            cursor=first['next_cursor'];rows=first['records'];pages=[]
            while cursor:
                before=self.ledger().read_bytes()
                page=self.cli('job.list',options=dict(limit=2,cursor=cursor));pages.append(page)
                self.assertEqual(self.ledger().read_bytes(),before)
                self.assertEqual(page['snapshot_total'],5);self.assertEqual(page['current_total'],6)
                rows.extend(page['records']);cursor=page['next_cursor']
            self.assertEqual([r['request_id'] for r in rows],ids)
            self.assertEqual(rows[2]['state'],'cancelled')
            self.assertEqual([p['offset'] for p in pages],[2,4])
            fresh=self.cli('job.list');self.assertEqual(fresh['snapshot_total'],6)
            self.assertEqual(fresh['records'][-1]['request_id'],'new-arrival')
            self.assertLess(len(json.dumps(fresh).encode()),8192)
            self.assertTrue(all('items' not in row['document'] for row in rows))
            self.assertFalse(any(self.root.glob('*.png')))
            with closing(Client(('--tools','core'),workspace=self.root)) as client:
                client.initialize();reply=client.tool('run',command='job.list',arguments={})
                self.assertEqual(reply['structuredContent']['result'],fresh)

    def test_list_cursor_rejects_other_roots_limit_changes_mutated_inputs_and_missing_store(self):
        with self.blocked_queue():
            for rid in ['one','two','three']:self.start(rid=rid)
            cursor=self.cli('job.list',options=dict(limit=1))['next_cursor']
            self.cli('job.list',options=dict(limit=2,cursor=cursor),error='INVALID_CURSOR')
            other=self.root/'other-queue';other.mkdir();shutil.copyfile(self.ledger(),other/'jobs.sqlite3')
            self.cli('job.list',job_root=str(other),options=dict(limit=1,cursor=cursor),error='JOB_CURSOR_CHANGED')
            with closing(sqlite3.connect(self.ledger())) as db:
                data=json.loads(db.execute('SELECT payload FROM inputs WHERE id=?',('two',)).fetchone()[0])
                data['document']['revision']+=1
                payload=json.dumps(data,separators=(',',':')).encode()
                db.execute('UPDATE inputs SET payload=?,sha256=? WHERE id=?',(payload,hashlib.sha256(payload).hexdigest(),'two'));db.commit()
            self.cli('job.list',options=dict(limit=1,cursor=cursor),error='JOB_CURSOR_CHANGED')
            changed=self.cli('job.list');self.assertEqual(changed['records'][1]['document']['revision'],1)
            cursor=self.cli('job.list',options=dict(limit=1))['next_cursor']
            saved=self.ledger().with_suffix('.saved');self.ledger().rename(saved)
            self.cli('job.list',options=dict(limit=1,cursor=cursor),error='JOB_CURSOR_CHANGED')
            self.assertFalse(self.ledger().exists());self.assertTrue(saved.exists())

    def test_list_completed_work_without_reopening_missing_resources_build_or_output(self):
        (self.root/'image.png').write_bytes(png(2,2,bytes([10,20,30,255]*4)))
        asset=self.cli('asset.import',source_path='image.png')['asset']
        doc=self.document();doc['assets']={'unused':asset}
        engine=self.root/'worker.exe';shutil.copyfile(EXE,engine)
        self.start(doc,options=dict(worker_executable=str(engine)));self.finish();self.idle()
        (self.root/'.inkbolt/assets'/(asset['sha256']+'.rgba8')).unlink()
        (self.root/'image.png').unlink();(self.root/'one.png').unlink();engine.unlink()
        page=self.cli('job.list');row=page['records'][0]
        self.assertEqual(row['request_id'],'one');self.assertEqual(row['state'],'completed')
        self.assertEqual(row['next_action'],'job.result');self.assertEqual(row['format'],'png')
        self.assertEqual(row['document'],dict(id=doc['id'],revision=doc['revision']))
        self.assertFalse((self.root/'one.png').exists())

    def test_list_byte_budget_shortens_pages_without_skipping_long_destinations(self):
        root=self.root
        for i in range(21):root=root/(str(i)+'x'*165)
        ids=[f'long-{i}' for i in range(12)]
        with self.blocked_queue():
            for rid in ids:self.cli('job.start',request_id=rid,document=self.document(),output=dict(output_root=str(root),file_name=rid+'.png',format='png'))
            options=dict(limit=32);seen=[];pages=0
            while True:
                page=self.cli('job.list',options=options);pages+=1
                self.assertLessEqual(len(json.dumps(page,separators=(',',':')).encode()),32768)
                self.assertGreater(page['returned'],0)
                seen.extend(r['request_id'] for r in page['records'])
                if not page['next_cursor']:break
                options['cursor']=page['next_cursor']
            self.assertGreater(pages,1);self.assertEqual(seen,ids)
            self.assertFalse(root.exists())

    def test_list_rejects_corrupt_rows_and_orphaned_inputs_without_partial_results(self):
        with self.blocked_queue():
            for rid in ['one','two']:self.start(rid=rid)
            with closing(sqlite3.connect(self.ledger())) as db:
                db.execute('UPDATE jobs SET state_sha256=? WHERE id=?',('0'*64,'two'));db.commit()
            before=self.ledger().read_bytes()
            self.cli('job.list',error='JOB_CORRUPT');self.assertEqual(self.ledger().read_bytes(),before)
            with closing(sqlite3.connect(self.ledger())) as db:
                db.execute('DELETE FROM jobs WHERE id=?',('two',));db.commit()
            before=self.ledger().read_bytes()
            self.cli('job.list',error='JOB_CORRUPT');self.assertEqual(self.ledger().read_bytes(),before)

    def test_list_page_uses_one_snapshot_during_concurrent_progress_commits(self):
        with self.blocked_queue():
            for rid in ['one','two','three','four']:self.start(rid=rid)
            ready=Event();stop=Event();commits=[]
            def writer():
                with closing(sqlite3.connect(self.ledger(),timeout=3)) as db:
                    states=[json.loads(row[0]) for row in db.execute('SELECT state FROM jobs')]
                    generation=0
                    while not stop.is_set():
                        generation+=1;db.execute('BEGIN IMMEDIATE')
                        for state in states:
                            state['progress']['completed']=generation
                            payload=json.dumps(state,separators=(',',':')).encode()
                            db.execute('UPDATE jobs SET state=?,state_sha256=? WHERE id=?',(payload,hashlib.sha256(payload).hexdigest(),state['id']))
                        db.commit();commits.append(generation);ready.set();time.sleep(.003)
            observed=[]
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(writer)
                try:
                    self.assertTrue(ready.wait(5))
                    for _ in range(10):
                        page=self.cli('job.list');self.assertEqual(page['returned'],4)
                        values={row['progress']['completed'] for row in page['records']}
                        self.assertEqual(len(values),1,page);observed.extend(values)
                finally:stop.set();future.result(timeout=5)
            self.assertGreater(len(commits),1);self.assertGreater(len(set(observed)),1)


if __name__=='__main__':unittest.main()
