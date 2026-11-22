"""Independently reopen and score retained model placements without running the model again."""
import argparse
import base64
from collections import Counter
import os
from pathlib import Path
import subprocess
import tempfile

from benchmark_driver import canonical, observations, read_json, transcript, workspace_files
from benchmark_codex_driver import observed_usage
from benchmark_runtime import require, strict_json, TaskFailure
from compare_placed_still import AFTER, BEFORE, BADGE_HEIGHT, BADGE_WIDTH, HEIGHT, WIDTH, artwork, expected, file_sha, preview_rgba
from run_placed_still_models import PREVIEWS
from workload_cases import ROOT, png, save, save_json, sha


def codex_observations(log, contract, checksum, reported_tokens):
    with log.open('rb') as stream:
        header = strict_json(stream.readline())
        require(header.get('type') == 'inkbolt.client_request' and header.get('contract_sha256') == checksum
                and header.get('model') == contract['model'] and header.get('client') == contract['client'],
                'Codex transcript belongs to a different request')
        turns = []
        shells = set()
        failed, output_bytes = 0, 0
        for line in stream:
            event = strict_json(line)
            if event['type'] in ('turn.started', 'turn.completed', 'turn.failed', 'error'):
                turns.append(event)
            item = event.get('item', {})
            if event['type'] == 'item.completed' and item.get('type') == 'command_execution':
                require(item['id'] not in shells, 'Duplicate completed shell event')
                shells.add(item['id'])
                failed += item.get('exit_code') != 0
                output_bytes += len(item['aggregated_output'].encode('utf-8'))
    require(observed_usage(turns) == reported_tokens, 'Token usage differs from the recorded client turn')
    return dict(completed_commands=len(shells), nonzero_exit_commands=failed, observed_stdout_stderr_bytes=output_bytes)


def traffic(directory, revisions, historical_sha256):
    commands, failures, response_sizes = Counter(), Counter(), Counter()
    valid, duplicate, unfinished, input_bytes, output_bytes = set(), 0, 0, 0, 0
    moved_commits, historical_renders = [], []
    for entry in directory.iterdir():
        launch = read_json(entry / 'launch.json')
        payload = (entry / 'input').read_bytes()
        try:
            request = strict_json(payload)
        except (ValueError, UnicodeError):
            request = None
        command = request.get('command') if isinstance(request, dict) else None
        label = command if isinstance(command, str) else ('--help' if '--help' in launch['argv'] else '(other CLI)')
        commands[label] += 1
        key = canonical(request) if command else canonical([launch['argv'], sha(payload)])
        if key in valid:
            duplicate += 1
        valid.add(key)
        input_bytes += len(payload)
        if not (entry / 'exit.json').is_file():
            unfinished += 1
            continue
        raw = (entry / 'stdout').read_bytes()
        output_bytes += len(raw)
        response_sizes[label] += len(raw)
        exited = read_json(entry / 'exit.json')
        if exited['code'] != 0:
            failures[label] += 1
            continue
        if not revisions or not isinstance(request, dict):
            continue
        if label in ('session.apply', 'session.apply_proposal', 'session.undo', 'session.redo'):
            receipt = strict_json(raw).get('result', {})
            if receipt.get('session_id', receipt.get('project_id')) == 'placement' and receipt.get(
                    'current_revision', receipt.get('revision')) == revisions['moved_revision']:
                moved_commits.append(exited['finished_ns'])
        if label in ('document.export', 'document.preview', 'document.publish', 'session.publish', 'preview.frame'):
            ref = request.get('document', request.get('project', request))
            if not isinstance(ref, dict) or ref.get('revision') != revisions['original_revision'] or ref.get(
                    'session_id', ref.get('project_id')) != 'placement':
                continue
            result = strict_json(raw).get('result', {})
            artifact = result.get('artifact', result)
            digest = artifact.get('sha256')
            if artifact.get('encoding') == 'base64':
                digest = sha(base64.b64decode(artifact['data'], validate=True))
            if historical_sha256 and digest == historical_sha256:
                historical_renders.append(launch['started_ns'])
    return dict(calls=sum(commands.values()), commands=dict(commands), failed_commands=dict(failures),
                unfinished=unfinished, repeated_requests=duplicate, input_bytes=input_bytes, stdout_bytes=output_bytes,
                stdout_bytes_by_command=dict(response_sizes), direct_historical_render_observed=any(
                    start >= end for end in moved_commits for start in historical_renders))


