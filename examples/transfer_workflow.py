"""Compose a layout from original reusable artwork without editing its source."""
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
    def rectangle(id,parent,x,y,w,h,color):return dict(id=id,parent=parent,content=dict(type='vector',geometry=dict(shape='rect',x=x,y=y,width=w,height=h),fill=color))
    def layer(id,parent=None,transform=None):return dict(id=id,name='Library',parent=parent,transform=transform or [1,0,0,1,0,0],content=dict(type='group',role='layer',isolated=True))
    empty=invoke('document.create',id='source-library',kind='vector',width=64,height=32)
    items=[dict(id='icon',content=dict(type='component_source')),rectangle('body','icon',0,0,8,8,[40,100,220,255]),rectangle('mark','icon',2,2,4,4,[30,180,100,255]),layer('layer',transform=[1,0,0,1,4,4]),layer('nested','layer'),dict(id='card',parent='nested',content=dict(type='instance',instance=dict(source='icon'))),rectangle('spare',None,44,4,8,8,[100,100,100,255])]
    source=invoke('document.edit',document=empty,expected_revision=0,operations=[dict(op='add',item=item) for item in items])['document'];retained=copy.deepcopy(source);publish('source',source)
    empty=invoke('document.create',id='composed-layout',kind='vector',width=64,height=32)
    destination=invoke('document.edit',document=empty,expected_revision=0,operations=[dict(op='add',item=layer('parent',transform=[2,0,0,2,12,0])),dict(op='add',item=rectangle('banner',None,0,24,64,4,[45,55,75,255]))])['document'];publish('destination',destination)
    ops=[dict(op='transfer',transfer=dict(source=source,ids=['card'],prefix=prefix,parent='parent')) for prefix in ['one','two']]+[dict(op='transform',id='two-layer',space='world',matrix=[1,0,0,1,24,0])]
    save('transfer-operations.json',ops);result=invoke('document.edit',document=destination,expected_revision=destination['revision'],operations=ops);save('transfer.json',result);combined=result['document'];publish('combined',combined)
    edit=dict(op='vector',id='one-mark',geometry=dict(shape='rect',x=2,y=2,width=4,height=4),fill=[220,60,80,255],stroke=None)
    save('revision-operation.json',edit);revised=invoke('document.edit',document=combined,expected_revision=combined['revision'],operations=[edit])['document'];publish('revised',revised)
    save('revision-diff.json',invoke('document.diff',before=combined,after=revised,compare_pixels=True))
    assert source==retained==json.loads((output/'source.json').read_text())
    assert destination==json.loads((output/'destination.json').read_text())
    print('Published source library and independently editable transferred artwork in '+str(output))


if __name__=='__main__':main()
