"""Local, retained CLI/MCP task traffic and explicit independently judged results."""
import base64
import copy
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time

from workload_cases import process_memory, run_process, save, save_json, sha
import linux_process_memory
from mcp_artifacts import restore
from benchmark_tasks import check_class

MAX_RESPONSE = 96*1024*1024


class TaskFailure(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise TaskFailure(message)


def safe_name(name):
    require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,119}', name),
            'Expected a portable benchmark filename or step name')
    return name


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate response key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite response')))


class Mcp:
    """One owned stdio server; background jobs require RecoveryTrial containment."""
    def __init__(self, case):
        self.case = case
        self.rid = 0
        self.closed = False
        self.stderr_path = case.root/'mcp.stderr.log'
        self.stderr = self.stderr_path.open('xb')
        try:
            self.process = case.spawn([str(case.executable), '--workspace', str(case.root),
                'mcp', '--tools', 'core'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=self.stderr, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except BaseException:
            self.stderr.close()
            raise
        self.lines = queue.Queue(maxsize=2)
        self.stop = threading.Event()
        def receive():
            try:
                while not self.stop.is_set():
                    raw = self.process.stdout.readline(MAX_RESPONSE+1)
                    if not raw:
                        self.lines.put_nowait(None)
                        return
                    self.lines.put(raw, timeout=1)
                    if len(raw) > MAX_RESPONSE:
                        return
            except (ValueError, OSError, queue.Full):
                pass
        self.reader = threading.Thread(target=receive, daemon=True)
        self.reader.start()

    def request(self, step, method, params=None, notification=False):
        self.rid += 1
        message = dict(jsonrpc='2.0', method=method)
        if not notification: message['id'] = self.rid
        if params is not None: message['params'] = params
        payload = (json.dumps(message, separators=(',', ':'))+'\n').encode()
        prefix = self.case.prefix(step)
        save(prefix.with_suffix('.request.json'), payload)
        started = time.perf_counter()
        raw = b''
        row = dict(step=step, phase=self.case.phase, transport='mcp', method=method,
                   request_bytes=len(payload), response_bytes=0)
        self.case.protocol.append(row)
        try:
            self.process.stdin.write(payload); self.process.stdin.flush()
            if notification:
                row['status'] = 'notification'
                return None, row
            try: raw = self.lines.get(timeout=self.case.timeout)
            except queue.Empty: raise TaskFailure('MCP response deadline exceeded') from None
            require(raw is not None, 'MCP server exited before its response')
            save(prefix.with_suffix('.response.json'), raw)
            row['response_bytes'] = len(raw)
            require(len(raw) <= MAX_RESPONSE and raw.endswith(b'\n'), 'MCP response exceeds framing bound')
            response = strict_json(raw)
            require(response.get('jsonrpc') == '2.0' and response.get('id') == self.rid,
                    'MCP returned a different response identity')
            require('result' in response and 'error' not in response, 'MCP protocol request failed')
            row['status'] = 'success'
            return response['result'], row
        except BaseException as error:
            row.update(status='failure', error=f'{type(error).__name__}: {error}')
            raise
        finally:
            row['seconds'] = time.perf_counter()-started
            row['completed_from_start_seconds'] = time.perf_counter()-self.case.started

    def initialize(self):
        self.request('initialize', 'initialize', dict(protocolVersion='2025-11-25', capabilities={},
            clientInfo=dict(name='inkbolt-task-benchmark', version='1')))
        self.request('initialized', 'notifications/initialized', notification=True)
        params = {}; catalog = []
        for page in range(128):
            result, _ = self.request(f'catalog-{page}', 'tools/list', params)
            require(isinstance(result.get('tools'), list), 'Missing tool catalog')
            catalog.extend(result['tools'])
            if 'nextCursor' not in result: break
            params = dict(cursor=result['nextCursor'])
        else: raise TaskFailure('Tool catalog exceeds page bound')
        require(len(json.dumps(catalog, separators=(',', ':')).encode()) <= 96*1024,
                'Core catalog exceeds the accepted 96 KiB budget')
        require(any(tool.get('name') == 'inkbolt_run' for tool in catalog), 'Missing dispatcher')

    def close(self):
        if self.closed: return self.case.server_memory
        self.closed = True
        self.stop.set()
        forced = False
        try:
            try: self.process.stdin.close()
            except OSError: pass
            try: self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                forced = True
                self.process.kill(); self.process.wait(timeout=10)
            memory = process_memory(self.process)
            self.case.server_memory = memory
            require(not forced and self.process.returncode == 0 and self.stderr_path.stat().st_size == 0,
                    'MCP server did not close cleanly; retained its stderr')
            return memory
        finally:
            if isinstance(self.process, linux_process_memory.Process):
                self.process.close()
            self.reader.join(timeout=2)
            self.process.stdout.close()
            self.stderr.close()


class Trial:
    def __init__(self, executable, root, task, repetition, transport, required_checks, timeout=90, arm='reference'):
        self.executable = Path(executable) if executable is not None else None
        self.arm = arm
        self.root = Path(root); self.root.mkdir()
        self.task, self.repetition, self.transport = task, repetition, transport
        self.required_checks = tuple(required_checks) + ('source-preservation',)
        self.timeout = timeout
        self.calls, self.protocol, self.checks, self.sources = [], [], [], {}
        self.results = {}
        self.error = None
        self.server = None; self.server_memory = None
        self.first_preview = None
        self.phase = 'setup'
        self.started = time.perf_counter()
        self.agent_started = None
        self.solve_seconds = None
        self.prompt_sha256 = None
        self._prefixes = set()

    def prefix(self, step):
        safe_name(step)
        require(step not in self._prefixes, 'Duplicate benchmark step')
        self._prefixes.add(step)
        return self.root/f'{len(self._prefixes):03d}-{step}'

    def source(self, name, data):
        relative=Path(name)
        require(not relative.is_absolute() and bool(relative.parts), 'Fixture paths must be relative')
        for part in relative.parts: safe_name(part)
        require(name not in self.sources, 'Duplicate fixture source')
        (self.root/relative).parent.mkdir(parents=True,exist_ok=True)
        save(self.root/name, data)
        self.sources[name] = sha(data)
        return str(self.root/name)

    def seed(self, document):
        raw = json.dumps(document, separators=(',', ':')).encode()
        self.source('source.json', raw)
        return dict(file_path='source.json', sha256=sha(raw))

    def begin(self, prompt):
        require(self.agent_started is None, 'Trial already started')
        save(self.root/'task.txt', prompt.encode())
        self.prompt_sha256 = sha(prompt.encode())
        self.agent_started = time.perf_counter()
        self.phase = 'task'
        if self.transport == 'mcp':
            self.server = Mcp(self)
            self.server.initialize()

    def spawn(self, argv, **options):
        if sys.platform == 'linux':
            return linux_process_memory.Process(argv, **options)
        return subprocess.Popen(argv, **options)

    def begin_judging(self):
        require(self.agent_started is not None and self.phase == 'task',
                'Judging must follow a started solve phase')
        self.solve_seconds = time.perf_counter()-self.agent_started
        self.phase = 'judge'

    def verified_preview(self, raw):
        """Match judged image bytes to an observed preview/publication response."""
        for row in self.calls:
            if (row.get('phase') == 'judge' or row['status'] != 'success'
                    or not row['response_observed']):
                continue
            result = self.results.get(row['step'], {}).get('result', {})
            if row['command'] == 'document.preview':
                artifact = result.get('artifact', {})
                if artifact.get('encoding') != 'base64':
                    continue
                try:
                    matches = base64.b64decode(artifact.get('data', ''), validate=True) == raw
                except (ValueError, TypeError):
                    continue
            elif row['command'] in ('document.publish', 'session.publish'):
                matches = (result.get('format') == 'png' and result.get('media_type') == 'image/png'
                           and result.get('bytes') == len(raw) and result.get('sha256') == sha(raw))
            else:
                continue
            if matches:
                elapsed = row['completed_task_seconds']
                self.first_preview = elapsed if self.first_preview is None else min(self.first_preview, elapsed)

    def execute(self, argv, payload):
        return run_process(argv, payload, self.timeout)

    def validate_command(self, command):
        require(not command.startswith('job.'), 'Background jobs require the separate recovery adapter')

    def memory_observations(self):
        memory = [row.get('memory') for row in self.calls if row.get('phase') != 'judge'] if self.transport == 'cli' else [self.server_memory]
        scope = 'individual solve CLI processes' if self.transport == 'cli' else 'complete persistent MCP server lifetime, including judge calls'
        if self.transport == 'mcp' and any('judge_workspace' in row for row in self.calls):
            scope += '; separate judge-workspace CLI processes are excluded'
        return memory, scope

    def extra_results(self):
        return {}

    def call(self, step, command, *, expected_error=None, retry_of=None, discard=False, preview=False, judge_workspace=None, **arguments):
        require(self.agent_started is not None, 'Start the task before making measured calls')
        if judge_workspace is not None:
            from pathlib import Path
            selected = Path(judge_workspace)
            require(self.phase == 'judge' and selected.is_dir() and not selected.is_symlink() and
                selected.resolve().is_relative_to(getattr(self, 'judge_root', self.root).resolve()),
                'A judge workspace must be an owned directory within the judge root')
        # Async jobs need their own containment/worker accounting adapter. Never
        # route one through the synchronous timeout cleanup implemented here.
        self.validate_command(command)
        request = dict(command=command, **arguments)
        fingerprint = sha(json.dumps(request, sort_keys=True, separators=(',', ':')).encode())
        if retry_of is not None:
            prior = [row for row in self.calls if row['step'] == retry_of]
            require(len(prior) == 1 and prior[0]['request_sha256'] == fingerprint,
                    'A retry must repeat an earlier exact request')
        row = dict(step=step, phase=self.phase, command=command, request_sha256=fingerprint,
                   retry_of=retry_of, response_observed=not discard, expected_error=expected_error)
        if judge_workspace is not None:
            row.update(judge_workspace=str(selected.resolve()), transport='cli')
        self.calls.append(row)
        try:
            if self.transport == 'cli' or judge_workspace is not None:
                prefix = self.prefix(step)
                payload = json.dumps(request, separators=(',', ':')).encode()
                save(prefix.with_suffix('.request.json'), payload)
                metrics, stdout, stderr = self.execute([str(self.executable), '--workspace',
                    str(selected.resolve() if judge_workspace is not None else self.root)], payload)
                save(prefix.with_suffix('.response.json'), stdout)
                save(prefix.with_suffix('.stderr.txt'), stderr)
                row.update(request_bytes=len(payload), response_bytes=len(stdout), **metrics)
                require(not metrics['timed_out'] and not stderr, 'CLI timeout or unexpected stderr')
                require(len(stdout) <= MAX_RESPONSE, 'CLI response exceeds bound')
                envelope = strict_json(stdout)
                require(metrics['exit_code'] == (0 if envelope.get('ok') else 1), 'CLI exit/envelope mismatch')
            else:
                result, wire = self.server.request(step, 'tools/call', dict(name='inkbolt_run',
                    arguments=dict(command=command, arguments=arguments, response_format='preview' if preview else 'json')))
                row.update({key:wire[key] for key in ('request_bytes','response_bytes','seconds')})
                envelope = restore(result)
                require(type(result.get('isError')) is bool and isinstance(envelope, dict)
                        and result['isError'] == (envelope.get('ok') is False), 'MCP envelope mismatch')
            require(isinstance(envelope, dict) and type(envelope.get('ok')) is bool, 'Missing response envelope')
            self.results[step] = copy.deepcopy(envelope)
            if not envelope['ok']:
                row['engine_error'] = envelope.get('error')
            if expected_error is not None:
                require(not envelope['ok'] and envelope.get('error',{}).get('code') == expected_error,
                        'Expected diagnostic did not occur')
                row.update(status='expected_error', error=envelope['error'])
                return envelope['error']
            if not envelope['ok']:
                raise TaskFailure('Unexpected engine error: '+str(envelope.get('error')))
            require(isinstance(envelope.get('result'), dict), 'Missing engine result object')
            row.update(status='response_lost' if discard else 'success',
                       replayed=bool(envelope['result'].get('replayed', False)))
            return None if discard else envelope['result']
        except BaseException as error:
            row.update(status='failure', error=f'{type(error).__name__}: {error}')
            raise
        finally:
            row['completed_task_seconds'] = time.perf_counter()-self.agent_started

    def check(self, name, predicate, preview_step=None):
        require(name in self.required_checks, 'Undeclared correctness check: '+name)
        require(not any(check['name'] == name for check in self.checks), 'Duplicate correctness check')
        try:
            value = predicate()
            require(value is not False, 'Oracle returned false')
            self.checks.append(dict(name=name, status='pass', check_class=check_class(self.task,name)))
            if preview_step is not None and self.first_preview is None:
                rows = [row for row in self.calls if row['step'] == preview_step]
                require(len(rows) == 1 and rows[0]['status'] == 'success', 'Preview must identify a successful observed response')
                self.first_preview = rows[0]['completed_task_seconds']
            return True
        except Exception as error:
            # Replace a just-added pass if preview provenance itself was invalid.
            self.checks = [check for check in self.checks if check['name'] != name]
            self.checks.append(dict(name=name, status='fail', check_class=check_class(self.task,name), error=f'{type(error).__name__}: {error}'))
            return False

    def not_applicable(self, name, reason):
        require(self.arm == 'baseline' and name in self.required_checks and check_class(self.task,name) == 'engine',
                'Only baseline engine checks can be not applicable')
        require(reason and not any(row['name'] == name for row in self.checks), 'Missing reason or duplicate check')
        self.checks.append(dict(name=name,status='not_applicable',check_class='engine',reason=reason))

    def has_solve_evidence(self):
        return any(row.get('phase') != 'judge' for row in self.calls)

    def calls_succeeded(self):
        return all(row['status'] in ('success','expected_error','response_lost') for row in self.calls)

    def close(self):
        if self.server is not None:
            try: self.server.close()
            except Exception as error: self.error = self.error or f'{type(error).__name__}: {error}'

    def finish(self):
        self.close()
        self.check('source-preservation', lambda: require(all(
            sha((self.root/name).read_bytes()) == expected for name,expected in self.sources.items()) and
            (self.prompt_sha256 is None or sha((self.root/'task.txt').read_bytes()) == self.prompt_sha256),
            'An original fixture source or task prompt changed'))
        names = {check['name'] for check in self.checks}
        missing = [name for name in self.required_checks if name not in names]
        complete = not missing and all(check['status'] == 'pass' or (self.arm == 'baseline' and
            check['status'] == 'not_applicable' and check_class(self.task,check['name']) == 'engine') for check in self.checks)
        solve_calls = [row for row in self.calls if row.get('phase') != 'judge']
        success = complete and self.has_solve_evidence() and not self.error and self.calls_succeeded()
        memory, memory_scope = self.memory_observations()
        memory_complete = bool(memory) and all(m and m.get('available') for m in memory)
        memory_values = [m for m in memory if m and m.get('available')]
        traffic = self.calls if self.transport == 'cli' else self.protocol
        if self.transport == 'mcp':
            # Independent publication probes use their own workspace/process;
            # count their retained wire bytes once, exclusively as judge work.
            traffic = traffic + [row for row in self.calls if 'judge_workspace' in row]
        judge_traffic = [row for row in traffic if row.get('phase') == 'judge']
        traffic = [row for row in traffic if row.get('phase') != 'judge']
        def invalid(row):
            error=row.get('engine_error') or row.get('error')
            return isinstance(error,dict) and error.get('code') in ('INVALID_JSON','INVALID_REQUEST')
        result = dict(schema_version=2, task=self.task, repetition=self.repetition, transport=self.transport, arm=self.arm,
            prompt_sha256=self.prompt_sha256,
            status='passed' if success else 'failed', error=self.error, required_checks=list(self.required_checks),
            missing_checks=missing, checks=self.checks, calls=self.calls, protocol=self.protocol,
            sources=self.sources, process_calls=len(solve_calls) if self.transport == 'cli' else int(self.server is not None),
            engine_commands=len(solve_calls), protocol_requests=sum(row.get('phase') != 'judge' for row in self.protocol),
            retries=sum(row['retry_of'] is not None for row in solve_calls),
            replayed_receipts=sum(row.get('replayed',False) for row in solve_calls),
            expected_errors=sum(row['status']=='expected_error' for row in solve_calls),
            invalid_calls=sum(invalid(row) for row in solve_calls),
            request_bytes=sum(row.get('request_bytes',0) for row in traffic),
            response_bytes=sum(row.get('response_bytes',0) for row in traffic),
            engine_roundtrip_seconds=sum(row.get('seconds',0) for row in traffic),
            scripted_wall_seconds=self.solve_seconds if self.solve_seconds is not None else
                None if self.agent_started is None else time.perf_counter()-self.agent_started,
            judge_separated=self.solve_seconds is not None,
            judge_engine_commands=len(self.calls)-len(solve_calls),
            judge_request_bytes=sum(row.get('request_bytes',0) for row in judge_traffic),
            judge_response_bytes=sum(row.get('response_bytes',0) for row in judge_traffic),
            judge_roundtrip_seconds=sum(row.get('seconds',0) for row in judge_traffic),
            first_verified_preview_seconds=self.first_preview,
            memory_complete=memory_complete, memory_scope=memory_scope,
            server_memory=self.server_memory if self.transport == 'mcp' else None,
            **linux_process_memory.resident_summary(memory),
            peak_working_set_bytes=max(m['peak_working_set_bytes'] for m in memory_values) if memory_complete else None,
            peak_commit_bytes=max(m['peak_commit_bytes'] for m in memory_values) if memory_complete else None,
            token_usage=None,model_calls=None,agent_seconds=None,model_trials=False)
        result.update(self.extra_results())
        save_json(getattr(self,'result_path',self.root/'result.json'),result)
        return result
