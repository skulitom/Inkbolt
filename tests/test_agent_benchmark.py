"""Benchmark evidence must reflect actual transport, required outcomes and failures."""
import copy
import io
import json
from pathlib import Path
import queue
import sys
import tempfile
from types import SimpleNamespace
import unittest

from test_cli import EXE, ROOT
sys.path.insert(0,str(ROOT/'tools'))
from agent_benchmark import run_task, aggregate
from benchmark_tasks import TASKS, CHECKS
from benchmark_adapters import ADAPTERS
from benchmark_graphics import pixels, png_check
from benchmark_runtime import Trial, TaskFailure, strict_json, Mcp
from test_images_cli import png


class AgentBenchmarkTests(unittest.TestCase):
    def test_fixed_twenty_outcomes_match_the_accepted_plan_and_open_tasks_stay_visible(self):
        text=(ROOT/'docs/AGENT_READINESS.md').read_text(encoding='utf-8')
        self.assertEqual(list(TASKS),[f'B{i:02d}' for i in range(1,21)])
        self.assertEqual(set(ADAPTERS),set(CHECKS))
        for task,(title,outcome) in TASKS.items():
            self.assertIn(f'| {task} | {title} | {outcome} |',text)
        with tempfile.TemporaryDirectory() as directory:
            row=run_task(EXE,Path(directory)/'open','B20',1,'cli')
            self.assertEqual(row['status'],'not_implemented')
            summary=aggregate([row])
            self.assertEqual(len(summary),20)
            self.assertEqual(summary[-1]['not_implemented'],1)
            self.assertEqual(sum(v['passed'] for v in summary),0)

    def test_each_scripted_task_passes_its_independent_judge_on_cli_and_compact_mcp(self):
        with tempfile.TemporaryDirectory() as directory:
            for transport in ['cli','mcp']:
                for task in ADAPTERS:
                    if task in ('B10','B19'):continue  # Separate photo/recovery modules keep feedback focused.
                    with self.subTest(transport=transport,task=task):
                        root=Path(directory)/(transport+'-'+task)
                        row=run_task(EXE,root,task,1,transport)
                        self.assertEqual(row['status'],'passed',json.dumps(row,indent=2))
                        self.assertEqual(set(c['name'] for c in row['checks']),set(CHECKS[task])|{'source-preservation'})
                        self.assertEqual(row['request_bytes'],sum(p.stat().st_size for p in root.glob('*.request.json')))
                        self.assertEqual(row['response_bytes'],sum(p.stat().st_size for p in root.glob('*.response.json')))
                        self.assertIsNone(row['token_usage']);self.assertIsNone(row['model_calls'])
                        self.assertFalse(row['model_trials'])
                        self.assertGreater(row['first_verified_preview_seconds'],0)
                        if sys.platform=='win32':
                            self.assertTrue(row['memory_complete'])
                            self.assertGreater(row['peak_commit_bytes'],0)
                        if task=='B17':
                            self.assertEqual(row['retries'],2)
                            lost=next(c for c in row['calls'] if c['step']=='lost')
                            self.assertFalse(lost['response_observed'])
                            self.assertEqual(lost['status'],'response_lost')

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
