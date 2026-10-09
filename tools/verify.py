"""Fast, resumable checks; --thorough reruns the complete verification suite.

Quick runs have a 180-second wall-clock budget, reuse only identical passing
inputs, and report unfinished checks with exit 2. They never award feature credit.
Use --only test_name or --rust module::tests for focused implementation feedback.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import unittest
import uuid

# Also support existing callers that load this script by absolute file path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_inputs import digest, environment_identity, fingerprints, snapshot
from verify_process import run

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, '-X', 'utf8']
EXE = ROOT / 'target/debug' / ('inkbolt.exe' if os.name == 'nt' else 'inkbolt')


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def state_directory(root):
    git = subprocess.check_output(['git', 'rev-parse', '--absolute-git-dir'], cwd=root, text=True).strip()
    return Path(git) / 'inkbolt-verify'


class Lease:
    """One verifier per checkout; OS locks are automatically released on death."""
    def __init__(self, path):
        self.file = path.open('a+b')
        self.file.seek(0)
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                self.file.close()
                raise RuntimeError('Another verifier owns this checkout') from None
        else:
            import fcntl
            try:
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self.file.close()
                raise RuntimeError('Another verifier owns this checkout') from None

    def close(self):
        self.file.close()


def load_state(path):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if (data.get('version') == 1 and isinstance(data.get('checks'), dict)
                and all(isinstance(n, str) and isinstance(row, dict) for n, row in data['checks'].items())
                and isinstance(data.get('files', {}), dict)):
            return data
    except (OSError, ValueError, AttributeError):
        pass
    return dict(version=1, checks={})


def reusable(previous, fingerprint):
    return previous.get('status') == 'passed' and previous.get('fingerprint') == fingerprint


def checked_result(row, expected=None, rust=False):
    """A zero exit without complete test accounting is a harness failure."""
    if row['status'] != 'passed':
        return row
    if expected is not None:
        counts = re.findall(r'^Ran (\d+) tests? in ', row['output'], re.MULTILINE)
        if len(counts) != 1 or int(counts[0]) != expected or expected <= 0:
            return dict(row, status='failed', reason=f'Incomplete Python accounting (expected {expected})')
        row['tests'] = expected
    if rust:
        counts = re.findall(r'^test result: ok\. (\d+) passed;', row['output'], re.MULTILINE)
        if not counts or sum(map(int, counts)) == 0:
            return dict(row, status='failed', reason='No passing Rust test evidence')
        row['tests'] = sum(map(int, counts))
    return row


def python_counts(modules):
    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / 'tests'), pattern='test_*.py')
    if loader.errors:
        raise RuntimeError('\n'.join(loader.errors))
    counts = {name: unittest.TestLoader().discover(str(ROOT / 'tests'), pattern=name + '.py').countTestCases() for name in modules}
    if sum(counts.values()) != suite.countTestCases() or any(n <= 0 for n in counts.values()):
        raise RuntimeError('Incomplete Python module discovery')
    return counts


def select(args, modules, history):
    available = set(modules) | {'rust', 'fmt', 'clippy', 'build', 'guard'}
    if args.last_failed:
        names = {n for n, row in history.items() if row.get('status') == 'failed'}
        if not names:
            raise ValueError('No unresolved failures; run the default check to resume pending work')
        unknown = {n for n in names if n not in available and not n.startswith('rust:')}
        if unknown:
            raise ValueError('Failed checks no longer exist: ' + ', '.join(sorted(unknown)))
    elif args.only:
        names = {n.strip().removesuffix('.py') for n in args.only.split(',') if n.strip()}
        unknown = names - available
        if unknown or not names:
            raise ValueError('Unknown or empty checks: ' + ', '.join(sorted(unknown)))
    elif args.rust:
        names = set()
    else:
        names = set(modules) | {'rust'}
    if args.rust:
        names.add('rust:' + args.rust)
    return names


def schedule(names, worker, jobs, deadline, previous, changed):
    """Longest known checks first; failures and edited fixtures have priority."""
    def priority(name):
        old = previous.get(name, {})
        direct = name.startswith('test_') and f'tests/{name}.py' in changed
        seconds = old.get('seconds', 90 if name == 'rust' or name == 'test_jobs' else 5)
        return (old.get('status') != 'failed', not direct, -seconds, name)
    pending = sorted(names, key=priority)
    result = {}
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        running = {}
        while pending or running:
            while pending and len(running) < jobs:
                name = pending.pop(0)
                if deadline is not None and time.monotonic() >= deadline:
                    result[name] = dict(status='deferred', seconds=0, exit_code=None)
                else:
                    running[pool.submit(worker, name)] = name
            if running:
                done, _ = wait(running, return_when=FIRST_COMPLETED)
                for future in done:
                    name = running.pop(future)
                    result[name] = future.result()
                    print(f"{name}: {result[name]['status']} ({result[name]['seconds']:.1f}s)", flush=True)
    return result


def python_checks(jobs):
    """Complete Python-only helper retained for callers and fixture self-tests."""
    modules = sorted(p.stem for p in (ROOT / 'tests').glob('test_*.py'))
    counts = python_counts(modules)
    def worker(name):
        return checked_result(run(PY + ['-m', 'unittest', 'discover', '-s', 'tests', '-p', name + '.py', '-v'], ROOT), counts[name])
    rows = schedule(modules, worker, jobs, None, {}, set())
    failures = [name for name, row in rows.items() if row['status'] != 'passed']
    if failures or sum(row.get('tests', 0) for row in rows.values()) != sum(counts.values()):
        raise RuntimeError('Python verification failed: ' + ', '.join(failures))
    print(f'All {sum(counts.values())} Python tests passed across {len(modules)} isolated modules.')


def execute(args):
    started = time.monotonic()
    deadline = None if args.thorough else started + args.budget
    state = state_directory(ROOT)
    state.mkdir(exist_ok=True)
    lease = Lease(state / 'lock')
    try:
        return verify(args, state, started, deadline)
    finally:
        lease.close()


def verify(args, state, started, deadline):
    print('Planning checks from current file contents and previous results...', flush=True)
    baseline = snapshot(ROOT)
    environment = environment_identity(ROOT)
    modules = sorted(p.stem for p in (ROOT / 'tests').glob('test_*.py'))
    cache = load_state(state / 'state.json')
    history = cache['checks']
    names = select(args, modules, history)
    keys = fingerprints(ROOT, baseline, environment, modules)
    selected = names | {'guard', 'fmt', 'clippy', 'build'}
    excluded = sorted((set(modules) | {'rust'}) - names)
    changed = {p for p in baseline.keys() | cache.get('files', {}).keys() if baseline.get(p) != cache.get('files', {}).get(p)}
    if not cache.get('files'):
        changed = set()  # A first run has no meaningful edit-priority baseline.
    before_exe = file_hash(EXE)
    if args.list:
        for name in sorted(selected):
            fingerprint = keys.get(name, keys['rust'])
            if name.startswith('test_'):
                fingerprint = digest([fingerprint, before_exe])
            if name == 'rust' or name.startswith('rust:'):
                fingerprint = digest([keys['rust'], name])
            old = history.get(name, {})
            status = 'reusable' if not (args.thorough or args.force) and name != 'guard' and reusable(old, fingerprint) else 'run'
            print(f'{status}: {name}')
        print(f'{len(excluded)} checks outside requested scope. No checks executed.')
        return 0
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
    directory = state / 'runs' / run_id
    directory.mkdir(parents=True)
    rows = {}
    retained_engine = None
    counts = None
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    def command(name, argv, fingerprint, expected=None, rust=False, force=False):
        old = history.get(name, {})
        if not (args.thorough or args.force or force) and reusable(old, fingerprint):
            return dict(old, status='reused', seconds=0)
        timeout = None if deadline is None else deadline - time.monotonic()
        try:
            row = checked_result(run(argv, ROOT, timeout, env), expected, rust)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            row = dict(status='failed', seconds=0, exit_code=None, output=str(error), reason='Check launcher failed')
        log = directory / (re.sub(r'[^a-zA-Z0-9_.-]', '_', name)[:80] + '-' + digest(name)[:8] + '.log')
        log.write_text(row.pop('output'), encoding='utf-8')
        row.update(fingerprint=fingerprint, command=argv, log=str(log))
        if row['status'] == 'failed':
            print(log.read_text(encoding='utf-8')[-12000:], flush=True)
        return row
    # The material guard always runs against current bytes. It is never cached.
    for name, argv in [('guard', PY + ['tools/check_repo.py']),
                       ('fmt', ['cargo', 'fmt', '--check']),
                       ('build', ['cargo', 'build', '--locked']),
                       ('clippy', ['cargo', 'clippy', '--locked', '--all-targets', '--', '-D', 'warnings'])]:
        rows[name] = command(name, argv, keys.get(name, digest(baseline)),
                             force=name == 'guard' or (name == 'build' and (before_exe is None or before_exe != cache.get('executable'))))
        print(f"{name}: {rows[name]['status']} ({rows[name]['seconds']:.1f}s)", flush=True)
        if rows[name]['status'] not in ('passed', 'reused'):
            break
    binary = file_hash(EXE)
    if all(rows.get(n, {}).get('status') in ('passed', 'reused') for n in ('guard', 'fmt', 'build', 'clippy')):
        if binary is None:
            raise RuntimeError('Build did not produce the expected debug executable')
        engine_copy = directory / EXE.name
        shutil.copy2(EXE, engine_copy)
        env['INKBOLT_EXE'] = str(engine_copy)
        counts = python_counts(modules)
        def worker(name):
            if name == 'rust' or name.startswith('rust:'):
                argv = ['cargo', 'test', '--locked']
                if name.startswith('rust:'):
                    argv.append(name[5:])
                return command(name, argv, digest([keys['rust'], name]), rust=True)
            return command(name, PY + ['-m', 'unittest', 'discover', '-s', 'tests', '-p', name + '.py', '-v'],
                           digest([keys[name], binary]), expected=counts[name])
        work = names - {'guard', 'fmt', 'clippy', 'build'}
        # Reuse before scheduling: an expired budget must never turn a valid
        # unchanged pass into a deferred check and erase its reusable evidence.
        if not (args.thorough or args.force):
            for name in sorted(work):
                fingerprint = digest([keys['rust'], name]) if name == 'rust' or name.startswith('rust:') else digest([keys[name], binary])
                if reusable(history.get(name, {}), fingerprint):
                    rows[name] = dict(history[name], status='reused', seconds=0)
            reused_count = len(work & rows.keys())
            if reused_count:
                print(f'Reusing {reused_count} checks with identical passing inputs.', flush=True)
            work -= rows.keys()
        rows.update(schedule(work, worker, args.jobs, deadline, history, changed))
        # Job containment has stopped this run's workers; remove only our copy.
        try:
            engine_copy.unlink()
        except PermissionError:
            # A scanner can briefly retain a handle after every owned process
            # exits. Preserve the evidence instead of losing completed passes.
            retained_engine = str(engine_copy)
    for name in selected - rows.keys():
        rows[name] = dict(status='deferred', seconds=0, reason='Prerequisite did not pass')
    stable = snapshot(ROOT) == baseline and file_hash(EXE) == binary and environment_identity(ROOT) == environment
    failures = sorted(n for n, row in rows.items() if row['status'] == 'failed')
    deferred = sorted(n for n, row in rows.items() if row['status'] == 'deferred')
    code = 1 if failures or not stable else 2 if deferred else 0
    report = dict(version=1, mode='thorough' if args.thorough else 'quick', seconds=time.monotonic() - started,
                  budget_seconds=None if args.thorough else args.budget, inputs_unchanged=stable,
                  input_fingerprint=digest(baseline), environment=environment, executable=binary,
                  checks=rows, failed=failures, deferred=deferred, outside_scope=excluded,
                  retained_engine_copy=retained_engine,
                  python_modules_discovered=len(modules), python_tests_discovered=sum(counts.values()) if counts else None,
                  python_tests_executed=sum(row.get('tests', 0) for name, row in rows.items() if name.startswith('test_') and row['status'] == 'passed'),
                  complete_suite=args.thorough and code == 0, exit_code=code)
    report_path = directory / 'report.json'
    report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if args.report:
        output = args.report.resolve()
        if output.is_relative_to(ROOT) and not output.is_relative_to(state):
            raise ValueError('Keep generated reports outside the checkout')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report_path.read_text(encoding='utf-8'), encoding='utf-8')
    # Completed independent stages survive another stage exhausting its budget.
    if stable:
        for name, row in rows.items():
            if row['status'] != 'reused':
                # A failure survives a deferral until the check actually passes.
                if row['status'] != 'deferred' or history.get(name, {}).get('status') != 'failed':
                    history[name] = row
                if name.startswith('rust:') and row['status'] == 'failed':
                    history.pop('rust', None)  # A narrower failure invalidates an older broad pass.
    else:
        history = {}
    updated = dict(version=1, files=baseline if stable else {}, checks=history, executable=binary,
                   latest_report=str(report_path))
    temporary = state / (run_id + '.tmp')
    temporary.write_text(json.dumps(updated, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, state / 'state.json')
    print(f"{report['mode'].capitalize()} check: {sum(r['status'] == 'passed' for r in rows.values())} passed, "
          f"{sum(r['status'] == 'reused' for r in rows.values())} reused, {len(failures)} failed, {len(deferred)} pending, "
          f"{len(excluded)} outside scope; {report['seconds']:.1f}s.\nReport: {report_path}", flush=True)
    if not stable:
        print('Inputs changed during verification; no results accepted.', flush=True)
    if deferred:
        print('Budget/prerequisite left checks pending. Rerun to resume, select --only/--rust, or use --thorough.', flush=True)
    if not args.thorough:
        print('Quick feedback only; use --thorough for milestone or completion evidence.', flush=True)
    return code


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--thorough', action='store_true', help='Rerun every check without cache reuse or the quick budget')
    parser.add_argument('--jobs', type=int, default=min(4, os.cpu_count() or 2), choices=range(1, 9), help='Concurrent stages (default: up to 4; maximum: 8)')
    parser.add_argument('--budget', type=float, default=180, help='Total quick-run seconds, including builds (default: 180)')
    parser.add_argument('--only', help='Comma-separated Python test module names (test_ prefix, no path), or rust')
    parser.add_argument('--rust', help='Run a focused Rust test filter; can combine with --only Python modules')
    parser.add_argument('--last-failed', action='store_true', help='Rerun unresolved failures, preserving unrelated pending checks')
    parser.add_argument('--force', action='store_true', help='Rerun selected quick checks even with identical passing inputs')
    parser.add_argument('--list', action='store_true', help='Explain selection/reuse without executing checks')
    parser.add_argument('--report', type=Path, help='Also write the JSON run report to an external path')
    args = parser.parse_args(argv)
    if args.budget <= 0 or not args.budget < float('inf'):
        parser.error('--budget must be finite and positive')
    if args.thorough and (args.only or args.rust or args.last_failed or args.force or args.budget != 180):
        parser.error('--thorough always runs every check; selection/cache/budget options are quick-only')
    if args.last_failed and (args.only or args.rust):
        parser.error('--last-failed cannot be combined with another selector')
    if args.rust and (not args.rust.strip() or args.rust.startswith('-')):
        parser.error('--rust requires a non-option test filter')
    return args


if __name__ == '__main__':
    try:
        raise SystemExit(execute(parse_args()))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(f'Verification failed: {error}') from error
