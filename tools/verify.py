"""Build and verify the CLI boundary and publication controls."""
from pathlib import Path
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def python_checks(jobs):
    if jobs == 1:
        subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"], cwd=ROOT, check=True)
        return
    # Each module gets its own interpreter and fixtures. Keep the same discovery
    # patterns as the serial runner, including imported test cases. Verify the
    # aggregate count against ordinary discovery; never treat a missing summary
    # or a worker failure as a passing shard.
    expected = unittest.TestLoader().discover(str(ROOT / 'tests'), pattern='test_*.py').countTestCases()
    files = sorted(ROOT.joinpath('tests').glob('test_*.py'))
    def run(path):
        return subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', path.name, '-v'],
                              cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
    total = 0; failures = []
    print(f'Verifying {expected} Python tests across {len(files)} modules with {jobs} workers.', flush=True)
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        pending = {pool.submit(run, path):path for path in files}
        for future in as_completed(pending):
            path = pending[future]
            process = future.result()
            print(f'\nModule {path.name}:\n{process.stdout}', end='', flush=True)
            count = re.findall(r'^Ran (\d+) tests? in ', process.stdout, flags=re.MULTILINE)
            if process.returncode or len(count) != 1:
                failures.append(path.name)
            if len(count) == 1: total += int(count[0])
    if failures or total != expected:
        raise RuntimeError(f'Python verification failed: modules={failures}, observed={total}, expected={expected}')
    print(f'All {total} Python tests passed across {len(files)} isolated modules.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs', type=int, default=1, choices=range(1,9), help='Independent Python module workers (default: serial; not a performance benchmark)')
    args = parser.parse_args()
    subprocess.run(['cargo', 'build', '--locked'], cwd=ROOT, check=True)
    python_checks(args.jobs)
    subprocess.run([sys.executable, 'tools/check_repo.py'], cwd=ROOT, check=True)
    print("Inkbolt CLI and publication verification passed.")


if __name__ == "__main__":
    main()
