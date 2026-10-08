"""Original shared palette with explicit retained declarations and preview delivery."""
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
        save(name+'-receipt.json',invoke('document.publish',document=d,output=dict(output_root=str(out),file_name=name,format=format)))
    d=invoke('document.create',id='shared-palette',kind='vector',width=34,height=16)
    d['swatches']={
        'accent':dict(name='Cool accent',definition=dict(type='process',color=dict(space='srgb',components=[.125,.5,.875]))),
        'ink':dict(name='Original warm ink',definition=dict(type='spot',alternate=dict(space='srgb',components=[.75,.25,.125]))),
        'pale':dict(name='Quarter tint',definition=dict(type='tint',base='ink',tint=.25)),
        'neutral':dict(name='Neutral',definition=dict(type='process',color=dict(space='gray',component=.375)))}
    for i,id in enumerate(['accent','ink','pale','neutral']):
        d['items'].append(dict(id='tile-'+str(i),content=dict(type='vector',geometry=dict(shape='rect',x=2+8*i,y=2,width=6,height=12),fill=dict(swatch=id))))
    d=invoke('document.validate',document=d);source=copy.deepcopy(d)
    publish(d,'original.json','snapshot');publish(d,'before.png','png');save('palette-before.json',invoke('swatch.inspect',document=d))
    color=copy.deepcopy(d['swatches']['ink']);color['definition']['alternate']['components']=[.125,.75,.5]
    changed=invoke('document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='swatch',id='ink',swatch=color)])['document']
    publish(changed,'recolored.json','snapshot');publish(changed,'after.png','png');save('palette-after.json',invoke('swatch.inspect',document=changed))
    save('comparison.json',invoke('document.diff',before=d,after=changed,compare_pixels=True))
    baked=invoke('document.edit',document=changed,expected_revision=changed['revision'],operations=[dict(op='swatch_bake',ids=[i['id'] for i in changed['items']])])
    save('bake-receipt.json',baked);publish(baked['document'],'display.svg','svg');publish(baked['document'],'display.pdf','pdf')
    assert d==source and changed['items']==source['items']
    print('Saved retained palettes, exact snapshots, before/after previews and explicitly baked SVG/PDF in '+str(out))


if __name__=='__main__':main()
