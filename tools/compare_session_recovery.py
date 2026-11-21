"""Compare a scripted lost-response recovery on explicit local Inkbolt and Cutbolt binaries."""
import argparse
from contextlib import closing
import os
from pathlib import Path
import platform
import time

from benchmark_runtime import Mcp, Trial, require
from workload_cases import save_json, sha


def connect(client, engine):
    response, _ = client.request('initialize', 'initialize', {
        'protocolVersion': '2025-11-25', 'capabilities': {},
        'clientInfo': {'name': 'session-recovery-comparison', 'version': '1'},
    })
    require(response['protocolVersion'] == '2025-11-25' and response['serverInfo']['name'] == engine,
            'Server identity or negotiated protocol differs')
    client.request('initialized', 'notifications/initialized', notification=True)
    return response['serverInfo']


def catalog(executable, engine, mode, root):
    trace = Trial(executable, root, 'catalog', 1, 'mcp', ())
    with closing(Mcp(trace, catalog=mode)) as client:
        server = connect(client, engine)
        names, cursors, sizes = set(), set(), []
        params = {}
        for page in range(128):
            result, row = client.request(f'page-{page}', 'tools/list', params)
            sizes.append(row['response_bytes'])
            for tool in result['tools']:
                require(tool['name'] not in names, 'Tool occurs twice in the catalog')
                names.add(tool['name'])
            if 'nextCursor' not in result:
                break
            cursor = result['nextCursor']
            require(isinstance(cursor, str) and cursor and cursor not in cursors, 'Invalid catalog cursor')
            cursors.add(cursor)
            params = {'cursor': cursor}
        else:
            raise ValueError('Catalog exceeds the page limit')
    require(names and (mode != 'core' or engine + '_run' in names), 'Incomplete catalog')
    return dict(status='passed', server=server, tools=len(names), pages=len(sizes), first_page_bytes=sizes[0],
                catalog_response_bytes=sum(sizes), server_memory=trace.server_memory, protocol=trace.protocol)


def create_arguments(engine, width):
    if engine == 'cutbolt':
        return dict(id='study', request_id='create', width=width, height=108, frame_rate=dict(num=25, den=1))
    document = dict(schema_version=2, id='study', kind='vector', color_space='srgb',
                    width=width, height=108, items=[])
    return dict(session_id='study', request_id='create', document=document)


def call(client, engine, step, command, arguments, expected_error=None):
    result, _ = client.request(step, 'tools/call', dict(
        name=engine + '_run', arguments=dict(command=command, arguments=arguments)))
    envelope = result['structuredContent']
    if expected_error:
        require(result['isError'] and envelope['ok'] is False and envelope['error']['code'] == expected_error,
                f'{step} did not refuse the changed request with {expected_error}')
        return envelope['error']['code']
    require(not result['isError'] and envelope['ok'] is True, f'{step} failed: {envelope.get("error")}')
    return envelope['result']


def judge(engine, original, found, retry, current, history):
    if engine == 'inkbolt':
        receipt = original['receipt']
        require(original['replayed'] is False and found['replayed'] is True and retry['replayed'] is True
                and found['receipt'] == retry['receipt'] == receipt, 'Saved Inkbolt receipt changed')
        require(all(row['session_id'] == 'study' and row['current_revision'] == 0
                    for row in (original, found, retry, current, history)), 'Unexpected saved session or revision')
        snapshot = current['document']
        require(original['document'] == found['document'] == retry['document'] == snapshot
                and snapshot['items'] == [] and snapshot['kind'] == 'vector'
                and receipt['state_sha256'] == current['state_sha256'], 'Saved document changed')
        require(history['entries'] == [receipt] and history['has_more'] is False, 'Unexpected Inkbolt history')
    else:
        receipt = original
        require(found == retry == receipt and receipt['project_id'] == 'study', 'Saved Cutbolt receipt changed')
        snapshot = current
        require(snapshot['clips'] == [] and snapshot['assets'] == [] and snapshot['frame_rate'] == dict(num=25, den=1),
                'Saved timeline changed')
        require(history['next_before_revision'] is None and len(history['entries']) == 1, 'Unexpected Cutbolt history')
    for entry in (receipt, history['entries'][0]):
        require(entry['request_id'] == 'create' and entry['action'] == 'create' and entry['revision'] == 0,
                'Creation receipt or history identity differs')
    require((snapshot['id'], snapshot['revision'], snapshot['width'], snapshot['height']) == ('study', 0, 192, 108),
            'Saved identity, revision or dimensions changed')


