"""Retain two linked graphic revisions and an explicitly timed sequence delivery."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess


def write_bundle(bundle, root):
    """New directory, create-only files, manifest last; no overwrite or implicit reuse."""
    files=bundle['files']
    manifest=bundle['manifest_file']['path']
    prepared={}
    for file in files:
        name=file['path']
        if Path(name).name!=name or '/' in name or '\\' in name or ':' in name:
            raise ValueError('Expected a flat delivery filename')
        raw=base64.b64decode(file['data'],validate=True)
        if len(raw)!=file['bytes'] or hashlib.sha256(raw).hexdigest()!=file['sha256']:
            raise ValueError('Delivery payload does not match its identity')
        if name in prepared:raise ValueError('Duplicate delivery filename')
        prepared[name]=raw
    if manifest not in prepared:raise ValueError('Missing handoff manifest')
    root.mkdir(exist_ok=False)
    for name in [n for n in prepared if n!=manifest]+[manifest]:
        with (root/name).open('xb') as out:out.write(prepared[name])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--inkbolt',type=Path,default=Path(__file__).resolve().parents[1]/'target/debug/inkbolt.exe')
    parser.add_argument('--cutbolt',type=Path,help='Optional local executable for real inspection and rendering')
    args=parser.parse_args()
    root=args.output
    if not root.is_absolute():raise ValueError('Use a new absolute output directory')
    root.mkdir(parents=True,exist_ok=False)
    def invoke(command,**fields):
        p=subprocess.run([str(args.inkbolt.resolve()),'--workspace',str(root)],
            input=json.dumps(dict(command=command,**fields)).encode(),capture_output=True,timeout=60)
        response=json.loads(p.stdout)
        if p.returncode or not response.get('ok'):raise RuntimeError(response)
        return response['result']
    def save(name,value):
        with (root/name).open('x',encoding='utf-8') as out:json.dump(value,out,indent=2)
    document=invoke('document.create',id='original-graphic',kind='vector',width=32,height=24)
    items=[dict(id='orange',content=dict(type='vector',geometry=dict(shape='rect',x=3,y=4,width=10,height=12),fill=[230,110,30,128])),
           dict(id='blue',content=dict(type='vector',geometry=dict(shape='rect',x=16,y=7,width=9,height=10),fill=[30,110,230,255]))]
    document=invoke('document.edit',document=document,expected_revision=0,operations=[dict(op='add',item=item) for item in items])['document']
    invoke('session.create',session_id='graphic',request_id='create',document=document)
    settings=dict(link_key='graphic',selection=dict(type='still'),duration=dict(num=2,den=5),
        frame_rate=dict(num=25,den=1),timing='strict',end='hold_last',alpha=dict(type='transparent'))
    pins=[]
    def deliver(revision,name,options,previous=None):
        bundle=invoke('handoff.export',document=dict(session_id='graphic',revision=revision),options=options,previous=previous)
        folder=root/name;write_bundle(bundle,folder)
        inspection=invoke('handoff.inspect',handoff=bundle['handoff'],input_root=name,include_schedule=True)
        save(name+'-checked.json',dict(handoff=bundle['handoff'],inspection=inspection))
        if args.cutbolt:
            scene=json.loads((folder/bundle['handoff']['manifest']['scene']['path']).read_text())
            for command in ('scene.inspect','scene.render'):
                request=dict(command=command,scene=scene,input_root=str(folder))
                if command=='scene.render':request.update(output_root=str(folder),output=str(folder/'compiled.mkv'))
                p=subprocess.run([str(args.cutbolt.resolve())],input=json.dumps(request).encode(),capture_output=True,timeout=120)
                response=json.loads(p.stdout);save(name+'-'+command+'.json',response)
                if p.returncode or not response.get('ok'):raise RuntimeError(response)
        pins.append(bundle['handoff']);return bundle['handoff']
    original=deliver(0,'revision-0',settings)
    invoke('session.apply',session_id='graphic',request_id='move',expected_revision=0,
        action=dict(type='edit',operations=[dict(op='transform',id='orange',matrix=[1,0,0,1,4,0])]))
    revised=deliver(1,'revision-1',settings,original)
    invoke('session.apply',session_id='graphic',request_id='sequence',expected_revision=1,
        action=dict(type='edit',operations=[dict(op='sequence_from_layers',ids=['orange','blue'],delay=dict(numerator=2,denominator=25),plays=0)]))
    deliver(2,'revision-2-sequence',dict(settings,selection=dict(type='sequence'),end='loop'),revised)
    # Reading the old pin still resolves the old files after every new delivery.
    invoke('handoff.inspect',handoff=original,input_root='revision-0')
    save('history.json',invoke('session.verify',session_id='graphic'))
    print('Created and checked two still revisions and an ordered sequence in '+str(root))


if __name__=='__main__':main()