def engine_result(workspace, engine, paths, request):
    env = dict(os.environ, CUTBOLT_FFMPEG=str(paths['ffmpeg']), CUTBOLT_FFPROBE=str(paths['ffprobe']))
    response = subprocess.run([str(paths[engine]), '--workspace', str(workspace)], input=canonical(request),
                              cwd=workspace, capture_output=True, timeout=60, env=env)
    value = strict_json(response.stdout)
    require(response.returncode == 0 and value.get('ok') is True,
            f'{request["command"]} could not reopen the saved work: {value.get("error", {})}')
    return value['result']


def native_preview(workspace, folder, engine, paths, revision, label):
    reference = {'session_id' if engine == 'inkbolt' else 'project_id': 'placement'}
    if revision is not None:
        reference['revision'] = revision
    elif engine == 'inkbolt':
        current = engine_result(workspace, engine, paths, dict(command='session.read', **reference, response_mode='compact'))
        reference['revision'] = current['current_revision']
    else:
        current = engine_result(workspace, engine, paths, dict(command='session.get', **reference))
        reference = current.get('project', current)
    output = folder / (label + '.png')
    if engine == 'inkbolt':
        request = dict(command='document.preview', document=reference)
    else:
        request = dict(command='preview.frame', project=reference, time=dict(num=0, den=1),
                       output=output.relative_to(workspace).as_posix())
    value = engine_result(workspace, engine, paths, request)
    if engine == 'inkbolt':
        save(output, base64.b64decode(value['artifact']['data'], validate=True))
    return preview_rgba(output, paths['ffmpeg'])


def score(workspace, engine, paths, inputs, samples):
    paper, badge = artwork()
    original = expected(paper, badge, BEFORE)
    moved = expected(paper, badge, AFTER)
    checks, errors, delivered = {}, {}, {}

    def check(name, verify):
        try:
            require(verify(), name + ' differs')
            checks[name] = True
        except (OSError, ValueError, KeyError, TypeError, TaskFailure, subprocess.SubprocessError) as error:
            errors[name] = str(error)
            checks[name] = False

    for filename, pixels in zip(PREVIEWS, (original, moved, original)):
        path = workspace / filename
        check(filename, lambda: preview_rgba(path, paths['ffmpeg']) == pixels)
        if checks[filename]:
            delivered[filename] = file_sha(path)
    check('inputs', lambda: all(file_sha(workspace / name) == inputs[name] for name in ('badge.png', 'paper.png')))
    revisions = {}

    def read_revisions():
        data = read_json(workspace / 'revisions.json')
        for key in ('original_revision', 'moved_revision'):
            require(type(data[key]) is int and data[key] >= 0, 'Expected nonnegative integer revisions')
        require(data['original_revision'] < data['moved_revision'], 'Original must precede moved revision')
        revisions.update({key: data[key] for key in ('original_revision', 'moved_revision')})
        return True

    check('revision_ids', read_revisions)
    # These are new judge-owned outputs. Render in the original workspace so
    # the test exercises the client's saved resource bindings and default store.
    with tempfile.TemporaryDirectory(dir=workspace, prefix='judge-preview-') as temp:
        for label, key, pixels in [('original', 'original_revision', original), ('moved', 'moved_revision', moved),
                                   ('current', None, moved)]:
            check('saved_' + label, lambda: native_preview(workspace, Path(temp), engine, paths,
                                                           revisions[key] if key else None, label) == pixels)
    times = [s['seconds'] for s in samples if s['file'] == 'before.png' and s['sha256'] == delivered.get('before.png')]
    return dict(checks=checks, errors=errors, delivered_sha256=delivered, revisions=revisions,
                first_correct_before_seconds=min(times, default=None),
                artwork_passed=all(checks[key] for key in [*PREVIEWS, 'inputs']), saved_workflow_passed=all(checks.values()))


