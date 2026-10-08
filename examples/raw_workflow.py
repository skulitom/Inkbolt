"""Develop an original calibrated Bayer colour chart with explicit local settings."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    w,h=64,48;black=[64,80,96,112];colors=[0,1,1,2]
    codes=[]
    for y in range(h):
        for x in range(w):
            site=y%2*2+x%2;c=colors[site]
            scene=[128+32*x,128+40*y,384 if (x//16+y//12)%2 else 1536]
            codes.append(black[site]+scene[c])
    source=out/'original.sensor'
    with source.open('xb') as f:f.write(struct.pack('<'+'H'*len(codes),*codes))
    source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    capture=dict(width=w,height=h,packing='u16_le',row_stride=w*2,pattern='rggb',black=black,
                 white=[v+2048 for v in black],camera_to_linear_srgb=[[1,0,0],[0,1,0],[0,0,1]])
    for name,gains,exposure in [('neutral',[1,1,1],0),('warmer',[1.25,1,.75],0),('brighter',[1,1,1],1)]:
        settings=dict(exposure_stops=exposure,white_balance=dict(type='gains',rgb=gains),output='srgb16',range='clip',resolution_ppi=300)
        args=dict(source_path=str(source),expected_sha256=source_hash,id='raw-example',capture=capture,settings=settings)
        save(name+'-request.json',dict(command='raw.develop',**args))
        result=invoke('raw.develop',**args);save(name+'-response.json',result);save(name+'.json',result['document']);save(name+'-recipe.json',result['recipe'])
        for fmt in ['png','tiff','snapshot']:
            output=dict(output_root=str(out),file_name=name+'.'+('snapshot.json' if fmt=='snapshot' else fmt),format=fmt)
            if fmt=='tiff':output['image_options']=dict(depth='u16',channels='rgba')
            receipt=invoke('document.publish',document=result['document'],output=output)
            save(name+'-'+fmt+'-receipt.json',receipt)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
    print('Saved original sensor bytes, three developments, recipes and PNG/TIFF/snapshot deliveries in '+str(out))


if __name__=='__main__':main()
