"""Compare retained external trials without mixing artifacts and engine guarantees."""
import hashlib
import json
import math
from pathlib import Path
import statistics

from benchmark_tasks import (SUITE, TASKS, CHECKS, ARTIFACT_CHECKS, ENGINE_CHECKS,
                             BASELINE_NOT_APPLICABLE, check_class)


# Fixed before model trials; changes require a new policy identity, not retroactive tuning.
CATEGORIES = {
    'authoring': ('B01','B02','B05','B06','B07','B12'),
    'input_admission': ('B04',), 'scale': ('B03','B10'),
    'pixel_editing': ('B08','B09','B11'), 'delivery': ('B13','B14','B20'),
    'repair': ('B15','B16'), 'recovery': ('B17','B18','B19'),
}
POLICY = dict(version=1, minimum_repetitions=5, cost_ratio=2,
              cost_metrics=['model_calls','input_output_tokens'], categories=CATEGORIES,
              baseline_versions=dict(resvg='0.47.0',pillow='12.3.0'),
              interval='95% Wilson score; independent Bernoulli trials assumed')
METRICS = ('model_calls','input_output_tokens','input_tokens','output_tokens',
           'cached_input_tokens','reasoning_tokens','engine_commands','invalid_calls',
           'retries','request_bytes','response_bytes','first_verified_preview_seconds',
           'agent_seconds','harness_wall_seconds','engine_roundtrip_seconds',
           'total_engine_commands','total_engine_retries','total_request_bytes',
           'total_response_bytes','total_engine_roundtrip_seconds','peak_commit_bytes',
           'peak_working_set_bytes','consumer_peak_tree_commit_bytes',
           'client_tree_peak_process_commit_bytes','client_tree_peak_job_commit_bytes')


def require(condition, message):
    if not condition: raise ValueError(message)


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(value):return hashlib.sha256(value).hexdigest()


def hash_string(value):
    return isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def read_bytes(path, limit):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size<=limit,
            'Missing, linked or oversized evidence: '+str(path))
    return path.read_bytes()


def read_json(path, limit=1024*1024):
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'Duplicate JSON key');result[key]=value
        return result
    def invalid(value):raise ValueError('Nonfinite JSON value: '+value)
    return json.loads(read_bytes(path,limit),object_pairs_hook=pairs,parse_constant=invalid)


