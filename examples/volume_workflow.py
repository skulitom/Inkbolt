"""Original dimensional diagram node with editable source, projected faces and undo."""
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
    d=invoke('document.create',id='dimensional-diagram-node',kind='vector',width=96,height=80)
    spec=dict(geometry=dict(shape='polygon',points=[[20,20],[70,20],[70,36],[45,36],[45,60],[20,60]]),depth=14,rotation=[25,-30,8],pivot=[45,40,-7],
              camera=dict(type='perspective',principal=[48,40],distance=200,near=20,far=400),
              material=dict(type='diffuse',color=[50,165,225],ambient=[.25,.25,.3],lights=[dict(direction=[-.5,-.7,1],color=[1,.95,.85],intensity=1)]))
    d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=dict(id='node',content=dict(type='volume',volume=spec)))])['document'];source=copy.deepcopy(d)
    for format in ['snapshot','png','svg','pdf']:publish(d,'source.'+('json' if format=='snapshot' else format),format)
    save('faces.json',invoke('volume.inspect',document=d,id='node'))
    session=dict(session_root=str(out/'sessions'),session_id='volume');invoke('session.create',**session,request_id='create',document=d)
    changed=copy.deepcopy(spec);changed['rotation']=[-15,40,-10]
    rotated=invoke('session.apply',**session,request_id='rotate',expected_revision=0,action=dict(type='edit',operations=[dict(op='volume',id='node',volume=changed)]))
    save('rotate.json',rotated);publish(rotated['document'],'rotated.png','png')
    expanded=invoke('session.apply',**session,request_id='expand',expected_revision=1,action=dict(type='edit',operations=[dict(op='volume_expand',id='node')]))
    save('expand.json',expanded);publish(expanded['document'],'expanded.json','snapshot');publish(expanded['document'],'expanded.png','png')
    undone=invoke('session.apply',**session,request_id='undo',expected_revision=2,action=dict(type='undo'))
    assert undone['document']['items']==rotated['document']['items'];save('undo.json',undone)
    save('verify.json',invoke('session.verify',**session));save('history.json',invoke('session.history',**session,limit=10));assert d==source
    print('Saved editable dimensional source, PNG/SVG/PDF faces, independent expansion and undo in '+str(out))


if __name__=='__main__':main()
