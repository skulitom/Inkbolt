"""B03 independent delivered pixels, editable geometry and session history checks."""
import json
from functools import lru_cache
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_cli import EXE, ROOT
sys.path.insert(0, str(ROOT / 'tools'))
from benchmark_large_layout import fixture, solve, judge, PROMPT, expected_picture, retained_session_store
from benchmark_runtime import Trial, TaskFailure
from benchmark_graphics import png_check
from benchmark_tasks import CHECKS
from test_images_cli import png
from workload_cases import sha


class LargeLayoutJudgeTests(unittest.TestCase):
    def prepare(self, root, alternate_session=False):
        trial = Trial(EXE, root, 'B03', 1, 'cli', CHECKS['B03'])
        self.addCleanup(trial.close)
        if alternate_session:
            original = trial.call
            def call(step, command, **arguments):
                if arguments.get('session_id') == 'work': arguments['session_id'] = 'artist-layout'
                return original('artist-'+step, command, **arguments)
            trial.call = call
        fixture(trial); trial.begin(PROMPT.read_text(encoding='utf-8')); solve(trial)
        return trial

    def test_judge_uses_deliveries_and_the_authors_session_id(self):
        with tempfile.TemporaryDirectory() as directory:
            trial = self.prepare(Path(directory)/'alternate', alternate_session=True)
            trial.results.clear(); trial.begin_judging(); judge(trial)
            row = trial.finish()
            self.assertEqual(row['status'], 'passed', row)
            self.assertIsNone(row['first_verified_preview_seconds'])
            self.assertEqual(json.loads((trial.root/'session.json').read_bytes())['session_id'], 'artist-layout')

    def test_correct_logs_cannot_hide_collateral_edits_or_false_history(self):
        # Reuse only identical raw PNG/dimension/expected-pixel tuples within
        # this mutation test. Engines still render and every changed image is
        # decoded; repeated correct images need not repeat the Python decoder.
        with tempfile.TemporaryDirectory() as directory, \
             patch('benchmark_large_layout.png_check', lru_cache(maxsize=8)(png_check)):
            trial = self.prepare(Path(directory)/'delivery')
            originals = {name:(trial.root/name).read_bytes() for name in
                ('editable.json','preview.png','historical.png','session.json','source.json')}
            call, check = trial.call, trial.check
            # Preserve correct solver logs, but give each independent mutation
            # unique judge log names. Stop only after a real oracle rejects it.
            trial.call = lambda step, command, **kw: call(alteration+'-'+step, command, **kw)
            def reject_early(name, oracle, **kw):
                if not check(name, oracle, **kw):
                    raise TaskFailure('Independent check rejected '+name)
            trial.check = reject_early
            trial.begin_judging()
            for alteration in ('other-transform','controls','paint','id','order','canvas','metadata',
                               'pixels','historical','revisions','other-session','missing','newer-head','source'):
                with self.subTest(alteration=alteration):
                    for name, raw in originals.items(): (trial.root/name).write_bytes(raw)
                    trial.checks.clear()
                    self.reject_mutation(trial, alteration)

    def reject_mutation(self, trial, alteration):
        path = trial.root/'editable.json'; document = json.loads(path.read_bytes())
        if alteration == 'other-transform': document['items'][17]['transform'][4] = 1
        elif alteration == 'controls': document['items'][2473]['content']['geometry']['x'] += 1
        elif alteration == 'paint': document['items'][17]['content']['fill'] = [0,0,0,255]
        elif alteration == 'id': document['items'][17]['id'] = 'changed'
        elif alteration == 'order': document['items'][17],document['items'][18] = document['items'][18],document['items'][17]
        elif alteration == 'canvas': document['width'] = 999
        elif alteration == 'metadata': document['metadata'] = {'title':'unrequested'}
        elif alteration == 'pixels': (trial.root/'preview.png').write_bytes(png(1000,500,expected_picture(False)))
        elif alteration == 'historical': (trial.root/'historical.png').write_bytes(png(1000,500,expected_picture()))
        elif alteration in ('revisions','other-session'):
            locator = json.loads((trial.root/'session.json').read_bytes())
            if alteration == 'revisions': locator['original_revision'] = 1
            else:
                # A valid independent session is insufficient: its saved
                # current state must equal the delivered edited snapshot.
                trial.call('other-session','session.create',session_id='unrelated',request_id='save',
                    document=dict(file_path='source.json',sha256=trial.sources['source.json']),response_mode='compact')
                trial.call('other-edit','session.apply',session_id='unrelated',request_id='edit',expected_revision=0,
                    action=dict(type='edit',operations=[dict(op='transform',id='cell-2472',matrix=[1,0,0,1,1,1],space='world')]),
                    response_mode='compact')
                locator['session_id'] = 'unrelated'
            (trial.root/'session.json').write_text(json.dumps(locator),encoding='utf-8')
        elif alteration == 'missing': (trial.root/'historical.png').unlink()
        elif alteration == 'newer-head':
            trial.call('later-edit','session.apply',session_id='work',request_id='later',expected_revision=1,
                action=dict(type='edit',operations=[dict(op='transform',id='cell-17',matrix=[1,0,0,1,1,1],space='world')]),
                response_mode='compact')
        else: (trial.root/'source.json').write_bytes(b'{}')
        path.write_text(json.dumps(document),encoding='utf-8')
        with self.assertRaises((TaskFailure,ValueError,KeyError)):
            judge(trial)

    def test_session_location_must_be_unambiguous_and_does_not_waive_database_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            trial = self.prepare(Path(directory)/'locations')
            self.assertEqual(retained_session_store(trial, 'work'), '.inkbolt/sessions')
            with self.assertRaisesRegex(TaskFailure, 'Missing or ambiguous'):
                retained_session_store(trial, 'unknown')
            # A second copy cannot silently replace the session named by the delivery.
            name = sha(b'work')+'.sqlite3'
            duplicate = trial.root/'another-store'; duplicate.mkdir()
            (duplicate/name).write_bytes((trial.root/'.inkbolt/sessions'/name).read_bytes())
            with self.assertRaisesRegex(TaskFailure, 'Missing or ambiguous'):
                retained_session_store(trial, 'work')
            (duplicate/name).unlink()
            (trial.root/'.inkbolt/sessions'/name).write_bytes(b'not a database')
            trial.begin_judging()
            with self.assertRaises(TaskFailure):
                judge(trial)
