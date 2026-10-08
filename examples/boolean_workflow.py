"""Build an original frame icon from rectangles, keeping source geometry and undo."""
import json
from pathlib import Path
import sys
from mask_workflow import invoke


def main(destination):
    output=Path(destination)
    if not output.is_absolute():raise ValueError('Use an absolute new output directory')
    output.mkdir(parents=True,exist_ok=False)
    d=invoke('document.create',id='frame-icon',kind='vector',width=32,height=24)
    boxes=[('outer',2,2,28,20),('opening',6,6,20,12),('notch',26,10,6,4)]
    items=[dict(id=id,content=dict(type='vector',geometry=dict(shape='rect',x=x,y=y,width=w,height=h),fill=[35,100,180,255])) for id,x,y,w,h in boxes]
    d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=i) for i in items])['document']
    combined=invoke('document.boolean',document=d,ids=[v[0] for v in boxes],mode='difference',curve_tolerance=0)
    with (output/'combination.json').open('x',encoding='utf8') as f:json.dump(combined,f,indent=2)
    args=dict(session_root=str(output/'sessions'),session_id='frame-icon')
    invoke('session.create',**args,request_id='create',document=d)
    def publish(revision,name,format):return invoke('session.publish',**args,expected_revision=revision,output=dict(output_root=str(output),file_name=name,format=format))
    receipts=[publish(0,'original.json','snapshot'),publish(0,'before.png','png'),publish(0,'before.svg','svg')]
    operations=[dict(op='properties',id=id,visible=False) for id,*_ in boxes]
    if not combined['empty']:operations.append(dict(op='add',item=dict(id='frame',name='Frame icon',content=dict(type='vector',geometry=combined['geometry'],fill_rule=combined['fill_rule'],fill=[35,100,180,255]))))
    invoke('session.apply',**args,expected_revision=0,request_id='combine',action=dict(type='edit',operations=operations))
    receipts.extend([publish(1,'combined.json','snapshot'),publish(1,'combined.png','png'),publish(1,'combined.svg','svg')])
    difference=invoke('session.diff',**args,from_revision=0,to_revision=1,compare_pixels=True)
    invoke('session.apply',**args,expected_revision=1,request_id='undo',action=dict(type='undo'))
    receipts.extend([publish(2,'restored.json','snapshot'),publish(2,'restored.png','png'),publish(2,'restored.svg','svg')])
    invoke('session.verify',**args)
    print(json.dumps(dict(receipts=receipts,diff=difference),indent=2))


if __name__=='__main__':main(sys.argv[1])
