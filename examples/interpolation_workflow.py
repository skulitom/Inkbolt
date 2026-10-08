"""Original editable shape/color progressions and curved diagram markers."""
import argparse
import copy
import json
from pathlib import Path
from mask_workflow import invoke

def rect(x,y,w,h):return dict(shape='rect',x=x,y=y,width=w,height=h)
def path(points):
    return dict(shape='path',commands=[dict(verb='move' if i==0 else 'line',to=p) for i,p in enumerate(points)]+[dict(verb='close')])
def endpoint(g,color):return dict(geometry=g,fill=color)
def cases():
    a=[240,40,20,255];b=[20,80,240,255]
    base={'from':endpoint(rect(4,8,4,4),a),'to':endpoint(rect(52,20,12,8),b),'count':5}
    topology={'from':endpoint(path([[10,16],[22,16],[16,28]]),a),'to':endpoint(rect(68,16,12,12),b),'count':5}
    spine=dict(shape='path',commands=[dict(verb='move',to=[12,40]),dict(verb='cubic',control1=[24,4],control2=[64,4],to=[84,40])])
    curved={'from':endpoint(rect(-2,-1,4,2),a),'to':endpoint(rect(-3,-2,6,4),b),'count':7,'spine':dict(geometry=spine,tolerance=.0001),'orientation':'tangent','space':'linear_rgb'}
    ring=path([[8,20],[20,20],[20,32],[8,32]])
    ring['commands']+=path([[12,24],[12,28],[16,28],[16,24]])['commands']
    holes={'from':endpoint(ring,a),'to':endpoint(rect(68,20,12,12),b),'count':3}
    return dict(axis=base,topology=topology,curved=curved,holes=holes)

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);out=p.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    def publish(name,d):
        for fmt,ext in [('snapshot','json'),('png','png'),('svg','svg')]:
            save(name+'-'+fmt+'-receipt.json',invoke('document.publish',document=d,output=dict(output_root=str(out),file_name=name+'.'+ext,format=fmt,scale=2 if fmt=='png' else 1)))
    for name,s in cases().items():
        d=invoke('document.create',id='original-interpolation-'+name,kind='vector',width=96,height=64)
        d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=dict(id='sequence',name='Editable '+name+' progression',content=dict(type='interpolation',interpolation=s)))])['document']
        retained=copy.deepcopy(d);publish(name+'-editable',d)
        save(name+'-inspection.json',invoke('interpolation.inspect',interpolation=s,include_geometry=True))
        operation=dict(op='interpolation_expand',id='sequence');save(name+'-operation.json',operation)
        result=invoke('document.edit',document=d,expected_revision=d['revision'],operations=[operation])
        save(name+'-edit.json',result);publish(name+'-expanded',result['document'])
        save(name+'-diff.json',invoke('document.diff',before=d,after=result['document'],compare_pixels=True))
        assert d==retained and (out/(name+'-editable.png')).read_bytes()==(out/(name+'-expanded.png')).read_bytes()
    print('Saved four editable progressions, inspections, expanded vectors and matching PNG/SVG deliveries in '+str(out))

if __name__=='__main__':main()
