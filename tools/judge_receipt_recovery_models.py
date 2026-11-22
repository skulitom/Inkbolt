"""Score a model's receipt recovery against the withheld reply and the native session."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from benchmark_driver import workspace_files
from benchmark_runtime import canonical, read_json, require, strict_json
from compare_session_recovery import create_arguments
from matched_cli_judge import capture_conditions, run_judge
from placed_still_judge import traffic
from workload_cases import sha


def creation(engine, width):
    return dict(command='session.create', **create_arguments(engine, width))


def receipt(engine, result):
    return result.get('receipt') if engine == 'inkbolt' else result


def matches_head(engine, result, original):
    document = result.get('document', {}) if engine == 'inkbolt' else result
    if engine == 'inkbolt':
        return (document == original['document'] and result.get('session_id') == 'study'
                and result.get('current_revision') == 0 and result.get('state_sha256') == original['receipt']['state_sha256'])
    return (document.get('id') == 'study' and document.get('revision') == 0 and document.get('width') == 192
            and document.get('height') == 108 and document.get('assets') == [] and document.get('clips') == []
            and document.get('frame_rate') == dict(num=25, den=1))


def matches_history(engine, result, original):
    entries = result.get('entries')
    seed = receipt(engine, original)
    if engine == 'inkbolt':
        return (entries == [seed] and result.get('session_id') == 'study'
                and result.get('current_revision') == 0 and result.get('has_more') is False)
    # Cutbolt's history summarizes the receipt's clip changes as a count.
    return (isinstance(entries, list) and len(entries) == 1 and isinstance(entries[0], dict)
            and all(k in entries[0] and entries[0][k] == seed[k]
                    for k in ('action', 'parent_revision', 'request_id', 'restored_from', 'revision'))
            and entries[0].get('changed_clips') == len(seed['changes']['clips'])
            and 'next_before_revision' in result and result['next_before_revision'] is None)


def recorded_recovery(directory, engine, original, started_ns):
    key = 'session_id' if engine == 'inkbolt' else 'project_id'
    current = 'session.read' if engine == 'inkbolt' else 'session.get'
    conflict = 'REQUEST_ID_REUSED' if engine == 'inkbolt' else 'REQUEST_ID_CONFLICT'
    first, changed = creation(engine, 192), creation(engine, 193)
    original_receipt = receipt(engine, original)
    events = {k: [] for k in ('lookup', 'replay', 'conflict', 'head', 'history')}
    stderr_bytes = 0
    for entry in directory.iterdir():
        if not (entry / 'exit.json').is_file():
            continue
        stderr_bytes += (entry / 'stderr').stat().st_size
        try:
            request = strict_json((entry / 'input').read_bytes())
            answer = strict_json((entry / 'stdout').read_bytes())
        except (ValueError, UnicodeError):
            continue
        if not isinstance(request, dict) or not isinstance(answer, dict):
            continue
        launch, exit_info = read_json(entry / 'launch.json'), read_json(entry / 'exit.json')
        span = (launch['started_ns'], exit_info['finished_ns'])
        require(started_ns <= span[0] <= span[1], 'Recorded call predates the client or ends before launch')
        command = request.get('command')
        if exit_info['code'] != 0:
            if request == changed and answer.get('ok') is False and answer.get('error', {}).get('code') == conflict:
                events['conflict'].append(span)
            continue
        result = answer.get('result')
        if answer.get('ok') is not True or not isinstance(result, dict):
            continue
        replayed = engine == 'cutbolt' or result.get('replayed') is True
        if request == first and replayed and receipt(engine, result) == original_receipt:
            events['replay'].append(span)
        if request.get(key) != 'study':
            continue
        if command == 'session.receipt' and request.get('request_id') == 'create' and replayed and receipt(engine, result) == original_receipt:
            events['lookup'].append(span)
        if command == current and 'revision' not in request and matches_head(engine, result, original):
            events['head'].append(span)
        if command == 'session.history' and matches_history(engine, result, original):
            events['history'].append(span)

    def first_end(label, after):
        return min((end for start, end in events[label] if after is not None and start >= after), default=None)

    lookup = first_end('lookup', started_ns)
    retry = first_end('replay', lookup)
    refused = first_end('conflict', retry)
    checks = dict(lookup=lookup is not None, exact_replay=retry is not None, changed_request_refused=refused is not None,
                  read_after_conflict=first_end('head', refused) is not None,
                  history_after_conflict=first_end('history', refused) is not None)
    metrics = traffic(directory, {}, None)
    metrics.pop('direct_historical_render_observed')
    metrics.update(stderr_bytes=stderr_bytes, first_receipt_response_seconds=None if lookup is None else (lookup-started_ns)/1e9)
    return checks, metrics


def native_read(executable, workspace, command, **arguments):
    run = subprocess.run([str(executable), '--workspace', str(workspace)], cwd=workspace,
                         input=canonical(dict(command=command, **arguments)), capture_output=True, timeout=60)
    answer = strict_json(run.stdout)
    require(run.returncode == 0 and not run.stderr and answer['ok'] is True, 'Native judge could not read ' + command)
    return answer['result']


def exact_file(path, expected):
    try:
        return canonical(read_json(path)) == canonical(expected)
    except (OSError, ValueError, RuntimeError):
        return False


def durable_checks(workspace, engine, executable, original):
    key = {'session_id' if engine == 'inkbolt' else 'project_id': 'study'}
    operations = [
        ('saved_receipt', 'session.receipt', dict(request_id='create'),
         lambda result: receipt(engine, result) == receipt(engine, original)),
        ('saved_head', 'session.read' if engine == 'inkbolt' else 'session.get', {},
         lambda result: matches_head(engine, result, original)),
        ('single_creation', 'session.history', dict(limit=2),
         lambda result: matches_history(engine, result, original)),
    ]
    checks, errors = {}, {}
    # A native open can recover a database journal. Reopen a separate copy so a
    # damaged or missing project still produces a score and the capture stays intact.
    with tempfile.TemporaryDirectory() as directory:
        copy = Path(directory) / 'workspace'
        shutil.copytree(workspace, copy)
        for name, command, options, matches in operations:
            try:
                checks[name] = matches(native_read(executable, copy, command, **key, **options))
            except (RuntimeError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
                checks[name] = False
                errors[name] = str(error)
    return checks, errors


def judge(root, engine, n, method, paths):
    workspace = root / 'workspace'
    starter = creation(engine, 192)
    fixtures = {'create-request.json': sha((json.dumps(starter, indent=2) + '\n').encode())}
    contract, files, execution, usage, _, shell = capture_conditions(
        root, engine, n, method, fixtures, (), extra_evidence=('withheld-response.json',))
    original = read_json(root / 'evidence' / 'withheld-response.json')
    require(original.get('ok') is True and isinstance(original.get('result'), dict), 'Missing accepted initial creation')
    original = original['result']
    expected_receipt = receipt(engine, original)
    require(expected_receipt['revision'] == 0 and expected_receipt['action'] == 'create' and expected_receipt['request_id'] == 'create',
            'Withheld reply is not the original creation')
    checks, cli = recorded_recovery(workspace / '.trial-tools/traffic', engine, original, execution['started_unix_ns'])
    checks.update(original_request=files.get('create-request.json') == contract['fixtures']['create-request.json'],
                  receipt_file=exact_file(workspace / 'receipt.json', expected_receipt),
                  head_file=exact_file(workspace / 'head.json', dict(id='study', revision=0, width=192, height=108, history_entries=1)))
    durable, errors = durable_checks(workspace, engine, paths[engine], original)
    checks.update(durable)
    require(workspace_files(workspace) == files, 'Judging changed captured workspace files')
    return dict(engine=engine, repetition=n, passed=all(checks.values()) and execution['status'] == 'passed',
                checks=checks, read_errors=errors, execution=execution, client=usage, shell=shell, cli=cli)


if __name__ == '__main__':
    raise SystemExit(run_judge('receipt-recovery-v1', (), judge, Path(__file__),
                               ('compare_session_recovery.py', 'placed_still_judge.py')))
