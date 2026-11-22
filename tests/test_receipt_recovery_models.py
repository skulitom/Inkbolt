"""A plausible receipt file cannot substitute for a replay and a fresh history read."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from test_cli import EXE, ROOT
sys.path.insert(0, str(ROOT / 'tools'))
from benchmark_runtime import canonical, read_json
from judge_receipt_recovery_models import creation, durable_checks, exact_file, matches_history, recorded_recovery
from run_receipt_recovery_models import prepare
from workload_cases import save_json


class ReceiptRecoveryModelTests(unittest.TestCase):
    def test_recorder_requires_the_withheld_receipt_replay_conflict_and_subsequent_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work, evidence = root / 'workspace', root / 'evidence'
            work.mkdir()
            evidence.mkdir()
            prepare(work, evidence, 'inkbolt', {'inkbolt': EXE})
            self.assertFalse((work / 'receipt.json').exists())
            original = read_json(evidence / 'withheld-response.json')['result']
            recorder = work / '.trial-tools'
            log = recorder / 'traffic'
            log.mkdir(parents=True)
            shutil.copyfile(ROOT / 'tools/placed_still_cli.py', recorder / 'engine.py')
            save_json(recorder / 'launch.json', dict(executable=str(EXE), environment={}))
            started = time.time_ns()

            def call(request, expected=0):
                result = subprocess.run([sys.executable, str(recorder / 'engine.py')], cwd=work,
                                        input=canonical(request), capture_output=True, timeout=30)
                self.assertEqual(result.returncode, expected, result.stdout)
                return json.loads(result.stdout)

            key = dict(session_id='study')
            history = dict(command='session.history', limit=2, **key)
            found = call(dict(command='session.receipt', request_id='create', **key))
            save_json(work / 'receipt.json', found['result']['receipt'])
            self.assertTrue(exact_file(work / 'receipt.json', original['receipt']))
            call(read_json(work / 'create-request.json'))
            call(history)
            call(creation('inkbolt', 193), expected=1)
            call(dict(command='session.read', **key))
            checks, metrics = recorded_recovery(log, 'inkbolt', original, started)
            self.assertEqual([name for name, passed in checks.items() if not passed], ['history_after_conflict'])
            self.assertEqual(metrics['calls'], 5)
            self.assertGreater(metrics['first_receipt_response_seconds'], 0)
            call(history)
            self.assertTrue(all(recorded_recovery(log, 'inkbolt', original, started)[0].values()))
            save_json(work / 'bad-head.json', dict(revision=False))
            self.assertFalse(exact_file(work / 'bad-head.json', dict(revision=0)))
            healthy, errors = durable_checks(work, 'inkbolt', EXE, original)
            self.assertTrue(all(healthy.values()), errors)
            (work / '.inkbolt').rename(root / 'removed-session')
            missing, errors = durable_checks(work, 'inkbolt', EXE, original)
            self.assertFalse(any(missing.values()))
            self.assertEqual(set(errors), set(missing))
            self.assertFalse((work / '.inkbolt').exists())


    def test_cutbolt_history_summary_must_account_for_the_original_creation_only(self):
        receipt = dict(action='create', request_id='create', parent_revision=None, restored_from=None,
                       revision=0, project_id='study', changes=dict(clips=[]))
        entry = dict(action='create', request_id='create', parent_revision=None, restored_from=None,
                     revision=0, changed_clips=0)
        history = dict(entries=[entry], next_before_revision=None)
        self.assertTrue(matches_history('cutbolt', history, receipt))
        for changed in (dict(history, entries=[entry, entry]), dict(history, next_before_revision=1),
                        dict(history, entries=[dict(entry, changed_clips=2)]),
                        dict(history, entries=[dict(entry, request_id='other')])):
            self.assertFalse(matches_history('cutbolt', changed, receipt))
