"""External arm orchestration, isolated from the scripted reference runner."""
import json
import subprocess
import traceback

from benchmark_driver import (config,driver_identity,read_json,run_external_task,model_run_complete,MIGRATED_TASKS)
from benchmark_baseline import tool_identity,file_hash
from benchmark_tasks import TASKS,SUITE,CHECKS,check_class
from measure_workloads import ROOT,candidate_identity,release_build,save_json,sha
import measurement_host


def run_suite(args, output, aggregate):
    configuration=config(args.driver_config)
    driver=driver_identity(configuration)
    baseline_config=read_json(args.baseline_tools) if args.baseline_tools else None
    tools=tool_identity(baseline_config) if baseline_config else None
    candidates=candidate_identity();environment=measurement_host.identity()
    executable,build=release_build(output) if args.arm=='model' else (None,None)
    selected=tuple(args.tasks or TASKS)
    identity=dict(schema_version=1,suite=SUITE,arm=args.arm,client=configuration['client'],model=configuration['model'],
        driver_kind=configuration['kind'],driver=driver,baseline_tools=tools,build=build,environment=environment,
        conditions=args.conditions,candidate_files=candidates,candidate_sha256=sha(json.dumps(candidates,sort_keys=True,separators=(',',':')).encode()),
        selected_tasks=selected,repetitions=args.repetitions,
        git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip())
    save_json(output/'inputs.json',identity)
    save_json(output/'tasks.json',dict(suite=SUITE,tasks=[dict(id=task,title=title,outcome=outcome,
        migrated=task in MIGRATED_TASKS,checks=[dict(name=name,check_class=check_class(task,name)) for name in CHECKS[task]])
        for task,(title,outcome) in TASKS.items()]))
    rows=[]
    for repetition in range(1,args.repetitions+1):
        offset=(repetition-1)%len(selected)
        for task in selected[offset:]+selected[:offset]:
            name=f'{repetition:02d}-{task}';base=output/name
            try:
                row=run_external_task(executable,base,task,repetition,args.arm,configuration,tools,
                    args.import_root.resolve()/name if args.import_root else None,args.prepare_only)
            except Exception as error:
                base.mkdir(exist_ok=True)
                row=dict(task=task,repetition=repetition,arm=args.arm,status='failed',model_trials=False,
                         error=f'{type(error).__name__}: {error}')
                save_json(base/'failure.json',row)
                (base/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
            rows.append(row)
            print(json.dumps(dict(task=task,repetition=repetition,arm=args.arm,status=row['status'])),flush=True)
    unchanged=(candidates==candidate_identity() and environment==measurement_host.identity() and
               driver==driver_identity(configuration) and (tools is None or tools==tool_identity(baseline_config)) and
               (executable is None or file_hash(executable)==build['executable_sha256']))
    success=all(row['status'] in (('prepared','not_applicable') if args.prepare_only else ('passed','not_applicable')) for row in rows)
    report=dict(schema_version=2,suite=SUITE,arm=args.arm,transport='external-client',
        selected_tasks=selected,all_tasks=list(TASKS),repetitions=args.repetitions,
        full_selection=set(selected)==set(TASKS),migrated_tasks=list(MIGRATED_TASKS),
        model_trials=any(row.get('model_trials') for row in rows),
        actual_model_benchmark_complete=model_run_complete(rows,selected,args.repetitions,unchanged),
        matched_cutbolt_comparison=False,complete_scripted_suite=False,inputs_unchanged=unchanged,
        rows=rows,aggregates=aggregate(rows),
        outcome='invalid_inputs_changed' if not unchanged else 'not_applicable' if all(row['status']=='not_applicable' for row in rows) else
            'prepared' if args.prepare_only and success else
            'selected_tasks_passed' if success else 'incomplete_or_failed',
        provenance=identity,
        limitations=['Only migrated tasks can be judged by external arms; the fixed twenty-task inventory remains visible.',
            'Client-reported usage is retained as observed data; missing observations remain null.',
            'The process owner applies deadlines and cleans up its process tree, but is not a filesystem/security sandbox.',
            'The configured client must enforce the supplied tool policy and retain a credential-free transcript.',
            'Captured hashes establish identity, not an authenticated attestation of the client or transcript.',
            'Synthetic drivers never count as actual model trials; complete-suite and matched-arm comparison remain separate gates.'])
    save_json(output/'report.json',report)
    print(str(output/'report.json'))
    return 0 if success and unchanged else 2
