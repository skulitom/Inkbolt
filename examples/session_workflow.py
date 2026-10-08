"""Persist an existing snapshot, hide an item, undo, and verify a safe retry."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--item', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--asset-root', type=Path)
    p.add_argument('--font-root', type=Path)
    args = p.parse_args()
    source = args.source.resolve()
    original = source.read_bytes()
    document = json.loads(original)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    exe = Path(__file__).resolve().parents[1] / 'target/debug' / ('inkbolt.exe' if os.name == 'nt' else 'inkbolt')
    resources = {name: str(path.resolve()) for name, path in [('asset_root', args.asset_root), ('font_root', args.font_root)] if path}
    session = dict(session_root=str(output/'sessions'), session_id='example')

    def call(command, **kw):
        process = subprocess.run([str(exe)], input=json.dumps(dict(command=command, **kw)).encode(), capture_output=True, timeout=40)
        result = json.loads(process.stdout)
        if process.returncode or not result['ok']:
            raise RuntimeError(result)
        return result['result']

    def save(name, data):
        with (output/name).open('xb') as f:
            f.write(data)

    def png(result):
        image = call('document.export', document=result['document'], format='png', **result['resources'])
        return base64.b64decode(image['data'])

    created = call('session.create', **session, request_id='create', document=document, resources=resources)
    saved = call('session.apply', **session, request_id='snapshot', expected_revision=0, action=dict(type='snapshot', name='initial'))
    action = dict(type='edit', label='Hide one item for review', operations=[dict(op='properties', id=args.item, visible=False)])
    edited = call('session.apply', **session, request_id='hide-item', expected_revision=1, action=action)
    undone = call('session.apply', **session, request_id='undo', expected_revision=2, action=dict(type='undo'))
    replay = call('session.apply', **session, request_id='hide-item', expected_revision=1, action=action)
    assert replay['replayed'] and replay['receipt'] == edited['receipt']
    assert replay['document'] == edited['document'] and replay['current_revision'] == 3
    current = call('session.read', **session)
    assert current['document'] == undone['document']
    assert dict(current['document'], revision=0) == created['document']
    before, after, restored = png(created), png(edited), png(current)
    assert before == restored
    assert source.read_bytes() == original
    for name, data in [('before.png',before), ('edited.png',after), ('restored.png',restored)]:
        save(name, data)
    save('document.json', json.dumps(current['document'],indent=2).encode())
    verification = call('session.verify', **session)
    report = dict(source_sha256=hashlib.sha256(original).hexdigest(), restored_pixels_equal=True,
                  retry_preserved_head=True, current_revision=current['current_revision'],
                  receipts=[r['receipt'] for r in [created,saved,edited,undone]], verification=verification)
    save('session-report.json',json.dumps(report,indent=2).encode())
    print('Saved editable session, history receipts and before/edited/restored PNGs in '+str(output))


if __name__ == '__main__':
    main()
