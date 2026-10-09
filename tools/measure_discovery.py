"""Measure local discovery traffic without editing documents or claiming task success."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import queue
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


def source_identity():
    paths = sorted([*ROOT.joinpath('src').rglob('*.rs'), ROOT / 'Cargo.toml',
                    ROOT / 'Cargo.lock', ROOT / 'docs/features.json'])
    digest = hashlib.sha256()
    for path in paths:
        name = path.relative_to(ROOT).as_posix().encode()
        data = path.read_bytes()
        digest.update(len(name).to_bytes(8, 'big')); digest.update(name)
        digest.update(len(data).to_bytes(8, 'big')); digest.update(data)
    return digest.hexdigest()


def inspect_catalog(executable, mode):
    start = time.perf_counter()
    process = subprocess.Popen([str(executable), 'mcp', '--tools', mode],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    lines = queue.Queue()
    reader = threading.Thread(target=lambda: [lines.put(line) for line in process.stdout], daemon=True)
    reader.start()
    def send(message):
        process.stdin.write((json.dumps(message) + '\n').encode()); process.stdin.flush()
    def request(rid, method, params):
        send(dict(jsonrpc='2.0', id=rid, method=method, params=params))
        raw = lines.get(timeout=30)
        response = json.loads(raw)
        if response.get('id') != rid or 'error' in response:
            raise RuntimeError('Unexpected discovery response')
        return response['result'], len(raw)
    try:
        initialized, _ = request(1, 'initialize', dict(protocolVersion='2025-11-25', capabilities={},
                                                     clientInfo=dict(name='inkbolt-discovery-measurement', version='1')))
        send(dict(jsonrpc='2.0', method='notifications/initialized'))
        tools = []; wire = 0; pages = 0; params = {}
        for rid in range(2, 258):
            page, size = request(rid, 'tools/list', params)
            tools.extend(page['tools']); wire += size; pages += 1
            if 'nextCursor' not in page:
                break
            params = dict(cursor=page['nextCursor'])
        else:
            raise RuntimeError('Discovery exceeded its page budget')
        return dict(mode=mode, server=initialized['serverInfo'], tools=len(tools), pages=pages,
                    catalog_wire_bytes=wire, catalog_json_bytes=len(json.dumps(tools, separators=(',', ':')).encode()),
                    protocol_requests=pages + 1, elapsed_seconds=time.perf_counter() - start)
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait()
        reader.join(timeout=2)
        stderr = process.stderr.read(); process.stdout.close(); process.stderr.close()
        if process.returncode != 0 or stderr:
            raise RuntimeError('Discovery process did not exit cleanly')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, default=ROOT / 'target/debug' / ('inkbolt.exe' if platform.system() == 'Windows' else 'inkbolt'))
    parser.add_argument('--output', type=Path, help='New JSON report outside the repository; parent must exist')
    args = parser.parse_args()
    if args.output and args.output.resolve().is_relative_to(ROOT.resolve()):
        parser.error('Retain generated measurement reports outside the repository')
    executable = args.executable.resolve(strict=True)
    source_before = source_identity()
    executable_before = hashlib.sha256(executable.read_bytes()).hexdigest()
    catalogs = [inspect_catalog(executable, mode) for mode in ['full', 'core']]
    lookups = []
    for lookup in [dict(name='index'), dict(name='document'), dict(name='operation', select='transform')]:
        request = dict(command='schema.lookup', **lookup)
        start = time.perf_counter()
        process = subprocess.run([str(executable)], input=json.dumps(request).encode(), capture_output=True, timeout=30, check=True)
        response = json.loads(process.stdout)
        if not response.get('ok') or process.stderr:
            raise RuntimeError('Schema lookup failed')
        lookups.append(dict(request=request, detail=response['result']['detail'],
                            response_bytes=len(process.stdout), elapsed_seconds=time.perf_counter() - start))
    report = dict(schema_version=1, measurement='discovery_only', model_trials=False,
                  source_sha256=source_before, executable_sha256=executable_before,
                  source_unchanged=source_before == source_identity(),
                  executable_unchanged=executable_before == hashlib.sha256(executable.read_bytes()).hexdigest(),
                  build_provenance='Existing executable; source-to-binary correspondence requires a recorded build',
                  environment=dict(system=platform.system(), release=platform.release(), machine=platform.machine()),
                  catalogs=catalogs, lookups=lookups)
    if not report['source_unchanged'] or not report['executable_unchanged']:
        raise RuntimeError('Measurement inputs changed; rerun on a stable build')
    encoded = json.dumps(report, indent=2) + '\n'
    if args.output:
        with args.output.open('x', encoding='utf-8') as output:
            output.write(encoded)
    print(encoded, end='')


if __name__ == '__main__':
    main()
