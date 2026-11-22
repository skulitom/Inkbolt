"""Capture paired model-driven placements with a caller-selected client and native engines."""
from pathlib import Path

from compare_placed_still import BADGE_HEIGHT, BADGE_WIDTH, HEIGHT, PREVIEWS, WIDTH, artwork
from matched_cli_models import Workflow, collect as collect_trial, run_trials
from workload_cases import png, save


PROMPT = """Use the supplied local graphics engine to place a still image, revise its position and review the saved original.

paper.png fills a 32 by 24 canvas. Place badge.png at its original size with its top-left corner at (3,5), measured from the top left of the canvas. Preserve transparency over the paper. Save this composition in the engine's default workspace session store under the ID placement. Export a full-resolution PNG of this saved arrangement as before.png.

Move only the badge so its top-left corner is at (17,12). Save the change as a later revision of that same session and export after.png. After the move, reopen the earlier saved revision and export historical.png. Leave the current session showing the moved badge. Keep the source images and everything the engine needs to reopen both revisions.

Deliver the three PNGs at the workspace root. Also write revisions.json there with two integer fields, original_revision and moved_revision, identifying the saved versions. Use the engine for the actual compositing, saving and rendering. Use the shell for discovery, preparing requests and writing delivered files. Run synchronous commands and render each requested preview from its saved revision.
"""


def prepare(workspace, evidence, name, paths):
    paper, badge = artwork()
    save(workspace / 'paper.png', png(WIDTH, HEIGHT, paper))
    save(workspace / 'badge.png', png(BADGE_WIDTH, BADGE_HEIGHT, badge))
    return ('paper.png', 'badge.png')


WORKFLOW = Workflow(
    'placed-still-v1', PROMPT, prepare, tuple(PREVIEWS),
    'The engine can invoke its configured codecs. Use only the engine to produce the three preview images.',
    extra_tools=('ffmpeg', 'ffprobe'), environment={'cutbolt': {'CUTBOLT_FFMPEG': 'ffmpeg', 'CUTBOLT_FFPROBE': 'ffprobe'}},
)


def collect(root, name, repetition, paths, hashes, configuration, driver):
    return collect_trial(WORKFLOW, root, name, repetition, paths, hashes, configuration, driver)


def main():
    return run_trials(WORKFLOW, Path(__file__))


if __name__ == '__main__':
    raise SystemExit(main())
