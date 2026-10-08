"""Two original panels share editable gradient/shape mask artwork and durable undo.

Run: python examples/artwork_mask_workflow.py C:/absolute/new-output-directory
All artifacts are create-only; the destination must not exist.
"""
import json
from pathlib import Path
import sys
from mask_workflow import invoke


def main(destination):
    output=Path(destination)
    if not output.is_absolute():raise ValueError('Use an absolute new output directory')
    output.mkdir(parents=True,exist_ok=False)
    def rectangle(id,parent,x,y,w,h,fill,**kw):
        return dict(id=id,parent=parent,content=dict(type='vector',geometry=dict(shape='rect',x=x,y=y,width=w,height=h),fill=fill),**kw)
    d=invoke('document.create',id='shared-reveal',kind='vector',width=232,height=104)
    gradient=dict(type='linear',start=[0,0],end=[96,0],stops=[dict(offset=0,color=[255,255,255,64]),dict(offset=1,color=[255,255,255,255])])
    items=[dict(id='reveal',content=dict(type='mask_source')),
           rectangle('fade','reveal',0,0,96,72,gradient),
           rectangle('window','reveal',16,16,48,40,[255,255,255,255])]
    for n,x in enumerate((12,124)):
        board=f'panel-{n}'
        items.append(dict(id=board,name=f'Panel {n+1}',transform=[1,0,0,1,x,16],content=dict(type='group'),artwork_mask=dict(source='reveal',region=[0,0,96,72])))
        items.extend([rectangle(f'background-{n}',board,0,0,96,72,[31,147,219,255]),rectangle(f'node-{n}',board,24,24,48,24,[243,168,72,255])])
    d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=i) for i in items])['document']
    args=dict(session_root=str(output/'sessions'),session_id='shared-reveal')
    invoke('session.create',**args,request_id='create',document=d)
    def publish(revision,name,format):
        return invoke('session.publish',**args,expected_revision=revision,output=dict(output_root=str(output),file_name=name,format=format))
    receipts=[publish(0,'before.json','snapshot'),publish(0,'before.png','png'),publish(0,'before.svg','svg')]
    invoke('session.apply',**args,expected_revision=0,request_id='revise-source',action=dict(type='edit',label='Revise both reveals',operations=[dict(op='properties',id='window',opacity=.25),dict(op='transform',id='window',matrix=[1,0,0,1,16,0])]))
    receipts.extend([publish(1,'edited.json','snapshot'),publish(1,'edited.png','png'),publish(1,'edited.svg','svg')])
    delta=invoke('session.diff',**args,from_revision=0,to_revision=1,compare_pixels=True)
    invoke('session.apply',**args,expected_revision=1,request_id='undo',action=dict(type='undo'))
    receipts.append(publish(2,'restored.png','png'))
    invoke('session.verify',**args)
    print(json.dumps(dict(receipts=receipts,diff=delta),indent=2))


if __name__=='__main__':main(sys.argv[1])
