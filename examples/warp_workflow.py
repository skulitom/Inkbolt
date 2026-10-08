"""Retained perspective, nonlinear envelopes and nested deformations with certificates."""
import argparse
import copy
import json
from pathlib import Path
from mask_workflow import invoke

def cases():
    g=dict(shape='rect',x=0,y=0,width=24,height=24)
    project=dict(type='perspective',domain=[0,0,24,24],corners=[[12,8],[42,12],[38,40],[8,32]])
    points=[[[6+8*x,6+8*y] for x in range(4)] for y in range(4)]
    points[0][1][1]-=4;points[0][2][1]+=6;points[1][1][0]+=4;points[2][2][1]-=6
    envelope=dict(type='envelope',domain=[0,0,24,24],points=points)
    outer=copy.deepcopy(envelope);outer['domain']=[0,0,48,48]
    curve=dict(shape='path',commands=[dict(verb='move',to=[2,12]),dict(verb='cubic',control1=[4,1],control2=[20,23],to=[22,12]),dict(verb='close')])
    return {n:dict(geometry=geometry,fill=[40,120,220,255],maps=maps,tolerance=.02) for n,geometry,maps in [
        ('perspective',g,[project]),('envelope',g,[envelope]),
        ('nested',g,[project,outer,dict(type='affine',matrix=[1,0,.25,1,4,2])]),
        ('curved',curve,[envelope])
    ]}

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);out=p.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    def publish(name,d):
        for fmt,ext in [('snapshot','json'),('png','png'),('svg','svg')]:
            save(name+'-'+fmt+'-receipt.json',invoke('document.publish',document=d,output=dict(output_root=str(out),file_name=name+'.'+ext,format=fmt,scale=2 if fmt=='png' else 1)))
    for name,s in cases().items():
        d=invoke('document.create',id='original-warp-'+name,kind='vector',width=64,height=48)
        d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=dict(id='warped',name='Editable '+name+' geometry',content=dict(type='warp',warp=s)))])['document']
        retained=copy.deepcopy(d);publish(name+'-editable',d)
        save(name+'-inspection.json',invoke('warp.inspect',warp=s,include_geometry=True,include_segments=True,samples=[[0,0],[24,0],[24,24],[0,24],[12,12]],grid=dict(domain=[0,0,24,24],columns=2,rows=2)))
        op=dict(op='warp_expand',id='warped');save(name+'-operation.json',op)
        result=invoke('document.edit',document=d,expected_revision=d['revision'],operations=[op]);save(name+'-edit.json',result);publish(name+'-expanded',result['document'])
        save(name+'-diff.json',invoke('document.diff',before=d,after=result['document'],compare_pixels=True))
        assert retained==d and (out/(name+'-editable.png')).read_bytes()==(out/(name+'-expanded.png')).read_bytes()
    print('Saved four editable warp fixtures, source controls, certified geometry, perspective/envelope grids and matching PNG/SVG deliveries in '+str(out))
if __name__=='__main__':main()
