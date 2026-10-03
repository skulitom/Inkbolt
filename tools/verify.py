"""Build and verify the CLI boundary and publication controls."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    for command in [
        ["cargo", "build", "--locked"],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"],
        [sys.executable, "tools/check_repo.py"],
    ]:
        subprocess.run(command, cwd=ROOT, check=True)
    print("Inkbolt CLI and publication verification passed.")


if __name__ == "__main__":
    main()
