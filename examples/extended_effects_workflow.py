"""Publish editable lighting, contour, gradient and effect-scale variations."""
import argparse
import json
from pathlib import Path
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    output=parser.parse_args().output.resolve();output.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (output/name).open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(value,indent=2)+'\n')
    def publish(name,d):
        for fmt,extension in [('snapshot','json'),('png','png')]:
            save(name+'-'+fmt+'-receipt.json',invoke('document.publish',document=d,output=dict(output_root=str(output),file_name=name+'.'+extension,format=fmt)))
    def gradient(a,b):return dict(type='linear',start=[0,0],end=[12,0],stops=[dict(offset=0,color=a),dict(offset=1,color=b)])
    colors=[[40+9*x,80+8*y,210,255 if 3<x<9 and 2<y<8 else 128] if 3<=x<=9 and 2<=y<=8 and not(6<=x<=7 and 4<=y<=6) else [220,30,80,0] for y in range(10) for x in range(12)]
    d=invoke('document.create',id='extended-effects-example',kind='raster',width=12,height=10)
    original=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=dict(id='art',content=dict(type='raster',width=12,height=10,rgba_hex=bytes(v for p in colors for v in p).hex())))])['document']
    save('original.json',original);publish('before',original)
    fx=[dict(id='shared',operator=dict(type='lit_shadow',distance=1.5,sigma=.5),color=[15,35,80,160],scale=1.25,contour=[[0,0],[.5,.75],[1,1]]),dict(id='local',operator=dict(type='lit_shadow',distance=1,sigma=0,azimuth=90),color=[180,70,45,80],scale=1.5),dict(id='outline',operator=dict(type='stroke',radius=1),color=gradient([230,90,30,64],[240,210,80,255])),dict(id='tint',operator=dict(type='overlay'),color=gradient([25,100,210,100],[30,200,170,200]),contour=[[0,0],[.5,.75],[1,1]],opacity=.625)]
    styled_ops=[dict(op='effects',id='art',effects=fx),dict(op='properties',id='art',fill_opacity=.625),dict(op='global_light',light=dict(azimuth=180))]
    variants=[('styled',styled_ops),('relit',styled_ops+[dict(op='global_light',light=dict(azimuth=270))]),('scaled',styled_ops+[dict(op='effects_scale',ids=['art'],factor=1.5)])]
    for name,ops in variants:
        result=invoke('document.edit',document=original,expected_revision=original['revision'],operations=ops)
        assert result['document']['items'][0]['content']==original['items'][0]['content']
        save(name+'-edit.json',result);publish(name,result['document'])
    assert json.loads((output/'original.json').read_text())==original
    print('Published original plus three editable light/contour/gradient/scale variants in '+str(output))


if __name__=='__main__':main()
