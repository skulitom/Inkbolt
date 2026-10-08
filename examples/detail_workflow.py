"""Original median cleanup, seeded texture and editable spatial styling.

Run: python examples/detail_workflow.py C:/absolute/new-output-directory
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
    source=invoke('document.create',id='original-detail-chart',kind='raster',width=w,height=h)
    pixels=bytes(v for y in range(h) for x in range(w) for v in (x*7,y*9,(x^y)*5,0 if x<3 else (79 if y<4 else 255)))
    source=invoke('document.edit',document=source,expected_revision=0,operations=[dict(op='add',item=dict(id='chart',content=dict(type='raster',width=w,height=h,rgba_hex=pixels.hex())))])['document']
    invoke('document.publish',document=source,output=dict(output_root=str(output),file_name='original-source.png',format='png'))
    asset=invoke('asset.import',source_path=str(output/'original-source.png'),store_root=str(output/'assets'))['asset']
    document=invoke('document.create',id='detail-image-edit',kind='raster',width=w,height=h)
    document=invoke('document.edit',document=document,expected_revision=0,operations=[dict(op='asset_put',id='source',asset=asset),dict(op='add',item=dict(id='picture',content=dict(type='image',asset_id='source',width=w,height=h)))])['document']
    args=dict(session_root=str(output/'sessions'),session_id='detail-image-edit')
    invoke('session.create',**args,request_id='create',document=document,resources=dict(asset_root=str(output/'assets')))
    def publish(revision,name,format='png'):
        return invoke('session.publish',**args,expected_revision=revision,output=dict(output_root=str(output),file_name=name,format=format))
    receipts=[publish(0,'original.json','snapshot'),publish(0,'before.png')]
    clean=dict(id='clean',operator=dict(type='detail',operator=dict(type='median',radius=1)),border='clamp')
    noise=dict(id='texture',operator=dict(type='detail',operator=dict(type='noise',amount=.05,seed=314)),opacity=.75)
    invoke('session.apply',**args,expected_revision=0,request_id='detail',action=dict(type='edit',operations=[dict(op='filters',id='picture',filters=[clean,noise])]))
    receipts.extend([publish(1,'detailed.json','snapshot'),publish(1,'detailed.png')])
    field=dict(width=2,height=2,vectors=[[-1,-1],[1,-1],[-1,1],[1,1]],transform=[16,0,0,12,0,0],sampling='bilinear')
    displacement=dict(id='bend',operator=dict(type='spatial',operator=dict(type='displace',map=field,amount=[2,-1])),border='reflect')
    mosaic=dict(id='blocks',operator=dict(type='spatial',operator=dict(type='mosaic',size=4)))
    invoke('session.apply',**args,expected_revision=1,request_id='stylize',action=dict(type='edit',operations=[dict(op='filters',id='picture',filters=[clean,noise,displacement,mosaic])]))
    receipts.extend([publish(2,'stylized.json','snapshot'),publish(2,'stylized.png')])
    diffs=[invoke('session.diff',**args,from_revision=0,to_revision=n,compare_pixels=True) for n in (1,2)]
    invoke('session.apply',**args,expected_revision=2,request_id='undo-style',action=dict(type='undo'))
    receipts.append(publish(3,'detailed-restored.png'))
    invoke('session.apply',**args,expected_revision=3,request_id='undo-detail',action=dict(type='undo'))
    receipts.extend([publish(4,'restored.json','snapshot'),publish(4,'restored.png')])
    invoke('session.verify',**args)
    print(json.dumps(dict(receipts=receipts,diffs=diffs),indent=2))


if __name__=='__main__':main(sys.argv[1])
