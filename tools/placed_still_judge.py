"""Check placed-image pixels, retained revisions and recorded native calls."""
import base64
from collections import Counter
import os
from pathlib import Path
import subprocess
import tempfile

from benchmark_runtime import TaskFailure, canonical, read_json, require, strict_json
from compare_placed_still import AFTER, BEFORE, PREVIEWS, artwork, expected, file_sha, preview_rgba
from workload_cases import save, sha


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