def retained_contract(root, row, provenance):
    """Check portable request and capture metadata, without rerunning any judge."""
    task=row['task'];rep=row['repetition'];base=root/f'{rep:02d}-{task}'
    require(base.resolve().is_relative_to(root.resolve()),'Trial evidence escapes report directory')
    saved=base/('result.json' if (base/'result.json').exists() else 'failure.json')
    require(read_json(saved,32*1024*1024)==row,'Aggregate row differs from retained trial result')
    if row['status']=='not_applicable':
        require(provenance['arm']=='baseline' and task in BASELINE_NOT_APPLICABLE and row.get('reason')==BASELINE_NOT_APPLICABLE[task],
                'Unexpected inapplicable trial')
        return None,False
    request=read_json(base/'evidence/request.json');contract=request['contract']
    require(request['contract_sha256']==digest(canonical(contract)),'Request contract hash differs')
    for key,value in dict(task=task,repetition=rep,arm=provenance['arm'],client=provenance['client'],
                          model=provenance['model'],kind=provenance['driver_kind']).items():
        require(contract[key]==value,'Request contract differs: '+key)
    # Creation tasks can have no source assets; their prompt is still hashed
    # separately and both arms must retain the same (possibly empty) manifest.
    require(hash_string(contract['prompt_sha256']) and isinstance(contract['fixtures'],dict) and
            all(hash_string(v) for v in contract['fixtures'].values()),'Invalid fixture/prompt identities')
    if 'prompt_sha256' in row:require(row['prompt_sha256']==contract['prompt_sha256'],'Row prompt differs')
    if 'sources' in row:require(row['sources']==contract['fixtures'],'Row fixture identities differ')
    engine=(provenance.get('build') or {}).get('executable_sha256')
    require(contract['engine_sha256']==engine,'Request engine differs from report build')
    if provenance['arm']=='baseline':require(engine is None,'Baseline report contains an Inkbolt build')
    else:require(hash_string(engine),'Missing model-arm executable identity')
    baseline=provenance.get('baseline_tools')
    require(contract['baseline_tools']==(None if baseline is None else
        {k:{a:b for a,b in v.items() if a!='path'} for k,v in baseline.items()}),'Baseline tools differ from contract')
    if task=='B20':
        require(contract['consumer_tools']=={k:dict(sha256=v['sha256']) for k,v in provenance['consumer_tools'].items()},
                'Consumer tools differ from contract')
    driver=row.get('driver')
    if not driver:
        require(row['status']!='passed','Passing trial lacks captured client evidence')
        return contract,False  # Failed clients remain in the denominator.
    capture=read_json(base/'evidence/capture.json',32*1024*1024)
    result=read_json(base/'evidence/driver-result.json')
    for key in ('kind','client','model'):
        require(driver[key]==result[key]==contract[key],'Captured client identity differs: '+key)
    require(capture['contract']==contract and driver['contract_sha256']==result['contract_sha256']==digest(canonical(contract)),
            'Captured contract differs')
    require(driver['result_sha256']==capture['result_sha256']==digest(read_bytes(base/'evidence/driver-result.json',1024*1024)),
            'Captured driver result differs')
    name=result['transcript']
    require(isinstance(name,str) and name not in ('','.','..') and '/' not in name and '\\' not in name and ':' not in name,
            'Invalid transcript filename')
    raw=read_bytes(base/'evidence'/name,64*1024*1024)
    require(bool(raw) and driver['transcript_sha256']==capture['transcript_sha256']==digest(raw),'Captured transcript differs')
    require(driver['execution']==capture['execution'] and driver['original_host']==capture['host'] and
            driver['workspace_sha256']==digest(canonical(capture['workspace_files'])),'Captured execution/workspace metadata differs')
    # Imported trials retain the original driver; matching uses the original hashes too.
    require(capture['driver_identity']==provenance['driver'],'Captured driver differs from configured driver')
    for key in ('model_calls','token_usage','agent_seconds'):
        require(row.get(key)==driver['observations'].get(key)==(result.get('observations') or {}).get(key),
                'Client observation differs: '+key)
    valid=not row.get('driver_failure') and driver['execution'].get('status')=='passed' and row['status'] in ('passed','failed')
    require(row['status']!='passed' or valid,'Passing trial has an incomplete captured execution')
    return contract,valid


