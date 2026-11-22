"""Exercise the placed-still judge without either external release binary."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_cli import ROOT
from test_editing_cli import png_pixels
from test_images_cli import png

sys.path.insert(0, str(ROOT / 'tools'))
from benchmark_runtime import TaskFailure, Trial
from compare_placed_still import run_trial


class PlacedStillJudgeTests(unittest.TestCase):
    def test_historical_pixels_and_source_preservation_are_required(self):
        for fault, message in [('none', None), ('latest-as-history', 'pixels differ'),
                               ('overwrite-observed', 'Changed preview'), ('overwrite-input', 'Source or retained')]:
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as folder:
                case = Trial(None, Path(folder) / 'trial', 'placed-still', 1, 'cli', ())

                def frames(trial, observe):
                    width, height, paper, _ = png_pixels((trial.root / 'paper.png').read_bytes())
                    w, h, badge, _ = png_pixels((trial.root / 'badge.png').read_bytes())
                    for step, (left, top) in [('before', (3, 5)), ('after', (17, 12)), ('historical', (3, 5))]:
                        if step == 'historical' and fault == 'latest-as-history':
                            left, top = 17, 12
                        image = bytearray(paper)
                        for i in range(w * h):
                            pixel = badge[4 * i:4 * i + 4]
                            if pixel[3]:
                                offset = 4 * ((top + i // w) * width + left + i % w)
                                image[offset:offset + 4] = pixel
                        (trial.root / (step + '.png')).write_bytes(png(width, height, image))
                        observe(step)
                    if fault == 'overwrite-observed':
                        (trial.root / 'before.png').write_bytes((trial.root / 'after.png').read_bytes())
                    if fault == 'overwrite-input':
                        (trial.root / 'badge.png').write_bytes(b'changed')

                def decode(argv, **kwargs):
                    path = Path(argv[argv.index('-i') + 1])
                    return SimpleNamespace(stdout=png_pixels(path.read_bytes())[2])

                row = {}
                with patch('compare_placed_still.subprocess.run', side_effect=decode):
                    if message is None:
                        run_trial(case, frames, Path('decoder'), row)
                        self.assertEqual(row['status'], 'passed')
                        self.assertLessEqual(row['first_verified_preview_seconds'], row['solve_seconds'])
                    else:
                        with self.assertRaisesRegex(TaskFailure, message):
                            run_trial(case, frames, Path('decoder'), row)
                        self.assertNotIn('first_verified_preview_seconds', row)
