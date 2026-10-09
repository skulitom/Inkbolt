"""Reproducible B01-B20 task evidence; scripted runs never count as model trials."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import traceback

from benchmark_tasks import SUITE, TASKS, CHECKS
from benchmark_graphics import ADAPTERS
from benchmark_runtime import Trial
from measure_workloads import (ROOT, candidate_identity, release_build, save_json,
                               sha, statistics_of)
import measurement_host


def run_task(executable, root, task, repetition, transport):
    if task not in ADAPTERS:
        root.mkdir()
        row=dict(task=task,repetition=repetition,transport=transport,status='not_implemented',
            required_outcome=TASKS[task][1],reason='The benchmark adapter and independent judge remain required.',
            calls=[],checks=[],token_usage=None,model_calls=None,agent_seconds=None,model_trials=False)
        save_json(root/'result.json',row)
        return row
    trial=Trial(executable,root,task,repetition,transport,CHECKS[task])
    try:
        ADAPTERS[task](trial)
    except Exception as error:
        trial.error=f'{type(error).__name__}: {error}'
        (root/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
    return trial.finish()


def aggregate(rows):
    def distribution(values):
        return dict(count=len(values),**statistics_of(values)) if values else None
    result=[]
    for task in TASKS:
        trials=[row for row in rows if row['task']==task]
        measured=[row for row in trials if row['status']!='not_implemented']
        result.append(dict(task=task,selected=bool(trials),trials=len(trials),
            passed=sum(row['status']=='passed' for row in trials),
            failed=sum(row['status']=='failed' for row in trials),
            not_implemented=sum(row['status']=='not_implemented' for row in trials),
            # Failed attempt metrics stay in these distributions; fast rejection
            # cannot silently become a successful-task performance observation.
            observations={key:distribution([row[key] for row in measured if row.get(key) is not None])
                for key in ('engine_commands','request_bytes','response_bytes','retries',
                            'engine_roundtrip_seconds','scripted_wall_seconds',
                            'first_verified_preview_seconds','peak_commit_bytes','peak_working_set_bytes')}))
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root',required=True,type=Path,help='New external directory; parent must exist')
    parser.add_argument('--conditions',required=True,help='Actual machine/load conditions; no isolation is implied')
    parser.add_argument('--repetitions',type=int,choices=range(1,11),default=5)
    parser.add_argument('--transport',choices=['cli','mcp'],default='mcp')
    parser.add_argument('--task',action='append',choices=list(TASKS),dest='tasks')
    args=parser.parse_args(argv)
    if sys.flags.optimize: parser.error('Independent oracles require assertions; do not use -O')
    if not args.conditions.strip() or len(args.conditions)>4096: parser.error('Provide bounded nonempty conditions')
    if args.tasks and len(set(args.tasks))!=len(args.tasks): parser.error('Task selections must be distinct')
    output=args.output_root.resolve()
    if output.is_relative_to(ROOT.resolve()) or not output.parent.is_dir() or output.exists():
        parser.error('Use a new external directory under an existing parent')
    output.mkdir()
    candidates=candidate_identity()
    environment=measurement_host.identity()
    executable,build=release_build(output)
    selected=tuple(args.tasks or TASKS)
    provenance=dict(schema_version=1,suite=SUITE,transport=args.transport,
        selected_tasks=list(selected),repetitions=args.repetitions,
        candidate_files=candidates,candidate_sha256=sha(json.dumps(candidates,sort_keys=True,separators=(',',':')).encode()),
        build=build,environment=environment,conditions=args.conditions,
        git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        git_status=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),
        toolchain=subprocess.check_output(['rustc','--version'],text=True).strip())
    # Preserve the exact starting state even if the driver is interrupted before
    # it can write an aggregate report. Completed trial files are already durable.
    save_json(output/'inputs.json',provenance)
    save_json(output/'tasks.json',dict(suite=SUITE,tasks=[dict(id=task,title=title,outcome=outcome,
        implemented=task in ADAPTERS,required_checks=list(CHECKS.get(task,()))) for task,(title,outcome) in TASKS.items()]))
    rows=[]
    for repetition in range(1,args.repetitions+1):
        offset=(repetition-1)%len(selected)
        for task in selected[offset:]+selected[:offset]:
            row=run_task(executable,output/f'{repetition:02d}-{task}',task,repetition,args.transport)
            rows.append(row)
            print(json.dumps(dict(task=task,repetition=repetition,status=row['status'],
                commands=row.get('engine_commands'),seconds=row.get('engine_roundtrip_seconds'))),flush=True)
    unchanged=(candidates==candidate_identity() and sha(executable.read_bytes())==build['executable_sha256']
               and environment==measurement_host.identity())
    full=set(selected)==set(TASKS)
    successful=all(row['status']=='passed' for row in rows)
    status='all_tasks_passed' if full and successful else 'selected_tasks_passed' if successful else 'incomplete_or_failed'
    if not unchanged: status='invalid_inputs_changed'
    report=dict(schema_version=1,suite=SUITE,transport=args.transport,model_trials=False,
        selected_tasks=list(selected),all_tasks=list(TASKS),full_selection=full,
        implemented_tasks=list(ADAPTERS),repetitions=args.repetitions,
        complete_scripted_suite=full and successful and unchanged,
        actual_model_benchmark_complete=False,matched_cutbolt_comparison=False,
        candidate_files=candidates,candidate_sha256=provenance['candidate_sha256'],
        inputs_unchanged=unchanged,build=build,
        git_commit=provenance['git_commit'],git_status=provenance['git_status'],toolchain=provenance['toolchain'],
        environment=environment,conditions=args.conditions,
        rows=rows,aggregates=aggregate(rows),outcome=status,
        timing='Round trips include local process/stdio/JSON costs. Scripted wall and retrospective verified-preview times include discovery and prior oracle work; fixture generation precedes begin. No autonomous agent time is inferred.',
        memory='CLI uses the maximum observed individual-process lifetime peaks; MCP uses the persistent server lifetime. Neither includes the Python driver. Missing observations stay null. No background workers are admitted by this adapter.',
        cache_conditions='Fresh workspace and server per trial; CLI process per call. OS caches may be warm. Repetition order rotates deterministically.',
        evidence='Raw CLI/MCP request/response bytes, stderr, original fixtures, delivered artifacts, exact source/executable and explicit required-check results retained. A lost-response injection retains the hidden response for the judge and marks it unobserved by the solver.',
        token_usage=None,model_calls=None,agent_seconds=None,
        limitations=['Scripted reference adapters are not autonomous model runs.',
            'Not-implemented tasks remain in the fixed twenty-task inventory and prevent full-suite acceptance.',
            'No claim of greater readiness than Cutbolt, production-scale acceptance, matched performance or added engine checkpoint credit.',
            'Reports are evidence records, not authenticated attestations; retain trusted raw files and review the independent oracles.'])
    save_json(output/'report.json',report)
    print(str(output/'report.json'))
    return 0 if successful and unchanged else 2


if __name__=='__main__':
    sys.exit(main())
