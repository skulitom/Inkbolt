"""Export named original layout datasets while retaining editable source properties."""
import argparse
import copy
import json
from pathlib import Path
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    output=parser.parse_args().output.resolve();output.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (output/name).open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(value,indent=2)+'\n')
    def val(type,value):return dict(type=type,value=value)
    definition=dict(bindings=[dict(key='place',item_id='tile',property='position'),dict(key='show',item_id='badge',property='visible'),dict(key='fade',item_id='tile',property='opacity')],datasets=dict(
        wide=dict(values=dict(place=val('position',[20,10]))),
        quiet=dict(parent='wide',values=dict(show=val('visible',False))),
        faint=dict(values=dict(fade=val('opacity',.5)))))
    for kind in ('vector','raster'):
        d=invoke('document.create',id='variants-'+kind,kind=kind,width=64,height=32)
        items=[]
        for id,x,y,size,color in [('tile',8,10,12,[40,100,220,255]),('badge',48,6,4,[30,180,100,255])]:
            content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=size,height=size),fill=color) if kind=='vector' else dict(type='raster',width=size,height=size,rgba_hex=bytes(color).hex()*(size*size))
            items.append(dict(id=id,transform=[1,0,0,1,x,y],content=content))
        original=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=i) for i in items])['document']
        retained=copy.deepcopy(original);save(kind+'-source.json',original)
        base=invoke('document.edit',document=original,expected_revision=original['revision'],operations=[dict(op='variants_set',definition=definition)])['document']
        for name in ('base','wide','quiet','faint'):
            change=invoke('document.edit',document=base,expected_revision=base['revision'],operations=[dict(op='variant_select',dataset=None if name=='base' else name)])
            current=change['document'];save(kind+'-'+name+'-selection.json',change)
            for fmt in ['snapshot','png']+(['svg'] if kind=='vector' else []):
                ext='json' if fmt=='snapshot' else fmt
                receipt=invoke('document.publish',document=current,output=dict(output_root=str(output),file_name=kind+'-'+name+'.'+ext,format=fmt,scale=2 if fmt=='png' else 1));save(kind+'-'+name+'-'+fmt+'-receipt.json',receipt)
            save(kind+'-'+name+'-diff.json',invoke('document.diff',before=base,after=current,compare_pixels=True))
            restored=invoke('document.edit',document=current,expected_revision=current['revision'],operations=[dict(op='variant_select',dataset=None)])['document']
            assert restored['items']==original['items']
        assert original==retained==json.loads((output/(kind+'-source.json')).read_text())
    print('Published four editable datasets for each document kind in '+str(output))


if __name__=='__main__':main()