def judge(root, engine, n, method, paths):
    workspace, evidence = root / 'workspace', root / 'evidence'
    capture = read_json(evidence / 'capture.json')
    contract = capture['contract']
    require(contract['engine'] == engine and contract['repetition'] == n and contract['task'] == method['workflow']
            and contract['engine_sha256'] == method['binaries'][engine] and contract['model'] == method['model']
            and contract['client'] == method['client'] and contract['prompt_sha256'] == method['prompt_sha256']
            and capture['driver'] == method['driver'] and sha(canonical(contract)) == capture['contract_sha256'],
            'Trial identity differs from registered conditions')
    files = workspace_files(workspace)
    require(files == capture['files'], 'Retained workspace differs from capture')
    for name, digest in capture['evidence_files'].items():
        require(Path(name).name == name and file_sha(evidence / name) == digest, 'Retained evidence differs')
    request = read_json(evidence / 'request.json')
    require(request['contract'] == contract and request['contract_sha256'] == capture['contract_sha256']
            and file_sha(workspace / '.trial-tools/engine.py') == method['recorder_sha256']
            and all(files.get(key) == capture['inputs'][key] for key in ('.trial-tools/launch.json', 'task.txt'))
            and contract['fixtures'] == {name: capture['inputs'][name] for name in ('paper.png', 'badge.png')},
            'Original trial conditions differ')
    paper, badge = artwork()
    require(contract['fixtures'] == {'paper.png': sha(png(WIDTH, HEIGHT, paper)),
                                     'badge.png': sha(png(BADGE_WIDTH, BADGE_HEIGHT, badge))},
            'Trial fixtures differ from the registered placement artwork')
    execution = read_json(evidence / 'execution.json')
    usage, samples, shell = {}, [], None
    if execution['status'] == 'passed':
        result = read_json(evidence / 'driver-result.json')
        require(result['kind'] == 'model' and result['client'] == contract['client'] and result['model'] == contract['model']
                and result['contract_sha256'] == capture['contract_sha256'], 'Client result belongs to another trial')
        log = transcript(evidence, result['transcript'])
        require(file_sha(log) == capture['evidence_files'][log.name], 'Client transcript differs')
        usage = observations(result, PREVIEWS)
        samples = usage.get('completed_event_previews', [])
        if contract['client']['id'] == 'codex-cli':
            shell = codex_observations(log, contract, capture['contract_sha256'], usage['token_usage'])
    row = score(workspace, engine, paths, contract['fixtures'], samples)
    row.update(engine=engine, repetition=n, execution=execution, client=usage, shell=shell, cli=traffic(
        workspace / '.trial-tools/traffic', row['revisions'], row['delivered_sha256'].get('historical.png')))
    require(workspace_files(workspace) == files, 'Judging changed captured workspace files')
    row['passed'] = row['saved_workflow_passed'] and execution['status'] == 'passed' and row['cli']['calls'] > 0
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('inkbolt', 'cutbolt', 'ffmpeg', 'ffprobe', 'capture', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    root = args.capture.resolve(strict=True)
    destination = args.output.resolve()
    if destination.is_relative_to(root) or destination.is_relative_to(ROOT):
        parser.error('Choose a new output file outside the capture and checkout')
    require(not destination.exists(), 'Judgment output already exists')
    paths = {name: getattr(args, name).resolve(strict=True) for name in ('inkbolt', 'cutbolt', 'ffmpeg', 'ffprobe')}
    method = read_json(root / 'method.json')
    require(method['binaries'] == {key: file_sha(path) for key, path in paths.items()}, 'Pinned binaries differ')
    collection = read_json(root / 'collection.json')
    expected = [(n, name) for n in range(1, method['pairs'] + 1)
                for name in (('inkbolt', 'cutbolt') if n % 2 else ('cutbolt', 'inkbolt'))]
    require(collection['executables_unchanged'] and [t['trial'] for t in collection['trials']] ==
            [f'{n:02d}-{name}' for n, name in expected], 'Incomplete or mismatched collection')
    rows = []
    for n, name in expected:
        try:
            row = judge(root / f'{n:02d}-{name}', name, n, method, paths)
        except (TaskFailure, ValueError, OSError, TypeError, KeyError) as error:
            row = dict(engine=name, repetition=n, passed=False, evidence_error=str(error))
        rows.append(row)
    save_json(destination, dict(method_sha256=file_sha(root / 'method.json'), judge_sha256=file_sha(Path(__file__)),
                                method=method, trials=rows))
    for engine in ('inkbolt', 'cutbolt'):
        count = sum(r['passed'] for r in rows if r['engine'] == engine)
        print(f'{engine}: {count}/{method["pairs"]} complete workflows')
    return 1 if any('evidence_error' in row for row in rows) else 0


if __name__ == '__main__':
    raise SystemExit(main())
