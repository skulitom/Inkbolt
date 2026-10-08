"""Original editable color tiles delivered with explicit RGB profiles."""
import argparse
import copy
import json
from pathlib import Path
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (out/name).open('x',encoding='utf8',newline='\n') as f:json.dump(value,f,indent=2);f.write('\n')
    d=invoke('document.create',id='original-profile-tiles',kind='vector',width=64,height=32)
    colors=[[20,80,220,255],[220,90,40,255],[30,180,110,128],[120,70,180,64]]
    items=[dict(id='tile-'+str(i),content=dict(type='vector',geometry=dict(shape='rect',x=i%2*32,y=i//2*16,width=32,height=16),fill=color)) for i,color in enumerate(colors)]
    d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=item) for item in items])['document'];source=copy.deepcopy(d);save('source.json',source)
    save('source-preview.json',invoke('document.render',document=source))
    for name in ['srgb','linear_srgb','display_p3']:
        result=invoke('document.edit',document=source,expected_revision=source['revision'],operations=[dict(op='output_profile',profile=dict(type='builtin',name=name))]);changed=result['document'];save(name+'-edit.json',result);save(name+'-inspect.json',invoke('document.inspect',document=changed))
        for format,extension in [('snapshot','json'),('png','png'),('tiff','tiff'),('jpeg','jpg')]:
            output=dict(output_root=str(out),file_name=name+'.'+extension,format=format)
            if format=='jpeg':output['image_options']=dict(quality=100,chroma='full',matte=[245]*3)
            save(name+'-'+format+'-receipt.json',invoke('document.publish',document=changed,output=output))
        save(name+'-import.json',invoke('asset.import',source_path=str(out/(name+'.png')),store_root=str(out/'assets'),color_policy='convert_srgb'))
        save(name+'-diff.json',invoke('document.diff',before=source,after=changed,compare_pixels=True))
    assert d==source==json.loads((out/'source.json').read_text())
    print('Published independently profiled PNG/TIFF/JPEG with retained source artwork in '+str(out))


if __name__=='__main__':main()
