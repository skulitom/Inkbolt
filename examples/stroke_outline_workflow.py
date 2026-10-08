"""Publish editable diagram links and equivalent expanded paths, preserving sources."""
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
    d=invoke('document.create',id='stroke-outline-example',kind='vector',width=96,height=64)
    settings=[
        dict(color=[42,104,213,255],width_profile=[[0,.5],[.5,3],[1,1]],start_arrow=dict(kind='bar',length=2,width=8),end_arrow=dict(kind='triangle',length=10,width=10)),
        dict(color=[26,160,110,220],width_profile=[[0,1],[.25,2],[.75,2],[1,.5]],dash=dict(array=[8,4],offset=-2),start_arrow=dict(kind='ellipse',length=8,width=8),end_arrow=dict(kind='diamond',length=10,width=10)),
        dict(color=[190,100,45,240],width_profile=[[0,0],[1,3]],end_arrow=dict(kind='chevron',length=10,width=10)),
    ]
    items=[dict(id=f'link-{i}',name=f'Editable link {i+1}',content=dict(type='vector',geometry=dict(shape='path',commands=[dict(verb='move',to=[8,12+i*20]),dict(verb='line',to=[88,12+i*20])]),stroke=dict(width=2,cap='round',join='round',**s))) for i,s in enumerate(settings)]
    original=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=i) for i in items])['document']
    retained=copy.deepcopy(original);save('original.json',original);publish('editable',original)
    expanded=invoke('document.edit',document=original,expected_revision=original['revision'],operations=[dict(op='stroke_expand',id=i['id'],fill_id=i['id']+'-fill',stroke_id=i['id']+'-outline') for i in original['items']])
    save('expansion.json',expanded);publish('expanded',expanded['document'])
    save('diff.json',invoke('document.diff',before=original,after=expanded['document'],compare_pixels=True))
    assert json.loads((output/'original.json').read_text())==retained==original
    assert (output/'editable.png').read_bytes()==(output/'expanded.png').read_bytes()
    print('Published editable and expanded diagram links in '+str(output))


if __name__=='__main__':main()
