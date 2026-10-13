"""B20 external commands, immutable measured captures and independent rejudging."""
import base64
import copy
import math
import os
from pathlib import Path
import sys

from benchmark_handoff import HandoffTrial,fixture,PROMPT,PREVIEW_FILES,judge
from benchmark_consumer import Consumer,tool_identities
from benchmark_handoff_control import HandoffControl
from benchmark_runtime import Trial,require,safe_name,strict_json
from workload_cases import save_json,sha
from verify_process import run as run_owned

CAPTURE_KEY='harness_handoff'
CONTROL_FILES=('benchmark_handoff_external.py','benchmark_handoff_control.py','benchmark_recovery_bridge.py','benchmark_consumer.py')


def control_identity():return {name:sha(Path(__file__).with_name(name).read_bytes()) for name in CONTROL_FILES}


def contract_fields(case):
    return dict(consumer_tools={name:dict(sha256=value['sha256']) for name,value in case.consumer_identities.items()})


def external_trial(*args,**kwargs):
    from benchmark_driver import ExternalTrial
    class ControlledTrial(HandoffTrial,ExternalTrial):
        def begin(self,prompt):
            self.consumer_identities=tool_identities(self.consumer_tools);Trial.begin(self,prompt)
        def begin_judging(self):
            if self.phase!='judge':Trial.begin_judging(self)
            if self.consumer is None:self.consumer=Consumer(self.judge_root/'consumer',self.consumer_tools,self.timeout)
            self.consumer.phase='judge'
        def close(self):
            Trial.close(self)
            if self.consumer is not None and not self.consumer_checked:
                self.consumer_checked=True
                try:require(self.consumer.unchanged(),'Consumer executables changed during the task')
                except Exception as error:self.error=self.error or f'{type(error).__name__}: {error}'
                save_json(self.judge_root/'consumer-report.json',self.consumer.result())
        def calls_succeeded(self):
            return all(r['status'] in ('success','expected_error','response_lost') or
                (self.driver_evidence is not None and r['phase']=='task' and r['status']=='failure' and
                 isinstance(r.get('engine_error'),dict)) for r in self.calls)
        def extra_results(self):
            value=ExternalTrial.extra_results(self);capture=(self.driver_evidence or {}).get(CAPTURE_KEY)
            value[CAPTURE_KEY]=capture
            if capture:
                value.update(capture['metrics']);consumer=copy.deepcopy(capture['consumer'])
                current=self.consumer.result() if self.consumer else {}
                for key in ('judge_calls','judges','judge_engine_commands','judge_request_bytes','judge_response_bytes','judge_roundtrip_seconds'):
                    consumer[key]=current.get(key)
                value['consumer']=consumer
                matches=[]
                for check,name in PREVIEW_FILES.items():
                    if any(c['name']==check and c['status']=='pass' for c in self.checks):
                        digest=sha((self.root/name).read_bytes())
                        matches += [p['seconds'] for p in capture['previews'] if p['sha256']==digest]
                if self.arm=='model':
                    value['first_verified_preview_seconds']=min(matches) if matches else None
                    value['preview_timing_source']='harness_observed'
            return value
    return ControlledTrial(*args,**kwargs)


def configure_request(case,request):
    require(os.name=='nt','B20 external consumer process accounting requires Windows')
    request.pop('engine_executable',None);request['mcp_config']=None
    request['handoff_bridge']=[sys.executable,str(Path(__file__).with_name('benchmark_recovery_bridge.py').resolve()),
        str((case.judge_root/'control-channel').resolve())]
    request['tool_policy']='Use the supplied bridge for all Inkbolt/Cutbolt commands; do not inspect harness evidence or control-channel files directly. Preserve workspace inputs.'
    if case.arm=='baseline':request['tool_policy']+=' Inkbolt is unavailable. Author graphics with file writing, shell and the pinned baseline image tools; the same Cutbolt consumer is available only for this linked-video task.'