def load_report(path, arm):
    path=Path(path);report=read_json(path,128*1024*1024);p=report['provenance']
    require(report['schema_version']==2 and report['suite']==SUITE and report['arm']==p['arm']==arm and
            report['transport']=='external-client','Expected a version-2 external '+arm+' report')
    require(p['suite']==SUITE and p['driver_kind'] in ('model','synthetic') and p.get('client') and p.get('model'),
            'Missing client/model provenance')
    require(hash_string(p['driver']['config_sha256']) and isinstance(p['driver']['files'],dict) and p['driver']['files'] and
            all(hash_string(v['sha256']) for v in p['driver']['files'].values()) and
            isinstance(p['environment'],dict) and bool(p['environment']) and
            isinstance(p['conditions'],str) and bool(p['conditions'].strip()),'Incomplete driver/machine/condition provenance')
    if arm=='baseline':
        tools=p['baseline_tools']
        require(set(tools)=={'resvg','python','pillow'} and all(hash_string(tools[k]['sha256']) for k in ('resvg','python')) and
                hash_string(tools['pillow']['files_sha256']) and all(tools[k]['version']==v for k,v in POLICY['baseline_versions'].items()),
                'Baseline tools are missing or not the pinned versions')
    require(isinstance(p['candidate_files'],dict) and bool(p['candidate_files']) and
            all(hash_string(v) for v in p['candidate_files'].values()) and
            p['candidate_sha256']==digest(canonical(p['candidate_files'])),'Candidate fingerprint differs')
    selected=report['selected_tasks'];reps=report['repetitions']
    require(isinstance(selected,list) and bool(selected) and len(selected)==len(set(selected)) and set(selected)<=set(TASKS),
            'Invalid task selection')
    require(type(reps) is int and 1<=reps<=10 and p['selected_tasks']==selected and p['repetitions']==reps,
            'Invalid repetition/selection provenance')
    rows={};contracts={};valid={};issues={}
    for row in report['rows']:
        key=(row['task'],row['repetition'])
        require(key[0] in selected and type(key[1]) is int and 1<=key[1]<=reps and key not in rows and row['arm']==arm,
                'Duplicate or unexpected trial row')
        require(row['status'] in ('passed','failed','prepared','not_applicable','not_implemented'),'Unknown trial status')
        checks=row.get('checks',[]);names=[c['name'] for c in checks]
        require(len(names)==len(set(names)) and set(names)<=set(CHECKS[key[0]])|{'source-preservation'},'Duplicate or unknown check')
        for check in checks:
            require(check['check_class']==check_class(key[0],check['name']) and check['status'] in ('pass','fail','not_applicable'),
                    'Invalid check class/status')
            require(check['status']!='not_applicable' or (arm=='baseline' and check['check_class']=='engine' and check.get('reason')),
                    'Artifact or model check cannot be inapplicable')
            require(arm!='baseline' or check['check_class']!='engine' or check['status']=='not_applicable',
                    'Baseline engine checks must be explicitly inapplicable')
        if row['status']=='passed':
            require(set(names)==set(CHECKS[key[0]])|{'source-preservation'} and not row.get('error') and
                    not row.get('driver_failure') and all(c['status'] in ('pass','not_applicable') for c in checks),
                    'Passing row has missing or failed checks')
        rows[key]=row
        try:contracts[key],valid[key]=retained_contract(path.parent,row,p)
        except (ValueError,KeyError,TypeError,OSError) as error:
            contracts[key]=None;valid[key]=False;issues[key]=str(error)
    return dict(report=report,rows=rows,contracts=contracts,valid=valid,issues=issues,
                path=str(path.resolve()),sha256=digest(read_bytes(path,128*1024*1024)))


def rate(passed, total):
    if not total:return dict(passed=0,total=0,rate=None,wilson_95=None)
    p=passed/total;z=1.959963984540054;den=1+z*z/total
    center=(p+z*z/(2*total))/den;radius=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/den
    return dict(passed=passed,total=total,rate=p,wilson_95=[max(0,center-radius),min(1,center+radius)])


def artifact_success(row, valid):
    return bool(row and valid and all(any(c['name']==name and c['status']=='pass' for c in row.get('checks',[]))
        for name in ARTIFACT_CHECKS[row['task']]+('source-preservation',)))


def number(value):
    require(value is None or (type(value) in (int,float) and math.isfinite(value) and value>=0),'Invalid numeric observation')
    return value


def metric(row, name):
    usage=row.get('token_usage') or {};driver=row.get('driver') or {}
    if name=='input_output_tokens':
        parts=[number(usage.get(k)) for k in ('input_tokens','output_tokens')]
        value=sum(parts) if all(v is not None for v in parts) else None
    elif name.endswith('_tokens'):value=usage.get(name)
    elif name=='harness_wall_seconds':value=driver.get('execution',{}).get('seconds')
    elif name.startswith('client_tree_'):
        memory=row.get('external_process_tree_memory') or {}
        value=memory.get(name.removeprefix('client_tree_')) if memory.get('available') is True else None
    elif name in ('peak_commit_bytes','peak_working_set_bytes'):
        value=row.get(name) if row.get('memory_complete') is True else None
    else:value=row.get(name)
    number(value)
    require(value is None or name.endswith('_seconds') or type(value) is int,'Count/byte observations must be integers')
    return value


