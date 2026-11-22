"""Capture paired model-driven placements with a caller-selected client and native engines."""
import argparse
from pathlib import Path
import platform

from benchmark_driver import canonical, config, driver_identity, workspace_files
from benchmark_runtime import require
from compare_placed_still import BADGE_HEIGHT, BADGE_WIDTH, HEIGHT, PREVIEWS, WIDTH, artwork, file_sha
from verify_process import run
from workload_cases import ROOT, png, save, save_json, sha


PROMPT = """Use the supplied local graphics engine to place a still image, revise its position and review the saved original.

paper.png fills a 32 by 24 canvas. Place badge.png at its original size with its top-left corner at (3,5), measured from the top left of the canvas. Preserve transparency over the paper. Save this composition in the engine's default workspace session store under the ID placement. Export a full-resolution PNG of this saved arrangement as before.png.

Move only the badge so its top-left corner is at (17,12). Save the change as a later revision of that same session and export after.png. After the move, reopen the earlier saved revision and export historical.png. Leave the current session showing the moved badge. Keep the source images and everything the engine needs to reopen both revisions.

Deliver the three PNGs at the workspace root. Also write revisions.json there with two integer fields, original_revision and moved_revision, identifying the saved versions. Use the engine for the actual compositing, saving and rendering. Use the shell for discovery, preparing requests and writing delivered files. Run synchronous commands and render each requested preview from its saved revision.
"""
HERE = Path(__file__).resolve().parent


def collect(root, name, repetition, paths, hashes, configuration, driver):
    workspace, evidence = root / 'workspace', root / 'evidence'
    workspace.mkdir(parents=True)
    evidence.mkdir()
    recorder = workspace / '.trial-tools'
    (recorder / 'traffic').mkdir(parents=True)
    save(recorder / 'engine.py', (HERE / 'placed_still_cli.py').read_bytes())
    environment = dict(CUTBOLT_FFMPEG=str(paths['ffmpeg']), CUTBOLT_FFPROBE=str(paths['ffprobe'])) if name == 'cutbolt' else {}
    save_json(recorder / 'launch.json', dict(executable=str(paths[name]), environment=environment))
    paper, badge = artwork()
    save(workspace / 'paper.png', png(WIDTH, HEIGHT, paper))
    save(workspace / 'badge.png', png(BADGE_WIDTH, BADGE_HEIGHT, badge))
    save(workspace / 'task.txt', PROMPT.encode())
    inputs = workspace_files(workspace)
    fixtures = {key: inputs[key] for key in ('paper.png', 'badge.png')}
    contract = dict(schema_version=1, task='placed-still-v1', arm='model', engine=name, kind='model',
                    repetition=repetition, engine_sha256=hashes[name], client=configuration['client'],
                    model=configuration['model'], fixtures=fixtures, prompt_sha256=inputs['task.txt'])
    policy = (f'The supplied engine is {name}. Run python .trial-tools/engine.py from the workspace. '
              'It starts the selected native CLI with this workspace already set. It accepts native CLI options '
              'such as --help, a JSON request on stdin, or the name of a JSON request file. '
              'Use the launcher for every engine call. Leave its files and traffic records alone. '
              'The engine can invoke its configured codecs. Use only the engine to produce the three preview images.')
    request = dict(schema_version=1, contract=contract, contract_sha256=sha(canonical(contract)), tool_policy=policy,
                   workspace=str(workspace), prompt_path=str(workspace / 'task.txt'), preview_files=PREVIEWS,
                   transcript_directory=str(evidence), result_path=str(evidence / 'driver-result.json'))
    save_json(evidence / 'request.json', request)
    require(driver_identity(configuration) == driver, 'External driver changed before the trial')
    execution = run(configuration['argv'] + [str(evidence / 'request.json')], workspace,
                    configuration['timeout_seconds'], observe_memory=True)
    execution.pop('output', None)
    save_json(evidence / 'execution.json', execution)
    files = workspace_files(workspace)
    retained = {p.name: file_sha(p) for p in evidence.iterdir() if p.is_file()}
    capture = dict(contract=contract, contract_sha256=request['contract_sha256'], execution=execution['status'],
                   inputs=inputs, files=files, evidence_files=retained, driver=driver)
    save_json(evidence / 'capture.json', capture)
    require(driver_identity(configuration) == driver, 'External driver changed during the trial')
    return capture['execution']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('inkbolt', 'cutbolt', 'ffmpeg', 'ffprobe', 'driver-config', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--pairs', type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.pairs <= 20:
        parser.error('Choose 1 to 20 pairs')
    configuration = config(args.driver_config)
    require(configuration['kind'] == 'model' and configuration['argv'], 'Supply a genuine external model driver')
    paths = {key: getattr(args, key).resolve(strict=True) for key in ('inkbolt', 'cutbolt', 'ffmpeg', 'ffprobe')}
    hashes = {key: file_sha(path) for key, path in paths.items()}
    root = args.output.resolve()
    if root.is_relative_to(ROOT):
        parser.error('Choose a new evidence directory outside the checkout')
    root.mkdir(parents=True, exist_ok=False)
    driver = driver_identity(configuration)
    method = dict(schema_version=1, workflow='placed-still-v1', pairs=args.pairs, host=platform.platform(),
                  binaries=hashes, driver=driver, client=configuration['client'], model=configuration['model'],
                  timeout_seconds=configuration['timeout_seconds'], prompt_sha256=sha(PROMPT.encode()),
                  runner_sha256=file_sha(Path(__file__)), recorder_sha256=file_sha(HERE / 'placed_still_cli.py'))
    save_json(root / 'method.json', method)
    rows = []
    for n in range(1, args.pairs + 1):
        for name in (('inkbolt', 'cutbolt') if n % 2 else ('cutbolt', 'inkbolt')):
            trial = root / f'{n:02d}-{name}'
            print(f'Starting {trial.name}', flush=True)
            try:
                status = collect(trial, name, n, paths, hashes, configuration, driver)
                rows.append(dict(trial=trial.name, execution=status))
            except (OSError, KeyError, ValueError, RuntimeError) as error:
                rows.append(dict(trial=trial.name, execution='failed', error=str(error)))
            print(rows[-1], flush=True)
    unchanged = all(file_sha(path) == hashes[key] for key, path in paths.items())
    save_json(root / 'collection.json', dict(trials=rows, executables_unchanged=unchanged))
    return 0 if unchanged and all(r['execution'] == 'passed' for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
