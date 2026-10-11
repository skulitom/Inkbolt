"""Separated judges must accept other solver IDs and reject plausible wrong deliveries."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

from test_cli import EXE, ROOT
sys.path.insert(0, str(ROOT/'tools'))
from benchmark_diagram import fixture, solve, judge, PROMPT
from benchmark_runtime import Trial, TaskFailure
from benchmark_tasks import CHECKS
from workload_cases import sha


class BenchmarkDiagramTests(unittest.TestCase):
    def prepare(self, root, transport='cli'):
        trial = Trial(EXE, root, 'B01', 1, transport, CHECKS['B01'])
        self.addCleanup(trial.close)
        fixture(trial)
        trial.begin(PROMPT.read_text(encoding='utf-8'))
        solve(trial)
        return trial

    def test_judge_accepts_different_object_font_and_document_ids_without_solver_results(self):
        with tempfile.TemporaryDirectory() as directory:
            trial = self.prepare(Path(directory)/'different')
            path = trial.root/'editable.json'
            doc = json.loads(path.read_bytes())
            doc['id'] = 'another-author'
            doc['fonts']['chosen-font'] = doc['fonts'].pop('face')
            doc['items'] = list(reversed(doc['items'][:3])) + list(reversed(doc['items'][3:]))
            for index, item in enumerate(doc['items']):
                item['id'] = f'independent-{index}'
                if item['content']['type'] == 'text':
                    item['content']['frame']['style']['font_id'] = 'chosen-font'
            path.write_text(json.dumps(doc), encoding='utf-8')
            trial.results.clear()
            trial.begin_judging()
            judge(trial)
            trial.verified_preview((trial.root/'preview.png').read_bytes())
            row = trial.finish()
            self.assertEqual(row['status'], 'passed', row)
            self.assertIsNone(row['first_verified_preview_seconds'])  # Judge rendering cannot supply a solve preview.
            self.assertEqual(row['prompt_sha256'], sha((trial.root/'task.txt').read_bytes()))
            self.assertFalse(row['model_trials'])
            self.assertIsNone(row['token_usage'])

    def test_altered_artifacts_and_font_bindings_fail_even_with_good_solver_responses(self):
        for alteration in ['geometry', 'font', 'png', 'visibility', 'source', 'prompt']:
            with self.subTest(alteration=alteration), tempfile.TemporaryDirectory() as directory:
                trial = self.prepare(Path(directory)/alteration)
                path = trial.root/'editable.json'
                doc = json.loads(path.read_bytes())
                if alteration == 'geometry':
                    doc['items'][0]['content']['geometry']['width'] = 47
                elif alteration == 'font':
                    doc['fonts']['face']['license_sha256'] = '0'*64
                elif alteration == 'visibility':
                    doc['items'][0]['visible'] = False
                elif alteration == 'png':
                    (trial.root/'preview.png').write_bytes(b'not a PNG')
                elif alteration == 'source':
                    (trial.root/'original.ttf').write_bytes(b'changed input')
                else:
                    (trial.root/'task.txt').write_bytes(b'changed prompt')
                path.write_text(json.dumps(doc), encoding='utf-8')
                trial.begin_judging()
                try:
                    judge(trial)
                except (TaskFailure, ValueError, KeyError) as error:
                    trial.error = str(error)
                self.assertEqual(trial.finish()['status'], 'failed')

    def test_both_transports_separate_judge_traffic_and_preserve_every_raw_byte(self):
        for transport in ['cli', 'mcp']:
            with self.subTest(transport=transport), tempfile.TemporaryDirectory() as directory:
                trial = self.prepare(Path(directory)/transport, transport)
                trial.begin_judging()
                judge(trial)
                trial.verified_preview((trial.root/'preview.png').read_bytes())
                row = trial.finish()
                self.assertEqual(row['status'], 'passed', row)
                self.assertTrue(row['judge_separated'])
                self.assertEqual(row['judge_engine_commands'], 2)
                self.assertEqual(row['engine_commands'], 5)
                self.assertGreater(row['first_verified_preview_seconds'], 0)
                self.assertLessEqual(row['first_verified_preview_seconds'], row['scripted_wall_seconds'])
                traffic = row['calls'] if transport == 'cli' else row['protocol']
                wire_bytes = dict(request=sum(p.stat().st_size for p in trial.root.glob('*.request.json')),
                                  response=sum(p.stat().st_size for p in trial.root.glob('*.response.json')))
                for direction in ['request', 'response']:
                    key = direction+'_bytes'
                    self.assertEqual(row[key], sum(r[key] for r in traffic if r['phase'] != 'judge'))
                    self.assertEqual(row[key]+row['judge_'+key], wire_bytes[direction])

    def test_judge_calls_alone_cannot_count_as_a_successful_solve(self):
        with tempfile.TemporaryDirectory() as directory:
            trial = Trial(EXE, Path(directory)/'no-solve', 'B01', 1, 'cli', [])
            trial.begin('Original test prompt')
            trial.begin_judging()
            trial.call('judge-only', 'preset.list')
            row = trial.finish()
            self.assertEqual(row['status'], 'failed')
            self.assertEqual(row['engine_commands'], 0)
            self.assertEqual(row['judge_engine_commands'], 1)


if __name__ == '__main__':
    unittest.main()