def distribution(values):
    known=[v for v in values if v is not None]
    return dict(observed=len(known),unknown=len(values)-len(known),minimum=min(known) if known else None,
        maximum=max(known) if known else None,mean=statistics.mean(known) if known else None,
        median=statistics.median(known) if known else None,stdev=statistics.stdev(known) if len(known)>1 else None)


def summarize(data, task):
    report=data['report'];reps=report['repetitions'] if task in report['selected_tasks'] else 0
    rows=[data['rows'].get((task,i)) for i in range(1,reps+1)]
    applicable=not (report['arm']=='baseline' and task in BASELINE_NOT_APPLICABLE)
    successes=[artifact_success(row,data['valid'].get((task,i),False)) for i,row in enumerate(rows,1)]
    trusted=[row if (task,i) not in data['issues'] else None for i,row in enumerate(rows,1)]
    engine={}
    for name in ENGINE_CHECKS[task]:
        counts=dict(passed=0,failed=0,not_applicable=0,missing=0,unverified=0)
        for rep,row in enumerate(rows,1):
            check=next((c for c in (row or {}).get('checks',[]) if c['name']==name),None)
            if (task,rep) in data['issues']:counts['unverified']+=1
            elif not applicable and row and row['status']=='not_applicable':counts['not_applicable']+=1
            elif check is None:counts['missing']+=1
            elif not data['valid'].get((task,rep),False):counts['unverified']+=1
            else:counts[{'pass':'passed','fail':'failed','not_applicable':'not_applicable'}[check['status']]]+=1
        engine[name]=counts
    return dict(selected=bool(reps),not_applicable_reason=BASELINE_NOT_APPLICABLE.get(task) if not applicable else None,
        statuses={s:sum((row or {}).get('status','missing')==s for row in rows)
                  for s in ('passed','failed','missing','prepared','not_implemented','not_applicable')},
        artifact=rate(sum(successes),reps) if applicable else None,
        workflow=rate(sum(bool(row and row['status']=='passed' and data['valid'].get((task,i),False) and
            all(any(c['name']==name and (c['status']=='pass' or (report['arm']=='baseline' and c['status']=='not_applicable'))
                for c in row.get('checks',[])) for name in CHECKS[task]+('source-preservation',))) for i,row in enumerate(rows,1)),reps)
            if applicable else None,
        engine_checks=engine,
        metrics={name:dict(all_attempts=distribution([metric(row or {},name) for row in trusted]),
                          artifact_successes=distribution([metric(row,name) for row,ok in zip(rows,successes) if ok])) for name in METRICS},
        memory_scopes=sorted({row['memory_scope'] for row in rows if row and row.get('memory_scope')}))


