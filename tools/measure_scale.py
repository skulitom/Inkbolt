"""Run the fixed scale-v2 suite without changing scale-v1 or the B10 budget."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import measure_workloads as measure
import scale_workloads as scale


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root',type=Path,required=True)
    parser.add_argument('--repetitions',type=int,choices=range(1,11),default=5)
    parser.add_argument('--case',action='append',choices=scale.CASES,dest='cases')
    parser.add_argument('--conditions',required=True)
    parser.add_argument('--jpeg-python',type=Path,help='External Python with pinned Pillow 10.3.0; required for the JPEG case')
    args=parser.parse_args(argv)
    if sys.flags.optimize:parser.error('Independent oracles require assertions; do not use -O')
    cases=tuple(args.cases or scale.CASES)
    if len(set(cases))!=len(cases):parser.error('Duplicate cases are not allowed')
    if not args.conditions.strip():parser.error('Describe actual measurement conditions')
    if 'jpeg-24mp' in cases and (args.jpeg_python is None or not args.jpeg_python.is_absolute() or not args.jpeg_python.is_file()):
        parser.error('Provide an absolute --jpeg-python executable with Pillow 10.3.0')
    output=args.output_root.resolve()
    if output.is_relative_to(measure.ROOT.resolve()) or not output.parent.is_dir() or output.exists():
        parser.error('Use a new external directory under an existing parent')
    output.mkdir()
    candidates=measure.candidate_identity();source=measure.source_identity()
    environment=measure.measurement_host.identity()
    executable,build=measure.release_build(output)
    measure.save_json(output/'inputs.json',dict(suite=scale.SUITE,candidate_files=candidates,
        source_sha256=source,build=build,environment=environment,conditions=args.conditions,
        cases=cases,repetitions=args.repetitions))
    rows=[]
    for repetition in range(1,args.repetitions+1):
        offset=(repetition-1)%len(cases)
        for name in cases[offset:]+cases[:offset]:
            case=measure.Case(executable,output/f'{repetition:02d}-{name}',name,repetition,timeout=1200)
            row=scale.run(case,jpeg_python=args.jpeg_python);rows.append(row)
            print(json.dumps(dict(case=name,repetition=repetition,success=row['success'],
                seconds=row['engine_seconds'],peak_commit=row['peak_commit_bytes'],
                peak_resident=row['peak_resident_bytes'],commit_budget=row['commit_budget']['status'])),flush=True)
    report=dict(schema_version=1,suite=scale.SUITE,adapter=measure.ADAPTERS[0],model_trials=False,
        full_readiness_benchmark=False,selected_cases=list(cases),repetitions=args.repetitions,
        source_sha256=source,source_unchanged=source==measure.source_identity(),candidate_files=candidates,
        candidate_files_unchanged=candidates==measure.candidate_identity(),build=build,
        executable_unchanged=measure.sha(executable.read_bytes())==build['executable_sha256'],
        environment=environment,environment_unchanged=environment==measure.measurement_host.identity(),
        git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=measure.ROOT,text=True).strip(),
        toolchain=subprocess.check_output(['rustc','--version'],text=True).strip(),conditions=args.conditions,
        rows=rows,aggregates=measure.aggregate(rows),
        timing='Sequential CLI lifetimes including transfer/startup; fixtures, independent oracles and compilation excluded',
        memory='Windows lifetime commit/working-set versus Linux RSS including isolated pre-exec footprint; RSS cannot establish D7 commit acceptance',
        cache_conditions='Fresh workspaces and processes; cases rotate; OS caches may be warm',
        complete_scale_acceptance=False,token_usage=None,model_calls=None,agent_time=None)
    report['valid_inputs']=all(report[key] for key in ('source_unchanged','candidate_files_unchanged','executable_unchanged','environment_unchanged'))
    success=all(row['success'] for row in rows)
    report['full_suite_fidelity']=report['valid_inputs'] and success and set(cases)==set(scale.CASES)
    report['outcome']='all_selected_workloads_passed' if success else 'baseline_recorded_with_failures'
    if not report['valid_inputs']:report['outcome']='invalid_inputs_changed'
    measure.save_json(output/'report.json',report)
    print(str(output/'report.json'))
    return 0 if success and report['valid_inputs'] else 2


if __name__=='__main__':sys.exit(main())
