"""Publish original diagram links with explicit object and document stroke widths."""
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
    d=invoke('document.create',id='transform-example',kind='vector',width=96,height=64)
    items=[dict(id=policy,name=policy+' stroke width',transform=[1,0,0,1,8,y],content=dict(type='vector',geometry=dict(shape='path',commands=[dict(verb='move',to=[0,0]),dict(verb='line',to=[20,0])]),stroke=dict(color=color,width=2,scaling=policy,dash=dict(array=[6,4])))) for policy,y,color in [('object',16,[42,104,213,255]),('document',40,[26,160,110,255])]]
    source=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=item) for item in items])['document']
    retained=copy.deepcopy(source);publish('source',source)
    ops=[dict(op='transform',id=policy,space='world',matrix=[3,0,0,2,0,0],anchor=[8,y]) for policy,y in [('object',16),('document',40)]]
    save('transform-operations.json',ops)
    resized=invoke('document.edit',document=source,expected_revision=source['revision'],operations=ops)['document'];publish('resized',resized)
    expanded=invoke('document.edit',document=resized,expected_revision=resized['revision'],operations=[dict(op='stroke_expand',id=policy,fill_id=policy+'-centerline',stroke_id=policy+'-outline') for policy in ['object','document']])
    save('expansion.json',expanded);publish('expanded',expanded['document'])
    save('resize-diff.json',invoke('document.diff',before=source,after=resized,compare_pixels=True))
    save('expansion-diff.json',invoke('document.diff',before=resized,after=expanded['document'],compare_pixels=True))
    assert source==retained==json.loads((output/'source.json').read_text())
    assert (output/'resized.png').read_bytes()==(output/'expanded.png').read_bytes()
    print('Published source, resized and expanded diagram links in '+str(output))


if __name__=='__main__':main()
