"""Create an original editable duotone chart and independently named ink delivery."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    exe = ROOT / 'target/debug' / ('inkbolt.exe' if os.name == 'nt' else 'inkbolt')

    def call(command, **kw):
        p = subprocess.run([str(exe)], input=json.dumps(dict(command=command, **kw)),
                           capture_output=True, text=True, check=True)
        return json.loads(p.stdout)['result']

    def save(name, value):
        with (output / name).open('x', encoding='utf8') as f:
            json.dump(value, f, indent=2)
            f.write('\n')

    d = call('document.create', id='duotone-chart', kind='raster', width=128, height=48,
             resolution_ppi=300)
    gray = bytes(round(x * 255 / 127) for y in range(48) for x in range(128))
    mask = bytes(255 if 4 <= x < 124 and 4 <= y < 44 else 0
                 for y in range(48) for x in range(128))
    d['channels'] = {name: dict(name=name, role=dict(type='alpha'),
                               plane=dict(width=128, height=48, gray_hex=data.hex()))
                     for name, data in [('gray', gray), ('coverage', mask)]}
    d = call('document.validate', document=d)
    save('original.json', d)
    recipe = dict(inks=[
        dict(id='blue', name='Blue ink', channel='gray', mask_channel='coverage',
             alternate_srgb=[30, 80, 170], curve=[[0, 1], [.5, .4], [1, 0]]),
        dict(id='warm', name='Warm ink', channel='gray', mask_channel='coverage',
             alternate_srgb=[190, 80, 30], curve=[[0, .7], [.5, .2], [1, 0]])],
        preview=dict(type='transmittance', paper_srgb=[255, 255, 255]))
    d = call('document.edit', document=d, expected_revision=d['revision'],
             operations=[dict(op='ink_recipe', recipe=recipe)])['document']
    save('recipe.json', d)

    def deliver(document, name):
        result = call('document.separations', document=document, scale=2)
        save(name + '-separations.json', result)
        for plate in result['plates']:
            with (output / (name + '-' + plate['id'] + '.png')).open('xb') as f:
                f.write(base64.b64decode(plate['data']))
        with (output / (name + '-preview.png')).open('xb') as f:
            f.write(base64.b64decode(result['preview']['data']))
        receipt = call('document.publish', document=document,
                       output=dict(output_root=str(output), file_name=name + '.pdf',
                                   format='pdf', pdf_options=dict(ink_recipe=dict(raster_scale=2))))
        save(name + '-pdf-receipt.json', receipt)

    deliver(d, 'duotone')
    recipe['inks'][1]['curve'] = [[0, .3], [.4, .8], [1, 0]]
    revised = call('document.edit', document=d, expected_revision=d['revision'],
                   operations=[dict(op='ink_recipe', recipe=recipe)])['document']
    save('revised.json', revised)
    save('changes.json', call('document.diff', before=d, after=revised))
    deliver(revised, 'revised')
    assert d['channels'] == revised['channels']
    print(json.dumps(dict(output=str(output),source_channels_unchanged=True,
                          inks=2,versions=2,print_jobs=0)))


if __name__ == '__main__':
    main()
