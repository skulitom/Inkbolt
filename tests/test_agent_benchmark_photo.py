"""Full native photographic task and a fixed, fail-closed process-memory budget."""
import json
import os
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
                    self.assertEqual(row['status'],'passed' if os.name=='nt' else 'failed',
                                     dict(error=row['error'],checks=row['checks'],missing=row['missing_checks']))
                    self.assertEqual({c['name'] for c in row['checks'] if c['status']=='fail'},
                                     set() if os.name=='nt' else {'memory-budget'})
                    self.assertEqual(set(c['name'] for c in row['checks']),set(CHECKS['B10'])|{'source-preservation'})
                    self.assertEqual(row['memory_complete'],os.name=='nt')
                    if os.name=='nt':
                        self.assertGreater(row['peak_commit_bytes'],0)
                        self.assertLessEqual(row['peak_commit_bytes'],MAX_PEAK_COMMIT_BYTES)
                    budget=json.loads((root/'memory-budget.json').read_bytes())
                    self.assertEqual(budget['maximum_peak_commit_bytes'],256*1024*1024)
                    if os.name=='nt':check_memory(budget['observations'])
                    for direction in ('request','response'):
                        self.assertEqual(row[direction+'_bytes']+row['judge_'+direction+'_bytes'],
                                         sum(p.stat().st_size for p in root.glob('*.'+direction+'.json')))
                    self.assertTrue(row['judge_separated'])
                    self.assertEqual(row['engine_commands'],14)
                    self.assertEqual(row['judge_engine_commands'],9)
                    self.assertEqual(row['sources']['original.png'],'f779277bae78c973c8cb229b014bc4771fe25de47879d868c220f792077d9958')
                    self.assertGreater(row['first_verified_preview_seconds'],0)
                    self.assertFalse(row['model_trials']);self.assertIsNone(row['token_usage'])

    def test_missing_zero_and_over_budget_observations_cannot_pass(self):
        check_memory([dict(available=True,peak_commit_bytes=MAX_PEAK_COMMIT_BYTES)])
        for observations in ([],[None],[dict(available=False)],
            [dict(available=1,peak_commit_bytes=1)],[dict(available=True,peak_commit_bytes=True)],
            [dict(available=True,peak_commit_bytes=1.5)],[dict(available=True)],
            [dict(available=True,peak_commit_bytes=0)],
            [dict(available=True,peak_commit_bytes=MAX_PEAK_COMMIT_BYTES+1)]):
            with self.subTest(observations=observations),self.assertRaises(TaskFailure):check_memory(observations)


if __name__=='__main__':unittest.main()
