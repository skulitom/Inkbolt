"""Original color-region isolation with retained channels, mask previews and undo.

Run: python examples/channel_workflow.py C:/absolute/new-output-directory
"""
import base64
import json
from pathlib import Path
import sys
from mask_workflow import invoke


def main(destination):
    output=Path(destination)
    if not output.is_absolute():raise ValueError('Use an absolute new output directory')
    output.mkdir(parents=True,exist_ok=False)
    w,h=32,24
    def pixel(x,y):
        if 4<=x<15 and 4<=y<20:return (215+(x-4)*3,40,50,255)
        if 22<=x<29 and 7<=y<15:return (230,40,50,255)
        return (30,90,190,0 if x<3 else 79 if y<4 else 255)
    source=invoke('document.create',id='original-region-chart',kind='raster',width=w,height=h)
    pixels=bytes(v for y in range(h) for x in range(w) for v in pixel(x,y))
    source=invoke('document.edit',document=source,expected_revision=0,operations=[dict(op='add',item=dict(id='chart',content=dict(type='raster',width=w,height=h,rgba_hex=pixels.hex())))])['document']
    invoke('document.publish',document=source,output=dict(output_root=str(output),file_name='original-source.png',format='png'))
    asset=invoke('asset.import',source_path=str(output/'original-source.png'),store_root=str(output/'assets'))['asset']
    document=invoke('document.create',id='channel-image-edit',kind='raster',width=w,height=h)
    document=invoke('document.edit',document=document,expected_revision=0,operations=[dict(op='asset_put',id='source',asset=asset),dict(op='add',item=dict(id='picture',content=dict(type='image',asset_id='source',width=w,height=h)))])['document']
    args=dict(session_root=str(output/'sessions'),session_id='channel-image-edit')
    invoke('session.create',**args,request_id='create',document=document,resources=dict(asset_root=str(output/'assets')))
    def publish(revision,name,format='png'):
        return invoke('session.publish',**args,expected_revision=revision,output=dict(output_root=str(output),file_name=name,format=format))
    receipts=[publish(0,'original.json','snapshot'),publish(0,'before.png')]
    operations=[
        dict(op='selection_sample',method=dict(type='connected',seeds=[[9,8]],tolerance=8,feather=16,components='rgb')),
        dict(op='channel_calculate',id='raw-region',name='Raw connected region',calculation=dict(type='copy',source=dict(type='selection'))),
        dict(op='selection_sample',method=dict(type='edge',radius=1,tolerance=64,black=16,white=240)),
        dict(op='channel_calculate',id='region-ink',name='Region ink',role=dict(type='spot',ink_id='warm-region',alternate_srgb=[230,40,50]),calculation=dict(type='combine',left=dict(type='selection'),right=dict(type='component',component='alpha'),mode='multiply')),
        dict(op='selection_set',selection=None),dict(op='channel_load',id='region-ink'),
    ]
    selected=invoke('session.apply',**args,expected_revision=0,request_id='select-save',action=dict(type='edit',operations=operations))['document']
    receipts.extend([publish(1,'selected.json','snapshot'),publish(1,'selected.png')])
    for display in ('gray','ink'):
        result=invoke('channel.export',document=selected,id='region-ink',display=display)
        data=base64.b64decode(result.pop('data'))
        with (output/('channel-'+display+'.png')).open('xb') as f:f.write(data)
        with (output/('channel-'+display+'.json')).open('x',encoding='utf8') as f:json.dump(result,f,indent=2)
    invoke('session.apply',**args,expected_revision=1,request_id='isolate',action=dict(type='edit',operations=[dict(op='mask_from_selection',id='picture')]))
    receipts.extend([publish(2,'isolated.json','snapshot'),publish(2,'isolated.png')])
    diffs=[invoke('session.diff',**args,from_revision=0,to_revision=n,compare_pixels=True) for n in (1,2)]
    invoke('session.apply',**args,expected_revision=2,request_id='undo-mask',action=dict(type='undo'))
    receipts.append(publish(3,'selected-restored.png'))
    invoke('session.apply',**args,expected_revision=3,request_id='undo-channels',action=dict(type='undo'))
    receipts.extend([publish(4,'restored.json','snapshot'),publish(4,'restored.png')])
    invoke('session.verify',**args)
    print(json.dumps(dict(receipts=receipts,diffs=diffs),indent=2))


if __name__=='__main__':main(sys.argv[1])
