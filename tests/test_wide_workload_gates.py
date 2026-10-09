"""The additional wide suite has a separate, complete, content-bound budget."""
import ast
import copy
import unittest
from test_cli import ROOT
import test_workload_gates as baseline_tests

gates = baseline_tests.gates


def report():
    r = baseline_tests.report()
    r['suite'] = 'wide-native-v1'
    r['selected_cases'] = ['wide-mixed-native']
    r['rows'] = [row for row in r['rows'] if row['case'] == 'native-control']
    for row in r['rows']:
        row['case'] = 'wide-mixed-native'
        row['calls'] = [c for c in row['calls'] if c['step'] not in ('undo', 'restored')]
        row['checks'] = [c for c in row['checks'] if c['name'] != 'restored']
        row['process_calls'] = len(row['calls'])
        row['engine_seconds'] = sum(c['seconds'] for c in row['calls'])
    r['candidate_files'].update({name: '3'*64 for name in
        ('tools/measure_extra.py', 'tools/measure_wide_native.py', 'tools/wide_native_workload.py')})
    return r


class WideWorkloadGateTests(unittest.TestCase):
    def setUp(self):
        self.report = report()
        self.gate = gates.create(self.report, '4'*64, 'Original synthetic records only')

    def reject(self, r):
        self.assertEqual(gates.check(self.gate, r)['status'], 'ineligible')
        with self.assertRaises((KeyError, TypeError, ValueError)):
            gates.create(r, '4'*64, 'Cannot admit incomplete evidence')

    def test_wide_budget_covers_its_seven_calls_and_all_six_oracles(self):
        self.assertEqual([c['step'] for c in self.report['rows'][0]['calls']],
                         ['import', 'save', 'initial', 'edit', 'edited', 'historical', 'verify'])
        self.assertEqual([c['name'] for c in self.report['rows'][0]['checks']],
                         ['initial', 'edited', 'historical', 'history-valid', 'revision-order', 'source-preservation'])
        result = gates.check(self.gate, self.report)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual([c['case'] for c in result['comparisons']], ['wide-mixed-native'])
        self.assertEqual(set(self.gate['limits']), {'wide-mixed-native'})
        self.assertEqual(self.gate['policy'], gates.POLICY)
        self.assertIn('wide-native-v1', self.gate['scope'])

    def test_every_wide_command_and_oracle_is_required(self):
        for field in ('calls', 'checks'):
            for index in range(len(self.report['rows'][0][field])):
                with self.subTest(field=field, index=index):
                    r = copy.deepcopy(self.report)
                    r['rows'][0][field].pop(index)
                    r['rows'][0]['process_calls'] = len(r['rows'][0]['calls'])
                    r['rows'][0]['engine_seconds'] = sum(c['seconds'] for c in r['rows'][0]['calls'])
                    self.reject(r)

    def test_missing_failed_and_duplicate_trials_do_not_improve_the_budget(self):
        for change in ('short', 'missing', 'duplicate', 'failed', 'blocked', 'oracle', 'memory', 'retry'):
            with self.subTest(change=change):
                r = copy.deepcopy(self.report)
                if change == 'short': r['repetitions'] = 4; r['rows'].pop()
                elif change == 'missing': r['rows'].pop()
                elif change == 'duplicate': r['rows'][-1] = copy.deepcopy(r['rows'][0])
                elif change == 'failed': r['rows'][0]['success'] = False
                elif change == 'blocked': r['rows'][0]['blocked_steps'] = 1
                elif change == 'oracle': r['rows'][0]['checks'][0]['status'] = 'fail'
                elif change == 'memory': r['rows'][0]['calls'][0]['memory']['available'] = False
                else: r['rows'][0]['calls'][0]['retries'] = 1
                self.reject(r)

    def test_wide_median_worst_time_and_peak_memory_are_independent(self):
        for metric in ('median_seconds', 'maximum_seconds', 'peak_commit_bytes'):
            with self.subTest(metric=metric):
                r = copy.deepcopy(self.report)
                rows = r['rows'] if metric == 'median_seconds' else r['rows'][-1:]
                for row in rows:
                    if metric == 'peak_commit_bytes':
                        row['calls'][0]['memory']['peak_commit_bytes'] = row['peak_commit_bytes'] = 20*1024*1024
                    else:
                        target = 4 if metric == 'median_seconds' else 10
                        for call in row['calls']: call['seconds'] = target/len(row['calls'])
                        row['engine_seconds'] = sum(c['seconds'] for c in row['calls'])
                result = gates.check(self.gate, r)
                self.assertEqual(result['status'], 'failed')
                self.assertEqual(result['comparisons'][0]['exceeded'], [metric])

    def test_fixed_and_wide_suites_cannot_substitute_for_each_other(self):
        fixed = baseline_tests.report()
        fixed_gate = gates.create(fixed, '5'*64, 'Fixed suite remains independent')
        self.assertEqual(gates.check(self.gate, fixed)['status'], 'ineligible')
        self.assertEqual(gates.check(fixed_gate, self.report)['status'], 'ineligible')
        for suite in ('scale-v1', 'unknown', 'wide-native-v2'):
            r = copy.deepcopy(self.report); r['suite'] = suite; self.reject(r)
        r = copy.deepcopy(self.report); r['adapter'] = 'legacy-v1'
        for row in r['rows']: row['adapter'] = 'legacy-v1'
        self.reject(r)
        self.assertEqual(gates.check(fixed_gate, fixed)['status'], 'passed')
        self.assertEqual(len(fixed_gate['limits']), 7)

    def test_every_wide_driver_helper_is_pinned_but_engine_changes_are_allowed(self):
        for name in gates.WIDE_HARNESS:
            with self.subTest(helper=name):
                r = copy.deepcopy(self.report); del r['candidate_files'][name]; self.reject(r)
                r = copy.deepcopy(self.report); r['candidate_files'][name] = '5'*64
                self.assertEqual(gates.check(self.gate, r)['status'], 'ineligible')
        r = copy.deepcopy(self.report)
        r['source_sha256'] = '6'*64
        r['build']['executable_sha256'] = '7'*64
        r['candidate_files']['src/render.rs'] = '8'*64
        self.assertEqual(gates.check(self.gate, r)['status'], 'passed')

    def test_wide_import_closure_is_complete_and_separate_from_the_fixed_driver(self):
        modules = {}
        for directory in ('tests', 'tools'):
            for path in (ROOT/directory).glob('*.py'):
                modules.setdefault(path.stem, set()).add(path.relative_to(ROOT).as_posix())
        for driver, harness in [('tools/measure_wide_native.py', gates.WIDE_HARNESS),
                                ('tools/measure_native_layout.py', gates.LAYOUT_HARNESS),
                                ('tools/measure_native_filter.py', gates.FILTER_HARNESS),
                                ('tools/measure_native_shadow.py', gates.SHADOW_HARNESS),
                                ('tools/measure_native_retouch.py', gates.RETOUCH_HARNESS),
                                ('tools/measure_native_brush.py', gates.BRUSH_HARNESS)]:
            pending = [driver]; seen = set()
            while pending:
                name = pending.pop()
                if name in seen: continue
                seen.add(name)
                for node in ast.walk(ast.parse((ROOT/name).read_text(encoding='utf-8'))):
                    names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ''] if isinstance(node, ast.ImportFrom) else []
                    for name in names: pending.extend(modules.get(name.split('.')[0], ()))
            self.assertEqual(seen, set(harness))
            self.assertTrue(set(gates.HARNESS) < seen)

    def test_native_layout_requires_its_own_fixture_and_cannot_replace_either_suite(self):
        r = copy.deepcopy(self.report)
        r['suite'] = 'native-layout-v1'
        r['selected_cases'] = ['mixed-native-5000']
        for row in r['rows']: row['case'] = 'mixed-native-5000'
        with self.assertRaises(KeyError): gates.create(r, '4'*64, 'Missing layout fixture')
        r['candidate_files'].update({name: '3'*64 for name in gates.LAYOUT_HARNESS})
        gate = gates.create(r, '4'*64, 'Original layout records only')
        self.assertEqual(gates.check(gate, r)['status'], 'passed')
        self.assertEqual(gates.check(self.gate, r)['status'], 'ineligible')
        self.assertEqual(gates.check(gate, self.report)['status'], 'ineligible')
        self.assertEqual(gates.check(gate, baseline_tests.report())['status'], 'ineligible')
        r['candidate_files']['tools/native_layout_workload.py'] = '9'*64
        self.assertEqual(gates.check(gate, r)['status'], 'ineligible')

    def test_unknown_missing_and_extra_baseline_metrics_cannot_relax_the_gate(self):
        for change in ('unknown', 'missing', 'extra'):
            gate = copy.deepcopy(self.gate)
            if change == 'unknown': gate['baseline']['suite'] = 'future-suite'
            elif change == 'missing': gate['baseline']['metrics'].clear()
            else: gate['baseline']['metrics']['ignored-case'] = gate['baseline']['metrics']['wide-mixed-native']
            self.assertEqual(gates.check(gate, self.report)['status'], 'ineligible')

    def test_native_filter_gate_retains_every_native_output_and_its_own_oracle(self):
        r=copy.deepcopy(self.report)
        r['suite']='native-filter-v1';r['selected_cases']=['native-box-blur']
        for row in r['rows']: row['case']='native-box-blur'
        r['candidate_files'].update({name:'3'*64 for name in gates.FILTER_HARNESS})
        gate=gates.create(r,'4'*64,'Original filter records only')
        self.assertEqual(gates.check(gate,r)['status'],'passed')
        self.assertEqual(gates.check(self.gate,r)['status'],'ineligible')
        self.assertEqual(gates.check(gate,self.report)['status'],'ineligible')
        for field in ('calls','checks'):
            for index in range(len(r['rows'][0][field])):
                broken=copy.deepcopy(r);broken['rows'][0][field].pop(index)
                self.assertEqual(gates.check(gate,broken)['status'],'ineligible')
        for name in gates.FILTER_HARNESS:
            changed=copy.deepcopy(r);changed['candidate_files'][name]='9'*64
            self.assertEqual(gates.check(gate,changed)['status'],'ineligible')


    def test_native_shadow_requires_all_outputs_and_its_separate_original_oracle(self):
        r=copy.deepcopy(self.report)
        r['suite']='native-shadow-v1';r['selected_cases']=['native-shadow-history']
        for row in r['rows']: row['case']='native-shadow-history'
        r['candidate_files'].update({name:'3'*64 for name in gates.SHADOW_HARNESS})
        gate=gates.create(r,'4'*64,'Original shadow records only')
        self.assertEqual(gates.check(gate,r)['status'],'passed')
        self.assertEqual(gates.check(self.gate,r)['status'],'ineligible')
        self.assertEqual(gates.check(gate,self.report)['status'],'ineligible')
        self.assertEqual(gates.check(gate,baseline_tests.report())['status'],'ineligible')
        for field in ('calls','checks'):
            for index in range(len(r['rows'][0][field])):
                broken=copy.deepcopy(r);broken['rows'][0][field].pop(index)
                self.assertEqual(gates.check(gate,broken)['status'],'ineligible')
        for name in gates.SHADOW_HARNESS:
            changed=copy.deepcopy(r);changed['candidate_files'][name]='9'*64
            self.assertEqual(gates.check(gate,changed)['status'],'ineligible')


    def test_native_retouch_requires_all_original_steps_and_its_own_fixture(self):
        r=copy.deepcopy(self.report)
        r['suite']='native-retouch-v1';r['selected_cases']=['native-retouch-history']
        for row in r['rows']:row['case']='native-retouch-history'
        r['candidate_files'].update({name:'3'*64 for name in gates.RETOUCH_HARNESS})
        gate=gates.create(r,'4'*64,'Original native retouch records only')
        self.assertEqual(gates.check(gate,r)['status'],'passed')
        self.assertEqual(gates.check(self.gate,r)['status'],'ineligible')
        self.assertEqual(gates.check(gate,self.report)['status'],'ineligible')
        for field in ('calls','checks'):
            for i in range(len(r['rows'][0][field])):
                broken=copy.deepcopy(r);broken['rows'][0][field].pop(i)
                self.assertEqual(gates.check(gate,broken)['status'],'ineligible')
        for name in gates.RETOUCH_HARNESS:
            changed=copy.deepcopy(r);changed['candidate_files'][name]='9'*64
            self.assertEqual(gates.check(gate,changed)['status'],'ineligible')

    def test_native_brush_requires_all_original_steps_and_its_own_fixture(self):
        r=copy.deepcopy(self.report)
        r['suite']='native-brush-v1';r['selected_cases']=['native-brush-history']
        for row in r['rows']:row['case']='native-brush-history'
        r['candidate_files'].update({name:'3'*64 for name in gates.BRUSH_HARNESS})
        gate=gates.create(r,'4'*64,'Original native brush records only')
        self.assertEqual(gates.check(gate,r)['status'],'passed')
        self.assertEqual(gates.check(self.gate,r)['status'],'ineligible')
        self.assertEqual(gates.check(gate,self.report)['status'],'ineligible')
        for field in ('calls','checks'):
            for i in range(len(r['rows'][0][field])):
                broken=copy.deepcopy(r);broken['rows'][0][field].pop(i)
                self.assertEqual(gates.check(gate,broken)['status'],'ineligible')
        for name in gates.BRUSH_HARNESS:
            changed=copy.deepcopy(r);changed['candidate_files'][name]='9'*64
            self.assertEqual(gates.check(gate,changed)['status'],'ineligible')


if __name__ == '__main__': unittest.main()