def compare(model, baseline):
    arms=dict(model=model,baseline=baseline);a=model['report'];b=baseline['report'];p=a['provenance'];q=b['provenance']
    global_issues=[]
    for key in ('candidate_sha256','client','model','driver_kind','driver','conditions'):
        if p.get(key)!=q.get(key):global_issues.append('Different '+key)
    for arm,data in arms.items():
        if data['report'].get('inputs_unchanged') is not True:global_issues.append(arm+' inputs changed or unverified')
    tasks=[];losing=[];failures=[]
    for task in TASKS:
        summaries={arm:summarize(data,task) for arm,data in arms.items()};issues=list(global_issues);pairs=[];identities=set()
        selected=all(task in data['report']['selected_tasks'] for data in arms.values())
        if not selected:issues.append('Task not selected in both arms')
        if a['repetitions']!=b['repetitions']:issues.append('Different repetition counts')
        for arm,data in arms.items():
            if task not in data['report']['selected_tasks']:continue
            for rep in range(1,data['report']['repetitions']+1):
                key=(task,rep);row=data['rows'].get(key)
                missing=[name for name in CHECKS[task]+('source-preservation',) if not any(c['name']==name for c in (row or {}).get('checks',[]))]
                if not row or row['status'] not in ('passed','not_applicable') or key in data['issues']:
                    failures.append(dict(arm=arm,task=task,repetition=rep,status=(row or {}).get('status','missing'),
                        error=(row or {}).get('error'),driver_failure=(row or {}).get('driver_failure'),
                        evidence_error=data['issues'].get(key),failed_checks=[c for c in (row or {}).get('checks',[]) if c['status']=='fail'],
                        missing_checks=missing))
                if key in data['issues']:issues.append(f'{arm} repetition {rep}: retained evidence invalid')
                if row and row['status'] in ('prepared','not_implemented'):
                    issues.append(f'{arm} repetition {rep}: trial did not execute')
        if selected and task not in BASELINE_NOT_APPLICABLE:
            for rep in range(1,min(a['repetitions'],b['repetitions'])+1):
                key=(task,rep);left=model['contracts'].get(key);right=baseline['contracts'].get(key)
                if left is None or right is None:issues.append(f'Repetition {rep}: request contract unavailable');continue
                for name in ('prompt_sha256','fixtures','control_files','consumer_tools'):
                    if left.get(name)!=right.get(name):issues.append(f'Repetition {rep}: different '+name)
                x=model['rows'].get(key,{});y=baseline['rows'].get(key,{})
                hosts=[(row.get('driver') or {}).get('original_host',data['report']['provenance']['environment'])
                       for row,data in ((x,model),(y,baseline))]
                if hosts[0]!=hosts[1]:issues.append(f'Repetition {rep}: different original hosts')
                identities.add(digest(canonical(dict(prompt=left['prompt_sha256'],fixtures=left['fixtures'],
                    controls=left.get('control_files'),consumer=left.get('consumer_tools'),host=hosts[0]))))
                pairs.append((key,x,y))
        if len(identities)>1:issues.append('Inputs or original host vary across repetitions')
        comparable=selected and task not in BASELINE_NOT_APPLICABLE and not issues
        reasons=[];costs={}
        enough=comparable and len(pairs)>=POLICY['minimum_repetitions']
        if enough and summaries['baseline']['artifact']['passed']>=summaries['model']['artifact']['passed']:
            reasons.append('baseline_artifact_success_at_least_model')
        successful=[(x,y) for key,x,y in pairs if artifact_success(x,model['valid'].get(key,False)) and
                    artifact_success(y,baseline['valid'].get(key,False))]
        for name in POLICY['cost_metrics']:
            xs=[metric(x,name) for x,y in successful];ys=[metric(y,name) for x,y in successful]
            complete=enough and len(successful)>=POLICY['minimum_repetitions'] and all(v is not None for v in xs+ys)
            left=statistics.median(xs) if complete else None;right=statistics.median(ys) if complete else None
            excessive=complete and left>right and left>=POLICY['cost_ratio']*right
            costs[name]=dict(successful_pairs=len(successful),observed_pairs=sum(x is not None and y is not None for x,y in zip(xs,ys)),
                complete=complete,model_median=left,baseline_median=right,ratio=left/right if complete and right>0 else None,
                baseline_zero=complete and right==0,excessive=excessive)
            if excessive:reasons.append('model_uses_at_least_twice_'+name)
        category=next(name for name,ids in CATEGORIES.items() if task in ids)
        row=dict(task=task,title=TASKS[task][0],category=category,arms=summaries,comparable=comparable,
            matched_pairs=len(pairs),minimum_repetitions_met=enough,issues=sorted(set(issues)),cost_comparison=costs,losing_reasons=reasons)
        tasks.append(row)
        if reasons:losing.append(dict(task=task,category=category,reasons=reasons))
    def complete(data):
        report=data['report']
        return set(report['selected_tasks'])==set(TASKS) and report['repetitions']>=5 and report['inputs_unchanged'] is True and all(
            data['valid'].get((task,rep),False) or (report['arm']=='baseline' and task in BASELINE_NOT_APPLICABLE and
                data['rows'].get((task,rep),{}).get('status')=='not_applicable' and (task,rep) not in data['issues'])
            for task in TASKS for rep in range(1,report['repetitions']+1))
    genuine=p['driver_kind']==q['driver_kind']=='model'
    matched=not global_issues and all(row['minimum_repetitions_met'] for row in tasks if row['task'] not in BASELINE_NOT_APPLICABLE)
    ready=genuine and matched and all(complete(data) for data in arms.values())
    return dict(schema_version=1,suite=SUITE,policy=POLICY,policy_sha256=digest(canonical(dict(policy=POLICY,checks=CHECKS,
        artifacts=ARTIFACT_CHECKS,engine=ENGINE_CHECKS))),
        inputs={arm:dict(report_path=data['path'],report_sha256=data['sha256'],candidate_sha256=data['report']['provenance']['candidate_sha256'])
                for arm,data in arms.items()},
        evidence_kind='declared_model' if genuine else 'synthetic_or_mixed',global_issues=global_issues,
        actual_model_benchmark_complete=p['driver_kind']=='model' and complete(model),
        matched_model_baseline_complete=ready,decision_ready=ready,matched_cutbolt_comparison=False,
        tasks=tasks,losing_tasks=losing,failures=failures,
        categories={name:dict(tasks=list(ids),comparable=sum(row['comparable'] for row in tasks if row['task'] in ids),
            losing=[row['task'] for row in losing if row['task'] in ids]) for name,ids in CATEGORIES.items()},
        limitations=['Retained reports/capture metadata are checked; artifact judges and full workspace hashing are not rerun.',
            'Hashes identify evidence; they cannot authenticate genuine client behavior. Retain trusted transcripts and judge evidence.',
            'Intervals assume independent trials. Five equal outcomes are a prioritization signal, not proof of equivalence.',
            'Unknown metrics stay unknown; failed attempts remain in totals and separate distributions.',
            'Engine, consumer and client-tree memory have different scopes; no cross-scope memory or engine-call efficiency claim is made.',
            'This comparison does not establish the separate matched Cutbolt-product readiness gate.'])


