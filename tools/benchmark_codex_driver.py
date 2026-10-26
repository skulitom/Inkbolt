"""Adapt a pinned local Codex CLI to the external benchmark protocol.

The caller supplies every model choice. Run through the benchmark harness so
its owned process tree and deadline cover the client and all of its children.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


MAX_METADATA = 1024 * 1024
MAX_TRANSCRIPT = 64 * 1024 * 1024
MAX_EVENT = 8 * 1024 * 1024
MCP_APPROVAL_MODES = ('auto', 'prompt', 'writes', 'approve')
DISABLED_FEATURES = ('apps', 'plugins', 'remote_plugin', 'browser_use',
    'browser_use_external', 'computer_use', 'image_generation', 'multi_agent',
    'memories', 'goals', 'skill_search')
POLICY = (
    'Complete the supplied task autonomously within the workspace. Preserve all '
    'original inputs and create new output files. Use only the supplied tools '
    'and local shell/file/image inspection. Do not use other engines, clients, '
    'models, plugins, skills, web access or delegation. Do not read the project '
    'repository, other trials, harness evidence or judge/reference implementations. '
    'Do not inspect credentials, authentication files or environment secrets. '
    'Use runtime discovery from the supplied engine when needed. The harness '
    'will independently judge delivered files; do not write verdicts, usage '
    'estimates or driver metadata. Finish with a brief account of delivery or failure.'
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    def invalid(_):
        raise ValueError('Nonfinite JSON value')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def regular(path, limit=MAX_METADATA):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= limit,
            'Missing, linked or oversized input')
    return path.read_bytes()


def file_digest(path, limit):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= limit,
            'Missing, linked or oversized input')
    result = hashlib.sha256(); total = 0
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            total += len(chunk)
            require(total <= limit, 'Input grew beyond its bound')
            result.update(chunk)
    return result.hexdigest()


def bridge_directory(request, workspace):
    """Allow the owned file channel without granting the evidence directory."""
    contract=request['contract']
    expected={'B19':'recovery_bridge','B20':'handoff_bridge'}.get(contract['task'])
    supplied=[key for key in ('recovery_bridge','handoff_bridge') if request.get(key) is not None]
    if expected is None:
        require(not supplied,'Unexpected bridge for this task')
        return None
    require(supplied==[expected] and (contract['task']!='B19' or contract['arm']=='model') and
            not request.get('engine_executable') and not request.get('mcp_config'),
            'Expected only the measured task bridge')
    bridge=request[expected]
    require(isinstance(bridge,list) and len(bridge)==3 and
            all(isinstance(arg,str) and arg for arg in bridge),'Invalid bridge argv')
    evidence=workspace.parent/'evidence';channel=evidence/'control-channel'
    require(Path(request['transcript_directory']).resolve()==evidence and evidence.is_dir() and
            not evidence.is_symlink() and evidence.resolve()==evidence,
            'Unexpected or linked bridge evidence directory')
    supplied_channel=Path(bridge[-1])
    require(supplied_channel.is_absolute() and supplied_channel.resolve()==channel and
            channel.is_dir() and not channel.is_symlink() and channel.resolve()==channel,
            'Expected the owned, unlinked control-channel directory')
    return channel


def prepare(request, executable, mcp_approval_mode=None, mcp_tools='core'):
    require(mcp_tools in ('core', 'essentials'), 'Unknown MCP catalog')
    require(mcp_approval_mode is None or mcp_approval_mode in MCP_APPROVAL_MODES,
            'Unknown MCP approval mode')
    contract = request['contract']
    require(request['schema_version'] == contract['schema_version'] == 1 and
            digest(canonical(contract)) == request['contract_sha256'], 'Invalid request identity')
    require(contract['kind'] in ('model', 'synthetic') and contract['client']['id'] == 'codex-cli',
            'Expected an explicitly declared Codex CLI client')
    model = contract['model']; settings = model['settings']
    require(isinstance(model['id'], str) and model['id'].strip() and not model['id'].startswith('-'),
            'Supply a nonempty model id; there is no default or fallback')
    require(set(settings) == {'reasoning_effort'} and isinstance(settings['reasoning_effort'], str)
            and settings['reasoning_effort'].strip(), 'Supply exactly reasoning_effort in model settings')
    workspace = Path(request['workspace']).resolve()
    require(workspace.is_dir(), 'Missing workspace')
    prompt_path = Path(request['prompt_path'])
    require(prompt_path.resolve().is_relative_to(workspace), 'Prompt escapes workspace')
    raw = regular(prompt_path)
    require(digest(raw) == contract['prompt_sha256'], 'Prompt hash differs')
    variant = contract.get('benchmark_variant', 'standard')
    require(variant == 'standard' or (variant == 'photo-50mp-v1' and contract['task'] == 'B10'),
            'Unknown benchmark variant or task')
    for name, expected in contract['fixtures'].items():
        path = workspace / name
        limit = (8192 * 6144 * 8 + 1024 * 1024) if variant == 'photo-50mp-v1' and name == 'original.tiff' else 128 * 1024 * 1024
        require(path.resolve().is_relative_to(workspace) and file_digest(path, limit) == expected,
                'Fixture identity differs')
    require(Path(executable).is_absolute() and Path(executable).is_file(), 'Supply an absolute client executable')
    require(contract['arm'] in ('model', 'baseline'), 'Unknown benchmark arm')
    if contract['arm'] == 'baseline':
        require(not request.get('engine_executable') and not request.get('mcp_config') and
                contract['engine_sha256'] is None and request.get('baseline_tools'),
                'Baseline must not expose Inkbolt')
    argv = [str(executable), 'exec', '--json', '--ephemeral', '--ignore-user-config',
            '--skip-git-repo-check', '--sandbox', 'workspace-write', '--cd', str(workspace),
            '--model', model['id'], '--color', 'never']
    channel=bridge_directory(request,workspace)
    if channel is not None:
        argv += ['--add-dir',str(channel)]
    overrides = dict(approval_policy='never', model_reasoning_effort=settings['reasoning_effort'],
        project_doc_max_bytes=0, web_search='disabled')
    if os.name == 'nt':
        # Ignoring user configuration also removes its native sandbox choice.
        # Require the provisioned sandbox; never fall back to unsandboxed exec.
        overrides['windows.sandbox'] = 'elevated'
    for key, value in overrides.items():
        argv += ['--config', key + '=' + json.dumps(value)]
    for name in DISABLED_FEATURES:
        argv += ['--disable', name]
    argv += ['--enable', 'skip_host_skill_discovery']
    if request.get('mcp_config'):
        mcp = strict_json(regular(request['mcp_config']))
        require(set(mcp) == {'mcpServers'} and set(mcp['mcpServers']) == {'inkbolt'},
                'Unexpected MCP server')
        server = mcp['mcpServers']['inkbolt']
        require(server == dict(command=request['engine_executable'],
                args=['--workspace', str(workspace), 'mcp', '--tools', 'core']), 'Unexpected MCP configuration')
        require(file_digest(server['command'], 512*1024*1024) == contract['engine_sha256'],
                'Engine executable identity differs')
        # The harness always supplies the pinned core launch. An explicit
        # evaluation setting changes discovery only, after identity validation.
        server_args = [*server['args'][:-1], mcp_tools]
        for key, value in dict(command=server['command'], args=server_args, required=True).items():
            argv += ['--config', 'mcp_servers.inkbolt.' + key + '=' + json.dumps(value)]
        if mcp_approval_mode is not None:
            argv += ['--config', 'mcp_servers.inkbolt.default_tools_approval_mode=' + json.dumps(mcp_approval_mode)]
    # B19/B20 supply only their measured bridge instead of a direct engine.
    tools = {key: request[key] for key in ('tool_policy', 'baseline_tools',
             'engine_executable', 'recovery_bridge', 'handoff_bridge') if request.get(key) is not None}
    tools['arm'] = contract['arm']
    prompt = POLICY + '\n\nAvailable tools and arm:\n' + json.dumps(tools, indent=2) + '\n\n' + raw.decode('utf-8')
    return argv + ['-'], prompt, workspace


def observed_usage(events):
    started = [e for e in events if e.get('type') == 'turn.started']
    completed = [e for e in events if e.get('type') == 'turn.completed']
    require(len(started) == len(completed) == 1 and
            not any(e.get('type') in ('turn.failed', 'error') for e in events),
            'Client did not complete exactly one successful turn')
    usage = completed[0].get('usage')
    if usage is None:
        return None
    require(isinstance(usage, dict), 'Malformed token usage')
    result = {}
    for source, target in (('input_tokens','input_tokens'), ('output_tokens','output_tokens'),
                           ('cached_input_tokens','cached_input_tokens'), ('reasoning_output_tokens','reasoning_tokens')):
        if source in usage:
            require(type(usage[source]) is int and usage[source] >= 0, 'Malformed token count')
            result[target] = usage[source]
    return result or None


def run(request_path, executable, mcp_approval_mode=None, mcp_tools='core'):
    request = strict_json(regular(request_path)); contract = request['contract']
    argv, prompt, workspace = prepare(request, executable, mcp_approval_mode, mcp_tools)
    options = dict(creationflags=subprocess.CREATE_NO_WINDOW) if os.name == 'nt' else {}
    version = subprocess.run([str(executable), '--version'], stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, timeout=15, check=True, **options).stdout.decode('utf-8').strip()
    require(version == 'codex-cli ' + contract['client']['version'], 'Client version differs from configuration')
    evidence = Path(request['transcript_directory']).resolve()
    result_path = Path(request['result_path'])
    require(evidence.is_dir() and result_path.resolve() == evidence/'driver-result.json', 'Unexpected result path')
    require(not result_path.exists(), 'Driver result already exists')
    transcript = evidence/'codex-events.jsonl'
    events = []; size = 0; started = time.perf_counter()
    with transcript.open('xb') as stream, tempfile.TemporaryFile() as solver_input:
        header = canonical(dict(type='inkbolt.client_request', contract_sha256=request['contract_sha256'],
            client=contract['client'], model=contract['model'], kind=contract['kind'], argv=argv, prompt=prompt)) + b'\n'
        stream.write(header); size += len(header)
        # A file avoids a write/read pipe deadlock if client startup emits a
        # full stdout buffer before accepting a large task prompt.
        solver_input.write(prompt.encode('utf-8')); solver_input.seek(0)
        with subprocess.Popen(argv, cwd=workspace, stdin=solver_input, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, **options) as child:
            try:
                while True:
                    line = child.stdout.readline(MAX_EVENT + 1)
                    if not line:
                        break
                    size += len(line)
                    require(len(line) <= MAX_EVENT and size <= MAX_TRANSCRIPT, 'Client transcript exceeds its bound')
                    stream.write(line); stream.flush()
                    event = strict_json(line)
                    require(isinstance(event, dict) and isinstance(event.get('type'), str), 'Malformed client event')
                    # Retain raw events on disk; only small completion metadata in memory.
                    if event['type'] in ('turn.started', 'turn.completed', 'turn.failed', 'error'):
                        events.append(event)
                require(child.wait() == 0, 'Client process failed; inspect retained JSON events')
            except BaseException:
                child.kill(); child.wait()
                raise
    usage = observed_usage(events)
    result = dict(schema_version=1, contract_sha256=request['contract_sha256'],
        kind=contract['kind'], client=contract['client'], model=contract['model'],
        transcript=transcript.name, observations=dict(source='client_reported',
            token_usage=usage, model_calls=None, agent_seconds=time.perf_counter()-started))
    with result_path.open('xb') as stream:
        stream.write(canonical(result) + b'\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client-executable', required=True, type=Path)
    parser.add_argument('--mcp-approval-mode', choices=MCP_APPROVAL_MODES,
                        help='Explicit approval policy for the supplied Inkbolt server only; omitted keeps client defaults')
    parser.add_argument('--mcp-tools', choices=('core', 'essentials'), default='core',
                        help='Explicit evaluation catalog; both arms must use the same driver configuration')
    parser.add_argument('request', type=Path)
    args = parser.parse_args(argv)
    try:
        run(args.request, args.client_executable, args.mcp_approval_mode, args.mcp_tools)
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        print(type(error).__name__ + ': ' + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
