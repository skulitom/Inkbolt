"""Capture paired model trials after a native creation reply is withheld."""
from pathlib import Path
import subprocess

from benchmark_runtime import canonical, require, strict_json
from compare_session_recovery import create_arguments
from matched_cli_models import Workflow, run_trials
from workload_cases import save_json


PROMPT = """Use the supplied local engine to recover a saved creation after the previous client lost its reply. That client submitted the JSON in create-request.json once and then exited. Its session is named study and its request ID is create.

Retrieve the original receipt by request ID and save the native receipt object in receipt.json. Retry the exact creation request. Then try the same request ID once with width 193 instead of 192 and verify that the engine rejects the changed request. Read the current saved project and its history after these attempts. Write head.json with exactly these fields: id, revision, width, height, history_entries. Use the actual history count.

Preserve the original request and saved project. Use the supplied CLI for all session operations. You may read your request file and write your two JSON deliverables with the shell. Use runtime discovery as needed. Leave the engine's storage files, launcher, and traffic records alone.
"""


def prepare(workspace, evidence, engine, paths):
    request = dict(command='session.create', **create_arguments(engine, 192))
    save_json(workspace / 'create-request.json', request)
    before = subprocess.run([str(paths[engine]), '--workspace', str(workspace)], cwd=workspace,
                            input=canonical(request), capture_output=True, timeout=60)
    answer = strict_json(before.stdout)
    require(before.returncode == 0 and not before.stderr and answer['ok'] is True,
            'The harness could not create the starting session')
    (evidence / 'withheld-response.json').write_bytes(before.stdout)
    return ('create-request.json',)


WORKFLOW = Workflow('receipt-recovery-v1', PROMPT, prepare, (),
                    'Use the native engine for every session operation and leave its backing store intact.')


if __name__ == '__main__':
    raise SystemExit(run_trials(WORKFLOW, Path(__file__)))
