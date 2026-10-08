"""Keep an original sensor chart editable through lens, noise/detail and sidecar workflows."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    w,h=32,24;black=[64,80,96,112];colors=[0,1,1,2];codes=[]
    for y in range(h):
        for x in range(w):
            site=y%2*2+x%2;c=colors[site];noise=(x*73+y*37+c*19)%129-64
            scene=[128+48*x,128+64*y,384 if x<16 else 1536]
            codes.append(black[site]+scene[c]+noise)
    source=out/'original.sensor'
    with source.open('xb') as f:f.write(struct.pack('<'+'H'*len(codes),*codes))
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    capture=dict(width=w,height=h,packing='u16_le',row_stride=w*2,pattern='rggb',black=black,white=[v+2048 for v in black],camera_to_linear_srgb=[[1,0,0],[0,1,0],[0,0,1]])
    settings=dict(exposure_stops=0,white_balance=dict(type='gains',rgb=[1,1,1]),output='srgb16',range='clip',resolution_ppi=300)
    args=dict(source_path=str(source),id='editable-raw',capture=capture,settings=settings)
    save('retain-request.json',dict(command='raw.retain',**args));original=invoke('raw.retain',**args)['document'];save('retained.json',original)
    lens=dict(center=[15.5,11.5],focal=[32,24],radial=[.25,-.0625,.015625],tangential=[.0078125,-.00390625],border='transparent')
    denoise=dict(radius=2,threshold=.09,amount=.75);detail=dict(radius=1,threshold=.01,amount=.625)
    for name,corrections in [('source',{}),('lens',dict(lens=lens)),('noise-detail',dict(denoise=denoise,detail=detail)),('combined',dict(lens=lens,denoise=denoise,detail=detail))]:
        request=dict(document=original,expected_revision=0,operations=[dict(op='raw_settings',id='raw',settings=settings,corrections=corrections)])
        save(name+'-request.json',dict(command='document.edit',**request));d=invoke('document.edit',**request)['document'];save(name+'.json',d)
        sidecar=invoke('raw.recipe',document=d,id='raw');save(name+'-recipe-receipt.json',sidecar)
        with (out/(name+'.recipe.json')).open('x',encoding='utf8') as f:f.write(sidecar['data'])
        reopened=invoke('raw.reopen',source_path=str(source),recipe_path=str(out/(name+'.recipe.json')),id='editable-raw')['document']
        assert reopened==dict(d,revision=0)
        save(name+'-reopened.json',reopened)
        for fmt in ['png','tiff','snapshot']:
            options=dict(output_root=str(out),file_name=name+'.'+('snapshot.json' if fmt=='snapshot' else fmt),format=fmt)
            if fmt=='tiff':options['image_options']=dict(depth='u16',channels='rgba')
            save(name+'-'+fmt+'-receipt.json',invoke('document.publish',document=d,output=options))
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
    print('Saved four editable developments, pinned sidecars, exact sensor source and PNG/TIFF/snapshot deliveries in '+str(out))


if __name__=='__main__':main()
