"""Original brick, hexagonal, mirrored and radial editable pattern fields."""
import argparse
import copy
import json
import math
from pathlib import Path
from mask_workflow import invoke
def path(points):return dict(shape='path',commands=[dict(verb='move' if i==0 else 'line',to=p) for i,p in enumerate(points)]+[dict(verb='close')])
def rect(x,y,w,h):return dict(shape='rect',x=x,y=y,width=w,height=h)
def cases():
    hexagon=path([[0,-8],[4*math.sqrt(3),-4],[4*math.sqrt(3),4],[0,8],[-4*math.sqrt(3),4],[-4*math.sqrt(3),-4]])
    outer=path([[-4,-3],[4,-3],[4,3],[-4,3]])
    outer['commands']+=path([[-2,-1],[-2,1],[0,1],[0,-1]])['commands']
    cases=[
        ('brick',rect(-4,-3,8,6),dict(type='brick',columns=4,rows=3,step=[8,6]),[14,14]),
        ('hex',hexagon,dict(type='hex',columns=3,rows=3,radius=8),[14,14]),
        ('mirrored',outer,dict(type='grid',columns=3,rows=2,step=[12,12],mirror='both'),[14,14]),
        ('radial',rect(-3,-1,6,2),dict(type='radial',count=8,radius=18,orientation='tangent'),[44,32]),
    ]
    return {n:dict(geometry=g,fill=[40,120,220,255],layout=layout,origin=origin) for n,g,layout,origin in cases}
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);out=p.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    def publish(name,d):
        for fmt,ext in [('snapshot','json'),('png','png'),('svg','svg')]:
            save(name+'-'+fmt+'-receipt.json',invoke('document.publish',document=d,output=dict(output_root=str(out),file_name=name+'.'+ext,format=fmt,scale=2 if fmt=='png' else 1)))
    for name,s in cases().items():
        d=invoke('document.create',id='original-repeat-'+name,kind='vector',width=96,height=64)
        d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=dict(id='pattern',name='Editable '+name+' field',content=dict(type='repeat',repeat=s)))])['document']
        retained=copy.deepcopy(d);publish(name+'-editable',d)
        save(name+'-inspection.json',invoke('repeat.inspect',repeat=s,include_geometry=True))
        operation=dict(op='repeat_expand',id='pattern');save(name+'-operation.json',operation)
        result=invoke('document.edit',document=d,expected_revision=d['revision'],operations=[operation]);save(name+'-edit.json',result);publish(name+'-expanded',result['document'])
        save(name+'-diff.json',invoke('document.diff',before=d,after=result['document'],compare_pixels=True))
        assert retained==d and (out/(name+'-editable.png')).read_bytes()==(out/(name+'-expanded.png')).read_bytes()
    print('Saved four editable repeat layouts, retained motifs, inspections and matching expanded PNG/SVG deliveries in '+str(out))
if __name__=='__main__':main()
