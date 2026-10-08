"""Original process-plus-duotone chart, reference proof and gamut diagnostics."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', type=Path, help='Explicit local CMYK output ICC profile')
    args = parser.parse_args()
    if args.profile:
        profile = args.profile.read_bytes()
    else:
        sys.path.insert(0, str(ROOT/'tests'))
        from gamut_fixtures import profile as original_profile
        profile = original_profile(modern=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    exe = ROOT/'target/debug'/('inkbolt.exe' if os.name == 'nt' else 'inkbolt')

    def call(command, **kw):
        p = subprocess.run([str(exe)], input=json.dumps(dict(command=command, **kw)),
                           capture_output=True, text=True, check=True)
        return json.loads(p.stdout)['result']

    def save(name, value):
        with (output/name).open('x', encoding='utf8') as f:
            json.dump(value, f, indent=2); f.write('\n')

    def image(name, artifact):
        with (output/name).open('xb') as f:
            f.write(base64.b64decode(artifact['data']))

    d = call('document.create', id='combined-chart', kind='raster', width=64, height=32, resolution_ppi=300)
    pixels = bytes(v for y in range(32) for x in range(64) for v in (x*4, 255-y*8, (x+y)*17 % 256, 255))
    d['items'] = [dict(id='chart', content=dict(type='raster', width=64, height=32, rgba_hex=pixels.hex()))]
    d['channels'] = {name: dict(name=name, role=dict(type='alpha'),
                               plane=dict(width=64, height=32, gray_hex=bytes(values).hex()))
                     for name, values in [('gray', [x*4 for y in range(32) for x in range(64)]),
                                          ('coverage', [255 if 3 <= x < 61 and 3 <= y < 29 else 0 for y in range(32) for x in range(64)])]}
    d = call('document.validate', document=d); save('original.json', d)
    recipe = dict(inks=[dict(id=name, name=name, channel='gray', mask_channel='coverage', alternate_srgb=color, curve=curve)
                        for name, color, curve in [('blue',[30,80,170],[[0,1],[.5,.4],[1,0]]),
                                                   ('warm',[190,80,30],[[0,.7],[.5,.2],[1,0]])]],
                  preview=dict(type='transmittance', paper_srgb=[255]*3))
    d = call('document.edit', document=d, expected_revision=0, operations=[dict(op='ink_recipe', recipe=recipe)])['document']
    save('source.json', d)
    with (output/'output.icc').open('xb') as f: f.write(profile)
    source = dict(type='file', source_path=str(output/'output.icc'), sha256=hashlib.sha256(profile).hexdigest())
    save('profile-provenance.json', dict(kind='provided_profile' if args.profile else 'original_analytic_demo_not_a_press_calibration', sha256=source['sha256']))
    settings = dict(profile=source, matte=[255]*3, raster_scale=2,
                    named_inks=dict(model='multiplicative_cmyk', alternate_cmyk=dict(blue=[.8,.5,0,0], warm=[0,.6,.8,0])))
    request = dict(print=settings, delta_e76_threshold=20, samples=[[16,16],[96,48]])
    save('proof-options.json', request)
    result = call('document.proof', document=d, options=request); save('proof.json', result)
    image('preview.png', result['preview'])
    for name, plate in result['plates'].items(): image(name+'.png', plate)
    for plate in result['named_plates']: image(plate['id']+'.png', plate)
    if result['gamut']['status'] == 'available':
        image('gamut.png', result['gamut']['mask']); image('unclassified.png', result['gamut']['unclassified_mask'])
    save('pdf-receipt.json', call('document.publish', document=d, output=dict(output_root=str(output), file_name='combined.pdf', format='pdf', pdf_options=dict(print=settings))))
    assert json.loads(call('document.export', document=d, format='snapshot')['data']) == d
    print(json.dumps(dict(output=str(output), source_unchanged=True, plates=6, gamut=result['gamut']['status'], print_jobs=0)))


if __name__ == '__main__':
    main()
