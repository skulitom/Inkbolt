"""Original editable image filters with explicit borders, a mask and saved undo history.

Run: python examples/filter_workflow.py C:/absolute/new-output-directory
"""
import json
from pathlib import Path
import sys
from mask_workflow import invoke


def main(destination):
    output=Path(destination)
    if not output.is_absolute():raise ValueError('Use an absolute new output directory')
    output.mkdir(parents=True,exist_ok=False)
    w,h=32,24
    source=invoke('document.create',id='original-filter-chart',kind='raster',width=w,height=h)
    pixels=bytes(v for y in range(h) for x in range(w) for v in (x*7,y*9,(x^y)*5,0 if x<3 else (79 if y<4 else 255)))
    source=invoke('document.edit',document=source,expected_revision=0,operations=[dict(op='add',item=dict(id='chart',content=dict(type='raster',width=w,height=h,rgba_hex=pixels.hex())))])['document']
    invoke('document.publish',document=source,output=dict(output_root=str(output),file_name='original-source.png',format='png'))
    asset=invoke('asset.import',source_path=str(output/'original-source.png'),store_root=str(output/'assets'))['asset']
    document=invoke('document.create',id='filter-image-edit',kind='raster',width=w,height=h)
    document=invoke('document.edit',document=document,expected_revision=0,operations=[dict(op='asset_put',id='source',asset=asset),dict(op='add',item=dict(id='picture',content=dict(type='image',asset_id='source',width=w,height=h)))])['document']
    args=dict(session_root=str(output/'sessions'),session_id='filter-image-edit')
    invoke('session.create',**args,request_id='create',document=document,resources=dict(asset_root=str(output/'assets')))
    def publish(revision,name,format='png'):
        return invoke('session.publish',**args,expected_revision=revision,output=dict(output_root=str(output),file_name=name,format=format))
    receipts=[publish(0,'original.json','snapshot'),publish(0,'before.png')]
    mask=dict(width=w,height=h,gray_hex=bytes(x*8 for y in range(h) for x in range(w)).hex())
    blur=dict(id='soften',operator=dict(type='box',radius=1),border='reflect',opacity=.75,mask=mask)
    invoke('session.apply',**args,expected_revision=0,request_id='soften',action=dict(type='edit',operations=[dict(op='filters',id='picture',filters=[blur])]))
    receipts.extend([publish(1,'softened.json','snapshot'),publish(1,'softened.png')])
    spin=dict(id='spin',operator=dict(type='radial',center=[16,12],angle=180,samples=3),border='wrap',opacity=.5)
    invoke('session.apply',**args,expected_revision=1,request_id='spin',action=dict(type='edit',operations=[dict(op='filters',id='picture',filters=[blur,spin])]))
    receipts.extend([publish(2,'stacked.json','snapshot'),publish(2,'stacked.png')])
    diffs=[invoke('session.diff',**args,from_revision=0,to_revision=n,compare_pixels=True) for n in (1,2)]
    invoke('session.apply',**args,expected_revision=2,request_id='undo-spin',action=dict(type='undo'))
    receipts.append(publish(3,'softened-restored.png'))
    invoke('session.apply',**args,expected_revision=3,request_id='undo-soften',action=dict(type='undo'))
    receipts.extend([publish(4,'restored.json','snapshot'),publish(4,'restored.png')])
    invoke('session.verify',**args)
    print(json.dumps(dict(receipts=receipts,diffs=diffs),indent=2))


if __name__=='__main__':main(sys.argv[1])
