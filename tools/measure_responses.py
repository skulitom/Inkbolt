"""Measure saved-result traffic with an original fixture, without claiming model task success."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import tempfile
import time

from measure_discovery import ROOT, source_identity


def measure(executable):
    calls = []
    with tempfile.TemporaryDirectory(prefix='inkbolt-volume-') as directory:
        def request(command, **arguments):
            payload = json.dumps(dict(command=command, **arguments), separators=(',', ':')).encode()
            started = time.perf_counter()
            process = subprocess.run([str(executable), '--workspace', directory], input=payload,
                                     capture_output=True, timeout=30, check=True)
            envelope = json.loads(process.stdout)
            if not envelope.get('ok') or process.stderr:
                raise RuntimeError('Measurement request failed')
            calls.append(dict(command=command, response_mode=arguments.get('response_mode', 'full'),
                              input_bytes=len(payload), output_bytes=len(process.stdout),
                              elapsed_seconds=time.perf_counter() - started))
            return envelope['result']

        doc = request('document.create', id='original-volume-fixture', kind='raster', width=256, height=256)
        pixels = bytes([17, 55, 142, 255] * 65536)
        doc['items'] = [dict(id='paint', content=dict(type='raster', width=256, height=256, rgba_hex=pixels.hex()))]
        request('session.create', session_id='volume', request_id='create', document=doc)
        full = request('session.receipt', session_id='volume', request_id='create', response_mode='full')
        full_output = calls[-1]['output_bytes']
        compact = request('session.receipt', session_id='volume', request_id='create', response_mode='compact')
        compact_output = calls[-1]['output_bytes']
        if compact['receipt_summary']['state_sha256'] != full['receipt']['state_sha256']:
            raise RuntimeError('Compact result changed state identity')
        if compact['document_ref']['revision'] != full['document']['revision']:
            raise RuntimeError('Compact result changed document revision')
        rendered = request('document.render', document=compact['document_ref'])
        if rendered['data'] != pixels.hex():
            raise RuntimeError('Referenced pixels differ from the original fixture')
        return dict(fixture=dict(kind='original_constant_rgba8', width=256, height=256,
                                 pixels_sha256=hashlib.sha256(pixels).hexdigest()),
                    full_receipt_stdout_bytes=full_output, compact_receipt_stdout_bytes=compact_output,
                    retained_bytes_ratio=compact_output / full_output,
                    compact_within_8kib=compact_output <= 8192,
                    original_pixels_recovered=True, calls=calls)


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
    measurement = measure(executable)
    report = dict(schema_version=1, measurement='session_receipt_volume_only', model_trials=False,
                  source_sha256=source_before, executable_sha256=executable_before,
                  source_unchanged=source_before == source_identity(),
                  executable_unchanged=executable_before == hashlib.sha256(executable.read_bytes()).hexdigest(),
                  build_provenance='Existing executable; source-to-binary correspondence requires a recorded build',
                  environment=dict(system=platform.system(), release=platform.release(), machine=platform.machine()),
                  **measurement)
    if not report['source_unchanged'] or not report['executable_unchanged']:
        raise RuntimeError('Measurement inputs changed; rerun on a stable build')
    rendered = json.dumps(report, indent=2) + '\n'
    if args.output:
        with args.output.open('x', encoding='utf-8') as output:
            output.write(rendered)
    print(rendered, end='')


if __name__ == '__main__':
    main()
