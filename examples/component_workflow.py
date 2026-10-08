"""Create shared icon variants, update once and detach one independent copy."""
import argparse
import copy
import json
from pathlib import Path
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    output=parser.parse_args().output.resolve();output.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (output/name).open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(value,indent=2)+'\n')
    def publish(name,d):
        for fmt,ext in [('snapshot','json'),('png','png'),('svg','svg')]:
            save(name+'-'+fmt+'-receipt.json',invoke('document.publish',document=d,output=dict(output_root=str(output),file_name=name+'.'+ext,format=fmt,scale=3 if fmt=='png' else 1)))
    d=invoke('document.create',id='component-workflow',kind='vector',width=128,height=48)
    items=[dict(id='tile',name='Shared tile',content=dict(type='component_source')),
           dict(id='body',parent='tile',content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=24,height=24),fill=[40,100,220,255])),
           dict(id='mark',parent='tile',content=dict(type='vector',geometry=dict(shape='rect',x=8,y=8,width=8,height=8),fill=[255]*4))]
    for i,x in enumerate([12,52,92]):
        overrides={'body':dict(vector_style=dict(fill=[30,170,100,255],stroke=None))} if i==1 else {}
        items.append(dict(id=f'copy-{i}',transform=[1,0,0,1,x,12],content=dict(type='instance',instance=dict(source='tile',overrides=overrides))))
    original=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=i) for i in items])['document']
    retained=copy.deepcopy(original);publish('original',original)
    edited=invoke('document.edit',document=original,expected_revision=original['revision'],operations=[dict(op='vector',id='mark',geometry=dict(shape='rect',x=6,y=10,width=12,height=4),fill=[255]*4)])['document']
    publish('edited',edited)
    detached=invoke('document.edit',document=edited,expected_revision=edited['revision'],operations=[dict(op='instance_unlink',id='copy-2')])
    save('unlink.json',detached);publish('detached',detached['document'])
    save('shared-edit-diff.json',invoke('document.diff',before=original,after=edited,compare_pixels=True))
    save('unlink-diff.json',invoke('document.diff',before=edited,after=detached['document'],compare_pixels=True))
    assert original==retained==json.loads((output/'original.json').read_text())
    assert (output/'edited.png').read_bytes()==(output/'detached.png').read_bytes()
    print('Published original, edited and detached icon variants in '+str(output))


if __name__=='__main__':main()