def metrics(calls,consumer,arm):
    require(arm in ('model','baseline') and (arm!='baseline' or not calls),'Baseline invoked Inkbolt')
    require(all(r['phase']=='task' and r['status'] in ('success','expected_error','failure') and
        type(r['seconds']) in (int,float) and math.isfinite(r['seconds']) and r['seconds']>=0 and
        all(type(r[k]) is int and r[k]>=0 for k in ('request_bytes','response_bytes')) for r in calls),'Invalid Inkbolt observations')
    require(consumer['memory_complete'] is True and consumer['commands']==len(consumer['calls'])>0 and
        all(r['phase']=='task' and r['memory_available'] is True and r['active_processes']==0 and r['processes']>=1 and
            type(r['peak_tree_commit_bytes']) is int and r['peak_tree_commit_bytes']>0 for r in consumer['calls']),
        'Incomplete consumer process observations')
    require(consumer['request_bytes']==sum(r['request_bytes'] for r in consumer['calls']) and
        consumer['response_bytes']==sum(r['response_bytes'] for r in consumer['calls']) and
        consumer['roundtrip_seconds']==sum(r['seconds'] for r in consumer['calls']) and
        consumer['retries']==sum(r['retry_of'] is not None for r in consumer['calls']) and
        consumer['peak_tree_commit_bytes']==max(r['peak_tree_commit_bytes'] for r in consumer['calls']),
        'Consumer metrics differ from recorded calls')
    memory=[r['memory'] for r in calls];complete=bool(memory) and all(m.get('available') is True for m in memory)
    require(arm=='baseline' or complete,'Incomplete Inkbolt memory observations')
    result=dict(engine_commands=len(calls),process_calls=len(calls),protocol_requests=0,
        request_bytes=sum(r['request_bytes'] for r in calls),response_bytes=sum(r['response_bytes'] for r in calls),
        invalid_calls=sum((r.get('engine_error') or {}).get('code') in ('INVALID_JSON','INVALID_REQUEST') for r in calls),
        retries=sum(r['retry_of'] is not None for r in calls),expected_errors=sum(r['status']=='expected_error' for r in calls),
        replayed_receipts=sum(r.get('replayed',False) for r in calls),engine_roundtrip_seconds=sum(r['seconds'] for r in calls),
        memory_complete=complete,memory_scope='individual solve CLI processes' if arm=='model' else 'Inkbolt unavailable in baseline arm',
        peak_commit_bytes=max(m['peak_commit_bytes'] for m in memory) if complete else None,
        peak_working_set_bytes=max(m['peak_working_set_bytes'] for m in memory) if complete else None)
    result.update(total_engine_commands=len(calls)+consumer['commands'],total_engine_retries=result['retries']+consumer['retries'],
        total_request_bytes=result['request_bytes']+consumer['request_bytes'],total_response_bytes=result['response_bytes']+consumer['response_bytes'],
        total_engine_roundtrip_seconds=result['engine_roundtrip_seconds']+consumer['roundtrip_seconds'],
        consumer_peak_tree_commit_bytes=consumer['peak_tree_commit_bytes'])
    return result


def execute_client(case,configuration,request_path):
    case.timeout=min(30,configuration['timeout_seconds'])
    case.consumer=Consumer(case.judge_root/'consumer',case.consumer_tools,case.timeout)
    broker=HandoffControl(case,case.judge_root/'control-channel');broker.start()
    try:execution=run_owned(configuration['argv']+[str(request_path)],case.root,configuration['timeout_seconds'],observe_memory=True)
    finally:
        try:broker.close()
        finally:HandoffTrial.begin_judging(case)
    require(broker.error is None,'Handoff controller failed: '+str(broker.error))
    require(case.consumer.unchanged(),'Consumer executables changed during solving')
    consumer=case.consumer.result();measured=metrics(case.calls,consumer,case.arm);previews=[]
    for row in case.calls:
        if row['command']=='document.preview' and row['status']=='success':
            artifact=case.results[row['step']]['result']['artifact']
            previews.append(dict(sha256=sha(base64.b64decode(artifact['data'],validate=True)),seconds=row['completed_task_seconds'],step=row['step']))
    save_json(case.judge_root/'handoff-control.json',dict(schema_version=1,arm=case.arm,calls=case.calls,results=case.results,
        metrics=measured,previews=previews))
    files={name:sha((case.judge_root/name).read_bytes()) for name in ('handoff-observations.json','handoff-control.json')}
    case.harness_handoff=dict(arm=case.arm,files=files,metrics=measured,consumer=consumer,previews=previews)
    return execution


def validate_capture(evidence,value):
    require(isinstance(value,dict) and set(value)=={'arm','files','metrics','consumer','previews'} and
        set(value['files'])=={'handoff-observations.json','handoff-control.json'},'Invalid handoff capture fields')
    for name,digest in value['files'].items():
        safe_name(name);path=evidence/name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size<=16*1024*1024 and sha(path.read_bytes())==digest,
            'Handoff evidence identity mismatch')
    control=strict_json((evidence/'handoff-control.json').read_bytes());proof=strict_json((evidence/'handoff-observations.json').read_bytes())
    require(set(control)=={'schema_version','arm','calls','results','metrics','previews'} and control['schema_version']==1 and
        value['arm']==control['arm'] and control['metrics']==value['metrics']==metrics(control['calls'],proof['consumer'],control['arm']) and
        value['consumer']==proof['consumer'] and value['previews']==control['previews'],'Invalid handoff metric fields or values')
    for preview in control['previews']:
        require(set(preview)=={'sha256','seconds','step'} and type(preview['seconds']) in (int,float) and
            math.isfinite(preview['seconds']) and preview['seconds']>=0 and
            any(r['step']==preview['step'] and r['command']=='document.preview' and r['status']=='success' and
                r['completed_task_seconds']==preview['seconds'] for r in control['calls']) and
            sha(base64.b64decode(control['results'][preview['step']]['result']['artifact']['data'],validate=True))==preview['sha256'],
            'Preview timing lacks its actual observed response')
    return copy.deepcopy(value)


def judge_baseline(case,tools):
    from benchmark_baseline_handoff import judge_handoff
    judge_handoff(case,tools)
