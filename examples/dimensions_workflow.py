"""Original editable card with physical dimensions and explicit guide placement."""
import argparse
import copy
import json
from pathlib import Path
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    d=invoke('document.create',id='measured-card',kind='vector',width=128,height=88)
    d['resolution_ppi']=127
    def rect(id,x,y,w,h,color):
        return dict(id=id,parent='card',content=dict(type='vector',geometry=dict(shape='rect',x=x,y=y,width=w,height=h),fill=color))
    items=[dict(id='page',content=dict(type='frame',frame=dict(role='artboard',width=128,height=88,guides=[dict(id='center-x',axis='x',position=64),dict(id='center-y',axis='y',position=44)]))),
        dict(id='card',parent='page',content=dict(type='group'),transform=[1,0,0,1,5,6]),
        rect('surface',0,0,30,20,[30,90,160,255]),rect('title',4,5,16,2,[255,235,180,255]),
        rect('detail',4,9,22,2,[190,220,250,255]),rect('badge',22,3,4,4,[245,160,60,255])]
    d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=i) for i in items])['document'];source=copy.deepcopy(d)
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    save('original.json',d)
    save('before-measurements.json',invoke('geometry.measure',document=d,options=dict(ids=['card'],unit='mm')))
    operations=[dict(op='dimensions',id='card',dimensions=dict(width=18,unit='mm',preserve_aspect=True)),
        dict(op='snap',ids=['card'],snap=dict(targets=[dict(type='guide',frame_id='page',id='center-x'),dict(type='guide',frame_id='page',id='center-y')],max_distance=12,unit='mm'))]
    result=invoke('document.edit',document=d,expected_revision=d['revision'],operations=operations)
    save('layout-receipt.json',result);changed=result['document']
    save('after-measurements.json',invoke('geometry.measure',document=changed,options=dict(ids=['card'],unit='mm')))
    for name,fmt in [('layout.json','snapshot'),('layout.svg','svg'),('layout.png','png')]:
        save(name+'-receipt.json',invoke('document.publish',document=changed,output=dict(output_root=str(out),file_name=name,format=fmt)))
    assert d==source and changed['items'][2:]==source['items'][2:]
    print('Saved original and edited source, measurements, SVG and PNG in '+str(out))


if __name__=='__main__':main()
