"""Explicit local consumer tools, retained traffic and Windows tree accounting."""
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import subprocess
import time

from benchmark_runtime import MAX_RESPONSE, require, safe_name, strict_json
from workload_cases import run_process, save, save_json, sha
from verify_process import WindowsJob


class BasicLimits(ctypes.Structure):
    _fields_ = [('process_time',ctypes.c_int64),('job_time',ctypes.c_int64),
        ('flags',w.DWORD),('minimum',ctypes.c_size_t),('maximum',ctypes.c_size_t),
        ('active',w.DWORD),('affinity',ctypes.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]


class ExtendedLimits(ctypes.Structure):
    # Documented JOBOBJECT_EXTENDED_LIMIT_INFORMATION. The OS tracks these
    # commit peaks continuously, including short-lived encoder/probe children.
    _fields_ = [('basic',BasicLimits),('io',ctypes.c_uint64*6),
        ('process_limit',ctypes.c_size_t),('job_limit',ctypes.c_size_t),
        ('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]


class Accounting(ctypes.Structure):
    _fields_ = [(n,ctypes.c_int64) for n in ('user','kernel','period_user','period_kernel')]+[
        (n,w.DWORD) for n in ('faults','total','active','terminated')]


def tool_identities(tools):
    require(set(tools)=={'cutbolt','ffmpeg','ffprobe'},
            'B20 requires explicit --cutbolt, --ffmpeg and --ffprobe local executable paths')
    result={}
    for name,value in tools.items():
        path=Path(value)
        require(path.is_absolute() and path.is_file(), 'Consumer executable must be an existing absolute file: '+name)
        result[name]=dict(path=str(path.resolve()),sha256=sha(path.read_bytes()))
    return result


def tree_command(argv, payload, environment, timeout):
    """The JSON caller waits for input until its entire future tree is contained.

    This is an aggregate job commit peak, not an RSS sample or a sum of
    individual high-water marks. No breakaway flags are enabled. Oracles run
    separately; their memory is never presented as consumer-engine memory.
    """
    require(os.name=='nt', 'B20 consumer process accounting requires Windows')
    job=WindowsJob();process=None;started=time.perf_counter()
    stdout=stderr=b'';metrics=dict(timed_out=False,memory_available=False)
    try:
        process=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            env=environment,creationflags=subprocess.DETACHED_PROCESS)
        job.assign(process)
        try:stdout,stderr=process.communicate(payload,timeout=timeout)
        except subprocess.TimeoutExpired:
            metrics['timed_out']=True
            job.close();stdout,stderr=process.communicate(timeout=5)
        metrics['exit_code']=process.returncode
        if job.handle:
            counts=Accounting();limits=ExtendedLimits();deadline=time.monotonic()+3
            while True:
                require(job.api.QueryInformationJobObject(job.handle,1,ctypes.byref(counts),ctypes.sizeof(counts),None),
                        'Cannot read consumer process-tree accounting')
                if counts.active==0 or time.monotonic()>=deadline:break
                time.sleep(.005)
            require(job.api.QueryInformationJobObject(job.handle,9,ctypes.byref(limits),ctypes.sizeof(limits),None),
                    'Cannot read consumer process-tree memory peaks')
            metrics.update(processes=counts.total,active_processes=counts.active,
                peak_tree_commit_bytes=limits.peak_job,peak_process_commit_bytes=limits.peak_process,
                memory_available=counts.active==0 and counts.total>=1 and limits.peak_job>0 and limits.peak_process>0)
    except Exception as error:
        # Preserve any completed response even if OS accounting failed. Missing
        # accounting is a failed trial, never an assumed zero-memory observation.
        metrics.update(memory_available=False,observation_error=f'{type(error).__name__}: {error}')
    finally:
        job.close()
        if process:
            if process.poll() is None:process.kill()  # Also covers failure before job assignment.
            process.wait(timeout=5)
            for pipe in (process.stdin,process.stdout,process.stderr):
                if pipe is not None:pipe.close()
            process._handle.Close()
            metrics.setdefault('exit_code',process.returncode)
    metrics['seconds']=time.perf_counter()-started
    return metrics,stdout,stderr


class Consumer:
    COMMANDS={'scene.inspect','scene.render','session.create','session.get','session.preview',
              'session.apply','session.undo','session.check','render.run'}

    def __init__(self, root, tools, timeout=90):
        self.identities=tool_identities(tools)
        self.root=Path(root);self.root.mkdir()
        self.judge_root=self.root/'judge';self.judge_root.mkdir()
        self.timeout=timeout;self.calls=[];self.judges=[];self.names=set()
        self.environment=os.environ.copy()
        self.environment.update(CUTBOLT_FFMPEG=self.identities['ffmpeg']['path'],
            CUTBOLT_FFPROBE=self.identities['ffprobe']['path'],
            CUTBOLT_INSPECTION_CACHE=str(self.root/'inspection-cache'))
        save_json(self.root/'tools.json',self.identities)

    def call(self, step, command, expected_error=None, retry_of=None, **fields):
        require(command in self.COMMANDS, 'Consumer command is outside the bounded synchronous workflow')
        safe_name(step);require(step not in self.names,'Duplicate consumer step');self.names.add(step)
        payload=json.dumps(dict(command=command,**fields),separators=(',',':')).encode()
        fingerprint=sha(payload)
        if retry_of is not None:
            previous=[r for r in self.calls if r['step']==retry_of]
            require(len(previous)==1 and previous[0]['request_sha256']==fingerprint,'Consumer retry changed its request')
        prefix=self.root/f'{len(self.calls)+1:03d}-{step}'
        save(prefix.with_suffix('.request.json'),payload)
        row=dict(step=step,command=command,request_sha256=fingerprint,request_bytes=len(payload),
                 response_bytes=0,retry_of=retry_of,expected_error=expected_error,status='failure')
        self.calls.append(row)
        try:
            metrics,stdout,stderr=tree_command([self.identities['cutbolt']['path']],payload,self.environment,self.timeout)
            save(prefix.with_suffix('.response.json'),stdout);save(prefix.with_suffix('.stderr.txt'),stderr)
            row.update(metrics,response_bytes=len(stdout))
            require(not metrics['timed_out'] and not stderr, 'Consumer timeout or unexpected stderr')
            require(metrics['memory_available'], 'Consumer process-tree observation is incomplete: '+str(metrics.get('observation_error')))
            require(len(stdout)<=MAX_RESPONSE,'Consumer response exceeds bound')
            envelope=strict_json(stdout)
            require(type(envelope.get('ok')) is bool and metrics['exit_code']==int(not envelope['ok']),
                    'Consumer exit/envelope mismatch')
            if expected_error:
                require(not envelope['ok'] and envelope.get('error',{}).get('code')==expected_error,
                        'Expected consumer diagnostic did not occur')
                row['status']='expected_error';return envelope['error']
            require(envelope['ok'],'Consumer command failed: '+str(envelope.get('error')))
            require(isinstance(envelope.get('result'),dict),'Missing consumer result')
            row['status']='success';return envelope['result']
        except Exception as error:
            row['error']=f'{type(error).__name__}: {error}';raise

    def judge(self, step, tool, arguments):
        safe_name(step);require(tool in ('ffmpeg','ffprobe'),'Unexpected independent decoder')
        argv=[self.identities[tool]['path'],*arguments]
        prefix=self.judge_root/step
        save_json(prefix.with_suffix('.argv.json'),argv)
        metrics,stdout,stderr=run_process(argv,b'',self.timeout)
        save(prefix.with_suffix('.stdout'),stdout);save(prefix.with_suffix('.stderr'),stderr)
        self.judges.append(dict(step=step,tool=tool,**metrics))
        require(not metrics['timed_out'] and metrics['exit_code']==0 and not stderr,'Independent decoder failed')
        return stdout

    def unchanged(self):
        return self.identities==tool_identities({k:v['path'] for k,v in self.identities.items()})

    def result(self):
        complete=bool(self.calls) and all(r.get('memory_available') for r in self.calls)
        return dict(tools=self.identities,commands=len(self.calls),calls=self.calls,judges=self.judges,
            request_bytes=sum(r['request_bytes'] for r in self.calls),
            response_bytes=sum(r['response_bytes'] for r in self.calls),
            roundtrip_seconds=sum(r.get('seconds',0) for r in self.calls),
            retries=sum(r['retry_of'] is not None for r in self.calls),memory_complete=complete,
            peak_tree_commit_bytes=max(r['peak_tree_commit_bytes'] for r in self.calls) if complete else None,
            scope='Cutbolt CLI plus all inherited encoder/probe processes, OS job commit peak per call; independent decoder/judge excluded')