def markdown(report):
    lines=['# Agent benchmark comparison','',
        'Evidence: '+report['evidence_kind']+'. Decision-ready: '+str(report['decision_ready']).lower()+'.',
        'Synthetic or incomplete comparisons do not establish model performance.','',
        '| Task | Category | Model artifact passes | Baseline artifact passes | Comparable |',
        '| --- | --- | ---: | ---: | --- |']
    def count(value):return 'N/A' if value is None else f"{value['passed']}/{value['total']}"
    for row in report['tasks']:
        lines.append(f"| {row['task']} | {row['category']} | {count(row['arms']['model']['artifact'])} | {count(row['arms']['baseline']['artifact'])} | {str(row['comparable']).lower()} |")
    lines+=['','## Losing-task signals','']
    lines += ['- '+row['task']+': '+', '.join(row['reasons']) for row in report['losing_tasks']] or ['None established.']
    lines+=['','## Coverage and interpretation','',
        f"Retained failed, missing or invalid trial rows: {len(report['failures'])}.",
        'Full JSON includes every failure, missing check, matching issue, Wilson interval, engine check and metric distribution.',
        'A cost signal requires at least five artifact-successful matched pairs, complete observations and a twofold median increase.',
        'Input plus output tokens exclude separate cached/reasoning counts to avoid double counting.',
        'Unknown observations cannot establish an efficiency advantage. Equal small samples do not prove equivalence.','']
    return '\n'.join(lines)
