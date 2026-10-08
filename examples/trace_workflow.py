"""Trace an original cell icon, retain source bytes and publish editable deliveries."""
import argparse
import base64
import json
from pathlib import Path
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    w,h=48,40;colors=[]
    for y in range(h):
        for x in range(w):
            radius=(x+.5-18)**2+(y+.5-20)**2
            c=[24,100,210,255] if 36<=radius<=196 else [0,0,0,0]
            if 31<=x<43 and 10<=y<30:c=[240,90,25,128]
            if (x,y) in [(3,2),(5,4)]:c=[50,180,90,255]
            if (x,y)==(38,18):c=[0,0,0,0]
            colors+=c
    source=dict(type='pixels',width=w,height=h,rgba_hex=bytes(colors).hex());save('source-pixels.json',source)
    raster=invoke('document.create',id='original-trace-input',kind='raster',width=w,height=h)
    raster=invoke('document.edit',document=raster,expected_revision=0,operations=[dict(op='add',item=dict(id='source',content=dict(type='raster',width=w,height=h,rgba_hex=source['rgba_hex'])))])['document']
    encoded=invoke('document.export',document=raster,format='png')['data']
    with (out/'source.png').open('xb') as f:f.write(base64.b64decode(encoded))
    imported=invoke('asset.import',source_path=str(out/'source.png'),store_root=str(out/'assets'));save('source-import.json',imported)
    for name,controls in [('exact',dict()),('cleaned',dict(min_region_pixels=2,max_hole_pixels=1))]:
        result=invoke('image.trace',id='original-traced-icon',source=dict(type='asset',asset=imported['asset']),asset_root=str(out/'assets'),options=dict(mode=dict(type='exact'),**controls))
        save(name+'-trace.json',result);document=result['document']
        for format,extension in [('snapshot','json'),('png','png'),('tiff','tif'),('svg','svg')]:
            save(name+'-'+format+'-receipt.json',invoke('document.publish',document=document,output=dict(output_root=str(out),file_name=name+'.'+extension,format=format)))
    print('Saved original source, trace parameters, editable paths and PNG/TIFF/SVG delivery in '+str(out))


if __name__=='__main__':main()
