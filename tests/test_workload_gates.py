"""Synthetic report adversaries test gating; no timings here claim engine performance."""
import copy
import ast
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_cli import ROOT

sys.path.insert(0, str(ROOT/'tools'))
import workload_gates as gates


def report():
    rows = []
    for repetition in range(1, 6):
        for name in gates.CASES:
            commands, checks = gates.CONTRACTS[name]
            calls = [dict(step=step, command=command, status='success', exit_code=0,
                          timed_out=False, retries=0, seconds=repetition/10,
                          memory=dict(available=True, peak_commit_bytes=8*1024*1024,
                                      peak_working_set_bytes=4*1024*1024)) for step, command in commands]
            rows.append(dict(case=name, adapter='native-tiled-v1', repetition=repetition,
                             success=True, blocked_steps=0, memory_complete=True,
                             calls=calls, process_calls=len(calls),
                             checks=[dict(name=n, status='pass') for n in checks],
                             engine_seconds=sum(c['seconds'] for c in calls),
                             peak_commit_bytes=8*1024*1024, peak_working_set_bytes=4*1024*1024))
    return dict(schema_version=1, suite='scale-v1', adapter='native-tiled-v1', model_trials=False,
                valid_inputs=True, source_unchanged=True, candidate_files_unchanged=True,
                executable_unchanged=True, environment_unchanged=True, outcome='all_selected_workloads_passed',
                selected_cases=list(gates.CASES), repetitions=5, source_sha256='1'*64,
                build=dict(executable_sha256='2'*64, artifact=dict(profile=dict(opt_level='3'),
                           target=dict(name='inkbolt', kind=['bin']))),
                environment=dict(system='Windows', release='test-release', version='test-version',
                                 machine='AMD64', pointer_bits=64, processor='test-cpu', logical_cpus=8, python='test-python',
                                 hardware_available=True, hardware_source='windows_native_system_info_and_cpu_registry_v1'),
                toolchain='rustc test', conditions='Synthetic records for validation tests only',
                candidate_files={name:'3'*64 for name in gates.HARNESS}, rows=rows,
                aggregates=[dict(case='misleading-summary', successful=9999)])


