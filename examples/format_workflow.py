"""Create original exact-palette artwork and explicit BMP/TGA/GIF/TIFF deliveries."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    exe=ROOT/'target/debug'/('inkbolt.exe' if __import__('os').name=='nt' else 'inkbolt')
    def call(request):
        p=subprocess.run([str(exe)],input=json.dumps(request),text=True,capture_output=True,check=True)
        response=json.loads(p.stdout);assert response['ok'],response;return response['result']
    def save(name,value):
        with (output/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    d=call(dict(command='document.create',id='format-chart',kind='raster',width=24,height=16,resolution_ppi=144))
    palette=[[28,60,110,255],[220,70,40,255],[40,180,120,255],[245,205,70,255],[0,0,0,0]]
    pixels=bytes(c for y in range(16) for x in range(24) for c in palette[(x//4+y//4)%5])
    d['items']=[dict(id='chart',name='Original palette chart',content=dict(type='raster',width=24,height=16,rgba_hex=pixels.hex()))]
    d['metadata']=dict(title='Original palette and alpha chart',private={'note':'keep-in-editable-source'})
    save('source.json',d);(output/'expected.rgba8').write_bytes(pixels)
    deliveries=[('reference','png',{}),('chart','tga',dict(metadata_policy=dict(mode='strip'))),
        ('chart','bmp',dict(image_options=dict(matte=[255]*3),metadata_policy=dict(mode='strip'))),
        ('chart','gif',{}),('straight','tiff',dict(image_options=dict(compression='none'))),
        ('associated','tiff',dict(image_options=dict(compression='none',alpha='associated')))]
    receipts={}
    for name,fmt,options in deliveries:
        request=dict(command='document.export',document=d,format=fmt,**options);save(name+'-'+fmt+'-request.json',request)
        artifact=call(request);save(name+'-'+fmt+'-receipt.json',artifact)
        data=base64.b64decode(artifact['data']);(output/(name+'.'+fmt)).write_bytes(data)
        receipts[name+'.'+fmt]=hashlib.sha256(data).hexdigest()
    # Two retained original layers become independently timed frame states.
    second=bytes(c for y in range(16) for x in range(24) for c in palette[(x//4+y//4+2)%5])
    d['items'].append(dict(id='alternate',content=dict(type='raster',width=24,height=16,rgba_hex=second.hex())))
    operations=[dict(op='sequence_from_layers',ids=['chart','alternate'],delay=dict(numerator=1,denominator=10),plays=3)]
    sequence=call(dict(command='document.edit',document=d,expected_revision=0,operations=operations))['document']
    sequence['variants']['sequence']['frames'][1]['delay']=dict(numerator=3,denominator=10)
    save('sequence.json',sequence)
    artifact=call(dict(command='document.export',document=sequence,format='gif'));save('animation-receipt.json',artifact)
    (output/'animation.gif').write_bytes(base64.b64decode(artifact['data']));(output/'alternate.rgba8').write_bytes(second)
    imported=call(dict(command='sequence.import',id='reopened-animation',source=dict(type='gif',source_path=str(output/'animation.gif')),color_policy='assume_srgb',store_root=str(output/'assets')))
    save('reopened-sequence.json',imported)
    receipts['animation.gif']=hashlib.sha256((output/'animation.gif').read_bytes()).hexdigest()
    save('deliveries.json',receipts)
    print('Created original BMP/TGA/GIF/TIFF deliveries and a retained two-frame sequence:',output)


if __name__=='__main__':main()
