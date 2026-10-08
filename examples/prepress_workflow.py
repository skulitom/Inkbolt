"""Original two-page ink layout with retained trim, bleed and source snapshots."""
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
    d=invoke('document.create',id='original-two-page-layout',kind='vector',width=512,height=192)
    d['resolution_ppi']=96
    d['swatches']={
        'base':dict(name='Process field',definition=dict(type='process',color=dict(space='cmyk',components=[.5,.25,0,0]))),
        'accent':dict(name='Original accent',definition=dict(type='spot',alternate=dict(space='cmyk',components=[0,0,.75,0])))}
    for i,id in enumerate(['cover','detail']):
        d['items'].append(dict(id=id,transform=[1,0,0,1,16+256*i,16],content=dict(type='frame',frame=dict(role='artboard',width=192,height=96,bleed=dict(top=4,right=8,bottom=12,left=16)))))
        def rectangle(name,x,y,w,h,fill):return dict(id=id+'-'+name,parent=id,content=dict(type='vector',geometry=dict(shape='rect',x=x,y=y,width=w,height=h),fill=fill))
        d['items'].append(rectangle('base',-16,-4,216,112,dict(swatch='base')))
        for n,mode in enumerate(['knockout','preserve','preserve_nonzero']):
            d['items'].append(rectangle(mode,8+56*n,16,40,64,dict(swatch='accent',tint=.5+.5*i,overprint=mode)))
    d=invoke('document.validate',document=d);original=copy.deepcopy(d)
    save('source.json-receipt.json',invoke('document.publish',document=d,output=dict(output_root=str(out),file_name='source.json',format='snapshot')))
    save('ink-inventory.json',invoke('swatch.inspect',document=d))
    for bleed in [True,False]:
        name='with-bleed.pdf' if bleed else 'trimmed.pdf'
        output=dict(output_root=str(out),file_name=name,format='pdf',pdf_options=dict(color='native_inks',artboards=dict(type='ids',ids=['cover','detail']),include_bleed=bleed))
        save(name+'-receipt.json',invoke('document.publish',document=d,output=output))
    assert d==original
    print('Saved editable source, ordered native ink pages with and without bleed, and page/ink receipts in '+str(out))


if __name__=='__main__':main()
