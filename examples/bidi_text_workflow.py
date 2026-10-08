"""Editable mixed-direction labels with explicit fonts and retained source text."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from mask_workflow import invoke


def cases():
    return {
        'mixed':dict(text='A \u05d0\u05d1 12 B'),
        'joining':dict(text='A \u0628\u0628\u062a B'),
        'brackets':dict(text='\u05d0 (12) \u05d1'),
        'marks':dict(text='A \u05d0\u05b0\u05d1 B'),
        'isolates':dict(text='A\u2067\u05d0\u2066AB\u2069\u05d1\u2069B'),
        'wrapped':dict(text='\u05d0 A B',width=8,wrap=True,align='start'),
        'path':dict(text='\u05d0\u05d1 AB',align='start',path=dict(geometry=dict(shape='path',commands=[
            dict(verb='move',to=[0,15]),dict(verb='line',to=[50,15])]))),
    }


def main():
    parser=argparse.ArgumentParser()
    for name in ['font','license','output']:parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    store=out/'fonts';resources=dict(font_root=str(store));source=args.font.resolve()
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    font=invoke('font.import',source_path=str(source),license_path=str(args.license.resolve()),store_root=str(store))
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    save('font-input.json',dict(font=font,source_sha256=digest))
    for kind in ['vector','raster']:
        for name,changes in cases().items():
            prefix=kind+'-'+name;d=invoke('document.create',id=prefix,kind=kind,width=300,height=200)
            frame=dict(width=100,height=40,wrap=False,overflow='visible',bidi='unicode',direction='auto',
                style=dict(font_id='body',size=10,fill=[25,100,200,255]))
            frame.update(changes)
            d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='font_put',id='body',font=font),
                dict(op='add',item=dict(id='label',transform=[5,0,0,5,3,2],content=dict(type='text',frame=frame)))])['document']
            saved=copy.deepcopy(d);save(prefix+'-source.json',saved)
            save(prefix+'-directions.json',invoke('text.directions',text=frame['text'],direction='auto'))
            save(prefix+'-inspection.json',invoke('text.inspect',document=d,id='label',include_outlines=True,**resources))
            for fmt in ['snapshot','png','tiff']+(['svg'] if kind=='vector' else []):
                output=dict(output_root=str(out),file_name=prefix+('.json' if fmt=='snapshot' else '.'+fmt),
                    format=fmt,scale=4 if fmt in ['png','tiff'] else 1)
                save(prefix+'-'+fmt+'-receipt.json',invoke('document.publish',document=d,resources=resources,output=output))
            if kind=='vector':
                outlined=invoke('document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='text_outline',id='label')],**resources)['document']
                save(prefix+'-outlined.json',outlined)
            assert d==saved
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
    print('Saved fourteen editable mixed-direction labels with reading-order inspection and delivery formats in '+str(out))


if __name__=='__main__':main()
