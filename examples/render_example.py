"""Original example client: create, inspect and export without overwriting inputs."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / 'target/debug' / ('inkbolt.exe' if os.name == 'nt' else 'inkbolt')


def invoke(request):
    process = subprocess.run([str(EXE)], input=json.dumps(request).encode(), capture_output=True, timeout=30)
    result = json.loads(process.stdout)
    if process.returncode or not result['ok']:
        raise RuntimeError(result.get('error', {'code':'PROCESS_FAILED'}))
    return result['result']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--vector-request', type=Path, default=ROOT/'examples/edit-vector.json')
    parser.add_argument('--raster-request', type=Path, default=ROOT/'examples/edit-raster.json')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    for lane in ('vector', 'raster'):
        request_path=args.vector_request if lane=='vector' else args.raster_request
        request = json.loads(request_path.read_text(encoding='utf8'))
        document = invoke(request)['document']
        with (args.output_dir / f'{lane}.json').open('x', encoding='utf8') as stream:
            json.dump(document, stream, indent=2)
        inspection = invoke({'command':'document.inspect','document':document})
        with (args.output_dir / f'{lane}-inspection.json').open('x', encoding='utf8') as stream:
            json.dump(inspection, stream, indent=2)
        for format_name in (('png','svg') if lane == 'vector' else ('png',)):
            result = invoke({'command':'document.export','document':document,'format':format_name})
            data = base64.b64decode(result['data']) if result['encoding']=='base64' else result['data'].encode('utf8')
            with (args.output_dir / f'{lane}.{format_name}').open('xb') as stream:
                stream.write(data)
    print('Created original vector and raster examples with editable snapshots and exports.')


if __name__ == '__main__':
    main()
