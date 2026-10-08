"""Edit an original image through a masked tone layer; measure, export and undo.

Run: python examples/adjustment_workflow.py C:/absolute/new-output-directory
"""
import json
from pathlib import Path
import sys
from mask_workflow import invoke


def main(destination):
    output=Path(destination)
    if not output.is_absolute():raise ValueError('Use an absolute new output directory')
    output.mkdir(parents=True,exist_ok=False)
    source=invoke('document.create',id='original-tone-chart',kind='raster',width=96,height=64)
    pixels=bytes(v for y in range(64) for x in range(96) for v in (x*2,y*3,80+(x+y)%96,255))
    source=invoke('document.edit',document=source,expected_revision=0,operations=[dict(op='add',item=dict(id='chart',content=dict(type='raster',width=96,height=64,rgba_hex=pixels.hex())))])['document']
    invoke('document.publish',document=source,output=dict(output_root=str(output),file_name='original-source.png',format='png'))
    asset=invoke('asset.import',source_path=str(output/'original-source.png'),store_root=str(output/'assets'))['asset']
    document=invoke('document.create',id='tone-image-edit',kind='raster',width=96,height=64)
    document=invoke('document.edit',document=document,expected_revision=0,operations=[dict(op='asset_put',id='source',asset=asset),dict(op='add',item=dict(id='picture',content=dict(type='image',asset_id='source',width=96,height=64)))])['document']
    args=dict(session_root=str(output/'sessions'),session_id='tone-image-edit')
    resources=dict(asset_root=str(output/'assets'))
    invoke('session.create',**args,request_id='create',document=document,resources=resources)
    def publish(revision,name,format='png'):
        return invoke('session.publish',**args,expected_revision=revision,output=dict(output_root=str(output),file_name=name,format=format))
    receipts=[publish(0,'original.json','snapshot'),publish(0,'before.png')]
    before=invoke('document.measure',document=document,**resources)
    operators=[dict(type='exposure',stops=0.5),dict(type='curve',points=[[0,0],[0.25,0.2],[0.75,0.85],[1,1]])]
    operations=[dict(op='add',item=dict(id='tone',name='Local exposure and contrast',content=dict(type='adjustment',adjustment=dict(operators=operators,clip_to='picture')))),dict(op='selection_shape',boundary=dict(shape='rect',x=16,y=8,width=64,height=48)),dict(op='selection_refine',mode='feather',radius=2),dict(op='mask_from_selection',id='tone')]
    edited=invoke('session.apply',**args,expected_revision=0,request_id='tone',action=dict(type='edit',label='Adjust selected region',operations=operations))['document']
    receipts.extend([publish(1,'edited.json','snapshot'),publish(1,'edited.png')])
    after=invoke('document.measure',document=edited,**resources)
    selected=invoke('document.measure',document=edited,options=dict(use_selection=True,alpha='weight',samples=[[48,32],[0,0]]),**resources)
    comparison=invoke('session.diff',**args,from_revision=0,to_revision=1,compare_pixels=True)
    invoke('session.apply',**args,expected_revision=1,request_id='undo',action=dict(type='undo'))
    receipts.extend([publish(2,'restored.json','snapshot'),publish(2,'restored.png')])
    invoke('session.verify',**args)
    with (output/'measurements.json').open('x',encoding='utf8') as f:
        json.dump(dict(before=before,after=after,selected=selected),f,indent=2);f.write('\n')
    print(json.dumps(dict(receipts=receipts,diff=comparison),indent=2))


if __name__=='__main__':main(sys.argv[1])
