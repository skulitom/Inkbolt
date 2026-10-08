"""Retain original transparent artwork through opaque background conversion."""
import argparse
import copy
import json
from pathlib import Path
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    w,h=32,24
    colors=bytes(v for y in range(h) for x in range(w)
        for v in [30+5*x,40+6*y,180,255 if 4<=x<28 and 4<=y<20 else 96 if (x+y)%3==0 else 0])
    d=invoke('document.create',id='retained-background',kind='raster',width=40,height=32)
    d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=dict(id='art',name='Original artwork',transform=[1,0,0,1,4,4],content=dict(type='raster',width=w,height=h,rgba_hex=colors.hex())))])['document']
    original=copy.deepcopy(d)
    def edit(d,*ops):return invoke('document.edit',document=d,expected_revision=d['revision'],operations=list(ops))['document']
    def convert(d,type,**kw):return edit(d,dict(op='background',id='art',action=dict(type=type,**kw)))
    bg=convert(d,'promote',matte=[238,244,250])
    duplicate=edit(bg,dict(op='duplicate',id='art',new_id='copy'),dict(op='pixel_fill',id='copy',rect=dict(x=8,y=7,width=16,height=10),color=[240,150,35,192]))
    ordinary=convert(bg,'to_layer',source_id='retained',matte_id='paper')
    restored=convert(bg,'restore_source')
    assert d==original and bg['items']==original['items'] and restored['items']==original['items']
    assert duplicate['items'][0]==original['items'][0]
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    for name,doc in [('original',d),('background',bg),('duplicate-edited',duplicate),('ordinary-layer',ordinary),('restored-source',restored)]:
        save(name+'.json',doc)
        for fmt in ['png','tiff','pdf']:
            output=dict(output_root=str(out),file_name=name+'.'+fmt,format=fmt,scale=4 if fmt!='pdf' else 1)
            save(name+'-'+fmt+'-receipt.json',invoke('document.publish',document=doc,output=output))
    print('Saved five editable states and source-preserving image/page deliveries in '+str(out))


if __name__=='__main__':main()
