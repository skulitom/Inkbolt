"""Verification must be fast without turning missing or stale checks into passes."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import verify
import verify_inputs as inputs
import verify_process as process


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='inkbolt-verify-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def files(self):
        return {p.relative_to(self.root).as_posix(): verify.file_hash(p) for p in self.root.rglob('*') if p.is_file()}

    def test_transitive_helpers_rust_additions_removals_and_environment_invalidate(self):
        self.write('src/lib.rs', 'original')
        self.write('Cargo.lock', 'locked')
        self.write('README.md', 'explanation')
        self.write('tests/test_one.py', 'from helper import value')
        self.write('tests/helper.py', 'from nested import value')
        self.write('tests/nested.py', 'value=1')
        self.write('tests/test_two.py', 'value=1')
        names = ['test_one', 'test_two']
        def keys(env='one'):
            return inputs.fingerprints(self.root, self.files(), env, names)
        before = keys()
        self.write('tests/nested.py', 'value=2')
        after = keys()
        self.assertNotEqual(before['test_one'], after['test_one'])
        self.assertEqual(before['test_two'], after['test_two'])
        self.assertEqual(before['rust'], after['rust'])
        self.write('README.md', 'new explanation')
        self.assertEqual(after, keys())
        self.write('src/added.rs', 'new behavior')
        changed = keys()
        self.assertTrue(all(after[n] != changed[n] for n in after))
        (self.root / 'src/added.rs').unlink()
        self.assertEqual(after, keys())
        self.assertTrue(all(after[n] != keys('different-environment')[n] for n in after))
        (self.root / 'tests/nested.py').unlink()
        self.assertNotEqual(after['test_one'], keys()['test_one'])

    def test_dynamic_imports_unknown_syntax_and_literal_files_fall_back_safely(self):
        self.write('tests/test_one.py', "import importlib\nm=importlib.import_module('dynamic')")
        self.write('tests/dynamic.py', 'value=1')
        self.write('examples/input.json', '{}')
        files = self.files()
        self.assertEqual(inputs.python_closure(self.root, 'tests/test_one.py', files), set(files))
        self.write('tests/test_one.py', "path=ROOT/'examples'/'input.json'")
        self.assertIn('examples/input.json', inputs.python_closure(self.root, 'tests/test_one.py', self.files()))
        self.write('tests/test_one.py', 'invalid Python !')
        self.assertEqual(inputs.python_closure(self.root, 'tests/test_one.py', self.files()), set(self.files()))
        self.write('tools/helper.py', 'value=1')
        self.write('tests/test_one.py', 'from tools.helper import value')
        self.assertIn('tools/helper.py', inputs.python_closure(self.root, 'tests/test_one.py', self.files()))
        self.write('tests/test_one.py', 'import importlib.util\nspec=importlib.util.spec_from_file_location("helper", ROOT/"tools/helper.py")')
        closure = inputs.python_closure(self.root, 'tests/test_one.py', self.files())
        self.assertIn('tools/helper.py', closure)
        self.assertNotIn('examples/input.json', closure)
        self.write('tests/test_one.py', "files=list(store.glob('*.rgba8'))")
        self.assertEqual(inputs.python_closure(self.root, 'tests/test_one.py', self.files()), {'tests/test_one.py'})
        self.write('examples/fixture.rgba8', 'fixture')
        self.assertIn('examples/fixture.rgba8', inputs.python_closure(self.root, 'tests/test_one.py', self.files()))

    def test_failed_deferred_and_different_inputs_never_reuse(self):
        for status in ('failed', 'deferred', 'reused'):
            self.assertFalse(verify.reusable(dict(status=status, fingerprint='same'), 'same'))
        self.assertFalse(verify.reusable(dict(status='passed', fingerprint='old'), 'new'))
        self.assertTrue(verify.reusable(dict(status='passed', fingerprint='same'), 'same'))

    def test_selection_errors_thorough_conflicts_and_zero_test_runs_fail(self):
        with redirect_stderr(io.StringIO()):
            for args in (['--thorough', '--only', 'test_one'], ['--thorough', '--rust', 'missing'],
                         ['--budget', 'nan'], ['--budget', '0'], ['--last-failed', '--only', 'test_one']):
                with self.assertRaises(SystemExit): verify.parse_args(args)
        args = verify.parse_args(['--only', 'test_typo'])
        with self.assertRaises(ValueError): verify.select(args, ['test_one'], {})
        selected = verify.select(verify.parse_args(['--last-failed']), ['test_one', 'test_two'],
                                 dict(test_one=dict(status='failed'), test_two=dict(status='deferred')))
        self.assertEqual(selected, {'test_one'})
        base = dict(status='passed', output='', seconds=0, exit_code=0)
        for output in ('', 'Ran 0 tests in 0.0s\nOK', 'Ran 2 tests in 0.0s\nOK'):
            self.assertEqual(verify.checked_result(dict(base, output=output), expected=1)['status'], 'failed')
        self.assertEqual(verify.checked_result(dict(base, output='test result: ok. 0 passed;'), rust=True)['status'], 'failed')
        self.assertEqual(verify.checked_result(dict(base, output='Ran 1 test in 0.0s\nOK'), expected=1)['tests'], 1)

    def test_timeout_stops_owned_descendants_and_retains_failure_output(self):
        heartbeat = self.root / 'heartbeat.txt'
        child = self.write('child.py', "from pathlib import Path\nimport time,sys\np=Path(sys.argv[1])\nwhile True:\n p.write_text(str(time.monotonic()))\n time.sleep(.02)\n")
        parent = self.write('parent.py', "import subprocess,sys,time\nsubprocess.Popen([sys.executable,sys.argv[1],sys.argv[2]])\nprint('owned-start',flush=True)\ntime.sleep(60)\n")
        started = time.monotonic()
        row = process.run([sys.executable, str(parent), str(child), str(heartbeat)], self.root, timeout=2)
        self.assertEqual(row['status'], 'deferred')
        self.assertIn('owned-start', row['output'])
        self.assertLess(time.monotonic() - started, 5)
        self.assertTrue(heartbeat.exists())
        before = heartbeat.read_bytes()
        time.sleep(.15)
        self.assertEqual(heartbeat.read_bytes(), before)
        failed = process.run([sys.executable, '-c', "print('test-error');raise SystemExit(7)"], self.root, timeout=3)
        self.assertEqual((failed['status'], failed['exit_code']), ('failed', 7))
        self.assertIn('test-error', failed['output'])

    def test_normal_completion_also_stops_owned_background_workers(self):
        child = self.write('child.py', 'import time\ntime.sleep(60)\n')
        parent = self.write('parent.py', 'import subprocess,sys\nsubprocess.Popen([sys.executable,sys.argv[1]])\n')
        row = process.run([sys.executable, str(parent), str(child)], self.root, timeout=3)
        self.assertEqual(row['status'], 'passed')
        self.assertLess(row['seconds'], 3)

    def test_scheduler_does_not_launch_pending_checks_after_deadline(self):
        with redirect_stdout(io.StringIO()):
            result = verify.schedule(['one', 'two'], lambda n: self.fail(n), 2, time.monotonic() - 1, {}, set())
        self.assertEqual({v['status'] for v in result.values()}, {'deferred'})

    def test_checkout_lease_blocks_second_verifier_and_releases(self):
        path = self.root / 'lease'
        lease = verify.Lease(path)
        try:
            with self.assertRaises(RuntimeError): verify.Lease(path)
        finally:
            lease.close()
        again = verify.Lease(path)
        again.close()

    def mini_run(self, args, fake, state):
        with patch.object(verify, 'ROOT', self.root), patch.object(verify, 'EXE', self.root/'engine.exe'), \
             patch.object(verify, 'environment_identity', return_value='test-environment'), \
             patch.object(verify, 'snapshot', side_effect=lambda r: {p:v for p,v in self.files().items() if not p.startswith('state/')}), \
             patch.object(verify, 'python_counts', return_value={'test_one': 1, 'test_two': 1}), \
             patch.object(verify, 'run', side_effect=fake), redirect_stdout(io.StringIO()):
            started = time.monotonic()
            return verify.verify(verify.parse_args(args), state, started, None)

    def test_resume_failure_selection_and_thorough_never_reuse(self):
        self.write('tests/test_one.py', 'value=1')
        self.write('tests/test_two.py', 'value=2')
        self.write('src/lib.rs', 'original')
        self.write('engine.exe', 'test-binary')
        state = self.root / 'state'; state.mkdir()
        commands = []
        fail = [True]
        def fake(argv, *a):
            commands.append(argv)
            output = 'Ran 1 test in 0.01s\nOK\n'
            if argv[:2] == ['cargo', 'test']: output = 'test result: ok. 2 passed; 0 failed;'
            status = 'failed' if 'test_two.py' in argv and fail[0] else 'passed'
            return dict(status=status, seconds=.01, output=output, exit_code=int(status == 'failed'))
        self.assertEqual(self.mini_run([], fake, state), 1)
        fail[0] = False; commands.clear()
        self.assertEqual(self.mini_run(['--last-failed'], fake, state), 0)
        self.assertEqual(len(commands), 2)  # guard + failed module, no Rust rerun
        commands.clear()
        self.assertEqual(self.mini_run([], fake, state), 0)
        self.assertEqual(len(commands), 1)  # guard always runs
        commands.clear()
        self.assertEqual(self.mini_run(['--thorough'], fake, state), 0)
        self.assertEqual(len(commands), 7)
        record = json.loads(Path(verify.load_state(state/'state.json')['latest_report']).read_text())
        self.assertTrue(record['complete_suite'])
        self.assertTrue(all(r['status'] == 'passed' for r in record['checks'].values()))

    def test_source_changes_during_run_discard_all_reuse(self):
        for n in ('one', 'two'): self.write(f'tests/test_{n}.py', 'value=1')
        source = self.write('src/lib.rs', 'original')
        self.write('engine.exe', 'test-binary')
        state = self.root/'state'; state.mkdir()
        def fake(argv, *a):
            source.write_text('changed')
            return dict(status='passed', seconds=.01, exit_code=0, output='Ran 1 test in 0.01s\nOK\n')
        self.assertEqual(self.mini_run(['--only', 'test_one'], fake, state), 1)
        self.assertEqual(verify.load_state(state/'state.json')['checks'], {})

    def test_budget_resume_and_locked_copy_preserve_finished_checks(self):
        for n in ('one', 'two'): self.write(f'tests/test_{n}.py', 'value=1')
        self.write('src/lib.rs', 'original')
        self.write('engine.exe', 'test-binary')
        state = self.root/'state'; state.mkdir()
        deferred = [True]; commands = []
        def fake(argv, *a):
            commands.append(argv)
            if 'test_two.py' in argv and deferred[0]:
                return dict(status='deferred', seconds=.01, exit_code=None, output='partial test output')
            output = 'test result: ok. 2 passed; 0 failed;' if argv[:2] == ['cargo', 'test'] else 'Ran 1 test in 0.01s\nOK\n'
            return dict(status='passed', seconds=.01, exit_code=0, output=output)
        unlink = Path.unlink
        def locked(path, *args, **kwargs):
            if path.name == 'engine.exe' and 'runs' in path.parts:
                raise PermissionError('Transient owned-copy lock')
            return unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', locked):
            self.assertEqual(self.mini_run([], fake, state), 2)
        record = json.loads(Path(verify.load_state(state/'state.json')['latest_report']).read_text())
        self.assertEqual(record['deferred'], ['test_two'])
        self.assertTrue(Path(record['retained_engine_copy']).exists())
        self.assertFalse(record['complete_suite'])
        # The next window can expire before scheduling. Already completed
        # checks must remain reusable instead of becoming new pending work.
        schedule = verify.schedule
        with patch.object(verify, 'schedule', side_effect=lambda names, worker, jobs, deadline, previous, changed:
                          schedule(names, worker, jobs, time.monotonic() - 1, previous, changed)):
            self.assertEqual(self.mini_run([], fake, state), 2)
        saved = verify.load_state(state/'state.json')
        record = json.loads(Path(saved['latest_report']).read_text())
        self.assertEqual(record['checks']['test_one']['status'], 'reused')
        self.assertEqual(saved['checks']['test_one']['status'], 'passed')
        deferred[0] = False; commands.clear()
        self.assertEqual(self.mini_run([], fake, state), 0)
        self.assertEqual(len(commands), 2)

    def test_launcher_error_is_a_failed_check_with_saved_report(self):
        self.write('tests/test_one.py', 'value=1')
        self.write('tests/test_two.py', 'value=1')
        self.write('engine.exe', 'test-binary')
        state = self.root/'state'; state.mkdir()
        def broken(*a): raise OSError('Synthetic launcher failure')
        self.assertEqual(self.mini_run([], broken, state), 1)
        record = json.loads(Path(verify.load_state(state/'state.json')['latest_report']).read_text())
        self.assertEqual(record['failed'], ['guard'])
        self.assertEqual(record['checks']['guard']['reason'], 'Check launcher failed')


if __name__ == '__main__':
    unittest.main()
