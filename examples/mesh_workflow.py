"""Original editable mesh shading, interior-knot edit and bounded delivery."""
import argparse
import copy
import json
from pathlib import Path
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    m=dict(origin=[0,0],size=[64,48],columns=3,rows=3,svg_samples_per_cell=32,knots=[])
    for y in range(3):
        for x in range(3):m['knots'].append(dict(color=[50+19*x+7*y,180-13*x-17*y,70+6*x*y,64+15*x+23*y],offset=[0,0]))
    d=invoke('document.create',id='original-mesh-shading',kind='vector',width=64,height=48)
    item=dict(id='shading',content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=64,height=48),fill=dict(type='mesh',mesh=m)))
    d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=item)])['document'];original=copy.deepcopy(d)
    edited=invoke('document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='mesh_knot',id='shading',column=1,row=1,color=[100,110,140,96],offset=[3,-2])])['document']
    for name,document in [('original',original),('edited',edited)]:
        field=document['items'][0]['content']['fill']
        save(name+'-inspection.json',invoke('mesh.inspect',mesh=field['mesh'],space=field['space'],parameters=[[x/4,y/4] for y in range(9) for x in range(9)]))
        for format,extension in [('snapshot','json'),('png','png'),('tiff','tif'),('svg','svg')]:
            output=dict(output_root=str(out),file_name=name+'.'+extension,format=format)
            save(name+'-'+format+'-receipt.json',invoke('document.publish',document=document,output=output))
    save('difference.json',invoke('document.diff',before=original,after=edited,compare_pixels=True))
    assert d==original
    print('Saved editable mesh sources, independent-knot inspection and image/SVG delivery in '+str(out))


if __name__=='__main__':main()
