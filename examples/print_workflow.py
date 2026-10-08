"""Create an editable original chart and calibrated CMYK PDF without overwriting files."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--profile',type=Path,help='Explicit local CMYK output ICC profile; omission uses an analytic demonstration fixture')
    args=parser.parse_args()
    if args.profile:
        profile=args.profile.read_bytes()
    else:
        sys.path.insert(0,str(ROOT/'tests'))
        from cmyk_fixtures import cmyk_profile
        profile=cmyk_profile(pcs='Lab ',modern=True)
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    exe=ROOT/'target/debug'/('inkbolt.exe' if os.name=='nt' else 'inkbolt')
    def call(request):
        p=subprocess.run([str(exe)],input=json.dumps(request),capture_output=True,text=True,check=True)
        response=json.loads(p.stdout);assert response['ok'],response;return response['result']
    def save(name,value):
        with (output/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    d=call(dict(command='document.create',id='print-chart',kind='raster',width=128,height=48,resolution_ppi=300))
    palette=[[30,70,150],[220,40,60],[20,190,100],[240,210,30],[60,30,90],[245,245,245],[0,0,0],[255,255,255]]
    raw=bytes(c for y in range(48) for x in range(128) for c in (*palette[x//16], [64,128,255][y//16]))
    d['items']=[dict(id='chart',name='Original ink chart',content=dict(type='raster',width=128,height=48,rgba_hex=raw.hex()))]
    d['metadata']=dict(title='Original calibrated page chart',private={'note':'retain in editable source'})
    d=call(dict(command='document.validate',document=d));save('source.json',d)
    (output/'source.rgba8').write_bytes(raw)
    (output/'output.icc').write_bytes(profile)
    profile_source=(dict(type='file',source_path=str(args.profile.resolve()),sha256=hashlib.sha256(profile).hexdigest())
                    if args.profile else dict(type='icc',data=base64.b64encode(profile).decode()))
    setting=dict(profile=profile_source,matte=[255,255,255],intent='relative_colorimetric')
    save('profile-provenance.json',dict(kind='provided_output_profile' if args.profile else 'original_analytic_demo_not_a_calibrated_press',sha256=hashlib.sha256(profile).hexdigest()))
    for scale in [1,2]:
        options=dict(print=dict(setting,raster_scale=scale))
        request=dict(command='document.export',document=d,format='pdf',pdf_options=options)
        save(f'print-{scale}-request.json',request);a=call(request);save(f'print-{scale}-receipt.json',a)
        (output/f'print-{scale}.pdf').write_bytes(base64.b64decode(a['data']))
    preview=call(dict(command='document.export',document=d,format='png'))
    (output/'source.png').write_bytes(base64.b64decode(preview['data']))
    print(json.dumps(dict(output=str(output),source_unchanged=True,pages=2)))


if __name__=='__main__':main()
