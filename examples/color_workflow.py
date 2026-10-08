"""Original local recoloring with an editable lookup, palette map and durable undo.

Run: python examples/color_workflow.py C:/absolute/new-output-directory
"""
import json
from pathlib import Path
import sys
from mask_workflow import invoke


def main(destination):
    output=Path(destination)
    if not output.is_absolute():raise ValueError('Use an absolute new output directory')
    output.mkdir(parents=True,exist_ok=False)
    source=invoke('document.create',id='original-color-chart',kind='raster',width=64,height=48)
    pixels=bytes(v for y in range(48) for x in range(64) for v in (x*4,y*5,60+(x//8%2)*128,0 if x<4 and y<4 else (128 if y<8 else 255)))
    source=invoke('document.edit',document=source,expected_revision=0,operations=[dict(op='add',item=dict(id='chart',content=dict(type='raster',width=64,height=48,rgba_hex=pixels.hex())))])['document']
    invoke('document.publish',document=source,output=dict(output_root=str(output),file_name='original-source.png',format='png'))
    asset=invoke('asset.import',source_path=str(output/'original-source.png'),store_root=str(output/'assets'))['asset']
    document=invoke('document.create',id='color-image-edit',kind='raster',width=64,height=48)
    document=invoke('document.edit',document=document,expected_revision=0,operations=[dict(op='asset_put',id='source',asset=asset),dict(op='add',item=dict(id='picture',content=dict(type='image',asset_id='source',width=64,height=48)))])['document']
    args=dict(session_root=str(output/'sessions'),session_id='color-image-edit')
    resources=dict(asset_root=str(output/'assets'))
    invoke('session.create',**args,request_id='create',document=document,resources=resources)
    def publish(revision,name,format='png'):
        return invoke('session.publish',**args,expected_revision=revision,output=dict(output_root=str(output),file_name=name,format=format))
    receipts=[publish(0,'original.json','snapshot'),publish(0,'before.png')]
    table=[[r*g,b,1-r] for b in (0,1) for g in (0,1) for r in (0,1)]
    lookup=dict(type='color',adjustment=dict(type='lut3d',size=2,values=table,strength=0.75))
    mask=dict(width=64,height=48,gray_hex=bytes(x*4 for y in range(48) for x in range(64)).hex())
    item=dict(id='recolor',name='Editable color treatment',opacity=0.8,mask=mask,content=dict(type='adjustment',adjustment=dict(clip_to='picture',operators=[lookup])))
    lookup_doc=invoke('session.apply',**args,expected_revision=0,request_id='lookup',action=dict(type='edit',operations=[dict(op='add',item=item)]))['document']
    receipts.extend([publish(1,'lookup.json','snapshot'),publish(1,'lookup.png')])
    palette=dict(type='color',adjustment=dict(type='gradient_map',stops=[dict(offset=0,color=[0.04,0.1,0.25]),dict(offset=1,color=[0.95,0.7,0.15])]))
    palette_doc=invoke('session.apply',**args,expected_revision=1,request_id='palette',action=dict(type='edit',operations=[dict(op='adjustment',id='recolor',adjustment=dict(clip_to='picture',operators=[palette]))]))['document']
    receipts.extend([publish(2,'palette.json','snapshot'),publish(2,'palette.png')])
    comparisons=[invoke('session.diff',**args,from_revision=0,to_revision=n,compare_pixels=True) for n in (1,2)]
    measurements={name:invoke('document.measure',document=doc,**resources) for name,doc in [('before',document),('lookup',lookup_doc),('palette',palette_doc)]}
    invoke('session.apply',**args,expected_revision=2,request_id='undo-palette',action=dict(type='undo'))
    receipts.append(publish(3,'lookup-restored.png'))
    invoke('session.apply',**args,expected_revision=3,request_id='undo-lookup',action=dict(type='undo'))
    receipts.extend([publish(4,'restored.json','snapshot'),publish(4,'restored.png')])
    invoke('session.verify',**args)
    with (output/'measurements.json').open('x',encoding='utf8') as f:json.dump(measurements,f,indent=2);f.write('\n')
    print(json.dumps(dict(receipts=receipts,diffs=comparisons),indent=2))


if __name__=='__main__':main(sys.argv[1])
