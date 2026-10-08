"""Publish original decorated artwork with distinct fill, opacity and coverage."""
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
    colors=[[40+6*x,80+5*y,210,255 if 4<=x<14 and 4<=y<12 else 128] if 3<=x<15 and 3<=y<13 and not(8<=x<11 and 6<=y<10) else [230,20,90,0] for y in range(16) for x in range(20)]
    d=invoke('document.create',id='appearance-example',kind='raster',width=20,height=16)
    original=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=dict(id='artwork',content=dict(type='raster',width=20,height=16,rgba_hex=bytes(v for p in colors for v in p).hex())))])['document']
    save('original.json',original);publish('before',original)
    effects=[dict(id='shadow',operator=dict(type='shadow',offset=[1.5,1.5],sigma=.75),color=[10,20,40,150]),dict(id='outline',operator=dict(type='stroke',radius=1),color=[220,170,55,255]),dict(id='tint',operator=dict(type='overlay'),color=[50,190,210,73],opacity=.625)]
    variants=[('decorated',1,1,None),('fill-quarter',.25,1,None),('opacity-quarter',1,.25,None),('fill-zero',0,1,None),('dissolve',.75,1,dict(type='dissolve',seed=827))]
    for name,fill,opacity,coverage in variants:
        props=dict(op='properties',id='artwork',fill_opacity=fill,opacity=opacity)
        if coverage:props['coverage']=coverage
        result=invoke('document.edit',document=original,expected_revision=original['revision'],operations=[dict(op='effects',id='artwork',effects=effects),props])
        assert result['document']['items'][0]['content']==original['items'][0]['content']
        save(name+'-edit.json',result);publish(name,result['document'])
    assert json.loads((output/'original.json').read_text())==original
    print('Published five editable effect/fill/coverage variants and preserved original artwork in '+str(output))


if __name__=='__main__':main()
