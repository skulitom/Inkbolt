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


if __name__=='__main__':unittest.main()
