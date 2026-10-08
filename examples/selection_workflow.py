"""Original image edit: select, subtract, soften, mask, apply and undo safely.

Run: python examples/selection_workflow.py C:/absolute/new-output-directory
"""
import json
from pathlib import Path
import sys
from mask_workflow import invoke


def main(destination):
    output=Path(destination)
    if not output.is_absolute():raise ValueError('Use an absolute new output directory')
    output.mkdir(parents=True,exist_ok=False)
    source=invoke('document.create',id='original-pattern',kind='raster',width=64,height=48)
    pixels=bytes(v for y in range(48) for x in range(64) for v in (x*4,y*5,180+(x//8%2)*30,255))
    source=invoke('document.edit',document=source,expected_revision=0,operations=[dict(op='add',item=dict(id='pattern',content=dict(type='raster',width=64,height=48,rgba_hex=pixels.hex())))])['document']
    invoke('document.publish',document=source,output=dict(output_root=str(output),file_name='original-source.png',format='png'))
    asset=invoke('asset.import',source_path=str(output/'original-source.png'),store_root=str(output/'assets'))['asset']
    document=invoke('document.create',id='selection-image-edit',kind='raster',width=96,height=64)
    document=invoke('document.edit',document=document,expected_revision=0,operations=[dict(op='asset_put',id='source',asset=asset),dict(op='add',item=dict(id='picture',transform=[1,0,0,1,16,8],content=dict(type='image',asset_id='source',width=64,height=48)))])['document']
    args=dict(session_root=str(output/'sessions'),session_id='selection-image-edit')
    invoke('session.create',**args,request_id='create',document=document,resources=dict(asset_root=str(output/'assets')))
    def publish(revision,name,format='png'):
        return invoke('session.publish',**args,expected_revision=revision,output=dict(output_root=str(output),file_name=name,format=format))
    receipts=[publish(0,'before.png'),publish(0,'original.json','snapshot')]
    operations=[dict(op='selection_shape',boundary=dict(shape='rect',x=24,y=16,width=48,height=32)),dict(op='selection_shape',boundary=dict(shape='rect',x=46,y=22,width=8,height=20),combine='subtract'),dict(op='selection_refine',mode='feather',radius=2),dict(op='mask_from_selection',id='picture')]
    invoke('session.apply',**args,request_id='select-mask',expected_revision=0,action=dict(type='edit',label='Select and soften cutout',operations=operations))
    receipts.extend([publish(1,'masked.png'),publish(1,'editable.json','snapshot')])
    invoke('session.apply',**args,request_id='apply-mask',expected_revision=1,action=dict(type='edit',label='Apply at native pixels',operations=[dict(op='mask_apply',id='picture'),dict(op='selection_set',selection=None)]))
    receipts.extend([publish(2,'applied.png'),publish(2,'applied.json','snapshot')])
    comparison=invoke('session.diff',**args,from_revision=1,to_revision=2,compare_pixels=True)
    invoke('session.apply',**args,request_id='undo-application',expected_revision=2,action=dict(type='undo'))
    receipts.append(publish(3,'editable-restored.json','snapshot'))
    invoke('session.apply',**args,request_id='undo-mask',expected_revision=3,action=dict(type='undo'))
    receipts.append(publish(4,'restored.png'))
    invoke('session.verify',**args)
    print(json.dumps(dict(receipts=receipts,application_diff=comparison),indent=2))


if __name__=='__main__':main(sys.argv[1])
