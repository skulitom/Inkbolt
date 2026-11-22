"""Independently reopen and score retained model placements without running the model again."""
from pathlib import Path

from benchmark_driver import workspace_files
from benchmark_runtime import require
from compare_placed_still import BADGE_HEIGHT, BADGE_WIDTH, HEIGHT, PREVIEWS, WIDTH, artwork
from matched_cli_judge import capture_conditions, run_judge
from placed_still_judge import score, traffic
from workload_cases import png, sha


def judge(root, engine, n, method, paths):
    workspace = root / 'workspace'
    paper, badge = artwork()
    fixtures = {'paper.png': sha(png(WIDTH, HEIGHT, paper)), 'badge.png': sha(png(BADGE_WIDTH, BADGE_HEIGHT, badge))}
    contract, files, execution, usage, samples, shell = capture_conditions(root, engine, n, method, fixtures, PREVIEWS)
    row = score(workspace, engine, paths, contract['fixtures'], samples)
    row.update(engine=engine, repetition=n, execution=execution, client=usage, shell=shell, cli=traffic(
        workspace / '.trial-tools/traffic', row['revisions'], row['delivered_sha256'].get('historical.png')))
    require(workspace_files(workspace) == files, 'Judging changed captured workspace files')
    row['passed'] = row['saved_workflow_passed'] and execution['status'] == 'passed' and row['cli']['calls'] > 0
    return row


def main():
    return run_judge('placed-still-v1', ('ffmpeg', 'ffprobe'), judge, Path(__file__),
                     ('placed_still_judge.py', 'compare_placed_still.py'))


if __name__ == '__main__':
    raise SystemExit(main())
