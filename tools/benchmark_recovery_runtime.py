"""Owned Windows process trees and retained fault evidence for the B19 adapter."""
from contextlib import closing, contextmanager
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import threading
import time
from types import SimpleNamespace

from benchmark_runtime import Trial, require
from measure_workloads import process_memory, save_json, sha
from verify_process import WindowsJob


class Accounting(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int64) for name in ('user', 'kernel', 'period_user', 'period_kernel')] + [
        (name, w.DWORD) for name in ('faults', 'total', 'active', 'terminated')]


class RecoveryTrial(Trial):
    """Commands wait on stdin until assigned; descendants inherit the owned job.

    The observer reads only this new fixture's ledger. Before retaining a worker
    handle it verifies creation time, executable path and membership in our job.
    No process-name search, database mutation or engine test hook is used.
    """
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.container = None
        self.closed = False
        self.observer = None
        self.stop = threading.Event()
        self.lock = threading.RLock()
        self.workers = {}
        self.frontends = set()
        self.events = []
        self.observer_error = None
        self.accounting = None
        self.outputs = ()
        self.ledger = self.root/'.inkbolt/jobs/jobs.sqlite3'

    def begin(self, prompt):
        require(os.name == 'nt', 'The recovery benchmark currently requires verified Windows containment')
        self.container = WindowsJob()
        self.api = self.container.api
        signatures = {
            'OpenProcess': ([w.DWORD,w.BOOL,w.DWORD],w.HANDLE),
            'GetProcessTimes': ([w.HANDLE,*([ctypes.POINTER(w.FILETIME)]*4)],w.BOOL),
            'QueryFullProcessImageNameW': ([w.HANDLE,w.DWORD,w.LPWSTR,ctypes.POINTER(w.DWORD)],w.BOOL),
            'IsProcessInJob': ([w.HANDLE,w.HANDLE,ctypes.POINTER(w.BOOL)],w.BOOL),
            'WaitForSingleObject': ([w.HANDLE,w.DWORD],w.DWORD),
            'TerminateProcess': ([w.HANDLE,w.UINT],w.BOOL),
            'GetSystemDirectoryW': ([w.LPWSTR,w.UINT],w.UINT),
        }
        for name,(args,result) in signatures.items():
            function=getattr(self.api,name);function.argtypes=args;function.restype=result
        directory=ctypes.create_unicode_buffer(32768)
        length=self.api.GetSystemDirectoryW(directory,len(directory))
        require(0<length<len(directory), 'Cannot resolve the Windows system directory')
        self.console_path=os.path.normcase(str(Path(directory.value)/'conhost.exe'))
        self.observer=threading.Thread(target=self.observe,daemon=True)
        self.observer.start()
        super().begin(prompt)

    def spawn(self, argv, **options):
        # Detached standard streams still use the explicit pipes. Unlike an
        # invisible console, this needs no short-lived console-host process.
        options['creationflags']=subprocess.DETACHED_PROCESS
        process=super().spawn(argv,**options)
        try:
            # CLI and MCP cannot start work until their first input request.
            with self.lock:
                self.frontends.add(process.pid)
                self.container.assign(process)
        except BaseException:
            process.kill();process.wait(timeout=5)
            for pipe in (process.stdin,process.stdout,process.stderr):
                if pipe is not None:pipe.close()
            raise
        return process

    def execute(self, argv, payload):
        started=time.perf_counter()
        with self.spawn(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        creationflags=subprocess.CREATE_NO_WINDOW) as process:
            timed_out=False
            try:stdout,stderr=process.communicate(payload,timeout=self.timeout)
            except subprocess.TimeoutExpired:
                timed_out=True
                process.kill();stdout,stderr=process.communicate(timeout=10)
            result=dict(exit_code=process.returncode,seconds=time.perf_counter()-started,
                        timed_out=timed_out,memory=process_memory(process))
            with self.lock:self.frontends.discard(process.pid)
            return result,stdout,stderr

    def validate_command(self, command):
        require(self.container is not None and not self.closed, 'Recovery containment is not active')
        require(self.observer_error is None, 'Recovery observer failed: '+str(self.observer_error))

    def event(self, kind, **fields):
        with self.lock:
            self.events.append(dict(kind=kind,seconds=time.perf_counter()-self.started,**fields))

    def snapshot(self):
        if not self.ledger.exists():return None
        with closing(sqlite3.connect(self.ledger.as_uri()+'?mode=ro',uri=True,timeout=.025)) as db:
            # One read transaction keeps identities, states and checksums coherent.
            db.execute('BEGIN')
            runtime=db.execute('SELECT payload,sha256 FROM runtime').fetchone()
            rows=db.execute('SELECT id,state,state_sha256 FROM jobs ORDER BY id').fetchall()
        require(runtime is not None and sha(runtime[0])==runtime[1], 'Runtime checksum differs')
        require(all(sha(raw)==digest for _,raw,digest in rows), 'Job state checksum differs')
        return dict(runtime=json.loads(runtime[0]),jobs={key:json.loads(raw) for key,raw,_ in rows})

    def capture(self, identity, role):
        if identity is None:return
        key=(identity['pid'],identity['created'])
        with self.lock:
            if key in self.workers:
                if role in ('runner','supervisor'):self.workers[key]['role']=role
                return
            handle=self.api.OpenProcess(0x100000|0x1000|0x10|1,False,key[0])
            require(bool(handle), 'Could not retain a recorded worker process handle')
            try:
                times=[w.FILETIME() for _ in range(4)]
                require(self.api.GetProcessTimes(handle,*(ctypes.byref(v) for v in times)), 'Cannot verify process creation')
                require((times[0].dwHighDateTime<<32)|times[0].dwLowDateTime==key[1], 'Recorded PID was reused')
                size=w.DWORD(32768);path=ctypes.create_unicode_buffer(size.value)
                require(self.api.QueryFullProcessImageNameW(handle,0,path,ctypes.byref(size)), 'Cannot verify worker executable')
                expected=self.console_path if role=='console-host' else os.path.normcase(str(self.executable.resolve()))
                require(os.path.normcase(path.value)==expected, 'Worker executable differs')
                member=w.BOOL()
                require(self.api.IsProcessInJob(handle,self.container.handle,ctypes.byref(member)) and member.value,
                        'Worker is outside the owned process tree')
                self.workers[key]=dict(identity=identity,role=role,handle=handle,executable=path.value)
                self.event('process-retained',identity=identity,role=role,executable=path.value)
            except BaseException:
                self.api.CloseHandle(handle)
                raise

    def capture_members(self):
        # Query only our job, never the system process list. Console hosts are
        # included in the lifetime count and measurements under their own role.
        entries=(ctypes.c_size_t*258)()
        with self.lock:
            require(self.api.QueryInformationJobObject(self.container.handle,3,ctypes.byref(entries),ctypes.sizeof(entries),None),
                    'Cannot enumerate the bounded owned process tree')
            header=ctypes.cast(entries,ctypes.POINTER(w.DWORD))
            require(header[0]==header[1] and header[1]<=256, 'Owned process inventory exceeds its bound')
            pids=ctypes.cast(ctypes.byref(entries,8),ctypes.POINTER(ctypes.c_size_t))
            known=self.frontends|{key[0] for key in self.workers}
            for index in range(header[1]):
                pid=pids[index]
                if pid in known:continue
                handle=self.api.OpenProcess(0x1000,False,pid)
                require(bool(handle), 'Owned process exited before identity capture')
                try:
                    times=[w.FILETIME() for _ in range(4)]
                    require(self.api.GetProcessTimes(handle,*(ctypes.byref(v) for v in times)), 'Cannot read owned process identity')
                    size=w.DWORD(32768);path=ctypes.create_unicode_buffer(size.value)
                    require(self.api.QueryFullProcessImageNameW(handle,0,path,ctypes.byref(size)), 'Cannot read owned process image')
                    identity=dict(pid=pid,created=(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime)
                    role='console-host' if os.path.normcase(path.value)==self.console_path else 'engine-worker'
                    self.capture(identity,role)
                finally:self.api.CloseHandle(handle)

    def observe(self):
        previous=None
        output_states={}
        try:
            while not self.stop.is_set():
                self.capture_members()
                try:current=self.snapshot()
                except sqlite3.OperationalError as error:
                    # Only short SQLite writer/startup races are retried. A
                    # missing final snapshot/count can never become a pass.
                    if not any(v in str(error) for v in ('locked','no such table')):raise
                    self.stop.wait(.005);continue
                if current is not None:
                    self.capture(current['runtime']['owner'],'supervisor')
                    for state in current['jobs'].values():
                        self.capture(state['worker'],'supervisor')
                        self.capture(state['runner'],'runner')
                    if current!=previous:self.event('ledger',snapshot=current)
                for name in self.outputs:
                    path=self.root/name
                    if path.exists():
                        stat=path.stat();identity=(stat.st_ino,stat.st_size,stat.st_mtime_ns)
                        if output_states.get(name)!=identity:
                            raw=path.read_bytes()
                            self.event('output-observed',name=name,identity=identity,bytes=len(raw),sha256=sha(raw))
                            output_states[name]=identity
                previous=current
                self.stop.wait(.005)
        except Exception as error:
            self.observer_error=f'{type(error).__name__}: {error}'
            self.event('observer-failed',error=self.observer_error)

    @contextmanager
    def blocked_queue(self):
        import msvcrt
        self.ledger.parent.mkdir(parents=True,exist_ok=True)
        with (self.ledger.parent/'worker.lock').open('a+b') as lease:
            lease.seek(0);msvcrt.locking(lease.fileno(),msvcrt.LK_NBLCK,1)
            try:yield
            finally:lease.seek(0);msvcrt.locking(lease.fileno(),msvcrt.LK_UNLCK,1)

    def rendering(self, request_id):
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            require(self.observer_error is None, 'Recovery observer failed: '+str(self.observer_error))
            with self.lock:
                snapshots=[e['snapshot'] for e in self.events if e['kind']=='ledger']
                current=snapshots[-1] if snapshots else None
                state=current['jobs'].get(request_id) if current else None
                if state and state['phase']=='running' and state['progress']['phase']=='rendering_and_encoding':
                    for role in ('worker','runner'):
                        identity=state[role]
                        require(identity is not None, 'Rendering lacks a process identity')
                        worker=self.workers[(identity['pid'],identity['created'])]
                        require(self.api.WaitForSingleObject(worker['handle'],0)==258, 'Rendering process already exited')
                    self.event('fault-boundary',request_id=request_id,state=state)
                    return state
                require(not state or state['phase'] in ('queued','running'), 'Output finished before the required fault boundary')
            time.sleep(.005)
        raise RuntimeError('No active rendering boundary within 20 seconds')

    @contextmanager
    def launch_boundary(self, step, command, request_id, **arguments):
        # A one-shot caller's pipe teardown can outlive its response and worker
        # startup. Let an independent CLI control caller act during that time.
        # MCP stays serial on its persistent connection. Every call is retained.
        errors=[]
        def launch():
            try:self.call(step,command,request_id=request_id,**arguments)
            except Exception as error:errors.append(error)
        pending=None
        if self.transport=='cli':
            pending=threading.Thread(target=launch,daemon=True);pending.start()
        else:launch()
        try:
            if errors:raise errors[0]
            yield self.rendering(request_id)
        finally:
            if pending:
                pending.join(timeout=self.timeout+10)
                require(not pending.is_alive(), 'Background launch caller did not exit')
            if errors:raise errors[0]

    def interrupt_supervisor(self, state):
        identity=state['worker']
        with self.lock:
            worker=self.workers[(identity['pid'],identity['created'])]
            require(self.api.TerminateProcess(worker['handle'],19), 'Unable to interrupt the exact owned supervisor')
            self.event('supervisor-interrupted',identity=identity)
            for name in ('worker','runner'):
                item=state[name];handle=self.workers[(item['pid'],item['created'])]['handle']
                require(self.api.WaitForSingleObject(handle,5000)==0, 'Interrupted process tree did not exit')
            self.event('interrupted-tree-exited',worker=state['worker'],runner=state['runner'])

    def totals(self):
        counts=Accounting()
        require(self.api.QueryInformationJobObject(self.container.handle,1,ctypes.byref(counts),ctypes.sizeof(counts),None),
                'Cannot read owned process-tree counts')
        return dict(total=counts.total,active=counts.active)

    def close(self):
        if self.closed:return
        self.closed=True
        super().close()
        if self.container is None:return
        try:
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                self.accounting=self.totals()
                if self.accounting['active']==0:break
                time.sleep(.01)
            self.stop.set()
            if self.observer:self.observer.join(timeout=2)
            require(self.observer is None or not self.observer.is_alive(), 'Recovery observer did not stop')
            require(self.observer_error is None, 'Recovery observer failed: '+str(self.observer_error))
            require(self.accounting['active']==0, 'An owned engine process leaked after the recovery task')
            expected=(len(self.calls) if self.transport=='cli' else int(self.server is not None))+len(self.workers)
            require(self.accounting['total']==expected, 'Not every engine process has a lifetime memory observation')
        except Exception as error:
            self.error=self.error or f'{type(error).__name__}: {error}'
        finally:
            self.container.close()  # Kill-on-close also contains timeout/failure cleanup.
            self.stop.set()
            if self.observer:self.observer.join(timeout=2)
            for worker in self.workers.values():
                worker['memory']=process_memory(SimpleNamespace(_handle=worker['handle']))
                self.api.CloseHandle(worker.pop('handle'))
            save_json(self.root/'recovery-evidence.json',dict(events=self.events,
                processes=list(self.workers.values()),accounting=self.accounting,observer_error=self.observer_error))

    def memory_observations(self):
        memory,scope=super().memory_observations()
        memory += [row.get('memory') for row in self.workers.values()]
        if self.observer_error or not self.accounting or self.accounting['total']!=(
                len(self.calls) if self.transport=='cli' else int(self.server is not None))+len(self.workers):
            memory.append(dict(available=False,reason='Background process coverage is incomplete'))
        return memory,scope+' plus every supervisor, runner and owned console-host lifetime; maximum individual-process peak, not a concurrent sum'

    def extra_results(self):
        return dict(background_processes=[{k:v for k,v in row.items() if k!='handle'} for row in self.workers.values()],
                    process_tree=self.accounting,recovery_evidence='recovery-evidence.json')
