"""Independently reopen and score retained model placements without running the model again."""
import argparse
from pathlib import Path

from benchmark_driver import canonical, observations, read_json, transcript, workspace_files
from benchmark_codex_driver import observed_usage
from benchmark_runtime import require, strict_json, TaskFailure
from compare_placed_still import BADGE_HEIGHT, BADGE_WIDTH, HEIGHT, PREVIEWS, WIDTH, artwork, file_sha
from placed_still_judge import score, traffic
from workload_cases import ROOT, png, save_json, sha


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
                                oracle_sha256={name: file_sha(Path(__file__).with_name(name)) for name in
                                               ('placed_still_judge.py', 'compare_placed_still.py')},
                                method=method, trials=rows))
    for engine in ('inkbolt', 'cutbolt'):
        count = sum(r['passed'] for r in rows if r['engine'] == engine)
        print(f'{engine}: {count}/{method["pairs"]} complete workflows')
    return 1 if any('evidence_error' in row for row in rows) else 0


if __name__ == '__main__':
    raise SystemExit(main())
