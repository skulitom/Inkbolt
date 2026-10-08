"""Create overlapping agent graphics with inspectable group compositing."""
import argparse
import json
from pathlib import Path
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    output=parser.parse_args().output.resolve();output.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (output/name).open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(value,indent=2)+'\n')
    def rect(id,box,color,**kw):
        x,y,w,h=box
        return dict(id=id,content=dict(type='vector',geometry=dict(shape='rect',x=x,y=y,width=w,height=h),fill=color),**kw)
    def publish(name,d):
        for fmt,extension in [('snapshot','json'),('png','png')]:
            save(name+'-'+fmt+'-receipt.json',invoke('document.publish',document=d,output=dict(output_root=str(output),file_name=name+'.'+extension,format=fmt)))
    d=invoke('document.create',id='knockout-example',kind='vector',width=24,height=16)
    items=[rect('background',[0,0,24,16],[30,65,110,173]),dict(id='cards',content=dict(type='group',isolated=True)),rect('coral',[2,2,12,9],[230,75,95,255],parent='cards',opacity=.625),rect('teal',[8,5,13,9],[35,200,170,255],parent='cards',opacity=.375,blend='multiply'),rect('cutout',[11,7,5,5],[240,190,60,128],parent='cards',opacity=.5)]
    original=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=i) for i in items])['document']
    save('original.json',original);publish('layered',original)
    for name,isolated,cut in [('isolated',True,False),('pass-through',False,False),('cutout',False,True)]:
        ops=[dict(op='group_options',id='cards',isolated=isolated,knockout=True)]
        if cut:ops.append(dict(op='properties',id='cutout',opacity=0))
        result=invoke('document.edit',document=original,expected_revision=original['revision'],operations=ops)
        save(name+'-edit.json',result);publish(name,result['document'])
    assert json.loads((output/'original.json').read_text())==original
    print('Published four editable group-compositing variants; original geometry and paints preserved in '+str(output))


if __name__=='__main__':main()
