"""Build one original editable badge, expand it, bake delivery and restore its source."""
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
    def publish(document,name,format):
        save(name+'-receipt.json',invoke('document.publish',document=document,output=dict(output_root=str(out),file_name=name,format=format)))
    d=invoke('document.create',id='original-appearance-badge',kind='vector',width=64,height=64)
    spec=dict(geometry=dict(shape='rounded_rect',x=14,y=14,width=36,height=32,radii=[6,6,6,6]),passes=[
        dict(id='offset',fill=[20,38,62,255],maps=[dict(type='affine',matrix=[1,0,0,1,0,5])]),
        dict(id='outer',stroke=dict(color=[20,38,62,255],width=6,join='round')),
        dict(id='body',fill=[30,160,220,255]),
        dict(id='rim',stroke=dict(color=[238,250,255,190],width=2,join='round'))])
    d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=dict(id='badge',content=dict(type='appearance',appearance=spec)))])['document']
    source=copy.deepcopy(d);publish(d,'source.json','snapshot');publish(d,'source.png','png');publish(d,'source.svg','svg')
    save('inspect.json',invoke('appearance.inspect',document=d,id='badge'))
    session=dict(session_root=str(out/'sessions'),session_id='badge')
    invoke('session.create',**session,request_id='create',document=d)
    expanded=invoke('session.apply',**session,request_id='expand',expected_revision=0,action=dict(type='edit',operations=[dict(op='appearance_expand',id='badge')]))
    save('expand.json',expanded);publish(expanded['document'],'expanded.json','snapshot');publish(expanded['document'],'expanded.png','png')
    restored=invoke('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'))['document']
    assert restored['items']==source['items']
    filtered=copy.deepcopy(spec);filtered['passes'][0]['filters']=[dict(id='soften',operator=dict(type='gaussian',sigma=1))]
    filtered=invoke('session.apply',**session,request_id='soften',expected_revision=2,action=dict(type='edit',operations=[dict(op='appearance',id='badge',appearance=filtered)]))['document']
    publish(filtered,'filtered.json','snapshot');publish(filtered,'filtered.png','png')
    baked=invoke('session.apply',**session,request_id='bake',expected_revision=3,action=dict(type='edit',operations=[dict(op='appearance_bake',id='badge',asset_id='badge-pixels',image_id='badge-image',region=dict(origin=[0,0],width=64,height=64,scale=1))]))
    save('bake.json',baked)
    for format in ['snapshot','png','svg','pdf']:publish(baked['document'],'baked.'+('json' if format=='snapshot' else format),format)
    save('history.json',invoke('session.history',**session,limit=10));save('verify.json',invoke('session.verify',**session))
    assert d==source
    print('Saved editable appearance, independent expansion, explicit pixel delivery and undo history in '+str(out))


if __name__=='__main__':main()
