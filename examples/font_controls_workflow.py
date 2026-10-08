"""Retained local variable-font labels with instance inspection and explicit delivery."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from mask_workflow import invoke


def cases():
    return {
        'default': ({}, {}, False),
        'light-narrow': ({'wght':100,'wdth':50}, {}, False),
        'intermediate': ({'wght':650,'wdth':150}, {}, False),
        'bold-wide': ({'wght':900,'wdth':200}, {}, False),
        'alternate': ({'wght':650,'wdth':150}, {'salt':2,'liga':0}, False),
        'path': ({'wght':900,'wdth':150}, {'ss01':1}, True),
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--font',required=True,type=Path)
    parser.add_argument('--license',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    store=out/'fonts';resources=dict(font_root=str(store))
    source=args.font.resolve();source_sha=hashlib.sha256(source.read_bytes()).hexdigest()
    font=invoke('font.import',source_path=str(source),license_path=str(args.license.resolve()),store_root=str(store))
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    save('font-input.json',dict(font=font,source_sha256=source_sha))
    for kind in ['vector','raster']:
        for name,(coordinates,features,path) in cases().items():
            prefix=kind+'-'+name
            save(prefix+'-font-inspection.json',invoke('font.inspect',font=font,font_root=str(store),variations=coordinates))
            d=invoke('document.create',id=prefix,kind=kind,width=300,height=100)
            frame=dict(text='fiAA',width=100,height=40,wrap=False,overflow='visible',
                style=dict(font_id='body',font_variations={'body':coordinates},features=features,size=10,fill=[25,100,200,255]))
            if path:
                frame['path']=dict(geometry=dict(shape='path',commands=[dict(verb='move',to=[0,15]),dict(verb='line',to=[70,15])]))
            d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='font_put',id='body',font=font),
                dict(op='add',item=dict(id='label',transform=[5,0,0,5,3,2],content=dict(type='text',frame=frame)))])['document']
            saved=copy.deepcopy(d);save(prefix+'-source.json',saved)
            save(prefix+'-inspection.json',invoke('text.inspect',document=d,id='label',font_root=str(store),include_outlines=True))
            for fmt in ['snapshot','png','tiff']+(['svg'] if kind=='vector' else []):
                ext='json' if fmt=='snapshot' else fmt
                output=dict(output_root=str(out),file_name=prefix+'.'+ext,format=fmt,scale=4 if fmt in ['png','tiff'] else 1)
                save(prefix+'-'+fmt+'-receipt.json',invoke('document.publish',document=d,resources=resources,output=output))
            if kind=='vector':
                outlined=invoke('document.edit',document=d,expected_revision=d['revision'],font_root=str(store),
                    operations=[dict(op='text_outline',id='label')])['document']
                save(prefix+'-outlined.json',outlined)
            assert d==saved
    assert hashlib.sha256(source.read_bytes()).hexdigest()==source_sha
    print('Saved twelve editable font-instance documents and independent delivery formats in '+str(out))


if __name__=='__main__':main()
