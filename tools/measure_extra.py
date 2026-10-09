"""Shared measurement mechanics for explicitly versioned additional workloads."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import measure_workloads as measure


def main(workload):
    parser=argparse.ArgumentParser(description=workload.__doc__)
    parser.add_argument('--output-root',type=Path,required=True)
    parser.add_argument('--repetitions',type=int,choices=range(1,11),default=5)
    parser.add_argument('--conditions',required=True)
    args=parser.parse_args()
    if sys.flags.optimize:
        parser.error('Independent correctness oracles require assertions; do not use -O')
    root=args.output_root.resolve()
    if root.is_relative_to(measure.ROOT.resolve()) or not root.parent.is_dir() or root.exists():
        parser.error('Use a new external directory under an existing parent')
    root.mkdir()
    candidates=measure.candidate_identity();source=measure.source_identity()
    environment=measure.measurement_host.identity()
    executable,build=measure.release_build(root)
    rows=[]
    for repetition in range(1,args.repetitions+1):
        row=workload.run(measure.Case(executable,root/f'{repetition:02d}-{workload.CASE}',workload.CASE,repetition))
        rows.append(row)
        print(json.dumps(dict(repetition=repetition,success=row['success'],seconds=row['engine_seconds'],
                              peak_commit=row['peak_commit_bytes'])),flush=True)
    successes=[row for row in rows if row['success']]
    report=dict(schema_version=1,suite=workload.SUITE,adapter=measure.ADAPTERS[0],selected_cases=[workload.CASE],
        repetitions=args.repetitions,source_sha256=source,source_unchanged=source==measure.source_identity(),
        candidate_files=candidates,candidate_files_unchanged=candidates==measure.candidate_identity(),
        build=build,executable_unchanged=measure.sha(executable.read_bytes())==build['executable_sha256'],
        environment=environment,environment_unchanged=environment==measure.measurement_host.identity(),
        git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=measure.ROOT,text=True).strip(),
        git_status=subprocess.check_output(['git','status','--porcelain'],cwd=measure.ROOT,text=True),
        toolchain=subprocess.check_output(['rustc','--version'],text=True).strip(),conditions=args.conditions,
        rows=rows,attempted=len(rows),successful=len(successes),failed=len(rows)-len(successes),
        successful_engine_seconds=measure.statistics_of([row['engine_seconds'] for row in successes]),
        successful_peak_commit_bytes=measure.statistics_of([row['peak_commit_bytes'] for row in successes if row['peak_commit_bytes'] is not None]),
        scope=f'Additional {workload.SUITE} baseline; unchanged scale-v1 and its gates remain separate; no full A5 acceptance',
        model_trials=False,token_usage=None,agent_time=None,
        timing='Sum of synchronous CLI process startup, transfer, execution and exit; fixture/oracle/build time excluded',
        memory='Maximum owned Windows process lifetime peak; driver excluded',
        latency_memory_gates=f'Not evaluated by this measurement driver; use workload_gates.py with a separate {workload.SUITE} baseline')
    report['valid_inputs']=all(report[k] for k in ('source_unchanged','candidate_files_unchanged','executable_unchanged','environment_unchanged'))
    report['outcome']='invalid_inputs_changed' if not report['valid_inputs'] else 'all_selected_workloads_passed' if len(successes)==len(rows) else 'baseline_recorded_with_failures'
    measure.save_json(root/'report.json',report)
    print(root/'report.json')
    return 0 if report['valid_inputs'] and len(successes)==len(rows) else 2

