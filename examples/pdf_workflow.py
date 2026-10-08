"""Original two-page diagram delivery with source retention and asymmetric bleed."""
import argparse
import copy
import json
from pathlib import Path
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    d=invoke('document.create',id='diagram-pages',kind='vector',width=480,height=240,resolution_ppi=96)
    items=[]
    for id,width,height,x in [('overview',192,144,0),('detail',144,192,220)]:
        items.append(dict(id=id,name=id.title(),transform=[1,0,0,1,x,0],content=dict(type='frame',frame=dict(role='artboard',width=width,height=height,bleed=dict(top=4,right=6,bottom=8,left=10),background=[248,250,252,255]))))
        items.append(dict(id=id+'-panel',parent=id,content=dict(type='vector',geometry=dict(shape='rounded_rect',x=16,y=16,width=width-32,height=height-32,radii=[12,12,12,12]),fill=[30,90,170,255])))
        items.append(dict(id=id+'-node',parent=id,opacity=.8,content=dict(type='vector',geometry=dict(shape='ellipse',cx=width/2,cy=height/2,rx=24,ry=24),fill=[240,170,30,255],stroke=dict(width=3,color=[255,255,255,255]))))
    d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=i) for i in items]+[dict(op='metadata',value=dict(title='Original two-page diagram',description='Local vector paths with page-specific dimensions.',private={'working_note':'Keep only in the editable snapshot'}))])['document']
    source=copy.deepcopy(d)
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    save('source.json',source)
    for name,selection,bleed in [('pages',dict(type='all'),False),('pages-with-bleed',dict(type='ids',ids=['detail','overview']),True)]:
        output=dict(output_root=str(out),file_name=name+'.pdf',format='pdf',pdf_options=dict(artboards=selection,include_bleed=bleed))
        save(name+'-receipt.json',invoke('document.publish',document=d,output=output))
    for id in ['overview','detail']:
        for fmt in ['png','svg']:
            output=dict(output_root=str(out),file_name=id+'.'+fmt,format=fmt,artboard_id=id,scale=4 if fmt=='png' else 1)
            save(id+'-'+fmt+'-receipt.json',invoke('document.publish',document=d,output=output))
    assert d==source
    print('Saved editable source, two ordered PDF deliveries and independent page previews in '+str(out))


if __name__=='__main__':main()
