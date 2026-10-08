"""Reduce an original diagram connector with a retained certificate and session undo."""
import json
from pathlib import Path
import sys
from mask_workflow import invoke


def halve(points):
    a,b,c,d=points
    def mid(a,b):return [(x+y)/2 for x,y in zip(a,b)]
    e,f,g=mid(a,b),mid(b,c),mid(c,d);h,i=mid(e,f),mid(f,g);j=mid(h,i)
    return [a,e,h,j],[j,i,g,d]


def main(destination):
    output=Path(destination)
    if not output.is_absolute():raise ValueError('Use an absolute new output directory')
    output.mkdir(parents=True,exist_ok=False)
    document=invoke('document.create',id='simplified-diagram',kind='vector',width=64,height=48)
    curves=[[[12,18],[20,40],[44,40],[52,18]]]
    for _ in range(3):curves=[part for curve in curves for part in halve(curve)]
    commands=[dict(verb='move',to=curves[0][0])]+[dict(verb='cubic',control1=c[1],control2=c[2],to=c[3]) for c in curves]
    items=[dict(id='left',content=dict(type='vector',geometry=dict(shape='rounded_rect',x=2,y=2,width=20,height=16,radii=[3]*4),fill=[35,75,150,255])),dict(id='right',content=dict(type='vector',geometry=dict(shape='rounded_rect',x=42,y=2,width=20,height=16,radii=[3]*4),fill=[25,140,110,255])),dict(id='connector',content=dict(type='vector',geometry=dict(shape='path',commands=commands),fill=None,stroke=dict(color=[45,95,185,255],width=2)))]
    document=invoke('document.edit',document=document,expected_revision=0,operations=[dict(op='add',item=i) for i in items])['document']
    args=dict(session_root=str(output/'sessions'),session_id='simplified-diagram')
    invoke('session.create',**args,request_id='create',document=document)
    def publish(revision,name,format):return invoke('session.publish',**args,expected_revision=revision,output=dict(output_root=str(output),file_name=name,format=format))
    receipts=[publish(0,'original.json','snapshot'),publish(0,'before.png','png'),publish(0,'before.svg','svg')]
    result=invoke('session.apply',**args,expected_revision=0,request_id='simplify',action=dict(type='edit',operations=[dict(op='path',id='connector',action=dict(type='simplify',tolerance=1e-10,space='world',max_span=8))]))
    certificate=result['receipt']['changes'][0]['details']
    with (output/'certificate.json').open('x',encoding='utf8') as f:json.dump(certificate,f,indent=2)
    receipts.extend([publish(1,'simplified.json','snapshot'),publish(1,'simplified.png','png'),publish(1,'simplified.svg','svg')])
    difference=invoke('session.diff',**args,from_revision=0,to_revision=1,compare_pixels=True)
    invoke('session.apply',**args,expected_revision=1,request_id='undo',action=dict(type='undo'))
    receipts.extend([publish(2,'restored.json','snapshot'),publish(2,'restored.png','png'),publish(2,'restored.svg','svg')])
    invoke('session.verify',**args)
    print(json.dumps(dict(receipts=receipts,certificate=certificate,diff=difference),indent=2))


if __name__=='__main__':main(sys.argv[1])
