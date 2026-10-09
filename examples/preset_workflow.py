"""Create, review and publish original screen artwork and a physical print page."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inkbolt', type=Path,
                        default=Path(__file__).resolve().parents[1]/'target/debug/inkbolt.exe')
    args = parser.parse_args()
    root = args.output
    if not root.is_absolute():
        raise ValueError('Use a new absolute output directory')
    root.mkdir(parents=True, exist_ok=False)

    def call(command, **fields):
        process = subprocess.run([str(args.inkbolt.resolve()), '--workspace', str(root)],
            input=json.dumps(dict(command=command, **fields)).encode(), capture_output=True, timeout=30)
        response = json.loads(process.stdout)
        if process.returncode or not response.get('ok'):
            raise RuntimeError(response)
        return response['result']

    def save(name, value):
        with (root/name).open('x', encoding='utf-8') as out:
            json.dump(value, out, indent=2)

    recipes = [
        ('artwork', 'png', dict(type='screen', size='icon256', kind='vector',
                               background=dict(type='transparent'))),
        ('page', 'pdf', dict(type='print_page', paper='a5', orientation='portrait',
                            resolution_ppi=72, color='display_rgb',
                            bleed_px=dict(top=9, right=9, bottom=9, left=9))),
    ]
    for name, extension, spec in recipes:
        preset = call('preset.create', version=1, id=name, preset=spec)
        save(name+'-preset.json', preset)
        call('session.create', session_id=name, request_id='create',
             document=preset['document'], response_mode='compact')
        # Artwork belongs to the preset's artboard, preserving independent delivery.
        items = [dict(id='badge', parent=preset['content_parent_id'],
                      content=dict(type='vector', geometry=dict(shape='rect', x=32, y=32,
                                   width=128, height=96), fill=[28, 96, 180, 255])),
                 dict(id='accent', parent=preset['content_parent_id'],
                      content=dict(type='vector', geometry=dict(shape='rect', x=112, y=96,
                                   width=96, height=64), fill=[244, 128, 48, 192]))]
        action = dict(type='edit', operations=[dict(op='add', item=item) for item in items])
        review = call('session.dry_run', session_id=name, expected_revision=0,
                      request_id='artwork', action=action, options=dict(preview=True))
        save(name+'-review.json', review)
        applied = call('session.apply_proposal', proposal=review['proposal'], action=action,
                       response_mode='compact')
        replay = call('session.apply_proposal', proposal=review['proposal'], action=action,
                      response_mode='compact')
        if not replay['replayed'] or applied['receipt_summary'] != replay['receipt_summary']:
            raise RuntimeError('Editing retry did not retain its original receipt')
        ref = dict(session_id=name, revision=1)
        output = preset['delivery'] | dict(file_name=name+'.'+extension)
        preflight = call('document.preflight', document=ref, output=output)
        if not preflight['ready']:
            raise RuntimeError(preflight)
        saved = call('session.publish', session_id=name, expected_revision=1, output=output,
                     receipt=dict(request_id='publish-'+name))
        if hashlib.sha256((root/(name+'.'+extension)).read_bytes()).hexdigest() != saved['sha256']:
            raise RuntimeError('Published bytes do not match the receipt')
        source = call('document.publish', document=ref,
                      output=dict(file_name=name+'-source.json', format='snapshot'))
        save(name+'-receipts.json', dict(edit=applied, retry=replay, preflight=preflight,
             publication=saved, source=source, history=call('session.verify', session_id=name)))
    print('Created reviewed artwork, a physical page and their editable sources in '+str(root))


if __name__ == '__main__':
    main()
