"""Original agent diagram with private working notes and reproducible public delivery."""
import argparse
import copy
import json
from pathlib import Path
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (out/name).open('x',encoding='utf8',newline='\n') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
    d=invoke('document.create',id='original-metadata-diagram',kind='vector',width=64,height=32,resolution_ppi=144)
    colors=[[20,80,220,255],[220,90,40,255],[30,180,110,255],[120,70,180,255]]
    items=[dict(id='node-'+str(i),content=dict(type='vector',geometry=dict(shape='rect',x=i%2*32,y=i//2*16,width=32,height=16),fill=color)) for i,color in enumerate(colors)]
    d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=item) for item in items])['document']
    original=copy.deepcopy(d);save('original.json',original)
    metadata=dict(title='Original four-part diagram',description='Editable agent graphic: café 漢字 🦉',author='Inkbolt example',rights='Original synthetic artwork; MIT',tags=['diagram','agent-delivery'],private={'working_source':str(out/'original.json'),'note':'Private drafting note'})
    operations=[dict(op='metadata',value=metadata)]+[dict(op='metadata',id=item['id'],value=dict(note='Original tile '+str(i),tags=['node'],private={'internal':'Drafting detail '+str(i)})) for i,item in enumerate(items)]
    d=invoke('document.edit',document=d,expected_revision=d['revision'],operations=operations)['document'];save('annotated.json',d)
    save('difference.json',invoke('document.diff',before=original,after=d,compare_pixels=True));save('inspection.json',invoke('document.inspect',document=d))
    save('master-receipt.json',invoke('document.publish',document=d,output=dict(output_root=str(out),file_name='master.json',format='snapshot')))
    for mode in ['public','strip']:
        for format,extension in [('png','png'),('jpeg','jpg'),('tiff','tif'),('svg','svg'),('snapshot','json')]:
            policy=dict(mode=mode,manifest=mode=='public',provenance=mode=='public')
            output=dict(output_root=str(out),file_name=mode+'.'+extension,format=format,metadata_policy=policy)
            if format=='jpeg':output['image_options']=dict(quality=100,chroma='full')
            save(mode+'-'+format+'-receipt.json',invoke('document.publish',document=d,output=output))
        for format,extension in [('png','png'),('jpeg','jpg'),('tiff','tif')]:
            save(mode+'-'+format+'-import.json',invoke('asset.import',source_path=str(out/(mode+'.'+extension)),store_root=str(out/'assets'),color_policy='require_srgb' if format=='png' else 'assume_srgb'))
    assert original==json.loads((out/'original.json').read_text(encoding='utf8'))
    print('Published public and stripped delivery files with preserved editable originals in '+str(out))


if __name__=='__main__':main()
