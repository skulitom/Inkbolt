"""Pass through the selected native CLI inside the solver's workspace and record its traffic."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid


def main():
    directory = Path(__file__).resolve().parent
    workspace = directory.parent
    config = json.loads((directory / 'launch.json').read_bytes())
    args = sys.argv[1:]
    request = b'' if args or sys.stdin.isatty() else sys.stdin.buffer.read()
    prefix = directory / 'traffic' / uuid.uuid4().hex
    prefix.mkdir()
    payload = request
    if len(args) == 1:
        filename = (Path.cwd() / args[0]).resolve()
        if filename.is_relative_to(workspace) and filename.is_file():
            payload = filename.read_bytes()
    (prefix / 'input').write_bytes(payload)
    started = time.time_ns()
    (prefix / 'launch.json').write_text(json.dumps(dict(argv=args, started_ns=started)), encoding='utf-8')
    result = subprocess.run([config['executable'], '--workspace', str(workspace), *args], input=request,
                            capture_output=True, env=dict(os.environ, **config['environment']))
    (prefix / 'stdout').write_bytes(result.stdout)
    (prefix / 'stderr').write_bytes(result.stderr)
    (prefix / 'exit.json').write_text(json.dumps(dict(code=result.returncode, finished_ns=time.time_ns())),
                                      encoding='utf-8')
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
