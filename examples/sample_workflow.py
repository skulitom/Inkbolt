"""Original precision ramp and native patch, with retained source and depth delivery."""
import argparse
import copy
import json
from pathlib import Path
import struct
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    def publish(d,name,format,**kw):
        save(name+'-receipt.json',invoke('document.publish',document=d,output=dict(output_root=str(out),file_name=name,format=format,**kw)))
    d=invoke('document.create',id='precise-ramp',kind='raster',width=96,height=32)
    values=[v for y in range(32) for x in range(96) for v in [12000+x*23,18000+y*31,32000+x*7+y*11,65535]]
    data=struct.pack('<'+'H'*len(values),*values).hex()
    d['items']=[dict(id='pixels',content=dict(type='samples',grid=dict(width=96,height=32,depth='u16',channels='rgba',data_hex=data)))]
    d=invoke('document.validate',document=d);source=copy.deepcopy(d);publish(d,'original.json','snapshot')
    patch=struct.pack('<4H',40001,20003,10007,50009).hex()*64
    edit=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='sample_replace',id='pixels',region=dict(x=8,y=8,width=8,height=8),data_hex=patch)])
    save('edit-receipt.json',edit);edited=edit['document'];publish(edited,'edited.json','snapshot')
    for depth in ['u16','f32']:publish(edited,depth+'.tiff','tiff',image_options=dict(depth=depth,compression='deflate'))
    publish(edited,'preview.png','png');save('inspection.json',invoke('document.inspect',document=edited))
    assert d==source
    print('Saved retained samples, exact native patch, explicit TIFF depths and a display preview in '+str(out))


if __name__=='__main__':main()
