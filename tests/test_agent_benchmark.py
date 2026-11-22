"""Benchmark evidence must reflect actual transport, required outcomes and failures."""
import copy
import io
from pathlib import Path
import queue
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_cli import EXE, ROOT
sys.path.insert(0,str(ROOT/'tools'))
from agent_benchmark import run_task, aggregate
from benchmark_reference_checks import reference_task
from benchmark_tasks import TASKS, CHECKS
from benchmark_adapters import ADAPTERS
from benchmark_graphics import pixels, png_check
from benchmark_runtime import Trial, TaskFailure, strict_json, Mcp
from test_images_cli import png


class AgentBenchmarkTests(unittest.TestCase):
    def test_verified_file_preview_requires_matching_observed_solve_publication(self):
        raw=png(1,1,bytes([20,80,150,255]))
        from workload_cases import sha
        for fault in ('none','hash','size','format','media','judge','lost','failed','missing','command'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as directory:
                case=Trial(None,Path(directory)/'publication','B12',1,'cli',[])
                result=dict(format='png',media_type='image/png',bytes=len(raw),sha256=sha(raw))
                row=dict(step='chosen-by-client',phase='task',status='success',response_observed=True,
                         command='document.publish',completed_task_seconds=.25)
                if fault=='hash':result['sha256']='0'*64
                elif fault=='size':result['bytes']+=1
                elif fault=='format':result['format']='snapshot'
                elif fault=='media':result['media_type']='application/json'
                elif fault=='judge':row['phase']='judge'
                elif fault=='lost':row['response_observed']=False
                elif fault=='failed':row['status']='failure'
                elif fault=='command':row['command']='document.validate'
                case.calls.append(row)
                if fault!='missing':case.results[row['step']]=dict(result=result)
                case.verified_preview(raw)
                self.assertEqual(case.first_preview,.25 if fault=='none' else None)
                case.close()

    def test_fixed_twenty_outcomes_match_the_accepted_plan_and_open_tasks_stay_visible(self):
        text=(ROOT/'docs/AGENT_READINESS.md').read_text(encoding='utf-8')
        self.assertEqual(list(TASKS),[f'B{i:02d}' for i in range(1,21)])
        self.assertEqual(set(ADAPTERS),set(CHECKS))
        for task,(title,outcome) in TASKS.items():
            self.assertIn(f'| {task} | {title} | {outcome} |',text)
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(ADAPTERS,{k:v for k,v in ADAPTERS.items() if k!='B20'},clear=True):
                row=run_task(EXE,Path(directory)/'open','B20',1,'cli')
            self.assertEqual(row['status'],'not_implemented')
            summary=aggregate([row])
            self.assertEqual(len(summary),20)
            self.assertEqual(summary[-1]['not_implemented'],1)
            self.assertEqual(sum(v['passed'] for v in summary),0)

    @reference_task('B01')
    def test_diagram_reference_on_cli_and_mcp(self, row):
        self.assertEqual(row['engine_commands'], 5)
        self.assertEqual(row['judge_engine_commands'], 2)

    def test_every_standard_reference_has_one_discovered_transport_pair(self):
        loader = unittest.TestLoader()
        pending = list(loader.discover(str(ROOT / 'tests'), pattern='test_*benchmark*.py'))
        self.assertFalse(loader.errors, loader.errors)
        tasks = []
        while pending:
            test = pending.pop()
            if isinstance(test, unittest.TestSuite):
                pending.extend(test)
                continue
            method = getattr(test, test._testMethodName)
            task = getattr(method, 'reference_task', None)
            if task:
                self.assertFalse(getattr(method, '__unittest_skip__', False), test.id())
                self.assertFalse(getattr(type(test), '__unittest_skip__', False), test.id())
                tasks.append(task)
        # Photo memory, controlled recovery and external handoff have dedicated
        # platform and tool contracts. Their existing tests cover them separately.
        self.assertCountEqual(tasks, set(ADAPTERS) - {'B10', 'B19', 'B20'})

    def test_missing_checks_unexpected_errors_and_invalid_retry_claims_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            trial=Trial(EXE,Path(directory)/'incomplete','B01',1,'cli',['must-prove'])
            trial.begin('Original test task')
            trial.call('catalog','preset.list')
            self.assertEqual(trial.finish()['status'],'failed')
            failed=Trial(EXE,Path(directory)/'failed','B01',1,'cli',[])
            failed.begin('Original error probe')
            with self.assertRaises(TaskFailure): failed.call('invalid','document.create',id='x',kind='vector',width=0,height=1)
            self.assertEqual(failed.finish()['status'],'failed')
            retry=Trial(EXE,Path(directory)/'retry','B01',1,'cli',[])
            retry.begin('Original retry probe');retry.call('catalog','preset.list')
            with self.assertRaises(TaskFailure):retry.call('not-a-retry','capabilities',retry_of='catalog')
            with self.assertRaises(TaskFailure):retry.call('worker','job.list')
            retry.close()

    def test_oracles_reject_wrong_pixels_dimensions_false_checks_and_malformed_json(self):
        expected=pixels(2,2,[(0,0,1,1,[1,2,3,255])])
        png_check(png(2,2,expected),2,2,expected)
        changed=bytearray(expected);changed[0]=9
        with self.assertRaises(TaskFailure):png_check(png(2,2,changed),2,2,expected)
        with self.assertRaises(TaskFailure):png_check(png(2,2,expected),1,4,expected)
        for raw in [b'{"ok":true,"ok":false}',b'{"value":NaN}',b'{}{}']:
            with self.assertRaises(ValueError):strict_json(raw)
        with tempfile.TemporaryDirectory() as directory:
            trial=Trial(EXE,Path(directory)/'false','B01',1,'cli',['oracle'])
            trial.begin('Original oracle probe');trial.call('catalog','preset.list')
            trial.check('oracle',lambda:False)
            self.assertEqual(trial.finish()['status'],'failed')

    def test_failed_metrics_remain_in_distributions_and_missing_metrics_are_not_zero(self):
        rows=[dict(task='B01',status='passed',engine_roundtrip_seconds=10),
              dict(task='B01',status='failed',engine_roundtrip_seconds=1)]
        report=aggregate(copy.deepcopy(rows))[0]
        self.assertEqual((report['passed'],report['failed']),(1,1))
        self.assertEqual(report['observations']['engine_roundtrip_seconds']['count'],2)
        self.assertIsNone(report['observations']['peak_commit_bytes'])
        self.assertIsNone(report['observations']['peak_resident_bytes'])

    def test_rejected_mcp_framing_and_response_identity_retain_observed_wire_bytes(self):
        for raw in [b'{"jsonrpc":"2.0","id":1,"result":{}}',
                    b'{"jsonrpc":"2.0","id":2,"result":{}}\n',
                    b'{"jsonrpc":"2.0","id":1,"error":{"code":-32600}}\n']:
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as directory:
                root=Path(directory)/'malformed'
                trial=Trial(EXE,root,'B01',1,'cli',[])
                # Controlled transport faults exercise the real parser and
                # recorder without requiring a malformed engine binary.
                server=object.__new__(Mcp)
                server.case=trial;server.rid=0
                server.process=SimpleNamespace(stdin=io.BytesIO())
                server.lines=queue.Queue();server.lines.put(raw)
                with self.assertRaises(TaskFailure):server.request('fault','tools/list')
                self.assertEqual(next(root.glob('*.response.json')).read_bytes(),raw)
                self.assertEqual(trial.protocol[0]['response_bytes'],len(raw))
                self.assertEqual(trial.protocol[0]['status'],'failure')


if __name__=='__main__':unittest.main()
