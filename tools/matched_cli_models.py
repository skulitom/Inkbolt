"""Collect matched local CLI trials with a caller-selected model and native binaries."""
import argparse
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
import platform
import time

from benchmark_driver import canonical, config, driver_identity, workspace_files
from benchmark_runtime import require
from compare_placed_still import file_sha
from verify_process import run
from workload_cases import ROOT, save, save_json, sha


HERE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Workflow:
    name: str
    prompt: str
    prepare: Callable
    observed_files: tuple
    instructions: str
    extra_tools: tuple = ()
    environment: dict = field(default_factory=dict)


def collect(workflow, root, name, repetition, paths, hashes, configuration, driver):
    workspace, evidence = root / 'workspace', root / 'evidence'
    workspace.mkdir(parents=True)
    evidence.mkdir()
    recorder = workspace / '.trial-tools'
    (recorder / 'traffic').mkdir(parents=True)
    save(recorder / 'engine.py', (HERE / 'placed_still_cli.py').read_bytes())
    environment = {key: str(paths[tool]) for key, tool in workflow.environment.get(name, {}).items()}
    save_json(recorder / 'launch.json', dict(executable=str(paths[name]), environment=environment))
    fixture_names = workflow.prepare(workspace, evidence, name, paths)
    save(workspace / 'task.txt', workflow.prompt.encode())
    inputs = workspace_files(workspace)
    fixtures = {key: inputs[key] for key in fixture_names}
    contract = dict(schema_version=1, task=workflow.name, arm='model', engine=name, kind='model',
                    repetition=repetition, engine_sha256=hashes[name], client=configuration['client'],
                    model=configuration['model'], fixtures=fixtures, prompt_sha256=inputs['task.txt'])
    policy = (f'The supplied engine is {name}. Run python .trial-tools/engine.py from the workspace. '
              'It starts the selected native CLI with this workspace already set. It accepts native CLI options '
              'such as --help, a JSON request on stdin, or the name of a JSON request file. '
              'Use the launcher for every engine call. Leave its files and traffic records alone. '
              + workflow.instructions)
    request = dict(schema_version=1, contract=contract, contract_sha256=sha(canonical(contract)), tool_policy=policy,
                   workspace=str(workspace), prompt_path=str(workspace / 'task.txt'), preview_files=workflow.observed_files,
                   transcript_directory=str(evidence), result_path=str(evidence / 'driver-result.json'))
    save_json(evidence / 'request.json', request)
    require(driver_identity(configuration) == driver, 'External driver changed before the trial')
    started_ns = time.time_ns()
    execution = run(configuration['argv'] + [str(evidence / 'request.json')], workspace,
                    configuration['timeout_seconds'], observe_memory=True)
    execution['started_unix_ns'] = started_ns
    execution.pop('output', None)
    save_json(evidence / 'execution.json', execution)
    files = workspace_files(workspace)
    retained = {p.name: file_sha(p) for p in evidence.iterdir() if p.is_file()}
    capture = dict(contract=contract, contract_sha256=request['contract_sha256'], execution=execution['status'],
                   inputs=inputs, files=files, evidence_files=retained, driver=driver)
    save_json(evidence / 'capture.json', capture)
    require(driver_identity(configuration) == driver, 'External driver changed during the trial')
    return capture['execution']


def run_trials(workflow, task_file):
    parser = argparse.ArgumentParser(description=workflow.name)
    for name in ('inkbolt', 'cutbolt', *workflow.extra_tools, 'driver-config', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--pairs', type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.pairs <= 20:
        parser.error('Choose 1 to 20 pairs')
    configuration = config(args.driver_config)
    require(configuration['kind'] == 'model' and configuration['argv'], 'Supply a genuine external model driver')
    paths = {key: getattr(args, key).resolve(strict=True) for key in ('inkbolt', 'cutbolt', *workflow.extra_tools)}
    hashes = {key: file_sha(path) for key, path in paths.items()}
    root = args.output.resolve()
    if root.is_relative_to(ROOT):
        parser.error('Choose a new evidence directory outside the checkout')
    root.mkdir(parents=True, exist_ok=False)
    driver = driver_identity(configuration)
    method = dict(schema_version=1, workflow=workflow.name, pairs=args.pairs, host=platform.platform(),
                  binaries=hashes, driver=driver, client=configuration['client'], model=configuration['model'],
                  timeout_seconds=configuration['timeout_seconds'], prompt_sha256=sha(workflow.prompt.encode()),
                  runner_sha256=file_sha(task_file), collector_sha256=file_sha(Path(__file__)),
                  recorder_sha256=file_sha(HERE / 'placed_still_cli.py'))
    save_json(root / 'method.json', method)
    rows = []
    for n in range(1, args.pairs + 1):
        for name in (('inkbolt', 'cutbolt') if n % 2 else ('cutbolt', 'inkbolt')):
            trial = root / f'{n:02d}-{name}'
            print(f'Starting {trial.name}', flush=True)
            try:
                status = collect(workflow, trial, name, n, paths, hashes, configuration, driver)
                rows.append(dict(trial=trial.name, execution=status))
            except (OSError, KeyError, ValueError, RuntimeError) as error:
                rows.append(dict(trial=trial.name, execution='failed', error=str(error)))
            print(rows[-1], flush=True)
    unchanged = all(file_sha(path) == hashes[key] for key, path in paths.items())
    save_json(root / 'collection.json', dict(trials=rows, executables_unchanged=unchanged))
    return 0 if unchanged and all(r['execution'] == 'passed' for r in rows) else 1
