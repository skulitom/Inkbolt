"""Original diagram fragments with a reversible opacity mask and durable undo.

Run: python examples/mask_workflow.py C:/absolute/new-output-directory
The destination must be new. All output files are published create-only by Inkbolt.
"""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT/'target/debug/inkbolt.exe'


def invoke(command, **args):
    result = subprocess.run([str(EXE)], input=json.dumps(dict(command=command, **args)).encode(), capture_output=True, check=True)
    response = json.loads(result.stdout)
    assert response['ok'], response
    return response['result']


def main(destination):
    output = Path(destination)
    if not output.is_absolute():
        raise ValueError('Use an absolute new output directory')
    output.mkdir(parents=True, exist_ok=False)
    document = invoke('document.create', id='mask-diagrams', kind='vector', width=202, height=80)
    operations = []
    for n,x in enumerate((10,74,138)):
        board=f'board-{n}';group=f'art-{n}'
        items=[dict(id=board,name=f'Diagram {n+1}',transform=[1,0,0,1,x,8],content=dict(type='frame',frame=dict(role='artboard',width=54,height=64))),
               dict(id=group,parent=board,transform=[1,0,0,1,3,16],content=dict(type='group')),
               dict(id=f'ground-{n}',parent=group,content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=48,height=32),fill=[31,147,219,255])),
               dict(id=f'node-{n}',parent=group,content=dict(type='vector',geometry=dict(shape='rect',x=10,y=8,width=28,height=16),fill=[243,168,72,255]))]
        operations.extend(dict(op='add',item=item) for item in items)
    document=invoke('document.edit',document=document,expected_revision=0,operations=operations)['document']
    args=dict(session_root=str(output/'sessions'),session_id='mask-diagrams')
    invoke('session.create',**args,request_id='create',document=document)
    def publish(revision,name,format='png'):
        return invoke('session.publish',**args,expected_revision=revision,output=dict(output_root=str(output),file_name=name,format=format))
    receipts=[publish(0,'original.json','snapshot'),publish(0,'before.png')]
    mask=dict(width=8,height=4,gray_hex=bytes([0,36,72,108,145,181,218,255]*4).hex(),transform=[6,0,0,8,0,0],feather=1,density=0.85)
    invoke('session.apply',**args,expected_revision=0,request_id='fade',action=dict(type='edit',label='Fade middle diagram',operations=[dict(op='mask',id='art-1',mask=mask)]))
    receipts.extend([publish(1,'masked.json','snapshot'),publish(1,'masked.png'),publish(1,'masked.svg','svg')])
    delta=invoke('session.diff',**args,from_revision=0,to_revision=1,compare_pixels=True)
    invoke('session.apply',**args,expected_revision=1,request_id='undo',action=dict(type='undo'))
    receipts.append(publish(2,'restored.png'))
    invoke('session.verify',**args)
    print(json.dumps(dict(receipts=receipts,diff=delta),indent=2))


if __name__=='__main__':
    main(sys.argv[1])
