"""Import once, place/crop/transform reusable images, and export into a new directory."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
from render_example import invoke


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--color-policy',choices=['require_srgb','assume_srgb'],default='require_srgb')
    args=parser.parse_args()
    source=args.source.resolve(strict=True)
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    output=args.output_dir.resolve()
    output.mkdir(parents=True,exist_ok=False)
    store=output/'assets'
    imported=invoke(dict(command='asset.import',source_path=str(source),store_root=str(store),color_policy=args.color_policy))
    asset=imported['asset']
    document=invoke(dict(command='document.create',id='image-layout',kind='vector',width=640,height=360))
    def rect(id,x,y,w,h,color):
        return dict(id=id,content=dict(type='vector',geometry=dict(shape='rect',x=x,y=y,width=w,height=h),fill=color))
    def picture(id,asset_id,width,height,matrix,crop=None):
        return dict(id=id,transform=matrix,content=dict(type='image',asset_id=asset_id,width=width,height=height,crop=crop,sampling='bilinear'))
    fit=min(280/asset['width'],180/asset['height'])
    width,height=asset['width']*fit,asset['height']*fit
    crop=dict(x=asset['width']//4,y=asset['height']//4,width=max(1,asset['width']//2),height=max(1,asset['height']//2))
    items=[
        rect('backdrop',0,0,640,360,[233,238,246,255]),
        rect('left-card',16,16,300,220,[255,255,255,255]),
        rect('right-card',324,16,300,220,[255,255,255,255]),
        picture('whole','original',width,height,[1,0,0,1,26+(280-width)/2,26+(180-height)/2]),
        picture('detail','original',280,180,[1,0,0,1,334,26],crop),
        rect('left-accent',32,216,76,4,[57,89,140,255]),
        rect('right-accent',340,216,116,4,[57,89,140,255]),
        picture('reflected','original',120,65,[-1,0,0,1,260,266]),
        picture('turned','original',96,52,[0,1,-1,0,438,244]),
    ]
    document=invoke(dict(command='document.edit',document=document,expected_revision=0,operations=[dict(op='asset_put',id='original',asset=asset)]+[dict(op='add',item=i) for i in items]))['document']
    for name,value in [('document.json',document),('import.json',imported),('inspection.json',invoke(dict(command='document.inspect',document=document)))]:
        with (output/name).open('x',encoding='utf8') as stream:
            json.dump(value,stream,indent=2)
    for format in ['png','svg']:
        result=invoke(dict(command='document.export',document=document,format=format,asset_root=str(store)))
        data=base64.b64decode(result['data']) if result['encoding']=='base64' else result['data'].encode()
        with (output/f'layout.{format}').open('xb') as stream:
            stream.write(data)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before,'Source changed during the example workflow'
    print('Created a reusable image layout, its immutable store and editable snapshot; source bytes unchanged.')


if __name__=='__main__':
    main()
