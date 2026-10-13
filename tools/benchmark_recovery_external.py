"""B19 external lifecycle hooks: measured engine broker and immutable captures."""
import copy
import base64
import math
import os
from pathlib import Path
import sys

from benchmark_recovery import fixture,PROMPT,PREVIEW_FILES,judge
from benchmark_recovery_runtime import RecoveryTrial
from benchmark_recovery_control import RecoveryControl
from benchmark_runtime import Trial,require,safe_name,strict_json
from workload_cases import save_json,sha
from verify_process import run as run_owned

CONTROL_FILES=('benchmark_recovery_external.py','benchmark_recovery_control.py','benchmark_recovery_bridge.py','benchmark_recovery_runtime.py')
METRIC_FIELDS={'engine_commands','process_calls','protocol_requests','request_bytes','response_bytes','invalid_calls','retries',
    'expected_errors','replayed_receipts','engine_roundtrip_seconds','memory_complete','memory_scope','peak_commit_bytes','peak_working_set_bytes'}
ENGINE_SCOPE='individual solve CLI processes plus every supervisor, runner and owned console-host lifetime; maximum individual-process peak, not a concurrent sum'


def control_identity():
    return {name:sha(Path(__file__).with_name(name).read_bytes()) for name in CONTROL_FILES}


def external_trial(*args,**kwargs):
    # Delay importing the generic lifecycle to avoid a registry import cycle.
    from benchmark_driver import ExternalTrial
    class ControlledTrial(RecoveryTrial,ExternalTrial):
        def begin(self,prompt):Trial.begin(self,prompt)
        def begin_judging(self):
            if self.phase!='judge':Trial.begin_judging(self)
        def spawn(self,*args,**kwargs):
            return RecoveryTrial.spawn(self,*args,**kwargs) if self.container and not self.closed else Trial.spawn(self,*args,**kwargs)
        def execute(self,*args,**kwargs):
            return RecoveryTrial.execute(self,*args,**kwargs) if self.container and not self.closed else Trial.execute(self,*args,**kwargs)
        def validate_command(self,command):
            if self.phase=='judge':
                require(not command.startswith('job.') or command in ('job.status','job.result'),'Judging cannot launch, cancel or resume jobs')
            else:RecoveryTrial.validate_command(self,command)
        def calls_succeeded(self):
            # A measured, returned engine diagnostic can be repaired by the
            # external agent. Judge, protocol and containment failures cannot.
            return all(r['status'] in ('success','expected_error','response_lost') or
                (self.driver_evidence is not None and r['phase']=='task' and
                 r['status']=='failure' and isinstance(r.get('engine_error'),dict)) for r in self.calls)
        def extra_results(self):
            result=ExternalTrial.extra_results(self)
            control=(self.driver_evidence or {}).get('harness_recovery')
            result['harness_recovery']=control
            if control:
                result.update(control['metrics'])
                matched=[]
                for check,name in PREVIEW_FILES.items():
                    if any(c['name']==check and c['status']=='pass' for c in self.checks):
                        digest=sha((self.root/name).read_bytes())
                        matched += [p['seconds'] for p in control['previews'] if p['sha256']==digest]
                result['first_verified_preview_seconds']=min(matched) if matched else None
                result['preview_timing_source']='harness_observed'
                # Solve time includes the external agent's waits and bridge;
                # retain it as observed wall time, never inferred model time.
                result['scripted_wall_seconds']=None
            return result
    return ControlledTrial(*args,**kwargs)


def configure_request(case,request):
    require(os.name=='nt','B19 external recovery requires verified Windows containment; Unix jobs are unsupported')
    request.pop('engine_executable',None);request['mcp_config']=None
    request['recovery_bridge']=[sys.executable,str(Path(__file__).with_name('benchmark_recovery_bridge.py').resolve()),str((case.judge_root/'control-channel').resolve())]
    request['tool_policy']='Use only the supplied recovery bridge for Inkbolt commands and fault controls. Preserve workspace inputs. Do not inspect harness evidence, control-channel files or process IDs directly.'


def measured(case):
    calls=[r for r in case.calls if r['phase']!='judge']
    observations,scope=RecoveryTrial.memory_observations(case)
    complete=bool(observations) and all(m and m.get('available') for m in observations)
    return dict(engine_commands=len(calls),process_calls=len(calls),protocol_requests=0,
        request_bytes=sum(r['request_bytes'] for r in calls),response_bytes=sum(r['response_bytes'] for r in calls),
        invalid_calls=sum((r.get('engine_error') or {}).get('code') in ('INVALID_JSON','INVALID_REQUEST') for r in calls),
        retries=sum(r['retry_of'] is not None for r in calls),
        expected_errors=sum(r['status']=='expected_error' for r in calls),replayed_receipts=sum(r.get('replayed',False) for r in calls),
        engine_roundtrip_seconds=sum(r['seconds'] for r in calls),memory_complete=complete,memory_scope=scope,
        peak_commit_bytes=max(m['peak_commit_bytes'] for m in observations) if complete else None,
        peak_working_set_bytes=max(m['peak_working_set_bytes'] for m in observations) if complete else None)


