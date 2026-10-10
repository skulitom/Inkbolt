"""Reproducible original scale workloads; failed tasks are evidence, never passes."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from measure_discovery import ROOT, source_identity
import measurement_host

from workload_cases import (
    SUITE_VERSION,
    ADAPTERS,
    CASES,
    COLOR,
    png,
    png_pixels,
    tiff_tags,
    Pdf,
    sha,
    save,
    save_json,
    MemoryCounters,
    process_memory,
    run_process,
    document,
    rectangle,
    native_pixels,
    native_png,
    rgba_pattern,
    check_png,
    check_tiff,
    check_pdf,
    Case,
    require,
    native_case,
    sparse_document,
    _run_case,
    run_case,
    statistics_of,
    aggregate,
)


def candidate_identity():
    # Include generators and imported oracles, not just engine source. Ignored
    # application research, artifacts and package caches never enter this list.
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others',
                                    '--exclude-standard', '-z'], cwd=ROOT).decode().split('\0')
    return {name: sha((ROOT/name).read_bytes()) for name in sorted(set(names)) if name}


def release_build(output):
    command = ['cargo', 'build', '--locked', '--release', '--message-format=json']
    start = time.perf_counter()
    build = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=1200)
    save(output/'build.stdout.jsonl', build.stdout)
    save(output/'build.stderr.txt', build.stderr)
    if build.returncode:
        raise RuntimeError('Release build failed; retained its complete logs')
    artifacts = [json.loads(line) for line in build.stdout.splitlines()]
    binaries = [value for value in artifacts if value.get('reason') == 'compiler-artifact'
                and value.get('target', {}).get('name') == 'inkbolt'
                and 'bin' in value.get('target', {}).get('kind', []) and value.get('executable')]
    if len(binaries) != 1 or binaries[0]['profile']['opt_level'] == '0':
        raise RuntimeError('Expected exactly one optimized Inkbolt binary')
    executable = Path(binaries[0]['executable']).resolve(strict=True)
    return executable, dict(command=command, seconds=time.perf_counter()-start,
                            artifact=binaries[0], executable_sha256=sha(executable.read_bytes()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', required=True, type=Path,
                        help='New directory outside the repository; parent must exist')
    parser.add_argument('--repetitions', type=int, default=5, choices=range(1, 11))
    parser.add_argument('--case', action='append', choices=CASES, dest='cases')
    parser.add_argument('--conditions', required=True, help='Describe machine load and other measurement conditions')
    parser.add_argument('--adapter', choices=ADAPTERS, default=ADAPTERS[0], help='Versioned engine calls; required outcomes/oracles stay unchanged')
    args = parser.parse_args()
    if sys.flags.optimize:
        parser.error('Correctness oracles require Python assertions; do not use -O')
    output = args.output_root.resolve()
    if output.is_relative_to(ROOT.resolve()) or not output.parent.is_dir() or output.exists():
        parser.error('Use a new external output directory under an existing parent')
    output.mkdir()
    candidates = candidate_identity()
    source = source_identity()
    environment = measurement_host.identity()
    executable, build = release_build(output)
    rows = []
    cases = tuple(dict.fromkeys(args.cases or CASES))
    for repetition in range(args.repetitions):
        # Rotate order deterministically. Each trial uses fresh process/workspace;
        # OS disk/page caches are not flushed and no cold-cache claim is made.
        offset = repetition % len(cases)
        for name in cases[offset:] + cases[:offset]:
            case = Case(executable, output/f'{repetition+1:02d}-{name}', name, repetition+1, adapter=args.adapter)
            row = run_case(case)
            rows.append(row)
            print(json.dumps(dict(case=name, repetition=repetition+1, success=row['success'],
                                  seconds=row['engine_seconds'], peak_commit=row['peak_commit_bytes'])), flush=True)
    unchanged = candidates == candidate_identity()
    report = dict(schema_version=1, suite=SUITE_VERSION, adapter=args.adapter, model_trials=False,
        full_readiness_benchmark=False, selected_cases=list(cases), repetitions=args.repetitions,
        source_sha256=source, source_unchanged=source == source_identity(),
        candidate_files=candidates, candidate_files_unchanged=unchanged, build=build,
        executable_unchanged=sha(executable.read_bytes()) == build['executable_sha256'],
        git_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
        git_status=subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT).decode(),
        toolchain=subprocess.check_output(['rustc', '--version']).decode().strip(),
        environment=environment, environment_unchanged=environment == measurement_host.identity(),
        conditions=args.conditions, rows=rows, aggregates=aggregate(rows),
        timing='Synchronous CLI process startup, JSON transfer, execution and exit; excludes fixture generation, oracle and report work',
        memory='Max of per-command Windows lifetime working-set/commit peaks; excludes driver and no child processes are started',
        cache_conditions='Fresh workspace and process per case/call; OS caches may be warm, no application cache reuse across cases',
        token_usage=None, model_calls=None, agent_time=None,
        latency_memory_gates='Not established; failed workloads cannot set successful-task budgets',
        outcome='baseline_recorded_with_failures' if any(not row['success'] for row in rows) else 'all_selected_workloads_passed')
    report['valid_inputs'] = (unchanged and report['source_unchanged'] and report['executable_unchanged']
                              and report['environment_unchanged'])
    if not report['valid_inputs']:
        report['outcome'] = 'invalid_inputs_changed'
    save_json(output/'report.json', report)
    if not report['valid_inputs']:
        raise RuntimeError('Measurement inputs changed; retained report is invalid')
    print(str(output/'report.json'))
    return 2 if any(not row['success'] for row in rows) else 0


if __name__ == '__main__':
    sys.exit(main())
