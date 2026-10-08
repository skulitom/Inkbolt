"""Produce inspectable process plates and two calibrated views of an original chart."""
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
    parser.add_argument('--profile',type=Path,help='Explicit local CMYK output ICC profile')
    args=parser.parse_args()
    if args.profile:profile=args.profile.read_bytes()
    else:
        sys.path.insert(0,str(ROOT/'tests'))
        from cmyk_fixtures import proof_profile
        profile=proof_profile(pcs='Lab ',modern=True,white=(.8,.9,.7))
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    exe=ROOT/'target/debug'/('inkbolt.exe' if os.name=='nt' else 'inkbolt')
    def call(request):
        p=subprocess.run([str(exe)],input=json.dumps(request),capture_output=True,text=True,check=True)
        response=json.loads(p.stdout);assert response['ok'],response;return response['result']
    def save(name,value):
        with (output/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    d=call(dict(command='document.create',id='proof-chart',kind='raster',width=128,height=48,resolution_ppi=300))
    palette=[[30,70,150],[220,40,60],[20,190,100],[240,210,30],[60,30,90],[245,245,245],[0,0,0],[255,255,255]]
    raw=bytes(c for y in range(48) for x in range(128) for c in (*palette[x//16],[64,128,255][y//16]))
    d['items']=[dict(id='chart',name='Original proof chart',content=dict(type='raster',width=128,height=48,rgba_hex=raw.hex()))]
    d=call(dict(command='document.validate',document=d));save('source.json',d)
    (output/'output.icc').write_bytes(profile)
    source=dict(type='file',source_path=str(output/'output.icc'),sha256=hashlib.sha256(profile).hexdigest())
    save('profile-provenance.json',dict(kind='provided_output_profile' if args.profile else 'original_analytic_demo_not_a_calibrated_press',sha256=source['sha256']))
    settings=dict(profile=source,matte=[255,255,255],intent='relative_colorimetric',raster_scale=2)
    for view in ['relative_colorimetric','absolute_colorimetric']:
        request=dict(command='document.proof',document=d,options=dict(print=settings,view_intent=view,delta_e76_threshold=20,samples=[[16,80],[144,80]]))
        save(view+'-request.json',request);result=call(request);save(view+'-receipt.json',result)
        (output/(view+'.png')).write_bytes(base64.b64decode(result['preview']['data']))
        (output/(view+'-difference.png')).write_bytes(base64.b64decode(result['difference']['mask']['data']))
        for name,plane in result['plates'].items():
            (output/(view+'-'+name+'.png')).write_bytes(base64.b64decode(plane['data']))
    pdf=call(dict(command='document.export',document=d,format='pdf',pdf_options=dict(print=settings)))
    (output/'print.pdf').write_bytes(base64.b64decode(pdf['data']));save('print-receipt.json',pdf)
    preview=call(dict(command='document.export',document=d,format='png',scale=2))
    (output/'source.png').write_bytes(base64.b64decode(preview['data']))
    print(json.dumps(dict(output=str(output),source_unchanged=True,views=2,print_jobs=0)))


if __name__=='__main__':main()
