"""Original editable curved label using an explicitly supplied licensed local font."""
import argparse
import copy
import json
from pathlib import Path
from mask_workflow import invoke


def main():
    p=argparse.ArgumentParser();p.add_argument('--font',type=Path,required=True);p.add_argument('--license',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--text',default='INKBOLT');args=p.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);store=out/'fonts'
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    font=invoke('font.import',source_path=str(args.font.resolve()),license_path=str(args.license.resolve()),store_root=str(store))
    d=invoke('document.create',id='original-curved-label',kind='vector',width=128,height=80)
    path=dict(geometry=dict(shape='path',commands=[dict(verb='move',to=[10,56]),dict(verb='cubic',control1=[26,8],control2=[98,8],to=[118,56])]),tolerance=.001)
    frame=dict(text=args.text,width=128,height=80,wrap=False,align='center',overflow='error',style=dict(font_id='label-font',size=16,fill=[25,100,200,220]),path=path)
    d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='font_put',id='label-font',font=font),dict(op='add',item=dict(id='label',content=dict(type='text',frame=frame)))])['document'];original=copy.deepcopy(d)
    frame=copy.deepcopy(d['items'][0]['content']['frame']);frame['path']['flip']=True;frame['path']['normal_offset']=3
    edited=invoke('document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='text',id='label',frame=frame)])['document']
    resources=dict(font_root=str(store))
    for name,document in [('original',original),('flipped',edited)]:
        save(name+'-inspection.json',invoke('text.inspect',document=document,id='label',include_outlines=True,**resources))
        outlined=invoke('document.edit',document=document,expected_revision=document['revision'],operations=[dict(op='text_outline',id='label')],**resources)['document'];save(name+'-outlined.json',outlined)
        for format,extension in [('snapshot','json'),('png','png'),('tiff','tif'),('svg','svg')]:
            save(name+'-'+format+'-receipt.json',invoke('document.publish',document=document,resources=resources,output=dict(output_root=str(out),file_name=name+'.'+extension,format=format)))
    save('difference.json',invoke('document.diff',before=original,after=edited,compare_pixels=True,before_resources=resources,after_resources=resources));assert d==original
    print('Saved editable curved labels, flipped placements, outlined copies and delivery receipts in '+str(out))


if __name__=='__main__':main()
