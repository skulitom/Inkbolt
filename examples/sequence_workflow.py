"""Retain editable frames, deliver PNG/APNG, and prepare a content-bound still handoff."""
import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import subprocess
from mask_workflow import invoke


def still_scene(path, width, height, background):
    """One explicitly held still; no animation timing or editable-layer transfer."""
    raw=path.read_bytes();hold=dict(num=1,den=25)
    return dict(schema_version=1,id='inkbolt-still',width=width,height=height,output_scale=1,
        duration=hold,background=background,color='srgb_straight_encoded',audio=None,layers=[
        dict(id='still',canvas=[width,height],start=dict(num=0,den=1),duration=hold,
            frames=[dict(image=dict(path=path.name,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)),hold=hold,offset=[0,0],anchor=[0,0])],
            timing='strict',end='hold_last',alpha_mode='straight',
            transform=dict(crop=[0,0,width,height],quarter_turns=0,scale=1,position=[0,0],opacity=255))])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--cutbolt',type=Path,help='Optionally verify the still using this local executable')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    d=invoke('document.create',id='original-status-icons',kind='raster',width=32,height=24)
    for index,color in enumerate([[220,50,30,255],[30,190,90,128],[40,100,230,64]]):
        pixels=bytes(v for y in range(24) for x in range(32) for v in (color if 4+index*3<=x<16+index*3 and 4<=y<20 else [0,0,0,0]))
        d['items'].append(dict(id=f'icon-{index}',content=dict(type='raster',width=32,height=24,rgba_hex=pixels.hex())))
    d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='sequence_from_layers',ids=['icon-2','icon-0','icon-1'],delay=dict(numerator=4,denominator=25),plays=2)])['document']
    source=copy.deepcopy(d)
    save('source.json-receipt.json',invoke('document.publish',document=d,output=dict(output_root=str(out),file_name='source.json',format='snapshot')))
    save('timeline.json',invoke('sequence.inspect',document=d))
    save('icons.apng-receipt.json',invoke('document.publish',document=d,output=dict(output_root=str(out),file_name='icons.apng',format='apng')))
    collection=invoke('sequence.export',document=d)
    for f in collection['frames']:
        raw=base64.b64decode(f['artifact'].pop('data'));assert hashlib.sha256(raw).hexdigest()==f['sha256']
        with (out/f['file_name']).open('xb') as stream:stream.write(raw)
    save('frames.json',collection)
    still=invoke('sequence.open',document=d,id='frame-2');save('still.json',still)
    save('still.png-receipt.json',invoke('document.publish',document=still['document'],output=dict(output_root=str(out),file_name='still.png',format='png')))
    scene=still_scene(out/'still.png',32,24,[12,18,24]);save('cutbolt-scene.json',scene)
    save('handoff.json',dict(source_frame='frame-2',source_delay=still['frame']['delay'],destination_hold=dict(num=1,den=25),
        background=[12,18,24],losses=['The PNG is flattened straight RGBA8; keep source.json and still.json for editable artwork.',
        'This still handoff omits animation order, delays and plays. The scene holds the selected still for an explicit 1/25 second.',
        'The scene composites alpha over the declared opaque background in encoded sRGB; transparent pixels do not survive the scene output.']))
    if args.cutbolt:
        for command in ['scene.inspect','scene.render']:
            request=dict(command=command,scene=scene,input_root=str(out))
            if command=='scene.render':request.update(output_root=str(out),output=str(out/'cutbolt-still.mkv'))
            p=subprocess.run([str(args.cutbolt.resolve())],input=json.dumps(request).encode(),capture_output=True,timeout=60)
            result=json.loads(p.stdout);save(command+'-receipt.json',result)
            if p.returncode or not result.get('ok'):raise RuntimeError(result)
    assert d==source
    print('Saved editable frames, exact timing, PNG/APNG output and an explicit still handoff in '+str(out))


if __name__=='__main__':main()
