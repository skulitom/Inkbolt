"""Check the common evidence contract on each task's real CLI and MCP trial."""
from functools import wraps
from pathlib import Path
import sys
import tempfile

from test_cli import EXE, ROOT
sys.path.insert(0, str(ROOT / 'tools'))
from agent_benchmark import run_task
from benchmark_tasks import CHECKS


def check_reference(case, root, task, transport, row):
    case.assertEqual(row['status'], 'passed', row)
    case.assertEqual({entry['name'] for entry in row['checks']}, set(CHECKS[task]) | {'source-preservation'})
    case.assertGreater(row['first_verified_preview_seconds'], 0)
    case.assertTrue(row['judge_separated'])
    case.assertIsNone(row['token_usage'])
    case.assertIsNone(row['model_calls'])
    case.assertFalse(row['model_trials'])
    for key, files in (('request_bytes', root.glob('*.request.json')), ('response_bytes', root.glob('*.response.json'))):
        case.assertEqual(row[key] + row['judge_' + key], sum(p.stat().st_size for p in files))
    if sys.platform == 'win32':
        case.assertTrue(row['memory_complete'])
        case.assertGreater(row['peak_commit_bytes'], 0)
    elif sys.platform == 'linux':
        case.assertTrue(row['resident_memory_complete'], row)
        case.assertGreater(row['peak_resident_bytes'], 0)
        case.assertFalse(row['memory_complete'])
        case.assertIsNone(row['peak_commit_bytes'])
        if transport == 'mcp':
            case.assertEqual(row['server_memory']['resident']['peak_resident_bytes'], row['peak_resident_bytes'])
            case.assertIn('including judge calls', row['memory_scope'])


def reference_task(task):
    def decorate(check_task):
        @wraps(check_task)
        def check_both_transports(case):
            for transport in ('cli', 'mcp'):
                with case.subTest(task=task, transport=transport), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory) / 'reference'
                    row = run_task(EXE, root, task, 1, transport)
                    check_reference(case, root, task, transport, row)
                    check_task(case, row)

        check_both_transports.reference_task = task
        return check_both_transports
    return decorate
