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

    def test_generated_limits_reference_invalidates_compiled_tests(self):
        self.write('src/limits.rs', 'include_str!("../docs/LIMITS.md")')
        self.write('docs/LIMITS.md', 'original reference')
        self.write('tests/test_one.py', "reference=ROOT/'docs/LIMITS.md'")
        self.write('tests/test_two.py', 'value=1')
        names = ['test_one', 'test_two']
        before = inputs.fingerprints(self.root, self.files(), 'same', names)
        self.write('docs/LIMITS.md', 'changed reference')
        after = inputs.fingerprints(self.root, self.files(), 'same', names)
        self.assertEqual({n for n in before if before[n] != after[n]},
                         {'build', 'fmt', 'clippy', 'rust', 'test_one'})
        (self.root/'docs/LIMITS.md').unlink()
        missing = inputs.fingerprints(self.root, self.files(), 'same', names)
        self.assertNotEqual(after['rust'], missing['rust'])

    def test_failed_deferred_and_different_inputs_never_reuse(self):
        for status in ('failed', 'deferred', 'reused'):
            self.assertFalse(verify.reusable(dict(status=status, fingerprint='same'), 'same'))
        self.assertFalse(verify.reusable(dict(status='passed', fingerprint='old'), 'new'))
        self.assertTrue(verify.reusable(dict(status='passed', fingerprint='same'), 'same'))

    def test_real_helper_boundaries_keep_report_edits_out_of_rendering_checks(self):
        root=verify.ROOT
        files=inputs.snapshot(root)
        modules=sorted(p.stem for p in (root/'tests').glob('test_*.py'))
        before=inputs.fingerprints(root,files,'fixture-environment',modules)
        changed=dict(files);changed['docs/IMPLEMENTATION.md']='original-doc-change'
        after=inputs.fingerprints(root,changed,'fixture-environment',modules)
        affected={name for name in before if before[name]!=after[name]}
        self.assertEqual(affected,{
            'test_implementation_registry','test_repo_guard','test_verification',
            'test_verification_runner','test_workload_gates','test_wide_workload_gates',
            'test_agent_benchmark','test_agent_benchmark_handoff',
            'test_agent_benchmark_photo','test_agent_benchmark_recovery','test_benchmark_recovery_external',
            'test_benchmark_driver',  # Captures complete external trial workspaces.
            'test_benchmark_icons','test_benchmark_large_layout',  # Exercise that capture lifecycle.
            'test_benchmark_svg','test_benchmark_palette','test_benchmark_flow','test_benchmark_typography','test_benchmark_mask','test_benchmark_retouch','test_benchmark_photo','test_benchmark_mixed','test_benchmark_variants','test_benchmark_screen','test_benchmark_print','test_benchmark_resources','test_benchmark_repair','test_benchmark_retry','test_benchmark_conflict',
            'test_wsl_verification',  # The WSL snapshot binds the whole candidate.
        })
        # Refactoring must still invalidate actual shared helper consumers and
        # must not weaken the conservative Rust/unknown-input boundary.
        changed=dict(files);changed['tools/workload_cases.py']='original-helper-change'
        after=inputs.fingerprints(root,changed,'fixture-environment',modules)
        for name in ['test_workload_measurement','test_native_locality','test_large_raster',
                     'test_tiled_filters','test_tiled_effects','test_native_retouch']:
            self.assertNotEqual(before[name],after[name],name)
        changed=dict(files);changed['tests/test_affine_inverse_cli.py']='original-evidence-change'
        after=inputs.fingerprints(root,changed,'fixture-environment',modules)
        self.assertNotEqual(before['test_implementation_registry'],after['test_implementation_registry'])
        changed=dict(files);changed['src/geometry.rs']='original-engine-change'
        after=inputs.fingerprints(root,changed,'fixture-environment',modules)
        self.assertTrue(all(before[name]!=after[name] for name in before))

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
        row = process.run([sys.executable, str(parent), str(child), str(heartbeat)], self.root, timeout=2, observe_memory=True)
        self.assertEqual(row['status'], 'deferred')
        self.assertIn('owned-start', row['output'])
        self.assertLess(time.monotonic() - started, 5)
        self.assertTrue(heartbeat.exists())
        before = heartbeat.read_bytes()
        time.sleep(.15)
        self.assertEqual(heartbeat.read_bytes(), before)
        self.assertEqual(row['memory']['available'], os.name == 'nt')
        failed = process.run([sys.executable, '-c', "print('test-error');raise SystemExit(7)"], self.root, timeout=3)
        self.assertEqual((failed['status'], failed['exit_code']), ('failed', 7))
        self.assertIn('test-error', failed['output'])
        self.assertNotIn('memory', failed)

    def test_optional_memory_distinguishes_unavailable_from_zero_and_preserves_default_results(self):
        command = [sys.executable, '-c', "print('completed')"]
        ordinary = process.run(command, self.root, timeout=5)
        self.assertEqual(set(ordinary), {'status','seconds','output','exit_code'})
        observed = process.run(command, self.root, timeout=5, observe_memory=True)
        self.assertEqual(observed['status'], 'passed')
        memory = observed['memory']
        self.assertEqual(memory['scope'], process.MEMORY_SCOPE)
        self.assertEqual(memory['available'], os.name == 'nt')
        if os.name == 'nt':
            self.assertEqual(memory['method'], process.MEMORY_METHOD)
            self.assertGreater(memory['peak_process_commit_bytes'], 0)
            self.assertGreater(memory['peak_job_commit_bytes'], 0)
        else:
            self.assertIsNone(memory['peak_process_commit_bytes'])
            self.assertIsNone(memory['peak_job_commit_bytes'])
            self.assertIn('unavailable', memory['reason'])
        deferred = process.run(command, self.root, timeout=0, observe_memory=True)
        self.assertEqual(deferred['status'], 'deferred')
        self.assertFalse(deferred['memory']['available'])
        self.assertIsNone(deferred['memory']['peak_process_commit_bytes'])

    @unittest.skipUnless(os.name == 'nt', 'Windows Job Object commit-memory counters')
    def test_job_memory_retains_short_lived_descendant_peaks_on_success_and_failure(self):
        child = self.write('allocate.py', "data=bytearray(64*1024*1024)\nfor i in range(0,len(data),4096): data[i]=1\nprint('allocated',len(data),flush=True)\n")
        parent = self.write('parent.py', 'import subprocess,sys\nsubprocess.run([sys.executable,sys.argv[1]],check=True)\nprint("child-exited",flush=True)\nraise SystemExit(int(sys.argv[2]))\n')
        for code in (0,7):
            with self.subTest(code=code):
                row = process.run([sys.executable,str(parent),str(child),str(code)], self.root,
                                  timeout=10, observe_memory=True)
                self.assertEqual(row['exit_code'], code)
                self.assertEqual(row['status'], 'passed' if code==0 else 'failed')
                self.assertIn('child-exited', row['output'])
                self.assertTrue(row['memory']['available'], row)
                self.assertGreaterEqual(row['memory']['peak_process_commit_bytes'], 64*1024*1024)
                self.assertGreaterEqual(row['memory']['peak_job_commit_bytes'], 64*1024*1024)

    @unittest.skipUnless(os.name == 'nt', 'Windows Job Object commit-memory counters')
    def test_job_memory_query_failure_and_incomplete_cleanup_are_explicit(self):
        job = process.WindowsJob()
        try:
            empty = job.memory()
            self.assertFalse(empty['available'])
            self.assertIsNone(empty['peak_process_commit_bytes'])
            with patch.object(job.api, 'QueryInformationJobObject', return_value=False):
                failed = job.memory()
                self.assertFalse(failed['available'])
                self.assertIn('query failed', failed['reason'])
                incomplete = job.close(observe_memory=True)
                self.assertFalse(incomplete['available'])
                self.assertIn('cleanup', incomplete['reason'])
            self.assertIsNone(job.handle)
        finally:
            job.close()

    def test_explicit_platform_skips_are_not_counted_as_executed_tests(self):
        output = "test_job ... skipped 'Engine capabilities.jobs.supported_here is false'\nRan 2 tests in 0.1s\nOK (skipped=1)\n"
        row = verify.checked_result(dict(status='passed', output=output), expected=2)
        self.assertEqual(row['tests'], 2)
        self.assertEqual(row['skipped'], 1)
        self.assertEqual(row['skip_reasons'], ["'Engine capabilities.jobs.supported_here is false'"])
        windows = verify.checked_result(dict(status='passed', output=output.replace('\n', '\r\n')), expected=2)
        self.assertEqual(windows['skipped'], 1)
        self.assertEqual(windows['skip_reasons'], row['skip_reasons'])
        broken = verify.checked_result(dict(status='passed', output=output.replace('skipped=1', 'skipped=3')), expected=2)
        self.assertEqual(broken['status'], 'failed')

    def test_normal_completion_also_stops_owned_background_workers(self):
        child = self.write('child.py', 'import time\ntime.sleep(60)\n')
        parent = self.write('parent.py', 'import subprocess,sys\nsubprocess.Popen([sys.executable,sys.argv[1]])\n')
        row = process.run([sys.executable, str(parent), str(child)], self.root, timeout=3)
        self.assertEqual(row['status'], 'passed')
        self.assertLess(row['seconds'], 3)

    @unittest.skipUnless(os.name == 'nt', 'Windows terminated-process directory handles')
    def test_timeout_releases_descendant_working_directories_before_returning(self):
        command = "import subprocess,sys,time;[subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']) for _ in range(3)];time.sleep(60)"
        for index in range(8):
            directory = self.root / ('cancelled-' + str(index)); directory.mkdir()
            row = process.run([sys.executable, '-c', command], directory, timeout=.2, observe_memory=True)
            self.assertEqual(row['status'], 'deferred')
            self.assertTrue(row['memory']['available'], row)
            directory.rmdir()  # No retry or grace sleep may hide an owned handle leak.

    def test_scheduler_does_not_launch_pending_checks_after_deadline(self):
        with redirect_stdout(io.StringIO()):
            result = verify.schedule(['one', 'two'], lambda n: self.fail(n), 2, time.monotonic() - 1, {}, set())
        self.assertEqual({v['status'] for v in result.values()}, {'deferred'})

    def test_scheduler_reserves_long_checks_before_edited_short_fixtures(self):
        launched = []
        def worker(name):
            launched.append(name)
            return dict(status='passed', seconds=1)
        previous = dict(test_long=dict(status='passed', seconds=100),
                        test_edited=dict(status='passed', seconds=2))
        with patch.object(verify.time, 'monotonic', return_value=100), redirect_stdout(io.StringIO()):
            rows = verify.schedule(previous, worker, 1, 300, previous, {'tests/test_edited.py'})
        self.assertEqual(launched, ['test_long', 'test_edited'])
        self.assertTrue(all(row['status'] == 'passed' for row in rows.values()))

    def test_scheduler_skips_known_overrun_but_runs_fitting_and_unknown_checks(self):
        launched = []
        def worker(name):
            launched.append(name)
            return dict(status='passed', seconds=1)
        previous = dict(long=dict(status='passed', seconds=10),
                        short=dict(status='passed', seconds=2))
        with patch.object(verify.time, 'monotonic', return_value=100), redirect_stdout(io.StringIO()):
            rows = verify.schedule(['long', 'short', 'unknown'], worker, 2, 110, previous, set())
        self.assertCountEqual(launched, ['short', 'unknown'])
        self.assertEqual(rows['long']['status'], 'deferred')
        self.assertEqual(rows['long']['seconds'], 0)
        self.assertEqual(rows['long']['remaining_seconds'], 10)
        self.assertIn('10% reserve', rows['long']['reason'])
        # Thorough mode runs everything, regardless of the saved estimate.
        launched.clear()
        with redirect_stdout(io.StringIO()):
            rows = verify.schedule(['long', 'short', 'unknown'], worker, 2, None, previous, set())
        self.assertCountEqual(launched, ['long', 'short', 'unknown'])
        self.assertTrue(all(row['status'] == 'passed' for row in rows.values()))

    def test_scheduler_rechecks_remaining_budget_after_a_worker_finishes(self):
        now = [100]
        launched = []
        def worker(name):
            launched.append(name)
            now[0] += 6 if name == 'first' else 1
            return dict(status='passed', seconds=1)
        previous = {name: dict(status='passed', seconds=seconds)
                    for name, seconds in [('first', 6), ('second', 5), ('short', 1)]}
        with patch.object(verify.time, 'monotonic', side_effect=lambda: now[0]), redirect_stdout(io.StringIO()):
            rows = verify.schedule(previous, worker, 1, 110, previous, set())
        self.assertEqual(launched, ['first', 'short'])
        self.assertEqual(rows['second']['remaining_seconds'], 4)
        self.assertEqual(rows['second']['status'], 'deferred')

    def test_duration_evidence_survives_deferral_and_failure_without_becoming_a_pass(self):
        previous = dict(status='passed', seconds=100)
        for status, seconds, expected in [('deferred', 0, 100), ('deferred', 120, 120), ('failed', 1, 120)]:
            row = dict(status=status, seconds=seconds)
            verify.retain_duration(row, previous)
            self.assertEqual(verify.duration_hint(row), expected)
            self.assertEqual(row['status'], status)
            previous = row
        fresh = dict(status='passed', seconds=5)
        verify.retain_duration(fresh, previous)
        self.assertEqual(verify.duration_hint(fresh), 5)
        self.assertIsNone(verify.duration_hint(dict(status='failed', seconds=1)))
        for invalid in [None, -1, 0, True, '120', float('nan'), float('inf')]:
            self.assertIsNone(verify.duration_hint(dict(status='passed', seconds=invalid)))

    def test_checkout_lease_blocks_second_verifier_and_releases(self):
        path = self.root / 'lease'
        lease = verify.Lease(path)
        try:
            with self.assertRaises(RuntimeError): verify.Lease(path)
        finally:
            lease.close()
        again = verify.Lease(path)
        again.close()

    def mini_run(self, args, fake, state, stdout=None, deadline=None):
        with patch.object(verify, 'ROOT', self.root), patch.object(verify, 'EXE', self.root/'engine.exe'), \
             patch.object(verify, 'environment_identity', return_value='test-environment'), \
             patch.object(verify, 'snapshot', side_effect=lambda r: {p:v for p,v in self.files().items() if not p.startswith('state/')}), \
             patch.object(verify, 'python_counts', return_value={'test_one': 1, 'test_two': 1}), \
             patch.object(verify, 'run', side_effect=fake), redirect_stdout(stdout if stdout is not None else io.StringIO()):
            started = time.monotonic()
            return verify.verify(verify.parse_args(args), state, started, deadline)

    def test_forecast_deferral_keeps_unresolved_failure_and_force_refreshes_timing(self):
        for name in ('one', 'two'): self.write(f'tests/test_{name}.py', 'value=1')
        self.write('engine.exe', 'test-binary')
        state = self.root/'state'; state.mkdir()
        commands = []
        def fake(argv, *args):
            commands.append(argv)
            return dict(status='passed', seconds=.01, exit_code=0,
                        output='Ran 1 test in 0.01s\nOK\n')
        self.assertEqual(self.mini_run(['--only', 'test_two'], fake, state), 0)
        saved = verify.load_state(state/'state.json')
        saved['checks']['test_two'].update(status='failed', seconds=.01, duration_hint_seconds=100)
        (state/'state.json').write_text(json.dumps(saved), encoding='utf-8')
        commands.clear()
        self.assertEqual(self.mini_run(['--last-failed'], fake, state, deadline=time.monotonic()+30), 2)
        self.assertEqual(len(commands), 1)  # Only the mandatory guard ran.
        saved = verify.load_state(state/'state.json')
        report = json.loads(Path(saved['latest_report']).read_text(encoding='utf-8'))
        self.assertEqual(report['deferred'], ['test_two'])
        self.assertEqual(saved['checks']['test_two']['status'], 'failed')
        self.assertEqual(saved['checks']['test_two']['duration_hint_seconds'], 100)
        commands.clear()
        self.assertEqual(self.mini_run(['--last-failed', '--force'], fake, state, deadline=time.monotonic()+30), 0)
        saved = verify.load_state(state/'state.json')
        self.assertEqual(saved['checks']['test_two']['status'], 'passed')
        self.assertEqual(saved['checks']['test_two']['duration_hint_seconds'], .01)
        self.assertEqual(sum('test_two.py' in command for command in commands), 1)

    def test_public_guard_is_reported_and_cannot_satisfy_next_private_run(self):
        self.write('tests/test_one.py', 'value=1')
        self.write('engine.exe', 'test-binary')
        state = self.root/'state'; state.mkdir()
        commands = []
        def fake(argv, *args):
            commands.append(argv)
            private = 'tools/check_repo.py' in argv and '--public' not in argv
            return dict(status='failed' if private else 'passed', seconds=.01,
                        exit_code=int(private), output='Missing private policy' if private else 'Ran 1 test in 0.01s\nOK\n')
        self.assertEqual(self.mini_run(['--public','--only','test_one'], fake, state), 0)
        saved = verify.load_state(state/'state.json')
        report = json.loads(Path(saved['latest_report']).read_text(encoding='utf-8'))
        self.assertEqual(report['repository_guard'], dict(mode='public_structural', private_policy='not_evaluated'))
        self.assertIn('--public', report['checks']['guard']['command'])
        commands.clear()
        self.assertEqual(self.mini_run(['--only','test_one'], fake, state), 1)
        self.assertEqual(commands, [verify.PY+['tools/check_repo.py']])
        saved = verify.load_state(state/'state.json')
        report = json.loads(Path(saved['latest_report']).read_text(encoding='utf-8'))
        self.assertEqual(report['repository_guard'], dict(mode='private', private_policy='required'))
        self.assertEqual(report['failed'], ['guard'])
        self.assertEqual(report['deferred'], ['build','clippy','fmt','test_one'])

    def test_unicode_failure_on_legacy_pipe_keeps_exact_log_report_and_retry(self):
        for name in ('one', 'two'):self.write(f'tests/test_{name}.py', 'value=1')
        self.write('engine.exe', 'test-binary')
        state=self.root/'state';state.mkdir()
        failed=[True];commands=[];text='Original fixture \u0394 \U0001f3a8 failed'
        def fake(argv,*args):
            commands.append(argv)
            output='test result: ok. 2 passed; 0 failed;' if argv[:2]==['cargo','test'] else 'Ran 1 test in 0.01s\nOK\n'
            bad=failed[0] and 'test_two.py' in argv
            return dict(status='failed' if bad else 'passed',seconds=.01,exit_code=int(bad),output=text if bad else output)
        buffer=io.BytesIO();stream=io.TextIOWrapper(buffer,encoding='cp1252',errors='strict')
        self.addCleanup(stream.close)
        self.assertEqual(self.mini_run([],fake,state,stream),1)
        stream.flush();console=buffer.getvalue().decode('cp1252')
        self.assertIn('\\u0394 \\U0001f3a8',console)
        saved=verify.load_state(state/'state.json');report=json.loads(Path(saved['latest_report']).read_text())
        self.assertEqual(report['failed'],['test_two'])
        self.assertEqual(Path(report['checks']['test_two']['log']).read_text(encoding='utf-8'),text)
        self.assertEqual(saved['checks']['test_two']['status'],'failed')
        failed[0]=False;commands.clear()
        self.assertEqual(self.mini_run(['--last-failed'],fake,state,stream),0)
        self.assertEqual(len(commands),2)

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
