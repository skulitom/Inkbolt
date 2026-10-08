"""Original coordinate charts with retained projective, mesh and articulated controls."""
import argparse
import copy
import json
from pathlib import Path
from mask_workflow import invoke

def cases():
    mesh=dict(type='mesh',columns=2,rows=2,points=[[2,2],[6,2],[10,2],[2,6],[7,5],[10,6],[2,10],[6,10],[10,10]])
    return {
        'perspective':(dict(type='perspective',corners=[[2,2],[12,3],[11,12],[1,10]]),'nearest'),
        'mesh':(mesh,'bilinear'),
        'articulated':(dict(type='articulated',columns=2,rows=4,joints=[dict(pivot=[0,0],angle=0,translation=[2,2]),dict(parent=0,pivot=[4,4],angle=35)],weights=[[1-r/4,r/4] for r in range(5) for c in range(3)]),'bilinear'),
        'mirrored':(dict(mesh,points=[[12-x,y] for x,y in mesh['points']]),'nearest')
    }
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);out=p.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    def publish(name,d):
        for fmt,ext in [('snapshot','json'),('png','png'),('tiff','tiff')]:
            save(name+'-'+fmt+'-receipt.json',invoke('document.publish',document=d,output=dict(output_root=str(out),file_name=name+'.'+ext,format=fmt,scale=4 if fmt!='snapshot' else 1)))
    rgba=bytes(v for y in range(8) for x in range(8) for v in [x*24,y*24,(x^y)*24,64+32*((x+y)%6)]).hex()
    for name,(warp,sampling) in cases().items():
        d=invoke('document.create',id='original-pixel-warp-'+name,kind='raster',width=16,height=16)
        d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=dict(id='pixels',name='Original coordinate chart',content=dict(type='raster',width=8,height=8,rgba_hex=rgba,sampling=sampling)))])['document']
        retained=copy.deepcopy(d);publish(name+'-source',d)
        op=dict(op='pixel_warp',id='pixels',warp=warp);save(name+'-operation.json',op)
        result=invoke('document.edit',document=d,expected_revision=d['revision'],operations=[op]);save(name+'-edit.json',result);publish(name+'-editable',result['document'])
        save(name+'-inspection.json',invoke('pixel_warp.inspect',warp=warp,width=8,height=8,include_mesh=True,samples=[[x,y] for y in [0,2,4,6,8] for x in [0,2,4,6,8]],inverse_samples=[[4,4],[6,6],[8,8],[0,0],[15,15]]))
        save(name+'-diff.json',invoke('document.diff',before=d,after=result['document'],compare_pixels=True))
        assert retained==d and result['document']['items'][0]['content']==d['items'][0]['content']
    print('Saved four original coordinate charts, retained deformation controls, inverse inspections and PNG/TIFF deliveries in '+str(out))
if __name__=='__main__':main()