class WorkloadGateTests(unittest.TestCase):
    def setUp(self):
        self.report = report()
        self.gate = gates.create(self.report, '4'*64, 'Synthetic baseline for tests')

    def reject(self, changed):
        result = gates.check(self.gate, changed)
        self.assertFalse(result['eligible'], result)
        self.assertEqual(result['status'], 'ineligible')
        with self.assertRaises((ValueError, KeyError, TypeError)):
            gates.create(changed, '4'*64, 'invalid baseline')

    def test_policy_uses_all_trials_and_observed_memory_with_explicit_headroom(self):
        self.assertEqual(self.gate['limits']['social-square'],
                         dict(median_seconds=.45, maximum_seconds=1., peak_commit_bytes=12*1024*1024))
        self.assertEqual(gates.check(self.gate, self.report)['status'], 'passed')
        self.assertEqual(len(self.gate['limits']), 7)

    def test_worst_trial_cannot_hide_behind_fast_successful_median(self):
        row=self.report['rows'][-1]
        row['calls'][0]['seconds']=10
        row['engine_seconds']=sum(c['seconds'] for c in row['calls'])
        result=gates.check(self.gate,self.report)
        self.assertTrue(result['eligible'])
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['comparisons'][-1]['exceeded'],['maximum_seconds'])

    def test_median_regression_is_checked_even_when_all_trials_fit_maximum(self):
        for row in self.report['rows']:
            if row['case']=='social-square':
                row['calls'][0]['seconds']=row['engine_seconds']=.6
        result=gates.check(self.gate,self.report)
        self.assertEqual(result['comparisons'][3]['exceeded'],['median_seconds'])

    def test_peak_memory_is_not_averaged_over_trials_or_commands(self):
        row=self.report['rows'][0]
        row['calls'][0]['memory']['peak_commit_bytes']=row['peak_commit_bytes']=20*1024*1024
        result=gates.check(self.gate,self.report)
        self.assertEqual(result['comparisons'][0]['exceeded'],['peak_commit_bytes'])

    def test_failed_fast_work_and_missing_oracle_are_never_success(self):
        for change in ('failure','oracle','blocked','timeout','retry','steps','no_checks'):
            with self.subTest(change=change):
                r=copy.deepcopy(self.report);row=r['rows'][0]
                if change=='failure':row['success']=False
                elif change=='oracle':row['checks'][0]['status']='fail'
                elif change=='blocked':row['blocked_steps']=1
                elif change=='timeout':row['calls'][0]['timed_out']=True
                elif change=='retry':row['calls'][0]['retries']=1
                elif change=='steps':row['calls'][0]['command']='capabilities'
                else:row['checks']=[dict(name='source-preservation',status='pass')]
                self.reject(r)

    def test_missing_duplicate_extra_and_short_runs_are_ineligible(self):
        for change in ('missing','duplicate','extra','short','subset','boolean_repetition'):
            with self.subTest(change=change):
                r=copy.deepcopy(self.report)
                if change=='missing':r['rows'].pop()
                elif change=='duplicate':r['rows'][1]=r['rows'][0]
                elif change=='extra':r['rows'].append(r['rows'][0])
                elif change=='short':r['repetitions']=4;r['rows']=r['rows'][:28]
                elif change=='subset':r['selected_cases'].pop()
                else:r['rows'][0]['repetition']=True
                self.reject(r)

    def test_invalid_nonfinite_unavailable_or_inconsistent_observations_fail_closed(self):
        for value in (None,False,-1,0,float('nan'),float('inf')):
            with self.subTest(value=value):
                r=copy.deepcopy(self.report);r['rows'][0]['calls'][0]['seconds']=value
                self.reject(r)
        for change in ('unavailable','no_peak','bad_sum','bad_peak','bad_working_set'):
            r=copy.deepcopy(self.report);row=r['rows'][0]
            if change=='unavailable':row['calls'][0]['memory']['available']=False
            elif change=='no_peak':row['calls'][0]['memory']['peak_commit_bytes']=None
            elif change=='bad_sum':row['engine_seconds']=.01
            elif change=='bad_peak':row['peak_commit_bytes']=1
            else:row['peak_working_set_bytes']=None
            self.reject(r)

    def test_changed_inputs_debug_build_and_unverified_platform_reject(self):
        for key in ('valid_inputs','source_unchanged','candidate_files_unchanged','executable_unchanged','environment_unchanged'):
            r=copy.deepcopy(self.report);r[key]=False;self.reject(r)
        r=copy.deepcopy(self.report);r['build']['artifact']['profile']['opt_level']='0';self.reject(r)
        r=copy.deepcopy(self.report);r['environment']['system']='Linux';self.reject(r)
        r=copy.deepcopy(self.report);r['environment']['hardware_available']=False;self.reject(r)

    def test_fixture_adapter_machine_and_toolchain_changes_need_reviewed_baseline(self):
        for change in ('harness','adapter','machine','compiler'):
            with self.subTest(change=change):
                r=copy.deepcopy(self.report)
                if change=='harness':r['candidate_files'][gates.HARNESS[0]]='5'*64
                elif change=='adapter':
                    r['adapter']='legacy-v1'
                    for row in r['rows']:row['adapter']='legacy-v1'
                elif change=='machine':r['environment']['processor']='another-cpu'
                else:r['toolchain']='new compiler'
                result=gates.check(self.gate,r)
                self.assertEqual(result['status'],'ineligible')
                self.assertIn('Incomparable',result['reason'])

    def test_engine_revision_may_change_while_the_same_contract_remains_bound(self):
        self.report['source_sha256']='5'*64
        self.report['build']['executable_sha256']='6'*64
        self.report['candidate_files']['src/render.rs']='7'*64
        self.assertEqual(gates.check(self.gate,self.report)['status'],'passed')

    def test_manual_budget_and_policy_relaxation_cannot_silently_pass(self):
        for key in ('limits','policy'):
            gate=copy.deepcopy(self.gate)
            if key=='limits':gate['limits']['native-screen']['maximum_seconds']=100
            else:gate['policy']['maximum_seconds_factor']=100
            self.assertEqual(gates.check(gate,self.report)['status'],'ineligible')

    def test_gate_cannot_mutate_the_checker_policy_through_shared_state(self):
        self.gate['policy']['maximum_seconds_factor']=100
        self.assertEqual(gates.POLICY['maximum_seconds_factor'],2)
        self.assertEqual(gates.check(self.gate,self.report)['status'],'ineligible')

    def changed_harness_report(self, factor=1):
        r=copy.deepcopy(self.report)
        r['candidate_files']['tools/workload_cases.py']='a'*64
        for row in r['rows']:
            for call in row['calls']:call['seconds']*=factor
            row['engine_seconds']=sum(call['seconds'] for call in row['calls'])
        return r

    def test_refresh_preserves_original_absolute_budgets_and_records_helper_review(self):
        report=self.changed_harness_report(1.25)
        before=copy.deepcopy(self.gate)
        refreshed=gates.refresh(self.gate,'5'*64,report,'6'*64,'Reviewed unchanged calculations after helper extraction')
        self.assertEqual(self.gate,before)
        self.assertEqual(refreshed['schema_version'],2)
        self.assertEqual(refreshed['limits'],self.gate['limits'])
        self.assertNotEqual(refreshed['limits'],gates.create(report,'6'*64,'A new budget')['limits'])
        self.assertEqual(refreshed['budget_origin'],self.gate)
        self.assertEqual(refreshed['refresh']['previous_gate_sha256'],'5'*64)
        self.assertEqual(refreshed['refresh']['changed_helpers'],[
            dict(path='tools/workload_cases.py',before='3'*64,after='a'*64)])
        self.assertEqual(gates.check(refreshed,report)['status'],'passed')
        self.assertEqual(gates.check(self.gate,report)['status'],'ineligible')
        # A slower new baseline must not permit a later regression that would
        # have failed the original median budget.
        for row in report['rows']:
            for call in row['calls']:call['seconds']=.48
            row['engine_seconds']=sum(call['seconds'] for call in row['calls'])
        self.assertEqual(gates.check(refreshed,report)['status'],'failed')

    def test_refresh_cannot_hide_a_failed_or_over_budget_fresh_reference(self):
        for kind in ('median','maximum','memory','failed'):
            with self.subTest(kind=kind):
                report=self.changed_harness_report()
                if kind=='failed':report['rows'][0]['success']=False
                elif kind=='maximum':
                    row=report['rows'][0];row['calls'][0]['seconds']=100
                    row['engine_seconds']=sum(c['seconds'] for c in row['calls'])
                elif kind=='memory':
                    row=report['rows'][0]
                    row['calls'][0]['memory']['peak_commit_bytes']=row['peak_commit_bytes']=100*1024*1024
                else:
                    for row in report['rows']:
                        for c in row['calls']:c['seconds']=.6
                        row['engine_seconds']=sum(c['seconds'] for c in row['calls'])
                with self.assertRaises(ValueError):gates.refresh(self.gate,'5'*64,report,'6'*64,'Review')

    def test_refresh_rejects_unchanged_helpers_missing_review_and_incomparable_environment(self):
        for change in ('same_helpers','review','gate_hash','report_hash','environment','compiler','adapter'):
            with self.subTest(change=change):
                report=self.changed_harness_report();reason='Review';gate_hash='5'*64;report_hash='6'*64
                if change=='same_helpers':report=copy.deepcopy(self.report)
                elif change=='review':reason=' '
                elif change=='gate_hash':gate_hash='missing'
                elif change=='report_hash':report_hash=self.gate['baseline_report_sha256']
                elif change=='environment':report['environment']['processor']='different-cpu'
                elif change=='compiler':report['toolchain']='different-rustc'
                else:
                    report['adapter']='legacy-v1'
                    for row in report['rows']:row['adapter']='legacy-v1'
                with self.assertRaises(ValueError):gates.refresh(self.gate,gate_hash,report,report_hash,reason)

    def test_repeated_refreshes_keep_one_original_budget_origin_without_ratchets(self):
        report=self.changed_harness_report(1.2)
        first=gates.refresh(self.gate,'5'*64,report,'6'*64,'First reviewed extraction')
        report['candidate_files']['tools/workload_cases.py']='b'*64
        second=gates.refresh(first,'7'*64,report,'8'*64,'Second reviewed extraction')
        self.assertEqual(second['budget_origin'],self.gate)
        self.assertEqual(second['limits'],self.gate['limits'])
        self.assertEqual(second['refresh']['previous_harness'],first['baseline']['harness'])
        self.assertEqual(second['refresh']['previous_gate_sha256'],'7'*64)
        self.assertEqual(gates.check(second,report)['status'],'passed')
        second['budget_origin']['limits']['native-control']['maximum_seconds']=999
        self.assertEqual(first['budget_origin'],self.gate)
        self.assertEqual(gates.check(second,report)['status'],'ineligible')

    def test_refreshed_gate_rejects_tampered_budgets_origins_and_review_records(self):
        report=self.changed_harness_report()
        good=gates.refresh(self.gate,'5'*64,report,'6'*64,'Reviewed helper split')
        for change in ('limits','origin_limit','origin_policy','origin_version','review','changes','previous','baseline','origin_host'):
            with self.subTest(change=change):
                gate=copy.deepcopy(good)
                if change=='limits':gate['limits']['social-square']['median_seconds']=999
                elif change=='origin_limit':gate['budget_origin']['limits']['social-square']['median_seconds']=999
                elif change=='origin_policy':gate['budget_origin']['policy']['median_seconds_factor']=999
                elif change=='origin_version':gate['budget_origin']['schema_version']=2
                elif change=='review':gate['refresh']['reason']='unmatched review'
                elif change=='changes':gate['refresh']['changed_helpers']=[]
                elif change=='previous':gate['refresh']['previous_harness']['tools/workload_cases.py']='not-a-hash'
                elif change=='baseline':gate['baseline']['metrics']['social-square']['median_seconds']=999
                else:gate['budget_origin']['baseline']['environment']['processor']='different-cpu'
                self.assertEqual(gates.check(gate,report)['status'],'ineligible')

    def test_cli_refresh_is_create_only_and_still_requires_a_distinct_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);old=root/'old.json';baseline=root/'baseline.json';out=root/'refreshed.json'
            old.write_text(json.dumps(self.gate));report=self.changed_harness_report()
            baseline.write_text(json.dumps(report));originals=(old.read_bytes(),baseline.read_bytes())
            command=[sys.executable,str(ROOT/'tools/workload_gates.py'),'refresh','--gate',str(old),
                     '--baseline',str(baseline),'--output',str(out),'--reason','Reviewed original helpers']
            first=subprocess.run(command,capture_output=True,timeout=15)
            self.assertEqual(first.returncode,0,first.stderr)
            saved=out.read_bytes();gate=json.loads(saved)
            self.assertEqual(gate['limits'],self.gate['limits'])
            self.assertEqual(gate['refresh']['previous_gate_sha256'],gates.digest(originals[0]))
            self.assertEqual(subprocess.run(command,capture_output=True,timeout=15).returncode,2)
            self.assertEqual(out.read_bytes(),saved)
            same=root/'same-result.json'
            check=[sys.executable,str(ROOT/'tools/workload_gates.py'),'check','--gate',str(out),
                   '--report',str(baseline),'--output',str(same)]
            self.assertEqual(subprocess.run(check,capture_output=True,timeout=15).returncode,2)
            self.assertEqual(json.loads(same.read_bytes())['status'],'ineligible')
            report['conditions']='Separate original synthetic comparison'
            current=root/'current.json';current.write_text(json.dumps(report));result=root/'result.json'
            check[-3]=str(current);check[-1]=str(result)
            self.assertEqual(subprocess.run(check,capture_output=True,timeout=15).returncode,0)
            self.assertEqual(json.loads(result.read_bytes())['status'],'passed')
            self.assertEqual((old.read_bytes(),baseline.read_bytes()),originals)

    def test_failed_refresh_leaves_no_output_and_preserves_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);old=root/'old.json';baseline=root/'bad.json';out=root/'never-created.json'
            old.write_text(json.dumps(self.gate));report=self.changed_harness_report(10)
            baseline.write_text(json.dumps(report));originals=(old.read_bytes(),baseline.read_bytes())
            result=subprocess.run([sys.executable,str(ROOT/'tools/workload_gates.py'),'refresh',
                '--gate',str(old),'--baseline',str(baseline),'--output',str(out),'--reason','Review'],
                capture_output=True,timeout=15)
            self.assertEqual(result.returncode,2)
            self.assertFalse(out.exists())
            self.assertEqual((old.read_bytes(),baseline.read_bytes()),originals)

    def test_pinned_helpers_cover_the_actual_local_driver_import_closure(self):
        modules={}
        for directory in ('tests','tools'):
            for path in (ROOT/directory).glob('*.py'):
                modules.setdefault(path.stem,set()).add(path.relative_to(ROOT).as_posix())
        pending=['tools/measure_workloads.py'];seen=set()
        while pending:
            name=pending.pop()
            if name in seen:continue
            seen.add(name)
            for node in ast.walk(ast.parse((ROOT/name).read_text(encoding='utf-8'))):
                names=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) else []
                for name in names:pending.extend(modules.get(name.split('.')[0],()))
        self.assertEqual(seen,set(gates.HARNESS),'Update the pinned helper contract when the measurement driver imports change')

    def test_cli_creates_content_bound_evidence_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);baseline=root/'baseline.json';gate=root/'gate.json';result=root/'result.json'
            raw=json.dumps(self.report).encode();baseline.write_bytes(raw)
            command=[sys.executable,str(ROOT/'tools/workload_gates.py')]
            create=command+['create','--baseline',str(baseline),'--output',str(gate),'--reason','Original synthetic report test']
            a=subprocess.run(create,capture_output=True)
            self.assertEqual(a.returncode,0,a.stderr)
            saved=gate.read_bytes()
            self.assertEqual(json.loads(saved)['baseline_report_sha256'],gates.digest(raw))
            b=subprocess.run(create,capture_output=True)
            self.assertEqual(b.returncode,2);self.assertEqual(gate.read_bytes(),saved)
            candidate=root/'candidate.json'
            self.report['source_sha256']='5'*64
            candidate.write_text(json.dumps(self.report),encoding='utf-8')
            compare=command+['check','--gate',str(gate),'--report',str(candidate),'--output',str(result)]
            c=subprocess.run(compare,capture_output=True)
            self.assertEqual(c.returncode,0,c.stderr)
            self.assertEqual(json.loads(result.read_bytes())['gate_sha256'],gates.digest(saved))
            self.report['rows'][0]['success']=False
            candidate.write_text(json.dumps(self.report),encoding='utf-8')
            result2=root/'failed.json';compare[-1]=str(result2)
            d=subprocess.run(compare,capture_output=True)
            self.assertEqual(d.returncode,2)
            self.assertEqual(json.loads(result2.read_bytes())['status'],'ineligible')
            compare[-3]=str(baseline);compare[-1]=str(root/'baseline-only.json')
            e=subprocess.run(compare,capture_output=True)
            self.assertEqual(e.returncode,2)
            self.assertIn('baseline itself',json.loads((root/'baseline-only.json').read_bytes())['reason'])

    def test_json_nonfinite_numbers_and_repository_outputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'bad.json';p.write_text('{"value":NaN}',encoding='utf-8')
            with self.assertRaises(ValueError):gates.load(p)
        with self.assertRaisesRegex(ValueError,'outside the repository'):
            gates.write(ROOT/'must-not-create-gate.json',{})
        self.assertFalse((ROOT/'must-not-create-gate.json').exists())


if __name__=='__main__':unittest.main()
