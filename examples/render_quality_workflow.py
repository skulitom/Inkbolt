"""Original editable icon with explicit image quality and effect evaluation bounds."""
import argparse
import copy
import json
from pathlib import Path
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    d=invoke('document.create',id='quality-icon',kind='vector',width=64,height=48)
    items=[dict(id='disc',content=dict(type='vector',geometry=dict(shape='ellipse',cx=31.125,cy=23.625,rx=23.75,ry=17.25),fill=[35,110,200,255]),effects=[dict(id='shadow',operator=dict(type='shadow',sigma=1.5,offset=[2.5,2.25]),color=[10,30,70,130])]),
        dict(id='mark',content=dict(type='vector',geometry=dict(shape='path',commands=[dict(verb='move',to=[17.25,24.125]),dict(verb='line',to=[27.625,31.25]),dict(verb='line',to=[45.375,15.125]),dict(verb='line',to=[42.25,12.5]),dict(verb='line',to=[27.375,26.25]),dict(verb='line',to=[20.125,21.125]),dict(verb='close')]),fill=[255,235,175,255]))]
    d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=i) for i in items])['document'];original=copy.deepcopy(d)
    def save(name,v):
        with (out/name).open('x',encoding='utf8') as f:json.dump(v,f,indent=2);f.write('\n')
    save('original.json',d)
    for name,opts,fmt in [('coverage',{},'png'),('smooth',dict(antialias='supersample4',padding=8),'png'),('linear',dict(antialias='supersample4',averaging_space='linear_srgb',padding=8),'png'),('padded',dict(antialias='supersample4',padding=8,crop_to_canvas=False),'tiff')]:
        output=dict(output_root=str(out),file_name=name+'.'+('tif' if fmt=='tiff' else fmt),format=fmt,render_options=opts)
        save(name+'-receipt.json',invoke('document.publish',document=d,output=output))
    assert d==original
    assert json.loads(invoke('document.export',document=d,format='snapshot')['data'])==d
    print('Saved editable source and four explicitly sampled images in '+str(out))


if __name__=='__main__':main()
