"""A correct thumbnail alone cannot establish saved history or preview latency."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_cli import EXE, ROOT
from test_editing_cli import png_pixels
from test_images_cli import png

sys.path.insert(0, str(ROOT / 'tools'))
from benchmark_runtime import Trial
from compare_placed_still import artwork, inkbolt, WIDTH, HEIGHT, BADGE_WIDTH, BADGE_HEIGHT
from judge_placed_still_models import score, traffic
from workload_cases import save_json, sha


class ModelPlacementTests(unittest.TestCase):
    def test_reopen_both_named_revisions_and_independently_read_the_current_head(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'workspace'
            trial = Trial(EXE, root, 'placement', 1, 'cli', ())
            paper, badge = artwork()
            trial.source('paper.png', png(WIDTH, HEIGHT, paper))
            trial.source('badge.png', png(BADGE_WIDTH, BADGE_HEIGHT, badge))
            trial.begin('Create both revisions')
            inkbolt(trial, lambda step: None)
            revisions = root / 'revisions.json'
            save_json(revisions, dict(original_revision=0, moved_revision=1))
            before = (root / 'before.png').read_bytes()
            samples = [dict(file='before.png', sha256='a' * 64, seconds=1),
                       dict(file='elsewhere.png', sha256=sha(before), seconds=2),
                       dict(file='before.png', sha256=sha(before), seconds=3)]
            paths = dict(inkbolt=EXE, ffmpeg=Path('decoder'), ffprobe=Path('probe'))
            with patch('judge_placed_still_models.preview_rgba', side_effect=lambda path, _: png_pixels(path.read_bytes())[2]):
                def run():
                    return score(root, 'inkbolt', paths, trial.sources, samples)

                accepted = run()
                self.assertTrue(accepted['saved_workflow_passed'], accepted['errors'])
                self.assertEqual(accepted['first_correct_before_seconds'], 3)
                revisions.write_text('{"original_revision":0,"moved_revision":42}')
                missing = run()
                self.assertTrue(missing['artwork_passed'])
                self.assertFalse(missing['checks']['saved_moved'])
                self.assertFalse(missing['saved_workflow_passed'])
                revisions.write_text('{"original_revision":0,"moved_revision":1}')
                trial.call('move-again', 'session.apply', session_id='placement', request_id='extra', expected_revision=1,
                           action=dict(type='edit', operations=[dict(op='transform', id='badge', matrix=[1, 0, 0, 1, 0, 0])]))
                changed = run()
                self.assertTrue(changed['checks']['saved_moved'])
                self.assertFalse(changed['checks']['saved_current'])

    def test_historical_response_must_bind_the_right_session_bytes_and_order(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def record(name, request, result, started):
                folder = root / name
                folder.mkdir()
                save_json(folder / 'launch.json', dict(argv=[], started_ns=started))
                save_json(folder / 'input', request)
                save_json(folder / 'stdout', dict(ok=True, result=result))
                save_json(folder / 'exit.json', dict(code=0, finished_ns=started + 1))
            ref = dict(revision=1, project_id='placement')
            digest = 'a' * 64
            preview = dict(command='preview.frame', project=ref, output='historical.png')
            revisions = dict(original_revision=1, moved_revision=2)
            record('first', preview, dict(sha256=digest), 10)
            record('move', dict(command='session.apply'), dict(revision=2, project_id='placement'), 20)
            record('wrong-image', preview, dict(sha256='b' * 64), 30)
            record('wrong-session', dict(preview, project=dict(ref, project_id='other')), dict(sha256=digest), 40)
            self.assertFalse(traffic(root, revisions, digest)['direct_historical_render_observed'])
            record('reopened', preview, dict(sha256=digest), 50)
            result = traffic(root, revisions, digest)
            self.assertTrue(result['direct_historical_render_observed'])
            self.assertEqual(result['calls'], 5)
            self.assertEqual(result['repeated_requests'], 2)
