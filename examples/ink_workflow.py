"""Original overlap chart with retained spot ink and explicit process conversion."""
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
    def publish(d,name,format):
        options=dict(output_root=str(out),file_name=name,format=format)
        if format=='pdf':options['pdf_options']=dict(color='native_inks')
        save(name+'-receipt.json',invoke('document.publish',document=d,output=options))
    d=invoke('document.create',id='native-ink-overlaps',kind='vector',width=48,height=16)
    d['swatches']={
        'base':dict(name='Process base',definition=dict(type='process',color=dict(space='cmyk',components=[.5,.25,0,0],preview_srgb=[.5,.75,1]))),
        'accent':dict(name='Original warm ink',definition=dict(type='spot',alternate=dict(space='cmyk',components=[0,0,.75,0],preview_srgb=[1,1,.25])))}
    def rect(id,x,width,fill):return dict(id=id,content=dict(type='vector',geometry=dict(shape='rect',x=x,y=2,width=width,height=12),fill=fill))
    d['items']=[rect('base',2,44,dict(swatch='base'))]
    for i,mode in enumerate(['knockout','preserve','preserve_nonzero']):
        d['items'].append(rect('patch-'+str(i),4+14*i,10,dict(swatch='accent',tint=.5,overprint=mode)))
    d=invoke('document.validate',document=d);source=copy.deepcopy(d)
    publish(d,'original.json','snapshot');publish(d,'spot.pdf','pdf');save('spot-inventory.json',invoke('swatch.inspect',document=d))
    converted=invoke('document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='swatch_convert',id='accent',kind='process')])
    save('conversion-receipt.json',converted);p=converted['document']
    publish(p,'process.json','snapshot');publish(p,'process.pdf','pdf');save('process-inventory.json',invoke('swatch.inspect',document=p))
    assert d==source and p['items']==d['items']
    print('Saved exact spot/process snapshots, native ink PDFs and explicit conversion diagnostics in '+str(out))


if __name__=='__main__':main()