def recover(executable, engine, repetition, root):
    root.mkdir()
    workspace = root / 'workspace'
    workspace.mkdir()
    create = create_arguments(engine, 192)
    first = Trial(executable, root / 'first', 'recovery', repetition, 'mcp', ())
    started = time.perf_counter()
    with closing(Mcp(first, workspace=workspace)) as client:
        connect(client, engine)
        # The recorder waits for commit and retains the reply. Recovery receives only the request.
        original = call(client, engine, 'withheld', 'session.create', create)
    reconnect = Trial(executable, root / 'reconnect', 'recovery', repetition, 'mcp', ())
    key = {'session_id' if engine == 'inkbolt' else 'project_id': 'study'}
    with closing(Mcp(reconnect, workspace=workspace)) as client:
        connect(client, engine)
        found = call(client, engine, 'receipt', 'session.receipt', dict(**key, request_id='create'))
        retry = call(client, engine, 'retry', 'session.create', create)
        refused = call(client, engine, 'changed', 'session.create', create_arguments(engine, 193),
                       'REQUEST_ID_REUSED' if engine == 'inkbolt' else 'REQUEST_ID_CONFLICT')
        current = call(client, engine, 'read', 'session.read' if engine == 'inkbolt' else 'session.get', key)
        history = call(client, engine, 'history', 'session.history', dict(**key, limit=2))
    seconds = time.perf_counter() - started
    judge(engine, original, found, retry, current, history)
    protocol = first.protocol + reconnect.protocol
    calls = [event for event in protocol if event['method'] == 'tools/call']
    return dict(status='passed', changed_request_error=refused, tool_calls=len(calls), seconds=seconds,
                server_memory=dict(first=first.server_memory, reconnect=reconnect.server_memory),
                tool_request_bytes=sum(r['request_bytes'] for r in calls),
                tool_response_bytes=sum(r['response_bytes'] for r in calls), protocol=protocol)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('inkbolt', 'cutbolt'):
        parser.add_argument('--' + name, type=Path, required=True, help='Exact native executable to compare')
    parser.add_argument('--output', type=Path, required=True, help='New directory for workspaces and wire evidence')
    args = parser.parse_args()
    binaries = {name: getattr(args, name).resolve(strict=True) for name in ('inkbolt', 'cutbolt')}
    root = args.output.resolve()
    if root.is_relative_to(Path(__file__).resolve().parents[1]):
        parser.error('Use a new output directory outside the source checkout for raw evidence')
    root.mkdir(parents=True, exist_ok=False)
    identities = {name: sha(path.read_bytes()) for name, path in binaries.items()}
    report = dict(schema_version=1, workflow='empty-session-recovery-v1', model_trials=False,
                  system=platform.system(), machine=platform.machine(), executables=identities,
                  cutbolt_catalog_env_set='CUTBOLT_MCP_TOOLS' in os.environ, catalogs={}, trials=[])
    try:
        for engine, executable in binaries.items():
            choices = (None, 'core', 'essentials') if engine == 'inkbolt' else (None, 'core')
            report['catalogs'][engine] = {}
            for mode in choices:
                label = mode or 'unqualified'
                try:
                    observation = catalog(executable, engine, mode, root / f'{engine}-{label}')
                except (RuntimeError, ValueError, KeyError, OSError) as error:
                    observation = dict(status='failed', error=str(error))
                report['catalogs'][engine][label] = observation
        for repetition in range(1, 6):
            for engine in (binaries if repetition % 2 else reversed(binaries)):
                trial = dict(engine=engine, repetition=repetition)
                report['trials'].append(trial)
                try:
                    trial.update(recover(binaries[engine], engine, repetition, root / f'{engine}-{repetition}'))
                except (RuntimeError, ValueError, KeyError, OSError) as error:
                    trial.update(status='failed', error=str(error))
    finally:
        report['binaries_unchanged'] = all(sha(path.read_bytes()) == identities[name] for name, path in binaries.items())
        save_json(root / 'report.json', report)
    passed = sum(t.get('status') == 'passed' for t in report['trials'])
    print(f'{passed}/10 recovery trials passed. {root / "report.json"}')
    catalogs_ok = all(row['status'] == 'passed' for modes in report['catalogs'].values() for row in modes.values())
    return 0 if passed == 10 and catalogs_ok and report['binaries_unchanged'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
