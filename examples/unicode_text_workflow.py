"""Explicit local-font Unicode labels, retained sources and create-only deliveries."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from mask_workflow import invoke


def cases():
    return {
        'arabic': ('\u0628\u0628\u062a', 'rtl', 'ar'),
        'indic': ('\u0915\u093f\u0915', 'ltr', 'hi'),
        'east': ('\u4e00\u3042\u30fc\u30a2\u30fc', 'ltr', 'ja'),
        'marks': ('A\u0301e\u0301', 'ltr', 'en'),
        'hangul': ('\u1100\u1161', 'ltr', 'ko'),
        'ligature': ('fiA', 'ltr', 'en'),
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--font',action='append',required=True,help='ID=absolute-font-path; supply latin, arabic, indic, east and marks')
    parser.add_argument('--license',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();paths={}
    for value in args.font:
        name,path=value.split('=',1)
        if name in paths: parser.error('Font IDs must be unique')
        paths[name]=Path(path).resolve()
    if set(paths)!={'latin','arabic','indic','east','marks'}:
        parser.error('Supply the five declared font IDs')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    store=out/'fonts';resources=dict(font_root=str(store))
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    originals={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in paths.items()}
    fonts={name:invoke('font.import',source_path=str(path),license_path=str(args.license.resolve()),store_root=str(store)) for name,path in paths.items()}
    save('font-inputs.json',dict(fonts=fonts,source_sha256=originals,license_sha256=hashlib.sha256(args.license.read_bytes()).hexdigest()))
    for kind in ('vector','raster'):
        for name,(text,direction,language) in cases().items():
            prefix=kind+'-'+name
            d=invoke('document.create',id=prefix,kind=kind,width=300,height=80)
            frame=dict(text=text,width=100,height=20,wrap=False,direction=direction,overflow='visible',
                style=dict(font_id='latin',fallback_fonts=['marks','arabic','indic','east'],
                    language=language,size=10,fill=[25,100,200,255]))
            d=invoke('document.edit',document=d,expected_revision=0,operations=[
                *[dict(op='font_put',id=id,font=f) for id,f in fonts.items()],
                dict(op='add',item=dict(id='label',transform=[5,0,0,5,3,2],content=dict(type='text',frame=frame)))
            ])['document']
            source=copy.deepcopy(d);save(prefix+'-source.json',source)
            save(prefix+'-inspection.json',invoke('text.inspect',document=d,id='label',font_root=str(store),include_outlines=True))
            for fmt in ['snapshot','png','tiff']+(['svg'] if kind=='vector' else []):
                ext='json' if fmt=='snapshot' else fmt
                output=dict(output_root=str(out),file_name=prefix+'.'+ext,format=fmt,scale=4 if fmt in ['png','tiff'] else 1)
                save(prefix+'-'+fmt+'-receipt.json',invoke('document.publish',document=d,resources=resources,output=output))
            if kind=='vector':
                outlined=invoke('document.edit',document=d,expected_revision=d['revision'],font_root=str(store),
                    operations=[dict(op='text_outline',id='label')])['document']
                save(prefix+'-outlined.json',outlined)
            assert d==source
    assert originals=={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in paths.items()}
    print('Saved twelve editable Unicode label documents and explicit-font deliveries in '+str(out))


if __name__=='__main__':main()
