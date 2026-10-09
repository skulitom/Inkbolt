"""Full native photographic task and a fixed, fail-closed process-memory budget."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

from test_cli import EXE,ROOT
sys.path.insert(0,str(ROOT/'tools'))
from agent_benchmark import run_task
from benchmark_photo import check_memory,MAX_PEAK_COMMIT_BYTES
from benchmark_runtime import TaskFailure
from benchmark_tasks import CHECKS


class PhotoBenchmarkTests(unittest.TestCase):
    def test_complete_native_photo_task_on_cli_and_mcp(self):
        with tempfile.TemporaryDirectory() as directory:
            for transport in ('cli','mcp'):
                with self.subTest(transport=transport):
                    root=Path(directory)/transport
                    row=run_task(EXE,root,'B10',1,transport)
                    self.assertEqual(row['status'],'passed',json.dumps(row,indent=2))
                    self.assertEqual(set(c['name'] for c in row['checks']),set(CHECKS['B10'])|{'source-preservation'})
                    self.assertTrue(row['memory_complete'])
                    self.assertGreater(row['peak_commit_bytes'],0)
                    self.assertLessEqual(row['peak_commit_bytes'],MAX_PEAK_COMMIT_BYTES)
                    budget=json.loads((root/'memory-budget.json').read_bytes())
                    self.assertEqual(budget['maximum_peak_commit_bytes'],256*1024*1024)
                    check_memory(budget['observations'])
                    self.assertEqual(row['request_bytes'],sum(p.stat().st_size for p in root.glob('*.request.json')))
                    self.assertEqual(row['response_bytes'],sum(p.stat().st_size for p in root.glob('*.response.json')))
                    self.assertGreater(row['first_verified_preview_seconds'],0)
                    self.assertFalse(row['model_trials']);self.assertIsNone(row['token_usage'])

    def test_missing_zero_and_over_budget_observations_cannot_pass(self):
        check_memory([dict(available=True,peak_commit_bytes=MAX_PEAK_COMMIT_BYTES)])
        for observations in ([],[None],[dict(available=False)],
            [dict(available=True,peak_commit_bytes=0)],
            [dict(available=True,peak_commit_bytes=MAX_PEAK_COMMIT_BYTES+1)]):
            with self.subTest(observations=observations),self.assertRaises(TaskFailure):check_memory(observations)


if __name__=='__main__':unittest.main()
