"""Create original artwork, publish three image formats and preserve editable sources."""
import argparse
import copy
import json
from pathlib import Path
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    output=parser.parse_args().output.resolve();output.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (output/name).open('x',encoding='utf8',newline='\n') as f:json.dump(value,f,indent=2);f.write('\n')
    width,height=96,64
    d=invoke('document.create',id='original-image-study',kind='raster',width=width,height=height,resolution_ppi=144)
    pixels=bytes(v for y in range(height) for x in range(width) for v in (30+x,40+y*2,50+(x+y)//2,64 if x<16 else 128 if x<32 else 255))
    d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=dict(id='original-pixels',content=dict(type='raster',width=width,height=height,rgba_hex=pixels.hex())))])['document'];before=copy.deepcopy(d)
    outputs=[('snapshot','original.json',None),('png','original.png',None),('tiff','original.tiff',dict(compression='deflate')),('jpeg','delivery.jpg',dict(quality=95,chroma='full',matte=[245,245,245]))]
    for format,name,options in outputs:
        args=dict(output_root=str(output),file_name=name,format=format)
        if options is not None:args['image_options']=options
        save(name+'-receipt.json',invoke('document.publish',document=d,output=args))
    for name in ('original.png','original.tiff','delivery.jpg'):
        imported=invoke('asset.import',source_path=str(output/name),store_root=str(output/'assets'),color_policy='assume_srgb');save(name+'-import.json',imported)
        placed=invoke('document.create',id='roundtrip-'+name.replace('.','-'),kind='raster',width=width,height=height)
        placed=invoke('document.edit',document=placed,expected_revision=0,operations=[dict(op='asset_put',id='source',asset=imported['asset']),dict(op='add',item=dict(id='placed',content=dict(type='image',asset_id='source',width=width,height=height)))])['document']
        save(name+'-roundtrip.json',placed)
        save(name+'-preview-receipt.json',invoke('document.publish',document=placed,resources=dict(asset_root=str(output/'assets')),output=dict(output_root=str(output),file_name=name+'-roundtrip.png',format='png')))
    assert d==before==json.loads((output/'original.json').read_text())
    print('Published lossless PNG/TIFF and explicit-matte JPEG, with editable source and import receipts in '+str(output))


if __name__=='__main__':main()
