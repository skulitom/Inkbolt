"""Create and check local performance budgets from complete successful measurements."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
CASES = ('native-control', 'native-screen', 'stored-screen', 'social-square',
         'sparse-5000', 'mixed-5001', 'print-page')
# Complete local import closure of the fixed scale-v1 fixture/measurement driver.
# Pin helpers as well as the driver; changing any requires a new reviewed baseline.
HARNESS = ('tests/pdf_reader.py', 'tests/test_boards_cli.py', 'tests/test_cli.py',
           'tests/test_editing_cli.py', 'tests/test_image_io_cli.py',
           'tests/test_images_cli.py', 'tests/test_layout_cli.py', 'tests/test_mcp.py',
           'tests/test_sessions_cli.py', 'tools/measure_discovery.py',
           'tools/measure_workloads.py', 'tools/measurement_host.py')
POLICY = dict(version='scale-regression-v1', minimum_repetitions=5,
              median_seconds_factor=1.5, maximum_seconds_factor=2,
              peak_commit_factor=1.5, seconds_quantum=.001,
              memory_quantum_bytes=1024*1024)
ENVIRONMENT = ('system', 'release', 'version', 'machine', 'pointer_bits',
               'processor', 'logical_cpus', 'python')
NATIVE_CALLS = [('import', 'sample.import'), ('save', 'session.create'),
                ('initial', 'document.publish'), ('edit', 'session.apply'),
                ('edited', 'document.publish'), ('historical', 'document.publish'),
                ('undo', 'session.apply'), ('restored', 'document.publish'), ('verify', 'session.verify')]
NATIVE_CHECKS = ['initial', 'edited', 'historical', 'restored', 'history-valid', 'revision-order', 'source-preservation']
CONTRACTS = {
    'native-control': (NATIVE_CALLS, NATIVE_CHECKS),
    'native-screen': (NATIVE_CALLS, NATIVE_CHECKS),
    'stored-screen': ([('import', 'asset.import'), ('screen', 'document.publish')], ['screen', 'source-preservation']),
    'social-square': ([('social', 'document.publish')], ['social', 'source-preservation']),
    'sparse-5000': ([('scene', 'document.publish')], ['scene', 'source-preservation']),
    'mixed-5001': ([('import', 'asset.import'), ('scene', 'document.publish')], ['scene', 'source-preservation']),
    'print-page': ([('page', 'document.publish'), ('preview', 'document.publish')], ['page', 'preview', 'source-preservation'])}
WIDE_CASES = ('wide-mixed-native',)
WIDE_HARNESS = HARNESS + ('tools/measure_extra.py', 'tools/measure_wide_native.py', 'tools/wide_native_workload.py')
WIDE_CONTRACTS = {'wide-mixed-native': (
    [('import', 'sample.import'), ('save', 'session.create'),
     ('initial', 'document.publish'), ('edit', 'session.apply'),
     ('edited', 'document.publish'), ('historical', 'document.publish'), ('verify', 'session.verify')],
    ['initial', 'edited', 'historical', 'history-valid', 'revision-order', 'source-preservation'])}
LAYOUT_CASES = ('mixed-native-5000',)
LAYOUT_HARNESS = HARNESS + ('tools/measure_extra.py', 'tools/measure_native_layout.py', 'tools/native_layout_workload.py')
LAYOUT_CONTRACTS = {'mixed-native-5000': WIDE_CONTRACTS['wide-mixed-native']}
FILTER_CASES = ('native-box-blur',)
FILTER_HARNESS = HARNESS + ('tools/measure_extra.py', 'tools/measure_native_filter.py', 'tools/native_filter_workload.py')
FILTER_CONTRACTS = {'native-box-blur': WIDE_CONTRACTS['wide-mixed-native']}
SHADOW_CASES = ('native-shadow-history',)
SHADOW_HARNESS = HARNESS + ('tools/measure_extra.py', 'tools/measure_native_shadow.py', 'tools/native_shadow_workload.py')
SHADOW_CONTRACTS = {'native-shadow-history': WIDE_CONTRACTS['wide-mixed-native']}
SUITES = {
    'scale-v1': (CASES, HARNESS, CONTRACTS, ('native-tiled-v1', 'legacy-v1')),
    'wide-native-v1': (WIDE_CASES, WIDE_HARNESS, WIDE_CONTRACTS, ('native-tiled-v1',)),
    'native-layout-v1': (LAYOUT_CASES, LAYOUT_HARNESS, LAYOUT_CONTRACTS, ('native-tiled-v1',)),
    'native-filter-v1': (FILTER_CASES, FILTER_HARNESS, FILTER_CONTRACTS, ('native-tiled-v1',)),
    'native-shadow-v1': (SHADOW_CASES, SHADOW_HARNESS, SHADOW_CONTRACTS, ('native-tiled-v1',)),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def digest(value):
    return hashlib.sha256(value).hexdigest()


def hash_value(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def summarize(report):
    """Recompute eligibility and metrics from every trial; ignore aggregate claims."""
    require(report['schema_version'] == 1 and report['suite'] in SUITES, 'Unknown measurement schema/suite')
    cases, harness_files, contracts, adapters = SUITES[report['suite']]
    require(report['adapter'] in adapters, 'Unknown call adapter for this suite')
    require(report['model_trials'] is False, 'Model trials need their own gate')
    require(all(report[k] is True for k in ('valid_inputs', 'source_unchanged',
            'candidate_files_unchanged', 'executable_unchanged', 'environment_unchanged')), 'Measurement inputs changed or are unverified')
    require(report['outcome'] == 'all_selected_workloads_passed', 'Measurement contains failed workloads')
    require(report['selected_cases'] == list(cases), 'Gate requires every fixed workload in canonical order')
    repetitions = report['repetitions']
    require(type(repetitions) is int and 5 <= repetitions <= 10, 'At least five complete repetitions required')
    require(hash_value(report['source_sha256']), 'Missing measured source identity')
    build = report['build']
    require(hash_value(build['executable_sha256']), 'Missing measured executable identity')
    require(build['artifact']['profile']['opt_level'] in ('1', '2', '3', 's', 'z'), 'Optimized build required')
    require(build['artifact']['target']['name'] == 'inkbolt'
            and 'bin' in build['artifact']['target']['kind'], 'Wrong measured executable target')
    require(report['environment']['system'] == 'Windows', 'Only Windows memory measurements are verified')
    require(report['environment']['hardware_available'] is True
            and report['environment']['hardware_source'] == 'windows_native_system_info_and_cpu_registry_v1',
            'Native machine identity is unavailable or unverified')
    environment = {k: report['environment'][k] for k in ENVIRONMENT}
    require(all(isinstance(environment[k], str) and environment[k] for k in ENVIRONMENT
                if k not in ('pointer_bits', 'logical_cpus')), 'Incomplete machine identity')
    require(type(environment['pointer_bits']) is int and environment['pointer_bits'] in (32, 64)
            and type(environment['logical_cpus']) is int and environment['logical_cpus'] > 0, 'Invalid machine dimensions')
    require(isinstance(report['conditions'], str) and report['conditions'].strip(), 'Missing measurement conditions')
    require(isinstance(report['toolchain'], str) and report['toolchain'], 'Missing compiler identity')
    harness = {p: report['candidate_files'][p] for p in harness_files}
    require(all(hash_value(v) for v in harness.values()), 'Missing fixture/oracle identity')
    rows = report['rows']
    expected = {(name, n) for name in cases for n in range(1, repetitions+1)}
    require(len(rows) == len(expected), 'Incomplete or duplicate trials')
    seen, groups = set(), {name: [] for name in cases}
    for row in rows:
        key = (row['case'], row['repetition'])
        require(type(row['repetition']) is int and key in expected and key not in seen,
                'Unknown, missing or duplicate case/repetition')
        seen.add(key)
        require(row['adapter'] == report['adapter'], 'Mixed call adapters')
        require(row['success'] is True and row['blocked_steps'] == 0, 'Failed or blocked trial')
        require(row['memory_complete'] is True, 'Missing memory measurement')
        calls, checks = row['calls'], row['checks']
        require(calls and checks and row['process_calls'] == len(calls), 'Missing command/oracle records')
        require([(c['step'], c['command']) for c in calls] == contracts[row['case']][0]
                and [c['name'] for c in checks] == contracts[row['case']][1], 'Workload steps or correctness checks changed')
        require(all(c['status'] == 'pass' for c in checks)
                and any(c['name'] == 'source-preservation' for c in checks), 'Failed/missing correctness or source check')
        for call in calls:
            require(call['status'] == 'success' and call['exit_code'] == 0
                    and call['timed_out'] is False and call['retries'] == 0, 'Failed, retried or timed-out command')
            require(positive(call['seconds']), 'Invalid command timing')
            memory = call['memory']
            require(memory['available'] is True, 'Missing command memory measurement')
            require(all(type(memory[k]) is int and memory[k] > 0 for k in
                        ('peak_commit_bytes', 'peak_working_set_bytes')), 'Invalid command memory peak')
        seconds = sum(c['seconds'] for c in calls)
        peak = max(c['memory']['peak_commit_bytes'] for c in calls)
        require(positive(row['engine_seconds']) and math.isclose(row['engine_seconds'], seconds, rel_tol=1e-12),
                'Trial time disagrees with command records')
        require(type(row['peak_commit_bytes']) is int and row['peak_commit_bytes'] == peak,
                'Trial memory disagrees with command records')
        require(row['peak_working_set_bytes'] == max(c['memory']['peak_working_set_bytes'] for c in calls),
                'Working set disagrees with command records')
        groups[row['case']].append((seconds, peak))
    require(seen == expected, 'Missing trials')
    return dict(suite=report['suite'], adapter=report['adapter'], repetitions=repetitions,
                environment=environment, toolchain=report['toolchain'], harness=harness,
                metrics={name: dict(median_seconds=statistics.median(v[0] for v in values),
                                    maximum_seconds=max(v[0] for v in values),
                                    peak_commit_bytes=max(v[1] for v in values))
                         for name, values in groups.items()})


def limits(metrics, cases=CASES):
    require(set(metrics) == set(cases), 'Baseline metrics do not match the fixed suite')
    result = {}
    for name in cases:
        row = metrics[name]
        require(all(positive(row[k]) for k in ('median_seconds', 'maximum_seconds', 'peak_commit_bytes')),
                'Invalid baseline metric')
        result[name] = dict(
            median_seconds=math.ceil(row['median_seconds']*POLICY['median_seconds_factor']*1000)/1000,
            maximum_seconds=math.ceil(row['maximum_seconds']*POLICY['maximum_seconds_factor']*1000)/1000,
            peak_commit_bytes=math.ceil(row['peak_commit_bytes']*POLICY['peak_commit_factor']/(1024*1024))*(1024*1024))
    return result


def create(report, report_sha256, reason):
    summary = summarize(report)
    require(hash_value(report_sha256), 'Missing baseline report identity')
    require(isinstance(reason, str) and reason.strip(), 'Record why this baseline was selected')
    return dict(schema_version=1, kind='inkbolt_local_workload_gate', policy=dict(POLICY),
                baseline_report_sha256=report_sha256, baseline_source_sha256=report['source_sha256'],
                baseline_executable_sha256=report['build']['executable_sha256'],
                baseline_conditions=report['conditions'], selection_reason=reason,
                baseline=summary, limits=limits(summary['metrics'], SUITES[summary['suite']][0]),
                scope=f"Fixed {summary['suite']} regression budgets on the recorded environment; not full A5 or model-task acceptance")


def evaluate(gate, report):
    require(gate['schema_version'] == 1 and gate['kind'] == 'inkbolt_local_workload_gate', 'Unknown gate format')
    require(gate['policy'] == POLICY, 'Unknown or modified budget policy')
    require(hash_value(gate['baseline_report_sha256']) and hash_value(gate['baseline_source_sha256'])
            and hash_value(gate['baseline_executable_sha256']), 'Missing baseline identity')
    baseline = gate['baseline']
    require(baseline['suite'] in SUITES and type(baseline['repetitions']) is int
            and 5 <= baseline['repetitions'] <= 10, 'Invalid gate baseline')
    cases = SUITES[baseline['suite']][0]
    require(gate['limits'] == limits(baseline['metrics'], cases), 'Budgets disagree with the recorded policy/baseline')
    current = summarize(report)
    for key in ('suite', 'adapter', 'environment', 'toolchain', 'harness'):
        require(current[key] == baseline[key], f'Incomparable {key}; retain the result and review a new baseline')
    comparisons = []
    for name in cases:
        observed, allowed = current['metrics'][name], gate['limits'][name]
        comparisons.append(dict(case=name, observed=observed, limits=allowed,
                                exceeded=[k for k in allowed if observed[k] > allowed[k]]))
    return dict(status='failed' if any(row['exceeded'] for row in comparisons) else 'passed',
                eligible=True, comparisons=comparisons, repetitions=current['repetitions'])


def check(gate, report):
    try:
        return evaluate(gate, report)
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        return dict(status='ineligible', eligible=False, reason=f'{type(error).__name__}: {error}', comparisons=[])


def load(path):
    raw = path.read_bytes()
    # NaN and infinity are accepted by Python's default decoder, but are not
    # valid JSON measurements and cannot be allowed to disable comparisons.
    def reject(value):
        raise ValueError(f'Invalid JSON constant {value}')
    return json.loads(raw, parse_constant=reject), digest(raw)


def write(path, value):
    path = path.resolve()
    require(not path.is_relative_to(ROOT.resolve()), 'Keep raw measurements and budgets outside the repository')
    with path.open('x', encoding='utf-8', newline='\n') as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    make = commands.add_parser('create', help='Create new budgets from a complete successful baseline')
    make.add_argument('--baseline', type=Path, required=True)
    make.add_argument('--output', type=Path, required=True)
    make.add_argument('--reason', required=True)
    compare = commands.add_parser('check', help='Compare a new full measurement against existing budgets')
    compare.add_argument('--gate', type=Path, required=True)
    compare.add_argument('--report', type=Path, required=True)
    compare.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'create':
            report, identity = load(args.baseline)
            result = create(report, identity, args.reason)
        else:
            gate, gate_hash = load(args.gate)
            report, report_hash = load(args.report)
            result = dict(schema_version=1, gate_sha256=gate_hash, report_sha256=report_hash,
                          policy=POLICY['version'], **check(gate, report))
            if report_hash == gate.get('baseline_report_sha256'):
                result.update(status='ineligible', eligible=False,
                              reason='The baseline itself is not a new regression measurement')
        write(args.output, result)
    except (OSError, KeyError, TypeError, ValueError, OverflowError) as error:
        print(f'No passing gate evidence: {error}', file=sys.stderr)
        return 2
    print(json.dumps(dict(output=str(args.output.resolve()), status=result.get('status', 'created'))))
    return 0 if args.command == 'create' or result['status'] == 'passed' else 2


if __name__ == '__main__':
    sys.exit(main())
