"""Create original editable source, independent placements and immutable delivery."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT/'target/debug/inkbolt.exe'


def call(command, **arguments):
    p = subprocess.run([str(EXE)], input=json.dumps(dict(command=command, **arguments)), text=True, capture_output=True, check=True)
    result = json.loads(p.stdout)
    if not result['ok']:
        raise RuntimeError(result)
    return result['result']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    source = call('document.create', id='motif', kind='vector', width=32, height=32)
    source['items'] = [dict(id='tile', content=dict(type='vector', geometry=dict(shape='rect', x=4, y=4, width=24, height=24), fill=[40,110,210,255]))]
    path = out/'motif.json'
    with path.open('x', encoding='utf8', newline='\n') as f:
        json.dump(source, f, indent=2); f.write('\n')
    imported = call('object.import', source_path=str(path), link_key='motif.json')
    obj = imported['object']; document = call('document.create', id='layout', kind='raster', width=96, height=48)
    items = [dict(id=name, transform=[1,0,0,1,x,8], content=dict(type='object', object=obj)) for name,x in [('first',8),('second',56)]]
    document = call('document.edit', document=document, expected_revision=0, operations=[dict(op='add',item=item) for item in items])['document']
    call('document.publish', document=document, output=dict(output_root=str(out),file_name='original-layout.json',format='snapshot'))
    opened = call('object.open', document=document, id='second')['document']
    opened['items'][0]['content']['fill'] = [220,100,35,255]
    replacement = call('object.import', snapshot=json.dumps(opened))['object']
    edited = call('document.edit', document=document, expected_revision=document['revision'], operations=[dict(op='object_replace',id='second',object=replacement)])['document']
    for filename, fmt in [('layout.json','snapshot'),('layout.png','png')]:
        call('document.publish', document=edited, output=dict(output_root=str(out),file_name=filename,format=fmt))
    status = call('object.status', document=edited, id='first', link_root=str(out))
    with (out/'source-status.json').open('x', encoding='utf8') as f:
        json.dump(status,f,indent=2);f.write('\n')
    print(f'Saved exact editable motif, independent placements, retained snapshots and preview in {out}')


if __name__ == '__main__':
    main()
