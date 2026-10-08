"""Original editable motif routes, compound contours and variable-width graphics."""
import argparse
import copy
import json
from pathlib import Path
from mask_workflow import invoke

def path(points):
    return dict(shape='path',commands=[dict(verb='move' if i==0 else 'line',to=p) for i,p in enumerate(points)])
def rect(x,y,w,h):return dict(shape='rect',x=x,y=y,width=w,height=h)
def ring():
    g=path([[-.5,-.5],[.5,-.5],[.5,.5],[-.5,.5]])
    g['commands'].append(dict(verb='close'))
    g['commands']+=path([[-.25,-.25],[-.25,.25],[.25,.25],[.25,-.25]])['commands']+[dict(verb='close')]
    return g

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    def publish(name,d):
        for fmt,ext in [('snapshot','json'),('png','png'),('svg','svg')]:
            save(name+'-'+fmt+'-receipt.json',invoke('document.publish',document=d,output=dict(output_root=str(out),file_name=name+'.'+ext,format=fmt,scale=2 if fmt=='png' else 1)))
    compound=path([[12,16],[84,16]]);compound['commands']+=path([[12,42],[84,42]])['commands']
    cases=[
        ('route',path([[12,12],[52,12],[52,44]]),dict(motif=ring(),spacing=2,corner_motif=rect(-1,-.25,2,.5),corner_clearance=1,corner_orientation='bisector',start_motif=rect(-.5,-.5,1,1),end_motif=rect(-.5,-.5,1,1),end_clearance=1),[]),
        ('compound',compound,dict(motif=ring(),spacing=4,phase=1),[]),
        ('profile',path([[12,32],[84,32]]),dict(motif=rect(-.5,-.5,1,1),spacing=3),[[0,.5],[.5,2],[1,.5]]),
    ]
    for name,g,brush,profile in cases:
        d=invoke('document.create',id='original-vector-brush-'+name,kind='vector',width=96,height=64)
        node=dict(id='path',name='Editable motif '+name,content=dict(type='vector',geometry=g,stroke=dict(color=[30,100,210,255],width=4,brush=brush,width_profile=profile)))
        d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=node)])['document']
        retained=copy.deepcopy(d);publish(name+'-editable',d)
        operation=dict(op='stroke_expand',id='path',fill_id='centerline',stroke_id='outline')
        save(name+'-operation.json',operation)
        result=invoke('document.edit',document=d,expected_revision=d['revision'],operations=[operation])
        save(name+'-edit.json',result);publish(name+'-expanded',result['document'])
        save(name+'-diff.json',invoke('document.diff',before=d,after=result['document'],compare_pixels=True))
        assert d==retained
        assert (out/(name+'-editable.png')).read_bytes()==(out/(name+'-expanded.png')).read_bytes()
    print('Saved three original editable brush graphics, retained centerlines, expansion receipts and matching PNG/SVG deliveries in '+str(out))

if __name__=='__main__':main()