def execute_client(case,configuration,request_path):
    case.timeout=min(30,configuration['timeout_seconds'])
    case.start_containment();broker=RecoveryControl(case,case.judge_root/'control-channel');broker.start()
    try:
        execution=run_owned(configuration['argv']+[str(request_path)],case.root,configuration['timeout_seconds'],observe_memory=True)
    finally:
        try:broker.close()
        finally:
            # Freeze intervention evidence before stopping the observer, then
            # drain/close every engine handle before taking a workspace capture.
            RecoveryTrial.begin_judging(case)
            case.close()
    require(case.error is None,'Recovery containment failed: '+str(case.error))
    require(broker.error is None,'Recovery controller failed: '+str(broker.error))
    require(broker.controls==['cancel-active','hold-queue','interrupt-queued'] and
        broker.checkpoints=={'after-inspection','before-replays','after-replays'},'Missing required recovery controls or observations')
    metrics=measured(case)
    require(metrics['memory_complete'],'Incomplete owned engine process observations')
    previews=[]
    for row in case.calls:
        if row['command']=='document.preview' and row['status']=='success':
            artifact=case.results[row['step']]['result']['artifact']
            previews.append(dict(sha256=sha(base64.b64decode(artifact['data'],validate=True)),seconds=row['completed_task_seconds'],step=row['step']))
    save_json(case.judge_root/'recovery-control.json',dict(schema_version=1,calls=case.calls,metrics=metrics,controls=broker.controls,previews=previews))
    names=['recovery-observations.json','recovery-evidence.json','recovery-control.json']
    names += [p.name for p in case.judge_root.iterdir() if p.name[:3].isdigit() and p.name.endswith(('.request.json','.response.json','.stderr.txt'))]
    files={name:sha((case.judge_root/name).read_bytes()) for name in sorted(names)}
    case.harness_recovery=dict(files=files,metrics=metrics,previews=previews)
    return execution


def validate_capture(evidence,value):
    require(isinstance(value,dict) and set(value)=={'files','metrics','previews'} and isinstance(value['files'],dict),'Missing recovery harness capture')
    files=value['files'];require({'recovery-observations.json','recovery-evidence.json','recovery-control.json'}<=set(files) and len(files)<=800,
        'Incomplete or oversized recovery evidence inventory')
    total=0
    for name,digest in files.items():
        safe_name(name);path=evidence/name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size<=16*1024*1024,'Missing, linked or oversized recovery evidence')
        total+=path.stat().st_size;require(total<=64*1024*1024 and sha(path.read_bytes())==digest,'Recovery evidence identity mismatch')
    proof=strict_json((evidence/'recovery-control.json').read_bytes());lifetime=strict_json((evidence/'recovery-evidence.json').read_bytes())
    require(set(proof)=={'schema_version','calls','metrics','controls','previews'} and proof['schema_version']==1 and proof['metrics']==value['metrics'] and
        proof['controls']==['cancel-active','hold-queue','interrupt-queued'],'Invalid recovery control record')
    calls=proof['calls'];metrics=proof['metrics'];processes=lifetime['processes']
    require(set(metrics)==METRIC_FIELDS and metrics['memory_scope']==ENGINE_SCOPE,'Invalid recovery metric fields or scope')
    require(all(type(metrics[k]) is int and 0<=metrics[k]<2**64 for k in METRIC_FIELDS-{'memory_scope','memory_complete','engine_roundtrip_seconds'}),
        'Invalid recovery metric value')
    require(proof['previews']==value['previews'] and isinstance(proof['previews'],list) and len(proof['previews'])<=len(calls),'Invalid recovery preview evidence')
    for preview in proof['previews']:
        require(set(preview)=={'sha256','seconds','step'} and isinstance(preview['sha256'],str) and len(preview['sha256'])==64 and
            type(preview['seconds']) in (int,float) and math.isfinite(preview['seconds']) and preview['seconds']>=0 and
            any(r['step']==preview['step'] and r['command']=='document.preview' and r['status']=='success' and
                r['completed_task_seconds']==preview['seconds'] for r in calls),'Preview timing lacks a successful observed command')
    require(calls and all(r['phase']=='task' and (r['status'] in ('success','expected_error') or
        (r['status']=='failure' and isinstance(r.get('engine_error'),dict))) for r in calls) and
        lifetime['observer_error'] is None and lifetime['accounting']=={'total':len(calls)+len(processes),'active':0},'Recovery process coverage is incomplete')
    require(metrics['engine_commands']==metrics['process_calls']==len(calls) and metrics['protocol_requests']==0 and
        metrics['invalid_calls']==sum((r.get('engine_error') or {}).get('code') in ('INVALID_JSON','INVALID_REQUEST') for r in calls) and
        metrics['request_bytes']==sum(r['request_bytes'] for r in calls) and metrics['response_bytes']==sum(r['response_bytes'] for r in calls) and
        metrics['retries']==sum(r['retry_of'] is not None for r in calls) and
        metrics['expected_errors']==sum(r['status']=='expected_error' for r in calls) and
        metrics['replayed_receipts']==sum(r.get('replayed',False) for r in calls) and
        metrics['engine_roundtrip_seconds']==sum(r['seconds'] for r in calls),'Recovery traffic metrics differ from observed calls')
    memory=[r['memory'] for r in calls]+[r['memory'] for r in processes]
    require(metrics['memory_complete'] is True and all(m.get('available') is True for m in memory) and
        metrics['peak_commit_bytes']==max(m['peak_commit_bytes'] for m in memory) and
        metrics['peak_working_set_bytes']==max(m['peak_working_set_bytes'] for m in memory),'Invalid recovery lifetime memory evidence')
    require(all(type(r['seconds']) in (int,float) and math.isfinite(r['seconds']) and r['seconds']>=0 for r in calls),'Invalid recovery duration')
    return copy.deepcopy(value)
